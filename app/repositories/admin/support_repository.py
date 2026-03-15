from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc, func, or_
from sqlalchemy.orm import selectinload
from app.models.support_ticket import SupportTicket
from app.models.support_message import SupportMessage
from app.models.user import Users
from app.models.enums import SupportTicketStatus
from app.repositories.admin.crud_repository import CrudRepository
from app.utils.search import escape_like


class SupportTicketRepository(CrudRepository):
    ITEMS_PER_PAGE = 20

    def __init__(self, db: AsyncSession):
        super().__init__(db, SupportTicket)

    async def get_by_user(self, user_id: int):
        stmt = (
            select(SupportTicket)
            .filter(SupportTicket.user_id == user_id)
            .options(selectinload(SupportTicket.messages))
            .order_by(desc(SupportTicket.updated_at))
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_new_tickets(self, page: int = 1):
        stmt = (
            select(SupportTicket)
            .filter(SupportTicket.status == SupportTicketStatus.OPEN)
            .options(selectinload(SupportTicket.user), selectinload(SupportTicket.messages))
            .order_by(desc(SupportTicket.created_at))
        )
        if page > 0:
            stmt = stmt.limit(self.ITEMS_PER_PAGE).offset(self.ITEMS_PER_PAGE * (page - 1))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def count_new_tickets(self):
        stmt = select(func.count()).select_from(SupportTicket).filter(
            SupportTicket.status == SupportTicketStatus.OPEN
        )
        result = await self.db.execute(stmt)
        return result.scalar()

    async def get_all_tickets(self, filters: dict = None, sort_by: str = 'created_at', sort_order: str = 'desc'):
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.user), selectinload(SupportTicket.messages))
        )

        if filters:
            if filters.get('status'):
                stmt = stmt.filter(SupportTicket.status == filters['status'])
            if filters.get('query'):
                like_term = f"%{escape_like(filters['query'])}%"
                stmt = stmt.join(Users).filter(
                    or_(
                        SupportTicket.subject.ilike(like_term),
                        Users.first_name.ilike(like_term),
                        Users.last_name.ilike(like_term),
                        Users.email.ilike(like_term),
                    )
                )

        if hasattr(SupportTicket, sort_by):
            sort_attr = getattr(SupportTicket, sort_by)
            stmt = stmt.order_by(asc(sort_attr) if sort_order == 'asc' else desc(sort_attr))
        else:
            stmt = stmt.order_by(desc(SupportTicket.created_at))

        if filters and filters.get('page', 0) > 0:
            stmt = stmt.limit(self.ITEMS_PER_PAGE).offset(self.ITEMS_PER_PAGE * (filters['page'] - 1))

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def count_all_tickets(self, filters: dict = None):
        stmt = select(func.count()).select_from(SupportTicket)
        if filters:
            if filters.get('status'):
                stmt = stmt.filter(SupportTicket.status == filters['status'])
            if filters.get('query'):
                like_term = f"%{escape_like(filters['query'])}%"
                stmt = stmt.join(Users).filter(
                    or_(
                        SupportTicket.subject.ilike(like_term),
                        Users.first_name.ilike(like_term),
                        Users.last_name.ilike(like_term),
                        Users.email.ilike(like_term),
                    )
                )
        result = await self.db.execute(stmt)
        return result.scalar()

    async def find_with_messages(self, ticket_id: int):
        stmt = (
            select(SupportTicket)
            .filter(SupportTicket.id == ticket_id)
            .options(
                selectinload(SupportTicket.user),
                selectinload(SupportTicket.messages).selectinload(SupportMessage.sender)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()


class SupportMessageRepository(CrudRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db, SupportMessage)
