"""
JWT authentication middleware for FastAPI.

Usage:
    from reusable_auth.middleware import JWTAuthMiddleware

    app.add_middleware(JWTAuthMiddleware, auth_service=auth_service, exempt_paths={"/api/auth/login"})
"""

from typing import Set
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .auth_service import AuthService


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Require a valid JWT Bearer token on every /api/ route except exempt paths."""

    def __init__(self, app, auth_service: AuthService, exempt_paths: Set[str] = None):
        super().__init__(app)
        self.auth_service = auth_service
        self.exempt_paths = exempt_paths or {"/api/auth/login"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if request.method == "OPTIONS":
            return await call_next(request)

        if not path.startswith("/api/") or path in self.exempt_paths:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid user. Authentication token required."},
            )

        token = auth_header[7:]
        payload = self.auth_service.verify_token(token)
        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid user. Token expired or invalid."},
            )

        request.state.user = payload
        return await call_next(request)
