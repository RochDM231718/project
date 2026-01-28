from app.repositories.admin.crud_repository import CrudRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.page import Page

class PageRepository(CrudRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db, Page)

    async def is_slug_exists(self, slug: str):
        stmt = select(self.model).filter(Page.slug == slug)
        result = await self.db.execute(stmt)
        return result.scalars().first()