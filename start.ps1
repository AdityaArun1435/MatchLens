<#
  Starts the MatchLens backend (FastAPI, port 8000) and the web app (Next.js, port 3000) together.
  Press Ctrl+C once to stop both.

    .\start.ps1             # real model through Ollama
    .\start.ps1 -Fake       # canned answers for the 2022 final, no Ollama needed (what the browser tests use)
    .\start.ps1 -NoOpen     # do not open the browser
#>
param(
    [switch]$Fake,
    [switch]$NoOpen,
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$web = Join-Path $root "web"

if (-not (Test-Path $python)) {
    throw "No virtual environment at $python. Run: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}
if (-not (Test-Path (Join-Path $root "data\raw"))) {
    Write-Warning "No match data yet. Run: .\.venv\Scripts\python scripts\fetch_data.py"
}
if (-not (Test-Path (Join-Path $web "node_modules"))) {
    Write-Host "Installing web dependencies (first run only)..."
    Push-Location $web; npm install; Pop-Location
}

if ($Fake) {
    $env:MATCHLENS_LLM_PROVIDER = "fake"
    Write-Host "Fake model: recaps are canned, nothing is sent to Ollama."
} else {
    try {
        Invoke-WebRequest -Uri "http://localhost:11434" -UseBasicParsing -TimeoutSec 2 | Out-Null
    } catch {
        Write-Warning "Ollama is not answering on port 11434. Start the Ollama app (or run 'ollama serve'). The match pages work without it; Generate will say so."
    }
}
$env:NEXT_PUBLIC_API_URL = "http://localhost:$ApiPort"

$procs = @()
try {
    Write-Host "Backend  -> http://localhost:$ApiPort"
    $procs += Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "matchlens.api:app", "--port", "$ApiPort") `
        -WorkingDirectory $root -NoNewWindow -PassThru
    Write-Host "Web app  -> http://localhost:$WebPort"
    $procs += Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--", "--port", "$WebPort") `
        -WorkingDirectory $web -NoNewWindow -PassThru

    if (-not $NoOpen) {
        for ($i = 0; $i -lt 60; $i++) {
            try {
                Invoke-WebRequest -Uri "http://localhost:$WebPort" -UseBasicParsing -TimeoutSec 2 | Out-Null
                Start-Process "http://localhost:$WebPort"
                break
            } catch { Start-Sleep -Seconds 1 }
        }
    }
    Write-Host "Running. Press Ctrl+C to stop both."
    while ($true) {
        if ($procs | Where-Object { $_.HasExited }) { Write-Warning "One of the servers stopped."; break }
        Start-Sleep -Seconds 1
    }
} finally {
    foreach ($p in $procs) {
        if (-not $p.HasExited) { & taskkill.exe /PID $p.Id /T /F | Out-Null }
    }
}
