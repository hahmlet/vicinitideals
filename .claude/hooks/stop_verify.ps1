# Stop-hook enforcement gate.
# 1. Bypass  — .claude/state/skip_verify.json skips all gates (manual mid-refactor escape hatch).
# 2. Fix-loop gate — blocks until the active /fix test passes (escalates after N tries).
# 3. Regression gate — runs unit+integration tests when app/ was modified this session.
#
# Exit 0 = allow stop.  Exit 2 + stderr message = block stop (agent must keep working).

$root      = Get-Location
$statePath = Join-Path $root ".claude\state"
New-Item -ItemType Directory -Force $statePath | Out-Null

# ── 1. Bypass flag ────────────────────────────────────────────────────────────
if (Test-Path (Join-Path $statePath "skip_verify.json")) {
    [Console]::Error.WriteLine("VERIFY SKIP: .claude/state/skip_verify.json present — all gates bypassed.")
    exit 0
}

# ── 2. Fix-loop gate ──────────────────────────────────────────────────────────
$markerPath = Join-Path $statePath "fixloop.json"
if (Test-Path $markerPath) {
    try   { $marker = Get-Content $markerPath -Raw | ConvertFrom-Json }
    catch { $marker = $null }

    if ($marker -and $marker.active) {
        $testCmd     = $marker.test_cmd
        $maxAttempts = if ($null -ne $marker.max_attempts) { [int]$marker.max_attempts } else { 3 }
        $attempts    = if ($null -ne $marker.attempts)     { [int]$marker.attempts     } else { 0 }

        if (-not $testCmd) {
            [Console]::Error.WriteLine("FIX LOOP: active=true but no test_cmd set. Set test_cmd in fixloop.json before stopping.")
            exit 2
        }

        $output = & pwsh -NonInteractive -Command $testCmd 2>&1 | Out-String
        $passed = $LASTEXITCODE -eq 0
        $attempts++
        $marker.attempts = $attempts

        if ($passed) {
            $marker.active = $false
            $marker.result = "passed"
            $marker | ConvertTo-Json | Set-Content $markerPath -Encoding UTF8
            # fall through to regression gate
        } else {
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
                ($output -split "`n" | Select-Object -Last 40) | ForEach-Object { [Console]::Error.WriteLine("  $_") }
                [Console]::Error.WriteLine("")
                [Console]::Error.WriteLine("Write an ESCALATION REPORT (see /fix skill) and stop.")
                exit 2
            }

            $remaining = $maxAttempts - $attempts
            [Console]::Error.WriteLine("")
            [Console]::Error.WriteLine("═══ FIX LOOP FAILED (attempt $attempts/$maxAttempts — $remaining left) ═══")
            [Console]::Error.WriteLine("Test: $testCmd")
            [Console]::Error.WriteLine("")
            ($output -split "`n" | Select-Object -Last 25) | ForEach-Object { [Console]::Error.WriteLine("  $_") }
            [Console]::Error.WriteLine("")
            [Console]::Error.WriteLine("Fix the issue. Run the test again before stopping.")
            exit 2
        }
    }
}

# ── 3. Regression gate ────────────────────────────────────────────────────────
# Fires when app/ files changed this session: uncommitted changes OR new commits
# since session start (captured at SessionStart in .claude/state/session_start_head.txt).

$appChanged = $false

# Uncommitted changes (staged + working tree)
$unstaged = (git diff HEAD --name-only 2>$null) -split "`n"
$staged   = (git diff --cached --name-only 2>$null) -split "`n"
if (($unstaged + $staged) | Where-Object { $_ -match '^app/' }) { $appChanged = $true }

# Commits made during this session
if (-not $appChanged) {
    $startHeadFile = Join-Path $statePath "session_start_head.txt"
    if (Test-Path $startHeadFile) {
        $startHead = (Get-Content $startHeadFile -Raw).Trim()
        if ($startHead) {
            $committed = (git diff "$startHead..HEAD" --name-only 2>$null) -split "`n"
            if ($committed | Where-Object { $_ -match '^app/' }) { $appChanged = $true }
        }
    }
}

if (-not $appChanged) { exit 0 }

# Load or init attempt counter
$gatePath  = Join-Path $statePath "regression_gate.json"
$maxAttempts = 3
$gateState = @{ attempts = 0 }
if (Test-Path $gatePath) {
    try   { $gateState = Get-Content $gatePath -Raw | ConvertFrom-Json }
    catch { $gateState = @{ attempts = 0 } }
}
$attempts = if ($null -ne $gateState.attempts) { [int]$gateState.attempts } else { 0 }

[Console]::Error.WriteLine("")
[Console]::Error.WriteLine("REGRESSION GATE: app/ changed this session — running unit + integration tests...")
[Console]::Error.WriteLine("")

$output = & uv run pytest tests/ -q --ignore=tests/e2e -x 2>&1 | Out-String
$passed = $LASTEXITCODE -eq 0

if ($passed) {
    Remove-Item $gatePath -Force -ErrorAction SilentlyContinue
    exit 0
}

$attempts++
@{ attempts = $attempts } | ConvertTo-Json | Set-Content $gatePath -Encoding UTF8

if ($attempts -ge $maxAttempts) {
    Remove-Item $gatePath -Force -ErrorAction SilentlyContinue
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("═══ REGRESSION GATE ESCALATED — $maxAttempts attempts exhausted ═══")
    [Console]::Error.WriteLine("Tests are still failing. Document what's broken and why before stopping.")
    [Console]::Error.WriteLine("")
    ($output -split "`n" | Select-Object -Last 30) | ForEach-Object { [Console]::Error.WriteLine("  $_") }
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("To bypass next time: touch .claude/state/skip_verify.json")
    exit 2
}

$remaining = $maxAttempts - $attempts
[Console]::Error.WriteLine("")
[Console]::Error.WriteLine("═══ REGRESSION GATE FAILED (attempt $attempts/$maxAttempts — $remaining left) ═══")
[Console]::Error.WriteLine("")
($output -split "`n" | Select-Object -Last 25) | ForEach-Object { [Console]::Error.WriteLine("  $_") }
[Console]::Error.WriteLine("")
[Console]::Error.WriteLine("Fix failing tests before stopping.")
[Console]::Error.WriteLine("To bypass: touch .claude/state/skip_verify.json")
exit 2
