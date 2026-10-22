<#
.SYNOPSIS
  Schedules the daily database backup in Windows Task Scheduler.

.DESCRIPTION
  Creates (or replaces) a daily task that runs `python -m jobs.backup` from this project.
  - Runs only while you are logged in. No password is stored.
  - If the PC was off or asleep at the scheduled time, it runs as soon as possible afterwards.
  - Never runs two copies at once, and stops after 1 hour.
  - If the nightly refresh is still running, the backup waits for it (up to 15 minutes) so it never captures a
    half-finished run. Default time is after the 3pm refresh.
  Docker Desktop must be running at that time (it normally starts when you log in). A failed backup shows a desktop alert.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\register_backup_task.ps1 -Time 18:00
#>
param(
    [string]$Time = "18:00",
    [string]$TaskName = "StockMarketBackup"
)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Can't find $python. Create the virtual environment first (see README)." }

$action = New-ScheduledTaskAction -Execute $python -Argument "-X utf8 -m jobs.backup" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "Backs up the Citewise for Markets database to the backups folder (or BACKUP_DIR)." -Force | Out-Null

Write-Host "Scheduled '$TaskName' daily at $Time."
Write-Host "Run it now:       Start-ScheduledTask -TaskName $TaskName"
Write-Host "See last result:  Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "List the backups: .venv\Scripts\python -m jobs.backup list"
Write-Host "Test a backup:    .venv\Scripts\python -m jobs.backup verify"
Write-Host "Remove it:        powershell -File scripts\unregister_backup_task.ps1"
