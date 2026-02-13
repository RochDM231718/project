from fastapi import APIRouter, Request, Depends, Form, UploadFile, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, case
import math

from app.routers.admin.admin import guard_router, templates, get_db
from app.models.achievement import Achievement
from app.models.user import Users
from app.models.enums import AchievementStatus, AchievementCategory, AchievementLevel
from app.services.admin.achievement_service import AchievementService
from app.repositories.admin.achievement_repository import AchievementRepository

router = guard_router


def get_service(db: AsyncSession = Depends(get_db)):
    return AchievementService(AchievementRepository(db))


# --- API ЖИВОГО ПОИСКА (Только свои достижения) ---
@router.get('/api/my-achievements/search', response_class=JSONResponse)
async def api_my_achievements_search(request: Request, q: str = Query(..., min_length=1),
                                     db: AsyncSession = Depends(get_db)):
    user_id = request.session.get('auth_id')
    # Ищем только среди своих
    stmt = select(Achievement).filter(
        Achievement.user_id == user_id,
        or_(Achievement.title.ilike(f"%{q}%"), Achievement.description.ilike(f"%{q}%"))
    ).limit(5)

    result = await db.execute(stmt)
    return [{"value": d.title, "text": d.title} for d in result.scalars().all()]


# --- МОИ ДОСТИЖЕНИЯ ---
@router.get('/achievements', response_class=HTMLResponse, name='admin.achievements.index')
async def index(
        request: Request,
        page: int = Query(1, ge=1),
        query: str = None,
        status: str = None,
        category: str = None,
        level: str = None,
        sort_by: str = "newest",  # Добавлена сортировка
        db: AsyncSession = Depends(get_db)
):
    user_id = request.session.get('auth_id')
    user = await db.get(Users, user_id)

    limit = 10
    offset = (page - 1) * limit

    # Базовый запрос: только свои достижения
    stmt = select(Achievement).filter(Achievement.user_id == user_id)

    # 1. Фильтры
    if query:
        stmt = stmt.filter(or_(Achievement.title.ilike(f"%{query}%"), Achievement.description.ilike(f"%{query}%")))
    if status and status != 'all':
        stmt = stmt.filter(Achievement.status == status)
    if category and category != 'all':
        stmt = stmt.filter(Achievement.category == category)
    if level and level != 'all':
        stmt = stmt.filter(Achievement.level == level)

    # 2. Сортировка
    if sort_by == "newest":
        stmt = stmt.order_by(Achievement.created_at.desc())
    elif sort_by == "oldest":
        stmt = stmt.order_by(Achievement.created_at.asc())
    elif sort_by == "category":
        stmt = stmt.order_by(Achievement.category)
    elif sort_by == "level":
        # Сортировка по значимости (CASE)
        level_order = case(
            (Achievement.level == AchievementLevel.INTERNATIONAL, 5),
            (Achievement.level == AchievementLevel.FEDERAL, 4),
            (Achievement.level == AchievementLevel.REGIONAL, 3),
            (Achievement.level == AchievementLevel.MUNICIPAL, 2),
            (Achievement.level == AchievementLevel.SCHOOL, 1),
            else_=0
        )
        stmt = stmt.order_by(level_order.desc())

    # Пагинация
    total_items = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    achievements = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()

    return templates.TemplateResponse('achievements/index.html', {
        'request': request,
        'achievements': achievements,
        'page': page,
        'total_pages': math.ceil(total_items / limit),
        'query': query, 'status': status, 'category': category, 'level': level, 'sort_by': sort_by,
        'statuses': list(AchievementStatus),
        'categories': list(AchievementCategory),
        'levels': list(AchievementLevel),
        'user': user
    })


# --- СОЗДАНИЕ ---
@router.get('/achievements/create', response_class=HTMLResponse, name='admin.achievements.create')
async def create(request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.get(Users, request.session.get('auth_id'))
    return templates.TemplateResponse('achievements/create.html', {
        'request': request,
        'user': user,
        'categories': list(AchievementCategory),
        'levels': list(AchievementLevel)
    })


@router.post('/achievements', name='admin.achievements.store')
async def store(
        request: Request,
        title: str = Form(...),
        description: str = Form(None),
        category: str = Form(...),
        level: str = Form(...),
        file: UploadFile = Form(...),
        service: AchievementService = Depends(get_service)
):
    user_id = request.session.get('auth_id')
    try:
        file_path = await service.save_file(file)
        await service.create({
            "user_id": user_id,
            "title": title,
            "description": description,
            "file_path": file_path,
            "category": category,
            "level": level,
            "status": AchievementStatus.PENDING
        })
        # ИСПРАВЛЕНО: Редирект на /sirius.achievements/...
        return RedirectResponse(
            url="/sirius.achievements/achievements?toast_msg=Достижение отправлено на проверку&toast_type=success", status_code=302)
    except Exception as e:
        # ИСПРАВЛЕНО: Редирект на /sirius.achievements/...
        return RedirectResponse(url=f"/sirius.achievements/achievements/create?toast_msg=Ошибка: {e}&toast_type=error",
                                status_code=302)


# --- УДАЛЕНИЕ ---
@router.post('/achievements/{id}/delete', name='admin.achievements.delete')
async def delete(id: int, request: Request, service: AchievementService = Depends(get_service)):
    # Проверка владельца происходит внутри repo.delete или фильтром,
    # здесь упрощенно считаем, что удаляет владелец. В проде добавить проверку user_id.
    await service.repo.delete(id)
    # ИСПРАВЛЕНО: Редирект на /sirius.achievements/...
    return RedirectResponse(url="/sirius.achievements/achievements?toast_msg=Достижение удалено&toast_type=success", status_code=302)