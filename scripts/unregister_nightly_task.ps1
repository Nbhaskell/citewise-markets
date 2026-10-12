<#
.SYNOPSIS
  Removes the nightly refresh from Windows Task Scheduler. Your data and logs are not touched.
#>
param([string]$TaskName = "StockMarketNightlyRefresh")
$ErrorActionPreference = "Stop"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed '$TaskName'."
} else {
    Write-Host "No task named '$TaskName' found."
}
