from app.models.user import Users
from app.repositories.admin.crud_repository import CrudRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, desc, asc
from app.schemas.admin.users import UserCreate


class UserRepository(CrudRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db, Users)

    async def get(self, filters: dict = None, sort_by: str = 'id', sort_order: str = 'desc'):
        stmt = select(self.model)

        if filters is not None:
            if 'query' in filters and filters['query'] != '':
                like_term = f"%{filters['query']}%"
                stmt = stmt.filter(
                    or_(
                        self.model.first_name.ilike(like_term),
                        self.model.last_name.ilike(like_term),
                        self.model.email.ilike(like_term),
                        self.model.phone_number.ilike(like_term),
                    )
                )

            if 'role' in filters and filters['role']:
                stmt = stmt.filter(self.model.role == filters['role'])

            if 'status' in filters and filters['status']:
                stmt = stmt.filter(self.model.status == filters['status'])

            if 'email' in filters and filters['email']:
                stmt = stmt.filter(self.model.email == filters['email'])

        if hasattr(self.model, sort_by):
            sort_attr = getattr(self.model, sort_by)
            if sort_order == 'asc':
                stmt = stmt.order_by(asc(sort_attr))
            else:
                stmt = stmt.order_by(desc(sort_attr))
        else:
            stmt = stmt.order_by(desc(self.model.id))

        stmt = self.paginate(stmt, filters)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create(self, obj_in):
        if isinstance(obj_in, UserCreate):
            user_data = obj_in.model_dump(exclude={"password"})
        elif isinstance(obj_in, dict):
            user_data = obj_in
        else:
            user_data = obj_in.dict(exclude={"password"})

        db_obj = self.model(**user_data)
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def update_password(self, id: int, password: str):
        db_obj = await self.find(id)
        if db_obj:
            db_obj.hashed_password = password
            await self.db.commit()
            await self.db.refresh(db_obj)

    async def hard_delete(self, id: int):
        return await self.delete(id)