import sys
import os
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from sqlalchemy import text
from app.infrastructure.database.connection import get_database_connection


def fix_enums():
    print(f"Connecting to database as user: {os.getenv('DB_USERNAME')}...")
    db = get_database_connection().get_session()

    commands = [
        "ALTER TYPE userstatus ADD VALUE 'rejected'",
        "ALTER TYPE userstatus ADD VALUE 'deleted'"
    ]

    for cmd in commands:
        try:
            db.execute(text(cmd))
            db.commit()
            print(f"Executed: {cmd}")
        except Exception as e:
            db.rollback()
            print(f"Skipped (likely exists): {cmd}")

    db.close()
    print("Done.")


if __name__ == "__main__":
    fix_enums()