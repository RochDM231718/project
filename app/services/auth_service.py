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
from app.infrastructure.jwt_handler import create_access_token, create_refresh_token, refresh_access_token
import os
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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

        if user.status == UserStatus.REJECTED:
            logger.warning("Login failed: user rejected", email=email)
            return None

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

    # --- НОВАЯ ЛОГИКА ОТПРАВКИ ЧЕРЕЗ SMTPLIB (СТАНДАРТНАЯ) ---

    def _send_mail_task(self, to_email: str, subject: str, body_text: str, body_html: str):
        """
        Отправка письма через стандартный smtplib (самый надежный способ).
        """
        smtp_host = os.getenv('MAIL_HOST', 'smtp.yandex.ru')
        smtp_port = int(os.getenv('MAIL_PORT', 465))
        smtp_user = os.getenv('MAIL_USERNAME')
        smtp_pass = os.getenv('MAIL_PASSWORD')
        mail_from = os.getenv('MAIL_FROM', smtp_user)

        # Формируем сообщение
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = mail_from
        msg['To'] = to_email

        # Добавляем текстовую и HTML версии
        part1 = MIMEText(body_text, 'plain')
        part2 = MIMEText(body_html, 'html')
        msg.attach(part1)
        msg.attach(part2)

        try:
            # Выбираем протокол в зависимости от порта
            if smtp_port == 465:
                # SSL подключение (Implicit SSL)
                server = smtplib.SMTP_SSL(smtp_host, smtp_port)
            else:
                # Обычное подключение + STARTTLS (для 587)
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

        # Генерируем код
        token_data = UserTokenCreate(
            user_id=user.id,
            type=UserTokenType.RESET_PASSWORD
        )
        user_token = await self.user_token_service.create(token_data)
        code = user_token.token

        # Тема и контент
        subject = "Разовый код"

        text_content = f"""Здравствуйте, {user.email}!
Мы получили запрос на отправку разового кода для вашей учетной записи Sirius.Achievements.
Ваш разовый код: {code}
Вводите этот код только на официальном сайте."""

        # HTML в стиле Microsoft
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