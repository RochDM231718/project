from fastapi import Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, asc, desc
from sqlalchemy.orm import selectinload  # <-- ВАЖНО: Импорт для подгрузки связей
from typing import Optional
from app.routers.admin.admin import guard_router, templates, get_db
from app.models.achievement import Achievement
from app.models.user import Users
from app.models.enums import UserRole, AchievementStatus
from app.services.admin.achievement_service import AchievementService
from app.repositories.admin.achievement_repository import AchievementRepository
from app.infrastructure.tranaslations import TranslationManager

router = guard_router


def get_achievement_service(db: AsyncSession = Depends(get_db)):
    return AchievementService(AchievementRepository(db))


def check_access(request: Request):
    role = request.session.get('auth_role')
    if role not in [UserRole.MODERATOR, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")


@router.get('/pages/search', response_class=JSONResponse, name='admin.pages.search_api')
async def search_documents(request: Request, query: str, status: Optional[str] = None,
                           db: AsyncSession = Depends(get_db)):
    check_access(request)
    if not query: return []

    stmt = select(Achievement).options(selectinload(Achievement.user)).join(Users)

    stmt = stmt.filter(or_(Achievement.title.ilike(f"%{query}%"), Users.first_name.ilike(f"%{query}%"),
                           Users.last_name.ilike(f"%{query}%"), Users.email.ilike(f"%{query}%")))
    if status: stmt = stmt.filter(Achievement.status == status)
    stmt = stmt.limit(10)

    result = await db.execute(stmt)
    documents = result.scalars().all()

    return [{"id": doc.user_id, "title": doc.title, "user": f"{doc.user.first_name} {doc.user.last_name}",
             "status": doc.status.value} for doc in documents]


@router.get('/pages', response_class=HTMLResponse, name="admin.pages.index")
async def index(request: Request, query: Optional[str] = "", status: Optional[str] = None,
                sort: Optional[str] = "created_at", order: Optional[str] = "desc", db: AsyncSession = Depends(get_db)):
    check_access(request)

    stmt = select(Achievement).options(selectinload(Achievement.user)).join(Users)

    if query: stmt = stmt.filter(or_(Achievement.title.ilike(f"%{query}%"), Users.first_name.ilike(f"%{query}%"),
                                     Users.last_name.ilike(f"%{query}%")))
    if status: stmt = stmt.filter(Achievement.status == status)

    if hasattr(Achievement, sort):
        field = getattr(Achievement, sort)
        stmt = stmt.order_by(asc(field) if order == 'asc' else desc(field))
    else:
        stmt = stmt.order_by(desc(Achievement.created_at))

    stmt = stmt.limit(50)

    result = await db.execute(stmt)
    documents = result.scalars().all()

    count_stmt = select(func.count()).select_from(Achievement).join(Users)
    if query: count_stmt = count_stmt.filter(
        or_(Achievement.title.ilike(f"%{query}%"), Users.first_name.ilike(f"%{query}%"),
            Users.last_name.ilike(f"%{query}%")))
    if status: count_stmt = count_stmt.filter(Achievement.status == status)

    res_count = await db.execute(count_stmt)
    total_count = res_count.scalar()

    return templates.TemplateResponse('pages/index.html', {'request': request, 'query': query, 'documents': documents,
                                                           'total_count': total_count, 'selected_status': status,
                                                           'statuses': list(AchievementStatus), 'current_sort': sort,
                                                           'current_order': order})


@router.post('/pages/{id}/delete', name='admin.pages.delete')
async def delete_document(id: int, request: Request, service: AchievementService = Depends(get_achievement_service)):
    check_access(request)
    user_id = request.session['auth_id']
    user_role = request.session.get('auth_role')

    await service.delete(id, user_id, user_role)

    locale = request.session.get('locale', 'en')
    translator = TranslationManager()
    url = request.url_for('admin.pages.index').include_query_params(
        toast_msg=translator.gettext("admin.toast.deleted", locale=locale), toast_type="success")
    return RedirectResponse(url=url, status_code=302)