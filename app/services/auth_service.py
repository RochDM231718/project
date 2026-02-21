import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
from app.infrastructure.jwt_handler import create_access_token, create_refresh_token, verify_token
import os
import structlog
from datetime import datetime, timedelta
import redis.asyncio as aioredis

logger = structlog.get_logger()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

redis_client = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)


class UserBlockedException(Exception):
    def __init__(self, message="Слишком много попыток. Аккаунт временно заблокирован"):
        self.message = message
        super().__init__(self.message)


class AuthService:
    def __init__(self, repository, user_token_service: UserTokenService):
        self.repository = repository
        self.db = repository.db
        self.user_token_service = user_token_service

    async def authenticate(self, email: str, password: str, role: str = None, ip: str = "unknown"):
        rl_key = f"login_attempts:{ip}:{email}"
        attempts = await redis_client.get(rl_key)

        if attempts and int(attempts) >= 5:
            ttl = await redis_client.ttl(rl_key)
            minutes = int(ttl / 60) + 1
            raise UserBlockedException(f"Слишком много попыток. Повторите через {minutes} мин.")

        user = await self.repository.get_by_email(email)
        if not user:
            pwd_context.hash(password)
            logger.warning("Login failed: user not found", email=email)
            await self._record_failed_attempt(rl_key)
            return None

        if user.status == UserStatus.REJECTED:
            logger.warning("Login failed: user rejected", email=email)
            return None

        if not self.verify_password(password, user.hashed_password):
            logger.warning("Login failed: wrong password", email=email)
            await self._record_failed_attempt(rl_key)
            return None

        await redis_client.delete(rl_key)

        logger.info("User logged in", user_id=user.id, email=user.email)
        return user

    async def _record_failed_attempt(self, key: str):
        await redis_client.incr(key)
        if await redis_client.ttl(key) == -1:
            await redis_client.expire(key, 900)

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
            education_level=data.education_level,
            course=data.course,
            hashed_password=hashed_pw,
            role=UserRole.GUEST,
            status=UserStatus.PENDING,
            is_active=True
        )

        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)

        logger.info("New user registered", email=data.email)
        return new_user

    async def api_authenticate(self, email: str, password: str, role: str = "User", ip: str = "unknown"):
        user = await self.authenticate(email, password, role, ip)
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

    async def api_refresh_token(self, refresh_token: str):
        payload = verify_token(refresh_token, refresh=True)
        if not payload or payload.get('type') != "refresh":
            return None

        user_id = payload.get("sub")
        stmt = select(Users).filter(Users.id == int(user_id))
        result = await self.db.execute(stmt)
        user = result.scalars().first()

        if not user or user.status == UserStatus.REJECTED or not user.is_active:
            logger.warning("Attempt to refresh token for inactive/blocked user", user_id=user_id)
            return None

        token_data = {"sub": str(user.id), "role": user.role.value}
        new_access = create_access_token(token_data)

        return {
            "access_token": new_access,
            "token_type": "bearer"
        }

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def _send_mail_task(self, to_email: str, subject: str, body_text: str, body_html: str):
        smtp_host = os.getenv('MAIL_HOST', 'smtp.yandex.ru')
        smtp_port = int(os.getenv('MAIL_PORT', 465))
        smtp_user = os.getenv('MAIL_USERNAME')
        smtp_pass = os.getenv('MAIL_PASSWORD')
        mail_from = os.getenv('MAIL_FROM', smtp_user)

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = mail_from
        msg['To'] = to_email

        part1 = MIMEText(body_text, 'plain')
        part2 = MIMEText(body_html, 'html')
        msg.attach(part1)
        msg.attach(part2)

        try:
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port)
                server.starttls()

            server.login(smtp_user, smtp_pass)
            server.sendmail(mail_from, to_email, msg.as_string())
            server.quit()

            logger.info(f"Email sent successfully via {smtp_host}:{smtp_port}", to=to_email)
            print(f"[INFO] Email sent to {to_email}")

        except Exception as e:
            logger.error("Failed to send email via SMTP", error=str(e))
            print(f"[ERROR] Mail send failed: {e}")

    async def forgot_password(self, email: str, background_tasks: BackgroundTasks = None):
        user = await self.repository.get_by_email(email)
        if not user:
            return True, "Код отправлен (если аккаунт существует)", 60

        retry_after = await self.user_token_service.get_time_until_next_retry(user.id)
        if retry_after > 0:
            return False, f"Повторная отправка возможна через {retry_after} сек.", retry_after

        token_data = UserTokenCreate(
            user_id=user.id,
            type=UserTokenType.RESET_PASSWORD
        )
        user_token = await self.user_token_service.create(token_data)
        code = user_token.token

        subject = "Разовый код"

        text_content = f"""Здравствуйте, {user.email}!
Мы получили запрос на отправку разового кода для вашей учетной записи Sirius.Achievements.
Ваш разовый код: {code}
Вводите этот код только на официальном сайте."""

        html_content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #000000; background-color: #ffffff; padding: 20px; max-width: 600px;">
            <p style="font-size: 15px; margin-bottom: 20px;">
                Здравствуйте, <a href="mailto:{user.email}" style="color: #0067b8; text-decoration: none;">{user.email}</a>!
            </p>
            <p style="font-size: 15px; margin-bottom: 20px;">
                Мы получили запрос на отправку разового кода для вашей учетной записи Sirius.Achievements.
            </p>
            <p style="font-size: 15px; margin-bottom: 5px;">
                Ваш разовый код: <span style="font-weight: 600; font-size: 16px;">{code}</span>
            </p>
            <p style="font-size: 15px; margin-top: 20px; margin-bottom: 25px;">
                Вводите этот код только на официальном сайте или в приложении. Не делитесь им ни с кем.
            </p>
            <p style="font-size: 15px; margin-bottom: 5px;">
                С уважением,<br>
                Служба технической поддержки Sirius.Achievements
            </p>
            <br>
            <div style="font-size: 12px; color: #666666; margin-top: 20px;">
                <p style="margin-bottom: 5px;">Заявление о конфиденциальности:</p>
                <a href="#" style="color: #0067b8; text-decoration: underline;">https://sirius.achievements/privacy</a>
                <p style="margin-top: 5px;">Sirius Corporation, Russia</p>
            </div>
        </div>
        """

        if background_tasks:
            background_tasks.add_task(self._send_mail_task, to_email=user.email, subject=subject,
                                      body_text=text_content, body_html=html_content)
        else:
            self._send_mail_task(user.email, subject, text_content, html_content)

        return True, "Код успешно отправлен", 60

    async def verify_code_only(self, email: str, code: str) -> bool:
        user = await self.repository.get_by_email(email)
        if not user:
            raise Exception("Пользователь не найден")

        user_token = await self.user_token_service.getResetPasswordToken(code)

        if user_token.user_id != user.id:
            raise Exception("Неверный код подтверждения")

        return True

    async def reset_password_final(self, email: str, new_password: str):
        user = await self.repository.get_by_email(email)
        if not user:
            raise Exception("Пользователь не найден")

        user.hashed_password = pwd_context.hash(new_password)
        self.db.add(user)
        await self.db.commit()
        return user