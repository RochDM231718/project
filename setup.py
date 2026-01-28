import asyncio
from passlib.context import CryptContext
from sqlalchemy import select, text
from app.infrastructure.database import engine, Base, async_session_maker

# Import all models to ensure they are registered
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.notification import Notification
from app.models.enums import UserRole, UserStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def init_db_and_create_admin():
    print("1. RESETTING DATABASE (PostgreSQL)...")
    async with engine.begin() as conn:
        # Forcefully drop tables with CASCADE to handle foreign keys
        print("   -> Dropping existing tables (CASCADE)...")
        # We drop known tables in specific order or just drop public schema if needed.
        # For safety, let's drop specific tables with cascade.
        await conn.execute(text("DROP TABLE IF EXISTS notifications CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS achievements CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS users CASCADE;"))
        # Drop the unexpected table mentioned in the error
        await conn.execute(text("DROP TABLE IF EXISTS user_tokens CASCADE;"))

        print("   -> Creating new tables...")
        await conn.run_sync(Base.metadata.create_all)
    print("   -> Tables created successfully.")

    print("2. CREATING SUPER ADMIN...")
    async with async_session_maker() as session:
        email = "admin@example.com"
        password = "admin"

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
            print(f"   -> Admin created! Email: {email} / Password: {password}")


if __name__ == "__main__":
    asyncio.run(init_db_and_create_admin())