from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
import math

from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.enums import AchievementStatus, UserRole, AchievementCategory, AchievementLevel
from app.services.admin.achievement_service import AchievementService
from app.repositories.admin.achievement_repository import AchievementRepository

router = guard_router


def get_service(db: AsyncSession = Depends(get_db)):
    return AchievementService(AchievementRepository(db))


def check_access(request: Request):
    if request.session.get('auth_role') not in [UserRole.MODERATOR, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")


# --- API ЖИВОГО ПОИСКА ---
@router.get('/api/documents/search', response_class=JSONResponse)
async def api_documents_search(request: Request, q: str = Query(..., min_length=1), db: AsyncSession = Depends(get_db)):
    check_access(request)
    # Ищем по названию или по фамилии автора
    stmt = select(Achievement).join(Users).filter(
        or_(
            Achievement.title.ilike(f"%{q}%"),
            Users.last_name.ilike(f"%{q}%"),
            Users.email.ilike(f"%{q}%")
        )
    ).limit(7)

    result = await db.execute(stmt)
    documents = result.scalars().all()

    return [
        {"value": d.title, "text": f"{d.title} ({d.category.value})"}
        for d in documents
    ]


# --- СПИСОК ДОКУМЕНТОВ ---
@router.get('/documents', response_class=HTMLResponse, name='admin.documents.index')
async def index(
        request: Request,
        status: str = None,
        category: str = None,  # <-- Отдельный фильтр
        level: str = None,  # <-- Отдельный фильтр
        query: str = None,
        page: int = Query(1, ge=1),
        db: AsyncSession = Depends(get_db)
):
    check_access(request)
    user = await db.get(Users, request.session.get('auth_id'))

    limit = 10
    offset = (page - 1) * limit

    stmt = select(Achievement).options(selectinload(Achievement.user)).order_by(Achievement.created_at.desc())

    # Фильтры
    if status and status != 'all': stmt = stmt.filter(Achievement.status == status)
    if category and category != 'all': stmt = stmt.filter(Achievement.category == category)
    if level and level != 'all': stmt = stmt.filter(Achievement.level == level)

    if query:
        stmt = stmt.filter(or_(Achievement.title.ilike(f"%{query}%"), Achievement.description.ilike(f"%{query}%")))

    total_items = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    achievements = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    total_pages = math.ceil(total_items / limit)

    return templates.TemplateResponse('documents/index.html', {
        'request': request, 'achievements': achievements, 'page': page,
        'total_pages': total_pages,
        'status': status, 'category': category, 'level': level, 'query': query,  # Передаем выбранные значения обратно
        'statuses': list(AchievementStatus),
        'categories': list(AchievementCategory),  # Передаем списки Enums
        'levels': list(AchievementLevel),
        'user': user
    })


@router.post('/documents/{id}/delete', name='admin.documents.delete')
async def delete_document(id: int, request: Request, service: AchievementService = Depends(get_service)):
    check_access(request)
    await service.repo.delete(id)
    return RedirectResponse(
        url=request.url_for('admin.documents.index').include_query_params(toast_msg="Документ удален",
                                                                          toast_type="success"), status_code=302)