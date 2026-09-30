"""
services/vlm_service.py — Multi-Provider VLM Service.

Providers:
  - XCLIPProvider:  Zero-shot video-text similarity for windowed prompt analysis.
  - KimiVLProvider: Local in-process Kimi-VL-A3B vision-language model via llama-cpp-python.
  - EvidenceAuditor: On-demand incident review using the local Kimi-VL model (fully offline).
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import base64
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

logger = logging.getLogger("vids.vlm_service")


# ---------------------------------------------------------------------------
#  Helper: locate models/ directory (same logic as threat_engine.py)
# ---------------------------------------------------------------------------

def _resolve_models_dir() -> Path:
    """Locate the models/ directory.

    Works in three scenarios:
      1. PyInstaller frozen bundle  -> next to executable or sys._MEIPASS / models
      2. Normal dev run             -> <backend_dir> / models
      3. Fallback                   -> current working directory / models
    """
    if getattr(sys, "frozen", False):
        exe_models = Path(sys.executable).parent / "models"
        if exe_models.exists():
            return exe_models
        if hasattr(sys, "_MEIPASS"):
            candidate = Path(sys._MEIPASS) / "models"
            if candidate.exists():
                return candidate

    backend_dir = Path(__file__).resolve().parent.parent
    candidate = backend_dir / "models"
    if candidate.exists():
        return candidate

    return Path.cwd() / "models"


def _locate_kimi_files() -> Tuple[Optional[Path], Optional[Path]]:
    r"""Locate Kimi-VL model and mmproj GGUF files using multi-tier dynamic search:
      1. ./models/ (App directory / frozen bundle)
      2. C:\Vigilinx\models
      3. Environment variables: KIMI_MODEL_DIR or VIGILINX_MODELS_DIR
      4. %USERPROFILE%\models (C:\Users\<user>\models)
      5. %USERPROFILE%\Downloads
      6. %USERPROFILE%\.cache\kimi or %USERPROFILE%\AppData\Local\Vigilinx\models
      7. E:\Fight\models (host dev fallback if present)
    """
    candidate_dirs = [
        _resolve_models_dir(),
        Path(r"C:\Vigilinx\models"),
    ]
    for env_k in ("KIMI_MODEL_DIR", "VIGILINX_MODELS_DIR"):
        v = os.environ.get(env_k)
        if v:
            candidate_dirs.append(Path(v))

    home = Path.home()
    candidate_dirs.extend([
        home / "models",
        home / "Downloads",
        home / ".cache" / "kimi",
        home / "AppData" / "Local" / "Vigilinx" / "models",
        Path(r"E:\Fight\models"),
    ])

    for d in candidate_dirs:
        try:
            if not d.exists() or not d.is_dir():
                continue
            model_candidate = d / "Kimi-VL-A3B-Thinking-2506-Q4_K_M.gguf"
            mmproj_candidate = d / "mmproj-Kimi-VL-A3B-Thinking-2506-f16.gguf"

            if model_candidate.exists() and mmproj_candidate.exists():
                logger.info(f"[KimiVL] Discovered Kimi-VL models in: {d}")
                return model_candidate, mmproj_candidate

            # Case-insensitive or glob pattern fallback
            models_in_d = list(d.glob("*Kimi*Q4*.gguf"))
            mmprojs_in_d = list(d.glob("*mmproj*.gguf"))
            if models_in_d and mmprojs_in_d:
                logger.info(f"[KimiVL] Discovered Kimi-VL matching models in: {d}")
                return models_in_d[0], mmprojs_in_d[0]
        except Exception:
            continue

    return None, None


# ---------------------------------------------------------------------------
#  Provider 1: X-CLIP (zero-shot video-text similarity)
# ---------------------------------------------------------------------------

class VLMProvider(ABC):
    @abstractmethod
    def analyze(self, frames: List[np.ndarray], prompts: List[str]) -> np.ndarray:
        pass


class XCLIPProvider(VLMProvider):
    def __init__(self, model_name: str = "microsoft/xclip-base-patch32"):
        self.model_name = model_name
        self.model = None
        self.processor = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def _load_model(self):
        if self.model is None:
            try:
                from transformers import AutoProcessor, AutoModel
                self.model = AutoModel.from_pretrained(self.model_name).to(self.device)
                self.processor = AutoProcessor.from_pretrained(self.model_name)
            except Exception as e:
                logger.error(f"Failed to load X-CLIP model: {e}")

    def analyze(self, frames: List[np.ndarray], prompts: List[str]) -> np.ndarray:
        self._load_model()
        if self.model is None or self.processor is None:
            logger.warning("X-CLIP model not loaded, returning uniform distribution")
            return np.ones(len(prompts), dtype=np.float32) / max(len(prompts), 1)

        valid_frames = [f for f in frames if f is not None and getattr(f, 'size', 0) > 0]
        if not valid_frames:
            return np.zeros(len(prompts), dtype=np.float32)

        if len(valid_frames) < len(frames):
            valid_frames = valid_frames + [valid_frames[-1]] * (len(frames) - len(valid_frames))
        pil_frames = [Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB) if f.shape[-1] == 3 else f) for f in valid_frames]

        try:
            inputs = self.processor(
                text=prompts,
                videos=pil_frames,
                return_tensors="pt",
                padding=True,
            ).to(self.device)

            if inputs.get("pixel_values") is None:
                logger.warning("X-CLIP processor did not produce pixel_values; skipping window.")
                return np.zeros(len(prompts), dtype=np.float32)

            with torch.no_grad():
                outputs = self.model(**inputs)

            probs = outputs.logits_per_video.softmax(dim=1)
            return probs.cpu().numpy()[0]
        except Exception as e:
            logger.error(f"X-CLIP inference error: {e}")
            return np.zeros(len(prompts), dtype=np.float32)


# ---------------------------------------------------------------------------
#  Provider 2: Kimi-VL (local in-process via llama-cpp-python)
# ---------------------------------------------------------------------------

class KimiVLProvider:
    """Local Kimi-VL-A3B vision-language model loaded in-process via llama-cpp-python.

    This is a heavy model (~10.5 GB). It is loaded lazily on first use and
    guarded by a threading lock so only one inference runs at a time.
    """

    def __init__(self):
        self._llm = None
        self._chat_handler = None
        self._inference_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._load_attempted = False

    def _ensure_loaded(self) -> bool:
        """Load the model if not already loaded. Returns True if model is ready."""
        if self._llm is not None:
            return True
        if self._load_attempted:
            return False

        self._load_attempted = True
        model_path, mmproj_path = _locate_kimi_files()

        if not model_path or not mmproj_path:
            logger.warning(
                "[KimiVL] Kimi-VL GGUF files not found in any standard search directory.\n"
                "Searched:\n"
                "  - ./models/\n"
                "  - C:\\Vigilinx\\models\\\n"
                "  - %USERPROFILE%\\models\\\n"
                "  - %USERPROFILE%\\Downloads\\\n"
                "  - %KIMI_MODEL_DIR%\n"
                "Local Kimi-VL inference unavailable; detections without an Ollama answer are shown as not verified."
            )
            return False

        try:
            from llama_cpp import Llama
            from llama_cpp.llama_chat_format import Llava15ChatHandler

            gpu_layers = 0
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_layers = 33
                    logger.info("[KimiVL] NVIDIA CUDA GPU detected! Setting n_gpu_layers=33 for acceleration.")
            except Exception:
                pass

            logger.info(f"[KimiVL] Loading model from {model_path} (n_gpu_layers={gpu_layers})...")
            t0 = time.time()

            self._chat_handler = Llava15ChatHandler(clip_model_path=str(mmproj_path))
            self._llm = Llama(
                model_path=str(model_path),
                chat_handler=self._chat_handler,
                n_ctx=4096,
                n_gpu_layers=gpu_layers,
                n_threads=os.cpu_count() or 4,
                verbose=False,
            )
            logger.info(f"[KimiVL] Model loaded in {time.time() - t0:.1f}s. Fully offline, ready for inference.")
            return True
        except ImportError:
            logger.warning("llama-cpp-python not installed. Local Kimi-VL inference unavailable.")
            return False
        except Exception as e:
            logger.error(f"[KimiVL] Failed to load model: {e}")
            return False

    @staticmethod
    def _frame_to_data_uri(image: np.ndarray) -> str:
        """OpenCV BGR image -> base64 JPEG data URI."""
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("Failed to encode image for VLM input.")
        b64 = base64.b64encode(buf).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"

    @staticmethod
    def _clean_thinking_tokens(text: str) -> Tuple[str, str]:
        """Robustly strip <think>...</think> or ◁think▷...◁/think▷ blocks even if unclosed."""
        if not text:
            return "", ""
        thinking_text = ""
        # 1. Closed thinking block
        think_match = re.search(r"[◁<]think[▷>](.*?)[◁<]/think[▷>]", text, flags=re.DOTALL)
        if think_match:
            thinking_text = think_match.group(1).strip()
            cleaned = re.sub(r"[◁<]think[▷>].*?[◁<]/think[▷>]", "", text, flags=re.DOTALL).strip()
        elif re.search(r"[◁<]think[▷>]", text):
            # Unclosed thinking block: everything from the start tag to end was internal thinking
            parts = re.split(r"[◁<]think[▷>]", text, maxsplit=1)
            before = parts[0].strip()
            thinking_text = parts[1].strip() if len(parts) > 1 else ""
            cleaned = before
        else:
            cleaned = text.strip()

        # Remove any stray closing tags or leftover artifacts
        cleaned = re.sub(r"[◁<]/think[▷>]", "", cleaned).strip()
        cleaned = re.sub(r"[◁<]think[▷>]?", "", cleaned).strip()
        return cleaned, thinking_text

    @staticmethod
    def _parse_response(raw_text: str) -> dict:
        """Parse the VLM's response, extracting thought tokens and JSON/natural language verdict."""
        cleaned, thinking_text = KimiVLProvider._clean_thinking_tokens(raw_text.strip())

        # Strip markdown fences
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

        # 2. Try to find a JSON block { ... } in the remaining text
        json_match = re.search(r"\{[^{}]*\"confirmed\"[^{}]*\}", cleaned, flags=re.DOTALL)
        if not json_match:
            json_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)

        if json_match:
            try:
                data = json.loads(json_match.group(0))
                desc = str(data.get("description", cleaned))
                # Ensure description itself has no leaked think tags
                clean_desc, _ = KimiVLProvider._clean_thinking_tokens(desc)
                return {
                    "confirmed": bool(data.get("confirmed", False)),
                    "confidence": float(data.get("confidence", 0.0)),
                    "description": clean_desc if clean_desc else "Scene verified by Kimi-VL.",
                    "thinking": thinking_text,
                    "raw": raw_text,
                }
            except Exception:
                pass

        # 3. Dynamic Natural Language Semantic Evaluation (when output is pure narrative)
        eval_text = (cleaned + " " + thinking_text).lower()

        has_fight = any(k in eval_text for k in ["altercation", "fighting", "assault", "brawl", "physical struggle", "punching", "grappling"]) and not any(k in eval_text for k in ["no fighting", "no altercation", "peaceful", "playful"])
        has_weapon = any(k in eval_text for k in ["handgun", "firearm", "knife", "blade", "rifle", "pistol", "brandishing weapon", "holding weapon"]) and not any(k in eval_text for k in ["no weapon", "no visible weapon", "no firearms", "no guns", "no weapons"])
        has_fire = any(k in eval_text for k in ["active fire", "open flames", "dense smoke", "blaze", "inferno"]) and not any(k in eval_text for k in ["no fire", "no smoke", "no flames"])
        has_animal_assault = any(k in eval_text for k in [
            "dog attack", "animal bite", "biting", "canine assault", "aggressive animal",
            "attacking a person", "lunging at", "animal mauling", "dog biting", "aggressive dog"
        ]) and not any(k in eval_text for k in [
            "no attack", "peaceful animal", "petting", "walking peacefully", "no aggression", "no biting"
        ])

        confirmed = has_fight or has_weapon or has_fire or has_animal_assault

        # Generate a clean, crisp description; NEVER leak raw thinking or timestamp lists
        if cleaned and not any(k in cleaned for k in ["00:05, 00:06", "timestamps"]):
            description = cleaned
        elif has_weapon:
            description = "Firearm / weapon presence identified in monitored area."
        elif has_animal_assault:
            description = "Aggressive animal assault / attack behavior identified."
        elif has_fire:
            description = "Active fire and smoke condition identified in scene."
        elif has_fight:
            description = "Physical altercation between individuals observed in progress."
        else:
            description = "Scene evaluated by Kimi-VL; no active safety breach confirmed."

        return {
            "confirmed": confirmed,
            "confidence": 0.85 if confirmed else 0.90,
            "description": description,
            "thinking": thinking_text,
            "raw": raw_text,
        }

    def infer(self, frame: np.ndarray, prompt: str) -> dict:
        """Run a single-frame inference synchronously. Thread-safe."""
        if not self._ensure_loaded():
            return {
                "confirmed": False,
                "confidence": 0.0,
                "description": "",
                "error": "Kimi-VL model not loaded.",
            }

        data_uri = self._frame_to_data_uri(frame)
        t0 = time.time()
        try:
            with self._inference_lock:
                response = self._llm.create_chat_completion(
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": data_uri}},
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                    max_tokens=800,
                    temperature=0.2,
                )
            raw_text = response["choices"][0]["message"]["content"]
            result = self._parse_response(raw_text)
            result["latency_seconds"] = round(time.time() - t0, 1)
            return result
        except Exception as e:
            return {
                "confirmed": False,
                "confidence": 0.0,
                "description": "",
                "error": f"inference_error: {e}",
                "latency_seconds": round(time.time() - t0, 1),
            }

    def infer_async(self, frame: np.ndarray, prompt: str):
        """Non-blocking entry point. Returns a concurrent.futures.Future."""
        return self._executor.submit(self.infer, frame, prompt)


# ---------------------------------------------------------------------------
#  Singleton Kimi-VL instance (shared across EvidenceAuditor and direct use)
# ---------------------------------------------------------------------------
_kimi_vl_instance: Optional[KimiVLProvider] = None
_kimi_vl_lock = threading.Lock()


def get_kimi_vl() -> KimiVLProvider:
    """Return the singleton KimiVLProvider, creating it on first call."""
    global _kimi_vl_instance
    if _kimi_vl_instance is None:
        with _kimi_vl_lock:
            if _kimi_vl_instance is None:
                _kimi_vl_instance = KimiVLProvider()
    return _kimi_vl_instance


# ---------------------------------------------------------------------------
#  Evidence Auditor (replaces the old remote-API auditor)
# ---------------------------------------------------------------------------

class EvidenceAuditor:
    """
    On-Demand Multi-Modal Evidence Reasoner.
    Called when an operator or supervisor wants to recheck/audit a triggered alert
    or conduct natural language forensic investigation.

    Uses the local Kimi-VL model — fully offline, no API key needed.
    """

    # Prompt templates for different audit contexts
    AUDIT_PROMPTS = {
        "security_audit": (
            "You are an expert CCTV security auditor. Analyze this surveillance frame "
            "objectively. Describe: 1) What objects or people are present, 2) Any "
            "visible weapons, fire, fighting, or hazards, 3) Conclude with your "
            "assessment.\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"confirmed": true/false, "confidence": 0.0-1.0, '
            '"description": "detailed description of the scene"}'
        ),
        "weapon_verify": (
            "You are a security monitoring assistant. Look at this CCTV frame and "
            "determine whether a visible weapon (gun, knife, or similar) is actually "
            "present and being held/brandished, as opposed to a false positive "
            "(e.g. a phone, tool, or other object).\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"confirmed": true/false, "confidence": 0.0-1.0, '
            '"description": "what is visible in the scene"}'
        ),
        "fight_verify": (
            "You are a security monitoring assistant. Look at this CCTV frame and "
            "determine whether this shows a physical altercation / fight / assault "
            "in progress, as opposed to a non-violent interaction (e.g. hugging, "
            "talking closely, handshake).\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"confirmed": true/false, "confidence": 0.0-1.0, '
            '"description": "what is happening in the scene"}'
        ),
        "fire_verify": (
            "You are a security monitoring assistant. Look at this CCTV frame and "
            "determine whether real fire or smoke is present, as opposed to a false "
            "positive (warm lighting, steam, red/orange objects, fog).\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"confirmed": true/false, "confidence": 0.0-1.0, '
            '"description": "what is visible in the scene"}'
        ),
        "animal_assault_verify": (
            "You are a security monitoring assistant. Look at this CCTV surveillance frame "
            "and determine whether an active animal assault or dog attack is occurring — "
            "specifically, is an animal (such as a dog) aggressively lunging, biting, or "
            "attacking a human, as opposed to a peaceful pet, stray animal walking peacefully, "
            "or a false detection (e.g. fire textures, shadows, inanimate objects).\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"confirmed": true/false, "confidence": 0.0-1.0, '
            '"description": "what is happening between the animal and person"}'
        ),
    }

    def __init__(self):
        self._kimi = get_kimi_vl()

    def audit_incident(
        self,
        frame_or_clip: np.ndarray,
        prompt: str = "Analyze this security frame and verify if there is an active threat or safety hazard.",
        context_type: str = "security_audit"
    ) -> Dict[str, Any]:
        """
        Runs multi-modal evidence reasoning on a keyframe or alert snapshot.

        Accepts one frame or a list of frames (a short sequence works much
        better for fights and bites). Tries, in order: Ollama (local, multi-frame),
        Kimi-VL (local, single frame, optional). If neither is available the
        result is an abstention (success=False): the detector's result stands,
        marked as not verified. A weak single-frame similarity model (X-CLIP)
        is deliberately not used as a verifier any more: it confirmed threats
        on near coin-flip scores and those showed up as "confirmed by AI".
        """
        frames = list(frame_or_clip) if isinstance(frame_or_clip, (list, tuple)) else [frame_or_clip]
        if not frames:
            return self._heuristic_fallback(np.zeros((1, 1, 3), np.uint8), prompt)

        from services.ollama_verifier import get_ollama_verifier
        ollama = get_ollama_verifier()
        o_res = ollama.verify(frames, context_type=context_type)
        if o_res.get("success"):
            return {"prompt": prompt, **o_res}

        key_frame = frames[len(frames) // 2]

        # Build the full prompt: use the template if available, otherwise
        # wrap the user's custom prompt
        template = self.AUDIT_PROMPTS.get(context_type)
        if template:
            full_prompt = template
        else:
            full_prompt = (
                f"{prompt}\n\n"
                "Respond with ONLY a JSON object:\n"
                '{"confirmed": true/false, "confidence": 0.0-1.0, '
                '"description": "your analysis"}'
            )

        result = self._kimi.infer(key_frame, full_prompt)

        if result.get("error"):
            # No real verifier available: abstain so the alert is shown as unverified
            return self._heuristic_fallback(key_frame, prompt)

        is_threat = result.get("confirmed", False)

        return {
            "success": True,
            "prompt": prompt,
            "reasoning": result.get("description", ""),
            "verified_threat": is_threat,
            "confidence": result.get("confidence", 0.0),
            "model_used": "kimi-vl-a3b-local",
            "latency_seconds": result.get("latency_seconds"),
        }

    def summarize_video_keyframes(
        self,
        keyframes: List[np.ndarray],
        timestamps: List[float],
        threat_summary: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generate chronological narrative summary and timeline across video keyframes.
        Works for both routine normal footage and threat incidents.
        """
        if not keyframes:
            return {
                "success": False,
                "environment": "Unknown",
                "narrative_summary": "No video frames provided for summarization.",
                "key_events": [],
                "incident_status": "ROUTINE_NORMAL",
                "confidence": 0.0,
                "latency_seconds": 0.0,
            }

        t0 = time.time()

        # Build a chronological storyboard montage with timestamp watermarks
        annotated_thumbs = []
        for frame, t_sec in zip(keyframes[:6], timestamps[:6]):
            thumb = cv2.resize(frame, (320, 240))
            mm = int(t_sec // 60)
            ss = int(t_sec % 60)
            t_str = f"{mm:02d}:{ss:02d}"
            cv2.rectangle(thumb, (5, 5), (85, 28), (0, 0, 0), -1)
            cv2.putText(thumb, t_str, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            annotated_thumbs.append(thumb)

        n = len(annotated_thumbs)
        if n == 1:
            montage = annotated_thumbs[0]
        elif n <= 3:
            montage = np.hstack(annotated_thumbs)
        else:
            mid = (n + 1) // 2
            row1 = np.hstack(annotated_thumbs[:mid])
            row2_list = annotated_thumbs[mid:]
            while len(row2_list) < len(annotated_thumbs[:mid]):
                row2_list.append(np.zeros_like(annotated_thumbs[0]))
            row2 = np.hstack(row2_list)
            montage = np.vstack([row1, row2])

        # Build summary prompt with injected sensor leads for temporal transition
        sensor_context = ""
        if threat_summary:
            animals_c = threat_summary.get('animals_count', 0)
            animal_assaults_c = threat_summary.get('animal_assaults_count', 0)
            fights_c = threat_summary.get('fights_count', 0)
            weapons_c = threat_summary.get('weapons_count', 0)
            fires_c = threat_summary.get('fires_count', 0)
            risk = threat_summary.get('risk_level', '')
            rec = threat_summary.get('recommendation', '')
            sensor_parts = []
            if animal_assaults_c > 0:
                sensor_parts.append(f"ANIMAL ASSAULT (DOG ATTACK) detected in {animal_assaults_c} frames")
            if animals_c > 0:
                sensor_parts.append(f"Animals detected in {animals_c} frames")
            if fights_c > 0:
                sensor_parts.append(f"Human fight detected in {fights_c} frames")
            if weapons_c > 0:
                sensor_parts.append(f"Weapons detected in {weapons_c} frames")
            if fires_c > 0:
                sensor_parts.append(f"Fire/smoke detected in {fires_c} frames")
            if sensor_parts:
                sensor_context = (
                    "\n\nSENSOR INTELLIGENCE (from neural network detectors): "
                    + "; ".join(sensor_parts) + f". Risk assessment: {risk}. {rec}"
                )

        summary_prompt = (
            "You are a CCTV surveillance intelligence analyst. "
            "Examine these chronological keyframe snapshots from a security recording. "
            "Provide ONLY 2-4 clear, concise sentences in plain English for a non-technical security operator. "
            "Start with routine baseline conditions, then describe any incident detected. "
            "IMPORTANT: Do NOT list timestamps or frame numbers. Do NOT include thinking. "
            "Respond with ONLY a JSON object:\n"
            "{\n"
            '  "environment": "setting type (e.g. office corridor, street)",\n'
            '  "narrative_summary": "2-4 clear plain English sentences describing what happened",\n'
            '  "incident_status": "ROUTINE_NORMAL" or "INCIDENT_DETECTED",\n'
            '  "confidence": 0.85\n'
            "}"
            + sensor_context
        )

        res = self._kimi.infer(montage, summary_prompt)

        raw_narrative = ""
        environment = "Surveillance Area"
        incident_status = "ROUTINE_NORMAL"
        confidence = 0.85

        if not res.get("error") and res.get("confirmed") is not None:
            raw = res.get("raw", "")
            try:
                cleaned, _ = KimiVLProvider._clean_thinking_tokens(raw.strip())
                cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
                cleaned = re.sub(r"```$", "", cleaned).strip()
                parsed = json.loads(cleaned)
                environment = parsed.get("environment", "Surveillance Area")
                raw_narrative = parsed.get("narrative_summary", "")
                incident_status = parsed.get("incident_status", "ROUTINE_NORMAL")
                confidence = float(parsed.get("confidence", res.get("confidence", 0.85)))
            except Exception:
                narrative_match = re.search(r'"narrative_summary"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
                env_match = re.search(r'"environment"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
                if narrative_match:
                    raw_narrative = narrative_match.group(1)
                if env_match:
                    environment = env_match.group(1)
                if not raw_narrative:
                    raw_narrative = res.get("description", "")
                incident_status = "INCIDENT_DETECTED" if res.get("confirmed") else "ROUTINE_NORMAL"
                confidence = res.get("confidence", 0.85)

        # Strictly sanitize narrative to guarantee 2-4 clean non-technical sentences
        final_narrative = self._sanitize_narrative(raw_narrative, threat_summary=threat_summary)

        return {
            "success": True,
            "environment": environment,
            "narrative_summary": final_narrative,
            "key_events": [],
            "incident_status": incident_status,
            "confidence": confidence,
            "latency_seconds": round(time.time() - t0, 1),
        }

    @staticmethod
    def _sanitize_narrative(text: str, threat_summary: Optional[Dict] = None) -> str:
        """Ensure the narrative is strictly a clean, 2-4 sentence non-technical summary."""
        cleaned, _ = KimiVLProvider._clean_thinking_tokens(text or "")
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

        # If it's a JSON string, extract the narrative
        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                parsed = json.loads(cleaned)
                cleaned = parsed.get("narrative_summary") or parsed.get("what_happened") or ""
                cleaned, _ = KimiVLProvider._clean_thinking_tokens(cleaned)
            except Exception:
                cleaned = ""

        # Reject if still contains think tags, timestamp spam, or raw code
        is_bad = (
            not cleaned
            or any(t in cleaned for t in ["<think>", "◁think▷", "◁/think▷", "</think>"])
            or bool(re.search(r"00:\d\d,\s*00:\d\d", cleaned))
            or bool(re.search(r"\d:\d\d\s*-\s*\d:\d\d:\s*Routine", cleaned))
            or len(cleaned) < 25
        )

        if not is_bad:
            return cleaned.strip()

        # Fallback to pristine 2-3 sentence executive human narrative
        if not threat_summary:
            return "Surveillance recording proceeded normally with no security incidents or safety hazards observed."

        risk = threat_summary.get("risk_level", "NORMAL")
        rec = threat_summary.get("recommendation", "Normal operations.")
        final = threat_summary.get("final_incident", "")
        weapons_c = threat_summary.get("weapons_count", 0)
        fights_c = threat_summary.get("fights_count", 0)
        fires_c = threat_summary.get("fires_count", 0)
        animal_assaults_c = threat_summary.get("animal_assaults_count", 0)
        animals_c = threat_summary.get("animals_count", 0)
        # Say "confirmed" only if a vision model really confirmed it.
        how = ("detected and confirmed by the AI vision check" if threat_summary.get("vlm_verified")
               else "detected by the camera detectors (not yet confirmed by the AI vision check; please review the footage)")

        if animal_assaults_c > 0 or final == "ANIMAL_ASSAULT":
            return f"Surveillance initially recorded routine activity in the area. A possible animal attack (dog attack) was {how}. {rec}"
        elif fires_c > 0 or final == "FIRE_SMOKE":
            return f"Surveillance footage initially captured normal conditions in the monitored area. Possible fire or smoke was {how}. {rec}"
        elif weapons_c > 0 or final == "WEAPON":
            return f"Surveillance recording initially shows routine baseline activity. A possible weapon (firearm/knife) was {how}. {rec}"
        elif fights_c > 0 or final == "FIGHT_ASSAULT":
            return f"Surveillance initially recorded normal interactions in the area. A possible physical altercation was {how}. {rec}"
        elif animals_c > 0 or final == "ROUTINE_ANIMAL":
            return "Surveillance footage shows peaceful routine activity. A non-aggressive animal was observed passing through the monitored zone with no safety risk."
        else:
            return "Surveillance recording proceeded normally with no physical threats, weapons, or safety hazards detected. Normal operational baseline confirmed."


    @staticmethod
    def _heuristic_fallback(frame: np.ndarray, prompt: str) -> Dict[str, Any]:
        """Abstention used when no verifier model is available."""
        reasoning = ("No AI verifier was available (Ollama and Kimi-VL offline), so this "
                     "detection was not double-checked. Review the footage.")

        return {
            "prompt": prompt,
            "reasoning": reasoning,
            "verified_threat": False,
            "confidence": 0.0,
            "model_used": "local-evidence-auditor",
            # No real model ran, so this is an abstention. success=False makes the
            # caller keep the detector's result instead of suppressing it.
            "success": False,
            "unavailable": True
        }


# ---------------------------------------------------------------------------
#  VLM Factory
# ---------------------------------------------------------------------------

class VLMFactory:
    _providers = {
        "xclip": XCLIPProvider,
        "kimi-vl": KimiVLProvider,
    }

    @classmethod
    def get_provider(cls, name: str):
        provider_class = cls._providers.get(name.lower())
        if not provider_class:
            raise ValueError(f"Unknown VLM provider: {name}. Available: {list(cls._providers.keys())}")
        return provider_class()

