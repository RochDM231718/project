import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response

logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Генерируем ID запроса
        request_id = str(uuid.uuid4())

        # Добавляем ID в контекст логгера (он будет во всех логах этого запроса)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            client_ip=request.client.host if request.client else "unknown"
        )

        start_time = time.time()

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Логируем успешный запрос (или ошибку 4xx/5xx)
            status_code = response.status_code
            log_method = logger.info if status_code < 400 else (logger.warning if status_code < 500 else logger.error)

            log_method(
                "Request finished",
                status_code=status_code,
                duration=f"{process_time:.4f}s"
            )

            # Добавляем заголовок с ID запроса в ответ (полезно для отладки)
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                "Request failed",
                error=str(e),
                duration=f"{process_time:.4f}s"
            )
            raise e