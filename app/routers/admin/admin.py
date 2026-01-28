from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.infrastructure.database import async_session_maker
from datetime import timedelta

# --- НАСТРОЙКА ШАБЛОНОВ ---
templates = Jinja2Templates(directory="templates/admin")

# Фильтр времени (МСК)
def msk_format(value):
    """Конвертирует UTC в МСК (+3 часа) и форматирует"""
    if not value:
        return "-"
    msk_time = value + timedelta(hours=3)
    return msk_time.strftime("%d.%m.%Y %H:%M")

# Регистрируем фильтр
templates.env.filters["msk"] = msk_format


# --- ЗАВИСИМОСТЬ БАЗЫ ДАННЫХ ---
async def get_db():
    async with async_session_maker() as session:
        yield session


# --- РОУТЕРЫ ---

# 1. Защищенный роутер (для дашборда, пользователей, достижений)
# Используйте его в файлах dashboard.py, users.py, achievements.py
guard_router = APIRouter(prefix="/admin", tags=["Admin Protected"])

# 2. Публичный роутер (для логина, статики, если нужно)
# Этот роутер импортируется в main.py
public_router = APIRouter(prefix="/admin", tags=["Admin Public"])


# --- ПРОВЕРКА АВТОРИЗАЦИИ (ЗАМЕНА MIDDLEWARE) ---
# Если вы хотите глобально проверять авторизацию для guard_router,
# лучше делать это через dependencies=[Depends(check_auth)] при создании роутера,
# либо вызывать проверку внутри каждого эндпоинта (как мы делали check_access).
# Ошибочный блок @guard_router.middleware("http") был удален.