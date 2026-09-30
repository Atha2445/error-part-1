"""
services/ollama_verifier.py — Confirms or rejects a flagged incident with a local
vision-language model served by Ollama (default: qwen3-vl:4b).

Unlike the old single-frame check, it looks at a short sequence of frames,
because fights and dog bites are actions: one still frame of two people close
together looks the same whether they are hugging or fighting.

It never pretends: if Ollama is unreachable or answers with something that
isn't the expected JSON, the result has success=False so callers keep the
detector's verdict instead of treating it as a rejection.
"""
import base64
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import cv2
import httpx
import numpy as np

logger = logging.getLogger("vids.ollama_verifier")

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3-vl:4b"

_SEQUENCE_NOTE = (
    "These {n} images are consecutive frames, in time order, from one residential "
    "CCTV camera covering about {seconds:.0f} seconds. "
)

# One question per threat type. Each asks for the specific action and names the
# harmless look-alikes that caused false alarms in testing.
PROMPTS: Dict[str, str] = {
    "fight_verify": (
        "Is a physical fight or assault happening: someone punching, kicking, "
        "shoving, grappling or beating another person? Answer false for hugging, "
        "handshakes, play, sports, dancing, people standing or talking close together."
    ),
    "weapon_verify": (
        "Is a person clearly holding a weapon such as a knife, gun, machete, rod "
        "or bat? Answer false for phones, keys, umbrellas, bags, tools being used "
        "for work, or when you cannot actually see the object in a hand."
    ),
    "animal_assault_verify": (
        "Is a dog attacking a person: biting, lunging at, jumping on aggressively "
        "or chasing someone who is fleeing? Answer false for a dog walking, "
        "sniffing, being walked on a leash, being petted, or playing calmly."
    ),
    "fire_verify": (
        "Is there real fire or smoke from something burning? Answer false for "
        "lamps, sunlight, reflections, steam, fog, dust or orange objects."
    ),
    "security_audit": (
        "Is anything dangerous happening: a fight, a weapon being held, an animal "
        "attacking a person, or fire? Answer false for normal activity."
    ),
}

_ANSWER_RULES = (
    " Respond only with JSON matching the schema. Set confirmed to true only if "
    "the images clearly show it; if unsure, set confirmed to false and explain "
    "in description. confidence is 0 to 1."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "confirmed": {"type": "boolean"},
        "confidence": {"type": "number"},
        "description": {"type": "string"},
    },
    "required": ["confirmed", "confidence", "description"],
}


def _encode(frame: np.ndarray, max_side: int = 768) -> str:
    h, w = frame.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("could not encode frame")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _parse(text: str) -> Optional[Dict[str, Any]]:
    """Pull the JSON object out of the reply (tolerates <think> blocks or fences)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data.get("confirmed"), bool):
        return None
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "confirmed": data["confirmed"],
        "confidence": max(0.0, min(1.0, conf)),
        "description": str(data.get("description", "")).strip(),
    }


class OllamaVerifier:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None,
                 timeout: Optional[float] = None, image_size: Optional[int] = None):
        self.base_url = (base_url or os.getenv("OLLAMA_URL", DEFAULT_URL)).rstrip("/")
        self.model = model or os.getenv("OLLAMA_VISION_MODEL", DEFAULT_MODEL)
        # On a CPU-only PC a check can take minutes: raise OLLAMA_TIMEOUT and
        # lower OLLAMA_IMAGE_SIZE (see deploy/frigate/windows/README.md).
        self.timeout = timeout if timeout is not None else float(os.getenv("OLLAMA_TIMEOUT", "90"))
        self.image_size = image_size if image_size is not None else int(os.getenv("OLLAMA_IMAGE_SIZE", "768"))
        self._available: Optional[bool] = None
        self._checked_at = 0.0
        # Context window: Ollama defaults to 4096 tokens, and every image costs
        # hundreds of tokens, so a multi-frame check can be rejected. If that
        # happens the window is raised to what the request needs (plus room
        # for the answer) and remembered. OLLAMA_NUM_CTX sets it up front.
        env_ctx = os.getenv("OLLAMA_NUM_CTX")
        self._num_ctx: Optional[int] = int(env_ctx) if env_ctx else None
        self._answer_tokens = int(os.getenv("OLLAMA_ANSWER_TOKENS", "2048"))
        # Frames per check adapt to how fast this machine answers: fewer when a
        # check uses most of the timeout (CPU), more again when it is quick (GPU).
        env_frames = os.getenv("OLLAMA_MAX_FRAMES")
        self._frame_cap: Optional[int] = int(env_frames) if env_frames else None
        self._max_frames: Optional[int] = self._frame_cap

    def is_available(self) -> bool:
        """True if Ollama is up and the model is pulled. Cached for 60s."""
        if self._available is not None and time.time() - self._checked_at < 60:
            return self._available
        self._checked_at = time.time()
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            r.raise_for_status()
            names = {m.get("name", "") for m in r.json().get("models", [])}
            wanted = self.model if ":" in self.model else f"{self.model}:latest"
            self._available = wanted in names
            if not self._available:
                logger.warning("Ollama is running but model %s is not pulled. Run: ollama pull %s "
                               "(if that is blocked: deploy/frigate/scripts/import_qwen_from_dockerhub.sh)",
                               self.model, self.model)
        except Exception as e:
            logger.warning("Ollama not reachable at %s: %s", self.base_url, e)
            self._available = False
        return self._available

    def verify(self, frames: List[np.ndarray], context_type: str = "security_audit",
               clip_seconds: Optional[float] = None) -> Dict[str, Any]:
        """Ask the model whether the frames show the threat. See module docstring."""
        t0 = time.time()
        base = {"model_used": f"ollama:{self.model}", "verified_threat": False,
                "confidence": 0.0, "reasoning": ""}
        frames = [f for f in frames if f is not None and getattr(f, "size", 0)]
        if not frames:
            return {**base, "success": False, "reasoning": "no frames to check"}
        if not self.is_available():
            return {**base, "success": False, "unavailable": True,
                    "reasoning": f"Ollama model {self.model} unavailable"}
        if self._max_frames and len(frames) > self._max_frames:
            # Keep the time order and the spread over the clip
            idx = sorted({round(i * (len(frames) - 1) / max(1, self._max_frames - 1))
                          for i in range(self._max_frames)}) if self._max_frames > 1 else [len(frames) // 2]
            frames = [frames[i] for i in idx]

        seconds = clip_seconds if clip_seconds is not None else max(1.0, len(frames) * 0.5)
        prompt = ""
        if len(frames) > 1:
            prompt = _SEQUENCE_NOTE.format(n=len(frames), seconds=seconds)
        prompt += PROMPTS.get(context_type, PROMPTS["security_audit"]) + _ANSWER_RULES

        body = {
            "model": self.model,
            "stream": False,
            "format": _SCHEMA,
            "options": {"temperature": 0},
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [_encode(f, self.image_size) for f in frames],
            }],
        }
        try:
            r = self._post(body)
            needed = self._context_needed(r)
            if needed:
                self._num_ctx = needed
                logger.info("Ollama context raised to %d tokens for %d-frame checks", needed, len(frames))
                r = self._post(body)
            r.raise_for_status()
            reply = r.json().get("message", {}).get("content", "")
        except httpx.TimeoutException:
            self._shrink_frames(len(frames), timed_out=True)
            logger.error("Ollama check timed out after %.0fs with %d frames; next checks use %s frames",
                         self.timeout, len(frames), self._max_frames)
            return {**base, "success": False, "reasoning": "ollama timed out",
                    "latency_seconds": round(time.time() - t0, 1)}
        except Exception as e:
            logger.error("Ollama verification failed: %s", e)
            self._available = None  # re-check next time
            return {**base, "success": False, "reasoning": f"ollama error: {e}",
                    "latency_seconds": round(time.time() - t0, 1)}
        self._adapt_frames(len(frames), time.time() - t0)

        parsed = _parse(reply)
        if parsed is None:
            logger.warning("Ollama gave an unusable answer: %.200s", reply)
            return {**base, "success": False, "reasoning": "unparseable model answer",
                    "raw": reply[:500], "latency_seconds": round(time.time() - t0, 1)}

        return {
            **base,
            "success": True,
            "verified_threat": parsed["confirmed"],
            "confidence": parsed["confidence"],
            "reasoning": parsed["description"],
            "frames_checked": len(frames),
            "latency_seconds": round(time.time() - t0, 1),
        }


    # ---- helpers ------------------------------------------------------------
    def _post(self, body: Dict[str, Any]) -> httpx.Response:
        if self._num_ctx:
            body["options"]["num_ctx"] = self._num_ctx
        return httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)

    def _context_needed(self, r: httpx.Response) -> Optional[int]:
        """If Ollama rejected the request as too long, the context size that fits it."""
        if r.status_code != 400 or "context" not in r.text:
            return None
        m = re.search(r"n_prompt_tokens[^0-9]*(\d+)", r.text) or re.search(r"\((\d+) tokens\)", r.text)
        if not m:
            return None
        need = int(m.group(1)) + self._answer_tokens
        need = ((need + 1023) // 1024) * 1024
        return need if not self._num_ctx or need > self._num_ctx else None

    def _shrink_frames(self, used: int, timed_out: bool = False):
        self._max_frames = max(1, used // 2 if timed_out else used - 1)

    def _adapt_frames(self, used: int, seconds: float):
        if seconds > 0.6 * self.timeout and used > 1:
            self._shrink_frames(used)
            logger.info("Ollama check took %.0fs of %.0fs allowed; next checks use %d frames",
                        seconds, self.timeout, self._max_frames)
        elif seconds < 0.3 * self.timeout and self._max_frames and self._max_frames == used:
            grown = used + 1
            self._max_frames = min(grown, self._frame_cap) if self._frame_cap else grown


_instance: Optional[OllamaVerifier] = None


def get_ollama_verifier() -> OllamaVerifier:
    global _instance
    if _instance is None:
        _instance = OllamaVerifier()
    return _instance
