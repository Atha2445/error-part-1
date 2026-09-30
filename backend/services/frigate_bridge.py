"""
services/frigate_bridge.py — Turns Frigate camera events into verified Vigilinx alerts.

How it works
------------
1. Frigate watches every camera and publishes each tracked object (person,
   animals, knife) on MQTT topic ``frigate/events``.
2. The bridge keeps a live list of objects per camera and starts a check when
   one of these is on camera:
     - PERSON: any person
     - ANIMAL: any animal (dog, cat, cow, horse, sheep, ...)
     - WEAPON: a knife
   Checks are rate limited per camera, so a busy lobby doesn't flood the GPU.
3. For each check it downloads the recording of that moment from Frigate
   (a few seconds before and after) and runs Vigilinx's own detectors on it
   (pose-based fight detector, weapon model, dog-contact logic). Ollama then
   looks at a short frame sequence and answers yes or no: about what the
   detectors found, or, if they found nothing, whether anything dangerous is
   happening at all (BRIDGE_VERIFY_ALL=true, the default), so an incident the
   detectors miss is still caught.
4. Confirmed incidents are saved (clip + snapshot + DB row) and sent to
   Telegram and email.

If Ollama is down, a detector hit is still alerted but marked UNVERIFIED, so
the system never goes silent because the verifier is broken (the bug that made
the old pipeline detect nothing).

Enable with FRIGATE_BRIDGE_ENABLED=true (see backend/.env.example).
"""
import json
import logging
import os
import queue
import sqlite3
import tempfile
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

import cv2
import httpx
import numpy as np

logger = logging.getLogger("vids.frigate_bridge")

# Which Vigilinx threat types count for each trigger, in priority order.
KIND_TO_THREATS = {
    "WEAPON": ["WEAPON"],
    "ANIMAL": ["ANIMAL_ASSAULT", "DOG_ATTACK"],
    "PERSON": ["FIGHT_ASSAULT", "WEAPON"],
}
# Frigate (COCO) labels that start an ANIMAL check
ANIMAL_LABELS = {"dog", "cat", "cow", "horse", "sheep", "bird", "bear", "elephant", "zebra", "giraffe"}
# What Ollama is asked, and what a "yes" is reported as, when the detectors found nothing
AI_ONLY_CHECK = {
    "PERSON": ("security_audit", "SECURITY_INCIDENT"),
    "ANIMAL": ("animal_assault_verify", "ANIMAL_ASSAULT"),
    "WEAPON": ("weapon_verify", "WEAPON"),
}
# FIGHT_NEAR_FIRE: fight-like motion right next to an established fire (often
# firefighters/evacuees). Kept as evidence, but checked only if nothing else
# was found, so it never takes the check away from the fire itself.
THREAT_PRIORITY = ["WEAPON", "ANIMAL_ASSAULT", "DOG_ATTACK", "FIGHT_ASSAULT", "FIRE_SMOKE", "FIGHT_NEAR_FIRE"]
THREAT_CONTEXT = {
    "WEAPON": "weapon_verify",
    "ANIMAL_ASSAULT": "animal_assault_verify",
    "DOG_ATTACK": "animal_assault_verify",
    "FIGHT_ASSAULT": "fight_verify",
    "FIRE_SMOKE": "fire_verify",
    "FIGHT_NEAR_FIRE": "fight_verify",
}
THREAT_TITLE = {
    "WEAPON": "Weapon seen",
    "ANIMAL_ASSAULT": "Dog attacking a person",
    "DOG_ATTACK": "Aggressive dog near a person",
    "FIGHT_ASSAULT": "Fight in progress",
    "FIRE_SMOKE": "Fire or smoke",
    "FIGHT_NEAR_FIRE": "Possible fight near a fire",
    "SECURITY_INCIDENT": "Possible incident spotted by AI",
}
# (final_incident, title, icon) as the dashboard's incident cards expect them
DASHBOARD_INCIDENT = {
    "WEAPON": ("WEAPON", "Weapon Detected", "🗡️"),
    "ANIMAL_ASSAULT": ("ANIMAL_ASSAULT", "Animal Assault (Dog Attack)", "🐕"),
    "DOG_ATTACK": ("ANIMAL_ASSAULT", "Animal Assault (Dog Attack)", "🐕"),
    "FIGHT_ASSAULT": ("FIGHT_ASSAULT", "Physical Altercation / Fight", "🥊"),
    "FIRE_SMOKE": ("FIRE_SMOKE", "Fire & Smoke Hazard", "🔥"),
    "FIGHT_NEAR_FIRE": ("FIGHT_ASSAULT", "Physical Altercation / Fight", "🥊"),
    "SECURITY_INCIDENT": ("SECURITY_INCIDENT", "Security Incident (spotted by AI)", "🚨"),
}


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class BridgeConfig:
    frigate_url: str = "http://127.0.0.1:5000"
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    topic_prefix: str = "frigate"
    pre_seconds: float = 6.0          # recording fetched before the trigger
    post_seconds: float = 4.0         # and after it
    recording_delay: float = 15.0     # wait for Frigate to finish writing segments
    analysis_fps: float = 5.0         # frames per second run through the detectors
    check_cooldown: float = 30.0      # min seconds between checks of one kind per camera
    alert_cooldown: float = 120.0     # min seconds between alerts of one kind per camera
    min_confidence: float = 0.5       # Ollama confidence needed to confirm
    alert_when_unverified: bool = True
    min_people: int = 1               # people on camera needed to start a PERSON check
    verify_all: bool = True           # ask Ollama even when the detectors found nothing
    verify_frames: int = 6            # frames sent to Ollama per check (fewer = faster on CPU)
    output_dir: str = field(default_factory=lambda: tempfile.gettempdir())

    @classmethod
    def from_env(cls, output_dir: Optional[str] = None) -> "BridgeConfig":
        c = cls()
        c.frigate_url = os.getenv("FRIGATE_URL", c.frigate_url).rstrip("/")
        c.mqtt_host = os.getenv("MQTT_HOST", c.mqtt_host)
        c.mqtt_port = int(os.getenv("MQTT_PORT", c.mqtt_port))
        c.topic_prefix = os.getenv("FRIGATE_TOPIC_PREFIX", c.topic_prefix)
        c.check_cooldown = float(os.getenv("BRIDGE_CHECK_COOLDOWN", c.check_cooldown))
        c.alert_cooldown = float(os.getenv("BRIDGE_ALERT_COOLDOWN", c.alert_cooldown))
        c.min_confidence = float(os.getenv("BRIDGE_MIN_CONFIDENCE", c.min_confidence))
        c.alert_when_unverified = _env_bool("BRIDGE_ALERT_WHEN_UNVERIFIED", c.alert_when_unverified)
        c.verify_frames = max(1, int(os.getenv("BRIDGE_VERIFY_FRAMES", c.verify_frames)))
        c.min_people = max(1, int(os.getenv("BRIDGE_MIN_PEOPLE", c.min_people)))
        c.verify_all = _env_bool("BRIDGE_VERIFY_ALL", c.verify_all)
        if output_dir:
            c.output_dir = output_dir
        return c


# ---------------------------------------------------------------------------
#  Live object list per camera, built from frigate/events
# ---------------------------------------------------------------------------

class ActiveObjects:
    """Tracks which objects Frigate currently sees on each camera."""

    STALE_AFTER = 60.0  # drop objects whose 'end' message was missed

    def __init__(self):
        self._by_camera: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self._lock = threading.Lock()

    def update(self, payload: Dict[str, Any]) -> Optional[str]:
        after = payload.get("after") or {}
        obj_id, camera = after.get("id"), after.get("camera")
        if not obj_id or not camera:
            return None
        with self._lock:
            objs = self._by_camera[camera]
            if payload.get("type") == "end" or after.get("end_time") or after.get("false_positive"):
                objs.pop(obj_id, None)
            else:
                objs[obj_id] = {
                    "id": obj_id,
                    "label": after.get("label"),
                    "score": after.get("top_score") or after.get("score") or 0.0,
                    "stationary": bool(after.get("stationary")),
                    "zones": list(after.get("current_zones") or []),
                    "seen": time.time(),
                }
            now = time.time()
            for oid in [k for k, v in objs.items() if now - v["seen"] > self.STALE_AFTER]:
                objs.pop(oid, None)
        return camera

    def on_camera(self, camera: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._by_camera.get(camera, {}).values())


def triggers_for(objects: List[Dict[str, Any]], min_people: int = 1) -> Set[str]:
    """Which checks the current scene calls for."""
    labels = [o["label"] for o in objects]
    kinds: Set[str] = set()
    if "knife" in labels:
        kinds.add("WEAPON")
    if any(label in ANIMAL_LABELS for label in labels):
        kinds.add("ANIMAL")
    if labels.count("person") >= min_people:
        kinds.add("PERSON")
    return kinds


@dataclass
class Job:
    camera: str
    kind: str
    trigger_time: float
    frigate_ids: List[str]
    knife_score: float = 0.0
    dog_seen: bool = False


# ---------------------------------------------------------------------------
#  The bridge
# ---------------------------------------------------------------------------

class FrigateBridge:
    def __init__(self, config: BridgeConfig, *,
                 threat_engine=None,
                 verifier=None,
                 notifier=None,
                 alert_service=None,
                 db_path: Optional[str] = None,
                 clip_fetcher: Optional[Callable[[str, float, float], Optional[str]]] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.time):
        self.cfg = config
        self._threat_engine = threat_engine
        self._verifier = verifier
        self._notifier = notifier
        self.alert_service = alert_service
        self.db_path = db_path
        self._fetch_clip = clip_fetcher or self._fetch_clip_http
        self._sleep = sleep
        self._clock = clock

        self.objects = ActiveObjects()
        self._jobs: "queue.Queue[Optional[Job]]" = queue.Queue(maxsize=100)
        self._last_check: Dict[tuple, float] = {}
        self._last_alert: Dict[tuple, float] = {}
        self._pending: Set[tuple] = set()
        self._lock = threading.Lock()
        self._worker: Optional[threading.Thread] = None
        self._mqtt = None
        self._running = False
        self.stats = {"events": 0, "checks_queued": 0, "checks_run": 0,
                      "detector_hits": 0, "confirmed": 0, "rejected": 0,
                      "unverified_alerts": 0, "clip_failures": 0,
                      "ai_only_checks": 0, "ai_only_confirmed": 0,
                      "mqtt_connected": False, "last_incident": None}

    # ---- lazily created heavy parts --------------------------------------
    @property
    def threat_engine(self):
        if self._threat_engine is None:
            from services.threat_engine import ThreatEngine
            self._threat_engine = ThreatEngine(enable_vlm=False)
        return self._threat_engine

    @property
    def verifier(self):
        if self._verifier is None:
            from services.ollama_verifier import get_ollama_verifier
            self._verifier = get_ollama_verifier()
        return self._verifier

    @property
    def notifier(self):
        if self._notifier is None:
            from services.telegram_notifier import TelegramNotifier
            self._notifier = TelegramNotifier()
        return self._notifier

    # ---- lifecycle ----------------------------------------------------------
    def start(self):
        import paho.mqtt.client as mqtt
        self._running = True
        self._worker = threading.Thread(target=self._work_loop, name="frigate-bridge", daemon=True)
        self._worker.start()

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="vigilinx-bridge")
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.connect_async(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=60)
        client.loop_start()
        self._mqtt = client
        logger.info("Frigate bridge started (MQTT %s:%s, Frigate %s)",
                    self.cfg.mqtt_host, self.cfg.mqtt_port, self.cfg.frigate_url)

    def stop(self):
        self._running = False
        if self._mqtt is not None:
            try:
                self._mqtt.loop_stop()
                self._mqtt.disconnect()
            except Exception:
                pass
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        ok = not getattr(reason_code, "is_failure", False)
        self.stats["mqtt_connected"] = ok
        if ok:
            client.subscribe(f"{self.cfg.topic_prefix}/events")
            logger.info("Connected to MQTT; listening on %s/events", self.cfg.topic_prefix)
        else:
            logger.error("MQTT connection refused: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.stats["mqtt_connected"] = False
        logger.warning("MQTT disconnected (%s); will retry", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            self.handle_event(json.loads(msg.payload))
        except Exception as e:
            logger.error("Bad Frigate event: %s", e)

    # ---- event handling ----------------------------------------------------
    def handle_event(self, payload: Dict[str, Any]) -> List[Job]:
        """Update the object list and queue any checks the scene calls for."""
        self.stats["events"] += 1
        camera = self.objects.update(payload)
        if not camera:
            return []
        objs = self.objects.on_camera(camera)
        queued = []
        now = self._clock()
        for kind in triggers_for(objs, self.cfg.min_people):
            key = (camera, kind)
            with self._lock:
                if key in self._pending:
                    continue
                if now - self._last_check.get(key, 0) < self.cfg.check_cooldown:
                    continue
                if now - self._last_alert.get(key, 0) < self.cfg.alert_cooldown:
                    continue
                self._last_check[key] = now
                self._pending.add(key)
            knife = max((o["score"] for o in objs if o["label"] == "knife"), default=0.0)
            job = Job(camera, kind, now, [o["id"] for o in objs], knife_score=knife,
                      dog_seen=any(o["label"] in ANIMAL_LABELS for o in objs))
            try:
                self._jobs.put_nowait(job)
                self.stats["checks_queued"] += 1
                queued.append(job)
            except queue.Full:
                logger.warning("Check queue full; skipping %s on %s", kind, camera)
                with self._lock:
                    self._pending.discard(key)
        return queued

    def _ready_at(self, job: Job) -> float:
        return job.trigger_time + self.cfg.post_seconds + self.cfg.recording_delay

    def _work_loop(self):
        """Run checks in the order their recordings become available.

        Jobs wait in a heap instead of the worker sleeping on each one, so a
        check that is still waiting for its recording never delays a check on
        another camera whose recording is already there.
        """
        import heapq
        waiting: List[tuple] = []
        seq = 0
        while self._running:
            timeout = None
            if waiting:
                timeout = max(0.0, waiting[0][0] - self._clock())
            try:
                job = self._jobs.get(timeout=timeout)
                if job is None:
                    break
                heapq.heappush(waiting, (self._ready_at(job), seq, job))
                seq += 1
                continue
            except queue.Empty:
                pass
            if not waiting or waiting[0][0] > self._clock():
                continue
            _, _, job = heapq.heappop(waiting)
            try:
                self.process_job(job, wait=False)
            except Exception as e:
                logger.exception("Check %s on %s failed: %s", job.kind, job.camera, e)
            finally:
                with self._lock:
                    self._pending.discard((job.camera, job.kind))

    # ---- one check ------------------------------------------------------------
    def process_job(self, job: Job, wait: bool = True) -> Dict[str, Any]:
        self.stats["checks_run"] += 1
        start = job.trigger_time - self.cfg.pre_seconds
        end = job.trigger_time + self.cfg.post_seconds
        delay = self._ready_at(job) - self._clock()
        if wait and delay > 0:
            self._sleep(delay)

        clip = None
        for attempt in range(3):
            clip = self._fetch_clip(job.camera, start, end)
            if clip:
                break
            if attempt < 2:
                self._sleep(5)
        if not clip:
            self.stats["clip_failures"] += 1
            logger.warning("No recording for %s %.0f-%.0f; is recording enabled?", job.camera, start, end)
            return {"status": "no_clip"}

        try:
            frames, fps = self._read_frames(clip)
            if not frames:
                return {"status": "empty_clip"}
            hits = self._detect(frames, job)
            threat = self._pick_threat(hits, job)
            if threat is None:
                if self.cfg.verify_all and job.kind in AI_ONLY_CHECK:
                    return self._ai_only_check(job, frames, clip)
                logger.info("[%s] %s check: detectors found nothing", job.camera, job.kind)
                return {"status": "clear"}

            self.stats["detector_hits"] += 1
            seq, best = self._verification_frames(hits.get(threat, []), frames, self.cfg.verify_frames)
            clip_seconds = (len(frames) / self.cfg.analysis_fps) if frames else None
            verdict = self.verifier.verify([f for _, f in seq], THREAT_CONTEXT.get(threat, "security_audit"),
                                           clip_seconds=clip_seconds)
            return self._decide(job, threat, verdict, best, clip)
        finally:
            try:
                os.remove(clip)
            except OSError:
                pass

    def _ai_only_check(self, job: Job, frames: List[np.ndarray], clip: str) -> Dict[str, Any]:
        """Detectors found nothing: let Ollama look at frames spread over the whole clip."""
        context, threat = AI_ONLY_CHECK[job.kind]
        n = min(self.cfg.verify_frames, len(frames))
        idxs = sorted({int((k + 0.5) * len(frames) / n) for k in range(n)})
        verdict = self.verifier.verify([frames[i] for i in idxs], context,
                                       clip_seconds=len(frames) / self.cfg.analysis_fps)
        self.stats["ai_only_checks"] += 1
        if not verdict.get("success"):
            logger.info("[%s] %s check: detectors found nothing; verifier unavailable", job.camera, job.kind)
            return {"status": "clear", "verdict": verdict}
        if not (verdict.get("verified_threat") and verdict.get("confidence", 0) >= self.cfg.min_confidence):
            logger.info("[%s] %s check: detectors and %s found nothing: %s", job.camera, job.kind,
                        verdict.get("model_used"), verdict.get("reasoning", "")[:160])
            return {"status": "clear", "verdict": verdict}
        self.stats["confirmed"] += 1
        self.stats["ai_only_confirmed"] += 1
        self._alert(job, threat, "confirmed", verdict, frames[idxs[len(idxs) // 2]], clip)
        return {"status": "confirmed", "threat": threat, "verdict": verdict}

    def _decide(self, job: Job, threat: str, verdict: Dict[str, Any], best_frame, clip: str) -> Dict[str, Any]:
        if verdict.get("success"):
            confirmed = verdict.get("verified_threat") and verdict.get("confidence", 0) >= self.cfg.min_confidence
            if not confirmed:
                self.stats["rejected"] += 1
                logger.info("[%s] %s rejected by %s: %s", job.camera, threat,
                            verdict.get("model_used"), verdict.get("reasoning", "")[:160])
                self._log_db(job.camera, threat, verdict.get("confidence", 0.0), is_alert=False,
                             note="rejected by verifier")
                return {"status": "rejected", "threat": threat, "verdict": verdict}
            status = "confirmed"
            self.stats["confirmed"] += 1
        else:
            if not self.cfg.alert_when_unverified:
                logger.warning("[%s] %s found but verifier unavailable; not alerting (BRIDGE_ALERT_WHEN_UNVERIFIED=false)",
                               job.camera, threat)
                return {"status": "unverified_dropped", "threat": threat}
            status = "unverified"
            self.stats["unverified_alerts"] += 1

        self._alert(job, threat, status, verdict, best_frame, clip)
        return {"status": status, "threat": threat, "verdict": verdict}

    # ---- detection helpers ------------------------------------------------------
    def _fetch_clip_http(self, camera: str, start: float, end: float) -> Optional[str]:
        url = f"{self.cfg.frigate_url}/api/{camera}/start/{start:.1f}/end/{end:.1f}/clip.mp4"
        try:
            with httpx.stream("GET", url, timeout=60.0) as r:
                if r.status_code != 200:
                    logger.debug("Clip not ready (%s): %s", r.status_code, url)
                    return None
                fd, path = tempfile.mkstemp(suffix=".mp4", prefix=f"frigate_{camera}_")
                with os.fdopen(fd, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            if os.path.getsize(path) < 1024:
                os.remove(path)
                return None
            return path
        except Exception as e:
            logger.warning("Clip download failed for %s: %s", camera, e)
            return None

    def _read_frames(self, clip_path: str) -> tuple:
        cap = cv2.VideoCapture(clip_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        stride = max(1, int(round(fps / self.cfg.analysis_fps)))
        frames, i = [], 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % stride == 0:
                frames.append(frame)
            i += 1
        cap.release()
        return frames, fps

    def _detect(self, frames: List[np.ndarray], job: Job) -> Dict[str, List[tuple]]:
        """Run Vigilinx's detectors over the clip. Returns {threat_type: [(idx, conf, annotated)]}."""
        cam_key = f"frigate:{job.camera}"
        engine = self.threat_engine
        engine.enable_vlm = False
        engine.reset_stream_state(cam_key)
        hits: Dict[str, List[tuple]] = defaultdict(list)
        fire_tracks: List[Any] = []  # track id of each FIRE_SMOKE hit, same order
        for idx, frame in enumerate(frames):
            res = engine.scan_frame(frame, camera_id=cam_key, annotate=True,
                                    timestamp_sec=idx / self.cfg.analysis_fps)
            annotated = res.get("annotated_frame")
            for t in res.get("threats", []):
                kind = t["type"]
                if kind == "FIGHT_ASSAULT" and t.get("near_fire"):
                    kind = "FIGHT_NEAR_FIRE"
                hits[kind].append((idx, float(t.get("confidence", 0.0)), annotated))
                if kind == "FIRE_SMOKE":
                    fire_tracks.append(t.get("track_id"))
            if res.get("animal_assault_detected") and not any(t["type"] in ("ANIMAL_ASSAULT", "DOG_ATTACK")
                                                              for t in res.get("threats", [])):
                hits["ANIMAL_ASSAULT"].append((idx, 0.5, annotated))
        # Fire/smoke boxes proven static later in the clip (lamps, signs, haze)
        get_static = getattr(engine, "get_static_fire_track_ids", None)
        static_ids = get_static(cam_key) if get_static else set()
        if static_ids and "FIRE_SMOKE" in hits:
            kept = [h for h, tid in zip(hits["FIRE_SMOKE"], fire_tracks) if tid not in static_ids]
            if kept:
                hits["FIRE_SMOKE"] = kept
            else:
                del hits["FIRE_SMOKE"]
        return hits

    def _pick_threat(self, hits: Dict[str, List[tuple]], job: Job) -> Optional[str]:
        # Frigate's own knife detection counts as a weapon hit even if the
        # Vigilinx weapon model missed it (knives are small on CCTV).
        if job.kind == "WEAPON" and "WEAPON" not in hits and job.knife_score > 0:
            hits["WEAPON"] = []
        # The engine turns any low-confidence "animal" touching a person into an
        # animal assault and then drops its fight hits; in a scuffle, tangled
        # bodies are often mistaken for a dog. Frigate's own dog tracking decides
        # whether there is an animal: if it saw none, those hits are the fight.
        # When Frigate did see an animal, its own ANIMAL check handles those hits.
        if job.kind == "PERSON":
            animal = hits.pop("ANIMAL_ASSAULT", []) + hits.pop("DOG_ATTACK", [])
            if animal and not job.dog_seen and "FIGHT_ASSAULT" not in hits:
                hits["FIGHT_ASSAULT"] = sorted(animal, key=lambda h: h[0])
        present = [t for t in THREAT_PRIORITY if t in hits]
        if not present:
            return None
        # Prefer what the trigger was looking for, then priority order.
        wanted = [t for t in KIND_TO_THREATS.get(job.kind, []) if t in present]
        return (wanted or present)[0]

    @staticmethod
    def _verification_frames(hit_list: List[tuple], frames: List[np.ndarray], n: int = 6):
        """Up to n raw frames spread over ~2s either side of the strongest hit."""
        if hit_list:
            peak_idx, _, annotated = max(hit_list, key=lambda h: h[1])
        else:
            peak_idx, annotated = len(frames) // 2, None
        lo, hi = max(0, peak_idx - 10), min(len(frames) - 1, peak_idx + 10)
        if n == 1:
            idxs = [peak_idx]
        else:
            idxs = sorted({int(round(lo + k * (hi - lo) / (n - 1))) for k in range(n)})
        best = annotated if annotated is not None else frames[peak_idx]
        return [(i, frames[i]) for i in idxs], best

    # ---- output ------------------------------------------------------------------
    def _alert(self, job: Job, threat: str, status: str, verdict: Dict[str, Any], best_frame, clip: str):
        now = self._clock()
        with self._lock:
            self._last_alert[(job.camera, job.kind)] = now
            # A person, an animal and a knife in one scene start separate checks
            # that can find the same incident: alert it once.
            if now - self._last_alert.get((job.camera, "threat:" + threat), -1e18) < self.cfg.alert_cooldown:
                logger.info("[%s] %s already alerted in the last %.0fs; not repeating",
                            job.camera, threat, self.cfg.alert_cooldown)
                return
            self._last_alert[(job.camera, "threat:" + threat)] = now
        ts = datetime.fromtimestamp(job.trigger_time).strftime("%d %b %Y, %I:%M:%S %p")
        title = THREAT_TITLE.get(threat, threat)
        conf = verdict.get("confidence", 0.0)
        if status == "confirmed":
            line2 = f"Confirmed by AI ({conf:.0%}): {verdict.get('reasoning', '')}"
        else:
            line2 = "Detected by camera AI, NOT double-checked (verifier offline). Please check the footage."
        caption = f"🚨 {title}\nCamera: {job.camera}\nTime: {ts}\n{line2}"

        # Keep the evidence
        os.makedirs(self.cfg.output_dir, exist_ok=True)
        stem = f"incident_{job.camera}_{int(job.trigger_time)}_{threat.lower()}"
        snap_path = os.path.join(self.cfg.output_dir, stem + ".jpg")
        clip_keep = os.path.join(self.cfg.output_dir, stem + ".mp4")
        ok, buf = cv2.imencode(".jpg", best_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        jpeg = buf.tobytes() if ok else None
        if jpeg:
            with open(snap_path, "wb") as f:
                f.write(jpeg)
        try:
            import shutil
            shutil.copyfile(clip, clip_keep)
        except OSError:
            clip_keep = None

        self._log_db(job.camera, threat, conf, is_alert=True, note=status, path=clip_keep)
        self._log_verdict(job.camera, threat, status, verdict, ts, clip_keep)
        self.stats["last_incident"] = {"camera": job.camera, "threat": threat, "status": status,
                                       "time": ts, "reasoning": verdict.get("reasoning", "")}
        logger.warning("[%s] ALERT %s (%s)", job.camera, threat, status)

        sent = 0
        try:
            sent = self.notifier.send_alert(caption, photo_jpeg=jpeg, clip_path=clip_keep)
        except Exception as e:
            logger.error("Telegram alert failed: %s", e)
        if self.alert_service is not None:
            try:
                self.alert_service.send_incident_alert(f"SECURITY ALERT: {title} on {job.camera}", caption, jpeg)
            except Exception as e:
                logger.error("Email alert failed: %s", e)
        if not sent and self.alert_service is None:
            logger.warning("Alert raised but no Telegram chat or email is configured")

    def _log_db(self, camera: str, threat: str, conf: float, is_alert: bool, note: str = "",
                path: Optional[str] = None):
        if not self.db_path:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO detections (video_path, frame_number, detected_action, confidence, "
                "is_alert, occupancy_count, timestamp) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                (path or f"frigate://{camera}", 0, f"LIVE {threat} [{note}] on {camera}",
                 float(conf), bool(is_alert), 0))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Could not log incident: %s", e)

    def _log_verdict(self, camera: str, threat: str, status: str, verdict: Dict[str, Any], ts: str,
                     path: Optional[str]):
        """Add the alert to video_verdicts, which the dashboard's counts and incident cards read."""
        if not self.db_path:
            return
        final, title, icon = DASHBOARD_INCIDENT.get(threat, (threat, THREAT_TITLE.get(threat, threat), "🚨"))
        confirmed = status == "confirmed"
        conf = float(verdict.get("confidence", 0.0)) if confirmed else 0.0
        what = f"Live camera {camera} at {ts}: {THREAT_TITLE.get(threat, threat).lower()}. "
        if confirmed:
            what += f"Confirmed by {verdict.get('model_used') or 'the AI verifier'}: {verdict.get('reasoning', '')}".strip()
        else:
            what += "Flagged by the camera detectors; the AI verifier was offline, so this was not double-checked."
        risk = "[CRITICAL] Immediate Action Required"
        recommendation = "Check the camera and the saved clip now." if confirmed else \
            "Review the saved clip to confirm before acting."
        details = {
            "narrative_summary": what,
            "human_summary": {"what_happened": what, "final_incident": final, "title": title,
                              "incident_icon": icon, "risk_level": risk, "recommendation": recommendation,
                              "time_of_incident": ts, "vlm_verified": confirmed, "vlm_confidence": conf},
            "final_incident": final, "incident_title": title, "incident_icon": icon,
            "vlm_verified": confirmed, "vlm_confidence": conf,
        }
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("ALTER TABLE video_verdicts ADD COLUMN details_json TEXT")
            except sqlite3.OperationalError:
                pass
            conn.execute(
                "INSERT INTO video_verdicts (video_path, total_analyzed, suspicious_frames, normal_frames, "
                "suspicious_percentage, risk_level, needs_attention, recommendation, ai_summary, details_json, "
                "timestamp) VALUES (?, 1, 1, 0, 100.0, ?, 1, ?, ?, ?, datetime('now'))",
                (os.path.basename(path) if path else f"frigate://{camera}", risk, recommendation, what,
                 json.dumps(details)))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Could not save incident verdict: %s", e)
