"""Initialize database tables and seed demo events."""
import os
from database import Base, engine, SessionLocal
import models

def init_and_seed():
    print("Creating database schema...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        count = db.query(models.Event).count()
        if count == 0:
            print("Seeding demo events...")
            demo_events = [
                models.Event(
                    title="Campus Hackathon 2026",
                    description="24-hour sprint building AI, Web, and Cloud applications with student teams.",
                    date="2026-11-15",
                    venue="Main Auditorium, Hall 1",
                    total_seats=50,
                ),
                models.Event(
                    title="Cloud Security & DevSecOps Workshop",
                    description="Hands-on masterclass on load balancing, HTTPS TLS termination, and rate limiting.",
                    date="2026-11-20",
                    venue="Computer Science Lab 3",
                    total_seats=30,
                ),
                models.Event(
                    title="AI Agents & LLM Architecture Summit",
                    description="Deep dive into autonomous reasoning, tool invocation, and multi-agent coordination.",
                    date="2026-12-05",
                    venue="Innovation Center B",
                    total_seats=40,
                ),
            ]
            db.add_all(demo_events)
            db.commit()
            print(f"Successfully seeded {len(demo_events)} events.")
        else:
            print(f"Database already contains {count} events.")
    finally:
        db.close()

if __name__ == "__main__":
    init_and_seed()
