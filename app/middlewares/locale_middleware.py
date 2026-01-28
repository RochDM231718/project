from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.infrastructure.tranaslations import current_locale


class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ЖЕСТКО ЗАДАЕМ РУССКИЙ ЯЗЫК
        # Игнорируем сессию и браузер, всегда 'ru'
        locale = 'ru'
        request.session['locale'] = locale

        token = current_locale.set(locale)

        try:
            response = await call_next(request)
            return response
        finally:
            current_locale.reset(token)