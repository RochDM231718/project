from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.repositories.admin.crud_repository import CrudRepository
from app.models.user_token import UserToken

class UserTokenRepository(CrudRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db, UserToken)

    async def find_by_token(self, token: str):
        stmt = select(self.model).filter(UserToken.token == token)
        result = await self.db.execute(stmt)
        return result.scalars().first()