import os
import sys


def _handle_cli_reset_trial() -> None:
    """If invoked with --reset-trial, reset the subscription row so the next
    launch sees a fresh 30-day trial, then exit. Called by the installer
    on every install so each install grants a fresh trial. Runs before any
    heavy imports (transformers, torch, FastAPI) to keep the install path fast.
    """
    if "--reset-trial" not in sys.argv:
        return
    from datetime import datetime, timedelta

    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.name == "nt":
        data_dir = os.environ.get("VIGILINX_DATA_DIR", r"C:\Vigilinx")
    else:
        data_dir = os.environ.get("VIGILINX_DATA_DIR", os.path.join(base_dir, "data"))
    db_path = os.environ.get("DB_PATH", os.path.join(data_dir, "vigilinx.db"))
    try:
        if os.path.isfile(db_path):
            import sqlite3

            now = datetime.utcnow()
            trial_end = now + timedelta(days=30)
            start_iso = now.isoformat()
            end_iso = trial_end.isoformat()
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                row = conn.execute("SELECT id FROM subscription WHERE id = 1").fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO subscription (id, plan, trial_start, trial_end, is_active) "
                        "VALUES (1, 'free_trial', ?, ?, 1)",
                        (start_iso, end_iso),
                    )
                else:
                    conn.execute(
                        "UPDATE subscription SET plan = 'free_trial', trial_start = ?, "
                        "trial_end = ?, is_active = 1, license_key = NULL, activated_at = NULL "
                        "WHERE id = 1",
                        (start_iso, end_iso),
                    )
                conn.commit()
                try:
                    conn.execute("PRAGMA wal_checkpoint(FULL)")
                except sqlite3.Error:
                    pass
            finally:
                conn.close()
            print(f"[Vigilinx] Trial reset. New trial: {start_iso} -> {end_iso}")
        else:
            print(f"[Vigilinx] No existing DB at {db_path}; fresh trial will be created on first launch.")
    except Exception as e:
        print(f"[Vigilinx] Reset-trial failed: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


_handle_cli_reset_trial()


def _bootstrap_runtime() -> None:
    """Windows console encoding + TLS CA paths for PyInstaller / Hugging Face downloads."""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if stream is not None and hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass
    try:
        import certifi

        ca_path = certifi.where()
        if not os.path.isfile(ca_path):
            meipass = getattr(sys, "_MEIPASS", "") if getattr(sys, "frozen", False) else ""
            if meipass:
                for name in ("certifi/cacert.pem", "cacert.pem"):
                    candidate = os.path.join(meipass, *name.split("/"))
                    if os.path.isfile(candidate):
                        ca_path = candidate
                        break
        if os.path.isfile(ca_path):
            os.environ.setdefault("SSL_CERT_FILE", ca_path)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)
            os.environ.setdefault("CURL_CA_BUNDLE", ca_path)
    except Exception:
        pass


_bootstrap_runtime()

from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, File, UploadFile, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import List, Optional, Dict, Any
from services.video_service import VideoService
from fastapi.responses import FileResponse
import sqlite3
import uuid
import shutil
import time
from services.watchdog_service import WatchdogService
from services.alert_service import AlertService
from services.db_initializer import DatabaseInitializer
from services.cctv_service import CCTVService
from services.subscription_service import SubscriptionService
from services.schemas import PromptCreate, CCTVIPCreate
from services.permissions import ALL_PERMISSIONS, DEFAULT_PERMISSIONS
from reusable_auth import setup_auth
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import asyncio
import threading
import logging
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _get_app_data_dir() -> str:
    """Return a writable directory for app data (DB, videos, uploads, outputs, config).
    On Windows uses C:\Vigilinx, falling back to %LOCALAPPDATA%\Vigilinx if C:\ has restricted permissions.
    Elsewhere uses a 'data' folder next to main.py.
    Can be overridden via VIGILINX_DATA_DIR env var."""
    override = os.environ.get("VIGILINX_DATA_DIR")
    if override:
        return override
    if os.name == "nt":
        target = r"C:\Vigilinx"
        try:
            os.makedirs(target, exist_ok=True)
            test_file = os.path.join(target, ".perm_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return target
        except Exception:
            local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            fallback = os.path.join(local_app, "Vigilinx")
            os.makedirs(fallback, exist_ok=True)
            return fallback
    return os.path.join(BASE_DIR, "data")

APP_DATA_DIR = _get_app_data_dir()
os.makedirs(APP_DATA_DIR, exist_ok=True)

_env_candidates = [
    os.path.join(APP_DATA_DIR, "Vigilinx.env"),
    os.path.join(APP_DATA_DIR, ".env"),
    os.path.join(BASE_DIR, ".env"),
]
for _env_path in _env_candidates:
    if os.path.isfile(_env_path):
        load_dotenv(dotenv_path=_env_path)
        break

_log_file = os.path.join(APP_DATA_DIR, "vigilinx.log")
def _console_log_handler():
    stream = sys.stderr
    if sys.platform == "win32" and stream and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return logging.StreamHandler(stream)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        _console_log_handler(),
    ],
)
logger = logging.getLogger("vids")

DB_PATH = os.getenv('DB_PATH', os.path.join(APP_DATA_DIR, 'vigilinx.db'))
DatabaseInitializer(DB_PATH).initialize_db()

EMAIL_CONFIG = {
    'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
    'smtp_port': int(os.getenv('SMTP_PORT', 587)),
    'sender_email': os.getenv('SENDER_EMAIL'),
    'sender_password': os.getenv('SENDER_PASSWORD'),
    'admin_email': os.getenv('ADMIN_EMAIL')
}

settings = {
    "watch_dir": os.path.join(APP_DATA_DIR, "videos"),
    "upload_dir": os.path.join(APP_DATA_DIR, "uploads"),
    "output_dir": os.path.join(APP_DATA_DIR, "outputs"),
    "vlm_model": "kimi-vl",
    "alert_threshold_minutes": 60
}

for _d in (settings["watch_dir"], settings["upload_dir"], settings["output_dir"]):
    os.makedirs(_d, exist_ok=True)

from services.analytics_service import AnalyticsService

alert_service = AlertService(settings["watch_dir"], EMAIL_CONFIG, DB_PATH)
video_service = VideoService(DB_PATH, alert_service)
cctv_service = CCTVService(DB_PATH, alert_service)
subscription_service = SubscriptionService(DB_PATH)
analytics_service = AnalyticsService(DB_PATH)

# In-memory storage for async tasks
analysis_tasks = {}
watch_tasks = {}

def _watch_task(video_path):
    name = os.path.basename(video_path)
    if name not in watch_tasks:
        watch_tasks[name] = {
            "filename": name,
            "video_path": video_path,
            "status": "processing",
            "stage": "detected",
            "progress": 0,
            "result": None,
            "error": None,
            "timestamp": time.time(),
        }
    return watch_tasks[name]

def _watch_on_detected(video_path):
    alert_service.update_last_video_time()
    _watch_task(video_path)

def _watch_on_progress(video_path, stage, progress):
    task = _watch_task(video_path)
    task["stage"] = stage
    task["progress"] = progress

def _watch_on_complete(video_path, verdict):
    task = _watch_task(video_path)
    task["status"] = "completed"
    task["stage"] = "done"
    task["progress"] = 100
    task["result"] = verdict
    task["error"] = None
    task["timestamp"] = time.time()

def _watch_on_error(video_path, error):
    task = _watch_task(video_path)
    task["status"] = "failed"
    task["stage"] = "failed"
    task["error"] = error
    task["timestamp"] = time.time()

watchdog_service = WatchdogService(
    settings["watch_dir"],
    video_service,
    output_path=settings["output_dir"],
    on_detected=_watch_on_detected,
    on_progress=_watch_on_progress,
    on_complete=_watch_on_complete,
    on_error=_watch_on_error,
)

def _get_processed_video_paths() -> set:
    conn = video_service.get_connection()
    if not conn:
        return set()
    try:
        rows = conn.execute("SELECT DISTINCT video_path FROM video_verdicts").fetchall()
        return {r["video_path"] for r in rows}
    except sqlite3.Error as e:
        logger.error("Error reading processed videos: %s", e)
        return set()
    finally:
        conn.close()

def _scan_existing_videos():
    """Process video files already present in the watch dir that have never
    been analyzed (e.g. added while the app was stopped). Runs in a background
    thread; processing is serialized by the watchdog's lock."""
    try:
        if not video_service.get_prompts():
            logger.info("No detection prompts configured; skipping initial scan of %s",
                        settings["watch_dir"])
            return
        processed = _get_processed_video_paths()
        for name in sorted(os.listdir(settings["watch_dir"])):
            if not name.lower().endswith((".mp4", ".avi", ".mkv")):
                continue
            path = os.path.join(settings["watch_dir"], name)
            if path in processed or name in watch_tasks:
                continue
            logger.info("Initial scan found %s - starting analysis", path)
            watchdog_service._process_video(path)
    except Exception as e:
        logger.exception("Initial scan failed: %s", e)

def _resolve_watch_dir(path: str) -> str:
    """Expand ~, env vars and make the path absolute."""
    if not path:
        return path
    expanded = os.path.expanduser(os.path.expandvars(path.strip()))
    return os.path.abspath(expanded)

def _persist_system_setting(key: str, value: str):
    try:
        conn = video_service.get_connection()
        if not conn:
            return
        try:
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES (?, ?)",
                (key, str(value)),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error("Error persisting setting %s: %s", key, e)

def _load_persisted_watch_dir() -> Optional[str]:
    try:
        conn = video_service.get_connection()
        if not conn:
            return None
        try:
            row = conn.execute(
                "SELECT setting_value FROM system_settings WHERE setting_key = 'watch_dir'"
            ).fetchone()
            return row["setting_value"] if row else None
        finally:
            conn.close()
    except Exception as e:
        logger.error("Error loading persisted watch_dir: %s", e)
        return None

# ---- Live cameras via Frigate (optional; see deploy/frigate/README.md) ----
frigate_bridge = None


def _start_frigate_bridge():
    """Start listening to Frigate if FRIGATE_BRIDGE_ENABLED=true."""
    global frigate_bridge
    if os.getenv("FRIGATE_BRIDGE_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return
    try:
        from services.frigate_bridge import FrigateBridge, BridgeConfig
        frigate_bridge = FrigateBridge(
            BridgeConfig.from_env(output_dir=settings["output_dir"]),
            alert_service=alert_service,
            db_path=DB_PATH,
        )
        frigate_bridge.start()
    except Exception as e:
        frigate_bridge = None
        logger.error("Frigate bridge failed to start: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_init = DatabaseInitializer(DB_PATH)
    db_init.initialize_db()

    # Restore the user-selected watch directory from previous run, if any
    persisted_watch_dir = _load_persisted_watch_dir()
    if persisted_watch_dir:
        resolved = _resolve_watch_dir(persisted_watch_dir)
        if resolved and os.path.isdir(resolved) and resolved != settings["watch_dir"]:
            settings["watch_dir"] = resolved
            watchdog_service.update_directory(resolved)
            alert_service.watch_path = resolved
            logger.info("Restored persisted watch directory: %s", resolved)

    # Start systems
    watchdog_service.start()
    threading.Thread(target=_scan_existing_videos, daemon=True).start()
    alert_task = asyncio.create_task(alert_service.run_inactivity_check(settings["alert_threshold_minutes"]))
    cctv_monitoring_task = asyncio.create_task(cctv_service.run_monitoring_task())
    _start_frigate_bridge()
    yield
    # Stop systems
    if frigate_bridge is not None:
        frigate_bridge.stop()
    watchdog_service.stop()
    alert_service.stop()
    cctv_service.stop_monitoring()
    alert_task.cancel()
    cctv_monitoring_task.cancel()

app = FastAPI(title="Vigilinx API", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUBSCRIPTION_EXEMPT_PATHS = {
    "/api/subscription/status",
    "/api/subscription/activate",
}

class TrialGuardMiddleware(BaseHTTPMiddleware):
    """Trial guard disabled: unlimited access."""

    async def dispatch(self, request: Request, call_next):
        return await call_next(request)

app.add_middleware(TrialGuardMiddleware)

# ─── Authentication (JWT) ──────────────────────────────────────────────
# Wires:
#   POST   /api/auth/login          (public)
#   GET    /api/auth/me             (requires Bearer token)
#   GET/POST/PUT/DELETE /api/admin/*  (requires admin permission)
# All other /api/* routes now require a Bearer token unless listed below.
# Default admin account on first run: username=admin, password=admin
# Override defaults via env vars:
#   VIGILINX_ADMIN_USERNAME, VIGILINX_ADMIN_PASSWORD,
#   JWT_SECRET_KEY (REQUIRED in production), JWT_EXPIRY_HOURS
AUTH_EXEMPT_PATHS = {
    "/api/auth/login",
    # Subscription status / activation must remain reachable before login
    # so the license screen can render when the trial has expired and
    # users haven't authenticated yet.
    "/api/subscription/status",
    "/api/subscription/activate",
    # Allow testing email configuration without auth
    "/api/email/test",
}

auth_service = setup_auth(
    app,
    db_path=DB_PATH,
    permissions=ALL_PERMISSIONS,
    default_permissions=DEFAULT_PERMISSIONS,
    exempt_paths=AUTH_EXEMPT_PATHS,
    admin_username=os.getenv("VIGILINX_ADMIN_USERNAME", "admin"),
    admin_password=os.getenv("VIGILINX_ADMIN_PASSWORD", "admin"),
)


@app.get("/api/subscription/status")
async def get_subscription_status():
    return subscription_service.get_status()


@app.post("/api/subscription/activate")
async def activate_subscription(body: Dict = Body(...)):
    license_key = body.get("license_key", "")
    result = subscription_service.activate_license(license_key)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/cctv")
async def get_cctv_ips():
    return cctv_service.get_all_cctv_ips()

@app.post("/api/cctv")
async def add_cctv_ip(cctv: CCTVIPCreate):
    cctv_id = cctv_service.add_cctv_ip(cctv.ip_address, cctv.location, cctv.user_id)
    if not cctv_id:
        raise HTTPException(status_code=500, detail="Failed to add CCTV IP")
    return {"status": "success", "id": cctv_id}

@app.delete("/api/cctv/{cctv_id}")
async def delete_cctv_ip(cctv_id: int):
    success = cctv_service.delete_cctv_ip(cctv_id)
    if not success:
        raise HTTPException(status_code=404, detail="CCTV IP not found")
    return {"status": "success"}

@app.get("/api/status")
async def get_status():
    return {"videos": video_service.get_video_verdicts()}

@app.get("/api/system-status")
async def get_system_status():
    return {
        "watchdog_running": watchdog_service.observer.is_alive() if watchdog_service.observer else False,
        "watch_dir": watchdog_service.watch_path,
        "settings": settings
    }

@app.get("/api/watch/status")
async def get_watch_status():
    tasks = sorted(watch_tasks.values(), key=lambda t: t.get("timestamp", 0), reverse=True)
    return {
        "watch_dir": watchdog_service.watch_path,
        "watchdog_running": watchdog_service.observer.is_alive() if watchdog_service.observer else False,
        "tasks": tasks,
    }

@app.get("/api/settings/alerts")
async def get_alert_settings():
    db_init = DatabaseInitializer(DB_PATH)
    connection = db_init._get_connection()
    if not connection:
        return {"alert_recipients": "", "video_alert_template": "", "inactivity_alert_template": ""}
    
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM system_settings")
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        
        settings_dict = {row['setting_key']: row['setting_value'] for row in rows}
        return {
            "alert_recipients": settings_dict.get('alert_recipients', EMAIL_CONFIG.get('admin_email', '')),
            "video_alert_template": settings_dict.get('video_alert_template', alert_service.default_video_template),
            "inactivity_alert_template": settings_dict.get('inactivity_alert_template', alert_service.default_inactivity_template)
        }
    except Exception as e:
        logger.error(f"Error fetching alert settings: {e}")
        return {"error": str(e)}

@app.post("/api/settings/alerts")
async def update_alert_settings(new_alert_settings: Dict = Body(...)):
    db_init = DatabaseInitializer(DB_PATH)
    connection = db_init._get_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = connection.cursor()
        for key, value in new_alert_settings.items():
            cursor.execute(
                "INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES (?, ?)",
                (key, value)
            )
        connection.commit()
        cursor.close()
        connection.close()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving alert settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/email/test")
async def test_email(body: Dict = Body(...)):
    """Send a test email to verify SMTP configuration."""
    recipient = body.get("recipient", "").strip()
    if not recipient:
        # Fall back to admin_email / alert_recipients
        recipients = alert_service._get_recipients()
        if not recipients:
            raise HTTPException(
                status_code=400,
                detail="No recipient specified and no default recipients configured. "
                       "Set ADMIN_EMAIL in .env or provide a 'recipient' in the request body."
            )
        recipient = recipients[0]

    result = alert_service.send_test_email(recipient)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result

@app.post("/api/settings")
async def update_settings(new_settings: Dict = Body(...)):
    global settings
    if "watch_dir" in new_settings:
        resolved = _resolve_watch_dir(new_settings["watch_dir"])
        settings["watch_dir"] = resolved
        watchdog_service.update_directory(resolved)
        alert_service.watch_path = resolved
        watch_tasks.clear()
        _persist_system_setting("watch_dir", resolved)
    
    if "vlm_model" in new_settings:
        settings["vlm_model"] = new_settings["vlm_model"]
        
    if "alert_threshold_minutes" in new_settings:
        settings["alert_threshold_minutes"] = new_settings["alert_threshold_minutes"]
        
    return {"status": "success", "settings": settings}

@app.get("/api/detections")
async def get_detections(is_alert: Optional[bool] = None):
    return video_service.get_detections(is_alert)

@app.get("/api/prompts")
async def get_prompts():
    return video_service.get_prompts()

@app.post("/api/prompts")
async def add_prompt(prompt: PromptCreate):
    success, error_message = video_service.add_prompt(
        prompt.prompt_text,
        prompt.category,
        prompt.is_suspicious,
        prompt.display_order
    )
    if not success:
        detail = error_message or "Failed to add prompt"
        raise HTTPException(status_code=500, detail=detail)
    return {"status": "success"}

@app.delete("/api/prompts/{prompt_id}")
async def delete_prompt(prompt_id: int):
    success = video_service.delete_prompt(prompt_id)
    if not success:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"status": "success"}

@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    verdicts = video_service.get_video_verdicts()
    detections = video_service.get_detections()
    
    total_videos = len(verdicts)
    suspicious_detections = sum(1 for v in verdicts if v.get('needs_attention') or v.get('is_critical'))
    normal_frames = total_videos - suspicious_detections
    
    # Calculate average occupancy from detections
    avg_occupancy = 0
    if detections:
        occupancy_counts = [d.get('occupancy_count', 0) for d in detections]
        avg_occupancy = sum(occupancy_counts) / len(occupancy_counts) if occupancy_counts else 0
        avg_occupancy = round(avg_occupancy)
    
    return {
        "totalVideos": total_videos,
        "suspiciousDetections": suspicious_detections,
        "normalFrames": normal_frames,
        "avgOccupancy": avg_occupancy
    }

@app.get("/api/verdicts")
async def get_verdicts():
    return {"verdicts": video_service.get_video_verdicts()}

@app.post("/api/video/analyze")
async def analyze_video(
    video: UploadFile = File(...),
    suspicious_threshold: float = Form(0.3),
    analyze_full_video: bool = Form(False),
    max_analysis_duration: int = Form(300),
):
    upload_dir = settings["upload_dir"]
    os.makedirs(upload_dir, exist_ok=True)
    
    video_filename = f"upload_{uuid.uuid4().hex[:8]}_{video.filename}"
    file_save_path = os.path.join(upload_dir, video_filename)
    
    try:
        with open(file_save_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
        
        prep_path, prep_info = video_service.prepare_video_for_analysis(
            file_save_path,
            max_duration_sec=max_analysis_duration,
            analyze_full=analyze_full_video,
        )
        
        output_filename = f"analyzed_{video_filename}"
        output_path = os.path.join(settings["output_dir"], output_filename)
        
        verdict = video_service.process_video(
            video_path=prep_path,
            output_path=output_path,
            suspicious_threshold=suspicious_threshold,
            save_output=True,
            compress_output=True,
        )
        
        if prep_info.get("prep_applied") and prep_path != file_save_path:
            try:
                os.remove(prep_path)
            except OSError:
                pass
        
        verdict["video_id"] = output_filename
        verdict["original_filename"] = video_filename
        verdict["analysis_scope"] = "full" if analyze_full_video else f"first {max_analysis_duration}s"
        
        return {"verdict": verdict}
    except Exception as e:
        logger.error(f"Error in video analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/video/occupancy")
async def analyze_video_occupancy(
    video: UploadFile = File(...),
    analyze_full_video: bool = Form(False),
    max_analysis_duration: int = Form(300),
):
    upload_dir = settings["upload_dir"]
    os.makedirs(upload_dir, exist_ok=True)

    video_filename = f"occupancy_{uuid.uuid4().hex[:8]}_{video.filename}"
    file_save_path = os.path.join(upload_dir, video_filename)

    try:
        with open(file_save_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        prep_path, prep_info = video_service.prepare_video_for_analysis(
            file_save_path,
            max_duration_sec=max_analysis_duration,
            analyze_full=analyze_full_video,
        )

        occupancy_data = video_service.analyze_video_occupancy(
            video_path=prep_path,
            model_name=settings.get("vlm_model", "xclip"),
        )

        if prep_info.get("prep_applied") and prep_path != file_save_path:
            try:
                os.remove(prep_path)
            except OSError:
                pass

        occupancy_data["original_filename"] = video_filename
        occupancy_data["analysis_scope"] = "full" if analyze_full_video else f"first {max_analysis_duration}s"

        return {"occupancy": occupancy_data}
    except Exception as e:
        logger.error(f"Error in occupancy analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/video/analyze-async")
async def analyze_video_async(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    suspicious_threshold: float = Form(0.3),
    analyze_full_video: bool = Form(False),
    max_analysis_duration: int = Form(300),
):
    task_id = str(uuid.uuid4())
    analysis_tasks[task_id] = {
        "status": "uploading",
        "stage": "uploading",
        "progress": 0,
        "result": None,
        "error": None,
        "timestamp": time.time(),
    }
    
    upload_dir = settings["upload_dir"]
    os.makedirs(upload_dir, exist_ok=True)
    
    video_filename = f"upload_{uuid.uuid4().hex[:8]}_{video.filename}"
    file_save_path = os.path.join(upload_dir, video_filename)
    
    with open(file_save_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)
    
    analysis_tasks[task_id]["status"] = "processing"
    analysis_tasks[task_id]["stage"] = "preparing"

    def make_progress_callback(tid):
        def callback(stage: str, progress: int):
            analysis_tasks[tid]["stage"] = stage
            analysis_tasks[tid]["progress"] = progress
        return callback

    def run_analysis(tid, path, threshold, filename, full, max_dur):
        try:
            prep_path, prep_info = video_service.prepare_video_for_analysis(
                path, max_duration_sec=max_dur, analyze_full=full,
            )
            analysis_tasks[tid]["stage"] = "analyzing"
            analysis_tasks[tid]["progress"] = 0

            output_filename = f"analyzed_{filename}"
            output_path = os.path.join(settings["output_dir"], output_filename)
            
            verdict = video_service.process_video(
                video_path=prep_path,
                output_path=output_path,
                suspicious_threshold=threshold,
                save_output=True,
                compress_output=True,
                progress_callback=make_progress_callback(tid),
            )
            
            if prep_info.get("prep_applied") and prep_path != path:
                try:
                    os.remove(prep_path)
                except OSError:
                    pass
            
            verdict["video_id"] = output_filename
            verdict["original_filename"] = filename
            verdict["analysis_scope"] = "full" if full else f"first {max_dur}s"
            
            analysis_tasks[tid]["status"] = "completed"
            analysis_tasks[tid]["stage"] = "done"
            analysis_tasks[tid]["progress"] = 100
            analysis_tasks[tid]["result"] = verdict
        except Exception as e:
            logger.exception(f"Async analysis error for task {tid}: {e}")
            analysis_tasks[tid]["status"] = "failed"
            analysis_tasks[tid]["stage"] = "failed"
            analysis_tasks[tid]["error"] = str(e)

    background_tasks.add_task(
        run_analysis, task_id, file_save_path, suspicious_threshold,
        video_filename, analyze_full_video, max_analysis_duration,
    )
    return {"task_id": task_id}

@app.get("/api/video/status/{task_id}")
async def get_video_status(task_id: str):
    if task_id not in analysis_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task_data = analysis_tasks[task_id]
    
    if task_data["status"] == "completed" and task_data["result"]:
        return {
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "verdict": task_data["result"],
        }
    
    return {
        "status": task_data["status"],
        "stage": task_data.get("stage", "unknown"),
        "progress": task_data.get("progress", 0),
        "error": task_data.get("error"),
    }

@app.get("/api/video/download/{video_id}")
async def download_video(video_id: str):
    # This assumes video_id is the filename in outputs directory
    # or part of it. The frontend seems to expect video_id.
    # In process_video, we might need to return video_id to frontend.
    
    file_path = os.path.join(settings["output_dir"], video_id)
    if not os.path.exists(file_path):
        # Fallback: check if it's a relative path provided by the DB/Service
        file_path = video_id
        if not os.path.isabs(file_path):
            file_path = os.path.join(settings["output_dir"], os.path.basename(video_id))
            
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Video file not found")
        
    return FileResponse(file_path, media_type='video/mp4', filename=os.path.basename(file_path))


# =====================================================================
# CONTINUOUS ZERO-PROMPT MULTI-THREAT SURVEILLANCE & ON-DEMAND VLM AUDIT
# =====================================================================

@app.post("/api/surveillance/analyze-threats")
async def analyze_threats_continuous(
    video: UploadFile = File(..., description="CCTV or surveillance video clip"),
    camera_id: str = Form("default_cam"),
    sample_stride: int = Form(2),
):
    """
    Continuous 24/7 Zero-Prompt Multi-Threat Surveillance Endpoint.
    Runs fast-path neural network detections for Weapons, Fire/Smoke, Dog Attacks, and Fights.
    """
    upload_dir = settings["upload_dir"]
    os.makedirs(upload_dir, exist_ok=True)
    
    video_filename = f"surveillance_{uuid.uuid4().hex[:8]}_{video.filename}"
    file_save_path = os.path.join(upload_dir, video_filename)
    
    try:
        with open(file_save_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
            
        output_filename = f"threat_annotated_{video_filename}"
        output_path = os.path.join(settings["output_dir"], output_filename)
        
        result = video_service.analyze_video_threats_continuous(
            video_path=file_save_path,
            camera_id=camera_id,
            output_path=output_path,
            save_output=True,
            sample_stride=sample_stride
        )
        
        result["video_id"] = output_filename
        result["download_url"] = f"/api/video/download/{output_filename}"
        return result
    except Exception as e:
        logger.error(f"Error in zero-prompt threat surveillance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/surveillance/camera-profile")
async def set_camera_alert_profile(profile: Dict[str, Any] = Body(...)):
    """
    Configures active threat modules for a specific CCTV camera stream
    (e.g., Gate Cam: enable_dog=True; Server Room: enable_fire=True).
    """
    try:
        from services.threat_engine import CameraAlertProfile
        cam_id = profile.get("camera_id", "default_cam")
        prof_obj = CameraAlertProfile(
            camera_id=cam_id,
            enable_weapon=profile.get("enable_weapon", True),
            enable_fire=profile.get("enable_fire", True),
            enable_dog=profile.get("enable_dog", True),
            enable_fight=profile.get("enable_fight", True),
            enable_coffmap=profile.get("enable_coffmap", False),
            weapon_conf_threshold=float(profile.get("weapon_conf_threshold", 0.20)),
            fire_conf_threshold=float(profile.get("fire_conf_threshold", 0.20)),
            smoke_conf_threshold=float(profile.get("smoke_conf_threshold", 0.30)),
            dog_conf_threshold=float(profile.get("dog_conf_threshold", 0.20)),
            fight_conf_threshold=float(profile.get("fight_conf_threshold", 0.30)),
            save_alert_snapshots=bool(profile.get("save_alert_snapshots", True)),
            alert_cooldown_seconds=float(profile.get("alert_cooldown_seconds", 5.0)),
        )
        video_service.threat_engine.set_camera_profile(prof_obj)
        return {"success": True, "message": f"Camera profile updated for '{cam_id}'", "profile": profile}
    except Exception as e:
        logger.error(f"Error setting camera profile: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/surveillance/camera-profile/{camera_id}")
async def get_camera_alert_profile(camera_id: str):
    """Retrieves active threat modules for a specific CCTV camera stream"""
    prof = video_service.threat_engine.get_or_create_profile(camera_id)
    return {
        "camera_id": prof.camera_id,
        "enable_weapon": prof.enable_weapon,
        "enable_fire": prof.enable_fire,
        "enable_dog": prof.enable_dog,
        "enable_fight": prof.enable_fight,
        "enable_coffmap": prof.enable_coffmap,
        "weapon_conf_threshold": prof.weapon_conf_threshold,
        "fire_conf_threshold": prof.fire_conf_threshold,
        "smoke_conf_threshold": prof.smoke_conf_threshold,
        "dog_conf_threshold": prof.dog_conf_threshold,
        "fight_conf_threshold": prof.fight_conf_threshold,
        "alert_cooldown_seconds": prof.alert_cooldown_seconds
    }


@app.post("/api/audit/recheck-evidence")
async def audit_evidence_incident(
    file: Optional[UploadFile] = File(None),
    image_base64: Optional[str] = Form(None),
    prompt: str = Form("Verify if there is an actual physical weapon, violence, or fire hazard in this frame."),
    context_type: str = Form("security_audit")
):
    """
    On-Demand VLM Evidence Reasoning & Forensic Audit Endpoint (Tier 3).
    Allows operators to recheck triggered alerts or query scene evidence with natural language.
    """
    try:
        import numpy as np
        import base64
        import cv2

        img = None
        if file is not None:
            contents = await file.read()
            nparr = np.frombuffer(contents, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        elif image_base64:
            clean_b64 = image_base64.split(",")[-1]
            nparr = np.frombuffer(base64.b64decode(clean_b64), np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Must provide an image file or base64 image payload")

        audit_res = video_service.audit_evidence(img, prompt=prompt, context_type=context_type)
        return audit_res
    except Exception as e:
        logger.error(f"Error in on-demand VLM audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/frigate/status")
async def frigate_status():
    """Is the live-camera bridge running, and what has it seen?"""
    if frigate_bridge is None:
        return {"enabled": False,
                "hint": "Set FRIGATE_BRIDGE_ENABLED=true and restart to use live cameras via Frigate."}
    from services.ollama_verifier import get_ollama_verifier
    v = get_ollama_verifier()
    return {"enabled": True, **frigate_bridge.stats,
            "verifier": {"model": v.model, "url": v.base_url, "available": v.is_available()},
            "telegram_enabled": frigate_bridge.notifier.enabled}


@app.post("/api/coffmap/space-analytics")
async def analyze_space_logistics(
    video: UploadFile = File(...),
    sample_stride: int = Form(2),
    generate_heatmap: bool = Form(True)
):
    """
    CoffMap Space, Customer Dwell & Vehicle Logistics Analytics Endpoint.
    """
    upload_dir = settings["upload_dir"]
    os.makedirs(upload_dir, exist_ok=True)
    video_filename = f"coffmap_{uuid.uuid4().hex[:8]}_{video.filename}"
    file_save_path = os.path.join(upload_dir, video_filename)
    
    try:
        with open(file_save_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
            
        heatmap_out = os.path.join(settings["output_dir"], f"heatmap_{video_filename}.jpg") if generate_heatmap else None
        
        report = video_service.threat_engine.coffmap_engine.analyze_clip(
            video_path=file_save_path,
            sample_stride=sample_stride,
            generate_heatmap_path=heatmap_out
        )
        
        if heatmap_out and os.path.exists(heatmap_out):
            report["heatmap_url"] = f"/api/video/download/{os.path.basename(heatmap_out)}"
            
        return report
    except Exception as e:
        logger.error(f"Error in CoffMap space analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------
# ANALYTICS & INTELLIGENCE DASHBOARD ENDPOINTS
# -------------------------------------------------------------
@app.get("/api/analytics/kpis")
async def get_analytics_kpis():
    """Returns top-level security and surveillance KPIs."""
    return analytics_service.get_overview_kpis()


@app.get("/api/analytics/threat-trends")
async def get_threat_trends(days: int = 7):
    """Returns daily time-series incident trends across the specified window."""
    return analytics_service.get_threat_trends(days=days)


@app.get("/api/analytics/threat-breakdown")
async def get_threat_breakdown():
    """Returns categorical breakdown of all detected threat types."""
    return analytics_service.get_threat_breakdown()


@app.get("/api/analytics/occupancy-hourly")
async def get_occupancy_hourly():
    """Returns average and peak occupancy counts grouped by hour of day (0-23)."""
    return analytics_service.get_occupancy_hourly()


@app.get("/api/analytics/export-csv")
async def export_analytics_csv():
    """Generates and downloads a CSV compliance & surveillance incident report."""
    from fastapi.responses import Response
    csv_data = analytics_service.export_csv_report()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vigilinx_surveillance_report.csv"}
    )


@app.post("/api/video/summarize/{video_id}")
async def summarize_video_endpoint(video_id: int):
    """Generate or retrieve on-demand AI narrative summary for a specific processed video."""
    conn = video_service.get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        row = conn.execute("SELECT * FROM video_verdicts WHERE id = ?", (video_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Verdict {video_id} not found")
        
        video_name = row["video_path"]
        candidate_paths = [
            os.path.join(settings["watch_dir"], video_name),
            os.path.join(settings["upload_dir"], video_name),
            os.path.join(settings["output_dir"], video_name),
        ]
        found_path = None
        for cp in candidate_paths:
            if os.path.exists(cp):
                found_path = cp
                break
        
        threat_data = {
            "needs_attention": bool(row["needs_attention"]),
            "risk_level": row["risk_level"],
            "recommendation": row["recommendation"],
            "duration": 0,
        }
        
        if found_path:
            summary = video_service.summarize_video(found_path, threat_summary=threat_data)
        else:
            summary = video_service.evidence_auditor.summarize_video_keyframes([], [], threat_summary=threat_data)

        sum_text = summary.get("narrative_summary") if isinstance(summary, dict) else str(summary)
        conn.execute("UPDATE video_verdicts SET ai_summary = ? WHERE id = ?", (sum_text, video_id))
        conn.commit()
        return summary
    finally:
        conn.close()



from fastapi.staticfiles import StaticFiles
import sys

def _get_frontend_build_path() -> str:
    """Resolve frontend build dir: works in dev, installed wheel, and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        cand = os.path.join(exe_dir, "frontend", "build")
        if os.path.isdir(cand):
            return cand
        if hasattr(sys, '_MEIPASS'):
            cand2 = os.path.join(sys._MEIPASS, "frontend", "build")
            if os.path.isdir(cand2):
                return cand2
    candidates = [
        os.path.join(BASE_DIR, "frontend", "build"),           # wheel install (frontend next to main.py)
        os.path.join(BASE_DIR, "..", "frontend", "build"),      # dev layout (ids/backend/../frontend/build)
    ]
    for c in candidates:
        p = os.path.abspath(c)
        if os.path.isdir(p):
            return p
    return ""

build_path = _get_frontend_build_path()
if build_path and os.path.exists(build_path):
    app.mount("/", StaticFiles(directory=build_path, html=True), name="static")

def main():
    import uvicorn

    is_frozen = getattr(sys, 'frozen', False)
    log_config = uvicorn.config.LOGGING_CONFIG
    if is_frozen:
        log_config["handlers"]["default"] = {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": _log_file,
        }
        log_config["handlers"]["access"] = {
            "class": "logging.FileHandler",
            "formatter": "access",
            "filename": _log_file,
        }

    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=log_config)

if __name__ == "__main__":
    main()
