#!/usr/bin/env bash
# Installs the Qwen3-VL vision model into Ollama from Docker Hub (ai/qwen3-vl),
# for networks where `ollama pull qwen3-vl:4b` fails because Ollama's own
# download server (registry.ollama.ai) is blocked but Docker Hub is reachable.
# Ollama still has to be installed and running: this only supplies the model.
#
#   ./import_qwen_from_dockerhub.sh                 # Ollama installed natively
#   OLLAMA_CONTAINER=vigilinx-ollama ./import_qwen_from_dockerhub.sh   # Ollama in Docker
#   MODEL_SIZE=8b ./import_qwen_from_dockerhub.sh   # the larger model
#
# Downloads ~3.4 GB (4b) or ~6.3 GB (8b) into ./qwen3-vl-download (kept, so a
# rerun skips finished files) and verifies each file's checksum.
set -euo pipefail

MODEL_SIZE="${MODEL_SIZE:-4b}"
case "$MODEL_SIZE" in
    4b) HUB_TAG="4B-UD-Q4_K_XL" ;;
    8b) HUB_TAG="8B-UD-Q4_K_XL" ;;
    *) echo "MODEL_SIZE must be 4b or 8b" >&2; exit 1 ;;
esac
OLLAMA_NAME="qwen3-vl:$MODEL_SIZE"      # the name Vigilinx asks for (OLLAMA_VISION_MODEL)
DIR="${DOWNLOAD_DIR:-$PWD/qwen3-vl-download}/$MODEL_SIZE"
REPO="ai/qwen3-vl"
mkdir -p "$DIR"

TOKEN=$(curl -fsS "https://auth.docker.io/token?service=registry.docker.io&scope=repository:$REPO:pull" |
        python3 -c 'import sys, json; print(json.load(sys.stdin)["token"])')
MANIFEST=$(curl -fsS -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.manifest.v1+json" \
    "https://registry-1.docker.io/v2/$REPO/manifests/$HUB_TAG")

layer_digest() {  # digest of the layer with the given media type
    python3 -c 'import sys, json
m = json.loads(sys.argv[1])
print(next(l["digest"] for l in m["layers"] if l["mediaType"] == sys.argv[2]))' "$MANIFEST" "$1"
}

fetch() {  # fetch <digest> <file>
    local digest="$1" out="$DIR/$2"
    if [ -f "$out" ] && echo "${digest#sha256:}  $out" | sha256sum -c --status -; then
        echo "$2: already downloaded"; return
    fi
    echo "Downloading $2 ..."
    curl -fL --retry 5 -C - -H "Authorization: Bearer $TOKEN" -o "$out" \
        "https://registry-1.docker.io/v2/$REPO/blobs/$digest"
    echo "${digest#sha256:}  $out" | sha256sum -c -
}

fetch "$(layer_digest application/vnd.docker.ai.gguf.v3)" model.gguf
fetch "$(layer_digest application/vnd.docker.ai.mmproj)" mmproj.gguf   # the vision part

if [ -n "${OLLAMA_CONTAINER:-}" ]; then
    docker exec "$OLLAMA_CONTAINER" mkdir -p /tmp/qwen-import
    docker cp "$DIR/model.gguf" "$OLLAMA_CONTAINER:/tmp/qwen-import/model.gguf"
    docker cp "$DIR/mmproj.gguf" "$OLLAMA_CONTAINER:/tmp/qwen-import/mmproj.gguf"
    printf 'FROM /tmp/qwen-import/model.gguf\nFROM /tmp/qwen-import/mmproj.gguf\n' |
        docker exec -i "$OLLAMA_CONTAINER" sh -c 'cat > /tmp/qwen-import/Modelfile'
    docker exec "$OLLAMA_CONTAINER" ollama create "$OLLAMA_NAME" -f /tmp/qwen-import/Modelfile
    docker exec "$OLLAMA_CONTAINER" rm -rf /tmp/qwen-import
else
    printf 'FROM %s/model.gguf\nFROM %s/mmproj.gguf\n' "$DIR" "$DIR" > "$DIR/Modelfile"
    ollama create "$OLLAMA_NAME" -f "$DIR/Modelfile"
fi

echo "Done: '$OLLAMA_NAME' is installed in Ollama. You can delete $DIR to free the space."
