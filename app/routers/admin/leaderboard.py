from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, desc

from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.enums import UserRole, UserStatus, AchievementStatus

router = guard_router


@router.get('/leaderboard', response_class=HTMLResponse, name='admin.leaderboard.index')
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get('auth_id')
    user = await db.get(Users, user_id)

    # SQL Запрос:
    # 1. Выбрать пользователей (Студентов, Активных)
    # 2. Присоединить (Join) Достижения, которые ОДОБРЕНЫ
    # 3. Посчитать сумму очков (coalesce заменяет NULL на 0, если достижений нет)
    # 4. Сгруппировать по ID пользователя
    # 5. Отсортировать по убыванию баллов

    stmt = (
        select(
            Users,
            func.coalesce(func.sum(Achievement.points), 0).label("total_points"),
            func.count(Achievement.id).label("achievements_count")
        )
        .outerjoin(Achievement, (Users.id == Achievement.user_id) & (Achievement.status == AchievementStatus.APPROVED))
        .filter(Users.role == UserRole.STUDENT, Users.status == UserStatus.ACTIVE)
        .group_by(Users.id)
        .order_by(desc("total_points"), desc("achievements_count"))
    )

    result = await db.execute(stmt)
    leaderboard = result.all()  # Возвращает список кортежей (User, points, count)

    # Находим место текущего пользователя
    my_rank = 0
    my_points = 0
    for idx, (u, pts, cnt) in enumerate(leaderboard, 1):
        if u.id == user_id:
            my_rank = idx
            my_points = pts
            break

    return templates.TemplateResponse('leaderboard/index.html', {
        'request': request,
        'leaderboard': leaderboard,
        'user': user,
        'my_rank': my_rank,
        'my_points': my_points
    })