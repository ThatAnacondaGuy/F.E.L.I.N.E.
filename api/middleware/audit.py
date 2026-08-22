"""Audit middleware for logging requests."""
import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

logger = logging.getLogger("meow_os.audit")

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Redact logic can be placed here if reading bodies (requires careful handling of stream)
        response = await call_next(request)
        
        process_time = time.time() - start_time
        logger.info(
            f"AUDIT | {request.client.host} | {request.method} {request.url.path} "
            f"| {response.status_code} | {process_time:.4f}s"
        )
        return response
