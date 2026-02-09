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
from app.routers.admin.admin import templates  # Импортируем templates для обработчиков ошибок

load_dotenv()

app = FastAPI()


# Создание таблиц при старте (для надежности)
@app.on_event("startup")
async def init_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "supersecret"))

# Подключение роутеров
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


# --- ОБРАБОТЧИКИ ОШИБОК ---

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Обработка HTTP ошибок (404, 403 и др.)"""
    if exc.status_code == 404:
        return templates.TemplateResponse("errors/404.html", {"request": request, "user": None}, status_code=404)
    elif exc.status_code == 403:
        return templates.TemplateResponse("errors/403.html", {"request": request, "user": None, "detail": exc.detail},
                                          status_code=403)

    # Для остальных кодов ошибок можно использовать общий шаблон или 500
    return templates.TemplateResponse("errors/500.html", {"request": request, "user": None, "error": exc.detail},
                                      status_code=exc.status_code)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Обработка всех остальных непредвиденных ошибок (500)"""
    # В продакшене лучше не выводить полный текст ошибки пользователю, но для разработки полезно
    error_msg = str(exc) if os.getenv("DEBUG") == "True" else "Internal Server Error"
    return templates.TemplateResponse("errors/500.html", {"request": request, "user": None, "error": str(exc)},
                                      status_code=500)

# ----------------------------

@app.get("/")
async def root():
    return RedirectResponse(url="/admin/login")


@app.get("/admin")
async def admin_root():
    return RedirectResponse(url="/admin/dashboard")