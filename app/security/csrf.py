import secrets
from fastapi import Request, HTTPException

CSRF_KEY = "csrf_token"


def get_csrf_token(request: Request):
    token = request.session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_KEY] = token
    return token


async def validate_csrf(request: Request):
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        session_token = request.session.get(CSRF_KEY)

        submitted_token = request.headers.get("X-CSRF-Token")

        if not submitted_token:
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                form = await request.form()
                submitted_token = form.get(CSRF_KEY)

        if not session_token or not submitted_token or not secrets.compare_digest(session_token, submitted_token):
            raise HTTPException(status_code=403, detail="CSRF Token Mismatch. Обновите страницу.")