import sys
from app.core.database import SessionLocal
from app.simulator.seed_data import seed_database

def main():
    force = "--force" in sys.argv
    db = SessionLocal()
    try:
        seed_database(db, force=force)
    finally:
        db.close()

if __name__ == "__main__":
    main()
