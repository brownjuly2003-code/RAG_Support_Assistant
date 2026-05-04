[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$NoCommit,
    [int]$PlannerTimeoutSec = 180,
    [int]$ExecutorTimeoutSec = 3600
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AutopilotDir = Join-Path $ProjectRoot ".autopilot"
$LockPath = Join-Path $AutopilotDir "LOCK"
$PausePath = Join-Path $AutopilotDir "PAUSE"
$BlockedPath = Join-Path $AutopilotDir "BLOCKED.md"
$NextTaskPath = Join-Path $AutopilotDir "NEXT_TASK.md"
$AllowedPathsPath = Join-Path $AutopilotDir "allowed-paths.txt"
$CommitMessagePath = Join-Path $AutopilotDir "commit-message.txt"
$LogPath = Join-Path $AutopilotDir "run.log"

function Ensure-AutopilotDir {
    if (-not (Test-Path -Path $AutopilotDir)) {
        New-Item -ItemType Directory -Path $AutopilotDir -Force | Out-Null
    }
}

function Write-Log {
    param([string]$Message)
    Ensure-AutopilotDir
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"), $Message
    Add-Content -Path $LogPath -Value $line
    Write-Host $Message
}

function Write-Blocked {
    param([string]$Reason)
    Ensure-AutopilotDir
    $body = "# Autopilot Blocked`n`nReason: $Reason`n`nTime: $(Get-Date -Format "yyyy-MM-ddTHH:mm:ssK")`n"
    [System.IO.File]::WriteAllText($BlockedPath, $body, [System.Text.Encoding]::UTF8)
    Write-Log "BLOCKED: $Reason"
}

function Test-Tool {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    return ($null -ne $cmd)
}

function Invoke-Checked {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments
    )
    $printable = "$FilePath $($Arguments -join ' ')"
    Write-Log "RUN: $printable"
    Push-Location $ProjectRoot
    try {
        & $FilePath @Arguments
        $code = $LASTEXITCODE
        if ($null -eq $code) {
            $code = 0
        }
        if ($code -ne 0) {
            throw "$Name failed with exit code $code"
        }
    }
    finally {
        Pop-Location
    }
}

function Stop-ProcessTree {
    param([int]$ProcessId)
    $children = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ParentProcessId -eq $ProcessId }
    foreach ($child in $children) {
        Stop-ProcessTree ([int]$child.ProcessId)
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Invoke-PiPlanner {
    param([string]$Prompt)
    $runnerPath = Join-Path $AutopilotDir "planner-runner.ps1"
    $promptPath = Join-Path $AutopilotDir "planner.prompt.md"
    $stdoutPath = Join-Path $AutopilotDir "planner.stdout.tmp"
    $stderrPath = Join-Path $AutopilotDir "planner.stderr.tmp"
    $exitCodePath = Join-Path $AutopilotDir "planner.exitcode.tmp"
    $escapedProjectRoot = $ProjectRoot -replace "'", "''"
    $escapedExitCodePath = $exitCodePath -replace "'", "''"
    [System.IO.File]::WriteAllText($promptPath, $Prompt, [System.Text.Encoding]::UTF8)
    $runner = @"
`$ErrorActionPreference = "Stop"
Set-Location -Path '$escapedProjectRoot'
`$env:OPENAI_API_KEY = `$null
`$promptArg = '@.autopilot/planner.prompt.md'
& pi --model openai-codex/gpt-5.3-codex-spark --thinking minimal --tools write --no-session --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files -p `$promptArg
`$code = `$LASTEXITCODE
if (`$null -eq `$code) {
    `$code = 0
}
[System.IO.File]::WriteAllText('$escapedExitCodePath', [string]`$code, [System.Text.Encoding]::UTF8)
exit `$code
"@
    [System.IO.File]::WriteAllText($runnerPath, $runner, [System.Text.Encoding]::UTF8)
    Remove-Item -Path $stdoutPath,$stderrPath,$exitCodePath -Force -ErrorAction SilentlyContinue
    Write-Log "RUN: pi --model openai-codex/gpt-5.3-codex-spark --thinking minimal --tools write --no-session -p @.autopilot/planner.prompt.md"
    $process = Start-Process -FilePath "powershell" -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", $runnerPath) -WorkingDirectory $ProjectRoot -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
    try {
        $timeoutMs = [Math]::Max(1, $PlannerTimeoutSec) * 1000
        if (-not $process.WaitForExit($timeoutMs)) {
            Stop-ProcessTree ([int]$process.Id)
            if ((Test-Path -Path $NextTaskPath) -and (Test-Path -Path $AllowedPathsPath)) {
                Write-Log "Planner timed out after ${PlannerTimeoutSec}s after writing artifacts; stopped planner process."
                return
            }
            throw "pi planner timed out after ${PlannerTimeoutSec}s without required artifacts"
        }

        $process.WaitForExit()
        $process.Refresh()
        $code = $null
        if (Test-Path -Path $exitCodePath) {
            $rawCode = [System.IO.File]::ReadAllText($exitCodePath).Trim()
            if ($rawCode -match "^-?\d+$") {
                $code = [int]$rawCode
            }
        }
        if ($null -eq $code -and $null -ne $process.ExitCode) {
            $code = $process.ExitCode
        }
        if ($null -eq $code) {
            throw "pi planner did not report an exit code"
        }
        if ($code -ne 0) {
            throw "pi planner failed with exit code $code"
        }
    }
    finally {
        Remove-Item -Path $runnerPath,$promptPath,$stdoutPath,$stderrPath,$exitCodePath -Force -ErrorAction SilentlyContinue
    }
}

function Get-GitLines {
    param([string[]]$Arguments)
    Push-Location $ProjectRoot
    try {
        $lines = & git @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "git $($Arguments -join ' ') failed"
        }
        return $lines
    }
    finally {
        Pop-Location
    }
}

function Read-PlannerContextFile {
    param(
        [string]$RelativePath,
        [int]$MaxChars = 12000
    )
    $path = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -Path $path)) {
        return "## $RelativePath`n[MISSING]"
    }
    $text = [System.IO.File]::ReadAllText($path)
    if ($text.Length -gt $MaxChars) {
        $text = "$($text.Substring(0, $MaxChars))`n[TRUNCATED]"
    }
    return "## $RelativePath`n$text"
}

function Join-ContextLines {
    param(
        [string[]]$Lines,
        [string]$EmptyText
    )
    if ($Lines.Count -eq 0) {
        return $EmptyText
    }
    return [System.String]::Join("`n", $Lines)
}

function Get-PlannerContext {
    $statusLines = @(Get-GitLines @("status", "--short"))
    $logLines = @(Get-GitLines @("log", "--oneline", "-12"))
    $docsRoot = Join-Path $ProjectRoot "docs"
    $docsLines = @()
    if (Test-Path -Path $docsRoot) {
        $docsLines = @(
            Get-ChildItem -Path $docsRoot -Recurse -Filter "*.md" |
                Sort-Object -Property FullName |
                Select-Object -First 80 |
                ForEach-Object { Normalize-RepoPath ($_.FullName.Substring($ProjectRoot.Length + 1)) }
        )
    }
    $statusText = Join-ContextLines $statusLines "clean"
    $logText = Join-ContextLines $logLines "[no git log output]"
    $docsText = Join-ContextLines $docsLines "[no docs markdown files found]"
    $agentState = Read-PlannerContextFile "AGENT_STATE.md"
    $backlog = Read-PlannerContextFile "BACKLOG.md"
    $readme = Read-PlannerContextFile "README.md" 8000
    $activePlan = Read-PlannerContextFile "docs/plans/2026-05-01-backlog.md"

    return @"
## git status --short
$statusText

## git log --oneline -12
$logText

## docs markdown files
$docsText

$agentState

$backlog

$readme

$activePlan
"@
}

function Test-CommitSubjectExists {
    param([string]$Subject)
    $subjects = Get-GitLines @("log", "--format=%s")
    foreach ($line in $subjects) {
        if ($line -eq $Subject) {
            return $true
        }
    }
    return $false
}

function Normalize-RepoPath {
    param([string]$Path)
    $p = $Path.Trim()
    if ($p.StartsWith('"') -and $p.EndsWith('"')) {
        $p = $p.Trim('"')
    }
    return ($p -replace "\\", "/")
}

function Get-ChangedPaths {
    $lines = Get-GitLines @("status", "--porcelain", "--untracked-files=all")
    $paths = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.Length -lt 4) {
            continue
        }
        $raw = $line.Substring(3)
        if ($raw -match " -> ") {
            $parts = $raw -split " -> "
            $raw = $parts[$parts.Length - 1]
        }
        $paths.Add((Normalize-RepoPath $raw))
    }
    return ,$paths
}

function Get-AllowedPaths {
    if (-not (Test-Path -Path $AllowedPathsPath)) {
        throw "Missing .autopilot/allowed-paths.txt"
    }
    $allowed = New-Object System.Collections.Generic.List[string]
    foreach ($line in [System.IO.File]::ReadAllLines($AllowedPathsPath)) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
            continue
        }
        $allowed.Add((Normalize-RepoPath $trimmed))
    }
    if ($allowed.Count -eq 0) {
        throw ".autopilot/allowed-paths.txt is empty"
    }
    return ,$allowed
}

function Test-PathAllowed {
    param(
        [string]$Path,
        [System.Collections.Generic.List[string]]$Allowed
    )
    foreach ($entry in $Allowed) {
        $candidate = $entry.TrimEnd("/")
        if ($Path -eq $candidate -or $Path.StartsWith("$candidate/")) {
            return $true
        }
    }
    return $false
}

function Assert-ChangedFilesAllowed {
    $allowed = Get-AllowedPaths
    $changed = Get-ChangedPaths
    foreach ($path in $changed) {
        if (-not (Test-PathAllowed $path $allowed)) {
            throw "Changed file outside allowed paths: $path"
        }
    }
    return ,$changed
}

function Assert-CleanTree {
    $changed = Get-ChangedPaths
    if ($changed.Count -ne 0) {
        throw "Git tree is dirty: $($changed -join ', ')"
    }
}

function Get-CommitAllowed {
    if (-not (Test-Path -Path $NextTaskPath)) {
        return $false
    }
    $task = [System.IO.File]::ReadAllText($NextTaskPath)
    return ($task -match "(?im)^\s*commit allowed:\s*yes\s*$")
}

function Get-CommitMessage {
    if (Test-Path -Path $CommitMessagePath) {
        $message = [System.IO.File]::ReadAllText($CommitMessagePath).Trim()
        if ($message.Length -gt 0) {
            return $message
        }
    }
    return "autopilot: apply bounded task"
}

function Test-PythonModule {
    param([string]$ModuleName)
    if (-not (Test-Tool "python")) {
        return $false
    }
    Push-Location $ProjectRoot
    try {
        & python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)"
        return ($LASTEXITCODE -eq 0)
    }
    finally {
        Pop-Location
    }
}

function Add-RuntimeGap {
    param([string]$Gap)
    $gapPath = Join-Path $AutopilotDir "RUNTIME_GAPS.md"
    Add-Content -Path $gapPath -Value "- $Gap"
    Write-Log "GAP: $Gap"
}

function Invoke-Gates {
    $changed = Get-ChangedPaths
    Invoke-Checked "git diff --check" "git" @("diff", "--check")

    if (Test-DocsOnlyChange $changed) {
        if (Test-Tool "ruff") {
            Invoke-Checked "ruff docs tests" "ruff" @("check", "tests/test_docs_quality.py", "tests/test_quickstart_docs.py")
        }
        else {
            Add-RuntimeGap "ruff is unavailable; skipped docs lint gate."
            throw "Required lint gate is unavailable"
        }

        if (Test-PythonModule "pytest") {
            Invoke-Checked "docs tests" "python" @("-m", "pytest", "-p", "no:schemathesis", "tests/test_docs_quality.py", "tests/test_quickstart_docs.py")
        }
        else {
            Add-RuntimeGap "pytest is unavailable; skipped docs test gate."
            throw "Required test gate is unavailable"
        }
        return
    }

    if (Test-Tool "ruff") {
        Invoke-Checked "ruff" "ruff" @("check", ".")
    }
    else {
        Add-RuntimeGap "ruff is unavailable; skipped lint gate."
        throw "Required lint gate is unavailable"
    }

    if (Test-PythonModule "mypy") {
        Invoke-Checked "mypy strict scope 1" "python" @("-m", "mypy", "auth", "db/models.py", "db/engine.py", "llm/providers/", "config/settings.py", "agent/state.py", "agent/prompts.py", "agent/prompt_registry.py", "agent/tools.py", "agent/graph.py", "--no-incremental", "--show-error-codes")
        Invoke-Checked "mypy api.app" "python" @("-m", "mypy", "api/app.py", "--no-incremental", "--follow-imports=skip", "--show-error-codes")
    }
    else {
        Add-RuntimeGap "mypy is unavailable; skipped type-check gate."
        throw "Required type-check gate is unavailable"
    }

    if (Test-PythonModule "pytest") {
        Invoke-Checked "unit tests" "python" @("-m", "pytest", "tests/", "-q", "--ignore=tests/integration", "-p", "no:schemathesis", "-p", "no:cacheprovider", "--basetemp=.tmp/pytest")
    }
    else {
        Add-RuntimeGap "pytest is unavailable; skipped unit-test gate."
        throw "Required unit-test gate is unavailable"
    }

    $helmTouched = $false
    foreach ($path in $changed) {
        if ($path.StartsWith("deploy/helm/")) {
            $helmTouched = $true
        }
    }
    if ($helmTouched) {
        if (Test-Tool "helm") {
            Invoke-Checked "helm lint" "helm" @("lint", "deploy/helm/", "--strict")
        }
        else {
            Add-RuntimeGap "helm is unavailable; skipped Helm gate."
            throw "Required Helm gate is unavailable"
        }
    }

    $requirementsTouched = $false
    foreach ($path in $changed) {
        if ($path -eq "requirements.lock" -or $path -eq "requirements-dev.lock") {
            $requirementsTouched = $true
        }
    }
    if ($requirementsTouched) {
        if (Test-Tool "pip-audit") {
            Invoke-Checked "pip-audit" "pip-audit" @("--strict", "--disable-pip", "--require-hashes", "-r", "requirements.lock")
        }
        else {
            Add-RuntimeGap "pip-audit is unavailable; skipped dependency audit gate."
            throw "Required dependency audit gate is unavailable"
        }
    }
}

function Test-DocsOnlyChange {
    param([System.Collections.Generic.List[string]]$Changed)
    if ($Changed.Count -eq 0) {
        return $false
    }
    foreach ($path in $Changed) {
        if ($path -eq "tests/test_docs_quality.py" -or $path -eq "tests/test_quickstart_docs.py") {
            continue
        }
        if ($path -eq "BACKLOG.md" -or $path -eq "2026-05-02-non-live-backlog.md") {
            continue
        }
        if ($path.StartsWith("docs/") -and $path.EndsWith(".md")) {
            continue
        }
        if ($path.EndsWith(".md") -and -not $path.Contains("/")) {
            continue
        }
        return $false
    }
    return $true
}

function Invoke-Planner {
    if (Test-Path -Path $NextTaskPath) {
        Remove-Item -Path $NextTaskPath -Force
    }
    if (Test-Path -Path $AllowedPathsPath) {
        Remove-Item -Path $AllowedPathsPath -Force
    }
    if (Test-Path -Path $CommitMessagePath) {
        Remove-Item -Path $CommitMessagePath -Force
    }

    $context = Get-PlannerContext
    $prompt = @"
You are the pi.dev planner for this repository. The runner has already read the repository context below. Use that context; do not claim you lack file access. Choose exactly one bounded task.

Write .autopilot/NEXT_TASK.md with:
- task title
- why this is next
- allowed files or directories
- acceptance criteria
- required verification
- commit allowed: yes/no
- suggested commit message

Also write .autopilot/allowed-paths.txt with one repo-relative allowed file or directory per line.
Also write .autopilot/commit-message.txt with one short commit message.
Do not edit product code. Do not ask the user anything. If no safe task exists, write .autopilot/BLOCKED.md instead.

Use only the write tool to create `.autopilot/NEXT_TASK.md`, `.autopilot/allowed-paths.txt`, and `.autopilot/commit-message.txt` or `.autopilot/BLOCKED.md`.

Repository context:
$context
"@

    try {
        Invoke-PiPlanner $prompt
    }
    catch {
        Write-Log "Planner failed: $($_.Exception.Message)"
        Invoke-BacklogPlanner
    }
    if (Test-Path -Path $BlockedPath) {
        throw "Planner wrote BLOCKED.md"
    }
    if (-not (Test-Path -Path $NextTaskPath)) {
        throw "Planner did not write NEXT_TASK.md"
    }
    if (-not (Test-Path -Path $AllowedPathsPath)) {
        throw "Planner did not write allowed-paths.txt"
    }
}

function Invoke-BacklogPlanner {
    $backlogPath = Join-Path $ProjectRoot "BACKLOG.md"
    if (-not (Test-Path -Path $backlogPath)) {
        throw "Planner failed and BACKLOG.md is missing"
    }

    $lines = [System.IO.File]::ReadAllLines($backlogPath)
    $queueStart = -1
    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i].Trim() -eq "## Autopilot Task Queue") {
            $queueStart = $i
            break
        }
    }
    if ($queueStart -lt 0) {
        throw "Planner failed and BACKLOG.md has no Autopilot Task Queue"
    }

    $taskStart = -1
    $searchStart = $queueStart + 1
    while ($searchStart -lt $lines.Length) {
        $candidateStart = -1
        for ($i = $searchStart; $i -lt $lines.Length; $i++) {
            if ($lines[$i] -match "^###\s+(.+)$") {
                $candidateStart = $i
                break
            }
            if ($lines[$i] -match "^##\s+") {
                break
            }
        }
        if ($candidateStart -lt 0) {
            break
        }

        $candidateLines = New-Object System.Collections.Generic.List[string]
        for ($i = $candidateStart; $i -lt $lines.Length; $i++) {
            if ($i -ne $candidateStart -and ($lines[$i] -match "^###\s+" -or $lines[$i] -match "^##\s+")) {
                break
            }
            $candidateLines.Add($lines[$i])
        }
        $candidateCommitMessage = $null
        foreach ($line in $candidateLines) {
            if ($line -match '^\s*-\s*Suggested commit message:\s*`([^`]+)`') {
                $candidateCommitMessage = $Matches[1]
            }
        }
        if ($null -ne $candidateCommitMessage -and (Test-CommitSubjectExists $candidateCommitMessage)) {
            Write-Log "Skipping completed backlog task: $candidateCommitMessage"
            $searchStart = $candidateStart + $candidateLines.Count
            continue
        }
        $taskStart = $candidateStart
        break
    }
    if ($taskStart -lt 0) {
        throw "Planner failed and Autopilot Task Queue has no task"
    }

    $taskLines = New-Object System.Collections.Generic.List[string]
    $title = ($lines[$taskStart] -replace "^###\s+", "").Trim()
    $taskLines.Add($lines[$taskStart])
    for ($i = $taskStart + 1; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -match "^###\s+" -or $lines[$i] -match "^##\s+") {
            break
        }
        $taskLines.Add($lines[$i])
    }

    $allowedLine = $null
    $commitAllowed = $false
    $commitMessage = "autopilot: apply bounded task"
    foreach ($line in $taskLines) {
        if ($line -match "^\s*-\s*Allowed files/directories:") {
            $allowedLine = $line
        }
        if ($line -match "^\s*-\s*Commit allowed:\s*yes\.?\s*$") {
            $commitAllowed = $true
        }
        if ($line -match '^\s*-\s*Suggested commit message:\s*`([^`]+)`') {
            $commitMessage = $Matches[1]
        }
    }
    if ($null -eq $allowedLine) {
        throw "Planner failed and selected backlog task has no allowed files"
    }

    $allowed = New-Object System.Collections.Generic.List[string]
    $matches = [regex]::Matches($allowedLine, '`([^`]+)`')
    foreach ($match in $matches) {
        $allowed.Add((Normalize-RepoPath $match.Groups[1].Value))
    }
    if ($allowed.Count -eq 0) {
        throw "Planner failed and selected backlog task has no parseable allowed paths"
    }

    $taskText = "# $title`n`n$([System.String]::Join("`n", $taskLines))`n`ncommit allowed: $(if ($commitAllowed) { "yes" } else { "no" })`n"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($NextTaskPath, $taskText, $utf8NoBom)
    [System.IO.File]::WriteAllText($AllowedPathsPath, [System.String]::Join("`n", $allowed), $utf8NoBom)
    [System.IO.File]::WriteAllText($CommitMessagePath, $commitMessage, $utf8NoBom)
    Write-Log "Falling back to BACKLOG.md autopilot task queue."
}

function Invoke-Executor {
    $task = [System.IO.File]::ReadAllText($NextTaskPath)
    $allowed = [System.IO.File]::ReadAllText($AllowedPathsPath)
    $prompt = @"
You are the Codex executor for this repository.

Read and execute only .autopilot/NEXT_TASK.md.

Allowed paths:
$allowed

Task:
$task

Rules:
- Edit only allowed paths.
- Write tests before backend behavior changes.
- Run relevant verification.
- Update AGENT_STATE.md and BACKLOG.md only if they are in the allowed paths.
- Do not commit.
- Do not push.
- Do not deploy.
- Do not read or print secrets.
- Do not call live external services or paid APIs.
- If blocked, write .autopilot/BLOCKED.md and stop.
"@
    try {
        Invoke-Checked "codex executor" "codex" @("exec", "--cd", $ProjectRoot, "--sandbox", "workspace-write", $prompt)
    }
    catch {
        Write-Log "Executor failed: $($_.Exception.Message)"
        Invoke-LocalExecutor
    }
}

function Invoke-LocalExecutor {
    $task = [System.IO.File]::ReadAllText($NextTaskPath)
    if ($task -match "Guard Historical Backlog Notes") {
        Invoke-LocalBacklogGuardTask
        return
    }
    throw "Executor failed and no local executor exists for this task"
}

function Invoke-LocalBacklogGuardTask {
    $path = Join-Path $ProjectRoot "tests\test_docs_quality.py"
    if (-not (Test-Path -Path $path)) {
        throw "Local backlog guard task requires tests/test_docs_quality.py"
    }
    $content = [System.IO.File]::ReadAllText($path)
    if ($content -match "test_top_level_backlog_notes_are_historical") {
        Write-Log "Local executor: backlog guard test already exists."
        return
    }
    $testBlock = @'


def test_top_level_backlog_notes_are_historical() -> None:
    backlog = (PROJECT_ROOT / "BACKLOG.md").read_text(encoding="utf-8")
    non_live = (PROJECT_ROOT / "2026-05-02-non-live-backlog.md").read_text(
        encoding="utf-8"
    )

    assert "Historical safe-task snapshot" in backlog
    assert "Historical completion note" in non_live
    assert "docs/plans/2026-05-01-backlog.md" in backlog
    assert "docs/plans/2026-05-01-backlog.md" in non_live
    assert "explicit live GraceKelly/Mistral opt-in" in backlog
    assert "explicit opt-in" in non_live
'@
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, "$content$testBlock`n", $utf8NoBom)
    Write-Log "Falling back to local executor."
}

function Invoke-ExplicitCommit {
    param([System.Collections.Generic.List[string]]$Changed)
    if ($NoCommit) {
        Write-Log "NoCommit set; leaving changes uncommitted."
        return
    }
    if (-not (Get-CommitAllowed)) {
        Write-Log "Task does not allow commit; leaving changes uncommitted."
        return
    }
    if ($Changed.Count -eq 0) {
        Write-Log "No changed files to commit."
        return
    }
    foreach ($path in $Changed) {
        Invoke-Checked "git add $path" "git" @("add", "--", $path)
    }
    Invoke-Checked "git diff --cached --check" "git" @("diff", "--cached", "--check")
    Invoke-Checked "git commit" "git" @("commit", "-m", (Get-CommitMessage))
}

function Invoke-DryRun {
    Ensure-AutopilotDir
    Write-Log "Dry run started."
    foreach ($tool in @("git", "pi", "codex", "python", "ruff", "pytest", "mypy")) {
        if (Test-Tool $tool) {
            Write-Log "Tool available: $tool"
        }
        else {
            Write-Log "Tool missing: $tool"
        }
    }
    if (Test-Path -Path $PausePath) {
        Write-Log "PAUSE protocol: runner would stop."
    }
    else {
        Write-Log "PAUSE protocol: no pause file present."
    }
    if (Test-Path -Path $BlockedPath) {
        Write-Log "BLOCKED protocol: runner would stop."
    }
    else {
        Write-Log "BLOCKED protocol: no blocker file present."
    }
    Write-Log "Allowed-paths protocol: runner will require .autopilot/allowed-paths.txt before execution changes are accepted."
    Invoke-Checked "git diff --check" "git" @("diff", "--check")
    Write-Log "Dry run completed."
}

Ensure-AutopilotDir

if ($DryRun) {
    Invoke-DryRun
    exit 0
}

$lockStream = $null
try {
    if (Test-Path -Path $PausePath) {
        Write-Log "PAUSE exists; exiting."
        exit 0
    }
    if (Test-Path -Path $BlockedPath) {
        Write-Log "BLOCKED.md exists; exiting."
        exit 1
    }
    Assert-CleanTree
    $lockStream = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $lockBytes = [System.Text.Encoding]::UTF8.GetBytes("pid=$PID time=$(Get-Date -Format "yyyy-MM-ddTHH:mm:ssK")")
    $lockStream.Write($lockBytes, 0, $lockBytes.Length)
    $lockStream.Flush()

    Invoke-Planner
    $plannerChanges = Get-ChangedPaths
    if ($plannerChanges.Count -ne 0) {
        throw "Planner changed tracked files: $($plannerChanges -join ', ')"
    }

    Invoke-Executor
    if (Test-Path -Path $BlockedPath) {
        throw "Executor wrote BLOCKED.md"
    }
    $changed = Assert-ChangedFilesAllowed
    Invoke-Gates
    Invoke-ExplicitCommit $changed
    Write-Log "Autopilot run finished."
}
catch {
    Write-Blocked $_.Exception.Message
    exit 1
}
finally {
    if ($null -ne $lockStream) {
        $lockStream.Close()
        $lockStream.Dispose()
    }
    if (Test-Path -Path $LockPath) {
        Remove-Item -Path $LockPath -Force
    }
}
