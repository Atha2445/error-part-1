import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("vids.db_initializer")

TRIAL_DURATION_DAYS = 30


class DatabaseInitializer:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @classmethod
    def init_db(cls, db_path: str):
        cls(db_path).initialize_db()

    def initialize_db(self, db_path: str = None):
        """Main entry point to initialize database and tables."""
        if isinstance(self, str):
            # Invoked as DatabaseInitializer.initialize_db(path)
            DatabaseInitializer(self).initialize_db()
            return
        if db_path:
            self.db_path = db_path
        self._create_tables()
        self._ensure_subscription_record()
        self._ensure_default_prompts()

    def _get_connection(self):
        """Return a new SQLite connection with row_factory set."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to SQLite: {e}")
            return None

    def _create_tables(self):
        """Create required tables if they don't exist."""
        connection = self._get_connection()
        if not connection:
            return

        try:
            cursor = connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_text TEXT NOT NULL,
                    category TEXT DEFAULT 'normal',
                    is_suspicious INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    display_order INTEGER DEFAULT 0
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT NOT NULL,
                    frame_number INTEGER NOT NULL,
                    detected_action TEXT,
                    confidence REAL,
                    is_alert INTEGER,
                    occupancy_count INTEGER DEFAULT 0,
                    timestamp DATETIME DEFAULT (datetime('now'))
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS video_verdicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT NOT NULL,
                    total_analyzed INTEGER,
                    suspicious_frames INTEGER,
                    normal_frames INTEGER,
                    suspicious_percentage REAL,
                    risk_level TEXT,
                    needs_attention INTEGER,
                    recommendation TEXT,
                    ai_summary TEXT,
                    timestamp DATETIME DEFAULT (datetime('now'))
                )
            """)

            # Migration: ensure ai_summary column exists in existing databases
            try:
                cursor.execute("ALTER TABLE video_verdicts ADD COLUMN ai_summary TEXT")
            except sqlite3.OperationalError:
                pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cctv_ips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    location TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'unknown',
                    last_checked DATETIME DEFAULT (datetime('now')),
                    created_at DATETIME DEFAULT (datetime('now'))
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscription (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    plan TEXT NOT NULL DEFAULT 'free_trial',
                    trial_start DATETIME NOT NULL,
                    trial_end DATETIME NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    license_key TEXT,
                    activated_at DATETIME
                )
            """)

            connection.commit()
            logger.info("All required tables checked/created.")

        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            connection.rollback()
        finally:
            connection.close()

    def _ensure_subscription_record(self):
        """Insert the single subscription row on first run so the trial clock starts."""
        connection = self._get_connection()
        if not connection:
            return
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM subscription WHERE id = 1")
            if cursor.fetchone() is None:
                now = datetime.utcnow()
                trial_end = now + timedelta(days=TRIAL_DURATION_DAYS)
                cursor.execute(
                    "INSERT INTO subscription (id, plan, trial_start, trial_end, is_active) VALUES (1, 'free_trial', ?, ?, 1)",
                    (now.isoformat(), trial_end.isoformat()),
                )
                connection.commit()
                logger.info("Free trial started: %s -> %s", now.isoformat(), trial_end.isoformat())
        except sqlite3.Error as e:
            logger.error(f"Error ensuring subscription record: {e}")
            connection.rollback()
        finally:
            connection.close()

    # Default prompts (is_suspicious=1) seeded on first run so auto-scan and
    # upload analysis work out of the box. Users can edit them in Settings -> Prompts.
    DEFAULT_PROMPTS = [
        # Weapon / threat
        ("a person holding a gun",        "weapon",      1, 10),
        ("a person holding a knife",      "weapon",      1, 20),
        ("a person holding a weapon",     "weapon",      1, 30),
        # Violence
        ("two people fighting",           "violence",    1, 40),
        ("a person being attacked",       "violence",    1, 50),
        ("a group of people fighting",    "violence",    1, 60),
        # Theft
        ("a person stealing something",   "theft",       1, 70),
        ("a person breaking into a store", "theft",      1, 80),
        # Intrusion
        ("an intruder breaking in",       "intrusion",   1, 90),
        ("a person entering an unauthorized area", "intrusion", 1, 100),
        # Normal baseline (non-suspicious anchors the operator sees)
        ("a person walking normally",     "normal",      0, 110),
        ("people working in an office",   "normal",      0, 120),
        ("an empty room",                 "normal",      0, 130),
    ]

    def _ensure_default_prompts(self):
        """Seed default prompts only when the prompts table is empty."""
        connection = self._get_connection()
        if not connection:
            return
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) AS cnt FROM prompts")
            if cursor.fetchone()["cnt"] == 0:
                cursor.executemany(
                    "INSERT INTO prompts (prompt_text, category, is_suspicious, is_active, display_order) "
                    "VALUES (?, ?, ?, 1, ?)",
                    self.DEFAULT_PROMPTS,
                )
                connection.commit()
                logger.info("Seeded %d default detection prompts", len(self.DEFAULT_PROMPTS))
        except sqlite3.Error as e:
            logger.error(f"Error seeding default prompts: {e}")
            connection.rollback()
        finally:
            connection.close()
