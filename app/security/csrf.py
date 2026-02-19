import secrets
from fastapi import Request, HTTPException, Form, Depends

CSRF_KEY = "csrf_token"

def get_csrf_token(request: Request):
    token = request.session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_KEY] = token
    return token

async def validate_csrf(request: Request):
    if request.method == "POST":
        form = await request.form()
        submitted_token = form.get(CSRF_KEY)
        session_token = request.session.get(CSRF_KEY)

        if not session_token or not submitted_token or session_token != submitted_token:
            raise HTTPException(status_code=403, detail="CSRF Token Mismatch. Обновите страницу.")