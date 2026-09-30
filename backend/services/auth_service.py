"""
Reusable JWT authentication service.

Drop this module into any FastAPI project. Configure via environment variables:
    JWT_SECRET_KEY  – signing key (required in production)
    JWT_ALGORITHM   – default HS256
    JWT_EXPIRY_HOURS – token lifetime, default 24
"""

import os
import sqlite3
import hashlib
import hmac
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import jwt  # PyJWT

from services.permissions import ALL_PERMISSION_KEYS, DEFAULT_PERMISSIONS

logger = logging.getLogger("auth_service")

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change-me-in-production-" + secrets.token_hex(16))
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))


def _hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    """Return (hex_hash, hex_salt) using PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = secrets.token_bytes(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260_000)
    return dk.hex(), salt.hex()


def _verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(stored_salt), iterations=260_000
    )
    return hmac.compare_digest(dk.hex(), stored_hash)


class AuthService:
    """Handles user CRUD, password verification, and JWT token lifecycle."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ── table bootstrap ──────────────────────────────────────────────

    def create_tables(self):
        conn = self._conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    display_name TEXT,
                    email TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT (datetime('now')),
                    last_login DATETIME
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    permission_key TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, permission_key)
                )
            """)
            # Drop legacy role column if it exists
            cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
            if "role" in cols:
                try:
                    conn.execute("ALTER TABLE users DROP COLUMN role")
                except Exception:
                    pass  # SQLite < 3.35 doesn't support DROP COLUMN; harmless to ignore
            conn.commit()
        finally:
            conn.close()

    def ensure_default_admin(self, username: str = "admin", password: str = "admin"):
        """Create the default admin account with all permissions if no users exist."""
        conn = self._conn()
        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
            if row["cnt"] == 0:
                pw_hash, pw_salt = _hash_password(password)
                conn.execute(
                    "INSERT INTO users (username, password_hash, password_salt, display_name) "
                    "VALUES (?, ?, ?, ?)",
                    (username, pw_hash, pw_salt, "Admin User"),
                )
                admin_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                for perm_key in ALL_PERMISSION_KEYS:
                    conn.execute(
                        "INSERT OR IGNORE INTO user_permissions (user_id, permission_key) VALUES (?, ?)",
                        (admin_id, perm_key),
                    )
                conn.commit()
                logger.info("Default admin user created (username: %s) with all permissions", username)

            # Ensure existing users who have "admin" permission also have any new permissions added since
            admin_user_ids = conn.execute(
                "SELECT DISTINCT user_id FROM user_permissions WHERE permission_key = 'admin'"
            ).fetchall()
            for uid_row in admin_user_ids:
                for perm_key in ALL_PERMISSION_KEYS:
                    conn.execute(
                        "INSERT OR IGNORE INTO user_permissions (user_id, permission_key) VALUES (?, ?)",
                        (uid_row["user_id"], perm_key),
                    )
            conn.commit()
        finally:
            conn.close()

    # ── authentication ───────────────────────────────────────────────

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Verify credentials. Returns user dict with permissions or None."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
            ).fetchone()
            if row is None:
                return None
            if not _verify_password(password, row["password_hash"], row["password_salt"]):
                return None
            conn.execute(
                "UPDATE users SET last_login = datetime('now') WHERE id = ?", (row["id"],)
            )
            conn.commit()
            return self._user_dict_with_perms(conn, row)
        finally:
            conn.close()

    # ── JWT helpers ──────────────────────────────────────────────────

    def create_token(self, user: Dict[str, Any]) -> str:
        payload = {
            "sub": str(user["id"]),
            "username": user["username"],
            "permissions": user.get("permissions", []),
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate a JWT. Returns the payload or None."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.debug("Token expired")
            return None
        except jwt.InvalidTokenError as exc:
            logger.debug("Invalid token: %s", exc)
            return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)
            ).fetchone()
            return self._user_dict_with_perms(conn, row) if row else None
        finally:
            conn.close()

    # ── user management ──────────────────────────────────────────────

    def create_user(
        self, username: str, password: str, display_name: str = "", email: str = "",
        permissions: Optional[list] = None,
    ) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            pw_hash, pw_salt = _hash_password(password)
            conn.execute(
                "INSERT INTO users (username, password_hash, password_salt, display_name, email) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, pw_hash, pw_salt, display_name, email),
            )
            user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            perm_list = permissions if permissions is not None else DEFAULT_PERMISSIONS
            for perm_key in perm_list:
                if perm_key in ALL_PERMISSION_KEYS:
                    conn.execute(
                        "INSERT OR IGNORE INTO user_permissions (user_id, permission_key) VALUES (?, ?)",
                        (user_id, perm_key),
                    )
            conn.commit()
            return self._get_user_with_perms(conn, user_id)
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    def get_all_users(self) -> list:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
            return [self._user_dict_with_perms(conn, row) for row in rows]
        finally:
            conn.close()

    def update_user(self, user_id: int, display_name: str = None, email: str = None, is_active: bool = None) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            updates, params = [], []
            if display_name is not None:
                updates.append("display_name = ?"); params.append(display_name)
            if email is not None:
                updates.append("email = ?"); params.append(email)
            if is_active is not None:
                updates.append("is_active = ?"); params.append(int(is_active))
            if not updates:
                return self._get_user_with_perms(conn, user_id)
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            return self._get_user_with_perms(conn, user_id)
        finally:
            conn.close()

    def delete_user(self, user_id: int) -> bool:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
            cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def change_password(self, user_id: int, new_password: str) -> bool:
        conn = self._conn()
        try:
            pw_hash, pw_salt = _hash_password(new_password)
            conn.execute(
                "UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
                (pw_hash, pw_salt, user_id),
            )
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    # ── permissions ──────────────────────────────────────────────────

    def get_user_permissions(self, user_id: int) -> list:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT permission_key FROM user_permissions WHERE user_id = ?", (user_id,)
            ).fetchall()
            return [r["permission_key"] for r in rows]
        finally:
            conn.close()

    def set_user_permissions(self, user_id: int, permission_keys: list) -> list:
        valid_keys = [k for k in permission_keys if k in ALL_PERMISSION_KEYS]
        conn = self._conn()
        try:
            conn.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
            for key in valid_keys:
                conn.execute(
                    "INSERT INTO user_permissions (user_id, permission_key) VALUES (?, ?)",
                    (user_id, key),
                )
            conn.commit()
            return valid_keys
        finally:
            conn.close()

    # ── helpers ──────────────────────────────────────────────────────

    def _get_user_with_perms(self, conn: sqlite3.Connection, user_id: int) -> Optional[Dict[str, Any]]:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return self._user_dict_with_perms(conn, row)

    def _user_dict_with_perms(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Dict[str, Any]:
        perms = conn.execute(
            "SELECT permission_key FROM user_permissions WHERE user_id = ?", (row["id"],)
        ).fetchall()
        d = self._user_dict(row)
        d["permissions"] = [p["permission_key"] for p in perms]
        return d

    @staticmethod
    def _user_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "email": row["email"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
            "last_login": row["last_login"],
        }
