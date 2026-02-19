from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from app.security.csrf import get_csrf_token
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware  # <--- Добавлен импорт
from fastapi.middleware.trustedhost import TrustedHostMiddleware  # <--- Добавлен импорт
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import os
import logging
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

# Настройка логгера
logger = logging.getLogger("uvicorn.error")

app = FastAPI(root_path=os.getenv("ROOT_PATH", ""))


# --- MIDDLEWARES ---

class CSRFContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Гарантируем, что CSRF токен есть в сессии.
        # Шаблоны будут брать его через {{ request.session.csrf_token }}
        get_csrf_token(request)
        response = await call_next(request)
        return response


@app.on_event("startup")
async def init_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


app.mount("/static", StaticFiles(directory="static"), name="static")

# --- КОНФИГУРАЦИЯ БЕЗОПАСНОСТИ ---

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "supersecretkey123":
    if os.getenv("ENV") == "production":
        raise ValueError("КРИТИЧЕСКАЯ ОШИБКА: Не установлен безопасный SECRET_KEY в переменной окружения!")
    else:
        logger.warning("ПРЕДУПРЕЖДЕНИЕ: Используется небезопасный SECRET_KEY!")

# ВНИМАНИЕ: Порядок добавления middleware важен (снизу вверх по исполнению).
# Поток запроса: TrustedHost -> Session -> CSRF -> Router

# 3. Внутренний слой: CSRF (требует наличия сессии)
app.add_middleware(CSRFContextMiddleware)

# 2. Средний слой: Сессии
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# 1. Внешний слой: Проверка хоста (защита от Host Header Injection)
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# --- ПОДКЛЮЧЕНИЕ РОУТЕРОВ ---
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
    if exc.status_code == 404:
        return templates.TemplateResponse("errors/404.html", {"request": request, "user": None}, status_code=404)
    elif exc.status_code == 403:
        return templates.TemplateResponse("errors/403.html", {"request": request, "user": None, "detail": exc.detail},
                                          status_code=403)
    return templates.TemplateResponse("errors/500.html", {"request": request, "user": None, "error": exc.detail},
                                      status_code=exc.status_code)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {exc}", exc_info=True)

    # Безопасная проверка режима отладки
    is_debug = str(os.getenv("DEBUG", "False")).lower() in ("true", "1", "yes")

    error_msg = str(exc) if is_debug else "Внутренняя ошибка сервера"

    return templates.TemplateResponse("errors/500.html", {
        "request": request,
        "user": None,
        "error": error_msg
    }, status_code=500)


@app.get("/")
async def root(request: Request):
    return RedirectResponse(url=request.url_for('admin.auth.login_page'))


@app.get("/admin")
async def admin_root(request: Request):
    return RedirectResponse(url=request.url_for('admin.dashboard.index'))