from typing import TypeVar, Type, Generic, Optional, List
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")

class BaseCrudRepository(Generic[T]):
    def __init__(self, db: AsyncSession, model: Type[T]):
        self.db = db
        self.model = model

    async def find(self, id: int) -> Optional[T]:
        stmt = select(self.model).where(self.model.id == id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_all(self) -> List[T]:
        stmt = select(self.model)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create(self, data: dict) -> T:
        instance = self.model(**data)
        self.db.add(instance)
        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def update(self, id: int, data: dict) -> Optional[T]:
        stmt = update(self.model).where(self.model.id == id).values(**data)
        await self.db.execute(stmt)
        await self.db.commit()
        return await self.find(id)

    async def delete(self, id: int) -> bool:
        stmt = delete(self.model).where(self.model.id == id)
        await self.db.execute(stmt)
        await self.db.commit()
        return True