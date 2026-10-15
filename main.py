"""EventEase - secure, load-balanced event registration API (FastAPI)."""
import hmac
import os
import socket
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

import models
from database import Base, engine, get_db
from schemas import EventIn, RegistrationIn

PRODUCTION = os.getenv("ENV") == "production"
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
# Cloud Run sets K_REVISION; the container hostname identifies the instance.
INSTANCE = os.getenv("K_REVISION", "local") + " / " + socket.gethostname()[-8:]

# ---------- Rate limiting ----------
GLOBAL_LIMIT = os.getenv("GLOBAL_LIMIT", "60/minute")
REGISTER_LIMIT = os.getenv("REGISTER_LIMIT", "5/minute")
ADMIN_LIMIT = os.getenv("ADMIN_LIMIT", "10/minute")
limiter = Limiter(key_func=get_remote_address, default_limits=[GLOBAL_LIMIT])


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError:
        pass  # another instance created the tables at the same moment
    yield


app = FastAPI(title="EventEase", lifespan=lifespan,
              docs_url=None if PRODUCTION and not os.getenv("SHOW_DOCS") else "/docs",
              redoc_url=None)
app.state.limiter = limiter

# ---------- HTTPS ----------
if PRODUCTION:
    app.add_middleware(HTTPSRedirectMiddleware)
if os.getenv("ALLOWED_HOSTS"):
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=os.getenv("ALLOWED_HOSTS").split(","))


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429,
                        headers={"Retry-After": "60"},
                        content={"detail": "Too many requests. Please wait a minute and try again."})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com data:; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'")
    h["X-Served-By"] = INSTANCE
    if request.url.path.startswith("/api"):
        h["Cache-Control"] = "no-store"   # never cache API responses
    return response


# ---------- Admin auth ----------
def require_admin(x_admin_key: str = Header(default="")):
    if not ADMIN_KEY:
        raise HTTPException(503, "Admin access is not configured on this server")
    if not hmac.compare_digest(x_admin_key.encode(), ADMIN_KEY.encode()):
        raise HTTPException(401, "Invalid admin key")


def event_out(ev: models.Event, taken: int):
    return {"id": ev.id, "title": ev.title, "description": ev.description,
            "date": ev.date, "venue": ev.venue, "total_seats": ev.total_seats,
            "seats_left": max(ev.total_seats - taken, 0)}


# ---------- Routes ----------
@app.get("/healthz")
@limiter.exempt
def health(request: Request):
    return {"status": "ok"}


@app.get("/api/info")
def info(request: Request):
    return {"served_by": INSTANCE}


@app.get("/api/events")
def list_events(request: Request, db: Session = Depends(get_db)):
    counts = dict(db.query(models.Registration.event_id, func.count())
                  .group_by(models.Registration.event_id).all())
    events = db.query(models.Event).order_by(models.Event.date, models.Event.id).all()
    return [event_out(e, counts.get(e.id, 0)) for e in events]


@app.post("/api/events/{event_id}/register", status_code=201)
@limiter.limit(REGISTER_LIMIT)
def register(request: Request, event_id: int, data: RegistrationIn,
             db: Session = Depends(get_db)):
    # Row lock (Postgres) so two instances can't oversell the last seat.
    ev = db.query(models.Event).filter(models.Event.id == event_id) \
           .with_for_update().first()
    if not ev:
        raise HTTPException(404, "Event not found")
    taken = db.query(func.count(models.Registration.id)) \
              .filter(models.Registration.event_id == event_id).scalar()
    if taken >= ev.total_seats:
        raise HTTPException(409, "This event is full")
    db.add(models.Registration(event_id=event_id, name=data.name, roll_no=data.roll_no))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This roll number is already registered for this event")
    return {"message": "Registered successfully", "seats_left": ev.total_seats - taken - 1}


@app.post("/api/admin/events", status_code=201, dependencies=[Depends(require_admin)])
@limiter.limit(ADMIN_LIMIT)
def create_event(request: Request, data: EventIn, db: Session = Depends(get_db)):
    ev = models.Event(**data.model_dump())
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return event_out(ev, 0)


@app.delete("/api/admin/events/{event_id}", dependencies=[Depends(require_admin)])
@limiter.limit(ADMIN_LIMIT)
def delete_event(request: Request, event_id: int, db: Session = Depends(get_db)):
    ev = db.get(models.Event, event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    db.delete(ev)
    db.commit()
    return {"message": "Event deleted"}


@app.get("/api/admin/events/{event_id}/registrations", dependencies=[Depends(require_admin)])
@limiter.limit(ADMIN_LIMIT)
def registrations(request: Request, event_id: int, db: Session = Depends(get_db)):
    rows = db.query(models.Registration).filter_by(event_id=event_id) \
             .order_by(models.Registration.id).all()
    return [{"id": r.id, "name": r.name, "roll_no": r.roll_no,
             "registered_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


# Must be last so it doesn't shadow /api routes
app.mount("/", StaticFiles(directory="static", html=True), name="static")
