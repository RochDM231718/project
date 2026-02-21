from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, desc

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.enums import UserRole, UserStatus, AchievementStatus, EducationLevel

router = guard_router


@router.get('/leaderboard', response_class=HTMLResponse, name='admin.leaderboard.index')
async def index(
        request: Request,
        education_level: str = Query(None),
        course: int = Query(None),
        db: AsyncSession = Depends(get_db)
):
    user_id = request.session.get('auth_id')
    user = await db.get(Users, user_id)

    if user.role not in [UserRole.SUPER_ADMIN, UserRole.MODERATOR]:
        edu_val = user.education_level.value if hasattr(user.education_level, 'value') else user.education_level
        education_level = edu_val if edu_val else 'all'
        course = user.course if user.course else 0
    else:
        if not education_level:
            education_level = 'all'
        if course is None:
            course = 0

    stmt = (
        select(
            Users,
            func.coalesce(func.sum(Achievement.points), 0).label("total_points"),
            func.count(Achievement.id).label("achievements_count")
        )
        .outerjoin(Achievement, (Users.id == Achievement.user_id) & (Achievement.status == AchievementStatus.APPROVED))
        .filter(Users.role == UserRole.STUDENT, Users.status == UserStatus.ACTIVE)
    )

    if education_level != 'all':
        stmt = stmt.filter(Users.education_level == education_level)
    if course != 0:
        stmt = stmt.filter(Users.course == course)

    stmt = stmt.group_by(Users.id).order_by(desc("total_points"), desc("achievements_count"))

    result = await db.execute(stmt)
    leaderboard = result.all()

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
        'my_points': my_points,
        'current_education_level': education_level,
        'current_course': course,
        'education_levels': list(EducationLevel)
    })