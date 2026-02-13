from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import Request, BackgroundTasks
from passlib.context import CryptContext
from app.models.enums import UserTokenType, UserRole, UserStatus
from app.models.user import Users
from app.repositories.admin.user_token_repository import UserTokenRepository
from app.schemas.admin.user_tokens import UserTokenCreate
from app.schemas.admin.auth import UserRegister
from app.services.admin.user_token_service import UserTokenService
from mailbridge import MailBridge
from app.infrastructure.jwt_handler import create_access_token, create_refresh_token, refresh_access_token
import os
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Инициализация почты
try:
    mailer = MailBridge(provider='smtp',
                        host=os.getenv('MAIL_HOST'),
                        port=int(os.getenv('MAIL_PORT', 587)),
                        username=os.getenv('MAIL_USERNAME'),
                        password=os.getenv('MAIL_PASSWORD'),
                        use_tls=True,
                        from_email=os.getenv('MAIL_FROM')
                        )
except Exception as e:
    print(f"[CRITICAL] Mailer failed to init: {e}")


class UserBlockedException(Exception):
    def __init__(self, message="Аккаунт временно заблокирован"):
        self.message = message
        super().__init__(self.message)


class AuthService:
    def __init__(self, repository, user_token_service: UserTokenService):
        self.repository = repository
        self.db = repository.db
        self.user_token_service = user_token_service

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

        # 3. Проверка статуса
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
            role=UserRole.STUDENT,
            status=UserStatus.PENDING,
            is_active=True
        )

        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)

        logger.info("New user registered", email=data.email)
        return new_user

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

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    # --- ЛОГИКА СБРОСА ПАРОЛЯ ---

    def _send_mail_task(self, to: str, subject: str, body: str, html: str):
        try:
            mailer.send(to=to, subject=subject, body=body, html=html)
            logger.info("Reset password email sent", to=to)
        except Exception as e:
            logger.error("Failed to send reset email in background", error=str(e))
            print(f"[ERROR] Mail send failed: {e}")

    async def forgot_password(self, email: str, background_tasks: BackgroundTasks = None):
        """
        Возвращает кортеж: (success: bool, message: str, retry_after: int)
        """
        user = await self.repository.get_by_email(email)
        if not user:
            # Имитируем успех для безопасности, но ставим задержку
            return True, "Код отправлен (если аккаунт существует)", 60

        # 1. Проверяем таймер (Rate Limiting)
        retry_after = await self.user_token_service.get_time_until_next_retry(user.id)
        if retry_after > 0:
            return False, f"Повторная отправка возможна через {retry_after} сек.", retry_after

        # 2. Генерируем 6-значный код
        token_data = UserTokenCreate(
            user_id=user.id,
            type=UserTokenType.RESET_PASSWORD
        )
        user_token = await self.user_token_service.create(token_data)

        # 3. Контент письма
        code = user_token.token
        subject = "Код подтверждения"
        text_content = f"Ваш код для сброса пароля: {code}"
        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; text-align: center;">
            <h2>Восстановление пароля</h2>
            <p>Ваш код подтверждения:</p>
            <h1 style="background: #f4f4f4; padding: 10px 20px; display: inline-block; letter-spacing: 5px; border-radius: 8px;">{code}</h1>
            <p style="color: #666; margin-top: 20px;">Введите этот код на сайте.</p>
            <p style="font-size: 12px; color: #999;">Код действителен 1 час.</p>
        </div>
        """

        # 4. Отправляем
        if background_tasks:
            background_tasks.add_task(self._send_mail_task, to=user.email, subject=subject, body=text_content,
                                      html=html_content)
        else:
            self._send_mail_task(user.email, subject, text_content, html_content)

        return True, "Код успешно отправлен", 60

    async def verify_code_only(self, email: str, code: str) -> bool:
        """
        Проверяет, подходит ли код к email.
        """
        user = await self.repository.get_by_email(email)
        if not user:
            raise Exception("Пользователь не найден")

        user_token = await self.user_token_service.getResetPasswordToken(code)

        if user_token.user_id != user.id:
            raise Exception("Неверный код подтверждения")

        return True

    async def reset_password_final(self, email: str, new_password: str):
        """
        Устанавливает новый пароль.
        """
        user = await self.repository.get_by_email(email)
        if not user:
            raise Exception("Пользователь не найден")

        user.hashed_password = pwd_context.hash(new_password)
        self.db.add(user)

        # Опционально: удалить использованные токены
        # await self.user_token_service.delete_all_for_user(user.id, UserTokenType.RESET_PASSWORD)

        await self.db.commit()
        logger.info("Password reset successfully", user_id=user.id)
        return user