@echo off
setlocal enabledelayedexpansion

REM ===================================================================
REM  Vigilinx Windows Build Script
REM  Produces: dist\Vigilinx\  (folder containing Vigilinx.exe + models)
REM ===================================================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%"
set "FRONTEND=%ROOT%..\frontend"
set "FIGHT_DIR=E:\Fight"
set "DIST=%BACKEND%dist\Vigilinx"
set "VENV_PYTHON=%BACKEND%.venv\Scripts\python.exe"
set "VENV_PIP=%BACKEND%.venv\Scripts\python.exe -m pip"
set "VENV_PYINSTALLER=%BACKEND%.venv\Scripts\pyinstaller.exe"

echo.
echo ===================================================
echo   Vigilinx Windows Build
echo ===================================================
echo.

REM ------------------------------------------------------------------
REM  Step 1: Ensure models/ has all required .pt weights
REM ------------------------------------------------------------------
echo [1/6] Checking model weights...

if not exist "%BACKEND%models" mkdir "%BACKEND%models"

REM Copy from Fight workspace if not already present
if exist "%FIGHT_DIR%\fire_smoke_detector_best.pt" (
    copy /Y "%FIGHT_DIR%\fire_smoke_detector_best.pt" "%BACKEND%models\" >nul
)
if exist "%FIGHT_DIR%\weapon_detector_best.pt" (
    copy /Y "%FIGHT_DIR%\weapon_detector_best.pt" "%BACKEND%models\" >nul
)
if exist "%FIGHT_DIR%\yolov8n.pt" (
    copy /Y "%FIGHT_DIR%\yolov8n.pt" "%BACKEND%models\" >nul
)
if exist "%FIGHT_DIR%\yolov8n-pose.pt" (
    copy /Y "%FIGHT_DIR%\yolov8n-pose.pt" "%BACKEND%models\" >nul
)

REM Move pose or coco models if in backend root
if exist "%BACKEND%yolov8n-pose.pt" (
    move /Y "%BACKEND%yolov8n-pose.pt" "%BACKEND%models\yolov8n-pose.pt" >nul
)
if exist "%BACKEND%yolov8n.pt" (
    move /Y "%BACKEND%yolov8n.pt" "%BACKEND%models\yolov8n.pt" >nul
)

echo    Verifying 4 Core Safety Detector Models:
if exist "%BACKEND%models\weapon_detector_best.pt" (echo    [OK] Weapons Detector: weapon_detector_best.pt) else (echo    [WARN] Missing: weapon_detector_best.pt)
if exist "%BACKEND%models\fire_smoke_detector_best.pt" (echo    [OK] Fire and Smoke Detector: fire_smoke_detector_best.pt) else (echo    [WARN] Missing: fire_smoke_detector_best.pt)
if exist "%BACKEND%models\yolov8n.pt" (echo    [OK] Animal / Stray Dog Detector: yolov8n.pt) else (echo    [WARN] Missing: yolov8n.pt)
if exist "%BACKEND%models\yolov8n-pose.pt" (echo    [OK] Fight / Assault Pose Detector: yolov8n-pose.pt) else (echo    [WARN] Missing: yolov8n-pose.pt)
echo.

REM ------------------------------------------------------------------
REM  Step 2: Create/activate Python virtual environment
REM ------------------------------------------------------------------
echo [2/6] Setting up Python virtual environment...

if not exist "%VENV_PYTHON%" (
    echo    Creating new venv...
    python -m venv "%BACKEND%.venv"
)

REM Ensure pre-built llama_cpp from Fight workspace is present
if not exist "%BACKEND%.venv\Lib\site-packages\llama_cpp" (
    if exist "%FIGHT_DIR%\venv\Lib\site-packages\llama_cpp" (
        echo    Copying pre-built llama_cpp from Fight workspace...
        xcopy /E /I /Q /Y "%FIGHT_DIR%\venv\Lib\site-packages\llama_cpp" "%BACKEND%.venv\Lib\site-packages\llama_cpp" >nul
        xcopy /E /I /Q /Y "%FIGHT_DIR%\venv\Lib\site-packages\llama_cpp_python*" "%BACKEND%.venv\Lib\site-packages\llama_cpp_python-0.3.35.dist-info\" >nul
        if exist "%FIGHT_DIR%\venv\Lib\site-packages\bin" (
            xcopy /E /I /Q /Y "%FIGHT_DIR%\venv\Lib\site-packages\bin" "%BACKEND%.venv\Lib\site-packages\bin\" >nul
        )
    )
)

echo    Installing dependencies...
%VENV_PIP% install --quiet --upgrade pip setuptools wheel
%VENV_PIP% install --quiet pyinstaller
%VENV_PIP% install --quiet -r "%BACKEND%requirements.txt"

echo    Python environment ready.
echo.

REM ------------------------------------------------------------------
REM  Step 3: Build frontend
REM ------------------------------------------------------------------
echo [3/6] Building frontend...

cd /d "%FRONTEND%"
if not exist "node_modules" (
    call npm install --silent
)
call npm run build
echo    Frontend build complete.
echo.

REM ------------------------------------------------------------------
REM  Step 4: Run PyInstaller
REM ------------------------------------------------------------------
echo [4/6] Running PyInstaller (this may take several minutes)...

cd /d "%BACKEND%"
"%VENV_PYINSTALLER%" --noconfirm --clean vigilinx.spec

if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller failed. Check the output above.
    exit /b 1
)
echo    PyInstaller build complete.
echo.

REM ------------------------------------------------------------------
REM  Step 5: Post-build bundle assembly
REM ------------------------------------------------------------------
echo [5/6] Post-build binary and model assembly...

REM 1. Copy models to dist
if not exist "%DIST%\models" mkdir "%DIST%\models"
copy /Y "%BACKEND%models\*.pt" "%DIST%\models\" >nul

REM 2. Ensure torchvision native C++ binaries are in _internal
if exist "%BACKEND%.venv\Lib\site-packages\torchvision" (
    copy /Y "%BACKEND%.venv\Lib\site-packages\torchvision\*.pyd" "%DIST%\_internal\torchvision\" >nul 2>nul
    copy /Y "%BACKEND%.venv\Lib\site-packages\torchvision\*.dll" "%DIST%\_internal\torchvision\" >nul 2>nul
    copy /Y "%BACKEND%.venv\Lib\site-packages\torchvision\*.dll" "%DIST%\_internal\" >nul 2>nul
)

REM 3. Ensure llama_cpp native DLLs are in _internal\llama_cpp\lib
if exist "%BACKEND%.venv\Lib\site-packages\llama_cpp\lib" (
    if not exist "%DIST%\_internal\llama_cpp\lib" mkdir "%DIST%\_internal\llama_cpp\lib"
    copy /Y "%BACKEND%.venv\Lib\site-packages\llama_cpp\lib\*.dll" "%DIST%\_internal\llama_cpp\lib\" >nul 2>nul
    copy /Y "%BACKEND%.venv\Lib\site-packages\llama_cpp\lib\*.dll" "%DIST%\_internal\" >nul 2>nul
)

REM 4. Generate README_MODELS.txt for portable recipients
(
echo ===================================================================
echo   Vigilinx Artificial Intelligence Surveillance Models
echo ===================================================================
echo.
echo 1. Fast-Path Real-Time Neural Networks ^(Pre-installed in this folder^):
echo    - weapon_detector_best.pt       : Guns, Knives, Blades, Grenades
echo    - fire_smoke_detector_best.pt    : Early warning fire ^& smoke
echo    - yolov8n.pt                    : Animals ^(dogs, strays, cattle, wildlife^)
echo    - yolov8n-pose.pt               : Violent fights, physical assaults, stances
echo.
echo 2. Offline Kimi-VL Vision-Language Reasoning Model ^(Optional heavy weights^):
echo    To enable in-process local Kimi-VL forensic reasoning, place:
echo      - Kimi-VL-A3B-Thinking-2506-Q4_K_M.gguf
echo      - mmproj-Kimi-VL-A3B-Thinking-2506-f16.gguf
echo    in ANY of these directories:
echo      a^) models\ ^(this folder, right beside Vigilinx.exe^)
echo      b^) C:\Vigilinx\models\
echo      c^) %%USERPROFILE%%\models\ ^(e.g., C:\Users\^<user^>\models\^)
echo      d^) Set environment variable KIMI_MODEL_DIR to your folder
echo.
echo If Kimi-VL .gguf files are not present, Vigilinx automatically uses
echo X-CLIP and zero-prompt fast paths without interrupting surveillance.
) > "%DIST%\models\README_MODELS.txt"

echo    Assembly complete.
echo.

REM ------------------------------------------------------------------
REM  Step 6: Summary
REM ------------------------------------------------------------------
echo [6/6] Build complete!
echo.
echo ===================================================
echo   Distributable folder:
echo     %DIST%
echo.
echo   Contents:
dir /B "%DIST%\*.exe" 2>nul
echo   Models:
dir /B "%DIST%\models\*" 2>nul
echo.
echo   To run:
echo     cd /d "%DIST%"
echo     Vigilinx.exe
echo.
echo   The app will be available at http://localhost:8000
echo ===================================================
echo.
