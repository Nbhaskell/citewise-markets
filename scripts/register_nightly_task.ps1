<#
.SYNOPSIS
  Schedules the nightly refresh in Windows Task Scheduler.

.DESCRIPTION
  Creates (or replaces) a daily task that runs `python -m jobs.refresh` from this project.
  - Runs only while you are logged in. No password is stored.
  - If the PC was off or asleep at the scheduled time, it runs as soon as possible afterwards.
  - Never runs two copies at once, and stops after 2 hours.
  Docker Desktop and Ollama must be running at that time (both normally start when you log in).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\register_nightly_task.ps1 -Time 23:00
#>
param(
    [string]$Time = "23:00",
    [string]$TaskName = "StockMarketNightlyRefresh"
)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Can't find $python. Create the virtual environment first (see docs/SETUP.md)." }

$action = New-ScheduledTaskAction -Execute $python -Argument "-X utf8 -m jobs.refresh" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "Refreshes prices, news, filings, embeddings and sentiment for the Citewise for Markets project." -Force | Out-Null

Write-Host "Scheduled '$TaskName' daily at $Time."
Write-Host "Run it now:      Start-ScheduledTask -TaskName $TaskName"
Write-Host "See last result: Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "Check the data:  .venv\Scripts\python -m jobs.refresh --status"
Write-Host "Remove it:       powershell -File scripts\unregister_nightly_task.ps1"
