from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
# ИСПРАВЛЕНО: Импортируем Users вместо User
from app.models.user import Users


async def get_current_user(request: Request, db: AsyncSession):
    """
    Асинхронное получение текущего пользователя из сессии.
    """
    user_id = request.session.get("auth_id")
    if not user_id:
        return None

    try:
        # Используем Users
        query = select(Users).where(Users.id == user_id)
        result = await db.execute(query)
        return result.scalars().first()
    except Exception as e:
        print(f"DEBUG: Ошибка авторизации в deps.py: {e}")
        return None