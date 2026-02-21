from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.infrastructure.database import async_session_maker
from datetime import timedelta
from app.security.csrf import validate_csrf
from app.routers.admin.deps import require_auth

templates = Jinja2Templates(directory="templates/admin")

def msk_format(value):
    if not value:
        return "-"
    msk_time = value + timedelta(hours=3)
    return msk_time.strftime("%d.%m.%Y %H:%M")

templates.env.filters["msk"] = msk_format

async def get_db():
    async with async_session_maker() as session:
        yield session

guard_router = APIRouter(
    prefix="/sirius.achievements",
    tags=["Admin Protected"],
    dependencies=[Depends(require_auth)]
)

public_router = APIRouter(prefix="/sirius.achievements", tags=["Admin Public"])
