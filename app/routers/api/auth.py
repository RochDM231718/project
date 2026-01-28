from fastapi import HTTPException, status, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.enums import UserRole
from app.routers.api.api import public_router as router, translation_manager
from app.services.auth_service import AuthService
from app.infrastructure.database.connection import get_db

@router.post("/login", name='api.auth.authentication')
async def login(email: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    result = await auth_service.api_authenticate(email, password, UserRole.GUEST)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translation_manager.gettext('api.auth.invalid_credentials')
        )
    return result

@router.post("/refresh",  name='api.auth.refresh')
def refresh(refresh_token: str = Form(...)):
    from app.services.auth_service import AuthService as Svc
    result = Svc(None).api_refresh_token(refresh_token)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translation_manager.gettext('api.auth.invalid_refresh_token'))
    return result