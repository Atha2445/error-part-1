# Running Vigilinx on Windows (no graphics card needed)

This gets the whole system running on an ordinary Windows 10/11 PC:

- **Part 1–4:** the Vigilinx app (dashboard + backend). After this you can log in and
  analyse uploaded videos.
- **Part 5–7 (optional):** live CCTV cameras with automatic alerts, using Frigate and Ollama.

Every command below goes in **PowerShell** (Start menu → type *PowerShell*).
Run them in order; each block assumes you are still in the folder the previous block left you in.

---

## Part 1 — Install the tools (once)

| Tool | Where | Notes |
|---|---|---|
| **Python 3.11** | https://www.python.org/downloads/release/python-3119/ → *Windows installer (64-bit)* | Tick **"Add python.exe to PATH"** on the first screen. Must be 3.11. |
| **Node.js LTS** | https://nodejs.org | Default options. |
| **Git** | https://git-scm.com/download/win | Default options. |

Close and reopen PowerShell, then check:

```powershell
py -3.11 --version
node --version
git --version
```

Each should print a version number.

## Part 2 — Get the code

```powershell
cd $HOME\Documents
git clone https://github.com/Atha2445/vigilinx.git
cd vigilinx
git checkout feature/frigate-ollama
```

(Skip the `git checkout` line once this pull request is merged into `main`.)

## Part 3 — Set up the backend and dashboard

**Backend** (10–20 minutes the first time; downloads about 2–3 GB):

```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
```

**Settings file:**

```powershell
copy .env.example .env
.venv\Scripts\python -c "import secrets; print(secrets.token_hex(32))"
notepad .env
```

In Notepad, replace `replace-with-a-long-random-string` with the long text the second command
printed, then save. (Email settings are optional; fill them in if you want email alerts.)

> If a file `C:\Vigilinx\.env` or `C:\Vigilinx\Vigilinx.env` exists, the app reads that one
> **instead of** `backend\.env`. Either delete it or make your edits there.

**Dashboard (frontend):**

```powershell
cd ..\frontend
npm install
npm run build
```

`npm install` shows some warnings; that's normal. It's done when `npm run build` says
*"The build folder is ready to be deployed."*

## Part 4 — Start the app

```powershell
cd ..\backend
.venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Leave this window open while using Vigilinx. When Windows Firewall asks, allow **Private networks**
if other computers on your network should open the dashboard.

1. Open **http://localhost:8000** in a browser.
2. Log in with username **`admin`**, password **`admin`**.
3. Change the password straight away in the **Admin** section.

You can now upload videos for analysis. The app keeps its data in `C:\Vigilinx`.

**Next time**, only Part 4's two commands are needed (from the `vigilinx` folder: `cd backend`, then the
`uvicorn` line). To stop it, press `Ctrl+C` in that window.

---

## Part 5 — Live cameras: install Docker Desktop and Ollama (once)

1. **Docker Desktop:** https://www.docker.com/products/docker-desktop/ . During setup keep
   **"Use WSL 2"** ticked. Restart the PC if asked, then open Docker Desktop and wait until it
   says *Engine running*.
2. **Ollama** (the AI that double-checks each incident): https://ollama.com/download → Windows.
   Then download the vision model (about 3 GB):

   ```powershell
   ollama pull qwen3-vl:4b
   ```

   If that fails because the network blocks Ollama's download server, get the same model from
   Docker Hub instead (from the `vigilinx` folder, with the Ollama app open):

   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\frigate\scripts\import_qwen_from_dockerhub.ps1
   ```

## Part 6 — Set up Frigate (the camera system)

From the `vigilinx` folder:

```powershell
cd deploy\frigate\cpu
copy .env.example .env
notepad .env
```

Enter the username and password you use to view the cameras (the DVR/NVR login). Save.

```powershell
copy config\config.example.yml config\config.yml
notepad config\config.yml
```

Under `cameras:`, change the IP address in both `rtsp://` lines to your camera's or DVR's.
The file lists the right paths for Hikvision/Prama and CP Plus/Dahua. For more cameras,
copy the `main_gate:` block, give it a new name (letters, numbers, `_` only) and change the
channel number. Save.

Build the detection model (once, 5–15 minutes), then start Frigate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export_yolov9.ps1
docker compose up -d
```

Get Frigate's first login password:

```powershell
docker logs vigilinx-frigate 2>&1 | Select-String "Password:"
```

Open **http://localhost:8971**, log in as `admin` with that password, and check that every camera
shows a picture. If one is black, its RTSP address or password is wrong: fix `config\config.yml`
and run `docker compose restart frigate`.

## Part 7 — Connect Vigilinx to the cameras

Open the backend settings again (from the `vigilinx` folder):

```powershell
notepad backend\.env
```

Change and add these lines, then save:

```
FRIGATE_BRIDGE_ENABLED=true

# CPU-only PC: give the AI more time and less to look at
BRIDGE_VERIFY_FRAMES=3
OLLAMA_TIMEOUT=300
OLLAMA_IMAGE_SIZE=512
```

To get alerts on Telegram (free, recommended):

1. In Telegram, message **@BotFather**, send `/newbot`, follow the steps, copy the **token**.
2. Add the new bot to the guards' Telegram group and send any message in the group.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser (put your token in place of `<TOKEN>`)
   and find `"chat":{"id":` followed by a number (group ids start with `-`).
4. In `backend\.env` set:
   ```
   TELEGRAM_BOT_TOKEN=<the token>
   TELEGRAM_CHAT_IDS=<the chat id>
   ```

Restart the app: in the window from Part 4 press `Ctrl+C`, then run the `uvicorn` line again.

**Check it's working** (in a new PowerShell window; use your Vigilinx admin password):

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/auth/login -ContentType "application/json" -Body '{"username":"admin","password":"YOUR-PASSWORD"}'
Invoke-RestMethod -Uri http://localhost:8000/api/frigate/status -Headers @{ Authorization = "Bearer $($login.token)" } | ConvertTo-Json
```

You want to see `"enabled": true`, `"mqtt_connected": true` and, under `"verifier"`, `"available": true`.
`"events"` goes up as people walk past the cameras.

---

## What to expect on a PC without a graphics card

- **Cameras:** about 2–4 cameras on a modern 4-core processor. More than that needs a graphics
  card or a dedicated Linux box.
- **Alert delay:** each alert waits ~20 seconds for Frigate to save the recording, then the AI check
  runs on the processor, which can take one to a few minutes. If Ollama is too slow or not running,
  Vigilinx still alerts, marked *not double-checked*.
- **Every person and animal is checked by the AI.** With people in view all day, checks queue up on
  a processor. If alerts come too late, add `BRIDGE_CHECK_COOLDOWN=120` (or `BRIDGE_MIN_PEOPLE=2` to
  skip single passers-by) to `backend/.env`.
- **Leave it running:** the PC must stay on, with Docker Desktop, Ollama and the Part 4 window open.
  Turn off sleep in Windows power settings.

## Troubleshooting

| Problem | Fix |
|---|---|
| `py` is not recognized | Reinstall Python 3.11 with *Add to PATH* ticked, then reopen PowerShell. |
| `pip install` fails on `llama-cpp-python` | You're on an old copy; `git pull`. It's now optional (`requirements-kimi.txt`). |
| Browser shows `{"detail":"Not Found"}` at localhost:8000 | The dashboard wasn't built: redo the `frontend` commands in Part 3. |
| Logged out every time the app restarts | `JWT_SECRET_KEY` isn't set in `.env` (Part 3). |
| `docker` is not recognized / engine not running | Open Docker Desktop and wait for *Engine running*. |
| Status shows `"mqtt_connected": false` | Frigate isn't running: `cd deploy\frigate\cpu` then `docker compose up -d`. |
| Status shows `"available": false` under `"verifier"` | Open the Ollama app, and run `ollama pull qwen3-vl:4b` (if that fails: `powershell -ExecutionPolicy Bypass -File deploy\frigate\scripts\import_qwen_from_dockerhub.ps1`). |
| `"clip_failures"` keeps rising | Recording isn't working: check the camera's `record` stream path in `config\config.yml`. |
