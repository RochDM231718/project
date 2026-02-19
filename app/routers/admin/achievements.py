from fastapi import APIRouter, Request, Depends, Form, UploadFile, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, case
import math

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.models.achievement import Achievement
from app.models.user import Users
from app.models.enums import AchievementStatus, AchievementCategory, AchievementLevel
from app.services.admin.achievement_service import AchievementService
from app.repositories.admin.achievement_repository import AchievementRepository

router = guard_router


def get_service(db: AsyncSession = Depends(get_db)):
    return AchievementService(AchievementRepository(db))


@router.get('/api/my-achievements/search', response_class=JSONResponse)
async def api_my_achievements_search(request: Request, q: str = Query(..., min_length=1),
                                     db: AsyncSession = Depends(get_db)):
    user_id = request.session.get('auth_id')
    stmt = select(Achievement).filter(
        Achievement.user_id == user_id,
        or_(Achievement.title.ilike(f"%{q}%"), Achievement.description.ilike(f"%{q}%"))
    ).limit(5)

    result = await db.execute(stmt)
    return [{"value": d.title, "text": d.title} for d in result.scalars().all()]


@router.get('/achievements', response_class=HTMLResponse, name='admin.achievements.index')
async def index(
        request: Request,
        page: int = Query(1, ge=1),
        query: str = None,
        status: str = None,
        category: str = None,
        level: str = None,
        sort_by: str = "newest",
        db: AsyncSession = Depends(get_db)
):
    user_id = request.session.get('auth_id')
    user = await db.get(Users, user_id)

    limit = 10
    offset = (page - 1) * limit

    stmt = select(Achievement).filter(Achievement.user_id == user_id)

    if query:
        stmt = stmt.filter(or_(Achievement.title.ilike(f"%{query}%"), Achievement.description.ilike(f"%{query}%")))
    if status and status != 'all':
        stmt = stmt.filter(Achievement.status == status)
    if category and category != 'all':
        stmt = stmt.filter(Achievement.category == category)
    if level and level != 'all':
        stmt = stmt.filter(Achievement.level == level)

    if sort_by == "newest":
        stmt = stmt.order_by(Achievement.created_at.desc())
    elif sort_by == "oldest":
        stmt = stmt.order_by(Achievement.created_at.asc())
    elif sort_by == "category":
        stmt = stmt.order_by(Achievement.category)
    elif sort_by == "level":
        level_order = case(
            (Achievement.level == AchievementLevel.INTERNATIONAL, 5),
            (Achievement.level == AchievementLevel.FEDERAL, 4),
            (Achievement.level == AchievementLevel.REGIONAL, 3),
            (Achievement.level == AchievementLevel.MUNICIPAL, 2),
            (Achievement.level == AchievementLevel.SCHOOL, 1),
            else_=0
        )
        stmt = stmt.order_by(level_order.desc())

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


@router.get('/achievements/create', response_class=HTMLResponse, name='admin.achievements.create')
async def create(request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.get(Users, request.session.get('auth_id'))
    return templates.TemplateResponse('achievements/create.html', {
        'request': request,
        'user': user,
        'categories': list(AchievementCategory),
        'levels': list(AchievementLevel)
    })


@router.post('/achievements', name='admin.achievements.store', dependencies=[Depends(validate_csrf)])
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
        return RedirectResponse(
            url="/sirius.achievements/achievements?toast_msg=Достижение отправлено на проверку&toast_type=success", status_code=302)
    except Exception as e:
        return RedirectResponse(url=f"/sirius.achievements/achievements/create?toast_msg=Ошибка: {e}&toast_type=error",
                                status_code=302)


@router.post('/achievements/{id}/delete', name='admin.achievements.delete', dependencies=[Depends(validate_csrf)])
async def delete(id: int, request: Request, service: AchievementService = Depends(get_service)):
    user_id = request.session.get('auth_id')
    user_role = request.session.get('auth_role')

    achievement = await service.repo.find(id)

    if not achievement:
        return RedirectResponse(
            url="/sirius.achievements/achievements?toast_msg=Достижение не найдено&toast_type=error",
            status_code=302
        )

    is_owner = achievement.user_id == user_id
    is_staff = str(user_role) in [UserRole.MODERATOR.value, UserRole.SUPER_ADMIN.value, 'moderator', 'super_admin']

    if not is_owner and not is_staff:
        return RedirectResponse(
            url="/sirius.achievements/achievements?toast_msg=У вас нет прав на удаление этого файла&toast_type=error",
            status_code=302
        )

    await service.repo.delete(id)

    return RedirectResponse(
        url="/sirius.achievements/achievements?toast_msg=Достижение удалено&toast_type=success",
        status_code=302
    )