from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import math

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.repositories.admin.user_repository import UserRepository
from app.repositories.admin.achievement_repository import AchievementRepository
from app.services.admin.user_service import UserService
from app.services.admin.achievement_service import AchievementService
from app.services.points_calculator import calculate_points
from app.models.user import Users
from app.models.achievement import Achievement
from app.models.notification import Notification
from app.models.enums import UserStatus, AchievementStatus, UserRole

router = guard_router


def get_user_service(db: AsyncSession = Depends(get_db)):
    return UserService(UserRepository(db))


def get_achievement_service(db: AsyncSession = Depends(get_db)):
    return AchievementService(AchievementRepository(db))


async def check_moderator(request: Request, db: AsyncSession):
    user_id = request.session.get('auth_id')
    if not user_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    user = await db.get(Users, user_id)

    if not user:
        raise HTTPException(status_code=403, detail="User not found")

    if user.role not in [UserRole.MODERATOR, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Access denied")

    return user


def is_in_zone(moderator: Users, target_education_level) -> bool:
    if moderator.role == UserRole.SUPER_ADMIN:
        return True
    if not moderator.education_level:
        return True

    mod_ed = moderator.education_level.value if hasattr(moderator.education_level,
                                                        'value') else moderator.education_level
    targ_ed = target_education_level.value if hasattr(target_education_level, 'value') else target_education_level

    return mod_ed == targ_ed


@router.get('/moderation/users', response_class=HTMLResponse, name='admin.moderation.users')
async def pending_users(request: Request, db: AsyncSession = Depends(get_db)):
    user = await check_moderator(request, db)

    stmt = select(Users).filter(Users.status == UserStatus.PENDING)

    if user.role == UserRole.MODERATOR and user.education_level:
        mod_ed = user.education_level.value if hasattr(user.education_level, 'value') else user.education_level
        stmt = stmt.filter(Users.education_level == mod_ed)

    stmt = stmt.order_by(Users.id.desc())
    users = (await db.execute(stmt)).scalars().all()

    return templates.TemplateResponse('moderation/users.html', {
        'request': request,
        'users': users,
        'total_count': len(users),
        'user': user
    })


@router.post('/moderation/users/{id}/approve', name='admin.moderation.users.approve',
             dependencies=[Depends(validate_csrf)])
async def approve_user(
        id: int,
        request: Request,
        service: UserService = Depends(get_user_service),
        db: AsyncSession = Depends(get_db)
):
    current_user = await check_moderator(request, db)
    target_user = await db.get(Users, id)

    if not target_user or not is_in_zone(current_user, target_user.education_level):
        return RedirectResponse(url=request.url_for('admin.moderation.users').include_query_params(
            toast_msg="У вас нет доступа к этому потоку", toast_type="error"), status_code=302)

    await service.repository.update(id, {
        "status": UserStatus.ACTIVE,
        "role": UserRole.STUDENT
    })
    return RedirectResponse(
        url=request.url_for('admin.moderation.users').include_query_params(toast_msg="Пользователь одобрен",
                                                                           toast_type="success"),
        status_code=302
    )


@router.post('/moderation/users/{id}/reject', name='admin.moderation.users.reject',
             dependencies=[Depends(validate_csrf)])
async def reject_user(
        id: int,
        request: Request,
        service: UserService = Depends(get_user_service),
        db: AsyncSession = Depends(get_db)
):
    current_user = await check_moderator(request, db)
    target_user = await db.get(Users, id)

    if not target_user or not is_in_zone(current_user, target_user.education_level):
        return RedirectResponse(url=request.url_for('admin.moderation.users').include_query_params(
            toast_msg="У вас нет доступа к этому потоку", toast_type="error"), status_code=302)

    await service.repository.update(id, {"status": UserStatus.REJECTED})
    return RedirectResponse(
        url=request.url_for('admin.moderation.users').include_query_params(toast_msg="Пользователь отклонен",
                                                                           toast_type="success"),
        status_code=302
    )


@router.get('/moderation/achievements', response_class=HTMLResponse, name='admin.moderation.achievements')
async def achievements_list(request: Request, page: int = Query(1, ge=1), db: AsyncSession = Depends(get_db)):
    user = await check_moderator(request, db)

    limit = 10
    offset = (page - 1) * limit

    stmt = select(Achievement).join(Users, Achievement.user_id == Users.id).options(selectinload(Achievement.user)) \
        .filter(Achievement.status == AchievementStatus.PENDING)

    if user.role == UserRole.MODERATOR and user.education_level:
        mod_ed = user.education_level.value if hasattr(user.education_level, 'value') else user.education_level
        stmt = stmt.filter(Users.education_level == mod_ed)

    stmt = stmt.order_by(Achievement.created_at.asc())

    total_pending = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    achievements = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()

    for item in achievements:
        if item.level and item.category:
            item.projected_points = calculate_points(item.level.value, item.category.value)
        else:
            item.projected_points = 0

    return templates.TemplateResponse('moderation/achievements.html', {
        'request': request,
        'achievements': achievements,
        'total_pending': total_pending,
        'stats': {"pending": total_pending, "approved": 0},
        'page': page,
        'total_pages': math.ceil(total_pending / limit) if total_pending > 0 else 1,
        'user': user
    })


@router.post('/moderation/achievements/{id}', name='admin.moderation.achievements.update',
             dependencies=[Depends(validate_csrf)])
async def update_achievement_status(
        id: int, request: Request, status: str = Form(...), rejection_reason: str = Form(None),
        db: AsyncSession = Depends(get_db)
):
    current_user = await check_moderator(request, db)

    stmt = select(Achievement).options(selectinload(Achievement.user)).where(Achievement.id == id)
    achievement = (await db.execute(stmt)).scalars().first()

    if not achievement:
        raise HTTPException(status_code=404, detail="Achievement not found")

    if not is_in_zone(current_user, achievement.user.education_level):
        return RedirectResponse(url=request.url_for('admin.moderation.achievements').include_query_params(
            toast_msg="Вы не можете проверять чужой поток", toast_type="error"), status_code=302)

    achievement.status = status

    if status == 'rejected' or status == AchievementStatus.REJECTED:
        achievement.rejection_reason = rejection_reason
        achievement.points = 0
        notif_message = f"Окончательный отказ по документу '{achievement.title}'. Причина: {rejection_reason}"

    elif status == 'revision' or status == AchievementStatus.REVISION:
        achievement.rejection_reason = rejection_reason
        achievement.points = 0
        notif_message = f"Документ '{achievement.title}' отправлен на доработку. Примечание: {rejection_reason}"

    elif status == 'approved' or status == AchievementStatus.APPROVED:
        points = calculate_points(achievement.level.value, achievement.category.value)
        achievement.points = points
        achievement.rejection_reason = None
        notif_message = f"Документ '{achievement.title}' одобрен! Начислено {points} баллов."

    notification = Notification(
        user_id=achievement.user_id,
        title="Статус заявки обновлен",
        message=notif_message,
        is_read=False
    )
    db.add(notification)
    await db.commit()

    return RedirectResponse(
        url=request.url_for('admin.moderation.achievements').include_query_params(toast_msg="Решение сохранено",
                                                                                  toast_type="success"),
        status_code=302
    )