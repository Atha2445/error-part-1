import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("vids.subscription")

TRIAL_DURATION_DAYS = 30


class SubscriptionService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.error(f"Subscription DB error: {e}")
            return None

    def _ensure_row(self, conn):
        """If the subscription row is missing, create a fresh trial and return it."""
        row = conn.execute("SELECT * FROM subscription WHERE id = 1").fetchone()
        if row:
            return row
        now = datetime.utcnow()
        trial_end = now + timedelta(days=TRIAL_DURATION_DAYS)
        conn.execute(
            "INSERT INTO subscription (id, plan, trial_start, trial_end, is_active) VALUES (1, 'free_trial', ?, ?, 1)",
            (now.isoformat(), trial_end.isoformat()),
        )
        conn.commit()
        logger.info(f"Fresh trial created: {now.isoformat()} -> {trial_end.isoformat()}")
        return conn.execute("SELECT * FROM subscription WHERE id = 1").fetchone()

    def get_status(self) -> dict:
        """Return current subscription status (permanently active/unlimited)."""
        now = datetime.utcnow()
        return {
            "plan": "paid",
            "expired": False,
            "days_remaining": -1,
            "trial_start": now.isoformat(),
            "trial_end": (now + timedelta(days=36500)).isoformat(),
        }

    def is_trial_expired(self) -> bool:
        return False

    def activate_license(self, license_key: str) -> dict:
        """Validate and activate a paid license key."""
        if not self._validate_license_key(license_key):
            return {"success": False, "error": "Invalid license key"}

        conn = self._get_connection()
        if not conn:
            return {"success": False, "error": "Database error"}

        try:
            now = datetime.utcnow()
            conn.execute(
                "UPDATE subscription SET plan = 'paid', is_active = 1, license_key = ?, activated_at = ? WHERE id = 1",
                (license_key, now.isoformat()),
            )
            conn.commit()
            logger.info(f"License activated: {license_key[:8]}...")
            return {"success": True, "message": "License activated successfully"}
        except sqlite3.Error as e:
            logger.error(f"Error activating license: {e}")
            return {"success": False, "error": "Failed to activate license"}
        finally:
            conn.close()

    @staticmethod
    def _validate_license_key(key: str) -> bool:
        """Validate the license key format.
        Replace this with real validation (e.g. server call, cryptographic check)."""
        if not key or len(key) < 16:
            return False
        return key.startswith("VLX-")
