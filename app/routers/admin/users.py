from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc
import math
import time

from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.enums import UserRole, UserStatus, AchievementStatus
from app.services.admin.user_service import UserService
from app.repositories.admin.user_repository import UserRepository

router = guard_router


def get_service(db: AsyncSession = Depends(get_db)):
    return UserService(UserRepository(db))


def check_admin(request: Request):
    if request.session.get('auth_role') not in [UserRole.SUPER_ADMIN, UserRole.MODERATOR]:
        raise HTTPException(status_code=403, detail="Access denied")


# --- API ЖИВОГО ПОИСКА ---
@router.get('/api/users/search', response_class=JSONResponse)
async def api_users_search(request: Request, q: str = Query(..., min_length=1), db: AsyncSession = Depends(get_db)):
    check_admin(request)
    stmt = select(Users).filter(
        or_(
            Users.first_name.ilike(f"%{q}%"),
            Users.last_name.ilike(f"%{q}%"),
            Users.email.ilike(f"%{q}%")
        )
    ).limit(5)
    users = (await db.execute(stmt)).scalars().all()
    return [{"value": u.email, "text": f"{u.first_name} {u.last_name} ({u.email})"} for u in users]


# --- СПИСОК ПОЛЬЗОВАТЕЛЕЙ ---
@router.get('/users', response_class=HTMLResponse, name='admin.users.index')
async def index(
        request: Request,
        page: int = Query(1, ge=1),
        query: str = None,
        role: str = None,
        status: str = None,
        sort_by: str = "newest",
        db: AsyncSession = Depends(get_db)
):
    check_admin(request)
    current_user = await db.get(Users, request.session.get('auth_id'))

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
        'sort_by': sort_by,
        'roles': list(UserRole),
        'statuses': list(UserStatus),
        'user': current_user
    })


# --- ПРОСМОТР ПРОФИЛЯ ---
@router.get('/users/{id}', response_class=HTMLResponse, name='admin.users.show')
async def show_user(id: int, request: Request, db: AsyncSession = Depends(get_db)):
    check_admin(request)

    # 1. Получаем целевого пользователя
    target_user = await db.get(Users, id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    current_user = await db.get(Users, request.session.get('auth_id'))

    # 2. Получаем достижения пользователя
    achievements_stmt = select(Achievement).filter(Achievement.user_id == id).order_by(Achievement.created_at.desc())
    achievements = (await db.execute(achievements_stmt)).scalars().all()

    total_docs = len(achievements)

    # 3. Расчет рейтинга (ТОЛЬКО ДЛЯ СТУДЕНТОВ)
    rank = None
    total_points = 0

    if target_user.role == UserRole.STUDENT and target_user.status == UserStatus.ACTIVE:
        # Логика из leaderboard.py
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

        # Находим пользователя в списке
        for idx, (uid, pts) in enumerate(results, 1):
            if uid == id:
                rank = idx
                total_points = pts
                break

    return templates.TemplateResponse('users/show.html', {
        'request': request,
        'user': target_user,  # Целевой пользователь профиля
        'current_user': current_user,  # Тот, кто смотрит (админ)
        'achievements': achievements,
        'total_docs': total_docs,
        'rank': rank,  # Место в рейтинге
        'total_points': total_points,  # Сумма баллов
        'roles': list(UserRole),
        'timestamp': int(time.time())  # Для сброса кэша картинок
    })


# --- ОБНОВЛЕНИЕ РОЛИ ---
@router.post('/users/{id}/role', name='admin.users.update_role')
async def update_user_role(id: int, request: Request, role: UserRole = Form(...),
                           service: UserService = Depends(get_service)):
    check_admin(request)

    # Защита: нельзя менять роль самому себе
    if id == request.session.get('auth_id'):
        return RedirectResponse(
            url=f"/admin/users/{id}?toast_msg=Нельзя изменить роль самому себе&toast_type=error",
            status_code=302
        )

    await service.update_role(id, role)

    return RedirectResponse(
        url=f"/admin/users/{id}?toast_msg=Роль обновлена&toast_type=success",
        status_code=302
    )


# --- УДАЛЕНИЕ ---
@router.post('/users/{id}/delete', name='admin.users.delete')
async def delete_user(id: int, request: Request, service: UserService = Depends(get_service)):
    check_admin(request)
    await service.repository.delete(id)
    return RedirectResponse(url="/admin/users?toast_msg=Пользователь удален&toast_type=success", status_code=302)