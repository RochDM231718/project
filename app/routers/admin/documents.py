import os
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession  # Добавили правильный тип сессии
from app.infrastructure.database import get_db
from app.services.admin.achievement_service import AchievementService
from app.repositories.admin.achievement_repository import AchievementRepository
from app.routers.admin.admin import templates
from app.routers.admin.deps import get_current_user
from app.security.csrf import validate_csrf

router = APIRouter(
    prefix="/sirius.achievements/documents",
    tags=["admin.documents"]
)


@router.get("/", response_class=HTMLResponse)
async def index(
        request: Request,
        query: str = "",
        status: str = "",
        category: str = "",
        level: str = "",
        sort_by: str = "newest",
        db: AsyncSession = Depends(get_db)  # AsyncSession
):
    # ВАЖНО: Добавлен await
    user = await get_current_user(request, db)

    if not user:
        return RedirectResponse(url="/")

    # Расширенный список ролей
    allowed_roles = [
        'admin', 'moderator', 'super_admin',
        'ADMIN', 'MODERATOR', 'SUPER_ADMIN'
    ]

    # Приведение роли к строке для безопасности
    user_role_str = str(user.role.value) if hasattr(user.role, 'value') else str(user.role)

    if user_role_str not in allowed_roles:
        return RedirectResponse(url="/sirius.achievements/dashboard")

    repo = AchievementRepository(db)

    achievements = await repo.get_all_with_filters(
        search=query,
        status=status,
        category=category,
        level=level,
        sort_by=sort_by
    )

    return templates.TemplateResponse("documents/index.html", {
        "request": request,
        "user": user,
        "achievements": achievements,
        "query": query,
        "status": status,
        "category": category,
        "level": level,
        "sort_by": sort_by,
        "statuses": repo.model.status.type.enums if hasattr(repo.model, 'status') else [],
        "categories": repo.model.category.type.enums if hasattr(repo.model, 'category') else [],
        "levels": repo.model.level.type.enums if hasattr(repo.model, 'level') else []
    })


@router.post("/{id}/delete")
async def delete(
        id: int,
        request: Request,
        db: AsyncSession = Depends(get_db),
        _=Depends(validate_csrf)
):
    # ВАЖНО: Добавлен await
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)

    user_role_str = str(user.role.value) if hasattr(user.role, 'value') else str(user.role)

    repo = AchievementRepository(db)
    service = AchievementService(repo)

    try:
        await service.delete(id, user.id, user_role_str)
        return RedirectResponse(
            url="/sirius.achievements/documents?toast_msg=Документ удален&toast_type=success",
            status_code=303
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/sirius.achievements/documents?toast_msg=Ошибка: {str(e)}&toast_type=error",
            status_code=303
        )


@router.get("/{id}/download")
async def download_document(
        id: int,
        request: Request,
        db: AsyncSession = Depends(get_db)
):
    # ВАЖНО: Добавлен await
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")

    user_role_str = str(user.role.value) if hasattr(user.role, 'value') else str(user.role)

    allowed_roles = [
        'admin', 'moderator', 'super_admin',
        'ADMIN', 'MODERATOR', 'SUPER_ADMIN'
    ]
    if user_role_str not in allowed_roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав для скачивания")

    repo = AchievementRepository(db)
    document = await repo.find(id)

    if not document or not document.file_path:
        raise HTTPException(status_code=404, detail="Документ не найден")

    file_full_path = os.path.join("static", document.file_path)

    if not os.path.exists(file_full_path):
        raise HTTPException(status_code=404, detail="Файл физически отсутствует на сервере")

    ext = os.path.splitext(file_full_path)[1]
    filename = f"document_{id}_user_{document.user_id}{ext}"

    return FileResponse(
        path=file_full_path,
        filename=filename,
        media_type='application/octet-stream'
    )