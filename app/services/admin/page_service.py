from app.schemas.admin.pages import PageCreate, PageUpdate
from app.repositories.admin.page_repository import PageRepository
from app.services.admin.base_crud_service import BaseCrudService, CreateSchemaType, ModelType
from app.models.page import Page
from slugify import slugify

class PageService(BaseCrudService[Page, PageCreate, PageUpdate]):
    def __init__(self, repo: PageRepository):
        super().__init__(repo)

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        obj_in.slug = await self._get_slug(obj_in.title)
        return await self.repository.create(obj_in)

    async def update(self, id: int, obj_in: CreateSchemaType) -> ModelType:
        obj_in.slug = await self._get_slug(obj_in.title)
        return await super().update(id, obj_in)

    async def _get_slug(self, title: str) -> str:
        base_slug = slugify(title)
        slug = base_slug
        counter = 1
        while await self.repository.is_slug_exists(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug