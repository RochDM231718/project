import asyncio
from passlib.context import CryptContext
from sqlalchemy import select
from app.infrastructure.database import async_session_maker

# ВАЖНО: Импортируем ВСЕ модели, которые связаны друг с другом
from app.models.user import Users
from app.models.achievement import Achievement  # <-- Добавлен этот импорт, чтобы починить ошибку
from app.models.enums import UserRole, UserStatus

# Настройка хеширования
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def create_super_admin():
    async with async_session_maker() as session:
        email = "admin@example.com"
        password = "admin"

        # Проверяем существование
        try:
            stmt = select(Users).where(Users.email == email)
            result = await session.execute(stmt)
            if result.scalars().first():
                print(f"Пользователь {email} уже существует")
                return
        except Exception as e:
            # Если таблицы вообще нет, упадет здесь, но это не страшно,
            # так как init_db должен был их создать.
            print(f"Ошибка проверки пользователя (возможно таблицы не созданы): {e}")
            return

        # Создаем админа
        admin = Users(
            first_name="Super",
            last_name="Admin",
            email=email,
            hashed_password=pwd_context.hash(password),
            role=UserRole.SUPER_ADMIN,
            status=UserStatus.ACTIVE,
            is_active=True
        )

        session.add(admin)
        await session.commit()
        print(f"Admin created successfully!\nLogin: {email}\nPassword: {password}")


if __name__ == "__main__":
    asyncio.run(create_super_admin())