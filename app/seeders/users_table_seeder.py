from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from app.models.user import Users
from app.models.enums import UserRole, UserStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UsersTableSeeder:
    @staticmethod
    async def run(db: AsyncSession):
        result = await db.execute(select(Users).limit(1))
        if result.scalars().first():
            print("   Skipping users (already exist)")
            return

        print("   Seeding users...")

        admin = Users(
            email="super.admin@example.com",
            hashed_password=pwd_context.hash("secret"),
            first_name="Super",
            last_name="Admin",
            role=UserRole.SUPER_ADMIN.value,
            status=UserStatus.ACTIVE.value,
            is_active=True
        )
        db.add(admin)

        moderator = Users(
            email="moderator@example.com",
            hashed_password=pwd_context.hash("secret"),
            first_name="Moderator",
            last_name="User",
            role=UserRole.MODERATOR.value,
            status=UserStatus.ACTIVE.value,
            is_active=True
        )
        db.add(moderator)

        student = Users(
            email="student@example.com",
            hashed_password=pwd_context.hash("secret"),
            first_name="Student",
            last_name="User",
            role=UserRole.STUDENT.value,
            status=UserStatus.ACTIVE.value,
            is_active=True
        )
        db.add(student)

        await db.commit()