import os
import smtplib
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import logging
import asyncio
from typing import Optional


class AlertService:
    def __init__(self, watch_path: str, email_config: dict, db_path: str = None):
        self.watch_path = watch_path
        self.email_config = email_config
        self.db_path = db_path
        self.last_video_time = datetime.now()
        self.is_running = False

        self.default_video_template = """
        <html>
        <body>
            <h2 style="color: #d32f2f;">Security Alert - Suspicious Activity Detected</h2>
            <p>Video: {video_name}</p>
            <p>Risk Level: {risk_level}</p>
            <p>Recommendation: {recommendation}</p>
            <hr>
            <p>Statistics: {stats}</p>
        </body>
        </html>
        """
        self.default_inactivity_template = "No new videos have been added to {watch_path} for {minutes:.1f} minutes."

    def _get_db_setting(self, key, default):
        if not self.db_path:
            return default
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = ?", (key,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return result[0] if result else default
        except Exception as e:
            logging.error(f"Error fetching setting {key}: {e}")
            return default

    def update_last_video_time(self):
        self.last_video_time = datetime.now()
        logging.info(f"Last video time updated: {self.last_video_time}")

    async def run_inactivity_check(self, threshold_minutes: int):
        self.is_running = True
        logging.info(f"Inactivity check started with threshold: {threshold_minutes} minutes")
        while self.is_running:
            await asyncio.sleep(60)

            elapsed = datetime.now() - self.last_video_time
            if elapsed > timedelta(minutes=threshold_minutes):
                logging.warning(f"Inactivity detected! No videos for {elapsed.total_seconds() / 60:.1f} minutes")
                self.send_email_alert(elapsed.total_seconds() / 60)
                self.last_video_time = datetime.now()

    def _get_recipients(self):
        admin_emails = self._get_db_setting('alert_recipients', self.email_config.get('admin_email', ''))
        if not admin_emails:
            return []
        return [email.strip() for email in admin_emails.split(',') if email.strip()]

    def _validate_email_config(self) -> Optional[str]:
        """Return None if config is valid, otherwise an error message."""
        missing = []
        if not self.email_config.get('smtp_server'):
            missing.append('SMTP_SERVER')
        if not self.email_config.get('sender_email'):
            missing.append('SENDER_EMAIL')
        if not self.email_config.get('sender_password'):
            missing.append('SENDER_PASSWORD')
        if missing:
            return f"Email not configured: missing {', '.join(missing)}. Set these in a .env file or environment variables."
        return None

    def send_email_alert(self, minutes: float):
        # Validate config first
        config_error = self._validate_email_config()
        if config_error:
            logging.warning("Inactivity email skipped: %s", config_error)
            return

        try:
            recipients = self._get_recipients()
            if not recipients:
                logging.warning("No email recipients configured. Set ADMIN_EMAIL in .env or alert_recipients in system_settings.")
                return

            template = self._get_db_setting('inactivity_alert_template', self.default_inactivity_template)
            body = template.format(watch_path=self.watch_path, minutes=minutes)

            msg = MIMEMultipart()
            msg['From'] = self.email_config['sender_email']
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = "ALERT - No New Videos Detected"
            msg.attach(MIMEText(body, 'plain' if '<html' not in body.lower() else 'html'))

            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg)

            logging.info(f"Inactivity alert email sent to {len(recipients)} recipients")
        except smtplib.SMTPAuthenticationError as e:
            logging.error("Email auth failed: %s (smtp_user=%s, smtp_server=%s:%s). "
                          "If using Gmail, you must use an App Password, not your regular password.",
                          e, self.email_config.get('sender_email'),
                          self.email_config.get('smtp_server'), self.email_config.get('smtp_port'))
        except smtplib.SMTPException as e:
            logging.error("SMTP error sending inactivity email: %s", e)
        except Exception as e:
            logging.error("Unexpected error sending inactivity email: %s", e)

    def send_detection_alert(self, video_path: str, verdict: dict):
        """Send email alert to admin with video analysis verdict."""
        config_error = self._validate_email_config()
        if config_error:
            logging.warning("Detection email skipped: %s", config_error)
            return False

        recipients = self._get_recipients()
        if not recipients:
            logging.warning("Detection email skipped: no recipients configured")
            return False

        try:
            template = self._get_db_setting('video_alert_template', self.default_video_template)

            stats = f"Total Frames: {verdict['total_analyzed']}, Suspicious: {verdict['suspicious_frames']} ({verdict['suspicious_percentage']:.1f}%)"

            body = template.format(
                video_name=os.path.basename(video_path),
                risk_level=verdict['risk_level'],
                recommendation=verdict['recommendation'],
                stats=stats,
                duration=verdict['duration']
            )

            msg = MIMEMultipart()
            msg['From'] = self.email_config['sender_email']
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = f"SECURITY ALERT - Suspicious Activity Detected in {os.path.basename(video_path)}"

            msg.attach(MIMEText(body, 'html' if '<html' in body.lower() else 'plain'))

            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg)

            logging.info(f"Alert email sent to {len(recipients)} recipients")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logging.error("Email auth failed for detection alert: %s (smtp_user=%s). "
                          "If using Gmail, you must use an App Password, not your regular password.",
                          e, self.email_config.get('sender_email'))
            return False
        except smtplib.SMTPException as e:
            logging.error("SMTP error sending detection email: %s", e)
            return False
        except Exception as e:
            logging.error("Unexpected error sending detection email: %s", e)
            return False

    def send_incident_alert(self, subject: str, body: str, snapshot_jpeg: Optional[bytes] = None) -> bool:
        """Email a live-camera incident (from the Frigate bridge) with its snapshot attached."""
        config_error = self._validate_email_config()
        if config_error:
            logging.warning("Incident email skipped: %s", config_error)
            return False
        recipients = self._get_recipients()
        if not recipients:
            logging.warning("Incident email skipped: no recipients configured")
            return False
        try:
            from email.mime.image import MIMEImage
            msg = MIMEMultipart()
            msg['From'] = self.email_config['sender_email']
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            if snapshot_jpeg:
                img = MIMEImage(snapshot_jpeg, _subtype="jpeg")
                img.add_header('Content-Disposition', 'attachment', filename='incident.jpg')
                msg.attach(img)
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg)
            logging.info("Incident email sent to %d recipients", len(recipients))
            return True
        except Exception as e:
            logging.error("Error sending incident email: %s", e)
            return False

    def stop(self):
        self.is_running = False

    def send_test_email(self, recipient: str) -> dict:
        """Send a test email to verify configuration. Returns dict with success/error."""
        config_error = self._validate_email_config()
        if config_error:
            return {"success": False, "error": config_error}

        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['sender_email']
            msg['To'] = recipient
            msg['Subject'] = "Vigilinx - Test Email"

            body = f"""
            <html>
            <body>
                <h2>Vigilinx Email Configuration Test</h2>
                <p>This is a test email from your Vigilinx intrusion detection system.</p>
                <p>SMTP Server: {self.email_config['smtp_server']}:{self.email_config['smtp_port']}</p>
                <p>Sender: {self.email_config['sender_email']}</p>
                <p>Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <hr>
                <p style="color: green;"><b>✅ If you received this, your email configuration is working correctly!</b></p>
            </body>
            </html>
            """
            msg.attach(MIMEText(body, 'html'))

            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg)

            logging.info(f"Test email sent successfully to {recipient}")
            return {"success": True, "message": f"Test email sent to {recipient}"}

        except smtplib.SMTPAuthenticationError as e:
            error_msg = (f"Authentication failed: {e}. "
                         f"If using Gmail, you must generate an App Password (Google Account → Security → 2-Step Verification → App Passwords). "
                         f"Regular password login is blocked by Google.")
            logging.error("Test email auth failed: %s", error_msg)
            return {"success": False, "error": error_msg}
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error: {e}"
            logging.error("Test email SMTP error: %s", e)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logging.error("Test email unexpected error: %s", e)
            return {"success": False, "error": error_msg}

    def send_cctv_offline_alert(self, ip_address: str, location: str, timestamp: datetime):
        """Send email alert when a CCTV camera goes offline."""
        config_error = self._validate_email_config()
        if config_error:
            logging.warning("CCTV offline email skipped: %s", config_error)
            return False

        recipients = self._get_recipients()
        if not recipients:
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['sender_email']
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = f"CCTV OFFLINE ALERT - {location} ({ip_address})"

            template = self._get_db_setting('cctv_offline_template', "CCTV Camera {location} ({ip_address}) went offline at {timestamp}")
            body = template.format(location=location, ip_address=ip_address, timestamp=timestamp.strftime('%Y-%m-%d %H:%M:%S'))

            msg.attach(MIMEText(body, 'html' if '<html' in body.lower() else 'plain'))

            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg)

            logging.info(f"CCTV offline alert email sent for {ip_address}")
            return True
        except smtplib.SMTPAuthenticationError as e:
            logging.error("Email auth failed for CCTV alert: %s", e)
            return False
        except smtplib.SMTPException as e:
            logging.error("SMTP error sending CCTV offline email: %s", e)
            return False
        except Exception as e:
            logging.error("Unexpected error sending CCTV offline email: %s", e)
            return False
