from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request


class UploadProtectionMiddleware(BaseHTTPMiddleware):
    """Block direct access to /static/uploads/achievements/ without authentication.

    Achievement files (PDFs, scans) contain sensitive user data and must
    only be served through the authenticated /documents/{id}/download endpoint.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path.startswith("/static/uploads/achievements/"):
            try:
                auth_id = request.session.get("auth_id")
            except Exception:
                auth_id = None

            if not auth_id:
                return Response(status_code=403, content="Forbidden")

        return await call_next(request)
