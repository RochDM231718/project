from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from sqlalchemy import select, func
from app.infrastructure.tranaslations import current_locale
from app.infrastructure.database.connection import db_instance
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.enums import UserStatus, AchievementStatus


class GlobalContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            locale = request.session.get('locale', 'en')
        except AssertionError:
            locale = 'en'

        token = current_locale.set(locale)

        async with db_instance.session_factory() as db:
            try:
                query_users = select(func.count()).select_from(Users).where(Users.status == UserStatus.PENDING)
                result_users = await db.execute(query_users)
                pending_users = result_users.scalar()

                query_ach = select(func.count()).select_from(Achievement).where(
                    Achievement.status == AchievementStatus.PENDING)
                result_ach = await db.execute(query_ach)
                pending_achievements = result_ach.scalar()

                request.state.app_name = "Sirius Achievements"
                request.state.pending_users_count = pending_users
                request.state.pending_achievements_count = pending_achievements

            except Exception as e:
                print(f"Middleware DB Error: {e}")
                request.state.pending_users_count = 0
                request.state.pending_achievements_count = 0

            response = await call_next(request)

            current_locale.reset(token)

            return response


async def auth(request: Request):
    if not request.session.get("auth_id"):
        from fastapi import HTTPException

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            raise HTTPException(status_code=401, detail="Unauthorized")

        # ИСПРАВЛЕНО: Редирект на новый путь
        raise HTTPException(status_code=302, headers={"Location": "/sirius.achievements/login"})