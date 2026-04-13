<#
.SYNOPSIS
  Stop all local dev processes for ai-website-agent (backend, dashboard, preview).

.DESCRIPTION
  - Frees listen ports (backend, dashboard, preview, common alternates).
  - Stops uvicorn / FastAPI and Next.js dev servers launched from this repo.
  - Stops PowerShell helpers (generate-and-wait, dev-reset-style windows).
  - Removes orphan python multiprocessing workers (uvicorn --reload) whose parent PID is gone.

.EXAMPLE
  .\scripts\dev-kill.ps1
 .\scripts\dev-kill.ps1 -BackendPort 8020 -DashboardPort 3001 -PreviewPort 3000
#>
param(
    [int]$BackendPort = 8020,
    [int]$DashboardPort = 3001,
    [int]$PreviewPort = 3000,
    [int[]]$ExtraPorts = @(8010, 8000)
)

$ErrorActionPreference = "SilentlyContinue"
# scripts\dev-kill.ps1 -> repo root
$root = Resolve-Path (Join-Path $PSScriptRoot "..") | ForEach-Object { $_.Path }
$repoLeaf = Split-Path -Leaf $root

$allPorts = @($BackendPort, $DashboardPort, $PreviewPort) + $ExtraPorts | Select-Object -Unique

function Stop-PortListeners {
    param([int[]]$Ports)
    foreach ($port in $Ports) {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $conns) { continue }
        $procIds = $conns | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $procIds) {
            if ($procId -and $procId -gt 0) {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "Stopped PID $procId (port $port)"
            }
        }
    }
}

function Stop-ByCommandLinePattern {
    param([string]$Pattern)
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -like $Pattern
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped PID $($_.ProcessId) $($_.Name)"
    }
}

function Stop-OrphanPythonMultiprocessingWorkers {
    # uvicorn --reload leaves spawn_main children; parents can exit while workers still LISTEN.
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | ForEach-Object {
        $line = $_.CommandLine
        if (-not $line -or $line -notmatch 'spawn_main\(parent_pid=(\d+)') { return }
        $parentPid = [int]$Matches[1]
        if (-not (Get-Process -Id $parentPid -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped orphan python worker PID $($_.ProcessId) (parent $parentPid gone)"
        }
    }
}

Write-Host "Stopping listeners on ports: $($allPorts -join ', ') ..."
for ($round = 0; $round -lt 3; $round++) {
    Stop-PortListeners -Ports $allPorts
    Start-Sleep -Milliseconds 400
}

Write-Host "Stopping uvicorn / backend (this repo only) ..."
Get-CimInstance Win32_Process | Where-Object {
    $c = $_.CommandLine
    -not [string]::IsNullOrEmpty($c) -and
        $c -like "*uvicorn*" -and
        ($c -like "*${repoLeaf}*backend*" -or
            $c.ToLowerInvariant().Contains($root.ToLowerInvariant()))
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped PID $($_.ProcessId) $($_.Name) (uvicorn)"
}

Write-Host "Stopping Next.js dashboard dev (this repo only) ..."
Get-CimInstance Win32_Process | Where-Object {
    $c = $_.CommandLine
    -not [string]::IsNullOrEmpty($c) -and
        ($c -like "*next dev*" -or $c -like "*npm run dev*") -and
        ($c -like "*${repoLeaf}*dashboard*" -or
            $c.ToLowerInvariant().Contains($root.ToLowerInvariant()))
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped PID $($_.ProcessId) $($_.Name) (dashboard dev)"
}

Write-Host "Stopping PowerShell helper scripts ..."
Stop-ByCommandLinePattern -Pattern "*generate-and-wait.ps1*"

Write-Host "Stopping orphan multiprocessing python workers ..."
Stop-OrphanPythonMultiprocessingWorkers

Write-Host "Final port pass ..."
Stop-PortListeners -Ports $allPorts
Start-Sleep -Seconds 1
Stop-OrphanPythonMultiprocessingWorkers

Write-Host "`nPort status:"
foreach ($port in $allPorts | Sort-Object -Unique) {
    $listen = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listen) {
        Write-Host "  WARNING: $port still LISTEN (OwningProcess: $($listen.OwningProcess -join ', '))" -ForegroundColor Yellow
    } else {
        Write-Host "  OK $port free"
    }
}

Write-Host "`nDone."
