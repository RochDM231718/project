import sys
import os
from dotenv import load_dotenv

sys.path.append(os.getcwd())

load_dotenv()

from sqlalchemy import text
from app.infrastructure.database.connection import get_database_connection


def check():
    print(f"Connecting to database as user: {os.getenv('DB_USERNAME')}...")
    try:
        db = get_database_connection().get_session()

        sql = "SELECT enum_range(NULL::userstatus)"
        result = db.execute(text(sql)).scalar()
        print(f"Current values in 'userstatus' enum: {result}")

        if 'rejected' in result and 'deleted' in result:
            print("SUCCESS: Database has the new values.")
        else:
            print("MISSING: 'rejected' or 'deleted' is missing.")

        db.close()
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    check()