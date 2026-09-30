# Running Vigilinx on Ubuntu (no graphics card needed)

This gets the whole system running on an ordinary Ubuntu 22.04 or 24.04 PC:

- **Part 1–4:** the Vigilinx app (dashboard + backend). After this you can log in and
  analyse uploaded videos.
- **Part 5–7 (optional):** live CCTV cameras with automatic alerts, using Frigate and Ollama.
- **Part 8 (recommended):** start everything automatically when the PC boots.

Every command below goes in a **Terminal** (`Ctrl+Alt+T`). Run them in order; each block assumes
you are still in the folder the previous block left you in. Commands starting with `sudo` ask for
your Ubuntu password.

---

## Part 1 — Install the tools (once)

```bash
sudo apt update
sudo apt install -y git curl build-essential

# Node.js 22 (Ubuntu's own version is too old for the dashboard)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# uv: installs the exact Python version the app needs (3.11) without touching Ubuntu's own Python
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

Check:

```bash
node --version    # v22.x
uv --version
git --version
```

## Part 2 — Get the code

```bash
cd ~
git clone https://github.com/Atha2445/vigilinx.git
cd vigilinx
git checkout feature/frigate-ollama
```

(Skip the `git checkout` line once this pull request is merged into `main`.)

## Part 3 — Set up the backend and dashboard

**Backend:**

```bash
cd backend
uv venv --python 3.11 .venv

# Optional but recommended on a PC without a graphics card: the CPU-only
# version of PyTorch saves about 2 GB. If this line errors, skip it.
uv pip install --python .venv/bin/python torch torchvision --index-url https://download.pytorch.org/whl/cpu

uv pip install --python .venv/bin/python -r requirements.txt
```

**Settings file:**

```bash
cp .env.example .env
sed -i "s/^JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')/" .env
nano .env
```

The `sed` line fills in `JWT_SECRET_KEY` for you (it keeps people logged in across restarts).
In `nano`, fill in the email settings if you want email alerts, then save with `Ctrl+O`, `Enter`, `Ctrl+X`.

> The app keeps its data in `backend/data`. If a file `backend/data/.env` exists, it is read
> **instead of** `backend/.env`.

**Dashboard (frontend):**

```bash
cd ../frontend
npm install
npm run build
```

`npm install` shows some warnings; that's normal. It's done when `npm run build` says
*"The build folder is ready to be deployed."*

## Part 4 — Start the app

```bash
cd ../backend
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

1. Open **http://localhost:8000** in a browser.
2. Log in with username **`admin`**, password **`admin`**.
3. Change the password straight away in the **Admin** section.

You can now upload videos for analysis. Other computers on the network can open
`http://<this-pc's-ip>:8000` (find the IP with `hostname -I`). If Ubuntu's firewall is on, allow it
with `sudo ufw allow 8000/tcp`.

Stop it with `Ctrl+C`. To start it again later: `cd ~/vigilinx/backend` and run the `uvicorn` line.
Part 8 makes it start by itself instead.

---

## Part 5 — Live cameras: install Docker and Ollama (once)

**Docker:**

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

**Log out of Ubuntu and back in** (so you can use `docker` without `sudo`), then check:

```bash
docker run --rm hello-world
```

**Ollama** (the AI that double-checks each incident) and its vision model (about 3 GB):

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3-vl:4b
```

Ollama installs itself as a background service that starts on boot.

If `ollama pull` fails (some office or ISP networks block Ollama's download server), get the same
model from Docker Hub instead:

```bash
~/vigilinx/deploy/frigate/scripts/import_qwen_from_dockerhub.sh
```

## Part 6 — Set up Frigate (the camera system)

```bash
cd ~/vigilinx/deploy/frigate/cpu
cp .env.example .env
nano .env
```

Enter the username and password you use to view the cameras (the DVR/NVR login). Save.

```bash
cp config/config.example.yml config/config.yml
nano config/config.yml
```

Under `cameras:`, change the IP address in both `rtsp://` lines to your camera's or DVR's.
The file lists the right paths for Hikvision/Prama and CP Plus/Dahua. For more cameras,
copy the `main_gate:` block, give it a new name (letters, numbers, `_` only) and change the
channel number. Save.

Build the detection model (once, 5–15 minutes), then start Frigate:

```bash
./scripts/export_yolov9.sh
docker compose up -d
```

Get Frigate's first login password:

```bash
docker logs vigilinx-frigate 2>&1 | grep "Password:"
```

Open **http://localhost:8971**, log in as `admin` with that password, and check that every camera
shows a picture. If one is black, its RTSP address or password is wrong: fix `config/config.yml`
and run `docker compose restart frigate`.

Frigate and Mosquitto restart automatically when the PC boots.

## Part 7 — Connect Vigilinx to the cameras

```bash
nano ~/vigilinx/backend/.env
```

Change and add these lines, then save:

```
FRIGATE_BRIDGE_ENABLED=true

# PC without a graphics card: give the AI more time and less to look at
BRIDGE_VERIFY_FRAMES=3
OLLAMA_TIMEOUT=300
OLLAMA_IMAGE_SIZE=512
```

To get alerts on Telegram (free, recommended):

1. In Telegram, message **@BotFather**, send `/newbot`, follow the steps, copy the **token**.
2. Add the new bot to the guards' Telegram group and send any message in the group.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser (put your token in place of `<TOKEN>`)
   and find `"chat":{"id":` followed by a number (group ids start with `-`).
4. In `backend/.env` set:
   ```
   TELEGRAM_BOT_TOKEN=<the token>
   TELEGRAM_CHAT_IDS=<the chat id>
   ```

Restart the app (`Ctrl+C` in its terminal, then the `uvicorn` line again; or, after Part 8,
`sudo systemctl restart vigilinx`).

**Check it's working** (use your Vigilinx admin password):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"YOUR-PASSWORD"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s http://localhost:8000/api/frigate/status -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

You want to see `"enabled": true`, `"mqtt_connected": true` and, under `"verifier"`, `"available": true`.
`"events"` goes up as people walk past the cameras.

## Part 8 — Start Vigilinx automatically on boot (recommended)

Stop the app if it's running in a terminal (`Ctrl+C`), then:

```bash
sudo tee /etc/systemd/system/vigilinx.service > /dev/null <<EOF
[Unit]
Description=Vigilinx AI Surveillance
After=network-online.target docker.service ollama.service
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$HOME/vigilinx/backend
ExecStart=$HOME/vigilinx/backend/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now vigilinx
```

Useful commands afterwards:

```bash
sudo systemctl status vigilinx      # is it running?
sudo systemctl restart vigilinx     # after editing backend/.env
journalctl -u vigilinx -f           # live log (Ctrl+C to leave)
```

Also stop Ubuntu from sleeping: *Settings → Power → Automatic Suspend → Off*.

---

## What to expect on a PC without a graphics card

- **Cameras:** about 2–4 cameras on a modern 4-core processor. More than that needs a graphics
  card (see `deploy/frigate/README.md` for the NVIDIA setup).
- **Alert delay:** each alert waits ~20 seconds for Frigate to save the recording, then the AI check
  runs on the processor, which can take one to a few minutes. If Ollama is too slow or not running,
  Vigilinx still alerts, marked *not double-checked*.
- **Every person and animal is checked by the AI.** With people in view all day, checks queue up on
  a processor. If alerts come too late, add `BRIDGE_CHECK_COOLDOWN=120` (or `BRIDGE_MIN_PEOPLE=2` to
  skip single passers-by) to `backend/.env`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `uv: command not found` | Run `source $HOME/.local/bin/env`, or open a new terminal. |
| `permission denied ... docker.sock` | You didn't log out and back in after Part 5. |
| Browser shows `{"detail":"Not Found"}` at localhost:8000 | The dashboard wasn't built: redo the `frontend` commands in Part 3. |
| Logged out every time the app restarts | `JWT_SECRET_KEY` isn't set in `backend/.env` (Part 3). |
| `address already in use` on port 8000 | It's already running (maybe as the Part 8 service): `sudo systemctl stop vigilinx`. |
| Status shows `"mqtt_connected": false` | Frigate isn't running: `cd ~/vigilinx/deploy/frigate/cpu && docker compose up -d`. |
| Status shows `"available": false` under `"verifier"` | `ollama pull qwen3-vl:4b` (or, if that fails, `deploy/frigate/scripts/import_qwen_from_dockerhub.sh`), and check `systemctl status ollama`. |
| `"clip_failures"` keeps rising | Recording isn't working: check the camera's `record` stream path in `config/config.yml`. |
