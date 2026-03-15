from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request


class UploadProtectionMiddleware(BaseHTTPMiddleware):
    """Block direct access to /static/uploads/ without authentication.

    Achievement files and support attachments contain sensitive user data
    and must only be served to authenticated users.
    """

    PROTECTED_PATHS = [
        "/static/uploads/achievements/",
        "/static/uploads/support/",
    ]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if any(path.startswith(p) for p in self.PROTECTED_PATHS):
            try:
                auth_id = request.session.get("auth_id")
            except Exception:
                auth_id = None

            if not auth_id:
                return Response(status_code=403, content="Forbidden")

        return await call_next(request)
