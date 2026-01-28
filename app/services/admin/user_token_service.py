from fastapi import HTTPException
from app.models.enums import UserTokenType
from app.schemas.admin.user_tokens import UserTokenCreate
from app.repositories.admin.user_token_repository import UserTokenRepository
import secrets
from datetime import datetime, timedelta, timezone


class UserTokenService:
    def __init__(self, repo: UserTokenRepository):
        self.repo = repo

    async def create(self, data: UserTokenCreate):
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=2)

        return await self.repo.create({
            'user_id': data.user_id,
            'token': token,
            'type': data.type,
            'expires_at': expires_at
        })

    async def getResetPasswordToken(self, token: str):
        user_token = await self.repo.find_by_token(token)

        if not user_token:
            raise HTTPException(status_code=404, detail="Token doesn't exists in the database.")

        if user_token.type != UserTokenType.RESET_PASSWORD:
            raise HTTPException(status_code=404, detail="Invalid token type.")

        if datetime.now(timezone.utc) > user_token.expires_at.replace(tzinfo=timezone.utc):
            raise HTTPException(status_code=404, detail="Token has expired.")

        return user_token

    async def delete(self, id: int):
        return await self.repo.delete(id)