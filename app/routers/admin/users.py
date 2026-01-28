from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
import math

from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.models.enums import UserRole, UserStatus
from app.services.admin.user_service import UserService
from app.repositories.admin.user_repository import UserRepository

router = guard_router


# Dependency для сервиса
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
        status: str = None,  # <-- Добавлено
        sort_by: str = "newest",  # <-- Добавлено
        db: AsyncSession = Depends(get_db)
):
    check_admin(request)
    current_user = await db.get(Users, request.session.get('auth_id'))

    limit = 10
    offset = (page - 1) * limit

    stmt = select(Users)

    # Фильтры
    if query:
        stmt = stmt.filter(or_(Users.first_name.ilike(f"%{query}%"), Users.last_name.ilike(f"%{query}%"),
                               Users.email.ilike(f"%{query}%")))

    if role and role != 'all':
        stmt = stmt.filter(Users.role == role)

    if status and status != 'all':
        stmt = stmt.filter(Users.status == status)

    # Сортировка
    if sort_by == "oldest":
        stmt = stmt.order_by(Users.created_at.asc())
    else:  # newest
        stmt = stmt.order_by(Users.created_at.desc())

    # Пагинация
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


# --- УДАЛЕНИЕ ---
@router.post('/users/{id}/delete', name='admin.users.delete')
async def delete_user(id: int, request: Request, service: UserService = Depends(get_service)):
    check_admin(request)
    await service.repository.delete(id)
    return RedirectResponse(url="/admin/users?toast_msg=Пользователь удален&toast_type=success", status_code=302)