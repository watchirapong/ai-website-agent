param(
    [string]$Prompt = "Create a clean one-page website",
    [string]$ApiBase = "http://127.0.0.1:8020",
    [switch]$ManualApproval
)

$ErrorActionPreference = "Stop"

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        Invoke-RestMethod -Method Get -Uri "$ApiBase/api/projects" | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    throw "Backend is not reachable at $ApiBase"
}

$body = @{
    prompt = $Prompt
    skip_deploy = $true
    manual_approval = [bool]$ManualApproval
} | ConvertTo-Json

$res = Invoke-RestMethod -Method Post -Uri "$ApiBase/api/generate" -ContentType "application/json" -Body $body
$id = $res.project_id
Write-Host "project=$id"

while ($true) {
    Start-Sleep -Seconds 3
    $s = Invoke-RestMethod -Method Get -Uri "$ApiBase/api/status/$id"
    $events = @($s.events)
    $last = if ($events.Count -gt 0) { $events[-1] } else { $null }
    if ($last) {
        Write-Host ("status={0} events={1} last={2}/{3}" -f $s.status, $events.Count, $last.step, $last.status)
    } else {
        Write-Host ("status={0} events=0" -f $s.status)
    }

    if ($s.status -eq "completed" -or $s.status -eq "failed") {
        Write-Host "=== FINAL ==="
        $s | ConvertTo-Json -Depth 8
        break
    }
}
