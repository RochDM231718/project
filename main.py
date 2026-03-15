from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from app.security.csrf import get_csrf_token
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
import os
import logging
import secrets
from dotenv import load_dotenv

from app.infrastructure.database import engine, async_session_maker, Base
from app.middlewares.security_headers import SecurityHeadersMiddleware
from app.middlewares.upload_protection import UploadProtectionMiddleware

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

# Import models so Base.metadata.create_all picks them up
from app.models.support_ticket import SupportTicket  # noqa: F401
from app.models.support_message import SupportMessage  # noqa: F401

# Import to register routes on guard_router
import app.routers.admin.support  # noqa: F401
import app.routers.admin.moderation_support  # noqa: F401

load_dotenv()

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app):
    from sqlalchemy import text
    async with engine.begin() as conn:
        # Create support enum and tables if they don't exist
        # Drop and recreate enum if table doesn't exist yet (safe: no data loss)
        table_exists = await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'support_tickets')"
        ))
        if not table_exists.scalar():
            await conn.execute(text("DROP TYPE IF EXISTS supportticketstatus CASCADE;"))
            await conn.execute(text(
                "CREATE TYPE supportticketstatus AS ENUM ('open', 'in_progress', 'closed')"
            ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subject VARCHAR(255) NOT NULL,
                status supportticketstatus DEFAULT 'open',
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            );
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id SERIAL PRIMARY KEY,
                ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
                sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                text TEXT,
                file_path VARCHAR,
                is_from_moderator BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT now()
            );
        """))
    yield
    await engine.dispose()
    logger.info("Database engine disposed. Graceful shutdown complete.")


app = FastAPI(root_path=os.getenv("ROOT_PATH", ""), lifespan=lifespan)

class CSRFContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        get_csrf_token(request)
        response = await call_next(request)
        return response


app.mount("/static", StaticFiles(directory="static"), name="static")

ENV = os.getenv("ENV", "development")
IS_DEBUG = str(os.getenv("DEBUG", "False")).lower() in ("true", "1", "yes")

if ENV == "production":
    IS_DEBUG = False

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "supersecretkey123":
    if ENV == "production":
        raise ValueError("КРИТИЧЕСКАЯ ОШИБКА: Не установлен безопасный SECRET_KEY в переменной окружения!")
    else:
        logger.warning("ПРЕДУПРЕЖДЕНИЕ: Не установлен SECRET_KEY! Сгенерирован временный случайный ключ для разработки.")
        SECRET_KEY = secrets.token_urlsafe(32)

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(UploadProtectionMiddleware)

app.add_middleware(CSRFContextMiddleware)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=ENV == "production", same_site="lax")

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

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
    logger.error(f"Global error: {exc}", exc_info=True)

    error_msg = str(exc) if IS_DEBUG else "Внутренняя ошибка сервера"

    return templates.TemplateResponse("errors/500.html", {
        "request": request,
        "user": None,
        "error": error_msg
    }, status_code=500)


@app.get("/health", include_in_schema=False)
async def health_check():
    """Health check for Docker/load balancer monitoring."""
    try:
        async with async_session_maker() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok", "database": "connected"})
    except Exception:
        return JSONResponse({"status": "error", "database": "unavailable"}, status_code=503)


@app.get("/")
async def root(request: Request):
    return RedirectResponse(url=request.url_for('admin.auth.login_page'))


@app.get("/admin")
async def admin_root(request: Request):
    return RedirectResponse(url=request.url_for('admin.dashboard.index'))