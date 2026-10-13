<#
.SYNOPSIS
  Removes the daily database backup from Windows Task Scheduler. Your data and existing backups are not touched.
#>
param([string]$TaskName = "StockMarketBackup")
$ErrorActionPreference = "Stop"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed '$TaskName'."
} else {
    Write-Host "No task named '$TaskName' found."
}
