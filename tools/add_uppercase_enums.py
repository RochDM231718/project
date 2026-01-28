import sys
import os
from dotenv import load_dotenv
from sqlalchemy import text

sys.path.append(os.getcwd())
load_dotenv()

from app.infrastructure.database.connection import get_database_connection


def fix():
    print(" Patching Database with UPPERCASE Enums...")
    db = get_database_connection().get_session()
    commands = [
        "ALTER TYPE userstatus ADD VALUE 'REJECTED'",
        "ALTER TYPE userstatus ADD VALUE 'DELETED'"
    ]

    for cmd in commands:
        try:
            db.execute(text(cmd))
            db.commit()
            print(f" Executed: {cmd}")
        except Exception as e:
            db.rollback()
            print(f" Skipped: {cmd} (Error: {e})")

    print("Done.")
    db.close()


if __name__ == "__main__":
    fix()