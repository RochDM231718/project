import sys
import os
from dotenv import load_dotenv
from sqlalchemy import text

sys.path.append(os.getcwd())
load_dotenv()

from app.infrastructure.database.connection import get_database_connection


def fix():
    print("Fixing Database Enums...")
    db = get_database_connection().get_session()

    values_to_add = ['rejected', 'deleted']

    for val in values_to_add:
        try:
            sql = f"ALTER TYPE userstatus ADD VALUE '{val}'"
            db.execute(text(sql))
            db.commit()
            print(f"Added value: '{val}'")
        except Exception as e:
            db.rollback()
            print(f"Value '{val}' likely exists or error: {e}")

    print("\n Database fix completed.")
    db.close()


if __name__ == "__main__":
    fix()