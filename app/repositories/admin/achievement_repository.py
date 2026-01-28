from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.repositories.admin.crud_repository import CrudRepository
from app.models.achievement import Achievement


class AchievementRepository(CrudRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db, Achievement)

    async def get_by_user(self, user_id: int, page: int = 1):
        stmt = select(self.model).filter(self.model.user_id == user_id)
        stmt = stmt.order_by(self.model.created_at.desc())
        stmt = self.paginate(stmt, {'page': page})

        result = await self.db.execute(stmt)
        return result.scalars().all()