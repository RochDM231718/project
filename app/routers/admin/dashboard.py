from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, literal_column
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
import json

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.enums import AchievementStatus, UserRole, UserStatus
# Импортируем из deps, чтобы избежать Circular Import
from app.routers.admin.deps import get_current_user

router = guard_router


@router.get('/dashboard', response_class=HTMLResponse, name='admin.dashboard.index')
async def index(request: Request, period: str = 'all', db: AsyncSession = Depends(get_db)):
    # 1. Получаем пользователя
    user = await get_current_user(request, db)

    if not user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    # 2. Безопасное определение роли (строковое сравнение)
    # Это защищает от падения, если в Enum нет значения или оно отличается регистром
    current_role = str(user.role.value) if hasattr(user.role, 'value') else str(user.role)

    # Список ролей с доступом к админской статистике
    admin_roles = ["MODERATOR", "SUPER_ADMIN", "ADMIN", "moderator", "super_admin", "admin"]

    # --- ПРОВЕРКА НА МОДЕРАЦИЮ ---
    # Если пользователь не одобрен и он не админ/модер, показываем заглушку
    if user.status == UserStatus.PENDING and current_role not in admin_roles:
        return templates.TemplateResponse('dashboard/index.html', {
            'request': request,
            'user': user,
            'pending_review': True,
            'stats': {},
            'period': period
        })

    # 3. ОПРЕДЕЛЕНИЕ ПЕРИОДА ДЛЯ СТАТИСТИКИ
    now = datetime.now()
    start_date = None

    if period == 'day':
        start_date = now - timedelta(days=1)
        date_trunc = 'hour'
        date_fmt = '%H:00'
    elif period == 'week':
        start_date = now - timedelta(weeks=1)
        date_trunc = 'day'
        date_fmt = '%d.%m'
    elif period == 'month':
        start_date = now - timedelta(days=30)
        date_trunc = 'day'
        date_fmt = '%d.%m'
    else:  # all
        start_date = datetime(2020, 1, 1)
        date_trunc = 'month'
        date_fmt = '%m.%Y'

    stats = {}

    # --- ЛОГИКА АДМИНА/МОДЕРАТОРА ---
    if current_role in admin_roles:
        new_users = (await db.execute(
            select(func.count()).filter(Users.role == UserRole.STUDENT, Users.created_at >= start_date))).scalar()

        ach_stats = (await db.execute(
            select(
                func.count().filter(Achievement.status == AchievementStatus.PENDING,
                                    Achievement.created_at >= start_date).label('pending'),
                func.count().filter(Achievement.status == AchievementStatus.APPROVED,
                                    Achievement.updated_at >= start_date).label('approved'),
                func.count().filter(Achievement.created_at >= start_date).label('total')
            )
        )).first()

        top_students_stmt = (
            select(Users, func.sum(Achievement.points).label('points'))
            .join(Achievement, Users.id == Achievement.user_id)
            .filter(
                Achievement.status == AchievementStatus.APPROVED,
                Achievement.updated_at >= start_date
            )
            .group_by(Users.id)
            .order_by(desc('points'))
            .limit(5)
        )
        top_students = (await db.execute(top_students_stmt)).all()

        recent_docs_stmt = (
            select(Achievement)
            .options(selectinload(Achievement.user))
            .join(Users)
            .filter(Achievement.created_at >= start_date)
            .order_by(Achievement.created_at.desc())
            .limit(5)
        )
        recent_docs = (await db.execute(recent_docs_stmt)).scalars().all()

        chart_query = (
            select(
                func.date_trunc(date_trunc, Achievement.created_at).label('d_date'),
                func.count().label('cnt')
            )
            .filter(Achievement.created_at >= start_date)
            .group_by(literal_column('d_date'))
            .order_by(literal_column('d_date'))
        )
        chart_res = (await db.execute(chart_query)).all()

        c_labels = [row.d_date.strftime(date_fmt) for row in chart_res] if chart_res else []
        c_data = [row.cnt for row in chart_res] if chart_res else []

        stats = {
            'new_users': new_users,
            'pending_docs': ach_stats.pending,
            'approved_docs': ach_stats.approved,
            'total_docs': ach_stats.total,
            'top_students': top_students,
            'recent_docs': recent_docs,
            'chart_labels': json.dumps(c_labels),
            'chart_data': json.dumps(c_data)
        }

    # --- ЛОГИКА СТУДЕНТА ---
    else:
        my_points = (await db.execute(
            select(func.coalesce(func.sum(Achievement.points), 0))
            .filter(
                Achievement.user_id == user.id,
                Achievement.status == AchievementStatus.APPROVED,
                Achievement.updated_at >= start_date
            )
        )).scalar()

        doc_stats = (await db.execute(
            select(
                func.count().filter(Achievement.user_id == user.id, Achievement.created_at >= start_date).label(
                    'total'),
                func.count().filter(Achievement.user_id == user.id, Achievement.status == AchievementStatus.PENDING,
                                    Achievement.created_at >= start_date).label('pending'),
                func.count().filter(Achievement.user_id == user.id, Achievement.status == AchievementStatus.APPROVED,
                                    Achievement.updated_at >= start_date).label('approved'),
                func.count().filter(Achievement.user_id == user.id, Achievement.status == AchievementStatus.REJECTED,
                                    Achievement.updated_at >= start_date).label('rejected')
            )
        )).first()

        subquery_points = (
            select(Achievement.user_id, func.sum(Achievement.points).label('total_points'))
            .filter(
                Achievement.status == AchievementStatus.APPROVED,
                Achievement.updated_at >= start_date
            )
            .group_by(Achievement.user_id)
            .subquery()
        )

        if my_points > 0:
            rank_stmt = select(func.count()).filter(subquery_points.c.total_points > my_points)
            better_than_me = (await db.execute(rank_stmt)).scalar() or 0
            my_rank = better_than_me + 1
        else:
            my_rank = 0

        recent_docs = (await db.execute(
            select(Achievement)
            .filter(Achievement.user_id == user.id, Achievement.created_at >= start_date)
            .order_by(Achievement.created_at.desc())
            .limit(5)
        )).scalars().all()

        cat_stats = (await db.execute(
            select(Achievement.category, func.sum(Achievement.points))
            .filter(
                Achievement.user_id == user.id,
                Achievement.status == AchievementStatus.APPROVED,
                Achievement.updated_at >= start_date
            )
            .group_by(Achievement.category)
        )).all()

        c_labels = [row[0].value for row in cat_stats if row[0]]
        c_data = [row[1] for row in cat_stats if row[0]]

        stats = {
            'my_points': my_points,
            'rank': my_rank,
            'total_docs': doc_stats.total,
            'pending_docs': doc_stats.pending,
            'approved_docs': doc_stats.approved,
            'rejected_docs': doc_stats.rejected,
            'recent_docs': recent_docs,
            'chart_labels': json.dumps(c_labels),
            'chart_data': json.dumps(c_data)
        }

    return templates.TemplateResponse('dashboard/index.html', {
        'request': request,
        'user': user,
        'stats': stats,
        'period': period
    })