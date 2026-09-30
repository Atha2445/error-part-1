# Frigate on a PC without a graphics card

Runs Frigate on the CPU (OpenVINO; works on Intel and AMD) plus Mosquitto, with
Docker Desktop on Windows or Docker Engine on Ubuntu. Ollama runs natively, not in Docker.

Step-by-step instructions, including running the Vigilinx app itself:
- **Windows:** [SETUP_WINDOWS.md](../../../SETUP_WINDOWS.md) (Parts 5–7)
- **Ubuntu:** [SETUP_UBUNTU.md](../../../SETUP_UBUNTU.md) (Parts 5–7)

| File | Purpose |
|---|---|
| `docker-compose.yml` | Frigate 0.18.0 (standard image) + Mosquitto |
| `config/config.example.yml` | CPU config: YOLOv9-tiny at 320px, 5 fps; validated against Frigate 0.18.0 |
| `scripts/export_yolov9.ps1` | Builds the model with Docker (Windows PowerShell) |
| `scripts/export_yolov9.sh` | Builds the model with Docker (Ubuntu) |
| `.env.example` | Camera username and password |
