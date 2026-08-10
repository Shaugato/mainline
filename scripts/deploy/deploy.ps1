# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

<#
.SYNOPSIS
  Clean checkout to a working https:// demo URL, in one command. Windows twin of
  scripts/deploy/deploy.sh.

.DESCRIPTION
  Ten stages, run in order, and NOT ONE OF THEM CONTINUES PAST A FAILURE. That is the
  whole design rule: a deploy script that carries on after a broken stage produces a URL
  serving yesterday's bytes, and there is no worse outcome for a submission whose entire
  claim is that it does not lie about what it is showing you.

      0  preflight        who am I, what is installed, is the DSN set
      1  state backend    scripts/deploy/bootstrap_state.sh
      2  secret           aws ssm put-parameter --type SecureString  (never echoed)
      3  database         cloud_chain.py then seed_demo.py           (idempotent)
      4  lambda package   scripts/deploy/build_lambda.ps1            (skipped by -Phase1)
      5  site payload     console build, then capture_demo_bundle.py
      6  infrastructure   terraform init + apply
      7  publish          aws s3 sync + CloudFront invalidation
      8  proof            demo_acceptance.py against the live URL — MUST exit 0
      9  hand-off         the URL and the judge credential block

  THIS IS NOT A TRANSLITERATION OF THE BASH SCRIPT, and one difference is load-bearing.
  On this machine `bash` on PATH resolves to C:\WINDOWS\system32\bash.exe, which is WSL:

      PS> bash -c "uname -a; command -v aws || echo 'NO AWS IN THIS BASH'"
      Linux AetherX 6.6.87.2-microsoft-standard-WSL2 ...
      NO AWS IN THIS BASH

  WSL is a different machine with a different filesystem and no AWS CLI, so a naive
  `bash scripts/deploy/bootstrap_state.sh` from PowerShell fails in a way that reads like
  a credentials problem. Git Bash is what is wanted:

      PS> & "C:\Program Files\Git\bin\bash.exe" -c "uname -o; command -v aws"
      Msys
      /c/Program Files/Amazon/AWSCLIV2/aws

  Resolve-GitBash below searches for a Git Bash specifically, verifies it is not WSL, and
  refuses with that explanation rather than letting the confusion propagate.
  $env:MAINLINE_BASH overrides the search.

.PARAMETER Phase1
  Stop after stage 7 and create no Lambda at all: no function, no Function URL, no /v1/*
  behaviour. THE PHASE-1 CUT LINE from docs/leads/deploy-plan.md §4. It exists so the URL
  is never hostage to the backend, and it still produces a real HTTPS demo URL serving
  the console over the verified EvidenceBundle with a REPLAY badge.

.PARAMETER DryRun
  Run preflight, then check that every artefact the other workers owe exists. Writes
  nothing. EXITS NON-ZERO if anything is missing — this is the check, not a preview.

.PARAMETER PreflightOnly
  Stage 0 and stop.

.PARAMETER AnyAccount
  Proceed even when the caller is not account 022950218246.

.EXAMPLE
  pwsh -File scripts/deploy/deploy.ps1 -Phase1
.EXAMPLE
  pwsh -File scripts/deploy/deploy.ps1 -DryRun
.EXAMPLE
  pwsh -File scripts/deploy/deploy.ps1
#>

[CmdletBinding()]
param(
    [switch]$Phase1,
    [switch]$DryRun,
    [switch]$PreflightOnly,
    [switch]$AnyAccount,
    [switch]$RecreateDb,
    [switch]$SkipDb,
    [switch]$SkipBuild,
    [switch]$Interactive,
    [ValidateSet('arm64', 'x86_64')]
    [string]$Arch = 'arm64',
    [string]$AwsProfile = $(if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { 'mainline-dev' }),
    [string]$Region = 'ap-southeast-1',
    [string]$StateBucket = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ── Where everything is ───────────────────────────────────────────────────────────────
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root        = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$TfDir       = Join-Path $Root 'infra\envs\demo'
$ConsoleDir  = Join-Path $Root 'verticals\mainline\apps\console'
$DistBundle  = Join-Path $Root 'dist\demo-bundle'

$ExpectedAccount = '022950218246'
$DsnParam        = '/mainline/demo/cockroach_dsn'
$NamePrefix      = 'mainline-demo'

$script:StageN = 0

# ── Output ────────────────────────────────────────────────────────────────────────────
function Write-Stage { param([int]$N, [string]$Name)
    $script:StageN = $N
    Write-Host ''
    Write-Host ("== stage {0} - {1}" -f $N, $Name) -ForegroundColor Cyan
}
function Write-Info { param([string]$M) Write-Host "   $M" }
function Write-Ok   { param([string]$M) Write-Host "   [ok] $M" -ForegroundColor Green }
function Write-Skip { param([string]$M) Write-Host "   [skipped] $M" -ForegroundColor DarkGray }

function Stop-Deploy {
    param([string]$Message, [int]$Code = 1)
    Write-Host ''
    Write-Host ("deploy: stage {0} FAILED" -f $script:StageN) -ForegroundColor Red
    foreach ($line in ($Message -split "`n")) { Write-Host "   $line" -ForegroundColor Red }
    Write-Host ''
    exit $Code
}

# Native commands do not throw on a non-zero exit; $ErrorActionPreference does nothing
# for them. Every external call in this script goes through here so that "fail loudly,
# never continue past a broken stage" is a property of the script rather than of my
# remembering to check $LASTEXITCODE nineteen times.
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$Exe,
        [string[]]$Arguments = @(),
        [string]$OnFail = '',
        [switch]$Capture,
        [switch]$AllowFail
    )
    if ($Capture) {
        $out = & $Exe @Arguments 2>&1
    } else {
        & $Exe @Arguments
        $out = $null
    }
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFail) {
        $detail = if ($Capture -and $out) { "`n" + (($out | Out-String).Trim()) } else { '' }
        Stop-Deploy ("{0} exited {1}.`n{2}{3}" -f (Split-Path -Leaf $Exe), $code, $OnFail, $detail)
    }
    $script:LastNativeExit = $code
    if ($Capture) { return (($out | Out-String).Trim()) }
}

# ── Git Bash, specifically, and never WSL ─────────────────────────────────────────────
function Resolve-GitBash {
    $candidates = @()
    if ($env:MAINLINE_BASH) { $candidates += $env:MAINLINE_BASH }
    $candidates += @(
        'C:\Program Files\Git\bin\bash.exe',
        'C:\Program Files (x86)\Git\bin\bash.exe',
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe",
        'C:\Program Files\Git\usr\bin\bash.exe'
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            # Prove it is not WSL before trusting it. `uname -o` says Msys for Git Bash
            # and GNU/Linux for WSL, and only the first one can see the Windows AWS CLI.
            $kind = & $c -c 'uname -o' 2>$null
            if ($LASTEXITCODE -eq 0 -and $kind -match 'Msys') { return $c }
        }
    }
    return $null
}

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 0 — PREFLIGHT
# ══════════════════════════════════════════════════════════════════════════════════════
$phaseLabel = if ($Phase1) { '1 (replay, no API)' } else { '2 (live API)' }
Write-Host ("MAINLINE demo deploy   phase={0}  region={1}  profile={2}" -f $phaseLabel, $Region, $AwsProfile) -ForegroundColor White
if ($DryRun) { Write-Host 'DRY RUN - nothing will be created, changed or uploaded.' -ForegroundColor DarkGray }

Write-Stage 0 'preflight'

$env:AWS_PROFILE        = $AwsProfile
$env:AWS_REGION         = $Region
$env:AWS_DEFAULT_REGION = $Region

function Get-Tool {
    param([string]$Name, [string]$Hint)
    $c = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $c) { Stop-Deploy "'$Name' is not on PATH. $Hint" 3 }
    return $c.Source
}
$AwsExe  = Get-Tool 'aws'       'Install the AWS CLI v2.'
$TfExe   = Get-Tool 'terraform' 'Install Terraform >= 1.10 - this stack needs use_lockfile for native S3 locking.'
$CurlExe = Get-Tool 'curl.exe'  'curl.exe ships with Windows 10+ at C:\Windows\System32\curl.exe.'

$TfVersion = (& $TfExe version -json | ConvertFrom-Json).terraform_version
Write-Info ("terraform      {0}" -f $TfVersion)
$tfParts = $TfVersion.Split('.')
if ([int]$tfParts[0] -lt 1 -or ([int]$tfParts[0] -eq 1 -and [int]$tfParts[1] -lt 10)) {
    Stop-Deploy ("Terraform $TfVersion is older than 1.10, which is where use_lockfile (native S3 state`n" +
                 "locking) was added. infra/envs/demo/backend.tf depends on it and there is`n" +
                 "deliberately no DynamoDB table to fall back to.") 3
}

# The interpreter. `uv` is not installed on this machine, so every `just` recipe that
# shells out to `uv run` is dead here; the venv interpreter is named explicitly.
$Py = $null
foreach ($cand in @((Join-Path $Root '.venv\Scripts\python.exe'), (Join-Path $Root '.venv\bin\python.exe'))) {
    if (Test-Path $cand) { $Py = $cand; break }
}
if (-not $Py) {
    Stop-Deploy ("no interpreter at .venv\Scripts\python.exe.`n" +
                 "Create the virtualenv first: python -m venv .venv") 3
}
Write-Info ("python         {0}  ({1})" -f (& $Py --version), $Py)

$NodeExe = Get-Tool 'node' 'Install Node 20+.'
Write-Info ("node           {0}" -f (& $NodeExe --version))
$PnpmCmd = Get-Command 'pnpm' -ErrorAction SilentlyContinue
if ($PnpmCmd) {
    Write-Info ("pnpm           {0}" -f (& pnpm --version))
} elseif (-not $SkipBuild) {
    Stop-Deploy ("pnpm is not on PATH and stage 5 builds the console with it.`n" +
                 "Install pnpm, or pass -SkipBuild and put a built console in $ConsoleDir\dist.") 3
}

$GitBash = Resolve-GitBash
if ($GitBash) {
    Write-Info ("git bash       {0}" -f $GitBash)
} else {
    Stop-Deploy ("no Git Bash found, and stage 1 runs scripts/deploy/bootstrap_state.sh.`n" +
                 "`n" +
                 "NOTE: 'bash' on this machine's PATH is C:\WINDOWS\system32\bash.exe, which is`n" +
                 "WSL - a different filesystem with no AWS CLI - so it is deliberately NOT used.`n" +
                 "Install Git for Windows, or set `$env:MAINLINE_BASH to a Git Bash bash.exe.") 3
}

# AWS identity. This refusal is what protects the four unrelated live projects in this
# account from a deploy pointed at the wrong credentials.
$Account = Invoke-Native $AwsExe @('--profile', $AwsProfile, '--region', $Region, '--output', 'text',
    '--no-cli-pager', 'sts', 'get-caller-identity', '--query', 'Account') -Capture `
    -OnFail "Run 'aws configure --profile $AwsProfile', or pass -AwsProfile <name>."
$Arn = Invoke-Native $AwsExe @('--profile', $AwsProfile, '--region', $Region, '--output', 'text',
    '--no-cli-pager', 'sts', 'get-caller-identity', '--query', 'Arn') -Capture -AllowFail
Write-Info ("aws account    {0}" -f $Account)
Write-Info ("aws identity   {0}" -f $Arn)
if ($Account -ne $ExpectedAccount -and -not $AnyAccount) {
    Stop-Deploy ("this is account $Account, not $ExpectedAccount.`n" +
                 "Everything this script creates carries the 'mainline-demo-' prefix, but a deploy`n" +
                 "into the wrong account still costs money and still has to be cleaned up by hand.`n" +
                 "Pass -AnyAccount if you really mean it.") 3
}

# The DSN. Read from the repo-root .env when not exported, exactly like every program in
# scripts/deploy/. Its VALUE is never printed - only its presence and its host.
if (-not $env:COCKROACH_DSN) {
    $envFile = Join-Path $Root '.env'
    if (Test-Path $envFile) {
        foreach ($line in (Get-Content $envFile)) {
            if ($line -match '^\s*COCKROACH_DSN\s*=\s*(.+)\s*$') {
                $env:COCKROACH_DSN = $Matches[1].Trim().Trim('"').Trim("'")
                break
            }
        }
    }
}
if (-not $env:COCKROACH_DSN) {
    if ($SkipDb) {
        Write-Skip 'COCKROACH_DSN unset, and -SkipDb was passed'
    } else {
        Stop-Deploy ("COCKROACH_DSN is not set and the repo-root .env does not define it.`n" +
                     "Stage 3 applies the migration chain and the demo seed against the Cloud cluster`n" +
                     "and cannot proceed without it. Set it, or pass -SkipDb.") 3
    }
} else {
    $dsnHost = '<unparsed>'
    try { $dsnHost = ([uri]$env:COCKROACH_DSN).Host } catch { }
    Write-Info ("cockroach dsn  set  (host {0})" -f $dsnHost)
}

# The application DSN for the Lambda. Phase 1 has no Lambda and does not need it.
if (-not $Phase1) {
    $apiDsnSource = ''
    if ($env:MAINLINE_API_DSN) {
        $apiDsnSource = 'MAINLINE_API_DSN'
    } elseif ($env:MAINLINE_API_PASSWORD -and $env:COCKROACH_DSN) {
        $apiDsnSource = 'derived from COCKROACH_DSN + MAINLINE_API_PASSWORD'
    } else {
        Stop-Deploy ("the Lambda's DSN is not available, so stage 2 has nothing to write to SSM.`n" +
                     "Mint the login's password once:`n" +
                     "    $Py scripts\deploy\cloud_roles.py --rotate`n" +
                     "then either export the whole DSN:`n" +
                     "    `$env:MAINLINE_API_DSN = 'postgresql://mainline_api:<pw>@<host>:26257/mainline_demo?sslmode=verify-full'`n" +
                     "or just the password, and this script will swap the userinfo into COCKROACH_DSN:`n" +
                     "    `$env:MAINLINE_API_PASSWORD = '<pw>'`n" +
                     "Or run with -Phase1, which needs neither.") 3
    }
    Write-Info ("api dsn        available ({0})" -f $apiDsnSource)
}

if (-not $StateBucket) {
    $StateBucket = if ($env:MAINLINE_STATE_BUCKET) { $env:MAINLINE_STATE_BUCKET } else { "$NamePrefix-tfstate-$Account" }
}
Write-Info ("state bucket   {0}" -f $StateBucket)
Write-Info ("dsn parameter  {0}  (name only; the value is never in Terraform)" -f $DsnParam)

$LambdaZip = if ($env:MAINLINE_LAMBDA_ZIP) { $env:MAINLINE_LAMBDA_ZIP } else { Join-Path $Root "out\lambda\mainline-demo-api-$Arch.zip" }
if (-not $Phase1) { Write-Info ("lambda zip     {0}  (arch {1})" -f $LambdaZip, $Arch) }

Write-Ok 'preflight passed'
if ($PreflightOnly) { Write-Host "`n-PreflightOnly: stopping here."; exit 0 }

# ── Prerequisites owed by other workers ───────────────────────────────────────────────
$BuildLambda   = Join-Path $ScriptDir 'build_lambda.ps1'
$CaptureBundle = Join-Path $ScriptDir 'capture_demo_bundle.py'
$Acceptance    = Join-Path $ScriptDir 'demo_acceptance.py'

if ($DryRun) {
    Write-Stage 0 'dry run - prerequisites'
    $missing = 0
    function Test-Artifact { param([string]$Path, [string]$Who, [string]$What)
        if (Test-Path $Path) { Write-Ok ("{0}: {1}" -f $What, $Path); return $true }
        Write-Host ("   [MISSING] {0}: {1}" -f $What, $Path) -ForegroundColor Red
        Write-Host ("      produced by: {0}" -f $Who) -ForegroundColor Red
        return $false
    }
    if (-not (Test-Artifact (Join-Path $TfDir 'main.tf')                     'this worker'              'terraform root'))    { $missing++ }
    if (-not (Test-Artifact (Join-Path $Root 'infra\modules\demo-site')      'w5-tf-site'               'site module'))       { $missing++ }
    if (-not (Test-Artifact (Join-Path $ScriptDir 'cloud_chain.py')          'w2-cloud-database'        'migration applier')) { $missing++ }
    if (-not (Test-Artifact (Join-Path $ScriptDir 'seed_demo.py')            'w2-cloud-database'        'demo seed'))         { $missing++ }
    if (-not (Test-Artifact $CaptureBundle                                   'w9-evidence-bundle'       'bundle capture'))    { $missing++ }
    if (-not (Test-Artifact (Join-Path $ConsoleDir 'package.json')           'w8-console-composition'   'console'))           { $missing++ }
    if (-not $Phase1) {
        if (-not (Test-Artifact (Join-Path $Root 'infra\modules\demo-api')   'w6-tf-api'                'api module'))        { $missing++ }
        if (-not (Test-Artifact $BuildLambda                                 'w6-tf-api'                'lambda build'))      { $missing++ }
        if (-not (Test-Artifact $Acceptance                                  'w10-judge-and-acceptance' 'acceptance prover')) { $missing++ }
    }
    Write-Host ''
    if ($missing -gt 0) {
        Stop-Deploy ("$missing prerequisite(s) missing, listed above. A dry run that found a hole exits`n" +
                     "non-zero on purpose: this is the check, not a preview.") 1
    }
    Write-Ok 'every prerequisite is present - a real run would proceed'
    exit 0
}

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 1 — STATE BACKEND
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 1 'state backend'
# The .sh is the single implementation of the bucket's safety rules. Duplicating them in
# PowerShell would give this project two places where "refuse a bucket outside the
# mainline-demo- prefix" is written, which is one more than it can afford.
$bootstrapPosix = (& $GitBash -c "cygpath -u '$(Join-Path $ScriptDir 'bootstrap_state.sh')'").Trim()
Invoke-Native $GitBash @($bootstrapPosix, '--bucket', $StateBucket, '--region', $Region, '--profile', $AwsProfile) `
    -OnFail 'bootstrap_state.sh refused or failed; its message above says which.'
Write-Ok "s3://$StateBucket ready (versioned, private, encrypted, tagged, native locking)"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 2 — THE SECRET, INTO SSM, NEVER INTO TERRAFORM
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 2 'secret'
if ($Phase1) {
    Write-Skip 'phase 1 has no Lambda, so nothing reads the DSN'
} else {
    # The payload is built by Python into a temp file and passed with --cli-input-json,
    # so the DSN never appears in an argument vector, in Get-Process output, in
    # PSReadLine history, or in a transcript. The finally block removes it on every path.
    $ssmJson = Join-Path ([System.IO.Path]::GetTempPath()) ("mainline-ssm-{0}.json" -f ([guid]::NewGuid().ToString('N')))
    $builder = Join-Path ([System.IO.Path]::GetTempPath()) ("mainline-ssm-{0}.py" -f ([guid]::NewGuid().ToString('N')))
    try {
        $pySrc = @'
import json, os, sys, urllib.parse

out = sys.argv[1]
dsn = os.environ.get("MAINLINE_API_DSN", "").strip()
if not dsn:
    base = os.environ.get("COCKROACH_DSN", "").strip()
    pw = os.environ.get("MAINLINE_API_PASSWORD", "").strip()
    if not (base and pw):
        sys.exit("neither MAINLINE_API_DSN nor (COCKROACH_DSN + MAINLINE_API_PASSWORD)")
    u = urllib.parse.urlsplit(base)
    host = u.hostname or ""
    port = f":{u.port}" if u.port else ""
    userinfo = "mainline_api:" + urllib.parse.quote(pw, safe="")
    # The database is forced to mainline_demo: the admin DSN usually points at defaultdb,
    # and a Lambda connected to the wrong database fails in a way that reads like a
    # privilege error. The query string is kept verbatim because a Cloud Basic DSN's
    # sslmode and options are load-bearing.
    dsn = urllib.parse.urlunsplit((u.scheme, userinfo + "@" + host + port, "/mainline_demo", u.query, ""))
if "mainline_api" not in dsn:
    sys.exit("refusing: the DSN does not name the mainline_api login. The Lambda must not "
             "connect as an admin - see docs/deploy/cloud-database.md section 3.")
with open(out, "w", encoding="utf-8") as fh:
    json.dump({
        "Name": os.environ["DSN_PARAM"],
        "Type": "SecureString",
        "Overwrite": True,
        "Tier": "Standard",
        "Description": "CockroachDB Cloud DSN for the mainline_demo Lambda. Written by scripts/deploy/deploy.ps1, never by Terraform.",
        "Value": dsn,
    }, fh)
'@
        Set-Content -Path $builder -Value $pySrc -Encoding UTF8
        $env:DSN_PARAM = $DsnParam
        Invoke-Native $Py @($builder, $ssmJson) -Capture -OnFail 'could not build the SSM payload.'

        $version = Invoke-Native $AwsExe @('--profile', $AwsProfile, '--region', $Region, '--output', 'text',
            '--no-cli-pager', 'ssm', 'put-parameter', '--cli-input-json', "file://$ssmJson", '--query', 'Version') -Capture `
            -OnFail "The IAM identity needs ssm:PutParameter and kms:Encrypt on alias/aws/ssm."
        Write-Ok "$DsnParam written as SecureString, version $version"
    }
    finally {
        foreach ($f in @($ssmJson, $builder)) { if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue } }
    }

    # Tagged separately: put-parameter with Overwrite=true rejects Tags outright.
    Invoke-Native $AwsExe @('--profile', $AwsProfile, '--region', $Region, '--no-cli-pager',
        'ssm', 'add-tags-to-resource', '--resource-type', 'Parameter', '--resource-id', $DsnParam,
        '--tags', 'Key=project,Value=mainline', 'Key=managed_by,Value=deploy.ps1') -Capture -AllowFail | Out-Null

    # Read the metadata back WITHOUT --with-decryption. This proves the write landed and
    # cannot print the value even by accident.
    $type = Invoke-Native $AwsExe @('--profile', $AwsProfile, '--region', $Region, '--output', 'text',
        '--no-cli-pager', 'ssm', 'get-parameter', '--name', $DsnParam, '--query', 'Parameter.Type') -Capture
    if ($type -ne 'SecureString') { Stop-Deploy "the parameter came back as type '$type', not SecureString." }
    Write-Ok 'read back: type=SecureString (value not requested, and never will be by this script)'
}

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 3 — THE DATABASE
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 3 'database'
if ($SkipDb) {
    Write-Skip '-SkipDb'
} else {
    $chainArgs = @((Join-Path $ScriptDir 'cloud_chain.py'))
    if ($RecreateDb) { $chainArgs += '--recreate' }
    & $Py @chainArgs
    $chainRc = $LASTEXITCODE
    switch ($chainRc) {
        0 { Write-Ok 'migration chain applied or already correct' }
        3 { Stop-Deploy ("cloud_chain.py refused: the migration tree or the live schema has drifted from`n" +
                         "the fingerprint recorded in trappoint.deploy_chain, and it will not replay`n" +
                         "forward-only migrations over a live database. Re-run with -RecreateDb to rebuild`n" +
                         "mainline_demo from empty. Nothing was changed.") }
        default { Stop-Deploy "cloud_chain.py exited $chainRc. Its output above names the file and SQLSTATE." }
    }
    Invoke-Native $Py @((Join-Path $ScriptDir 'seed_demo.py')) `
        -OnFail ("The demo world is what the console and the EvidenceBundle both read; a deploy on top`n" +
                 "of an unseeded database would serve an empty screen.")
    Write-Ok 'demo world seeded and the seeded permit verified refusable'
}

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 4 — THE LAMBDA PACKAGE
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 4 'lambda package'
if ($Phase1) {
    Write-Skip '-Phase1 creates no Lambda'
} elseif ($SkipBuild) {
    if (-not (Test-Path $LambdaZip)) { Stop-Deploy "-SkipBuild was passed but $LambdaZip does not exist." }
    Write-Skip "-SkipBuild, reusing $LambdaZip"
} else {
    if (-not (Test-Path $BuildLambda)) {
        Stop-Deploy ("scripts\deploy\build_lambda.ps1 does not exist. It is produced by worker w6-tf-api`n" +
                     "and builds the psycopg-bearing deployment zip. Until it lands, run with -Phase1,`n" +
                     "which needs no Lambda at all and still produces a working demo URL.")
    }
    Invoke-Native 'pwsh' @('-NoProfile', '-File', $BuildLambda, '-Arch', $Arch, '-Out', $LambdaZip) `
        -OnFail 'build_lambda.ps1 failed.'
    if (-not (Test-Path $LambdaZip)) {
        Stop-Deploy "build_lambda finished but $LambdaZip is not there. Set `$env:MAINLINE_LAMBDA_ZIP if it writes elsewhere."
    }
    Write-Ok ("{0} ({1:N0} bytes, {2})" -f $LambdaZip, (Get-Item $LambdaZip).Length, $Arch)
}

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 5 — THE SITE PAYLOAD
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 5 'site payload'
if ($SkipBuild) {
    if (-not (Test-Path (Join-Path $ConsoleDir 'dist'))) { Stop-Deploy "-SkipBuild was passed but $ConsoleDir\dist does not exist." }
    Write-Skip "-SkipBuild, reusing $ConsoleDir\dist"
} else {
    Push-Location $ConsoleDir
    try {
        if ($env:MAINLINE_CONSOLE_BUILD_CMD) {
            Write-Info 'console build: $env:MAINLINE_CONSOLE_BUILD_CMD'
            Invoke-Expression $env:MAINLINE_CONSOLE_BUILD_CMD
            if ($LASTEXITCODE -ne 0) { Stop-Deploy 'the console build command failed.' }
        } else {
            Invoke-Native 'pnpm' @('install', '--frozen-lockfile') -OnFail 'pnpm install failed.'
            Invoke-Native 'pnpm' @('run', 'build') -OnFail (
                "If w8-console-composition documents a different command, set`n" +
                "`$env:MAINLINE_CONSOLE_BUILD_CMD and re-run.")
        }
    } finally { Pop-Location }
    if (-not (Test-Path (Join-Path $ConsoleDir 'dist\index.html'))) { Stop-Deploy 'the build produced no dist/index.html.' }
    Write-Ok ("console built: {0} files" -f (Get-ChildItem (Join-Path $ConsoleDir 'dist') -Recurse -File).Count)
}

if (Test-Path $CaptureBundle) {
    Invoke-Native $Py @($CaptureBundle, '--out', $DistBundle) `
        -OnFail ("The bundle is the Phase-1 demo and the console's REPLAY source; publishing without`n" +
                 "it would serve a console with nothing to show.")
    Write-Ok "EvidenceBundle captured into $DistBundle"
} else {
    Stop-Deploy ("scripts\deploy\capture_demo_bundle.py does not exist. It is produced by worker`n" +
                 "w9-evidence-bundle and captures the cryptographically verified bundle from the Cloud`n" +
                 "cluster. Without it the console has no REPLAY source. There is no way to fake this`n" +
                 "file and none is attempted.")
}

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 6 — INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 6 'infrastructure'
Push-Location $TfDir
try {
    Invoke-Native $TfExe @('init', '-input=false', '-reconfigure',
        "-backend-config=bucket=$StateBucket", "-backend-config=region=$Region") `
        -OnFail "If it complains about a state lock, see docs/deploy/RUNBOOK.md."

    $tfVars = @("-var", "aws_region=$Region", "-var", "dsn_parameter_name=$DsnParam", "-var", "name_prefix=$NamePrefix")
    if ($Phase1) {
        $tfVars += @("-var", "enable_api=false")
    } else {
        $tfVars += @("-var", "enable_api=true", "-var", "lambda_package_path=$LambdaZip", "-var", "lambda_architecture=$Arch")
    }
    $applyArgs = @('apply', '-input=false')
    if (-not $Interactive) { $applyArgs += '-auto-approve' }
    Invoke-Native $TfExe ($applyArgs + $tfVars) -OnFail (
        "Nothing else in this script has run; the state file records exactly what did get`n" +
        "created, and teardown.sh --yes removes it.`n" +
        "`n" +
        "IF THE ERROR MENTIONS CloudFront AND 'Your account must be verified':`n" +
        "  that is an AWS account-level hold on creating CloudFront distributions, not a bug`n" +
        "  in this repository. It was reproduced on 2026-08-10 with a bare`n" +
        "  'aws cloudfront create-distribution' and no Terraform involved, from an identity`n" +
        "  holding AdministratorAccess. Only AWS Support can lift it - open a case under`n" +
        "  Service: CloudFront, Category: account verification, and paste the RequestID.`n" +
        "  docs\deploy\RUNBOOK.md carries the transcript and the fallback options.")

    $summaryJson = Invoke-Native $TfExe @('output', '-json', 'deploy_summary') -Capture
    $summary = $summaryJson | ConvertFrom-Json
} finally { Pop-Location }

$DemoUrl    = $summary.demo_url
$DistId     = $summary.distribution_id
$SiteBucket = $summary.site_bucket
$FnName     = $summary.api_function_name
if (-not $DemoUrl) { Stop-Deploy 'terraform applied but produced no demo_url output.' }
Write-Ok "distribution $DistId -> $DemoUrl"
Write-Ok "site bucket  $SiteBucket"
if ($FnName) { Write-Ok "lambda       $FnName" }

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 7 — PUBLISH
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Content types are set EXPLICITLY and not left to `aws s3 sync`'s guess, because that
# guess comes from Python's `mimetypes`, which on Windows reads the registry. Measured on
# this machine with the repository interpreter:
#
#     .js    -> application/javascript      (fine)
#     .mjs   -> text/plain                  <- a module served as text/plain does not load
#     .map   -> text/plain                  (harmless)
#     .woff2 -> None                        <- falls back to binary/octet-stream
#
# One wrong Content-Type on the entry chunk is a blank page with a console error, on the
# one URL the whole submission depends on.
Write-Stage 7 'publish'
$distDir = Join-Path $ConsoleDir 'dist'
$s3Base  = @('--profile', $AwsProfile, '--region', $Region, '--no-cli-pager')

Invoke-Native $AwsExe ($s3Base + @('s3', 'sync', "$distDir\", "s3://$SiteBucket/", '--delete',
    '--exclude', 'index.html', '--exclude', '*.js', '--exclude', '*.mjs', '--exclude', '*.css',
    '--exclude', '*.woff2', '--exclude', '*.map',
    '--cache-control', 'public, max-age=31536000, immutable')) -OnFail 's3 sync of the static assets failed.'

function Publish-Typed {
    param([string]$Glob, [string]$ContentType)
    Invoke-Native $AwsExe ($s3Base + @('s3', 'cp', "$distDir\", "s3://$SiteBucket/", '--recursive',
        '--exclude', '*', '--include', $Glob,
        '--content-type', $ContentType,
        '--cache-control', 'public, max-age=31536000, immutable')) -Capture -OnFail "s3 cp of $Glob failed." | Out-Null
}
Publish-Typed '*.js'    'text/javascript; charset=utf-8'
Publish-Typed '*.mjs'   'text/javascript; charset=utf-8'
Publish-Typed '*.css'   'text/css; charset=utf-8'
Publish-Typed '*.map'   'application/json; charset=utf-8'
Publish-Typed '*.woff2' 'font/woff2'
Write-Ok 'assets uploaded with explicit content types, immutable for a year'

# The entry document: never cached, because it is the only file whose name does not
# change when its contents do.
Invoke-Native $AwsExe ($s3Base + @('s3', 'cp', (Join-Path $distDir 'index.html'), "s3://$SiteBucket/index.html",
    '--content-type', 'text/html; charset=utf-8',
    '--cache-control', 'no-cache, no-store, must-revalidate')) -Capture -OnFail 's3 cp of index.html failed.' | Out-Null
Write-Ok 'index.html uploaded, no-cache'

if (Test-Path $DistBundle) {
    Invoke-Native $AwsExe ($s3Base + @('s3', 'sync', "$DistBundle\", "s3://$SiteBucket/evidence/", '--delete',
        '--content-type', 'application/json; charset=utf-8',
        '--cache-control', 'no-cache, must-revalidate')) -Capture -OnFail 's3 sync of the EvidenceBundle failed.' | Out-Null
    Write-Ok 'EvidenceBundle published under /evidence/'
}

Invoke-Native $AwsExe ($s3Base + @('cloudfront', 'create-invalidation', '--distribution-id', $DistId,
    '--paths', '/index.html', '/', '--output', 'text')) -Capture `
    -OnFail ("The objects are uploaded; judges would see the previous index.html until the cache`n" +
             "expires. Re-run: aws cloudfront create-invalidation --distribution-id $DistId --paths '/index.html' '/'") | Out-Null
Write-Ok 'invalidated /index.html and /'

# A live HTTPS check of our own, in BOTH phases, before anything is printed. A new
# distribution can take a few minutes to propagate; 20 attempts at 15 s is five minutes.
Write-Info 'waiting for the distribution to answer over HTTPS...'
$code = '000'
for ($i = 0; $i -lt 20; $i++) {
    $code = (& $CurlExe -s -o NUL -w '%{http_code}' --max-time 20 "$DemoUrl/") 2>$null
    if ($code -eq '200') { break }
    Start-Sleep -Seconds 15
}
if ($code -ne '200') {
    Stop-Deploy ("$DemoUrl/ answered HTTP $code after five minutes of trying.`n" +
                 "The objects are uploaded and the distribution exists - check the OAC and the bucket`n" +
                 "policy in infra/modules/demo-site. Nothing is printed as a working URL until it is.")
}
Write-Ok "GET $DemoUrl/ -> 200"

if ($Phase1) {
    Write-Host ''
    Write-Host '-Phase1: stopping after stage 7, as designed.' -ForegroundColor DarkGray
    Write-Host '   No Lambda exists, so there is no live gate to prove and stage 8 is not run.'
    Write-Host '   The console serves the verified EvidenceBundle with a REPLAY badge.'
}

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 8 — PROOF
# ══════════════════════════════════════════════════════════════════════════════════════
if (-not $Phase1) {
    Write-Stage 8 'proof'
    if (-not (Test-Path $Acceptance)) {
        Stop-Deploy ("scripts\deploy\demo_acceptance.py does not exist. It is produced by worker`n" +
                     "w10-judge-and-acceptance and is the only thing that proves the live gate refuses`n" +
                     "and then admits over HTTPS. A phase-2 deploy that cannot prove itself is a failed`n" +
                     "deploy, so this is fatal rather than a warning. Use -Phase1 to ship the URL`n" +
                     "without the live path.")
    }
    Invoke-Native $Py @($Acceptance, '--url', $DemoUrl) -OnFail (
        "THE DEPLOY IS FAILED. The live gate did not refuse and then admit over HTTPS, which is`n" +
        "the product's entire claim. Do not submit this URL. Read the prover's output above,`n" +
        "then: aws logs tail /aws/lambda/$FnName --since 10m")
    Write-Ok 'the live gate refused, refused under attack, and then admitted - over HTTPS'
}

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 9 — HAND-OFF
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 9 'hand-off'
$phaseText = if ($Phase1) { '1 - REPLAY, verified EvidenceBundle, no backend' } else { '2 - LIVE, CockroachDB Cloud Basic in Singapore' }
Write-Host ''
Write-Host "  DEMO URL   $DemoUrl" -ForegroundColor Green
Write-Host "  phase      $phaseText"
Write-Host "  region     $Region (AWS)   ·   aws-ap-southeast-1 (CockroachDB Cloud)"
Write-Host "  account    $Account"
Write-Host "  bucket     s3://$SiteBucket"
Write-Host "  cloudfront $DistId"
if ($FnName) { Write-Host "  lambda     $FnName" }
Write-Host ''
Write-Host '  JUDGE ACCESS - free and unrestricted, no sign-up, no key' -ForegroundColor White
Write-Host '  * The URL above needs no credential. Open it.'
Write-Host '  * Read-only SQL, if a judge wants to check the database themselves:'
Write-Host '      user      mainline_judge'
Write-Host '      database  mainline_demo   on cluster mainline-dev (aws-ap-southeast-1)'
Write-Host '      scope     SELECT on the fourteen mainline_audit views, and nothing else'
Write-Host '      password  minted by scripts\deploy\cloud_roles.py --rotate, printed once, and'
Write-Host '                deliberately not stored by this script or anywhere in the repository.'
Write-Host '                Paste it into the submission form''s private notes field.'
Write-Host '  * The judge pack:  verticals\mainline\demo\judge\PACK.md'
Write-Host '  * What is broken, published on the same site as the claims:  docs\HONESTY.md'
Write-Host ''
Write-Host '  Teardown, when judging is over:'
Write-Host '      & "C:\Program Files\Git\bin\bash.exe" scripts/deploy/teardown.sh --yes'
Write-Host ''
Write-Ok 'done'
exit 0
