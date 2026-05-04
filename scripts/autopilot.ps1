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

    $prompt = @"
You are the pi.dev planner for this repository. Read AGENT_STATE.md, BACKLOG.md, README.md, docs, and git state. Choose exactly one bounded task.

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
"@

    Invoke-Checked "pi planner" "pi" @("--tools", "read,grep,find,ls,write", "--no-session", "-p", $prompt)
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
    Invoke-Checked "codex executor" "codex" @("exec", "--cd", $ProjectRoot, "--sandbox", "workspace-write", "--ask-for-approval", "never", $prompt)
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
