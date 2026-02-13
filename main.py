from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import os
from dotenv import load_dotenv

from app.infrastructure.database import engine, Base

# Импорт роутеров
from app.routers.admin.auth import router as admin_auth_router
from app.routers.admin.dashboard import router as admin_dashboard_router
from app.routers.admin.users import router as admin_users_router
from app.routers.admin.profile import router as admin_profile_router
from app.routers.admin.achievements import router as admin_achievements_router
from app.routers.admin.moderation import router as admin_moderation_router
from app.routers.admin.documents import router as admin_documents_router
from app.routers.admin.notifications import router as admin_notifications_router
from app.routers.admin.leaderboard import router as admin_leaderboard_router
from app.routers.admin.admin import public_router as admin_common_router
from app.routers.admin.admin import templates

load_dotenv()

# ИСПРАВЛЕНО: Добавлен root_path для корректной работы за прокси
app = FastAPI(root_path=os.getenv("ROOT_PATH", ""))


@app.on_event("startup")
async def init_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "supersecret"))

app.include_router(admin_common_router)
app.include_router(admin_auth_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_users_router)
app.include_router(admin_profile_router)
app.include_router(admin_achievements_router)
app.include_router(admin_moderation_router)
app.include_router(admin_documents_router)
app.include_router(admin_notifications_router)
app.include_router(admin_leaderboard_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("errors/404.html", {"request": request, "user": None}, status_code=404)
    elif exc.status_code == 403:
        return templates.TemplateResponse("errors/403.html", {"request": request, "user": None, "detail": exc.detail},
                                          status_code=403)
    return templates.TemplateResponse("errors/500.html", {"request": request, "user": None, "error": exc.detail},
                                      status_code=exc.status_code)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc) if os.getenv("DEBUG") == "True" else "Internal Server Error"
    return templates.TemplateResponse("errors/500.html", {"request": request, "user": None, "error": str(exc)},
                                      status_code=500)


@app.get("/")
async def root(request: Request):
    # ИСПРАВЛЕНО: Используем url_for для редиректа
    return RedirectResponse(url=request.url_for('admin.auth.login_page'))


@app.get("/admin")
async def admin_root(request: Request):
    # ИСПРАВЛЕНО: Используем url_for для редиректа
    return RedirectResponse(url=request.url_for('admin.dashboard.index'))