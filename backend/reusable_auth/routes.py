"""
FastAPI auth & admin routes. Call register_auth_routes(app, ...) to mount them.

Provides:
    POST /api/auth/login
    GET  /api/auth/me
    GET  /api/admin/permissions
    GET  /api/admin/users
    POST /api/admin/users
    PUT  /api/admin/users/{user_id}
    DELETE /api/admin/users/{user_id}
    PUT  /api/admin/users/{user_id}/password
    GET  /api/admin/users/{user_id}/permissions
    PUT  /api/admin/users/{user_id}/permissions
"""

from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from .auth_service import AuthService


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""
    email: str = ""
    permissions: Optional[List[str]] = None


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    new_password: str


class SetPermissionsRequest(BaseModel):
    permissions: List[str]


def register_auth_routes(app: FastAPI, auth_service: AuthService, all_permissions: list):
    """Mount login, /me, and admin CRUD endpoints onto the given FastAPI app."""

    def _require_admin(request: Request):
        perms = request.state.user.get("permissions", [])
        if "admin" not in perms:
            raise HTTPException(status_code=403, detail="Admin access required")

    # ── login / me ───────────────────────────────────────────────────

    @app.post("/api/auth/login")
    async def login(body: LoginRequest):
        user = auth_service.authenticate(body.username, body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = auth_service.create_token(user)
        return {"token": token, "user": user}

    @app.get("/api/auth/me")
    async def get_current_user(request: Request):
        payload = request.state.user
        user = auth_service.get_user_by_id(int(payload["sub"]))
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    # ── admin: permissions catalogue ─────────────────────────────────

    @app.get("/api/admin/permissions")
    async def get_all_permissions_route(request: Request):
        _require_admin(request)
        return all_permissions

    # ── admin: user CRUD ─────────────────────────────────────────────

    @app.get("/api/admin/users")
    async def list_users(request: Request):
        _require_admin(request)
        return auth_service.get_all_users()

    @app.post("/api/admin/users")
    async def create_user(body: CreateUserRequest, request: Request):
        _require_admin(request)
        user = auth_service.create_user(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            email=body.email,
            permissions=body.permissions,
        )
        if user is None:
            raise HTTPException(status_code=400, detail="Username already exists")
        return user

    @app.put("/api/admin/users/{user_id}")
    async def update_user(user_id: int, body: UpdateUserRequest, request: Request):
        _require_admin(request)
        user = auth_service.update_user(
            user_id,
            display_name=body.display_name,
            email=body.email,
            is_active=body.is_active,
        )
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    @app.delete("/api/admin/users/{user_id}")
    async def delete_user(user_id: int, request: Request):
        _require_admin(request)
        if int(request.state.user["sub"]) == user_id:
            raise HTTPException(status_code=400, detail="Cannot delete your own account")
        if not auth_service.delete_user(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        return {"status": "success"}

    @app.put("/api/admin/users/{user_id}/password")
    async def admin_change_password(user_id: int, body: ChangePasswordRequest, request: Request):
        _require_admin(request)
        if not auth_service.change_password(user_id, body.new_password):
            raise HTTPException(status_code=404, detail="User not found")
        return {"status": "success"}

    # ── admin: per-user permissions ──────────────────────────────────

    @app.get("/api/admin/users/{user_id}/permissions")
    async def get_user_permissions_route(user_id: int, request: Request):
        _require_admin(request)
        return auth_service.get_user_permissions(user_id)

    @app.put("/api/admin/users/{user_id}/permissions")
    async def set_user_permissions_route(user_id: int, body: SetPermissionsRequest, request: Request):
        _require_admin(request)
        perms = auth_service.set_user_permissions(user_id, body.permissions)
        return {"permissions": perms}
