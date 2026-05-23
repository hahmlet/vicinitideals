# PostToolUse hook: when Edit/Write touches docs/FINANCIAL_MODEL.md,
# emit additional context to Claude with the diff + cross-references
# so the parent agent knows to spawn a review subagent.
#
# Layer 2 of the FINANCIAL_MODEL.md consistency safety net. Layer 1
# (tests/docs/test_financial_model_appendix_f.py) is the load-bearing
# mechanical gate that runs in CI. This hook is the semantic gate that
# fires during interactive editing.
#
# Output contract: emit JSON to stdout matching the PostToolUse hook
# spec — { "hookSpecificOutput": { "additionalContext": "string" } }.
# Silent (no output) when the edit doesn't touch FINANCIAL_MODEL.md.

[CmdletBinding()] param()
$ErrorActionPreference = 'Continue'

try {
    $raw = [Console]::In.ReadToEnd()
    if (-not $raw) { exit 0 }
    $payload = $raw | ConvertFrom-Json
} catch {
    exit 0
}

$toolName = $payload.tool_name
if ($toolName -notin @('Edit', 'Write')) { exit 0 }

$filePath = $payload.tool_input.file_path
if (-not $filePath) { exit 0 }

# Normalize: only fire on docs/FINANCIAL_MODEL.md (avoid matching unrelated
# files that happen to contain the substring).
$norm = $filePath -replace '\\', '/'
if ($norm -notmatch 'docs/FINANCIAL_MODEL\.md$') { exit 0 }

# Compute diff vs HEAD for that file. If no diff (e.g. write produced
# identical content), exit silently.
$diff = & git diff --unified=0 -- $filePath 2>$null
if (-not $diff) { exit 0 }

# Extract changed ##### headings (data-point rows) from the diff:
# look for added/removed lines starting with `##### `.
$changedHeadings = @()
foreach ($line in $diff -split "`n") {
    if ($line -match '^[+\-]##### (.+)$') {
        $h = $matches[1].Trim()
        if ($changedHeadings -notcontains $h) {
            $changedHeadings += $h
        }
    }
}

# Also scan the diff body for already-existing headings whose body
# was modified. Walk the diff hunks, track current heading.
$currentHeading = $null
foreach ($line in $diff -split "`n") {
    if ($line -match '^@@') {
        # Hunk header — heading context might shift; reset.
        $currentHeading = $null
        continue
    }
    if ($line -match '^[ ]##### (.+)$') {
        # Unchanged heading line in context — track it.
        $currentHeading = $matches[1].Trim()
        continue
    }
    if ($line -match '^[+\-]' -and $line -notmatch '^[+\-]{3}') {
        # Actual changed line under the current heading.
        if ($currentHeading -and ($changedHeadings -notcontains $currentHeading)) {
            $changedHeadings += $currentHeading
        }
    }
}

if (-not $changedHeadings) { exit 0 }

# For each changed heading, compute the slug + grep doc for cross-refs.
function Get-Slug([string]$heading) {
    $s = $heading.ToLowerInvariant()
    # Drop punctuation GitHub strips.
    $s = $s -replace "[&(),.—–'""!?]", ''
    # Non-alphanumeric → hyphen.
    $s = $s -replace '[^a-z0-9]+', '-'
    $s = $s.Trim('-')
    return $s
}

$reportLines = @()
$reportLines += "## FINANCIAL_MODEL.md edit detected"
$reportLines += ""
$reportLines += "Changed data-point row(s): $($changedHeadings -join ', ')"
$reportLines += ""

$anyRefs = $false
foreach ($h in $changedHeadings) {
    $slug = Get-Slug $h
    if (-not $slug) { continue }
    # grep for (#$slug) anywhere in the file, exclude the heading line itself.
    $refs = & git grep -nF "(#$slug)" -- $filePath 2>$null | Where-Object { $_ -notmatch '^[^:]+:[0-9]+:##### ' }
    if ($refs) {
        $anyRefs = $true
        $reportLines += "### Cross-references to '$h' (anchor: #$slug)"
        $reportLines += '```'
        foreach ($r in $refs) {
            $reportLines += $r
        }
        $reportLines += '```'
        $reportLines += ""
    }
}

if (-not $anyRefs) {
    $reportLines += "(No other rows reference the changed data-point(s) — no cross-row review needed.)"
}

$reportLines += ""
$reportLines += "**Action required:** Spawn an Agent (subagent_type=general-purpose) to verify the cross-referencing rows above are still consistent with the edited data-point's new definition/formula/notes. The subagent has Edit access and should auto-apply fixes to any inconsistent rows. After the agent returns, run ``uv run pytest tests/docs/test_financial_model_appendix_f.py`` to confirm Layer-1 integrity is intact."

$context = ($reportLines -join "`n")

# Emit hookSpecificOutput JSON.
$output = @{
    hookSpecificOutput = @{
        hookEventName = 'PostToolUse'
        additionalContext = $context
    }
}
$output | ConvertTo-Json -Depth 10 -Compress
