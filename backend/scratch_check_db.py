import sqlite3
conn = sqlite3.connect('C:/Vigilinx/vigilinx.db')
c = conn.cursor()
c.execute("SELECT id, video_path, total_analyzed, suspicious_frames, normal_frames, risk_level, recommendation, ai_summary FROM video_verdicts WHERE video_path LIKE '%WhatsApp%'")
for row in c.fetchall():
    print("Verdict:", row)

c.execute("SELECT detected_action, COUNT(1) FROM detections WHERE video_path LIKE '%WhatsApp%' GROUP BY detected_action")
for row in c.fetchall():
    print("Action count:", row)
