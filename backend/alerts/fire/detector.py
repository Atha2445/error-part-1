"""
alerts/fire/detector.py — Fire & Smoke Detection Alert Module.

Wraps the fine-tuned YOLOv8 fire/smoke model with severity classification:
  SMOKE_ONLY       -> Early warning (smoke detected, no visible flame)
  SMALL_FIRE       -> Confirmed fire, small area (<15% of frame)
  LARGE_FIRE       -> Large fire (15-40% of frame)
  INFERNO          -> Critical (>40% of frame or multiple fire regions)
"""
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from ultralytics import YOLO


class FireSmokeDetector:
    SEVERITY_LEVELS = {
        "CLEAR": {"level": 0, "color": (0, 200, 0), "label": "ALL CLEAR"},
        "SMOKE_ONLY": {"level": 1, "color": (200, 200, 0), "label": "SMOKE DETECTED"},
        "SMALL_FIRE": {"level": 2, "color": (0, 140, 255), "label": "FIRE CONFIRMED (SMALL)"},
        "LARGE_FIRE": {"level": 3, "color": (0, 40, 255), "label": "LARGE FIRE"},
        "INFERNO": {"level": 4, "color": (0, 0, 255), "label": "CRITICAL - INFERNO"},
    }

    def __init__(
        self,
        model_path: str = None,
        conf_threshold: float = 0.18,
        device: str = "cpu",
        smoke_conf_threshold: float = 0.30,
    ):
        resolved = None
        if model_path and Path(model_path).exists():
            resolved = model_path
        else:
            candidates = []
            if getattr(sys, "frozen", False):
                candidates.append(Path(sys.executable).parent / "models" / "fire_smoke_detector_best.pt")
                if hasattr(sys, "_MEIPASS"):
                    candidates.append(Path(sys._MEIPASS) / "models" / "fire_smoke_detector_best.pt")
            base1 = Path(__file__).resolve().parent.parent.parent / "models" / "fire_smoke_detector_best.pt"
            base2 = Path(__file__).resolve().parent.parent / "models" / "fire_smoke_detector_best.pt"
            candidates.extend([base1, base2, Path.cwd() / "models" / "fire_smoke_detector_best.pt"])
            for candidate in candidates:
                if candidate.exists():
                    resolved = str(candidate)
                    break

        if resolved and Path(resolved).exists():
            self.model = YOLO(resolved)
            self.model_loaded = True
        else:
            self.model = None
            self.model_loaded = False
            print(f"[FireSmoke] WARNING: Weights not found at {model_path or resolved}")
            print(f"[FireSmoke] Run scripts/13_train_fire_smoke.py first.")

        # Separate floors per class: smoke is easily confused with fog, dust and
        # steam, so it needs more confidence than fire before it is reported.
        self.conf_threshold = conf_threshold
        self.smoke_conf_threshold = smoke_conf_threshold
        self.device = device
        self.class_names = {0: "smoke", 1: "fire"}

    def detect(self, image: np.ndarray, annotate: bool = True) -> Dict:
        """
        Run fire/smoke detection on a single image/frame.

        Returns:
            dict with keys: detections, severity, annotated_image (optional)
        """
        if not self.model_loaded:
            return {
                "detections": [],
                "severity": "CLEAR",
                "severity_info": self.SEVERITY_LEVELS["CLEAR"],
                "smoke_detected": False,
                "fire_detected": False,
                "fire_area_pct": 0.0,
                "model_loaded": False,
            }

        h, w = image.shape[:2]
        frame_area = h * w
        t0 = time.time()

        results = self.model.predict(
            image, conf=min(self.conf_threshold, self.smoke_conf_threshold),
            device=self.device, verbose=False
        )
        inference_ms = round((time.time() - t0) * 1000, 2)

        detections = []
        total_fire_area = 0
        total_smoke_area = 0
        has_fire = False
        has_smoke = False

        boxes = results[0].boxes
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                cls_id = int(box.cls.item())
                conf = float(box.conf.item())
                coords = box.xyxy[0].tolist()
                bw = coords[2] - coords[0]
                bh = coords[3] - coords[1]
                box_area = bw * bh
                area_pct = (box_area / frame_area) * 100

                cls_name = self.class_names.get(cls_id, f"class_{cls_id}")
                min_conf = self.smoke_conf_threshold if cls_name == "smoke" else self.conf_threshold
                if conf < min_conf:
                    continue

                if cls_name == "fire":
                    has_fire = True
                    total_fire_area += area_pct
                elif cls_name == "smoke":
                    has_smoke = True
                    total_smoke_area += area_pct

                detections.append({
                    "class_name": cls_name,
                    "class_id": cls_id,
                    "confidence": round(conf, 4),
                    "bbox": {
                        "x1": round(coords[0], 1), "y1": round(coords[1], 1),
                        "x2": round(coords[2], 1), "y2": round(coords[3], 1),
                    },
                    "area_percent": round(area_pct, 2),
                })

        # Determine severity
        severity = self._classify_severity(has_fire, has_smoke, total_fire_area, len(detections))

        result = {
            "detections": detections,
            "severity": severity,
            "severity_info": self.SEVERITY_LEVELS[severity],
            "smoke_detected": has_smoke,
            "fire_detected": has_fire,
            "fire_area_pct": round(total_fire_area, 2),
            "smoke_area_pct": round(total_smoke_area, 2),
            "inference_ms": inference_ms,
            "model_loaded": True,
        }

        if annotate:
            result["annotated_image"] = self._annotate(image, detections, severity)

        return result

    def _classify_severity(self, has_fire, has_smoke, fire_area, n_detections):
        if has_fire and fire_area > 40:
            return "INFERNO"
        if has_fire and fire_area > 15:
            return "LARGE_FIRE"
        if has_fire:
            return "SMALL_FIRE"
        if has_smoke:
            return "SMOKE_ONLY"
        return "CLEAR"

    def _annotate(self, image, detections, severity):
        annotated = image.copy()
        info = self.SEVERITY_LEVELS[severity]
        color = info["color"]

        for det in detections:
            x1 = int(det["bbox"]["x1"])
            y1 = int(det["bbox"]["y1"])
            x2 = int(det["bbox"]["x2"])
            y2 = int(det["bbox"]["y2"])
            cls = det["class_name"].upper()
            conf = det["confidence"]

            det_color = (0, 0, 255) if cls == "FIRE" else (0, 200, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), det_color, 2)

            label = f"{cls} {conf*100:.0f}%"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - lh - 6), (x1 + lw + 4, y1), det_color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Severity banner
        cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 30), color, -1)
        cv2.putText(annotated, f"FIRE ALERT: {info['label']}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return annotated
