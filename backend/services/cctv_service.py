import os
import subprocess
import asyncio
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger("vids.cctv_service")


class CCTVService:
    def __init__(self, db_path: str, alert_service: Any):
        self.db_path = db_path
        self.alert_service = alert_service
        self.is_monitoring = False

    def _get_connection(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database: {e}")
            return None

    def add_cctv_ip(self, ip_address: str, location: str, user_id: int) -> Optional[int]:
        conn = self._get_connection()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO cctv_ips (ip_address, location, user_id, status, last_checked)
                VALUES (?, ?, ?, ?, datetime('now'))
            """
            cursor.execute(query, (ip_address, location, user_id, 'unknown'))
            conn.commit()
            new_id = cursor.lastrowid
            cursor.close()
            return new_id
        except sqlite3.Error as e:
            logger.error(f"Error adding CCTV IP: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def delete_cctv_ip(self, cctv_id: int) -> bool:
        conn = self._get_connection()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cctv_ips WHERE id = ?", (cctv_id,))
            conn.commit()
            success = cursor.rowcount > 0
            cursor.close()
            return success
        except sqlite3.Error as e:
            logger.error(f"Error deleting CCTV IP: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def get_all_cctv_ips(self, user_id: int = 1) -> List[Dict]:
        conn = self._get_connection()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cctv_ips WHERE user_id = ?", (user_id,))
            results = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return results
        except sqlite3.Error as e:
            logger.error(f"Error fetching CCTV IPs: {e}")
            return []
        finally:
            conn.close()

    def update_status(self, cctv_id: int, status: str):
        conn = self._get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE cctv_ips SET status = ?, last_checked = datetime('now') WHERE id = ?",
                (status, cctv_id)
            )
            conn.commit()
            cursor.close()
        except sqlite3.Error as e:
            logger.error(f"Error updating CCTV status: {e}")
            conn.rollback()
        finally:
            conn.close()

    async def ping_ip(self, ip: str) -> bool:
        """Ping an IP address to check if it's reachable."""
        param = "-n" if os.name == "nt" else "-c"
        command = ["ping", param, "1", "-w", "2000", ip]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return result.returncode == 0
        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            logger.error(f"Error pinging {ip}: {error_msg}")
            return False

    async def run_monitoring_task(self):
        """Continuous background task to monitor CCTVs."""
        self.is_monitoring = True
        logger.info("CCTV Monitoring task started")

        while self.is_monitoring:
            ips_to_check = self.get_all_cctv_ips()

            for cctv in ips_to_check:
                cctv_id = cctv['id']
                ip = cctv['ip_address']
                location = cctv['location']
                old_status = cctv['status']

                is_online = await self.ping_ip(ip)
                new_status = 'online' if is_online else 'offline'

                if new_status != old_status:
                    logger.info(f"CCTV {ip} at {location} changed status from {old_status} to {new_status}")
                    self.update_status(cctv_id, new_status)

                    if new_status == 'offline':
                        self.alert_service.send_cctv_offline_alert(ip, location, datetime.now())
                else:
                    self.update_status(cctv_id, new_status)

            await asyncio.sleep(10)

    def stop_monitoring(self):
        self.is_monitoring = False
