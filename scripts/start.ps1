<#
.SYNOPSIS
  Starts everything the app needs, in order, and opens it in your browser.

.DESCRIPTION
  1. Starts the database (docker compose up -d) and waits until it reports healthy.
  2. Checks that Ollama answers and has the model. Only a warning if not: prices, news, and filings still work, but
     the copilot and sentiment need it.
  3. Starts the API (python -m api) in its own window, unless something is already listening on its port.
  4. Starts the web app (npm run dev) in its own window, unless something is already listening on its port.
  5. Waits until both answer, then opens http://localhost:5173.
  Safe to run again: anything already running is left alone. Stop the two servers with scripts\stop.ps1.
  Docker Desktop and Ollama are not started by this script (open them first; Docker Desktop normally starts when you
  log in). Nothing here changes Windows settings or the scheduled tasks.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -NoBrowser
#>
param(
    [switch]$NoBrowser,
    [string]$OllamaUrl = "http://127.0.0.1:11434",
    [string]$OllamaModel = "qwen3:latest",
    [string]$DbContainer = "stockmarket-db",
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$web = Join-Path $root "web"
Set-Location $root

function Step($text) { Write-Host "==> $text" }
function Warn($text) { Write-Host "WARNING: $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }

function Test-Url([string]$url, [int]$seconds = 3, [string]$mustContain = "") {
    try {
        $reply = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $seconds
        return $reply.StatusCode -lt 400 -and ($mustContain -eq "" -or $reply.Content -like "*$mustContain*")
    } catch { return $false }
}
function Get-PortOwner([int]$port) {  # a short description of what is using a port, for messages
    $id = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty OwningProcess
    if (-not $id) { return "something" }
    return "'" + (Get-Process -Id $id -ErrorAction SilentlyContinue).ProcessName + "' (process $id)"
}
function Test-Listening([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}
function Wait-Until([scriptblock]$ready, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $ready) { return $true }
        Start-Sleep -Seconds 2
    }
    return [bool](& $ready)
}
function Run-Quietly([scriptblock]$command) {  # a native command's exit code, without its stderr turning into an error
    $before = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $command 2>&1 | Out-Null } finally { $ErrorActionPreference = $before }
    return $LASTEXITCODE
}

# ---- what must exist before anything can start ----
if (-not (Test-Path $python)) { Fail "Can't find $python. Create the virtual environment first (see README)." }
if (-not (Test-Path (Join-Path $root ".env"))) { Fail "Can't find .env. Copy .env.example to .env first (see README)." }
if (-not (Test-Path (Join-Path $web "node_modules"))) { Fail "The web app isn't installed. Run 'npm install' in the web folder first." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker isn't installed or isn't on PATH. The database runs in Docker." }
if ((Run-Quietly { docker info }) -ne 0) { Fail "Docker isn't running. Open Docker Desktop, wait for it to say it is running, and try again." }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $env:PATH += ";C:\Program Files\nodejs"  # a terminal opened before Node was installed doesn't have it on PATH
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "Can't find Node.js. Install it (see README) and try again." }
}

# ---- 1. the database ----
Step "Starting the database"
docker compose up -d
if (-not (Wait-Until { (docker inspect -f "{{.State.Health.Status}}" $DbContainer 2>$null) -eq "healthy" } 90)) {
    Fail "The database container '$DbContainer' didn't become healthy within 90 seconds. Check it with: docker compose logs db"
}
Write-Host "    database is healthy"

# ---- 2. Ollama (a warning only) ----
Step "Checking Ollama"
$ollamaOk = $false
try {
    $tags = Invoke-WebRequest -Uri "$OllamaUrl/api/tags" -UseBasicParsing -TimeoutSec 3
    if ($tags.Content -match [regex]::Escape("`"$OllamaModel`"")) {
        $ollamaOk = $true
        Write-Host "    Ollama is running with $OllamaModel"
    } else {
        Warn "Ollama is running but doesn't have '$OllamaModel'. Install it with: ollama pull $OllamaModel"
    }
} catch {
    Warn "Ollama isn't answering at $OllamaUrl. Open the Ollama app. The copilot and sentiment won't work until it is running."
}

# ---- 3 and 4. the API and the web app ----
# The window titles double as markers, so scripts\stop.ps1 can tell these windows from anything else.
$apiUrl = "http://127.0.0.1:$ApiPort/api/stocks"
$webUrl = "http://localhost:$WebPort/"
$apiUp = $false
$webUp = $false
$apiBlocked = $false
$webBlocked = $false

if (Test-Listening $ApiPort) {
    if (Test-Url $apiUrl) {
        Step "The API is already running on port $ApiPort, so it is left alone"
        $apiUp = $true
    } else {
        $apiBlocked = $true
        Warn "Port $ApiPort is used by $(Get-PortOwner $ApiPort), which isn't answering as this app's API. Close it, or use -ApiPort."
    }
} else {
    Step "Starting the API (port $ApiPort)"
    $apiCommand = "`$host.UI.RawUI.WindowTitle = 'stockMarket-api-server'; `$env:PYTHONIOENCODING = 'utf-8'; Set-Location '$root'; & '$python' -m api"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "`"$apiCommand`"" | Out-Null
}

if (Test-Listening $WebPort) {
    if (Test-Url $webUrl 3 "stockMarket") {
        Step "The web app is already running on port $WebPort, so it is left alone"
        $webUp = $true
    } else {
        $webBlocked = $true
        Warn "Port $WebPort is used by $(Get-PortOwner $WebPort), which isn't serving this app. Close it, or use -WebPort."
    }
} else {
    Step "Starting the web app (port $WebPort)"
    $webCommand = "`$host.UI.RawUI.WindowTitle = 'stockMarket-web-server'; Set-Location '$web'; npm run dev"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "`"$webCommand`"" -WorkingDirectory $web | Out-Null
}

# ---- 5. wait, then open ----
Step "Waiting for both to answer"
if (-not $apiUp -and -not $apiBlocked) {
    $apiUp = Wait-Until { Test-Url $apiUrl } 60
    if (-not $apiUp) { Warn "The API didn't answer within 60 seconds. Look at its window ('stockMarket-api-server') for the error." }
}
if (-not $webUp -and -not $webBlocked) {
    $webUp = Wait-Until { Test-Url $webUrl 3 "stockMarket" } 60
    if (-not $webUp) { Warn "The web app didn't answer within 60 seconds. Look at its window ('stockMarket-web-server') for the error." }
}

Write-Host ""
Write-Host ("    database : healthy")
Write-Host ("    Ollama   : " + $(if ($ollamaOk) { "ready" } else { "NOT ready (copilot and sentiment won't work)" }))
Write-Host ("    API      : " + $(if ($apiUp) { "http://127.0.0.1:$ApiPort" } else { "NOT answering" }))
Write-Host ("    web app  : " + $(if ($webUp) { "http://localhost:$WebPort" } else { "NOT answering" }))
Write-Host ""
Write-Host "Stop the API and web app with: powershell -File scripts\stop.ps1   (the database keeps running for the nightly jobs)"

if ($apiUp -and $webUp -and -not $NoBrowser) { Start-Process "http://localhost:$WebPort" }
if (-not ($apiUp -and $webUp)) { exit 1 }
