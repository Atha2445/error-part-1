# Live cameras with Frigate + Ollama

This folder runs the three services Vigilinx needs for live CCTV. The Vigilinx
backend keeps running as before and connects to them.

| Service | What it does |
|---|---|
| **Frigate** 0.18.0 | Reads every camera over RTSP, records, and tracks people, animals and knives on the GPU |
| **Mosquitto** | Carries Frigate's events to Vigilinx |
| **Ollama** (`qwen3-vl:4b`) | Looks at a few frames of a flagged moment and answers "is this really a fight / weapon / dog attack?" |

## How an alert happens

1. Frigate sees a **person**, an **animal** (dog, cat, cow, horse, sheep) or a
   **knife** on a camera.
2. Vigilinx downloads the ~10 seconds of recording around that moment from Frigate
   and runs its own detectors on it (pose-based fight detector, weapon model,
   dog-contact logic).
3. Ollama checks 6 frames and answers yes/no:
   - if the detectors found something, about that (e.g. "is this really a fight?");
   - if they found nothing, whether anything dangerous is happening at all
     (a fight, a weapon, an animal attacking someone), so incidents the
     detectors miss are still caught. Set `BRIDGE_VERIFY_ALL=false` to skip this.
4. **Yes** → Telegram photo + clip, email, and an incident on the Vigilinx dashboard.
   **No** → logged, no alert.
   **Ollama down** → a detector hit still alerts, marked *not double-checked*, so
   the system never goes silent because the verifier broke.

Alerts arrive roughly 20–30 seconds after the event, because Frigate has to finish
writing the recording first. Checks are rate-limited per camera (30 s between
checks, 2 min between alerts of the same kind); tune in `backend/.env`.

Because every person and animal is now checked by Ollama, a camera with people
in view runs about one Ollama check every 30 seconds. On a GPU that is easy; on
a CPU-only PC one check takes 1–3 minutes, so checks queue up (at most one
waiting per camera and kind). If alerts arrive too late, raise
`BRIDGE_CHECK_COOLDOWN`, or set `BRIDGE_MIN_PEOPLE=2` so a single passer-by
isn't checked.

## Setup

> **No NVIDIA graphics card?** Follow [SETUP_WINDOWS.md](../../SETUP_WINDOWS.md) or
> [SETUP_UBUNTU.md](../../SETUP_UBUNTU.md) instead; both use the files in `cpu/`.

Needs Ubuntu with an NVIDIA GPU (16 GB recommended), the NVIDIA driver, Docker and the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

```bash
cd deploy/frigate
cp .env.example .env                       # camera username/password
cp config/config.example.yml config/config.yml
nano config/config.yml                     # add your cameras (RTSP paths are listed in the file)

./scripts/export_yolov9.sh                 # builds the detection model once (few minutes)

docker compose up -d
docker exec vigilinx-ollama ollama pull qwen3-vl:4b
```

If `ollama pull` fails because Ollama's download server (registry.ollama.ai) is blocked,
install the same model from Docker Hub instead:
`OLLAMA_CONTAINER=vigilinx-ollama ./scripts/import_qwen_from_dockerhub.sh`.

Check Frigate at `http://<server-ip>:8971`. The first login password is printed in
`docker logs vigilinx-frigate`. Draw object masks there over areas you want ignored.

Then in `backend/.env`:

```
FRIGATE_BRIDGE_ENABLED=true
TELEGRAM_BOT_TOKEN=...        # from @BotFather
TELEGRAM_CHAT_IDS=...         # guards' group id
```

Restart Vigilinx. `GET /api/frigate/status` (logged in) shows whether it is
connected, whether Ollama is reachable, and counts of checks, confirmations and
rejections.

## Tuning

- **Too many alerts from a busy area:** in Frigate, draw an object mask over areas
  to ignore (a road outside the gate, a TV in the lobby); masked objects never reach
  Vigilinx. Or raise `BRIDGE_MIN_CONFIDENCE`.
- **Missed incidents:** check `/api/frigate/status`. If `detector_hits` stays at 0,
  the local detectors aren't firing on your footage; if `rejected` is high, look at
  the reasons in the backend log.
- **Better verification:** `OLLAMA_VISION_MODEL=qwen3-vl:8b` is more accurate and
  still fits a 16 GB card alongside Frigate, but is slower.
- Guns aren't in Frigate's standard labels. Vigilinx's own weapon model still checks
  every flagged clip, but a gun alone (with nobody fighting and no knife) won't start
  a check. Training a custom Frigate model that includes guns would fix that.

## Licences to be aware of if you sell this

- The YOLOv9 model built by `export_yolov9.sh` comes from WongKinYiu/yolov9 (GPL-3.0).
- Vigilinx's own detectors use Ultralytics (AGPL-3.0).
- Frigate is MIT; Ollama is MIT; check the licence of whichever vision model you pull.
