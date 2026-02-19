from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, get_db
from app.models.notification import Notification

router = guard_router


@router.get('/api/notifications/unread-count')
async def get_unread_count(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get('auth_id')
    if not user_id:
        return JSONResponse({"count": 0, "notifications": []})

    count_stmt = select(func.count()).filter(
        Notification.user_id == user_id,
        Notification.is_read == False
    )
    count = (await db.execute(count_stmt)).scalar() or 0

    items_stmt = select(Notification) \
        .filter(Notification.user_id == user_id) \
        .order_by(Notification.created_at.desc()) \
        .limit(5)

    items = (await db.execute(items_stmt)).scalars().all()

    data = [{
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "is_read": n.is_read,
        "created_at": n.created_at.strftime("%H:%M %d.%m")  # Форматируем дату
    } for n in items]

    return JSONResponse({"count": count, "notifications": data})


@router.post('/api/notifications/mark-read', dependencies=[Depends(validate_csrf)])
async def mark_all_read(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get('auth_id')
    if user_id:
        await db.execute(
            update(Notification)
            .where(Notification.user_id == user_id)
            .values(is_read=True)
        )
        await db.commit()

    return JSONResponse({"status": "ok"})