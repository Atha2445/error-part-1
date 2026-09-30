"""
services/threat_engine.py — High-Performance Zero-Prompt Multi-Threat Engine.

Provides continuous, real-time threat detection across:
1. Weapons (Guns, Knives, Grenades)
2. Fire & Smoke Early Warning
3. Dog Attacks & Aggressive Stray Animals
4. Fights, Physical Assaults & Violent Stances (Proximity + Motion Gated)

Two-stage pipeline:
  Stage 1 (Fast): YOLO-based neural network detectors (real-time, every frame)
  Stage 2 (Deep): Kimi-VL forensic reasoning (async, on flagged frames only)
"""
import logging
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import cv2
import numpy as np

logger = logging.getLogger("vids.threat_engine")

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None
    logger.warning("ultralytics not installed. Please install ultralytics.")

from alerts.fire.detector import FireSmokeDetector
from alerts.fire.tracker import FireSceneTracker
from alerts.dog.detector import DogAttackDetector
from alerts.fight.detector import FightDetector


def _resolve_models_dir() -> Path:
    """Locate the models/ directory.

    Works in three scenarios:
      1. PyInstaller frozen bundle  → next to executable or sys._MEIPASS / models
      2. Normal dev run             → <backend_dir> / models
      3. Fallback                   → current working directory / models
    """
    if getattr(sys, "frozen", False):
        exe_models = Path(sys.executable).parent / "models"
        if exe_models.exists():
            return exe_models
        if hasattr(sys, "_MEIPASS"):
            candidate = Path(sys._MEIPASS) / "models"
            if candidate.exists():
                return candidate

    backend_dir = Path(__file__).resolve().parent.parent
    candidate = backend_dir / "models"
    if candidate.exists():
        return candidate

    return Path.cwd() / "models"


@dataclass
class CameraAlertProfile:
    camera_id: str = "default_cam"
    enable_weapon: bool = True
    enable_fire: bool = True
    enable_dog: bool = True
    enable_fight: bool = True
    weapon_conf_threshold: float = 0.18
    fire_conf_threshold: float = 0.18
    smoke_conf_threshold: float = 0.30
    dog_conf_threshold: float = 0.20
    fight_conf_threshold: float = 0.30
    save_alert_snapshots: bool = True
    alert_cooldown_seconds: float = 5.0
    enable_coffmap: bool = False  # read/written by main.py's camera-profile endpoints


class ThreatEngine:
    """
    Unified Zero-Prompt Multi-Threat Surveillance Engine.

    Two-stage architecture:
      Stage 1 (Fast, every frame): YOLO-based detectors for weapons, fire,
              dogs, and fights (proximity + motion gated).
      Stage 2 (Deep, flagged frames only): Kimi-VL forensic reasoning via
              EvidenceAuditor — confirms or rejects the fast-path detection
              to reduce false positives.
    """

    # Map threat types to EvidenceAuditor context types for VLM verification
    _VLM_CONTEXT_MAP = {
        "WEAPON": "weapon_verify",
        "FIRE_SMOKE": "fire_verify",
        "DOG_ATTACK": "animal_assault_verify",
        "ANIMAL_ASSAULT": "animal_assault_verify",
        "FIGHT_ASSAULT": "fight_verify",
    }

    def __init__(self, device: Optional[str] = None, enable_vlm: bool = True):
        if device is None:
            # Use the NVIDIA GPU when there is one; this used to be hard-coded to CPU.
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        self.device = device
        logger.info(f"ThreatEngine running detectors on: {self.device}")
        self.models_dir = _resolve_models_dir()
        logger.info(f"ThreatEngine using models directory: {self.models_dir}")

        # ---- Stage 1: Fast-path YOLO detectors ----

        # 1. Weapon Detector Model
        weapon_weights = self.models_dir / "weapon_detector_best.pt"
        if not weapon_weights.exists():
            weapon_weights = self.models_dir / "yolov8n.pt"

        logger.info(f"Loading Weapon Detector from {weapon_weights}")
        self.weapon_model = YOLO(str(weapon_weights)) if YOLO else None

        # 2. Fire & Smoke Detector Module
        fire_weights = str(self.models_dir / "fire_smoke_detector_best.pt")
        self.fire_detector = FireSmokeDetector(model_path=fire_weights, conf_threshold=0.18,
                                               smoke_conf_threshold=0.30, device=self.device)
        # Per-camera fire/smoke behaviour over time (flicker, growth, static fixtures)
        self._fire_trackers: Dict[str, FireSceneTracker] = {}

        # 3. Dog Attack / Stray Animal Detector Module (Generic COCO YOLO)
        dog_weights = self.models_dir / "dog_attack_detector_best.pt"
        if not dog_weights.exists():
            dog_weights = self.models_dir / "yolov8n.pt"
        self.dog_detector = DogAttackDetector(model_path=str(dog_weights), conf_threshold=0.20, device=self.device)

        # 4. Fight & Assault Detector (Proximity + Motion Gated)
        pose_weights = str(self.models_dir / "yolov8n-pose.pt")
        self.fight_detector = FightDetector(pose_model_path=pose_weights, device=self.device)

        # ---- Stage 2: Kimi-VL forensic confirmation ----
        self.enable_vlm = enable_vlm
        self._vlm_auditor = None  # Lazy-loaded on first use
        self._vlm_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vlm")
        self._pending_vlm: Dict[str, Future] = {}  # camera_id -> Future

        # Per-camera profiles and cooldown trackers
        self.camera_profiles: Dict[str, CameraAlertProfile] = {}
        self.last_alert_timestamps: Dict[str, Dict[str, float]] = defaultdict(dict)

        # Persistent animal lead tracking per camera stream
        self._animal_leads: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "last_species": None,
            "last_seen_sec": None,
            "total_animal_frames": 0,
            "is_aggressive_lead": False,
            "consecutive_contact_frames": 0,
            "contact_history": [],
            "leads": [],
        })

        logger.info("ThreatEngine initialized successfully with all 4 specialized safety modules.")
        if enable_vlm:
            logger.info("Stage 2 VLM confirmation enabled (Kimi-VL, loaded on first threat).")

    def get_or_create_profile(self, camera_id: str) -> CameraAlertProfile:
        if camera_id not in self.camera_profiles:
            self.camera_profiles[camera_id] = CameraAlertProfile(camera_id=camera_id)
        return self.camera_profiles[camera_id]

    def set_camera_profile(self, profile: CameraAlertProfile):
        self.camera_profiles[profile.camera_id] = profile

    def scan_frame(
        self,
        frame: np.ndarray,
        camera_id: str = "default_cam",
        annotate: bool = True,
        timestamp_sec: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Continuously scans a single CCTV video frame across all enabled threat modules.
        Uses a Unified Dynamic Scene Graph architecture:
          1. Grounded Entity Tracking (Persons, 17-Keypoint Skeletons, Animals, Vehicles)
          2. Spatial-Semantic Conflict Arbitration (zero if-else spaghetti)
          3. Dynamic Role Escalation (Combatants in physical altercations)
          4. Stage-2 Kimi-VL Cognitive Arbitration for flagged incident frames
        """
        if timestamp_sec is None:
            timestamp_sec = time.time()

        profile = self.get_or_create_profile(camera_id)
        h, w = frame.shape[:2]
        t0 = time.time()

        threats_detected = []
        overall_severity = "CLEAR"
        annotated_frame = frame.copy() if annotate else None

        # SKELETON CONNECTIONS FOR COCO 17-KEYPOINT POSE
        SKELETON_PAIRS = [
            (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
            (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)
        ]
        VEHICLE_CLASSES = {1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

        # -------------------------------------------------------------
        # STEP 1: POSE ESTIMATION & PHYSICAL ALTERCATION DETECTION
        # -------------------------------------------------------------
        persons = []
        fight_sev = "NORMAL"
        fight_predictions = []
        if profile.enable_fight and self.fight_detector:
            try:
                fight_res = self.fight_detector.detect(frame, annotate=False, timestamp_sec=timestamp_sec)
                persons = fight_res.get("persons", [])
                fight_sev = fight_res.get("severity", "NORMAL")
                fight_predictions = fight_res.get("predictions", [])
            except Exception as e:
                logger.error(f"Error during fight pose scan: {e}")

        # -------------------------------------------------------------
        # STEP 2: ANIMAL & VEHICLE GROUNDING (COCO Multi-Object Model)
        # -------------------------------------------------------------
        animals = []
        vehicles = []
        animal_leads_this_frame = []
        if self.dog_detector and self.dog_detector.model_loaded:
            try:
                # Use COCO detector to ground real-world animals and vehicles
                coco_res = self.dog_detector.model.predict(
                    frame, conf=0.10, device=self.device, verbose=False
                )[0]
                if coco_res.boxes is not None:
                    for box in coco_res.boxes:
                        cid = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        coords = box.xyxy[0].tolist()
                        bw, bh = coords[2] - coords[0], coords[3] - coords[1]
                        if bw > w * 0.9 and bh > h * 0.9:
                            continue
                        # Bbox area gate: filter tiny sub-pixel artifacts (< 0.1% frame area)
                        # Calibrated to preserve distant CCTV animals while rejecting flame-texture sparks
                        if (bw * bh) < (0.001 * w * h):
                            continue

                        raw_name = self.dog_detector.model.names.get(cid, "")
                        if cid in [14, 15, 16, 17, 18, 19, 20, 21, 22, 23] or any(k in raw_name.lower() for k in ["dog", "cat", "animal", "bird", "horse", "cow"]):
                            animal_name = "dog" if "dog" in raw_name.lower() or cid == 16 else (raw_name or "animal")
                            if conf >= 0.12:
                                animals.append({
                                    "class_name": animal_name,
                                    "confidence": conf,
                                    "bbox": coords,
                                    "is_aggressive": False
                                })
                            if conf < 0.25:
                                animal_leads_this_frame.append({
                                    "class_name": animal_name,
                                    "confidence": round(conf, 3),
                                    "bbox": coords,
                                    "timestamp_sec": round(timestamp_sec, 2)
                                })
                        elif cid in VEHICLE_CLASSES or any(k in raw_name.lower() for k in ["motorcycle", "car", "bicycle", "truck", "bus"]):
                            veh_name = VEHICLE_CLASSES.get(cid, raw_name or "vehicle")
                            vehicles.append({
                                "class_name": veh_name,
                                "confidence": conf,
                                "bbox": coords
                            })
            except Exception as e:
                logger.error(f"Error during animal/vehicle scan: {e}")

        # -------------------------------------------------------------
        # STEP 3: SPECIALIZED WEAPON CANDIDATE PROPOSALS
        # -------------------------------------------------------------
        raw_weapons = []
        if profile.enable_weapon and self.weapon_model:
            try:
                self.weapon_model.to(self.device)
                w_results = self.weapon_model.predict(
                    frame, conf=0.35, verbose=False
                )
                if w_results[0].boxes is not None:
                    for box in w_results[0].boxes:
                        cid = int(box.cls.item())
                        conf = float(box.conf.item())
                        name = self.weapon_model.names.get(cid, f"class_{cid}")
                        coords = box.xyxy[0].tolist()
                        bw, bh = coords[2] - coords[0], coords[3] - coords[1]
                        if bw < w * 0.85 and bh < h * 0.85:
                            raw_weapons.append({
                                "class_name": name,
                                "confidence": conf,
                                "bbox": coords
                            })
            except Exception as e:
                logger.error(f"Error during weapon scan: {e}")

        # -------------------------------------------------------------
        # STEP 4: SPECIALIZED FIRE & SMOKE CANDIDATE PROPOSALS
        # -------------------------------------------------------------
        raw_fires = []
        if profile.enable_fire and self.fire_detector and self.fire_detector.model_loaded:
            try:
                self.fire_detector.conf_threshold = profile.fire_conf_threshold
                self.fire_detector.smoke_conf_threshold = profile.smoke_conf_threshold
                f_res = self.fire_detector.detect(frame, annotate=False)
                for det in f_res.get("detections", []):
                    raw_fires.append(det)
                # Judge each box over time: flicker/growth = real, unchanging = fixture.
                # Updated on every frame (also with no boxes) so frame differences stay valid.
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
                self._fire_tracker(camera_id).update(gray, raw_fires, timestamp_sec)
            except Exception as e:
                logger.error(f"Error during fire scan: {e}")

        # -------------------------------------------------------------
        # STEP 5: SPATIAL-SEMANTIC TENSOR ARBITRATION (Zero If-Else Ladder)
        # -------------------------------------------------------------
        # Arbitrate weapons against grounded vehicles, animals, and non-combatant clothing
        verified_weapons = []
        for w_cand in raw_weapons:
            wb = w_cand["bbox"]
            is_suppressed = False
            # 1. Suppress if overlapping vehicle (kickstands, handles, exhaust)
            for v in vehicles:
                vb = v["bbox"]
                ix1, iy1 = max(wb[0], vb[0]), max(wb[1], vb[1])
                ix2, iy2 = min(wb[2], vb[2]), min(wb[3], vb[3])
                inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                area_w = (wb[2] - wb[0]) * (wb[3] - wb[1])
                area_v = (vb[2] - vb[0]) * (vb[3] - vb[1])
                union = area_w + area_v - inter
                iou = inter / union if union > 0 else 0.0
                if iou > 0.10 or (area_w > 0 and inter / area_w > 0.20):
                    is_suppressed = True
                    break
            if is_suppressed:
                continue

            # 2. Suppress if overlapping animal (biological creature != weapon)
            for a in animals:
                ab = a["bbox"]
                ix1, iy1 = max(wb[0], ab[0]), max(wb[1], ab[1])
                ix2, iy2 = min(wb[2], ab[2]), min(wb[3], ab[3])
                inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                area_w = (wb[2] - wb[0]) * (wb[3] - wb[1])
                area_a = (ab[2] - ab[0]) * (ab[3] - ab[1])
                union = area_w + area_a - inter
                iou = inter / union if union > 0 else 0.0
                if iou > 0.10 or (area_w > 0 and inter / area_w > 0.20):
                    is_suppressed = True
                    break
            if is_suppressed:
                continue

            # 3. Suppress if contained inside non-combatant clothing (e.g. sitting person pants)
            for p in persons:
                if not p.get("is_combatant", False):
                    pb = p["bbox"]
                    ix1, iy1 = max(wb[0], pb[0]), max(wb[1], pb[1])
                    ix2, iy2 = min(wb[2], pb[2]), min(wb[3], pb[3])
                    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                    area_w = (wb[2] - wb[0]) * (wb[3] - wb[1])
                    if area_w > 0 and (inter / area_w > 0.50) and w_cand["confidence"] < 0.60:
                        is_suppressed = True
                        break

            if not is_suppressed:
                verified_weapons.append(w_cand)

        # Fire and smoke detections, minus boxes proven to be unchanging fixtures
        # (lamps, signs, reflections, haze): real flames flicker and real smoke grows/drifts.
        verified_fires = [f for f in raw_fires if not f.get("static")]
        static_fires = [f for f in raw_fires if f.get("static")]
        if static_fires:
            logger.debug(f"[Arbitration] Ignoring {len(static_fires)} static fire/smoke look-alike(s) on {camera_id}")

        # -------------------------------------------------------------
        # STEP 5.5: FIRE-ANIMAL CROSS-SUPPRESSION (Reject Fire Textures)
        # -------------------------------------------------------------
        # Flickering flames and smoke silhouettes often falsely trigger animal detection.
        # If any candidate animal bbox overlaps an active fire/smoke zone, suppress the animal.
        if verified_fires and animals:
            all_fires = verified_fires
            filtered_animals = []
            for a in animals:
                ab = a["bbox"]
                area_a = max(1.0, (ab[2] - ab[0]) * (ab[3] - ab[1]))
                is_fire_artifact = False
                for f_cand in all_fires:
                    # Only open flames or intense infernos (conf >= 0.65) suppress animals; do not suppress real dogs on gray street smoke noise
                    f_label = str(f_cand.get("label", f_cand.get("class_name", ""))).upper()
                    f_conf = float(f_cand.get("confidence", 0.0))
                    if f_label != "FIRE" and f_conf < 0.65:
                        continue

                    fb = f_cand["bbox"] if isinstance(f_cand["bbox"], list) else [
                        f_cand["bbox"]["x1"], f_cand["bbox"]["y1"], f_cand["bbox"]["x2"], f_cand["bbox"]["y2"]
                    ]
                    ix1, iy1 = max(ab[0], fb[0]), max(ab[1], fb[1])
                    ix2, iy2 = min(ab[2], fb[2]), min(ab[3], fb[3])
                    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                    if (inter / area_a) >= 0.20:
                        is_fire_artifact = True
                        logger.info(f"[Arbitration] Suppressed ghost animal ({a['class_name']}) overlapping flame zone (overlap={inter/area_a:.2f})")
                        break
                if not is_fire_artifact:
                    filtered_animals.append(a)
            animals = filtered_animals

        # -------------------------------------------------------------
        # STEP 6: PERSON-ANIMAL CONTACT ARBITRATION & ATTACK DYNAMICS
        # -------------------------------------------------------------
        animal_assault_detected = False
        animal_assault_species = []
        contact_this_frame = False
        for a_det in animals:
            # Gate 1: Confirmed animal candidates (conf >= 0.12)
            if a_det["confidence"] < 0.12:
                continue

            for p in persons:
                p_bbox = p["bbox"]
                a_bbox = a_det["bbox"]
                p_height = p_bbox[3] - p_bbox[1]
                if p_height <= 0:
                    continue

                # Relative animal coverage & IoU
                # In real CCTV, standing humans (~150k px) are vastly larger than dogs (~8k px).
                # Max possible standard IoU is < 0.06 even during active bites.
                # We check relative animal coverage (fraction of animal overlapping human).
                ix1 = max(p_bbox[0], a_bbox[0])
                iy1 = max(p_bbox[1], a_bbox[1])
                ix2 = min(p_bbox[2], a_bbox[2])
                iy2 = min(p_bbox[3], a_bbox[3])
                inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                area_a = max(1.0, (a_bbox[2] - a_bbox[0]) * (a_bbox[3] - a_bbox[1]))
                relative_coverage = inter / area_a

                # Center-to-center distance
                p_cx = (p_bbox[0] + p_bbox[2]) / 2
                p_cy = (p_bbox[1] + p_bbox[3]) / 2
                a_cx = (a_bbox[0] + a_bbox[2]) / 2
                a_cy = (a_bbox[1] + a_bbox[3]) / 2
                dist = ((p_cx - a_cx) ** 2 + (p_cy - a_cy) ** 2) ** 0.5

                # Gate 2: Physical overlap on the animal (>= 10% of animal on person)
                # OR close proximity to person's lower body/limbs (dist < p_height * 0.80)
                if relative_coverage >= 0.10 or dist < (p_height * 0.80):
                    contact_this_frame = True
                    species = a_det["class_name"].upper()
                    if species not in animal_assault_species:
                        animal_assault_species.append(species)

        # Update persistent animal lead tracking
        lead = self._animal_leads[camera_id]
        if animals:
            high_conf_animals = [a for a in animals if a["confidence"] >= 0.12]
            if high_conf_animals:
                lead["last_species"] = high_conf_animals[0]["class_name"].upper()
                lead["last_seen_sec"] = timestamp_sec
                lead["total_animal_frames"] += 1

        # Record sensor intelligence leads
        for alead in animal_leads_this_frame:
            if len(lead.get("leads", [])) < 20:
                lead["leads"].append(alead)

        # Gate 3: Temporal persistence via 6-frame rolling window (resilient to motion blur)
        # Requires 2+ contact detections across the last 6 sampled frames
        if "contact_history" not in lead:
            lead["contact_history"] = []
        lead["contact_history"].append(contact_this_frame)
        if len(lead["contact_history"]) > 6:
            lead["contact_history"].pop(0)

        recent_contacts = sum(1 for c in lead["contact_history"] if c)
        if recent_contacts >= 2:
            animal_assault_detected = True
            lead["is_aggressive_lead"] = True
            # Mark the aggressive animals for this frame
            for a_det in animals:
                a_det["is_aggressive"] = True

        # -------------------------------------------------------------
        # STEP 7: AGGREGATE DETECTED THREATS & SEVERITY
        # -------------------------------------------------------------
        # Cross-Threat Conflict Arbitration:
        # 1. Active Fire Scene: people working right next to an established fire
        #    (firefighters, evacuees) move like fighters. Their fight score is
        #    lowered one level instead of being deleted, and only for them.
        #    Smoke alone never lowers a fight score.
        fire_zones = [self._bbox_list(f["bbox"]) for f in verified_fires
                      if f.get("persistent") and str(f.get("class_name", "")).lower() == "fire"]
        persons_by_tid = {p.get("track_id"): p for p in persons}

        # 2. Animal Assault takes priority: struggling against an animal is NOT a human fight
        if animal_assault_detected:
            # Generate ANIMAL_ASSAULT threats
            for a_det in animals:
                if a_det.get("is_aggressive"):
                    threats_detected.append({
                        "type": "ANIMAL_ASSAULT",
                        "label": f"DOG_ATTACK_{a_det['class_name'].upper()}",
                        "confidence": a_det["confidence"],
                        "severity": "CRITICAL",
                        "bbox": {
                            "x1": round(a_det["bbox"][0], 1), "y1": round(a_det["bbox"][1], 1),
                            "x2": round(a_det["bbox"][2], 1), "y2": round(a_det["bbox"][3], 1)
                        }
                    })
            overall_severity = "CRITICAL"
            # Always suppress human fight when animal attack is actively ongoing
            fight_sev = "NORMAL"
            fight_predictions = []

        # 3. Fight Threats (only if not suppressed by animal attack)
        if fight_sev in ["ACTIVE_FIGHT", "AGGRESSIVE_STANCE"]:
            for pred in fight_predictions:
                sev = "CRITICAL" if pred.get("prediction") == "fighting" else "HIGH"
                conf = pred.get("confidence", 0.90)
                person = persons_by_tid.get(pred.get("track_id"))
                near_fire = bool(person and fire_zones and self._near_any(person["bbox"], fire_zones))
                if near_fire:
                    sev = "HIGH" if sev == "CRITICAL" else "MEDIUM"
                    conf = round(conf * 0.5, 3)
                if self._SEV_RANK[sev] > self._SEV_RANK.get(overall_severity, 0):
                    overall_severity = sev
                threats_detected.append({
                    "type": "FIGHT_ASSAULT",
                    "label": pred.get("prediction", "FIGHTING").upper(),
                    "confidence": conf,
                    "severity": sev,
                    "track_id": pred.get("track_id"),
                    "near_fire": near_fire,
                    "cues": pred.get("cues", []),
                })

        # 3. Verified Weapon Threats
        for w_det in verified_weapons:
            threats_detected.append({
                "type": "WEAPON",
                "label": w_det["class_name"].upper(),
                "confidence": round(w_det["confidence"], 4),
                "severity": "CRITICAL",
                "bbox": {
                    "x1": round(w_det["bbox"][0], 1), "y1": round(w_det["bbox"][1], 1),
                    "x2": round(w_det["bbox"][2], 1), "y2": round(w_det["bbox"][3], 1)
                }
            })
            overall_severity = "CRITICAL"

        # 4. Verified Fire/Smoke Threats
        for f_det in verified_fires:
            fb = f_det["bbox"] if isinstance(f_det["bbox"], dict) else {
                "x1": f_det["bbox"][0], "y1": f_det["bbox"][1], "x2": f_det["bbox"][2], "y2": f_det["bbox"][3]
            }
            cname = f_det.get("class_name", "FIRE").upper()
            threats_detected.append({
                "type": "FIRE_SMOKE",
                "label": cname,
                "confidence": f_det["confidence"],
                "severity": "CRITICAL" if "FIRE" in cname else "MEDIUM",
                "bbox": fb,
                "track_id": f_det.get("track_id"),
                "growing": bool(f_det.get("growing")),
                "persistent": bool(f_det.get("persistent")),
            })
            if "FIRE" in cname:
                overall_severity = "CRITICAL"
            elif overall_severity == "CLEAR":
                overall_severity = "MEDIUM"

        # 5. Non-aggressive animal presence (still tracked as entity, not threat)
        for a_det in animals:
            if a_det.get("is_aggressive") and not animal_assault_detected:
                # Legacy path: aggressive animal not caught by contact arbitration
                threats_detected.append({
                    "type": "DOG_ATTACK",
                    "label": f"AGGRESSIVE_{a_det['class_name'].upper()}",
                    "confidence": a_det["confidence"],
                    "severity": "HIGH",
                    "bbox": {
                        "x1": round(a_det["bbox"][0], 1), "y1": round(a_det["bbox"][1], 1),
                        "x2": round(a_det["bbox"][2], 1), "y2": round(a_det["bbox"][3], 1)
                    }
                })
                if overall_severity in ["CLEAR", "LOW"]:
                    overall_severity = "HIGH"

        # -------------------------------------------------------------
        # STEP 8: UNIFIED DYNAMIC SCENE RENDERING
        # -------------------------------------------------------------
        if annotate and annotated_frame is not None:
            # 1. Render Grounded Vehicles (subtle slate border)
            for v in vehicles:
                bx = [int(c) for c in v["bbox"]]
                cv2.rectangle(annotated_frame, (bx[0], bx[1]), (bx[2], bx[3]), (160, 160, 160), 1)
                cv2.putText(annotated_frame, f"VEHICLE: {v['class_name'].upper()}", (bx[0], max(16, bx[1] - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 160, 160), 1)

            # 2. Render Grounded Animals (Emerald Green)
            for a in animals:
                bx = [int(c) for c in a["bbox"]]
                cv2.rectangle(annotated_frame, (bx[0], bx[1]), (bx[2], bx[3]), (0, 220, 80), 2)
                cv2.putText(annotated_frame, f"ANIMAL: {a['class_name'].upper()}", (bx[0], max(16, bx[1] - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 80), 2)

            # 3. Render Grounded Persons (Cyan for Normal, Bold Crimson for Combatants)
            for p in persons:
                bx = [int(c) for c in p["bbox"]]
                is_combatant = p.get("is_combatant", False) or (fight_sev in ["ACTIVE_FIGHT", "AGGRESSIVE_STANCE"] and p.get("motion_score", 0) > 0.001)
                color = (0, 0, 255) if is_combatant else (255, 180, 0)
                label = f"COMBATANT #{p['track_id']} [FIGHTING]" if is_combatant else f"PERSON #{p['track_id']}"

                cv2.rectangle(annotated_frame, (bx[0], bx[1]), (bx[2], bx[3]), color, 2)
                cv2.putText(annotated_frame, label, (bx[0], max(18, bx[1] - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                # Draw 17-Keypoint Pose Skeleton
                kps = p.get("keypoints", [])
                if len(kps) >= 17:
                    for p1_idx, p2_idx in SKELETON_PAIRS:
                        x1, y1 = int(kps[p1_idx][0]), int(kps[p1_idx][1])
                        x2, y2 = int(kps[p2_idx][0]), int(kps[p2_idx][1])
                        if x1 > 0 and y1 > 0 and x2 > 0 and y2 > 0:
                            cv2.line(annotated_frame, (x1, y1), (x2, y2), (0, 0, 255) if is_combatant else (255, 200, 0), 2)
                    for kp in kps:
                        kx, ky = int(kp[0]), int(kp[1])
                        if kx > 0 and ky > 0:
                            cv2.circle(annotated_frame, (kx, ky), 3, (0, 0, 255) if is_combatant else (0, 255, 0), -1)

            # 4. Render Confirmed Weapons (Crimson)
            for w_det in verified_weapons:
                bx = [int(c) for c in w_det["bbox"]]
                cv2.rectangle(annotated_frame, (bx[0], bx[1]), (bx[2], bx[3]), (0, 0, 255), 2)
                cv2.putText(annotated_frame, f"WEAPON: {w_det['class_name'].upper()} {w_det['confidence']*100:.0f}%",
                            (bx[0], max(18, bx[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            # 5. Render Confirmed Fire/Smoke (Amber/Orange)
            for f_det in verified_fires:
                fb = f_det["bbox"]
                if isinstance(fb, dict):
                    x1, y1, x2, y2 = int(fb["x1"]), int(fb["y1"]), int(fb["x2"]), int(fb["y2"])
                else:
                    x1, y1, x2, y2 = int(fb[0]), int(fb[1]), int(fb[2]), int(fb[3])
                cname = f_det.get("class_name", "FIRE").upper()
                color = (0, 60, 255) if "FIRE" in cname else (0, 160, 255)
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated_frame, f"{cname} {f_det['confidence']*100:.0f}%",
                            (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # 6. Render Modern Glassmorphic HUD Banner with Persistent Animal Lead
            hud_color = (0, 0, 180) if overall_severity in ["CRITICAL", "HIGH"] else (40, 40, 40)
            cv2.rectangle(annotated_frame, (0, 0), (w, 32), hud_color, -1)

            # Build animal segment of HUD with persistent lead intelligence
            animal_hud = f"ANIMALS: {len(animals)}"
            if animals:
                species_list = list(set(a["class_name"].upper() for a in animals))
                if animal_assault_detected:
                    animal_hud += f" [{', '.join(species_list)} - ATTACK]"
                else:
                    animal_hud += f" [{', '.join(species_list)}]"
            elif lead["last_species"]:
                # Animal left the frame but we retain the intelligence lead
                animal_hud += f" [LEAD: {lead['last_species']} OBSERVED]"

            hud_text = f"VIGILINX CCTV | STATUS: {overall_severity} | PERSONS: {len(persons)} | {animal_hud} | VEHICLES: {len(vehicles)}"
            cv2.putText(annotated_frame, hud_text, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1)

        total_latency_ms = round((time.time() - t0) * 1000, 2)

        # Check alert trigger & cooldown
        has_active_threat = len(threats_detected) > 0
        should_trigger_alert = False

        if has_active_threat:
            last_alert = self.last_alert_timestamps[camera_id].get(overall_severity, 0.0)
            if (timestamp_sec - last_alert) >= profile.alert_cooldown_seconds:
                should_trigger_alert = True
                self.last_alert_timestamps[camera_id][overall_severity] = timestamp_sec

        # -------------------------------------------------------------
        # STEP 9: STAGE 2 KIMI-VL FORENSIC AUDITING (Async, non-blocking)
        # -------------------------------------------------------------
        vlm_confirmation = None
        if (self.enable_vlm
                and should_trigger_alert
                and overall_severity in ("HIGH", "CRITICAL")
                and threats_detected):
            primary_threat = threats_detected[0]
            context_type = self._VLM_CONTEXT_MAP.get(primary_threat["type"], "security_audit")
            try:
                vlm_confirmation = self._submit_vlm_confirmation(frame, camera_id, context_type)
            except Exception as e:
                logger.error(f"Failed to submit VLM confirmation: {e}")

        return {
            "camera_id": camera_id,
            "timestamp_sec": timestamp_sec,
            "has_threat": has_active_threat,
            "overall_severity": overall_severity,
            "should_trigger_alert": should_trigger_alert,
            "threats_count": len(threats_detected),
            "threats": threats_detected,
            "latency_ms": total_latency_ms,
            "annotated_frame": annotated_frame if annotate else None,
            "vlm_pending": vlm_confirmation is not None,
            "animals": animals,
            "vehicles": vehicles,
            "persons": persons,
            "animal_assault_detected": animal_assault_detected,
            "animal_assault_species": animal_assault_species,
            "animal_leads": animal_leads_this_frame,
            "lead_history": lead.get("leads", []),
            "animal_lead": {
                "last_species": lead["last_species"],
                "last_seen_sec": lead["last_seen_sec"],
                "total_animal_frames": lead["total_animal_frames"],
                "is_aggressive_lead": lead["is_aggressive_lead"],
            },
            "scene_entities": {
                "persons": len(persons),
                "animals": len(animals),
                "vehicles": len(vehicles)
            }
        }

    # ------------------------------------------------------------------
    #  Stage 2: VLM confirmation helpers
    # ------------------------------------------------------------------

    def _get_auditor(self):
        """Lazy-load the EvidenceAuditor (and Kimi-VL model) on first use."""
        if self._vlm_auditor is None:
            try:
                from services.vlm_service import EvidenceAuditor
                self._vlm_auditor = EvidenceAuditor()
                logger.info("[Stage 2] EvidenceAuditor (Kimi-VL) loaded.")
            except Exception as e:
                logger.error(f"[Stage 2] Failed to load EvidenceAuditor: {e}")
        return self._vlm_auditor

    def _submit_vlm_confirmation(
        self, frame, camera_id: str, context_type: str
    ) -> Optional[Future]:
        """Submit a frame to Kimi-VL for forensic confirmation (non-blocking)."""
        if not self.enable_vlm:
            return None
        auditor = self._get_auditor()
        if auditor is None:
            return None

        def _run():
            try:
                result = auditor.audit_incident(
                    frame, context_type=context_type
                )
                confirmed = result.get("verified_threat", False)
                confidence = result.get("confidence", 0.0)
                description = result.get("reasoning", "")
                model = result.get("model_used", "unknown")
                latency = result.get("latency_seconds", 0)

                status = "CONFIRMED" if confirmed else "REJECTED"
                logger.info(
                    f"[Stage 2 VLM] {status} threat on {camera_id} "
                    f"(confidence={confidence:.2f}, model={model}, "
                    f"latency={latency}s): {description[:100]}"
                )
                return result
            except Exception as e:
                logger.error(f"[Stage 2 VLM] Error during confirmation: {e}")
                return {"error": str(e), "verified_threat": False}

        future = self._vlm_executor.submit(_run)
        self._pending_vlm[camera_id] = future
        return future

    def get_vlm_result(self, camera_id: str) -> Optional[Dict]:
        """Check if a pending VLM confirmation has completed for this camera."""
        future = self._pending_vlm.get(camera_id)
        if future is None:
            return None
        if not future.done():
            return {"status": "pending"}
        try:
            result = future.result(timeout=0)
            del self._pending_vlm[camera_id]
            return result
        except Exception as e:
            del self._pending_vlm[camera_id]
            return {"error": str(e)}

    # ------------------------------------------------------------------
    #  Fire tracking / arbitration helpers
    # ------------------------------------------------------------------
    _SEV_RANK = {"CLEAR": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

    def _fire_tracker(self, camera_id: str) -> FireSceneTracker:
        if camera_id not in self._fire_trackers:
            self._fire_trackers[camera_id] = FireSceneTracker()
        return self._fire_trackers[camera_id]

    def get_static_fire_track_ids(self, camera_id: str) -> set:
        """Fire/smoke tracks of the current stream that turned out to be fixtures.
        Earlier frames of these tracks were reported before that was known."""
        tracker = self._fire_trackers.get(camera_id)
        return tracker.static_track_ids() if tracker else set()

    @staticmethod
    def _bbox_list(bbox) -> List[float]:
        if isinstance(bbox, dict):
            return [bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]]
        return list(bbox[:4])

    @staticmethod
    def _near_any(person_bbox, zones) -> bool:
        """Person within one body size (longer box side) of any zone."""
        pb = person_bbox
        body = max(pb[2] - pb[0], pb[3] - pb[1])
        for z in zones:
            dx = max(0.0, z[0] - pb[2], pb[0] - z[2])
            dy = max(0.0, z[1] - pb[3], pb[1] - z[3])
            if (dx * dx + dy * dy) ** 0.5 <= body:
                return True
        return False

    def reset_stream_state(self, camera_id: str, clear_scene_memory: bool = False):
        """Resets per-camera state when switching videos or camera streams.

        clear_scene_memory also forgets fixtures (lamps, signs) learned for this
        camera id; use it when the next video may come from a different place.
        """
        if self.fight_detector:
            self.fight_detector.reset_buffers()
        if camera_id in self._fire_trackers:
            self._fire_trackers[camera_id].reset_stream(clear_memory=clear_scene_memory)
        if camera_id in self.last_alert_timestamps:
            self.last_alert_timestamps[camera_id].clear()
        # Reset persistent animal lead tracking for this camera
        if camera_id in self._animal_leads:
            self._animal_leads[camera_id] = {
                "last_species": None,
                "last_seen_sec": None,
                "total_animal_frames": 0,
                "is_aggressive_lead": False,
                "consecutive_contact_frames": 0,
                "contact_history": [],
                "leads": [],
            }
