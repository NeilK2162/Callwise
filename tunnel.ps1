# Start a Cloudflare quick tunnel to the Callwise webhook-ingest service (your BASE_URL).
# Self-bootstrapping: if cloudflared is not installed, it downloads the official binary
# (no admin, no PATH change) into your LocalAppData, then runs it. Pure ASCII for PS 5.1.
#
#   .\tunnel.ps1            # tunnels http://localhost:8001 (default)
#   .\tunnel.ps1 -Port 8001
#
# If PowerShell blocks the script:  powershell -ExecutionPolicy Bypass -File .\tunnel.ps1

param([int]$Port = 8001)

function Resolve-Cloudflared {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @((Join-Path $env:LOCALAPPDATA 'cloudflared\cloudflared.exe'), (Join-Path $PSScriptRoot 'cloudflared.exe'))) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$exe = Resolve-Cloudflared
if (-not $exe) {
    Write-Host "cloudflared not found - downloading the official binary (one time, ~50 MB)..." -ForegroundColor Yellow
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $dir = Join-Path $env:LOCALAPPDATA 'cloudflared'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $exe = Join-Path $dir 'cloudflared.exe'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-$arch.exe"
    Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
    Write-Host "Installed: $exe" -ForegroundColor Green
}

Write-Host "Starting Cloudflare tunnel -> http://localhost:$Port" -ForegroundColor Cyan
Write-Host "Copy the https://<...>.trycloudflare.com URL into BASE_URL (.env) and the ElevenLabs portal." -ForegroundColor Yellow
Write-Host "Keep this window open for the whole demo. Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""
& $exe tunnel --url "http://localhost:$Port"
