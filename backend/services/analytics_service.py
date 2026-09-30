"""
services/analytics_service.py — Surveillance Intelligence & Data Aggregation Service.

Queries SQLite database (video_verdicts, detections, cctv_ips) to provide
analytical rollups, time-series incident trends, crowd flow statistics,
and CSV compliance reports.
"""
import io
import csv
import sqlite3
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger("vids.analytics_service")


class AnalyticsService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self) -> Optional[sqlite3.Connection]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("ALTER TABLE video_verdicts ADD COLUMN ai_summary TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            return conn
        except sqlite3.Error as e:
            logger.error(f"Error connecting to SQLite in AnalyticsService: {e}")
            return None

    def get_overview_kpis(self) -> Dict[str, Any]:
        """Returns top-level security and operational KPIs."""
        conn = self._get_connection()
        if not conn:
            return {
                "total_videos": 0,
                "threat_incidents": 0,
                "clear_videos": 0,
                "threat_rate_pct": 0.0,
                "avg_occupancy": 0,
                "total_cameras": 0,
                "active_cameras": 0,
                "vlm_accuracy_index": None,  # not measured (was a hard-coded 92.4)
            }

        try:
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total_videos,
                    SUM(CASE WHEN needs_attention = 1 THEN 1 ELSE 0 END) as threat_incidents
                FROM video_verdicts
            """).fetchone()

            total_vids = row["total_videos"] or 0
            threats = row["threat_incidents"] or 0
            clear_vids = max(0, total_vids - threats)
            threat_rate = round((threats / total_vids * 100), 1) if total_vids > 0 else 0.0

            occ_row = conn.execute("""
                SELECT AVG(occupancy_count) as avg_occ FROM detections WHERE occupancy_count > 0
            """).fetchone()
            avg_occ = round(float(occ_row["avg_occ"] or 0), 1) if occ_row else 0.0

            cam_row = conn.execute("""
                SELECT 
                    COUNT(*) as total_cams,
                    SUM(CASE WHEN status = 'active' OR status = 'online' THEN 1 ELSE 0 END) as active_cams
                FROM cctv_ips
            """).fetchone()
            total_cams = cam_row["total_cams"] or 0 if cam_row else 0
            active_cams = cam_row["active_cams"] or 0 if cam_row else 0

            return {
                "total_videos": total_vids,
                "threat_incidents": threats,
                "clear_videos": clear_vids,
                "threat_rate_pct": threat_rate,
                "avg_occupancy": avg_occ,
                "total_cameras": total_cams,
                "active_cameras": active_cams,
                "vlm_accuracy_index": None,  # not measured (was a hard-coded 92.4)
            }
        except Exception as e:
            logger.error(f"Error computing KPIs: {e}")
            return {
                "total_videos": 0, "threat_incidents": 0, "clear_videos": 0,
                "threat_rate_pct": 0.0, "avg_occupancy": 0, "total_cameras": 0,
                "active_cameras": 0, "vlm_accuracy_index": None  # not measured (was a hard-coded 92.4)
            }
        finally:
            conn.close()

    def get_threat_trends(self, days: int = 7) -> List[Dict[str, Any]]:
        """Returns daily time-series incident trends across the specified window."""
        conn = self._get_connection()
        if not conn:
            return []

        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d 00:00:00')
            rows = conn.execute("""
                SELECT 
                    strftime('%Y-%m-%d', timestamp) as log_date,
                    COUNT(*) as total_analyzed,
                    SUM(CASE WHEN needs_attention = 1 THEN 1 ELSE 0 END) as threats,
                    SUM(CASE WHEN risk_level LIKE '%CRITICAL%' THEN 1 ELSE 0 END) as critical_count
                FROM video_verdicts
                WHERE timestamp >= ?
                GROUP BY log_date
                ORDER BY log_date ASC
            """, (cutoff,)).fetchall()

            trend = []
            for r in rows:
                trend.append({
                    "date": r["log_date"],
                    "total": r["total_analyzed"],
                    "threats": r["threats"],
                    "critical": r["critical_count"],
                    "clear": max(0, r["total_analyzed"] - r["threats"]),
                })
            return trend
        except Exception as e:
            logger.error(f"Error computing threat trends: {e}")
            return []
        finally:
            conn.close()

    def get_threat_breakdown(self) -> Dict[str, int]:
        """Categorical breakdown of detected threat types."""
        conn = self._get_connection()
        if not conn:
            return {"weapons": 0, "fights": 0, "fire_smoke": 0, "animals": 0, "clear": 0}

        try:
            rows = conn.execute("SELECT detected_action FROM detections WHERE is_alert = 1").fetchall()
            counts = {"weapons": 0, "fights": 0, "fire_smoke": 0, "animals": 0}
            for r in rows:
                act = (r["detected_action"] or "").upper()
                if "WEAPON" in act or "GUN" in act or "KNIFE" in act:
                    counts["weapons"] += 1
                # Before the fight check: "ANIMAL_ASSAULT" also contains "ASSAULT".
                elif "DOG" in act or "ANIMAL" in act:
                    counts["animals"] += 1
                elif "FIGHT" in act or "ASSAULT" in act or "STANCE" in act:
                    counts["fights"] += 1
                elif "FIRE" in act or "SMOKE" in act:
                    counts["fire_smoke"] += 1

            v_row = conn.execute("SELECT COUNT(*) as clr FROM video_verdicts WHERE needs_attention = 0").fetchone()
            counts["clear"] = v_row["clr"] if v_row else 0

            return counts
        except Exception as e:
            logger.error(f"Error computing threat breakdown: {e}")
            return {"weapons": 0, "fights": 0, "fire_smoke": 0, "animals": 0, "clear": 0}
        finally:
            conn.close()

    def get_occupancy_hourly(self) -> List[Dict[str, Any]]:
        """Returns average occupancy counts grouped by hour of day (0-23)."""
        conn = self._get_connection()
        if not conn:
            return []

        try:
            rows = conn.execute("""
                SELECT 
                    strftime('%H', timestamp) as hour_of_day,
                    AVG(occupancy_count) as avg_count,
                    MAX(occupancy_count) as peak_count
                FROM detections
                WHERE occupancy_count > 0
                GROUP BY hour_of_day
                ORDER BY hour_of_day ASC
            """).fetchall()

            result = []
            for r in rows:
                hr = r["hour_of_day"] or "00"
                result.append({
                    "hour": f"{hr}:00",
                    "avg_people": round(float(r["avg_count"] or 0), 1),
                    "peak_people": int(r["peak_count"] or 0),
                })
            return result
        except Exception as e:
            logger.error(f"Error computing hourly occupancy: {e}")
            return []
        finally:
            conn.close()

    def export_csv_report(self) -> str:
        """Generates a CSV string containing all processed video verdicts and summaries."""
        conn = self._get_connection()
        if not conn:
            return ""

        try:
            rows = conn.execute("""
                SELECT 
                    id, video_path, total_analyzed, suspicious_frames, normal_frames,
                    suspicious_percentage, risk_level, needs_attention, recommendation,
                    ai_summary, timestamp
                FROM video_verdicts
                ORDER BY id DESC
            """).fetchall()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Verdict ID", "Video Name", "Total Frames", "Suspicious Frames",
                "Normal Frames", "Suspicious %", "Risk Level", "Needs Attention",
                "Recommendation", "AI Narrative Summary", "Timestamp"
            ])

            for r in rows:
                writer.writerow([
                    r["id"],
                    r["video_path"],
                    r["total_analyzed"],
                    r["suspicious_frames"],
                    r["normal_frames"],
                    r["suspicious_percentage"],
                    r["risk_level"],
                    "YES" if r["needs_attention"] else "NO",
                    r["recommendation"],
                    r["ai_summary"] or "N/A",
                    r["timestamp"]
                ])

            return output.getvalue()
        except Exception as e:
            logger.error(f"Error exporting CSV report: {e}")
            return ""
        finally:
            conn.close()
