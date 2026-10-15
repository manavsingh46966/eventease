"""Database setup. SQLite locally, shared Postgres (e.g. Neon) in the cloud."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

url = os.getenv("DATABASE_URL", "sqlite:///./eventease.db")

# Neon / Heroku style URLs start with postgres:// ; SQLAlchemy needs postgresql://
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

kwargs = {}
if url.startswith("sqlite"):
    kwargs["connect_args"] = {"check_same_thread": False}
else:
    kwargs["pool_pre_ping"] = True   # survive idle connections being dropped
    kwargs["pool_size"] = 3
    kwargs["max_overflow"] = 2

engine = create_engine(url, **kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
