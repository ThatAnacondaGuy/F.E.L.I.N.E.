"""Local auth middleware for Meow OS."""
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

class LocalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.scope.get("type") == "websocket":
            return await call_next(request)
            
        client_ip = request.client.host if request.client else "127.0.0.1"
        allowed_ips = ["127.0.0.1", "::1", "localhost", "testclient"]
        
        if client_ip not in allowed_ips and not request.url.path.startswith("/static"):
            return JSONResponse(
                status_code=403,
                content={"detail": "Access forbidden: Localhost only"}
            )
            
        return await call_next(request)
