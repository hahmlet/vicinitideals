# Fix-loop enforcement gate. Runs on every agent Stop.
# Blocks stopping when a fix loop is active and its test is failing.
# Exit 0 = allow stop. Exit 2 + stderr = block stop (agent must keep working).

$markerPath = Join-Path (Get-Location) ".claude\state\fixloop.json"
if (-not (Test-Path $markerPath)) { exit 0 }

try {
    $marker = Get-Content $markerPath -Raw | ConvertFrom-Json
} catch {
    exit 0
}
if (-not $marker.active) { exit 0 }

$testCmd   = $marker.test_cmd
$maxAttempts = if ($null -ne $marker.max_attempts) { [int]$marker.max_attempts } else { 3 }
$attempts  = if ($null -ne $marker.attempts)  { [int]$marker.attempts  } else { 0 }

if (-not $testCmd) {
    [Console]::Error.WriteLine("FIX LOOP: active=true but no test_cmd set. Set test_cmd in .claude/state/fixloop.json before stopping.")
    exit 2
}

# Run the verification test
$output = & pwsh -NonInteractive -Command $testCmd 2>&1 | Out-String
$passed  = $LASTEXITCODE -eq 0

$attempts++
$marker.attempts = $attempts

if ($passed) {
    $marker.active = $false
    $marker.result = "passed"
    $marker | ConvertTo-Json | Set-Content $markerPath -Encoding UTF8
    exit 0
}

$marker | ConvertTo-Json | Set-Content $markerPath -Encoding UTF8

if ($attempts -ge $maxAttempts) {
    $marker.active = $false
    $marker.result = "escalated"
    $marker | ConvertTo-Json | Set-Content $markerPath -Encoding UTF8

    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("═══ FIX LOOP ESCALATED — $maxAttempts attempts exhausted ═══")
    [Console]::Error.WriteLine("Bug:  $($marker.bug)")
    [Console]::Error.WriteLine("Test: $testCmd")
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("Last failure output:")
    ($output -split "`n" | Select-Object -Last 40) | ForEach-Object {
        [Console]::Error.WriteLine("  $_")
    }
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("Write an ESCALATION REPORT (see /fix skill) and stop.")
    exit 2
}

$remaining = $maxAttempts - $attempts
[Console]::Error.WriteLine("")
[Console]::Error.WriteLine("═══ VERIFICATION FAILED (attempt $attempts/$maxAttempts — $remaining left) ═══")
[Console]::Error.WriteLine("Test: $testCmd")
[Console]::Error.WriteLine("")
($output -split "`n" | Select-Object -Last 25) | ForEach-Object {
    [Console]::Error.WriteLine("  $_")
}
[Console]::Error.WriteLine("")
[Console]::Error.WriteLine("Go back and fix the issue. Run the test again before stopping.")
exit 2
