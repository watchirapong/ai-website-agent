$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$scriptPath = Join-Path $projectRoot "scripts\\dev-reset.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Host "dev-reset script not found at: $scriptPath"
    exit 0
}

Write-Host "[hook] Running auto dev reset..."
powershell -ExecutionPolicy Bypass -File $scriptPath
Write-Host "[hook] Auto dev reset finished."
