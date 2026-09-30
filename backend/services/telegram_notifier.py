"""
services/telegram_notifier.py — Sends incident alerts (photo + short clip) to one
or more Telegram chats through the Bot API.

Setup (free):
  1. In Telegram, message @BotFather, send /newbot, copy the token.
  2. Add the bot to the guards' group (or message it directly), then open
     https://api.telegram.org/bot<TOKEN>/getUpdates to find the chat id.
  3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS (comma separated) in .env.
"""
import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger("vids.telegram")

API = "https://api.telegram.org"
MAX_VIDEO_BYTES = 45 * 1024 * 1024  # Bot API upload limit is 50MB


class TelegramNotifier:
    def __init__(self, token: Optional[str] = None, chat_ids: Optional[List[str]] = None):
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        if chat_ids is None:
            chat_ids = [c.strip() for c in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
        self.chat_ids = chat_ids

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_ids)

    def _post(self, method: str, data: dict, files: Optional[dict] = None, timeout: float = 30.0) -> bool:
        try:
            r = httpx.post(f"{API}/bot{self.token}/{method}", data=data, files=files, timeout=timeout)
            if r.status_code != 200 or not r.json().get("ok"):
                logger.error("Telegram %s failed: %s %s", method, r.status_code, r.text[:200])
                return False
            return True
        except Exception as e:
            logger.error("Telegram %s error: %s", method, e)
            return False

    def send_alert(self, caption: str, photo_jpeg: Optional[bytes] = None,
                   clip_path: Optional[str] = None) -> int:
        """Send to every chat. Returns how many chats got at least the text/photo."""
        if not self.enabled:
            return 0
        caption = caption[:1000]  # Telegram caption limit is 1024
        delivered = 0
        for chat in self.chat_ids:
            if photo_jpeg:
                ok = self._post("sendPhoto", {"chat_id": chat, "caption": caption},
                                files={"photo": ("incident.jpg", photo_jpeg, "image/jpeg")})
            else:
                ok = self._post("sendMessage", {"chat_id": chat, "text": caption})
            delivered += int(ok)
            if ok and clip_path and os.path.exists(clip_path) and os.path.getsize(clip_path) <= MAX_VIDEO_BYTES:
                with open(clip_path, "rb") as f:
                    self._post("sendVideo", {"chat_id": chat, "caption": "Clip of the incident"},
                               files={"video": ("incident.mp4", f, "video/mp4")}, timeout=120.0)
        return delivered
