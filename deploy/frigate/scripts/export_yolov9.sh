#!/usr/bin/env bash
# Builds the YOLOv9 ONNX model Frigate uses for person/dog/knife detection and
# puts it where config.yml expects it (config/model_cache/yolov9-s-640.onnx).
#
# Recipe taken from Frigate 0.18.0's docs (docs/data/object_detectors_models.yaml).
# Needs Docker and internet access; takes a few minutes; run once.
#
# MODEL_SIZE: t (fastest) s m c e (most accurate). IMG_SIZE: 320 or 640.
# 640 helps with small objects such as knives on CCTV; if you change either,
# update model.width/height/path in config.yml to match.
set -euo pipefail

MODEL_SIZE="${MODEL_SIZE:-s}"
IMG_SIZE="${IMG_SIZE:-640}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$HERE/config/model_cache}"
mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

docker build . --build-arg MODEL_SIZE="$MODEL_SIZE" --build-arg IMG_SIZE="$IMG_SIZE" --output . -f- <<'EOF'
FROM python:3.11 AS build
RUN apt-get update && apt-get install --no-install-recommends -y cmake libgl1 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /bin/
WORKDIR /yolov9
ADD https://github.com/WongKinYiu/yolov9.git .
RUN uv pip install --system -r requirements.txt
RUN uv pip install --system onnx==1.18.0 onnxruntime onnx-simplifier==0.4.* onnxscript
ARG MODEL_SIZE
ARG IMG_SIZE
ADD https://github.com/WongKinYiu/yolov9/releases/download/v0.1/yolov9-${MODEL_SIZE}-converted.pt yolov9-${MODEL_SIZE}.pt
RUN sed -i "s/ckpt = torch.load(attempt_download(w), map_location='cpu')/ckpt = torch.load(attempt_download(w), map_location='cpu', weights_only=False)/g" models/experimental.py
RUN python3 export.py --weights ./yolov9-${MODEL_SIZE}.pt --imgsz ${IMG_SIZE} --simplify --include onnx
FROM scratch
ARG MODEL_SIZE
ARG IMG_SIZE
COPY --from=build /yolov9/yolov9-${MODEL_SIZE}.onnx /yolov9-${MODEL_SIZE}-${IMG_SIZE}.onnx
EOF

echo "Model written to $OUT_DIR/yolov9-${MODEL_SIZE}-${IMG_SIZE}.onnx"
