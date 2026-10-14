<#
.SYNOPSIS
  Stops the API and web app that scripts\start.ps1 (or you) started. The database is left running.

.DESCRIPTION
  - Closes the two windows scripts\start.ps1 opened (found by their window titles) and everything running inside them.
  - Then checks the API and web ports. If something is still listening and it looks like this app's server
    (python -m api, or the Vite dev server), it is stopped too, which covers servers you started by hand.
  - Anything else listening on those ports is left alone, with a message saying what it is.
  The database keeps running on purpose: the nightly refresh and backup need it. To stop it too: docker compose stop

.EXAMPLE
  powershell -File scripts\stop.ps1
#>
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)
$ErrorActionPreference = "Stop"

function Step($text) { Write-Host "==> $text" }
function Warn($text) { Write-Host "WARNING: $text" -ForegroundColor Yellow }

function Stop-Tree([int]$id) {  # the process and everything it started
    & taskkill.exe /PID $id /T /F 2>&1 | Out-Null
}
function Get-CommandLine([int]$id) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId = $id" -ErrorAction SilentlyContinue
    if ($p) { return [string]$p.CommandLine } else { return "" }
}

# ---- 1. the windows start.ps1 opened ----
$titles = @("stockMarket-api-server", "stockMarket-web-server")
$windows = @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" | Where-Object {
    $line = [string]$_.CommandLine
    $_.ProcessId -ne $PID -and ($titles | Where-Object { $line -like "*$_*" })
})
foreach ($w in $windows) {
    Step "Closing a server window (process $($w.ProcessId))"
    Stop-Tree $w.ProcessId
}

# ---- 2. anything still serving this app on its ports ----
Start-Sleep -Seconds 1
$expect = @{ $ApiPort = "-m api"; $WebPort = "vite" }
foreach ($port in $expect.Keys) {
    $owners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($id in $owners) {
        $line = Get-CommandLine $id
        $name = (Get-Process -Id $id -ErrorAction SilentlyContinue).ProcessName
        if ($line -like "*$($expect[$port])*") {
            Step "Stopping $name (process $id) on port $port"
            Stop-Tree $id
        } else {
            Warn "Port $port is used by '$name' (process $id), which doesn't look like this app's server, so it was left alone."
        }
    }
}

# ---- 3. report ----
Start-Sleep -Seconds 1
foreach ($port in $ApiPort, $WebPort) {
    $up = [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    Write-Host ("    port {0}: {1}" -f $port, $(if ($up) { "still in use" } else { "free" }))
}
Write-Host "The database is still running (the nightly jobs need it). To stop it too: docker compose stop"
