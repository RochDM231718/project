import asyncio
import secrets
import string
import os
from passlib.context import CryptContext
from sqlalchemy import select, text
from app.infrastructure.database import engine, Base, async_session_maker

from app.models.user import Users
from app.models.achievement import Achievement
from app.models.notification import Notification
from app.models.support_ticket import SupportTicket
from app.models.support_message import SupportMessage
from app.models.enums import UserRole, UserStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_secure_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.isupper() for c in password)
                and any(c.islower() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^&*" for c in password)):
            return password


async def init_db_and_create_admin():
    print("1. RESETTING DATABASE (PostgreSQL)...")
    async with engine.begin() as conn:
        print("   -> Dropping existing tables (CASCADE)...")
        await conn.execute(text("DROP TABLE IF EXISTS notifications CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS achievements CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS users CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS user_tokens CASCADE;"))

        print("   -> Creating new tables...")
        await conn.run_sync(Base.metadata.create_all)
    print("   -> Tables created successfully.")

    print("2. CREATING SUPER ADMIN...")
    async with async_session_maker() as session:
        email = os.getenv("ADMIN_EMAIL", "admin@example.com")
        password = os.getenv("ADMIN_PASSWORD") or generate_secure_password()

        stmt = select(Users).where(Users.email == email)
        result = await session.execute(stmt)
        if result.scalars().first():
            print(f"   -> Admin already exists.")
        else:
            new_admin = Users(
                first_name="Super",
                last_name="Admin",
                email=email,
                hashed_password=pwd_context.hash(password),
                role=UserRole.SUPER_ADMIN,
                status=UserStatus.ACTIVE,
                is_active=True
            )
            session.add(new_admin)
            await session.commit()
            print(f"   -> Admin created! Email: {email}")
            if not os.getenv("ADMIN_PASSWORD"):
                # Write generated password to file instead of stdout/logs
                cred_file = ".setup_credentials"
                with open(cred_file, "w") as f:
                    f.write(f"email: {email}\npassword: {password}\n")
                print(f"   -> Credentials saved to {cred_file} (NOT in logs)")
                print(f"   -> IMPORTANT: Change this password immediately after first login!")
            else:
                print(f"   -> Password set from ADMIN_PASSWORD env variable.")


if __name__ == "__main__":
    asyncio.run(init_db_and_create_admin())