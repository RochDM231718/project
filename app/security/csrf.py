# app/security/csrf.py
import secrets
from fastapi import Request, HTTPException, Form, Depends

# Имя ключа в сессии и в форме
CSRF_KEY = "csrf_token"

def get_csrf_token(request: Request):
    """
    Генерирует токен, если его нет в сессии, и возвращает его.
    Используется для подстановки в шаблоны.
    """
    token = request.session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_KEY] = token
    return token

async def validate_csrf(request: Request):
    """
    Зависимость для проверки токена в POST-запросах.
    """
    if request.method == "POST":
        form = await request.form()
        submitted_token = form.get(CSRF_KEY)
        session_token = request.session.get(CSRF_KEY)

        if not session_token or not submitted_token or session_token != submitted_token:
            raise HTTPException(status_code=403, detail="CSRF Token Mismatch. Обновите страницу.")