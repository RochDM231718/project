from fastapi import HTTPException, status, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.enums import UserRole
from app.routers.api.api import public_router as router, translation_manager
from app.services.auth_service import AuthService
from app.infrastructure.database.connection import get_db
from app.repositories.admin.user_repository import UserRepository
from app.repositories.admin.user_token_repository import UserTokenRepository
from app.services.admin.user_token_service import UserTokenService

def get_auth_service(db: AsyncSession = Depends(get_db)):
    user_repo = UserRepository(db)
    token_repo = UserTokenRepository(db)
    token_service = UserTokenService(token_repo)
    return AuthService(user_repo, token_service)

@router.post("/login", name='api.auth.authentication')
async def login(email: str = Form(...), password: str = Form(...), auth_service: AuthService = Depends(get_auth_service)):
    result = await auth_service.api_authenticate(email, password, UserRole.GUEST)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translation_manager.gettext('api.auth.invalid_credentials')
        )
    return result

@router.post("/refresh",  name='api.auth.refresh')
async def refresh(refresh_token: str = Form(...), auth_service: AuthService = Depends(get_auth_service)):
    result = await auth_service.api_refresh_token(refresh_token)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translation_manager.gettext('api.auth.invalid_refresh_token')
        )
    return result