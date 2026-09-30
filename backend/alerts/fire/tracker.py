"""
alerts/fire/tracker.py — Tells real fire/smoke apart from look-alikes over time.

The fire model looks at one frame at a time, so a lamp, a sunset reflection or
an orange sign can look exactly like a flame. Over a few seconds they behave
differently:

  - real flames flicker: the brightness inside the box keeps changing, more
    than the brightness around it does;
  - real smoke grows or drifts upward;
  - lamps, signs, reflections and haze stay put and stay the same.

This tracker follows each fire/smoke box of one camera over time and labels it:

  static      proven not to flicker, grow or move -> a fixture, not a fire
  growing     smoke whose area grows or whose top edge rises (early warning)
  persistent  a real (non-static) fire seen for a while (an established fire zone)

Every test is relative (inside vs. around the box, a box vs. its own size,
later vs. earlier), so it works for any resolution, distance or frame rate.
Detections are never judged before enough history exists, so the first frames
of a real fire are reported immediately, exactly as before.

Places proven static are remembered per camera (wall-clock TTL), so a lamp that
was already proven static is not re-reported at the start of the next clip.
A remembered place is forgotten as soon as something there behaves like fire.
"""
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class FireScenePolicy:
    # How much history is used, and how much is needed before judging a box.
    window_sec: float = 6.0
    judge_after_sec: float = 3.0
    min_samples: int = 5
    # A track ends when its box has not been seen for this long.
    track_gap_sec: float = 2.0
    match_iou: float = 0.2
    # "Changing": mean brightness change inside the box, relative to its brightness.
    min_relative_change: float = 0.03
    # "Flickering": change inside the box vs. change in a ring around it.
    min_flicker_ratio: float = 1.5
    # "Not moving": centre shift and area spread relative to the box's own size.
    static_shift_frac: float = 0.15
    static_area_spread: float = 0.15
    # Smoke "growing": later area / earlier area, or top-edge rise / box height.
    smoke_growth_ratio: float = 1.25
    smoke_rise_frac: float = 0.15
    # A non-static fire seen this long is an established fire zone.
    persist_sec: float = 3.0
    # Remembered static places.
    memory_iou: float = 0.5
    memory_ttl_sec: float = 6 * 3600.0


def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _bbox_list(bbox) -> List[float]:
    if isinstance(bbox, dict):
        return [float(bbox["x1"]), float(bbox["y1"]), float(bbox["x2"]), float(bbox["y2"])]
    return [float(v) for v in bbox[:4]]


class FireSceneTracker:
    """Per-camera fire/smoke tracker. Call update() on every scanned frame."""

    def __init__(self, policy: Optional[FireScenePolicy] = None):
        self.policy = policy or FireScenePolicy()
        self._prev_gray: Optional[np.ndarray] = None
        self._tracks: Dict[int, Dict[str, Any]] = {}
        self._next_id = 0
        self._static_final: Dict[int, bool] = {}   # every track of this stream -> last verdict
        self._memory: List[Dict[str, Any]] = []    # places proven static (survive reset_stream)

    # ------------------------------------------------------------------
    def reset_stream(self, clear_memory: bool = False):
        """Forget tracks (new clip/video). Keep static places unless asked."""
        self._prev_gray = None
        self._tracks.clear()
        self._static_final.clear()
        self._next_id = 0
        if clear_memory:
            self._memory.clear()

    def static_track_ids(self) -> set:
        """Tracks whose latest verdict is 'static' (for filtering earlier frames)."""
        return {tid for tid, is_static in self._static_final.items() if is_static}

    # ------------------------------------------------------------------
    def update(self, gray: np.ndarray, detections: List[Dict[str, Any]], t: float) -> List[Dict[str, Any]]:
        """Annotate fire/smoke detections of this frame in place and return them."""
        p = self.policy
        prev = self._prev_gray if (self._prev_gray is not None and self._prev_gray.shape == gray.shape) else None

        # Close tracks that have not been seen for a while.
        for tid in [k for k, tr in self._tracks.items() if t - tr["last_t"] > p.track_gap_sec or t < tr["last_t"]]:
            self._tracks.pop(tid, None)

        used = set()
        for det in detections:
            cls = str(det.get("class_name", "fire")).lower()
            box = _bbox_list(det["bbox"])
            tid = self._match(cls, box, used)
            if tid is None:
                tid = self._next_id
                self._next_id += 1
                self._tracks[tid] = {"cls": cls, "first_t": t, "last_t": t, "samples": deque()}
            used.add(tid)
            tr = self._tracks[tid]
            tr["last_t"] = t
            change, ratio = self._change_stats(prev, gray, box)
            tr["samples"].append({"t": t, "box": box, "change": change, "ratio": ratio})
            while tr["samples"] and t - tr["samples"][0]["t"] > p.window_sec:
                tr["samples"].popleft()

            verdict = self._judge(tr)
            if verdict["judged"]:
                self._remember(cls, box, verdict["static"])
            elif self._in_memory(cls, box):
                verdict["static"] = True
                verdict["from_memory"] = True
            self._static_final[tid] = verdict["static"]

            det.update({
                "track_id": tid,
                "static": verdict["static"],
                "growing": verdict["growing"],
                "persistent": verdict["persistent"],
                "flicker_ratio": verdict["flicker_ratio"],
                "relative_change": verdict["relative_change"],
            })

        self._prev_gray = gray
        return detections

    # ------------------------------------------------------------------
    def _match(self, cls: str, box: List[float], used: set) -> Optional[int]:
        best, best_iou = None, 0.0
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        for tid, tr in self._tracks.items():
            if tid in used or tr["cls"] != cls or not tr["samples"]:
                continue
            last = tr["samples"][-1]["box"]
            iou = _iou(box, last)
            # Smoke changes shape as it grows, so also accept a centre inside the last box.
            centre_inside = last[0] <= cx <= last[2] and last[1] <= cy <= last[3]
            score = iou if iou >= self.policy.match_iou else (self.policy.match_iou if centre_inside else 0.0)
            if score > best_iou:
                best, best_iou = tid, score
        return best

    @staticmethod
    def _change_stats(prev: Optional[np.ndarray], gray: np.ndarray, box: List[float]) -> Tuple[Optional[float], Optional[float]]:
        """(change inside relative to brightness, change inside / change in the ring around)."""
        if prev is None:
            return None, None
        h, w = gray.shape[:2]
        x1, y1 = max(0, int(box[0])), max(0, int(box[1]))
        x2, y2 = min(w, int(box[2])), min(h, int(box[3]))
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None, None
        bw, bh = x2 - x1, y2 - y1
        ex1, ey1 = max(0, x1 - bw // 2), max(0, y1 - bh // 2)
        ex2, ey2 = min(w, x2 + bw // 2), min(h, y2 + bh // 2)

        diff = cv2.absdiff(gray[ey1:ey2, ex1:ex2], prev[ey1:ey2, ex1:ex2]).astype(np.float32)
        inner = diff[y1 - ey1:y2 - ey1, x1 - ex1:x2 - ex1]
        inner_mean = float(inner.mean())
        ring_count = diff.size - inner.size
        ring_mean = float((diff.sum() - inner.sum()) / ring_count) if ring_count > 0 else inner_mean
        brightness = float(gray[y1:y2, x1:x2].mean())
        # +1 is one grey level: keeps two near-zero values from forming a big ratio.
        return inner_mean / (brightness + 1.0), (inner_mean + 1.0) / (ring_mean + 1.0)

    def _judge(self, tr: Dict[str, Any]) -> Dict[str, Any]:
        p = self.policy
        samples = list(tr["samples"])
        out = {"judged": False, "static": False, "growing": False, "persistent": False,
               "flicker_ratio": None, "relative_change": None}
        span = samples[-1]["t"] - samples[0]["t"] if samples else 0.0
        stats = [s for s in samples if s["change"] is not None]
        if stats:
            out["relative_change"] = round(float(np.median([s["change"] for s in stats])), 4)
            out["flicker_ratio"] = round(float(np.median([s["ratio"] for s in stats])), 3)
        if span < p.judge_after_sec or len(samples) < p.min_samples or len(stats) < p.min_samples - 1:
            return out
        out["judged"] = True

        boxes = np.array([s["box"] for s in samples], dtype=np.float32)
        widths, heights = boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1]
        areas = np.maximum(widths * heights, 1.0)
        size = float(np.sqrt(np.median(areas)))
        centres = np.stack([(boxes[:, 0] + boxes[:, 2]) / 2, (boxes[:, 1] + boxes[:, 3]) / 2], axis=1)
        shift = float(np.linalg.norm(centres.max(axis=0) - centres.min(axis=0))) / max(size, 1.0)
        area_spread = float(np.std(areas) / np.mean(areas))

        third = max(1, len(samples) // 3)
        growth = float(np.mean(areas[-third:]) / np.mean(areas[:third]))
        rise = float(np.mean(boxes[:third, 1]) - np.mean(boxes[-third:, 1])) / max(float(np.median(heights)), 1.0)

        changing = out["relative_change"] >= p.min_relative_change or out["flicker_ratio"] >= p.min_flicker_ratio
        still = shift < p.static_shift_frac and area_spread < p.static_area_spread

        if tr["cls"] == "smoke":
            out["growing"] = growth >= p.smoke_growth_ratio or rise >= p.smoke_rise_frac
            out["static"] = still and not changing and not out["growing"]
        else:
            out["static"] = still and not changing
            out["persistent"] = (not out["static"]) and (tr["last_t"] - tr["first_t"]) >= p.persist_sec
        return out

    # ---- remembered static places ------------------------------------
    def _remember(self, cls: str, box: List[float], is_static: bool):
        now = time.time()
        self._memory = [m for m in self._memory if now - m["seen"] < self.policy.memory_ttl_sec]
        hits = [m for m in self._memory if m["cls"] == cls and _iou(m["box"], box) >= self.policy.memory_iou]
        if is_static:
            if hits:
                hits[0].update(box=box, seen=now)
            else:
                self._memory.append({"cls": cls, "box": box, "seen": now})
        elif hits:
            # Something at a remembered place now behaves like fire: stop trusting the memory.
            self._memory = [m for m in self._memory if m not in hits]

    def _in_memory(self, cls: str, box: List[float]) -> bool:
        now = time.time()
        return any(m["cls"] == cls and now - m["seen"] < self.policy.memory_ttl_sec
                   and _iou(m["box"], box) >= self.policy.memory_iou for m in self._memory)
