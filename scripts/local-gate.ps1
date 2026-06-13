[CmdletBinding()]
param(
    [switch]$List,
    [switch]$DryRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Test-Tool {
    param([string]$Name)
    return ($null -ne (Get-Command $Name -ErrorAction SilentlyContinue))
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

function Invoke-Checked {
    param(
        [string]$Name,
        [string]$Command,
        [string[]]$Arguments
    )
    Write-Host ("RUN: {0} {1}" -f $Command, ($Arguments -join " "))
    Push-Location $ProjectRoot
    try {
        & $Command @Arguments
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

function Get-ChangedPaths {
    Push-Location $ProjectRoot
    try {
        $lines = & git status --porcelain --untracked-files=all
        if ($LASTEXITCODE -ne 0) {
            throw "git status failed"
        }
    }
    finally {
        Pop-Location
    }

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
        $paths.Add(($raw.Trim('"') -replace "\\", "/"))
    }
    return $paths
}

function Add-Gate {
    param(
        [System.Collections.Generic.List[object]]$Gates,
        [string]$Name,
        [string]$Command,
        [string[]]$Arguments
    )
    $Gates.Add(
        [pscustomobject]@{
            Name = $Name
            Command = $Command
            Arguments = $Arguments
        }
    ) | Out-Null
}

function Format-Gate {
    param([object]$Gate)
    return "{0} {1}" -f $Gate.Command, ($Gate.Arguments -join " ")
}

$changed = Get-ChangedPaths
$helmTouched = $false
$requirementsTouched = $false
$dependencyFiles = @("requirements.txt", "requirements-dev.txt", "requirements.lock", "requirements-dev.lock")
foreach ($path in $changed) {
    if ($path.StartsWith("deploy/helm/")) {
        $helmTouched = $true
    }
    if ($dependencyFiles -contains $path) {
        $requirementsTouched = $true
    }
}

$gates = New-Object System.Collections.Generic.List[object]
Add-Gate $gates "git diff --check" "git" @("diff", "--check")
Add-Gate $gates "ruff" "ruff" @("check", ".")
Add-Gate $gates "mypy strict scope" "python" @("-m", "mypy", "auth", "db", "llm/providers/", "config/settings.py", "agent/state.py", "agent/prompts.py", "agent/prompt_registry.py", "agent/tools.py", "agent/graph.py", "tasks", "utils", "--no-incremental", "--show-error-codes")
Add-Gate $gates "mypy api.app" "python" @("-m", "mypy", "api/app.py", "--no-incremental", "--follow-imports=skip", "--show-error-codes")
Add-Gate $gates "unit tests" "python" @("-m", "pytest", "tests/", "-q", "--ignore=tests/integration", "-p", "no:schemathesis", "-p", "no:cacheprovider", "--basetemp=.tmp/pytest")
if ($helmTouched) {
    Add-Gate $gates "helm lint" "helm" @("lint", "deploy/helm/", "--strict")
}
if ($requirementsTouched) {
    Add-Gate $gates "pip-audit" "pip-audit" @("--strict", "--disable-pip", "--require-hashes", "--timeout", "15", "--progress-spinner", "off", "--cache-dir", ".tmp/pip-audit-cache", "--ignore-vuln", "CVE-2026-45829", "--ignore-vuln", "GHSA-f4j7-r4q5-qw2c", "--ignore-vuln", "CVE-2025-3000", "-r", "requirements.lock")
}

if ($List -or $DryRun) {
    Write-Host "Local gate commands:"
    foreach ($gate in $gates) {
        Write-Host ("- {0}" -f (Format-Gate $gate))
    }
    if (-not $helmTouched) {
        Write-Host "- helm lint deploy/helm/ --strict (skipped: deploy/helm/ unchanged)"
    }
    if (-not $requirementsTouched) {
        Write-Host "- pip-audit --strict --disable-pip --require-hashes --timeout 15 --progress-spinner off --cache-dir .tmp/pip-audit-cache --ignore-vuln CVE-2026-45829 --ignore-vuln GHSA-f4j7-r4q5-qw2c --ignore-vuln CVE-2025-3000 -r requirements.lock (skipped: dependency files unchanged)"
    }
    if ($DryRun) {
        foreach ($tool in @("git", "python", "ruff", "mypy", "pytest")) {
            if (Test-Tool $tool) {
                Write-Host ("Tool available: {0}" -f $tool)
            }
            else {
                Write-Host ("Tool missing: {0}" -f $tool)
            }
        }
    }
    exit 0
}

if (-not (Test-Tool "git")) {
    throw "Required gate tool is unavailable: git"
}
if (-not (Test-Tool "ruff")) {
    throw "Required gate tool is unavailable: ruff"
}
if (-not (Test-PythonModule "mypy")) {
    throw "Required Python module is unavailable: mypy"
}
if (-not (Test-PythonModule "pytest")) {
    throw "Required Python module is unavailable: pytest"
}
if ($helmTouched -and -not (Test-Tool "helm")) {
    throw "Required gate tool is unavailable: helm"
}
if ($requirementsTouched -and -not (Test-Tool "pip-audit")) {
    throw "Required gate tool is unavailable: pip-audit"
}

foreach ($gate in $gates) {
    Invoke-Checked $gate.Name $gate.Command $gate.Arguments
}
