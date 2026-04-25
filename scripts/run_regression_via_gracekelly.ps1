#!/usr/bin/env powershell
<#
.SYNOPSIS
    Regression wrapper for GraceKelly (claude-sonnet-4-6-api) via RAG pipeline.

.DESCRIPTION
    1. Validates GraceKelly is running and NOT in dry-run mode.
    2. Starts disposable postgres:16-alpine + redis:7-alpine (idempotent).
    3. Runs alembic migrations.
    4. Ingests docs/ into the vector store.
    5. Executes scripts/regression_eval.py baseline=ministral-3b-latest
       candidate=claude-sonnet-4-6 (browser.perplexity adapter) through
       gracekelly-primary profile.
    6. Cleans up disposable containers on exit.

.EXAMPLE
    .\scripts\run_regression_via_gracekelly.ps1
#>

[CmdletBinding()]
param(
    [string]$GraceKellyUrl = "http://127.0.0.1:8011",
    [string]$PostgresImage = "postgres:16-alpine",
    [string]$RedisImage = "redis:7-alpine",
    [int]$PostgresPort = 15432,
    [int]$RedisPort = 16379,
    [int]$PostgresContainerPort = 5432,
    [int]$RedisContainerPort = 6379,
    [string]$PostgresUser = "rag",
    [string]$PostgresPassword = "rag_test",
    [string]$PostgresDb = "rag_regression_test",
    [string]$Baseline = "ministral-3b-latest",
    [string]$Candidate = "claude-sonnet-4-6",
    [string]$CandidateProfile = "",
    [int]$MaxCases = 20
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-Fatal($msg) {
    Write-Host "FATAL: $msg" -ForegroundColor Red
    $cleanupVar = Get-Variable -Scope Script -Name StartedContainersToCleanup -ErrorAction SilentlyContinue
    if ($cleanupVar) {
        foreach ($containerName in $script:StartedContainersToCleanup) {
            docker stop $containerName 2>$null | Out-Null
            docker rm $containerName 2>$null | Out-Null
        }
    }
    exit 1
}

function Test-Command($cmd) {
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

function Import-DotEnv($path) {
    if (-not (Test-Path -LiteralPath $path)) {
        return
    }
    foreach ($line in Get-Content -LiteralPath $path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed -notmatch "^\s*([^#=\s]+)\s*=\s*(.*)\s*$") {
            continue
        }
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if (-not [Environment]::GetEnvironmentVariable($key, "Process")) {
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

function Get-GraceKellyHeaders {
    $headers = @{}
    $apiKey = $env:GRACEKELLY_API_KEY
    if ($apiKey) {
        $headers["Authorization"] = "Bearer $apiKey"
    }
    return $headers
}

function Invoke-GraceKelly($path, [bool]$AllowFailure = $true) {
    try {
        $resp = Invoke-RestMethod `
            -Uri "$GraceKellyUrl$path" `
            -Method GET `
            -Headers (Get-GraceKellyHeaders) `
            -TimeoutSec 5 `
            -ErrorAction Stop
        return $resp
    } catch {
        if (-not $AllowFailure) {
            Write-Fatal "GraceKelly request failed: $GraceKellyUrl$path ($($_.Exception.Message))"
        }
        return $null
    }
}

function Find-FirstPropertyValue($value, [string[]]$names) {
    if ($null -eq $value) {
        return $null
    }
    if ($value -is [string] -or $value -is [ValueType]) {
        return $null
    }

    foreach ($name in $names) {
        $property = $value.PSObject.Properties[$name]
        if ($null -ne $property -and $null -ne $property.Value) {
            return [string]$property.Value
        }
    }

    if ($value -is [System.Array]) {
        foreach ($item in $value) {
            $found = Find-FirstPropertyValue $item $names
            if ($found) {
                return $found
            }
        }
        return $null
    }

    if ($value -is [System.Collections.IDictionary]) {
        foreach ($key in $value.Keys) {
            if ($names -contains [string]$key -and $null -ne $value[$key]) {
                return [string]$value[$key]
            }
            $found = Find-FirstPropertyValue $value[$key] $names
            if ($found) {
                return $found
            }
        }
        return $null
    }

    foreach ($property in $value.PSObject.Properties) {
        $found = Find-FirstPropertyValue $property.Value $names
        if ($found) {
            return $found
        }
    }

    return $null
}

$ProjectRoot = (Split-Path -Parent $PSScriptRoot | Resolve-Path).Path
Import-DotEnv (Join-Path $ProjectRoot ".env")

# ---------------------------------------------------------------------------
# 1. GraceKelly readiness guard
# ---------------------------------------------------------------------------
$ready = Invoke-GraceKelly "/healthz/ready"
if (-not $ready -or $ready.status -ne "ok") {
    Write-Fatal @"
GraceKelly is not responding on $GraceKellyUrl/healthz/ready.
Start it first:
    cd D:\GraceKelly
    uvicorn gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011
"@
}

# ---------------------------------------------------------------------------
# 2. GraceKelly execution profile guard (fail-fast on dry-run)
# ---------------------------------------------------------------------------
$adminProviders = Invoke-GraceKelly "/api/admin/providers"
$profile = Find-FirstPropertyValue $adminProviders @(
    "GRACEKELLY_EXECUTION_PROFILE",
    "execution_profile",
    "executionProfile"
)
if (-not $profile) {
    $readiness = Invoke-GraceKelly "/api/v1/readiness" $false
    $profile = Find-FirstPropertyValue $readiness @(
        "GRACEKELLY_EXECUTION_PROFILE",
        "execution_profile",
        "executionProfile"
    )
}
if (-not $profile) {
    Write-Fatal "Could not determine GraceKelly execution profile from /api/admin/providers or /api/v1/readiness."
}
if ($profile -eq "dry-run") {
    Write-Fatal @"
GraceKelly is in execution_profile=dry-run.
Switch to real execution before running regression:
    # Option A: override env at startup
    `$env:GRACEKELLY_EXECUTION_PROFILE = "hybrid"
    uvicorn gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011

    # Option B: edit D:\GraceKelly\.env (requires confirmation)
"@
}
Write-Host "GraceKelly OK (profile=$profile)"

# ---------------------------------------------------------------------------
# 2b. Browser-route candidate. The alias `claude-sonnet-4-6` resolves in
#     GraceKelly to the browser.perplexity adapter; if the browser session
#     is dead, the regression run will fail-fast on the first request with
#     `[provider_unavailable]`. We do not pre-validate readiness here because
#     /api/v1/readiness reports the session as `degraded` until first launch.
# ---------------------------------------------------------------------------
Write-Host "Candidate '$Candidate' routes through browser.perplexity (lazy-launched on first request)."

# ---------------------------------------------------------------------------
# 3. Docker guards
# ---------------------------------------------------------------------------
if (-not (Test-Command "docker")) {
    Write-Fatal "docker CLI not found in PATH."
}

$pgContainer = "rag-regression-postgres"
$redisContainer = "rag-regression-redis"
$startedPg = $false
$startedRedis = $false
$script:StartedContainersToCleanup = @()

function Get-MappedHostPort($name, $containerPort) {
    $mapping = docker port $name "$containerPort/tcp" 2>$null | Select-Object -First 1
    if (-not $mapping) {
        return $null
    }
    return ($mapping -split ":")[-1]
}

function Wait-ContainerReady($name) {
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 1
        if ($name -eq $pgContainer) {
            docker exec $name pg_isready -U $PostgresUser -d $PostgresDb 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Container $name is ready (pg_isready)"
                return
            }
        } elseif ($name -eq $redisContainer) {
            $probe = docker exec $name redis-cli ping 2>$null
            if ($probe -eq "PONG") {
                Write-Host "Container $name is ready (PONG)"
                return
            }
        }
    }
    Write-Fatal "Container $name did not become ready in 45s"
}

function Ensure-Container($name, $image, $hostPort, $containerPort, $envVars) {
    $existing = docker ps -aq -f "name=^/$name$" 2>$null | Select-Object -First 1
    if ($existing) {
        $running = docker ps -q -f "name=^/$name$" 2>$null | Select-Object -First 1
        if ($running) {
            Write-Host "Reusing already-running container: $name"
            $mappedPort = Get-MappedHostPort $name $containerPort
            if (-not $mappedPort) {
                Write-Fatal "Container $name is running but does not publish $containerPort/tcp."
            }
            Wait-ContainerReady $name
            return [pscustomobject]@{ Started = $false; HostPort = [int]$mappedPort }
        } else {
            Write-Host "Removing stopped container: $name"
            docker rm -f $name 2>$null | Out-Null
        }
    }

    Write-Host "Starting container: $name"
    $runArgs = @("run", "-d", "--name", $name, "-p", "${hostPort}:${containerPort}")
    foreach ($e in $envVars) {
        $runArgs += "-e"
        $runArgs += $e
    }
    $runArgs += $image

    & docker @runArgs | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fatal "Failed to start container $name"
    }
    $script:StartedContainersToCleanup += $name

    Wait-ContainerReady $name
    return [pscustomobject]@{ Started = $true; HostPort = $hostPort }
}

# ---------------------------------------------------------------------------
# 4. Start infrastructure
# ---------------------------------------------------------------------------
$pgEnv = @(
    "POSTGRES_USER=$PostgresUser",
    "POSTGRES_PASSWORD=$PostgresPassword",
    "POSTGRES_DB=$PostgresDb"
)
$pgContainerState = Ensure-Container $pgContainer $PostgresImage $PostgresPort $PostgresContainerPort $pgEnv
$redisContainerState = Ensure-Container $redisContainer $RedisImage $RedisPort $RedisContainerPort @()
$startedPg = [bool]$pgContainerState.Started
$startedRedis = [bool]$redisContainerState.Started
$PostgresHostPort = [int]$pgContainerState.HostPort
$RedisHostPort = [int]$redisContainerState.HostPort

# ---------------------------------------------------------------------------
# 5. Build env for the regression run
# ---------------------------------------------------------------------------
$DatabaseUrlAsync = "postgresql+asyncpg://${PostgresUser}:${PostgresPassword}@localhost:${PostgresHostPort}/${PostgresDb}"
$DatabaseUrlSync = "postgresql+psycopg2://${PostgresUser}:${PostgresPassword}@localhost:${PostgresHostPort}/${PostgresDb}"
$env:DATABASE_URL = $DatabaseUrlAsync
$env:REDIS_URL = "redis://localhost:${RedisHostPort}/0"
$env:LLM_PROVIDER_PROFILE = "gracekelly-primary"
$env:GRACEKELLY_BASE_URL = $GraceKellyUrl
if (-not $env:HF_HUB_OFFLINE) {
    $env:HF_HUB_OFFLINE = "1"
}
if (-not $env:TRANSFORMERS_OFFLINE) {
    $env:TRANSFORMERS_OFFLINE = "1"
}
if (-not $env:DB_ENCRYPTION_KEY) {
    $env:DB_ENCRYPTION_KEY = "regression-disposable-$([Guid]::NewGuid().ToString('N'))"
    Write-Host "Using generated disposable DB_ENCRYPTION_KEY for regression database."
}

# Preserve existing MISTRAL_API_KEY if set; otherwise fail before baseline calls.
if (-not $env:MISTRAL_API_KEY) {
    Write-Fatal "MISTRAL_API_KEY is not set in the process environment or project .env."
}

Push-Location $ProjectRoot

$exitCode = 0
try {
    # -----------------------------------------------------------------------
    # 6. Alembic migrations
    # -----------------------------------------------------------------------
    Write-Host "Running alembic upgrade head..."
    $env:DATABASE_URL = $DatabaseUrlSync
    try {
        alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            Write-Fatal "alembic upgrade head failed"
        }
    } finally {
        $env:DATABASE_URL = $DatabaseUrlAsync
    }

    # -----------------------------------------------------------------------
    # 7. Ingest seed docs
    # -----------------------------------------------------------------------
    Write-Host "Ingesting docs/ into vector store..."
    $ingestPy = @"
import sys
import shutil
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import ingestion.pipeline as ingestion_pipeline

def _annotate_without_llm(docs, tenant_id='default'):
    assigned = {}
    for index, doc in enumerate(docs):
        metadata = getattr(doc, 'metadata', None)
        if not isinstance(metadata, dict):
            metadata = {}
            setattr(doc, 'metadata', metadata)
        source = str(metadata.get('source') or metadata.get('file_name') or metadata.get('file_path') or f'document-{index}')
        source_name = Path(source).name
        metadata['categories'] = ['uncategorized']
        metadata['primary_category'] = 'uncategorized'
        metadata.setdefault('doc_id', source_name)
        metadata.setdefault('title', source_name)
        assigned[source_name] = ['uncategorized']
    return assigned

ingestion_pipeline.annotate_documents_with_categories = _annotate_without_llm
from ingestion.pipeline import IngestPipeline
seed_docs = ('warranty.md', 'returns_policy.md', 'errors_e10_e30.md')
with tempfile.TemporaryDirectory() as tmp_dir:
    tmp_path = Path(tmp_dir)
    for name in seed_docs:
        shutil.copy2(Path('docs') / name, tmp_path / name)
    vs, chunks = IngestPipeline().ingest(tmp_path, tenant_id='default')
print(f'Ingested {len(chunks)} chunks from {len(seed_docs)} seed docs')
"@
    python -c $ingestPy
    if ($LASTEXITCODE -ne 0) {
        Write-Fatal "Doc ingestion failed"
    }

    # -----------------------------------------------------------------------
    # 8. Run regression
    # -----------------------------------------------------------------------
    if ($CandidateProfile) {
        Write-Host "Running regression: baseline=$Baseline candidate-profile=$CandidateProfile max_cases=$MaxCases ..."
        python scripts/regression_eval.py `
            --baseline $Baseline `
            --candidate-profile $CandidateProfile `
            --allow-paid-apis `
            --max-cases $MaxCases
    } else {
        Write-Host "Running regression: baseline=$Baseline candidate=$Candidate max_cases=$MaxCases ..."
        python scripts/regression_eval.py `
            --baseline $Baseline `
            --candidate $Candidate `
            --allow-paid-apis `
            --max-cases $MaxCases
    }

    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Warning "Regression eval exited with code $exitCode"
    } else {
        Write-Host "Regression completed successfully." -ForegroundColor Green
    }
} finally {
    Pop-Location

    # -----------------------------------------------------------------------
    # 9. Cleanup containers we started
    # -----------------------------------------------------------------------
    if ($startedPg -and (docker ps -aq -f "name=^/$pgContainer$" 2>$null)) {
        Write-Host "Stopping postgres container $pgContainer ..."
        docker stop $pgContainer 2>$null | Out-Null
        docker rm $pgContainer 2>$null | Out-Null
    }
    if ($startedRedis -and (docker ps -aq -f "name=^/$redisContainer$" 2>$null)) {
        Write-Host "Stopping redis container $redisContainer ..."
        docker stop $redisContainer 2>$null | Out-Null
        docker rm $redisContainer 2>$null | Out-Null
    }
}

exit $exitCode
