from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import Request
from passlib.context import CryptContext
from app.models.enums import UserTokenType, UserRole, UserStatus
from app.models.user import Users
from app.repositories.admin.user_token_repository import UserTokenRepository
from app.schemas.admin.user_tokens import UserTokenCreate
from app.schemas.admin.auth import UserRegister
from app.services.admin.user_token_service import UserTokenService
from app.routers.admin.admin import templates
from mailbridge import MailBridge
from app.infrastructure.jwt_handler import create_access_token, create_refresh_token, refresh_access_token
import os
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

mailer = MailBridge(provider='smtp',
                    host=os.getenv('MAIL_HOST'),
                    port=os.getenv('MAIL_PORT'),
                    username=os.getenv('MAIL_USERNAME'),
                    password=os.getenv('MAIL_PASSWORD'),
                    use_tls=True,
                    from_email=os.getenv('MAIL_USERNAME')
                    )


class UserBlockedException(Exception):
    def __init__(self, message="Аккаунт временно заблокирован"):
        self.message = message
        super().__init__(self.message)


class AuthService:
    def __init__(self, repository):
        self.repository = repository
        self.db = repository.db

    async def authenticate(self, email: str, password: str, role: str = None):
        user = await self.repository.get_by_email(email)

        if not user:
            logger.warning("Login failed: user not found", email=email)
            return None

        # 1. Проверка блокировки
        if user.blocked_until:
            if user.blocked_until > datetime.utcnow():
                wait_time = user.blocked_until - datetime.utcnow()
                minutes = int(wait_time.total_seconds() / 60) + 1
                raise UserBlockedException(f"Слишком много попыток. Аккаунт заблокирован на {minutes} мин.")
            else:
                user.blocked_until = None
                user.failed_attempts = 0
                self.db.add(user)
                await self.db.commit()

        # 2. Проверка пароля
        if not self.verify_password(password, user.hashed_password):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= 5:
                user.blocked_until = datetime.utcnow() + timedelta(minutes=15)
                logger.warning("User blocked due to too many failed attempts", email=email)

            self.db.add(user)
            await self.db.commit()

            logger.warning("Login failed: wrong password", email=email)
            if user.blocked_until and user.blocked_until > datetime.utcnow():
                raise UserBlockedException("Слишком много попыток. Аккаунт заблокирован на 15 мин.")
            return None

        # 3. Статус REJECTED
        if user.status == UserStatus.REJECTED:
            logger.warning("Login failed: user rejected", email=email)
            return None

        # 4. Успешный вход
        if (user.failed_attempts and user.failed_attempts > 0) or user.blocked_until:
            user.failed_attempts = 0
            user.blocked_until = None
            self.db.add(user)
            await self.db.commit()

        logger.info("User logged in", user_id=user.id, email=user.email)
        return user

    async def api_authenticate(self, email: str, password: str, role: str = "User"):
        user = await self.authenticate(email, password, role)
        if not user:
            return None

        token_data = {"sub": str(user.id), "role": user.role.value}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name
            }
        }

    async def register_user(self, data: UserRegister) -> Users:
        stmt = select(Users).where(Users.email == data.email)
        result = await self.db.execute(stmt)
        if result.scalars().first():
            raise Exception("Пользователь с таким email уже существует")

        hashed_pw = pwd_context.hash(data.password)

        new_user = Users(
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            hashed_password=hashed_pw,
            # ВАЖНО: передаем строку "guest", которая совпадает с тем, что в базе
            role=UserRole.GUEST,
            status=UserStatus.PENDING,
            is_active=True
        )

        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)

        logger.info("New user registered", email=data.email)
        return new_user

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    async def reset_password(self, email: str, request: Request) -> bool:
        return True