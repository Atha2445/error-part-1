"""
alerts/fight/detector.py — Fight/Assault Detection (Proximity + Motion Gated).

Replaces the previous .pkl Random Forest classifier approach with the
proximity-gating architecture from the Fight workspace:

  1. YOLOv8-Pose extracts person skeletons and bounding boxes
  2. Proximity gate: are two people within arm's reach?
  3. Motion analysis: are arms moving rapidly? (wrist velocity over time)
  4. Posture check: are arms raised aggressively above shoulders?

  5. Body cues (added): directed strikes with hands, feet or head, shoves and
     tackles (sudden torso acceleration), a person knocked down, and attacks
     on a person who is already down. These are measured in torso lengths per
     second using real timestamps, so they don't depend on camera distance,
     resolution or frame rate, and a lying person is measured correctly.

No .pkl files required. Works out of the box with just yolov8n-pose.pt.

Severity levels:
  NORMAL           -> No concerning activity
  AGGRESSIVE_STANCE -> Close proximity with moderate motion or raised arms
  ACTIVE_FIGHT     -> Close proximity with rapid arm movement (punching)
"""
import itertools
import math
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None


@dataclass
class FightCuePolicy:
    """Body-relative limits for the added fight cues.

    Speeds are in torso lengths (shoulder-to-hip) per second, so one set of
    values holds for near and far people and any frame rate. They are
    physically motivated starting points; calibrate them on labelled clips.
    """
    strike_aggressive: float = 6.0    # hand/foot/head moving at the other person (vs. own hips)
    strike_fighting: float = 10.0
    shove_accel: float = 15.0         # torso acceleration, torso lengths / s^2
    approach_speed: float = 4.0       # closing speed of two people
    planted_hip_speed: float = 2.0    # feet count as kicks only when the body isn't travelling
    upright_angle: float = 35.0       # torso angle from vertical, degrees
    fallen_angle: float = 60.0
    fall_window_sec: float = 1.5      # went from upright to fallen within this time
    fall_memory_sec: float = 2.0      # a fall stays "recent" this long
    cue_window_sec: float = 1.0       # motion looked at for strikes/shoves
    min_step_sec: float = 0.15        # samples closer than this are skipped (keypoint jitter)
    max_step_sec: float = 0.6         # larger gaps are not treated as one movement
    max_step_torso: float = 2.0       # bigger jumps between samples = tracking swap, ignored
    history_sec: float = 3.0
    torso_to_body: float = 0.3        # torso ~ 0.3 x body length, used when keypoints are missing


class FightDetector:
    SEVERITY_LEVELS = {
        "NORMAL": {"level": 0, "color": (0, 200, 0), "label": "NORMAL ACTIVITY"},
        "AGGRESSIVE_STANCE": {"level": 1, "color": (0, 140, 255), "label": "AGGRESSIVE STANCE DETECTED"},
        "ACTIVE_FIGHT": {"level": 2, "color": (0, 0, 255), "label": "FIGHT IN PROGRESS"},
    }

    # COCO 17-keypoint indices
    NOSE = 0
    L_SHOULDER, R_SHOULDER = 5, 6
    L_ELBOW, R_ELBOW = 7, 8
    L_WRIST, R_WRIST = 9, 10
    L_HIP, R_HIP = 11, 12
    L_KNEE, R_KNEE = 13, 14
    L_ANKLE, R_ANKLE = 15, 16
    KP_CONF = 0.3

    # --- Tunable thresholds ---------------------------------------------------

    # Proximity: two persons whose center-to-center pixel distance is less than
    # this fraction of the average bounding-box height are "within arm's reach".
    PROXIMITY_RATIO = 0.95

    # Normalized wrist velocity per frame (keypoints are 0-1 normalized).
    # Calibrated for real physical altercations (punching, tackling, brawling).
    WRIST_VEL_AGGRESSIVE = 0.025   # moderate grappling / aggressive posture
    WRIST_VEL_FIGHTING = 0.040     # rapid punching / physical combat

    # Minimum frames of keypoint history needed before motion can be computed.
    MIN_HISTORY_FRAMES = 3

    # Maximum keypoint buffer length per person (prevents unbounded memory).
    MAX_BUFFER_LEN = 30

    def __init__(
        self,
        pose_model_path: str = "yolov8n-pose.pt",
        device: str = "cpu",
        cue_policy: Optional[FightCuePolicy] = None,
        **kwargs,  # Accept and ignore classifier_path/scaler_path for backward compat
    ):
        # Resolve pose model path from models/ directory
        if not Path(pose_model_path).exists():
            candidates = []
            if getattr(sys, "frozen", False):
                candidates.append(Path(sys.executable).parent / "models" / Path(pose_model_path).name)
                if hasattr(sys, "_MEIPASS"):
                    candidates.append(Path(sys._MEIPASS) / "models" / Path(pose_model_path).name)
            base1 = Path(__file__).resolve().parent.parent.parent / "models"
            base2 = Path(__file__).resolve().parent.parent / "models"
            candidates.extend([base1 / Path(pose_model_path).name, base2 / Path(pose_model_path).name, Path.cwd() / "models" / Path(pose_model_path).name])
            for candidate in candidates:
                if candidate.exists():
                    pose_model_path = str(candidate)
                    break

        # Load pose model
        if YOLO is not None:
            self.pose_model = YOLO(pose_model_path)
        else:
            self.pose_model = None
            print("[Fight] WARNING: ultralytics not available.")

        self.device = device
        self.cues = cue_policy or FightCuePolicy()
        # Per-person timestamped pose history for the body cues
        self._pose_history: Dict[int, deque] = {}
        self._last_fall: Dict[int, float] = {}
        # Per-person keypoint history: track_id → list of (17, 2) normalized arrays
        self.keypoint_buffers: Dict[int, List[np.ndarray]] = {}
        # Spatial IoU tracking to eliminate person ID-swapping artifacts
        self._prev_tracks: List[Dict] = []
        self._next_track_id: int = 0

    def reset(self):
        """Reset temporal state between video streams."""
        self.keypoint_buffers.clear()
        self._pose_history.clear()
        self._last_fall.clear()
        self._prev_tracks.clear()
        self._next_track_id = 0

    def reset_buffers(self):
        """Compatibility alias for ThreatEngine."""
        self.reset()

    def _assign_tracks(self, bboxes: List[Tuple[float, float, float, float]]) -> List[int]:
        """Assign persistent track IDs based on spatial bounding box IoU."""
        if not bboxes:
            self._prev_tracks = []
            return []

        assigned_ids = []
        used_prev = set()

        for b in bboxes:
            best_iou = 0.0
            best_idx = -1
            for idx, prev in enumerate(self._prev_tracks):
                if idx in used_prev:
                    continue
                pb = prev["bbox"]
                ix1, iy1 = max(b[0], pb[0]), max(b[1], pb[1])
                ix2, iy2 = min(b[2], pb[2]), min(b[3], pb[3])
                inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                area_b = (b[2] - b[0]) * (b[3] - b[1])
                area_p = (pb[2] - pb[0]) * (pb[3] - pb[1])
                union = area_b + area_p - inter
                iou = inter / union if union > 0 else 0.0

                if iou > best_iou:
                    best_iou = iou
                    best_idx = idx

            if best_iou >= 0.20 and best_idx >= 0:
                tid = self._prev_tracks[best_idx]["track_id"]
                used_prev.add(best_idx)
                assigned_ids.append(tid)
            else:
                tid = self._next_track_id
                self._next_track_id += 1
                assigned_ids.append(tid)

        self._prev_tracks = [{"track_id": tid, "bbox": bboxes[i]} for i, tid in enumerate(assigned_ids)]
        return assigned_ids

    def detect(self, image: np.ndarray, annotate: bool = True,
               timestamp_sec: Optional[float] = None) -> Dict:
        """
        Run fight detection on a single frame.

        Pipeline:
          1. YOLOv8-Pose → person bounding boxes + 17 keypoints
          2. Spatial IoU tracking to eliminate frame-to-frame index swapping
          3. Buffer keypoints per person for temporal motion analysis
          4. Compute per-person arm (wrist) velocity
          5. Check all person-pairs for proximity
          6. Combine proximity + motion + posture → severity
        """
        if self.pose_model is None:
            return {
                "persons_detected": 0,
                "severity": "NORMAL",
                "severity_info": self.SEVERITY_LEVELS["NORMAL"],
                "predictions": [],
                "model_loaded": False,
            }

        h, w = image.shape[:2]
        t0 = time.time()
        now = timestamp_sec if timestamp_sec is not None else t0

        # --- Step 1: Pose estimation ---
        results = self.pose_model.predict(
            image, device=self.device, verbose=False, conf=0.3
        )
        inference_ms = round((time.time() - t0) * 1000, 2)

        persons = []

        if results[0].keypoints is not None and len(results[0].keypoints) > 0:
            kps_data = results[0].keypoints.data.cpu().numpy()  # (N, 17, 3)
            boxes = results[0].boxes

            raw_bboxes = []
            valid_indices = []
            for i, kps in enumerate(kps_data):
                if kps is None or len(kps) < 17:
                    continue
                confs = kps[:, 2]
                if boxes is not None and i < len(boxes):
                    bbox = tuple(boxes[i].xyxy[0].tolist())
                else:
                    valid_mask = confs > 0.3
                    if valid_mask.any():
                        bbox = (
                            float(kps[valid_mask, 0].min()),
                            float(kps[valid_mask, 1].min()),
                            float(kps[valid_mask, 0].max()),
                            float(kps[valid_mask, 1].max()),
                        )
                    else:
                        continue
                raw_bboxes.append(bbox)
                valid_indices.append(i)

            # Spatial tracking: match to previous frame by IoU to avoid jumping indices
            track_ids = self._assign_tracks(raw_bboxes)

            for idx, i in enumerate(valid_indices):
                kps = kps_data[i]
                bbox = raw_bboxes[idx]
                track_id = track_ids[idx]

                xy = kps[:, :2]       # (17, 2) pixel coords
                confs = kps[:, 2]     # (17,) per-keypoint confidence

                # Normalize to 0-1 for frame-size-independent velocity
                xy_norm = xy.copy()
                xy_norm[:, 0] /= max(w, 1)
                xy_norm[:, 1] /= max(h, 1)

                # --- Step 2: Buffer keypoints ---
                if track_id not in self.keypoint_buffers:
                    self.keypoint_buffers[track_id] = []
                self.keypoint_buffers[track_id].append(xy_norm)
                if len(self.keypoint_buffers[track_id]) > self.MAX_BUFFER_LEN:
                    self.keypoint_buffers[track_id] = \
                        self.keypoint_buffers[track_id][-self.MAX_BUFFER_LEN:]

                # --- Step 3: Per-person motion + posture ---
                motion_score = self._compute_wrist_velocity(track_id)
                raised_arms = self._check_raised_arms(xy_norm, confs)
                body = self._record_pose(track_id, now, xy, confs, bbox)

                persons.append({
                    "track_id": track_id,
                    "bbox": bbox,
                    "keypoints": xy.tolist(),
                    "avg_confidence": round(float(np.mean(confs)), 3),
                    "motion_score": motion_score,
                    "raised_arms": raised_arms,
                    "fallen": body["fallen"],
                    "fell_recently": body["fell_recently"],
                })

        # Forget people who left the scene
        for tid in [k for k, hist in self._pose_history.items() if not hist or now - hist[-1]["t"] > self.cues.history_sec or now < hist[-1]["t"]]:
            self._pose_history.pop(tid, None)
            self._last_fall.pop(tid, None)

        # --- Step 4: Proximity check between all pairs ---
        close_pairs = self._find_close_pairs(persons)

        # --- Step 5: Combine proximity + motion → severity & predictions ---
        predictions = []
        max_severity = "NORMAL"
        seen_pairs = set()

        for (idx_a, idx_b, pixel_dist, threshold) in close_pairs:
            pa, pb = persons[idx_a], persons[idx_b]
            max_motion = max(pa["motion_score"], pb["motion_score"])
            either_raised = pa["raised_arms"] or pb["raised_arms"]

            # Original rule: wrist speed of either person
            level, confidence, cues = 0, 0.0, []
            if max_motion >= self.WRIST_VEL_FIGHTING:
                level, confidence, cues = 2, min(0.95, 0.70 + max_motion * 5), ["wrist_speed"]
            elif max_motion >= self.WRIST_VEL_AGGRESSIVE or (either_raised and max_motion >= 0.038):
                level, confidence, cues = 1, min(0.85, 0.50 + max_motion * 5), ["wrist_speed"]

            # Added body cues (kicks, headbutts, shoves, knock-downs, attacks on a downed person)
            cue_level, cue_conf, cue_names, cue_values = self._pair_cues(pa["track_id"], pb["track_id"], now)
            if cue_level > level or (cue_level == level and cue_conf > confidence):
                level, confidence = cue_level, cue_conf
            if cue_level:
                cues = cues + cue_names

            if level == 0:
                # Close together but no significant motion — just standing near
                continue
            pred_label, pred_id = ("fighting", 2) if level == 2 else ("aggressive_stance", 1)

            # Update max severity
            if pred_label == "fighting":
                max_severity = "ACTIVE_FIGHT"
            elif pred_label == "aggressive_stance" and max_severity != "ACTIVE_FIGHT":
                max_severity = "AGGRESSIVE_STANCE"

            # Emit one prediction per involved person (avoid duplicates)
            for person in (pa, pb):
                tid = person["track_id"]
                if tid in seen_pairs:
                    continue
                seen_pairs.add(tid)

                predictions.append({
                    "track_id": tid,
                    "prediction": pred_label,
                    "prediction_id": pred_id,
                    "confidence": round(confidence, 3),
                    "proximity_px": round(pixel_dist, 1),
                    "threshold_px": round(threshold, 1),
                    "motion_score": round(max_motion, 4),
                    "cues": cues,
                    "cue_values": cue_values,
                })

        # Mark combatant status on persons
        combatant_tids = {p["track_id"] for p in predictions if p.get("prediction") in ["fighting", "aggressive_stance"]}
        for p in persons:
            p["is_combatant"] = p["track_id"] in combatant_tids

        result = {
            "persons_detected": len(persons),
            "persons": persons,
            "severity": max_severity,
            "severity_info": self.SEVERITY_LEVELS[max_severity],
            "predictions": predictions,
            "inference_ms": inference_ms,
            "model_loaded": True,
        }

        if annotate:
            result["annotated_image"] = self._annotate(
                image, results, predictions, max_severity
            )

        return result

    # ------------------------------------------------------------------
    #  Internal analysis helpers
    # ------------------------------------------------------------------

    def _compute_wrist_velocity(self, track_id: int) -> float:
        """Average wrist velocity over recent frames (normalized 0-1 coords).

        Uses the maximum of left/right wrist displacement per frame pair,
        averaged over the last MIN_HISTORY_FRAMES frames.
        """
        buf = self.keypoint_buffers.get(track_id, [])
        if len(buf) < self.MIN_HISTORY_FRAMES:
            return 0.0

        recent = buf[-self.MIN_HISTORY_FRAMES:]
        velocities = []
        for i in range(1, len(recent)):
            prev, curr = recent[i - 1], recent[i]
            lw_vel = float(np.linalg.norm(curr[self.L_WRIST] - prev[self.L_WRIST]))
            rw_vel = float(np.linalg.norm(curr[self.R_WRIST] - prev[self.R_WRIST]))
            velocities.append(max(lw_vel, rw_vel))

        return float(np.mean(velocities)) if velocities else 0.0

    def _check_raised_arms(self, kps_norm: np.ndarray, confs: np.ndarray) -> bool:
        """Check if either wrist is above the corresponding shoulder.

        In image coordinates, "above" means a smaller y value.
        This is a strong indicator of an aggressive/fighting posture
        (raised fists, overhead swings).
        """
        if confs[self.L_WRIST] < 0.3 and confs[self.R_WRIST] < 0.3:
            return False

        left_raised = (
            confs[self.L_WRIST] > 0.3
            and confs[self.L_SHOULDER] > 0.3
            and kps_norm[self.L_WRIST][1] < kps_norm[self.L_SHOULDER][1]
        )
        right_raised = (
            confs[self.R_WRIST] > 0.3
            and confs[self.R_SHOULDER] > 0.3
            and kps_norm[self.R_WRIST][1] < kps_norm[self.R_SHOULDER][1]
        )
        return left_raised or right_raised

    def _find_close_pairs(self, persons: list) -> list:
        """Find all pairs of persons within arm's reach of each other.

        Uses the average bounding-box height of each pair as a scale
        reference: if two people's centers are closer than
        PROXIMITY_RATIO × avg_height, they are "within arm's reach".
        """
        close_pairs = []
        for i, j in itertools.combinations(range(len(persons)), 2):
            a_bbox = persons[i]["bbox"]
            b_bbox = persons[j]["bbox"]

            # Center of each bounding box
            a_cx = (a_bbox[0] + a_bbox[2]) / 2
            a_cy = (a_bbox[1] + a_bbox[3]) / 2
            b_cx = (b_bbox[0] + b_bbox[2]) / 2
            b_cy = (b_bbox[1] + b_bbox[3]) / 2

            pixel_dist = ((a_cx - b_cx) ** 2 + (a_cy - b_cy) ** 2) ** 0.5

            # Body size (longer box side) as the real-world scale: equals the
            # height of a standing person and still works for someone lying down.
            a_h = max(a_bbox[3] - a_bbox[1], a_bbox[2] - a_bbox[0])
            b_h = max(b_bbox[3] - b_bbox[1], b_bbox[2] - b_bbox[0])
            avg_h = (a_h + b_h) / 2
            if avg_h <= 0:
                continue

            threshold_px = avg_h * self.PROXIMITY_RATIO

            # Physical contact check via bounding box overlap
            inter_w = max(0.0, min(a_bbox[2], b_bbox[2]) - max(a_bbox[0], b_bbox[0]))
            inter_h = max(0.0, min(a_bbox[3], b_bbox[3]) - max(a_bbox[1], b_bbox[1]))
            inter_area = inter_w * inter_h
            area_a = (a_bbox[2] - a_bbox[0]) * (a_bbox[3] - a_bbox[1])
            area_b = (b_bbox[2] - b_bbox[0]) * (b_bbox[3] - b_bbox[1])
            union = area_a + area_b - inter_area
            contact_iou = (inter_area / union) if union > 0 else 0.0

            if pixel_dist < threshold_px or contact_iou > 0.05:
                close_pairs.append((i, j, pixel_dist, threshold_px))

        return close_pairs

    # ------------------------------------------------------------------
    #  Body cues (torso lengths per second, real timestamps)
    # ------------------------------------------------------------------

    def _body_frame(self, xy: np.ndarray, confs: np.ndarray, bbox) -> Dict[str, Any]:
        """Torso length, hip centre and torso angle for one pose."""
        ok = confs > self.KP_CONF
        shoulders = [i for i in (self.L_SHOULDER, self.R_SHOULDER) if ok[i]]
        hips = [i for i in (self.L_HIP, self.R_HIP) if ok[i]]
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if shoulders and hips:
            s = xy[shoulders].mean(axis=0)
            hp = xy[hips].mean(axis=0)
            v = s - hp
            torso = float(np.linalg.norm(v))
            if torso > 1.0:
                # 0 deg = upright, 90 deg = lying (image y grows downward)
                angle = math.degrees(math.atan2(abs(float(v[0])), -float(v[1])))
                return {"torso": torso, "hip": hp, "angle": angle}
        centre = np.array([(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2], dtype=np.float32)
        angle = 90.0 if bw > bh * 1.2 else (0.0 if bh > bw * 1.2 else None)
        return {"torso": max(1.0, max(bw, bh) * self.cues.torso_to_body), "hip": centre, "angle": angle}

    def _record_pose(self, track_id: int, t: float, xy: np.ndarray, confs: np.ndarray, bbox) -> Dict[str, Any]:
        c = self.cues
        hist = self._pose_history.setdefault(track_id, deque(maxlen=256))
        if hist and t <= hist[-1]["t"]:
            hist.clear()  # timestamps restarted (new clip)
        frame = self._body_frame(xy, confs, bbox)
        hist.append({"t": t, "xy": xy.copy(), "conf": confs.copy(), **frame})
        while hist and t - hist[0]["t"] > c.history_sec:
            hist.popleft()

        angle = frame["angle"]
        fallen = angle is not None and angle >= c.fallen_angle
        if fallen:
            recent = [s for s in hist if t - s["t"] <= c.fall_window_sec]
            was_upright = any(s["angle"] is not None and s["angle"] <= c.upright_angle for s in recent)
            if was_upright:
                self._last_fall[track_id] = t
        fell_recently = track_id in self._last_fall and 0 <= t - self._last_fall[track_id] <= c.fall_memory_sec
        return {"fallen": fallen, "fell_recently": fell_recently}

    def _spaced(self, hist, now: float) -> List[Dict[str, Any]]:
        """Samples inside the cue window, at least min_step_sec apart (newest kept)."""
        c = self.cues
        out = []
        for s in reversed(hist):
            if now - s["t"] > c.cue_window_sec:
                break
            if not out or out[-1]["t"] - s["t"] >= c.min_step_sec:
                out.append(s)
        return out[::-1]

    def _steps(self, samples):
        """Consecutive sample pairs usable as one movement (no gaps, no tracking swaps)."""
        c = self.cues
        for s0, s1 in zip(samples, samples[1:]):
            dt = s1["t"] - s0["t"]
            torso = (s0["torso"] + s1["torso"]) / 2
            if dt <= 0 or dt > c.max_step_sec:
                continue
            if np.linalg.norm(s1["hip"] - s0["hip"]) / torso > c.max_step_torso:
                continue
            yield s0, s1, dt, torso

    def _directed_strike(self, attacker, target_point: np.ndarray) -> float:
        """Fastest hand/foot/head movement toward the target, relative to the attacker's hips."""
        c = self.cues
        best = 0.0
        limbs = (self.L_WRIST, self.R_WRIST, self.NOSE)
        feet = (self.L_ANKLE, self.R_ANKLE)
        for s0, s1, dt, torso in self._steps(attacker):
            to_target = target_point - s1["hip"]
            norm = float(np.linalg.norm(to_target))
            if norm < 1e-6:
                continue
            u = to_target / norm
            hip_speed = float(np.linalg.norm(s1["hip"] - s0["hip"])) / dt / torso
            candidates = limbs + (feet if hip_speed < c.planted_hip_speed else ())
            for k in candidates:
                if s0["conf"][k] <= self.KP_CONF or s1["conf"][k] <= self.KP_CONF:
                    continue
                rel_v = ((s1["xy"][k] - s1["hip"]) - (s0["xy"][k] - s0["hip"])) / dt / torso
                best = max(best, float(np.dot(rel_v, u)))
        return best

    def _torso_accel(self, samples) -> float:
        steps = list(self._steps(samples))
        best = 0.0
        for (a0, a1, dta, ta), (b0, b1, dtb, tb) in zip(steps, steps[1:]):
            if a1 is not b0:
                continue
            v1 = (a1["hip"] - a0["hip"]) / dta / ta
            v2 = (b1["hip"] - b0["hip"]) / dtb / tb
            best = max(best, float(np.linalg.norm(v2 - v1)) / ((dta + dtb) / 2))
        return best

    def _approach(self, hist_a, hist_b, now: float) -> float:
        """Fastest closing speed of the pair (torso lengths / s)."""
        by_t = {s["t"]: s for s in hist_b}
        common = [s for s in hist_a if s["t"] in by_t]
        best = 0.0
        for s0, s1, dt, torso in self._steps(self._spaced(common, now)):
            b0, b1 = by_t[s0["t"]], by_t[s1["t"]]
            d0 = float(np.linalg.norm(s0["hip"] - b0["hip"]))
            d1 = float(np.linalg.norm(s1["hip"] - b1["hip"]))
            scale = (torso + (b0["torso"] + b1["torso"]) / 2) / 2
            best = max(best, (d0 - d1) / dt / scale)
        return best

    def _pair_cues(self, tid_a: int, tid_b: int, now: float):
        """Returns (level 0/1/2, confidence, cue names, cue values) for one close pair."""
        c = self.cues
        hist_a, hist_b = self._pose_history.get(tid_a), self._pose_history.get(tid_b)
        if not hist_a or not hist_b:
            return 0, 0.0, [], {}
        sa, sb = self._spaced(hist_a, now), self._spaced(hist_b, now)
        cur_a, cur_b = hist_a[-1], hist_b[-1]

        strike_ab = self._directed_strike(sa, cur_b["hip"])
        strike_ba = self._directed_strike(sb, cur_a["hip"])
        strike = max(strike_ab, strike_ba)
        accel_a, accel_b = self._torso_accel(sa), self._torso_accel(sb)
        approach = self._approach(hist_a, hist_b, now)
        fell_a = tid_a in self._last_fall and 0 <= now - self._last_fall[tid_a] <= c.fall_memory_sec
        fell_b = tid_b in self._last_fall and 0 <= now - self._last_fall[tid_b] <= c.fall_memory_sec
        down_a = cur_a["angle"] is not None and cur_a["angle"] >= c.fallen_angle
        down_b = cur_b["angle"] is not None and cur_b["angle"] >= c.fallen_angle
        up_a = cur_a["angle"] is not None and cur_a["angle"] <= c.upright_angle
        up_b = cur_b["angle"] is not None and cur_b["angle"] <= c.upright_angle

        half = c.strike_aggressive / 2
        names, level = [], 0
        if strike >= c.strike_fighting:
            names.append("strike"); level = 2
        elif strike >= c.strike_aggressive:
            names.append("strike"); level = max(level, 1)
        # Knocked down: one fell while the other moved at them
        if (fell_b and strike_ab >= half) or (fell_a and strike_ba >= half):
            names.append("knocked_down"); level = 2
        # Attack on a person already down: the standing one strikes at them
        if (down_b and up_a and strike_ab >= c.strike_aggressive) or (down_a and up_b and strike_ba >= c.strike_aggressive):
            names.append("attack_on_downed"); level = 2
        # Shove / tackle: sudden torso acceleration while the other closed in or reached out
        if (accel_b >= c.shove_accel and (strike_ab >= half or approach >= c.approach_speed)) or \
           (accel_a >= c.shove_accel and (strike_ba >= half or approach >= c.approach_speed)):
            names.append("shove"); level = max(level, 1)

        values = {"strike": round(strike, 2), "accel": round(max(accel_a, accel_b), 2),
                  "approach": round(approach, 2)}
        if level == 0:
            return 0, 0.0, [], values
        strength = strike / c.strike_fighting
        if level == 2:
            conf = 0.75 + 0.20 * min(1.0, strength / 2)
        else:
            conf = 0.55 + 0.25 * min(1.0, strength)
        return level, round(conf, 3), names, values

    # ------------------------------------------------------------------
    #  Annotation / drawing
    # ------------------------------------------------------------------

    def _annotate(self, image, pose_results, predictions, severity):
        """Draw skeletons, prediction labels, and severity banner."""
        annotated = image.copy()
        info = self.SEVERITY_LEVELS[severity]

        # Draw skeletons
        if pose_results[0].keypoints is not None:
            kps_data = pose_results[0].keypoints.data.cpu().numpy()
            skeleton_pairs = [
                (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
                (5, 11), (6, 12), (11, 12), (11, 13), (13, 15),
                (12, 14), (14, 16),
            ]
            for person_kps in kps_data:
                for (a, b) in skeleton_pairs:
                    if person_kps[a][2] > 0.3 and person_kps[b][2] > 0.3:
                        pt1 = (int(person_kps[a][0]), int(person_kps[a][1]))
                        pt2 = (int(person_kps[b][0]), int(person_kps[b][1]))
                        cv2.line(annotated, pt1, pt2, info["color"], 2)

                for kp in person_kps:
                    if kp[2] > 0.3:
                        cv2.circle(
                            annotated, (int(kp[0]), int(kp[1])), 3,
                            (255, 255, 255), -1,
                        )

        # Draw prediction labels
        for pred in predictions:
            label = (
                f"Person {pred['track_id']}: "
                f"{pred['prediction'].upper()} "
                f"({pred['confidence'] * 100:.0f}%)"
            )
            y_pos = 50 + pred["track_id"] * 25
            color = (0, 0, 255) if pred["prediction_id"] == 2 else (0, 140, 255)
            cv2.putText(
                annotated, label, (10, y_pos),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,
            )

        # Severity banner
        cv2.rectangle(
            annotated, (0, 0), (annotated.shape[1], 30), info["color"], -1,
        )
        cv2.putText(
            annotated, f"FIGHT ALERT: {info['label']}", (10, 22),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
        )

        return annotated

    def reset_buffers(self):
        """Clear all per-person history (call between videos/clips)."""
        self.reset()
