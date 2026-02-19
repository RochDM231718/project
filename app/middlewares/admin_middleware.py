import os
import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, HTTPException
from sqlalchemy import select, func
from app.infrastructure.tranaslations import current_locale
from app.infrastructure.database.connection import db_instance
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.enums import UserStatus, AchievementStatus, UserRole

redis_client = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
CACHE_TTL = 60


class GlobalContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            locale = request.session.get('locale', 'en')
        except AssertionError:
            locale = 'en'

        token = current_locale.set(locale)

        try:
            pending_users = await redis_client.get("admin:pending_users")
            pending_ach = await redis_client.get("admin:pending_achievements")

            if pending_users is None or pending_ach is None:
                async with db_instance.session_factory() as db:
                    query_users = select(func.count()).select_from(Users).where(Users.status == UserStatus.PENDING)
                    result_users = await db.execute(query_users)
                    pending_users_val = result_users.scalar()

                    query_ach = select(func.count()).select_from(Achievement).where(
                        Achievement.status == AchievementStatus.PENDING)
                    result_ach = await db.execute(query_ach)
                    pending_achievements_val = result_ach.scalar()

                    await redis_client.set("admin:pending_users", pending_users_val, ex=CACHE_TTL)
                    await redis_client.set("admin:pending_achievements", pending_achievements_val, ex=CACHE_TTL)

                    pending_users = pending_users_val
                    pending_ach = pending_achievements_val
            else:
                pending_users = int(pending_users)
                pending_ach = int(pending_ach)

            request.state.app_name = "Sirius Achievements"
            request.state.pending_users_count = pending_users
            request.state.pending_achievements_count = pending_ach

        except Exception as e:
            print(f"Middleware DB/Cache Error: {e}")
            request.state.pending_users_count = 0
            request.state.pending_achievements_count = 0

        response = await call_next(request)

        current_locale.reset(token)

        return response


async def auth(request: Request):
    auth_id = request.session.get("auth_id")

    if not auth_id:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            raise HTTPException(status_code=401, detail="Unauthorized")
        raise HTTPException(status_code=302, headers={"Location": "/sirius.achievements/login"})

    async with db_instance.session_factory() as db:
        stmt = select(Users).filter(Users.id == int(auth_id))
        result = await db.execute(stmt)
        user = result.scalars().first()

        if not user or user.status == UserStatus.REJECTED or not user.is_active:
            request.session.clear()
            raise HTTPException(status_code=302, headers={"Location": "/sirius.achievements/login"})

        if user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                raise HTTPException(status_code=403, detail="Forbidden")
            raise HTTPException(status_code=403, detail="Доступ запрещен")

        request.state.admin_user = user