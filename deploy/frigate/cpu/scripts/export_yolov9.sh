#!/usr/bin/env bash
# Builds the small YOLOv9 model for CPU-only machines (Linux/macOS) and puts it in
# cpu/config/model_cache/yolov9-t-320.onnx, the path cpu/config/config.yml expects.
# Uses the same Frigate recipe as ../../scripts/export_yolov9.sh. Run once:
#     ./scripts/export_yolov9.sh        (from deploy/frigate/cpu)
set -euo pipefail
CPU_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_SIZE="${MODEL_SIZE:-t}" IMG_SIZE="${IMG_SIZE:-320}" OUT_DIR="$CPU_DIR/config/model_cache" \
    "$CPU_DIR/../scripts/export_yolov9.sh"
