# Installs the Qwen3-VL vision model into Ollama from Docker Hub (ai/qwen3-vl),
# for networks where `ollama pull qwen3-vl:4b` fails because Ollama's own
# download server (registry.ollama.ai) is blocked but Docker Hub is reachable.
# Ollama (the Windows app) still has to be installed and running: this only
# supplies the model.
#
#   powershell -ExecutionPolicy Bypass -File deploy\frigate\scripts\import_qwen_from_dockerhub.ps1
#   powershell -ExecutionPolicy Bypass -File deploy\frigate\scripts\import_qwen_from_dockerhub.ps1 -ModelSize 8b
#
# Downloads ~3.4 GB (4b) or ~6.3 GB (8b) into .\qwen3-vl-download (kept, so a
# rerun skips finished files) and verifies each file's checksum.
param(
    [ValidateSet("4b", "8b")] [string]$ModelSize = "4b",
    [string]$DownloadDir = (Join-Path (Get-Location) "qwen3-vl-download")
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # the progress bar makes big downloads very slow
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12   # Windows PowerShell 5.1

$hubTag = @{ "4b" = "4B-UD-Q4_K_XL"; "8b" = "8B-UD-Q4_K_XL" }[$ModelSize]
$ollamaName = "qwen3-vl:$ModelSize"          # the name Vigilinx asks for (OLLAMA_VISION_MODEL)
$repo = "ai/qwen3-vl"
$dir = Join-Path $DownloadDir $ModelSize
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$token = (Invoke-RestMethod "https://auth.docker.io/token?service=registry.docker.io&scope=repository:${repo}:pull").token
$headers = @{ Authorization = "Bearer $token" }
$manifest = Invoke-RestMethod -Headers ($headers + @{ Accept = "application/vnd.oci.image.manifest.v1+json" }) `
    "https://registry-1.docker.io/v2/$repo/manifests/$hubTag"
if ($manifest -is [string]) { $manifest = $manifest | ConvertFrom-Json }   # 5.1 doesn't parse +json types

function Get-Layer([string]$file, [string]$mediaType) {
    $digest = ($manifest.layers | Where-Object mediaType -eq $mediaType | Select-Object -First 1).digest
    $expected = $digest.Substring(7)
    $out = Join-Path $dir $file
    if ((Test-Path $out) -and (Get-FileHash $out -Algorithm SHA256).Hash -eq $expected) {
        Write-Host "${file}: already downloaded"
        return
    }
    Write-Host "Downloading $file ..."
    Invoke-WebRequest -UseBasicParsing -Headers $headers -OutFile $out "https://registry-1.docker.io/v2/$repo/blobs/$digest"
    if ((Get-FileHash $out -Algorithm SHA256).Hash -ne $expected) {
        throw "$file is corrupt (checksum mismatch). Delete it and run this script again."
    }
    Write-Host "${file}: OK"
}

Get-Layer "model.gguf" "application/vnd.docker.ai.gguf.v3"
Get-Layer "mmproj.gguf" "application/vnd.docker.ai.mmproj"   # the vision part

$modelfile = Join-Path $dir "Modelfile"
"FROM $(Join-Path $dir 'model.gguf')`nFROM $(Join-Path $dir 'mmproj.gguf')`n" | Set-Content -Path $modelfile -NoNewline
ollama create $ollamaName -f $modelfile
if ($LASTEXITCODE -ne 0) { throw "ollama create failed. Is the Ollama app running?" }

Write-Host "Done: '$ollamaName' is installed in Ollama. You can delete $dir to free the space."
