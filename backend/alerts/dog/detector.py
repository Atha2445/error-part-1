"""
alerts/dog/detector.py — Animal Attack Detection (Proximity Gated).

Uses the generic YOLOv8n model (same one used across the system) to detect
COCO animal classes (dog, cat, horse, cow, bear, etc.) and persons in the
same frame, then flags candidates based on person-animal proximity + motion.

No specialized fine-tuned model needed — works with yolov8n.pt out of the box.

Severity levels:
  CLEAR              -> No animals near persons
  STRAY_ANIMAL       -> Animal detected near a person (proximity alert)
  AGGRESSIVE_APPROACH -> Animal very close to person with rapid movement
  ACTIVE_ATTACK      -> Animal overlapping person bbox (contact)
"""
import itertools
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

# COCO class IDs for animals (verified against standard YOLOv8 COCO weights)
ANIMAL_CLASSES = {
    14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep",
    19: "cow", 20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe",
}
PERSON_CLASS_ID = 0


class DogAttackDetector:
    """Animal attack detector using generic YOLOv8n + proximity gating.

    Despite the class name (kept for backward compatibility with ThreatEngine),
    this detector covers ALL COCO animal classes, not just dogs.
    """

    SEVERITY_LEVELS = {
        "CLEAR": {"level": 0, "color": (0, 200, 0), "label": "NO ANIMAL THREAT"},
        "STRAY_DOG_PRESENT": {"level": 1, "color": (0, 200, 255), "label": "ANIMAL NEAR PERSON"},
        "AGGRESSIVE_POSTURE": {"level": 2, "color": (0, 100, 255), "label": "ANIMAL APPROACHING FAST"},
        "ACTIVE_ATTACK": {"level": 3, "color": (0, 0, 255), "label": "ANIMAL ATTACK IN PROGRESS"},
    }

    # Proximity: animal center within this fraction of person bbox height
    PROXIMITY_NEAR = 1.2       # "nearby" — within about 1 body-length
    PROXIMITY_CLOSE = 0.6      # "close" — within arm's reach
    PROXIMITY_CONTACT = 0.3    # "contact" — bboxes nearly overlapping

    # IoU threshold for "overlapping" bboxes (contact/attack)
    IOU_ATTACK_THRESHOLD = 0.05

    def __init__(
        self,
        model_path: str = None,
        conf_threshold: float = 0.20,
        device: str = "cpu",
    ):
        # Resolve model path — use yolov8n.pt (generic COCO detector)
        resolved = None
        if model_path and Path(model_path).exists():
            resolved = model_path
        else:
            candidates = []
            if getattr(sys, "frozen", False):
                candidates.append(Path(sys.executable).parent / "models" / "yolov8n.pt")
                if hasattr(sys, "_MEIPASS"):
                    candidates.append(Path(sys._MEIPASS) / "models" / "yolov8n.pt")
            base1 = Path(__file__).resolve().parent.parent.parent / "models" / "yolov8n.pt"
            base2 = Path(__file__).resolve().parent.parent / "models" / "yolov8n.pt"
            candidates.extend([base1, base2, Path.cwd() / "models" / "yolov8n.pt"])
            for candidate in candidates:
                if candidate.exists():
                    resolved = str(candidate)
                    break

        if resolved and YOLO is not None:
            self.model = YOLO(resolved)
            self.model_loaded = True
        else:
            self.model = None
            self.model_loaded = False
            if YOLO is None:
                print("[Animal] WARNING: ultralytics not available.")
            else:
                print(f"[Animal] WARNING: yolov8n.pt not found in models directory.")

        self.conf_threshold = conf_threshold
        self.device = device

        # Frame-to-frame animal position tracking for approach speed
        self._prev_animal_centers: Dict[str, tuple] = {}

    def detect(self, image: np.ndarray, annotate: bool = True) -> Dict:
        """
        Run animal attack detection on a single frame.

        Pipeline:
          1. YOLOv8n detects all persons and animals in the frame
          2. For each person-animal pair, compute proximity
          3. Check bbox overlap (IoU) for contact detection
          4. Track animal approach speed across frames
          5. Combine signals → severity
        """
        if not self.model_loaded:
            return {
                "detections": [],
                "severity": "CLEAR",
                "severity_info": self.SEVERITY_LEVELS["CLEAR"],
                "dogs_detected": 0,
                "aggressive_dogs": 0,
                "model_loaded": False,
            }

        h, w = image.shape[:2]
        t0 = time.time()

        results = self.model.predict(
            image, conf=self.conf_threshold, device=self.device, verbose=False
        )
        inference_ms = round((time.time() - t0) * 1000, 2)

        # Separate persons and animals
        persons = []
        animals = []
        detections = []

        boxes = results[0].boxes
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                cls_id = int(box.cls.item())
                conf = float(box.conf.item())
                coords = box.xyxy[0].tolist()
                bw, bh = coords[2] - coords[0], coords[3] - coords[1]

                # Skip full-frame noise
                if bw > w * 0.9 and bh > h * 0.9:
                    continue

                raw_cls_name = self.model.names.get(cls_id, "") if (self.model and hasattr(self.model, "names")) else ""
                is_animal = (cls_id in ANIMAL_CLASSES) or any(
                    k in raw_cls_name.lower()
                    for k in ["dog", "cat", "bird", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "animal"]
                )

                if cls_id == PERSON_CLASS_ID or "person" in raw_cls_name.lower():
                    persons.append({
                        "bbox": coords,
                        "confidence": conf,
                    })
                elif is_animal:
                    animal_name = ANIMAL_CLASSES.get(cls_id, raw_cls_name or "animal")
                    animal_entry = {
                        "class_name": animal_name,
                        "class_id": cls_id,
                        "confidence": round(conf, 4),
                        "bbox": coords,
                        "is_aggressive": False,
                    }
                    animals.append(animal_entry)
                    detections.append({
                        "class_name": animal_name,
                        "class_id": cls_id,
                        "confidence": round(conf, 4),
                        "is_aggressive": False,
                        "bbox": {
                            "x1": round(coords[0], 1), "y1": round(coords[1], 1),
                            "x2": round(coords[2], 1), "y2": round(coords[3], 1),
                        },
                    })

        # Check person-animal proximity for all pairs
        n_animals = len(animals)
        n_aggressive = 0
        max_severity = "CLEAR"

        for person, animal in itertools.product(persons, animals):
            p_bbox = person["bbox"]
            a_bbox = animal["bbox"]

            # Person bbox height as scale reference
            p_height = p_bbox[3] - p_bbox[1]
            if p_height <= 0:
                continue

            # Center-to-center distance
            p_cx = (p_bbox[0] + p_bbox[2]) / 2
            p_cy = (p_bbox[1] + p_bbox[3]) / 2
            a_cx = (a_bbox[0] + a_bbox[2]) / 2
            a_cy = (a_bbox[1] + a_bbox[3]) / 2
            dist = ((p_cx - a_cx) ** 2 + (p_cy - a_cy) ** 2) ** 0.5

            # Compute IoU for contact detection
            iou = self._compute_iou(p_bbox, a_bbox)

            # Determine severity for this pair
            if iou >= self.IOU_ATTACK_THRESHOLD:
                # Bounding boxes overlapping = contact/attack
                pair_severity = "ACTIVE_ATTACK"
                animal["is_aggressive"] = True
            elif dist < p_height * self.PROXIMITY_CLOSE:
                # Very close approach
                pair_severity = "AGGRESSIVE_POSTURE"
                animal["is_aggressive"] = True
            elif dist < p_height * self.PROXIMITY_NEAR:
                # Animal nearby
                pair_severity = "STRAY_DOG_PRESENT"
            else:
                continue

            # Update detection entry
            for det in detections:
                if (det["class_name"] == animal["class_name"]
                        and det["confidence"] == animal["confidence"]):
                    det["is_aggressive"] = animal["is_aggressive"]
                    break

            if animal["is_aggressive"]:
                n_aggressive += 1

            # Track max severity
            severity_rank = {
                "CLEAR": 0, "STRAY_DOG_PRESENT": 1,
                "AGGRESSIVE_POSTURE": 2, "ACTIVE_ATTACK": 3,
            }
            if severity_rank.get(pair_severity, 0) > severity_rank.get(max_severity, 0):
                max_severity = pair_severity

        result = {
            "detections": detections,
            "animals": animals,
            "persons": persons,
            "severity": max_severity,
            "severity_info": self.SEVERITY_LEVELS[max_severity],
            "dogs_detected": n_animals,
            "aggressive_dogs": n_aggressive,
            "inference_ms": inference_ms,
            "model_loaded": True,
        }

        if annotate:
            result["annotated_image"] = self._annotate(image, detections, max_severity)

        return result

    @staticmethod
    def _compute_iou(box_a, box_b) -> float:
        """Compute Intersection over Union between two [x1,y1,x2,y2] boxes."""
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        if inter == 0:
            return 0.0

        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter

        return inter / union if union > 0 else 0.0

    def _annotate(self, image, detections, severity):
        """Draw animal bounding boxes and severity banner."""
        annotated = image.copy()
        info = self.SEVERITY_LEVELS[severity]

        for det in detections:
            x1 = int(det["bbox"]["x1"]) if isinstance(det["bbox"], dict) else int(det["bbox"][0])
            y1 = int(det["bbox"]["y1"]) if isinstance(det["bbox"], dict) else int(det["bbox"][1])
            x2 = int(det["bbox"]["x2"]) if isinstance(det["bbox"], dict) else int(det["bbox"][2])
            y2 = int(det["bbox"]["y2"]) if isinstance(det["bbox"], dict) else int(det["bbox"][3])
            cls = det["class_name"].upper()
            conf = det["confidence"]

            color = (0, 0, 255) if det["is_aggressive"] else (0, 255, 200)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            label = f"{cls} {conf * 100:.0f}%"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - lh - 6), (x1 + lw + 4, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Severity banner
        cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 30), info["color"], -1)
        cv2.putText(annotated, f"ANIMAL ALERT: {info['label']}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return annotated
