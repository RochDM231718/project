from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse  # <--- Добавлено RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case, literal_column
from datetime import datetime, timedelta
import json

from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.enums import AchievementStatus, UserRole

router = guard_router


@router.get('/dashboard', response_class=HTMLResponse, name='admin.dashboard.index')
async def index(request: Request, period: str = 'all', db: AsyncSession = Depends(get_db)):
    user_id = request.session.get('auth_id')

    # Если в сессии нет ID, сразу редирект (чтобы не делать запрос к БД зря)
    if not user_id:
        return RedirectResponse(url='/admin/login', status_code=302)

    user = await db.get(Users, user_id)

    # --- ИСПРАВЛЕНИЕ ОШИБКИ ---
    # Если пользователя удалили или ID в сессии старый/неверный
    if not user:
        return RedirectResponse(url='/admin/login', status_code=302)
    # --------------------------

    # 1. ОПРЕДЕЛЕНИЕ ПЕРИОДА
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
        start_date = datetime(2020, 1, 1)  # Условное начало времен
        date_trunc = 'month'
        date_fmt = '%m.%Y'

    stats = {}

    # --- ЛОГИКА АДМИНА (ПОЛНАЯ СТАТИСТИКА) ---
    if user.role in [UserRole.MODERATOR, UserRole.SUPER_ADMIN]:

        # А. ТЕКСТОВАЯ СТАТИСТИКА (С учетом фильтра времени!)
        # Новые пользователи за период
        new_users = (await db.execute(
            select(func.count()).filter(Users.role == UserRole.STUDENT, Users.created_at >= start_date))).scalar()

        # Документы за период
        ach_stats = (await db.execute(
            select(
                func.count().filter(Achievement.status == AchievementStatus.PENDING,
                                    Achievement.created_at >= start_date).label('pending'),
                func.count().filter(Achievement.status == AchievementStatus.APPROVED,
                                    Achievement.updated_at >= start_date).label('approved'),
                func.count().filter(Achievement.created_at >= start_date).label('total')
            )
        )).first()

        # Б. ТАБЛИЦА: ТОП-5 СТУДЕНТОВ ЗА ЭТОТ ПЕРИОД
        # Считаем сумму баллов только за достижения, обновленные в этот период
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

        # В. ТАБЛИЦА: ПОСЛЕДНИЕ ЗАГРУЗКИ (ДЕТАЛИЗАЦИЯ)
        recent_docs_stmt = (
            select(Achievement).join(Users)
            .filter(Achievement.created_at >= start_date)
            .order_by(Achievement.created_at.desc())
            .limit(5)
        )
        recent_docs = (await db.execute(recent_docs_stmt)).scalars().all()

        # Г. ГРАФИКИ (ДИНАМИКА)
        # График документов
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

    # --- ЛОГИКА СТУДЕНТА (Личная статистика) ---
    else:
        # Мои баллы (Всего)
        my_points = (await db.execute(
            select(func.coalesce(func.sum(Achievement.points), 0)).filter(Achievement.user_id == user_id,
                                                                          Achievement.status == AchievementStatus.APPROVED))).scalar()

        # На проверке
        pending_count = (await db.execute(select(func.count()).filter(Achievement.user_id == user_id,
                                                                      Achievement.status == AchievementStatus.PENDING))).scalar()

        # График: Мои баллы по категориям
        cat_stats = (await db.execute(
            select(Achievement.category, func.sum(Achievement.points))
            .filter(Achievement.user_id == user_id, Achievement.status == AchievementStatus.APPROVED)
            .group_by(Achievement.category)
        )).all()

        c_labels = [row[0].value for row in cat_stats]
        c_data = [row[1] for row in cat_stats]

        stats = {
            'my_points': my_points,
            'pending_count': pending_count,
            'chart_labels': json.dumps(c_labels),
            'chart_data': json.dumps(c_data)
        }

    return templates.TemplateResponse('dashboard/index.html', {
        'request': request,
        'user': user,
        'stats': stats,
        'period': period
    })