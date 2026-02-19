from fastapi import HTTPException
from sqlalchemy import select, desc
from app.models.enums import UserTokenType
from app.schemas.admin.user_tokens import UserTokenCreate
from app.repositories.admin.user_token_repository import UserTokenRepository
import secrets
import string
from datetime import datetime, timedelta, timezone


class UserTokenService:
    def __init__(self, repo: UserTokenRepository):
        self.repo = repo

    async def create(self, data: UserTokenCreate):
        token = ''.join(secrets.choice(string.digits) for _ in range(6))

        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        return await self.repo.create({
            'user_id': data.user_id,
            'token': token,
            'token_type': data.type.value if hasattr(data.type, 'value') else data.type,
            'expires_at': expires_at
        })

    async def getResetPasswordToken(self, token: str):
        user_token = await self.repo.find_by_token(token)

        if not user_token:
            raise HTTPException(status_code=404, detail="Неверный код.")

        if user_token.token_type != UserTokenType.RESET_PASSWORD.value:
            raise HTTPException(status_code=404, detail="Неверный тип токена.")

        if datetime.now(timezone.utc) > user_token.expires_at.replace(tzinfo=timezone.utc):
            raise HTTPException(status_code=400, detail="Срок действия кода истек.")

        return user_token

    async def get_time_until_next_retry(self, user_id: int) -> int:

        stmt = select(self.repo.model).where(
            self.repo.model.user_id == user_id,
            self.repo.model.token_type == UserTokenType.RESET_PASSWORD.value
        ).order_by(desc(self.repo.model.created_at)).limit(1)

        result = await self.repo.db.execute(stmt)
        last_token = result.scalars().first()

        if not last_token:
            return 0

        last_created = last_token.created_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        diff = (now - last_created).total_seconds()

        if diff < 60:
            return int(60 - diff)

        return 0

    async def delete(self, id: int):
        return await self.repo.delete(id)