# Builds the YOLOv9 model Frigate uses on a CPU-only Windows PC and puts it in
# config\model_cache\yolov9-t-320.onnx (the path config.yml expects).
#
# Same recipe as Frigate 0.18.0's docs, run through Docker Desktop.
# Run once, in PowerShell, from deploy\frigate\cpu:
#     powershell -ExecutionPolicy Bypass -File scripts\export_yolov9.ps1
# Takes 5-15 minutes and needs internet. If you change the size or resolution,
# update model.width/height/path in config\config.yml to match.

param(
    [string]$ModelSize = "t",   # t (fastest) s m c e
    [string]$ImgSize = "320"    # 320 or 640
)
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $here "config\model_cache"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$buildDir = Join-Path $env:TEMP "vigilinx-yolov9-build"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

# Written with Unix line endings: Windows line endings break the RUN lines.
$dockerfile = @(
    'FROM python:3.11 AS build',
    'RUN apt-get update && apt-get install --no-install-recommends -y cmake libgl1 && rm -rf /var/lib/apt/lists/*',
    'COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /bin/',
    'WORKDIR /yolov9',
    'ADD https://github.com/WongKinYiu/yolov9.git .',
    'RUN uv pip install --system -r requirements.txt',
    'RUN uv pip install --system onnx==1.18.0 onnxruntime onnx-simplifier==0.4.* onnxscript',
    'ARG MODEL_SIZE',
    'ARG IMG_SIZE',
    'ADD https://github.com/WongKinYiu/yolov9/releases/download/v0.1/yolov9-${MODEL_SIZE}-converted.pt yolov9-${MODEL_SIZE}.pt',
    'RUN sed -i "s/ckpt = torch.load(attempt_download(w), map_location=''cpu'')/ckpt = torch.load(attempt_download(w), map_location=''cpu'', weights_only=False)/g" models/experimental.py',
    'RUN python3 export.py --weights ./yolov9-${MODEL_SIZE}.pt --imgsz ${IMG_SIZE} --simplify --include onnx',
    'FROM scratch',
    'ARG MODEL_SIZE',
    'ARG IMG_SIZE',
    'COPY --from=build /yolov9/yolov9-${MODEL_SIZE}.onnx /yolov9-${MODEL_SIZE}-${IMG_SIZE}.onnx'
) -join "`n"
$dfPath = Join-Path $buildDir "Dockerfile"
[System.IO.File]::WriteAllText($dfPath, $dockerfile + "`n")

docker build --build-arg "MODEL_SIZE=$ModelSize" --build-arg "IMG_SIZE=$ImgSize" --output $outDir -f $dfPath $buildDir
if ($LASTEXITCODE -ne 0) { throw "docker build failed (is Docker Desktop running?)" }

$model = Join-Path $outDir "yolov9-$ModelSize-$ImgSize.onnx"
if (-not (Test-Path $model)) { throw "Model was not produced: $model" }
Write-Host "Model written to $model"
