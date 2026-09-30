"""
One-call setup function that wires everything together.

Usage:
    from reusable_auth import setup_auth

    MY_PERMISSIONS = [
        {"key": "dashboard", "label": "Dashboard", "description": "View dashboard"},
        {"key": "admin",     "label": "Admin",     "description": "Manage users & permissions"},
    ]

    auth_service = setup_auth(
        app,
        db_path="data/app.db",
        permissions=MY_PERMISSIONS,
        default_permissions=["dashboard"],
        exempt_paths={"/api/auth/login", "/api/health"},
    )
"""

import logging
from typing import List, Set, Optional
from fastapi import FastAPI

from .auth_service import AuthService
from .middleware import JWTAuthMiddleware
from .routes import register_auth_routes

logger = logging.getLogger("reusable_auth.setup")


def setup_auth(
    app: FastAPI,
    db_path: str,
    permissions: List[dict],
    default_permissions: Optional[List[str]] = None,
    exempt_paths: Optional[Set[str]] = None,
    admin_username: str = "admin",
    admin_password: str = "admin",
) -> AuthService:
    """
    Wire auth into a FastAPI app in one call.

    Args:
        app:                 The FastAPI application instance.
        db_path:             Path to the SQLite database file.
        permissions:         List of {"key", "label", "description"} dicts — your page/module registry.
        default_permissions: Keys assigned to new non-admin users. Defaults to first 3 permission keys.
        exempt_paths:        URL paths that skip JWT verification (login is always exempt).
        admin_username:      Default admin username created on first run.
        admin_password:      Default admin password created on first run.

    Returns:
        The AuthService instance (in case you need it for custom endpoints).
    """
    all_keys = [p["key"] for p in permissions]
    defaults = default_permissions or all_keys[:3]

    auth_service = AuthService(db_path, all_keys, defaults)

    def _init_db():
        logger.info("Initializing auth tables and ensuring default admin exists...")
        auth_service.create_tables()
        auth_service.ensure_default_admin(admin_username, admin_password)
        logger.info("Auth initialization complete.")

    # Run immediately so tables exist for middleware registration
    _init_db()

    # Also re-run on every startup to recover from unclean shutdowns
    @app.on_event("startup")
    async def _reinit_auth_tables():
        _init_db()

    base_exempt = {"/api/auth/login"}
    if exempt_paths:
        base_exempt |= exempt_paths

    app.add_middleware(JWTAuthMiddleware, auth_service=auth_service, exempt_paths=base_exempt)
    register_auth_routes(app, auth_service, permissions)

    return auth_service
