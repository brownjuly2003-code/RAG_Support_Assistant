[CmdletBinding()]
param(
    [string]$TaskName = "RAG Support Assistant Autopilot",
    [string]$DailyAt = "03:00",
    [switch]$DryRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runner = Join-Path $ProjectRoot "scripts\autopilot.ps1"

if (-not (Test-Path -Path $Runner)) {
    throw "Runner not found: $Runner"
}

$time = [DateTime]::ParseExact($DailyAt, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$Runner`""
$trigger = New-ScheduledTaskTrigger -Daily -At $time
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable:$false

if ($DryRun) {
    Write-Host "Would register scheduled task '$TaskName' for $DailyAt."
    Write-Host "Action: powershell.exe -ExecutionPolicy Bypass -File `"$Runner`""
    exit 0
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Local guarded autopilot runner for RAG Support Assistant. Never pushes or deploys." | Out-Null
Write-Host "Registered scheduled task '$TaskName'."
Write-Host "Pause with: New-Item -ItemType File -Path `"$ProjectRoot\.autopilot\PAUSE`" -Force"
Write-Host "Disable with: Unregister-ScheduledTask -TaskName `"$TaskName`" -Confirm:`$false"
