from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .base import AbstractRepository
from enum import Enum


class CrudRepository(AbstractRepository):
    ITEMS_PER_PAGE = 20

    def __init__(self, db: AsyncSession, model):
        self.db = db
        self.model = model

    def getDb(self) -> AsyncSession:
        return self.db

    async def find(self, id: int):
        stmt = select(self.model).where(self.model.id == id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get(self, filters: dict = None):
        stmt = select(self.model)
        stmt = self.paginate(stmt, filters)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create(self, obj_in):
        obj_data = obj_in if isinstance(obj_in, dict) else obj_in.dict()
        db_obj = self.model(**obj_data)
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def update(self, id: int, obj_in):
        db_obj = await self.find(id)
        if not db_obj:
            return None

        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.dict(exclude_unset=True)

        for field, value in update_data.items():
            # ИСПРАВЛЕНИЕ: Если значение - Enum, берем его строковое представление
            if isinstance(value, Enum):
                value = value.value

            setattr(db_obj, field, value)

        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, id: int):
        db_obj = await self.find(id)
        if db_obj:
            await self.db.delete(db_obj)
            await self.db.commit()
            return True
        return False

    def paginate(self, stmt, filters):
        if filters is not None and 'page' in filters and filters['page'] > 0:
            stmt = stmt.limit(self.ITEMS_PER_PAGE).offset(self.ITEMS_PER_PAGE * (filters['page'] - 1))
        return stmt