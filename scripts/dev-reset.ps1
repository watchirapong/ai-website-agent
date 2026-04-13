param(
    [int]$BackendPort = 8020,
    [int]$DashboardPort = 3001
)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot

function Stop-PortListeners([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen
    if (-not $conns) { return }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pids) {
        if ($p -gt 0) {
            Stop-Process -Id $p -Force
            Write-Host "Stopped PID $p on port $Port"
        }
    }
}

function Stop-ByPattern([string]$Pattern) {
    $targets = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -like $Pattern
    }
    foreach ($t in $targets) {
        Stop-Process -Id $t.ProcessId -Force
        Write-Host "Stopped PID $($t.ProcessId) ($($t.Name))"
    }
}

Write-Host "Cleaning old dev processes..."
Stop-PortListeners -Port $BackendPort
Stop-PortListeners -Port $DashboardPort
Stop-ByPattern -Pattern "*uvicorn*main:app*"
Stop-ByPattern -Pattern "*next dev -p $DashboardPort*"

Write-Host "Starting backend on :$BackendPort"
# Force sane step timeouts so a stale user/machine env (e.g. 15s) cannot break local LLM runs.
$timeoutBlock = @"
`$env:PIPELINE_STEP_TIMEOUT_SECONDS='600'
`$env:PLANNER_TIMEOUT_SECONDS='300'
`$env:DEVELOPER_TIMEOUT_SECONDS='600'
`$env:TESTER_TIMEOUT_SECONDS='600'
`$env:REVIEWER_TIMEOUT_SECONDS='300'
`$env:DEPLOYER_TIMEOUT_SECONDS='300'
Set-Location '$root\backend'
& '$root\venv\Scripts\uvicorn.exe' main:app --host 127.0.0.1 --port $BackendPort --reload
"@
Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoExit",
    "-Command",
    $timeoutBlock.Trim()
)

Write-Host "Starting dashboard on :$DashboardPort"
Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:$BackendPort'; Set-Location '$root\dashboard'; npm run dev"
)

Write-Host "Done. Backend: http://127.0.0.1:$BackendPort  Dashboard: http://127.0.0.1:$DashboardPort"
