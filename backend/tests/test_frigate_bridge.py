"""Tests for the Frigate bridge and the Ollama verifier (no GPU, Frigate or Ollama needed)."""
import json
import os
import sys
import tempfile

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.frigate_bridge import ActiveObjects, BridgeConfig, FrigateBridge, Job, triggers_for  # noqa: E402
from services import ollama_verifier as ov  # noqa: E402


def ev(obj_id, label, camera="gate", kind="new", stationary=False, score=0.8, end=False):
    after = {"id": obj_id, "camera": camera, "label": label, "top_score": score,
             "stationary": stationary, "current_zones": [], "false_positive": False,
             "end_time": 123.0 if end else None}
    return {"type": "end" if end else kind, "before": after, "after": after}


def make_clip(n=30, fps=15, size=(320, 240)):
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for i in range(n):
        frame = np.full((size[1], size[0], 3), (i * 7) % 255, np.uint8)
        out.write(frame)
    out.release()
    return path


class FakeEngine:
    """Returns the given threat type on frames in [hit_from, hit_to)."""

    def __init__(self, threat=None, hit_from=5, hit_to=15):
        self.threat, self.hit_from, self.hit_to = threat, hit_from, hit_to
        self.enable_vlm = True
        self.frames_seen = 0

    def reset_stream_state(self, cam):
        self.frames_seen = 0

    def scan_frame(self, frame, camera_id, annotate, timestamp_sec):
        i = self.frames_seen
        self.frames_seen += 1
        threats = []
        if self.threat and self.hit_from <= i < self.hit_to:
            threats = [{"type": self.threat, "confidence": 0.5 + i / 100}]
        return {"threats": threats, "annotated_frame": frame}


class FakeVerifier:
    def __init__(self, result):
        self.result, self.calls = result, []

    def verify(self, frames, context_type, clip_seconds=None):
        self.calls.append((len(frames), context_type))
        return dict(self.result)


class FakeNotifier:
    enabled = True

    def __init__(self):
        self.sent = []

    def send_alert(self, caption, photo_jpeg=None, clip_path=None):
        self.sent.append({"caption": caption, "photo": photo_jpeg is not None,
                          "clip": clip_path and os.path.exists(clip_path)})
        return 1


def bridge(engine, verifier, tmp_path, **cfg):
    c = BridgeConfig(output_dir=str(tmp_path), recording_delay=0, **cfg)
    notifier = FakeNotifier()
    b = FrigateBridge(c, threat_engine=engine, verifier=verifier, notifier=notifier,
                      clip_fetcher=lambda cam, s, e: make_clip(), sleep=lambda s: None)
    return b, notifier


# ---- triggers ---------------------------------------------------------------

def test_triggers():
    p = {"label": "person", "stationary": False}
    assert triggers_for([]) == set()
    assert triggers_for([p]) == {"PERSON"}
    assert triggers_for([{"label": "person", "stationary": True}]) == {"PERSON"}  # someone standing still
    assert triggers_for([p], min_people=2) == set()
    assert triggers_for([{"label": "dog", "stationary": False}]) == {"ANIMAL"}  # animal on its own
    assert triggers_for([{"label": "cow", "stationary": True}]) == {"ANIMAL"}
    assert triggers_for([p, {"label": "dog", "stationary": False}]) == {"PERSON", "ANIMAL"}
    assert triggers_for([{"label": "knife", "stationary": True}]) == {"WEAPON"}
    assert triggers_for([{"label": "car", "stationary": False}]) == set()


def test_active_objects_add_and_end():
    objs = ActiveObjects()
    objs.update(ev("a", "person"))
    objs.update(ev("b", "dog"))
    assert {o["label"] for o in objs.on_camera("gate")} == {"person", "dog"}
    objs.update(ev("b", "dog", end=True))
    assert [o["label"] for o in objs.on_camera("gate")] == ["person"]


def test_event_queues_once_then_cools_down(tmp_path):
    b, _ = bridge(FakeEngine(), FakeVerifier({}), tmp_path)
    assert [j.kind for j in b.handle_event(ev("a", "person"))] == ["PERSON"]
    jobs = b.handle_event(ev("b", "dog"))
    assert [j.kind for j in jobs] == ["ANIMAL"]
    assert b.handle_event(ev("b", "dog", kind="update")) == []  # already pending
    b._pending.clear()
    assert b.handle_event(ev("b", "dog", kind="update")) == []  # within check cooldown


def test_cameras_are_independent(tmp_path):
    b, _ = bridge(FakeEngine(), FakeVerifier({}), tmp_path)
    b.handle_event(ev("a", "person", camera="gate"))
    b.handle_event(ev("b", "dog", camera="gate"))
    jobs = b.handle_event(ev("c", "person", camera="lobby"))
    assert [(j.camera, j.kind) for j in jobs] == [("lobby", "PERSON")]
    jobs = b.handle_event(ev("d", "dog", camera="lobby"))
    assert [(j.camera, j.kind) for j in jobs] == [("lobby", "ANIMAL")]


# ---- decisions --------------------------------------------------------------

CONFIRM = {"success": True, "verified_threat": True, "confidence": 0.9,
           "reasoning": "two men punching", "model_used": "ollama:test"}
REJECT = {"success": True, "verified_threat": False, "confidence": 0.8,
          "reasoning": "people hugging", "model_used": "ollama:test"}
DOWN = {"success": False, "unavailable": True, "verified_threat": False, "confidence": 0.0}


def test_confirmed_fight_alerts_with_photo_and_clip(tmp_path):
    verifier = FakeVerifier(CONFIRM)
    b, notifier = bridge(FakeEngine("FIGHT_ASSAULT"), verifier, tmp_path)
    out = b.process_job(Job("gate", "PERSON", 1000.0, ["a", "b"]))
    assert out["status"] == "confirmed"
    assert verifier.calls and verifier.calls[0][1] == "fight_verify" and verifier.calls[0][0] > 1
    assert len(notifier.sent) == 1
    sent = notifier.sent[0]
    assert "Fight in progress" in sent["caption"] and "two men punching" in sent["caption"]
    assert sent["photo"] and sent["clip"]
    assert any(f.endswith(".jpg") for f in os.listdir(tmp_path))


def test_rejected_by_verifier_does_not_alert(tmp_path):
    b, notifier = bridge(FakeEngine("FIGHT_ASSAULT"), FakeVerifier(REJECT), tmp_path)
    assert b.process_job(Job("gate", "PERSON", 1000.0, []))["status"] == "rejected"
    assert notifier.sent == []


def test_low_confidence_yes_counts_as_no(tmp_path):
    weak = dict(CONFIRM, confidence=0.3)
    b, notifier = bridge(FakeEngine("FIGHT_ASSAULT"), FakeVerifier(weak), tmp_path)
    assert b.process_job(Job("gate", "PERSON", 1000.0, []))["status"] == "rejected"
    assert notifier.sent == []


def test_verifier_down_still_alerts_marked_unverified(tmp_path):
    """The original bug: a broken verifier silenced every detection."""
    b, notifier = bridge(FakeEngine("ANIMAL_ASSAULT"), FakeVerifier(DOWN), tmp_path)
    assert b.process_job(Job("gate", "ANIMAL", 1000.0, []))["status"] == "unverified"
    assert "NOT double-checked" in notifier.sent[0]["caption"]


def test_verifier_down_can_be_set_to_stay_quiet(tmp_path):
    b, notifier = bridge(FakeEngine("ANIMAL_ASSAULT"), FakeVerifier(DOWN), tmp_path,
                         alert_when_unverified=False)
    assert b.process_job(Job("gate", "ANIMAL", 1000.0, []))["status"] == "unverified_dropped"
    assert notifier.sent == []


def test_nothing_found_skips_verifier_when_verify_all_is_off(tmp_path):
    verifier = FakeVerifier(CONFIRM)
    b, notifier = bridge(FakeEngine(None), verifier, tmp_path, verify_all=False)
    assert b.process_job(Job("gate", "PERSON", 1000.0, []))["status"] == "clear"
    assert verifier.calls == [] and notifier.sent == []


def test_nothing_found_still_asks_ai_and_alerts_if_it_sees_something(tmp_path):
    verifier = FakeVerifier(CONFIRM)
    b, notifier = bridge(FakeEngine(None), verifier, tmp_path, verify_frames=3)
    out = b.process_job(Job("gate", "PERSON", 1000.0, []))
    assert out["status"] == "confirmed" and out["threat"] == "SECURITY_INCIDENT"
    assert verifier.calls == [(3, "security_audit")] and len(notifier.sent) == 1
    assert b.stats["ai_only_confirmed"] == 1


def test_nothing_found_and_ai_says_no_is_quiet(tmp_path):
    for verdict in (REJECT, DOWN):
        verifier = FakeVerifier(verdict)
        b, notifier = bridge(FakeEngine(None), verifier, tmp_path)
        assert b.process_job(Job("gate", "ANIMAL", 1000.0, []))["status"] == "clear"
        assert verifier.calls[0][1] == "animal_assault_verify" and notifier.sent == []


def test_same_incident_found_by_two_checks_alerts_once(tmp_path):
    b, notifier = bridge(FakeEngine("WEAPON"), FakeVerifier(CONFIRM), tmp_path)
    b._clock = lambda: 5000.0
    assert b.process_job(Job("gate", "WEAPON", 5000.0, []))["status"] == "confirmed"
    assert b.process_job(Job("gate", "PERSON", 5000.0, []))["status"] == "confirmed"
    assert len(notifier.sent) == 1


def test_frigate_knife_is_checked_even_if_weapon_model_misses(tmp_path):
    verifier = FakeVerifier(CONFIRM)
    b, notifier = bridge(FakeEngine(None), verifier, tmp_path)
    out = b.process_job(Job("gate", "WEAPON", 1000.0, ["k"], knife_score=0.6))
    assert out["status"] == "confirmed" and verifier.calls[0][1] == "weapon_verify"


def test_missing_recording_reports_no_clip(tmp_path):
    b, notifier = bridge(FakeEngine("FIGHT_ASSAULT"), FakeVerifier(CONFIRM), tmp_path)
    b._fetch_clip = lambda cam, s, e: None
    assert b.process_job(Job("gate", "PERSON", 1000.0, []))["status"] == "no_clip"
    assert b.stats["clip_failures"] == 1


def test_alert_cooldown_blocks_repeat_checks(tmp_path):
    b, _ = bridge(FakeEngine("FIGHT_ASSAULT"), FakeVerifier(CONFIRM), tmp_path)
    b._clock = lambda: 5000.0
    job = b.handle_event(ev("a", "person"))[0]
    b.process_job(job)
    b._pending.clear()
    b._last_check.clear()
    assert b.handle_event(ev("c", "person")) == []  # still inside alert cooldown


def test_logs_to_detections_table(tmp_path):
    import sqlite3
    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE detections (id INTEGER PRIMARY KEY, video_path TEXT, frame_number INT,"
                 " detected_action TEXT, confidence REAL, is_alert BOOL, occupancy_count INT, timestamp TEXT)")
    conn.commit()
    conn.close()
    b, _ = bridge(FakeEngine("FIGHT_ASSAULT"), FakeVerifier(CONFIRM), tmp_path)
    b.db_path = db
    b.process_job(Job("gate", "PERSON", 1000.0, []))
    rows = sqlite3.connect(db).execute("SELECT detected_action, is_alert FROM detections").fetchall()
    assert rows == [("LIVE FIGHT_ASSAULT [confirmed] on gate", 1)]


def test_alert_adds_dashboard_verdict(tmp_path):
    import json
    import sqlite3
    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE video_verdicts (id INTEGER PRIMARY KEY, video_path TEXT, total_analyzed INT,"
                 " suspicious_frames INT, normal_frames INT, suspicious_percentage REAL, risk_level TEXT,"
                 " needs_attention INT, recommendation TEXT, ai_summary TEXT, timestamp TEXT)")
    conn.commit()
    conn.close()
    b, _ = bridge(FakeEngine("FIGHT_ASSAULT"), FakeVerifier(DOWN), tmp_path)
    b.db_path = db
    b.process_job(Job("gate", "PERSON", 1000.0, []))
    path, risk, attn, details = sqlite3.connect(db).execute(
        "SELECT video_path, risk_level, needs_attention, details_json FROM video_verdicts").fetchone()
    assert path.startswith("incident_gate_1000_fight_assault") and risk.startswith("[CRITICAL]") and attn == 1
    details = json.loads(details)
    assert details["final_incident"] == "FIGHT_ASSAULT" and details["vlm_verified"] is False


# ---- Ollama verifier --------------------------------------------------------

class _Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_parse_handles_think_blocks_and_fences():
    assert ov._parse('<think>hmm</think>```json\n{"confirmed": true, "confidence": 1.4, "description": "x"}\n```') == \
        {"confirmed": True, "confidence": 1.0, "description": "x"}
    assert ov._parse("I think yes") is None
    assert ov._parse('{"confirmed": "yes", "confidence": 1}') is None


def test_verifier_sends_frames_and_schema(monkeypatch):
    sent = {}
    monkeypatch.setattr(ov.httpx, "get", lambda url, timeout: _Resp({"models": [{"name": "qwen3-vl:4b"}]}))

    def fake_post(url, json, timeout):
        sent.update(json)
        return _Resp({"message": {"content": '{"confirmed": true, "confidence": 0.8, "description": "dog biting leg"}'}})

    monkeypatch.setattr(ov.httpx, "post", fake_post)
    v = ov.OllamaVerifier(base_url="http://x", model="qwen3-vl:4b")
    frames = [np.zeros((1080, 1920, 3), np.uint8)] * 4
    res = v.verify(frames, "animal_assault_verify", clip_seconds=4)
    assert res["success"] and res["verified_threat"] and res["confidence"] == 0.8
    msg = sent["messages"][0]
    assert len(msg["images"]) == 4 and "dog" in msg["content"] and "4 images" in msg["content"]
    assert sent["format"]["required"] == ["confirmed", "confidence", "description"]
    assert sent["stream"] is False


def test_verifier_unavailable_abstains(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("refused")
    monkeypatch.setattr(ov.httpx, "get", boom)
    res = ov.OllamaVerifier(base_url="http://x").verify([np.zeros((10, 10, 3), np.uint8)], "fight_verify")
    assert res["success"] is False and res["verified_threat"] is False


def test_verifier_model_not_pulled_abstains(monkeypatch):
    monkeypatch.setattr(ov.httpx, "get", lambda url, timeout: _Resp({"models": [{"name": "llama3:latest"}]}))
    res = ov.OllamaVerifier(base_url="http://x", model="qwen3-vl:4b").verify(
        [np.zeros((10, 10, 3), np.uint8)], "fight_verify")
    assert res["success"] is False


def test_verifier_garbage_answer_abstains(monkeypatch):
    monkeypatch.setattr(ov.httpx, "get", lambda url, timeout: _Resp({"models": [{"name": "qwen3-vl:4b"}]}))
    monkeypatch.setattr(ov.httpx, "post", lambda url, json, timeout: _Resp({"message": {"content": "Sure!"}}))
    res = ov.OllamaVerifier(base_url="http://x", model="qwen3-vl:4b").verify(
        [np.zeros((10, 10, 3), np.uint8)], "fight_verify")
    assert res["success"] is False


# ---- CPU tuning settings --------------------------------------------------------

def test_cpu_settings_from_env(monkeypatch):
    monkeypatch.setenv("BRIDGE_VERIFY_FRAMES", "3")
    monkeypatch.setenv("OLLAMA_TIMEOUT", "300")
    monkeypatch.setenv("OLLAMA_IMAGE_SIZE", "512")
    assert BridgeConfig.from_env().verify_frames == 3
    v = ov.OllamaVerifier(base_url="http://x")
    assert v.timeout == 300.0 and v.image_size == 512


def test_verify_frames_setting_limits_frames_sent(tmp_path):
    verifier = FakeVerifier(CONFIRM)
    b, _ = bridge(FakeEngine("FIGHT_ASSAULT"), verifier, tmp_path, verify_frames=3)
    b.process_job(Job("gate", "PERSON", 1000.0, []))
    assert verifier.calls[0][0] == 3


def test_single_verify_frame_uses_peak(tmp_path):
    verifier = FakeVerifier(CONFIRM)
    b, _ = bridge(FakeEngine("FIGHT_ASSAULT"), verifier, tmp_path, verify_frames=1)
    b.process_job(Job("gate", "PERSON", 1000.0, []))
    assert verifier.calls[0][0] == 1


def test_image_size_setting_shrinks_frames(monkeypatch):
    import base64 as b64
    sent = {}
    monkeypatch.setattr(ov.httpx, "get", lambda url, timeout: _Resp({"models": [{"name": "qwen3-vl:4b"}]}))

    def fake_post(url, json, timeout):
        sent.update(json, timeout=timeout)
        return _Resp({"message": {"content": '{"confirmed": false, "confidence": 0.9, "description": "calm"}'}})

    monkeypatch.setattr(ov.httpx, "post", fake_post)
    v = ov.OllamaVerifier(base_url="http://x", model="qwen3-vl:4b", timeout=300, image_size=512)
    v.verify([np.zeros((1080, 1920, 3), np.uint8)], "fight_verify")
    img = cv2.imdecode(np.frombuffer(b64.b64decode(sent["messages"][0]["images"][0]), np.uint8), cv2.IMREAD_COLOR)
    assert max(img.shape[:2]) == 512 and sent["timeout"] == 300


def test_fight_check_without_dog_verifies_animal_hits_as_fight(tmp_path):
    # Tangled bodies in a scuffle can look like a dog to the engine; if Frigate
    # saw no dog, the verifier must be asked about a fight, not a dog attack.
    v = FakeVerifier(CONFIRM)
    b, _ = bridge(FakeEngine("ANIMAL_ASSAULT"), v, tmp_path)
    out = b.process_job(Job("gate", "PERSON", 1000.0, [], dog_seen=False))
    assert out["threat"] == "FIGHT_ASSAULT" and v.calls[0][1] == "fight_verify"


def test_person_check_leaves_animal_hits_to_the_animal_check_when_a_dog_is_seen(tmp_path):
    v = FakeVerifier(REJECT)
    b, _ = bridge(FakeEngine("ANIMAL_ASSAULT"), v, tmp_path)
    b.process_job(Job("gate", "PERSON", 1000.0, [], dog_seen=True))
    assert v.calls[0][1] == "security_audit"
    b.process_job(Job("gate", "ANIMAL", 1000.0, [], dog_seen=True))
    assert v.calls[1][1] == "animal_assault_verify"


def test_queued_job_records_whether_frigate_saw_a_dog(tmp_path):
    b, _ = bridge(FakeEngine(), FakeVerifier(CONFIRM), tmp_path)
    jobs = b.handle_event(ev("p1", "person"))
    assert [j.kind for j in jobs] == ["PERSON"] and jobs[0].dog_seen is False
    b2, _ = bridge(FakeEngine(), FakeVerifier(CONFIRM), tmp_path)
    for oid, label in (("p1", "person"), ("p2", "person"), ("d1", "dog")):
        jobs = b2.handle_event(ev(oid, label))
    assert jobs and all(j.dog_seen for j in jobs)
