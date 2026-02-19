from fastapi import HTTPException, Request
from sqlalchemy import select
from app.infrastructure.jwt_handler import verify_token
from app.infrastructure.tranaslations import TranslationManager
from app.models.user import Users
from app.infrastructure.database.connection import db_instance
from app.models.enums import UserRole, UserStatus

translation_manager = TranslationManager()


async def auth(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=translation_manager.gettext('api.auth.invalid_authorization_token'))

    token = auth_header.split(" ")[1]
    payload = verify_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail=translation_manager.gettext('api.auth.invalid_token'))

    async with db_instance.session_factory() as db:
        user_id = payload.get("sub")
        stmt = select(Users).filter(Users.id == int(user_id))
        result = await db.execute(stmt)
        user = result.scalars().first()

        if not user or user.status == UserStatus.REJECTED or not user.is_active:
            raise HTTPException(status_code=401, detail=translation_manager.gettext('api.auth.user_not_found'))

    request.state.user = user
    request.state.user_role = UserRole(user.role)

    return user