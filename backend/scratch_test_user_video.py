import cv2
import os
from services.threat_engine import ThreatEngine

te = ThreatEngine()
video_path = r"C:\Vigilinx\videos\WhatsApp Video 2026-09-18 at 5.11.26 PM.mp4"
if not os.path.exists(video_path):
    print("Video does not exist:", video_path)
    exit(1)

cap = cv2.VideoCapture(video_path)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS) or 25
print(f"Video: {total} frames, {fps} fps")

idx = 0
threat_summary = {}
while True:
    ret, frame = cap.read()
    if not ret:
        break
    if idx % 5 == 0:
        res = te.scan_frame(frame, annotate=False)
        if res["has_threat"]:
            for t in res["threats"]:
                key = f"{t['type']}: {t['label']}"
                threat_summary[key] = threat_summary.get(key, 0) + 1
                if threat_summary[key] <= 3:
                    print(f"Frame {idx}: {key} (conf={t['confidence']}, bbox={t.get('bbox')})")
    idx += 1
cap.release()
print("Final threat summary:", threat_summary)
