import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

_logger = logging.getLogger(__name__)

DB_DRIVER = os.getenv("DB_DRIVER", "postgresql")
DB_USER = os.getenv("DB_USERNAME", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "sirius_db")

if DB_DRIVER == "sqlite":
    DATABASE_URL = "sqlite+aiosqlite:///./db.sqlite3"
else:
    DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

safe_url = DATABASE_URL.replace(DB_PASSWORD, "****") if DB_PASSWORD else DATABASE_URL
_logger.info("Database connection: %s", safe_url)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session_maker() as session:
        yield session

# --- ВАЖНО: Импортируем модели здесь, чтобы они знали друг о друге ---
# (Используем try/except чтобы не ломать скрипты, если таблицы еще не созданы)
try:
    from app.models.user import Users
    from app.models.achievement import Achievement
    from app.models.notification import Notification
    from app.models.user_token import UserToken
except ImportError:
    pass