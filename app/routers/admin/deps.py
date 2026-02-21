from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import Users
from app.models.enums import UserStatus
import structlog

logger = structlog.get_logger()


async def get_current_user(request: Request, db: AsyncSession):
    user_id = request.session.get("auth_id")
    if not user_id:
        return None

    try:
        query = select(Users).where(Users.id == user_id)
        result = await db.execute(query)
        return result.scalars().first()
    except Exception as e:
        logger.error("Auth error in deps.py", error=str(e))
        return None


async def require_auth(request: Request):
    """Guard dependency: redirects unauthenticated users to login."""
    auth_id = request.session.get("auth_id")
    if not auth_id:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            raise HTTPException(status_code=401, detail="Unauthorized")
        raise HTTPException(status_code=302, headers={"Location": "/sirius.achievements/login"})