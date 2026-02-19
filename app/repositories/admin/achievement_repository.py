from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.repositories.admin.base_crud_repository import BaseCrudRepository
from app.models.achievement import Achievement


class AchievementRepository(BaseCrudRepository):
    def __init__(self, db):
        super().__init__(db, Achievement)

    async def get_all_with_filters(
            self,
            search: str = "",
            status: str = "",
            category: str = "",
            level: str = "",
            sort_by: str = "newest"
    ):
        """
        Получение списка достижений с фильтрацией и сортировкой.
        """
        # Начинаем запрос с подгрузкой данных пользователя (join)
        stmt = select(self.model).options(selectinload(self.model.user))

        # Поиск по названию (регистронезависимый)
        if search:
            stmt = stmt.filter(self.model.title.ilike(f"%{search}%"))

        # Фильтры по статусу, категории и уровню
        # Проверяем, что значение не пустое и не равно 'all' (значение по умолчанию в фильтрах)
        if status and status != "all":
            stmt = stmt.filter(self.model.status == status)

        if category and category != "all":
            stmt = stmt.filter(self.model.category == category)

        if level and level != "all":
            stmt = stmt.filter(self.model.level == level)

        # Сортировка
        if sort_by == "oldest":
            stmt = stmt.order_by(self.model.created_at.asc())
        elif sort_by == "level":
            stmt = stmt.order_by(self.model.level.asc())
        elif sort_by == "category":
            stmt = stmt.order_by(self.model.category.asc())
        else:
            # По умолчанию: сначала новые
            stmt = stmt.order_by(self.model.created_at.desc())

        result = await self.db.execute(stmt)
        return result.scalars().all()