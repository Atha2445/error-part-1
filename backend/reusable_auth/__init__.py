"""
Reusable JWT Auth Module for FastAPI + SQLite.

Copy this folder into any FastAPI project, then:

    from reusable_auth import AuthService, setup_auth

    auth = setup_auth(app, db_path="data/app.db", permissions=MY_PERMISSIONS)

See README.md for full integration guide.
"""

from .auth_service import AuthService
from .middleware import JWTAuthMiddleware
from .routes import register_auth_routes
from .setup import setup_auth

__all__ = [
    "AuthService",
    "JWTAuthMiddleware",
    "register_auth_routes",
    "setup_auth",
]
