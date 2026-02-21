from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc
import math
import time

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.season_result import SeasonResult  # <--- Импорт новой таблицы
from app.models.enums import UserRole, UserStatus, AchievementStatus, EducationLevel
from app.services.admin.user_service import UserService
from app.repositories.admin.user_repository import UserRepository
from app.routers.admin.deps import get_current_user

router = guard_router


def get_service(db: AsyncSession = Depends(get_db)):
    return UserService(UserRepository(db))


async def check_admin_rights(request: Request, db: AsyncSession):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=403, detail="Not authenticated")

    allowed_roles = [UserRole.SUPER_ADMIN, UserRole.MODERATOR]
    if user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Access denied")
    return user


ROLE_HIERARCHY = {
    UserRole.GUEST: 0,
    UserRole.STUDENT: 1,
    UserRole.MODERATOR: 2,
    UserRole.SUPER_ADMIN: 3
}


@router.get('/api/users/search', response_class=JSONResponse)
async def api_users_search(request: Request, q: str = Query(..., min_length=1), db: AsyncSession = Depends(get_db)):
    await check_admin_rights(request, db)
    stmt = select(Users).filter(
        or_(
            Users.first_name.ilike(f"%{q}%"),
            Users.last_name.ilike(f"%{q}%"),
            Users.email.ilike(f"%{q}%")
        )
    ).limit(5)
    users = (await db.execute(stmt)).scalars().all()
    return [{"value": u.email, "text": f"{u.first_name} {u.last_name} ({u.email})"} for u in users]


@router.get('/users', response_class=HTMLResponse, name='admin.users.index')
async def index(
        request: Request,
        page: int = Query(1, ge=1),
        query: str = None,
        role: str = None,
        status: str = None,
        education_level: str = None,
        course: int = None,
        sort_by: str = "newest",
        db: AsyncSession = Depends(get_db)
):
    current_user = await check_admin_rights(request, db)

    limit = 10
    offset = (page - 1) * limit

    stmt = select(Users)

    if query:
        stmt = stmt.filter(or_(Users.first_name.ilike(f"%{query}%"), Users.last_name.ilike(f"%{query}%"),
                               Users.email.ilike(f"%{query}%")))
    if role and role != 'all':
        stmt = stmt.filter(Users.role == role)
    if status and status != 'all':
        stmt = stmt.filter(Users.status == status)
    if education_level and education_level != 'all':
        stmt = stmt.filter(Users.education_level == education_level)
    if course and course != 0:
        stmt = stmt.filter(Users.course == course)

    if sort_by == "oldest":
        stmt = stmt.order_by(Users.created_at.asc())
    else:
        stmt = stmt.order_by(Users.created_at.desc())

    total_items = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    users = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()

    return templates.TemplateResponse('users/index.html', {
        'request': request,
        'users': users,
        'page': page,
        'total_pages': math.ceil(total_items / limit),
        'query': query,
        'role': role,
        'status': status,
        'education_level': education_level,
        'course': course,
        'sort_by': sort_by,
        'roles': list(UserRole),
        'statuses': list(UserStatus),
        'education_levels': list(EducationLevel),
        'user': current_user
    })


@router.get('/users/{id}', response_class=HTMLResponse, name='admin.users.show')
async def show_user(id: int, request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await check_admin_rights(request, db)

    target_user_obj = await db.get(Users, id)
    if not target_user_obj:
        raise HTTPException(status_code=404, detail="User not found")

    # Текущие достижения (не архивные)
    achievements_stmt = select(Achievement).filter(
        Achievement.user_id == id,
        Achievement.status != AchievementStatus.ARCHIVED
    ).order_by(Achievement.created_at.desc())
    achievements = (await db.execute(achievements_stmt)).scalars().all()

    # Загрузка истории прошлых сезонов
    history_stmt = select(SeasonResult).filter(SeasonResult.user_id == id).order_by(SeasonResult.created_at.desc())
    season_history = (await db.execute(history_stmt)).scalars().all()

    total_docs = len(achievements)
    rank = None
    total_points = 0

    if target_user_obj.role == UserRole.STUDENT and target_user_obj.status == UserStatus.ACTIVE:
        leaderboard_stmt = (
            select(
                Users.id,
                func.coalesce(func.sum(Achievement.points), 0).label("total_points")
            )
            .outerjoin(Achievement,
                       (Users.id == Achievement.user_id) & (Achievement.status == AchievementStatus.APPROVED))
            .filter(Users.role == UserRole.STUDENT, Users.status == UserStatus.ACTIVE)
            .group_by(Users.id)
            .order_by(desc("total_points"))
        )
        results = (await db.execute(leaderboard_stmt)).all()
        for idx, (uid, pts) in enumerate(results, 1):
            if uid == id:
                rank = idx
                total_points = pts
                break

    return templates.TemplateResponse('users/show.html', {
        'request': request,
        'user': current_user,
        'target_user': target_user_obj,
        'achievements': achievements,
        'season_history': season_history,  # <--- Передаем историю в шаблон
        'total_docs': total_docs,
        'rank': rank,
        'total_points': total_points,
        'roles': list(UserRole),
        'education_levels': list(EducationLevel),
        'timestamp': int(time.time())
    })


@router.post('/users/{id}/role', name='admin.users.update_role', dependencies=[Depends(validate_csrf)])
async def update_user_role(
        id: int,
        request: Request,
        role: UserRole = Form(...),
        education_level: str = Form(None),
        service: UserService = Depends(get_service),
        db: AsyncSession = Depends(get_db)
):
    current_user = await check_admin_rights(request, db)

    if id == current_user.id:
        return RedirectResponse(
            url=f"/sirius.achievements/users/{id}?toast_msg=Нельзя изменить роль самому себе&toast_type=error",
            status_code=302
        )

    target_user = await db.get(Users, id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role != UserRole.SUPER_ADMIN:
        current_level = ROLE_HIERARCHY.get(current_user.role, 0)
        target_level = ROLE_HIERARCHY.get(target_user.role, 0)
        new_role_level = ROLE_HIERARCHY.get(role, 0)

        if target_level >= current_level or new_role_level >= current_level:
            return RedirectResponse(
                url=f"/sirius.achievements/users/{id}?toast_msg=У вас недостаточно прав для этого действия&toast_type=error",
                status_code=302
            )

    update_data = {"role": role}

    if role == UserRole.MODERATOR:
        if education_level and education_level != 'all':
            update_data["education_level"] = education_level
        else:
            update_data["education_level"] = None
    elif role == UserRole.SUPER_ADMIN:
        update_data["education_level"] = None

    await service.repository.update(id, update_data)

    return RedirectResponse(
        url=f"/sirius.achievements/users/{id}?toast_msg=Роль и права обновлены&toast_type=success",
        status_code=302
    )


@router.post('/users/{id}/delete', name='admin.users.delete', dependencies=[Depends(validate_csrf)])
async def delete_user(
        id: int,
        request: Request,
        service: UserService = Depends(get_service),
        db: AsyncSession = Depends(get_db)
):
    current_user = await check_admin_rights(request, db)

    if id == current_user.id:
        return RedirectResponse(
            url=f"/sirius.achievements/users/{id}?toast_msg=Нельзя удалить самого себя&toast_type=error",
            status_code=302
        )

    target_user = await db.get(Users, id)
    if target_user:
        current_level = ROLE_HIERARCHY.get(current_user.role, 0)
        target_level = ROLE_HIERARCHY.get(target_user.role, 0)

        if current_user.role != UserRole.SUPER_ADMIN and target_level >= current_level:
            return RedirectResponse(
                url=f"/sirius.achievements/users/{id}?toast_msg=Недостаточно прав для удаления этого пользователя&toast_type=error",
                status_code=302
            )

    await service.repository.delete(id)
    return RedirectResponse(url="/sirius.achievements/users?toast_msg=Пользователь удален&toast_type=success",
                            status_code=302)