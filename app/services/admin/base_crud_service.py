from typing import Generic, TypeVar, List, Optional
from app.repositories.admin.base import AbstractRepository

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")

class BaseCrudService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, repository: AbstractRepository):
        self.repository = repository

    async def find(self, id: int) -> Optional[ModelType]:
        return await self.repository.find(id)

    async def get(self, filters: dict = None) -> List[ModelType]:
        return await self.repository.get(filters)

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        return await self.repository.create(obj_in)

    async def update(self, id: int, obj_in: UpdateSchemaType) -> Optional[ModelType]:
        return await self.repository.update(id, obj_in)

    async def delete(self, id: int) -> None:
        return await self.repository.delete(id)