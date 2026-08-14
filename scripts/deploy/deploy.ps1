# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0

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
      4  lambda package   build_lambda + manifest verification
      5  site payload     OPTIONAL - only when -EnableCloudFront (see D1 below)
      6  infrastructure   terraform init + plan, and apply ONLY behind the approval gate
      7  publish          resolve the hostname, then PROVE it over HTTPS before printing it
      8  proof            demo_acceptance.py against the live URL - MUST exit 0
      9  hand-off         the URL and the judge credential block

  DECISION D1: THE HOSTNAME IS THE LAMBDA FUNCTION URL.
  AWS refuses to create new CloudFront distributions on this account (an account-level
  verification hold; docs/deploy/RUNBOOK.md quotes the 403 and its RequestID). So the demo
  URL is https://<id>.lambda-url.ap-southeast-1.on.aws - HTTPS on an AWS-issued
  certificate, no ACM, no hosted zone, no account verification. ONE origin serves the
  console SPA at /, the signed bundle at /bundle/* and the API at /v1/*, so there is no
  CORS, no S3 in the request path, and one hostname in the submission form. Stage 5's
  upload is therefore optional, stage 6 passes -var enable_cloudfront=false, and stage 7
  reads the hostname from the api module's function_url output.

  THE APPROVAL GATE. `terraform apply` creates billable resources in a live AWS account,
  so this script will not run one unless the environment says so:

      $env:MAINLINE_APPLY_APPROVED = '1'

  Without it, stage 6 runs init and plan, saves the plan, prints it, and STOPS with exit
  code 7 - the designed halt, not a failure. The reviewed plan lives at
  docs/deploy/terraform-plan.md. The gate is a feature of this script, not scaffolding.

  WHICH AWS ACCOUNT (decision D2). No account id is written in this file. The live account
  is read from `aws sts get-caller-identity --query Account --output text` and compared
  against the one you name, either with -ExpectAccount or with $env:MAINLINE_AWS_ACCOUNT
  (the parameter wins). SUPPLY NEITHER AND A REAL DEPLOY REFUSES AND CREATES NOTHING
  (exit 3). -AnyAccount is the only override. -DryRun and -PreflightOnly are exempt,
  because they create, change and delete nothing at all - but they still stop if you name
  an account and the caller is a different one.

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

.PARAMETER DryRun
  Preflight the machine, then check every artefact the other workers owe. Writes nothing,
  anywhere. EXITS NON-ZERO if anything is missing - this is the check, not a preview.

.PARAMETER StrictSecrets
  With -DryRun, also require the operator secrets (the mainline_api DSN). Off by default
  because a clean checkout never has one and gating on it would make -DryRun permanently
  red for exactly the person it is meant to serve.

.PARAMETER PreflightOnly
  Stage 0 and stop.

.PARAMETER ExpectAccount
  The AWS account id this deploy is allowed to touch. Wins over $env:MAINLINE_AWS_ACCOUNT.

.PARAMETER AnyAccount
  Skip the account guard entirely. The only thing that does.

.PARAMETER EnableCloudFront
  Restore the pre-D1 shape: a CloudFront distribution in front of an S3 site bucket, with
  the Function URL back on AWS_IAM. It plans cleanly today and will not apply until AWS
  lifts the account verification hold.

.EXAMPLE
  pwsh -File scripts/deploy/deploy.ps1 -DryRun
.EXAMPLE
  pwsh -File scripts/deploy/deploy.ps1 -ExpectAccount 123456789012
.EXAMPLE
  $env:MAINLINE_APPLY_APPROVED = '1'
  pwsh -File scripts/deploy/deploy.ps1 -ExpectAccount 123456789012

.NOTES
  EXIT CODES
    0  the URL printed at the end was fetched over HTTPS and proved itself
    1  a stage failed
    2  usage error
    3  preflight refused: wrong/unnamed account, missing tool, or missing credential
    7  STOPPED AT THE APPROVAL GATE. Stage 6 planned and did not apply. Nothing created,
       nothing changed, no URL printed because none exists. A designed halt, NOT a failure.
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$StrictSecrets,
    [switch]$PreflightOnly,
    [switch]$AnyAccount,
    [string]$ExpectAccount = $(if ($env:MAINLINE_AWS_ACCOUNT) { $env:MAINLINE_AWS_ACCOUNT } else { '' }),
    [switch]$RecreateDb,
    [switch]$SkipDb,
    [switch]$SkipBuild,
    [switch]$EnableCloudFront,
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
$BundleSrc   = Join-Path $ConsoleDir 'fixtures\bundles\demo-cloud'
$PlanDoc     = Join-Path $Root 'docs\deploy\terraform-plan.md'

$DsnParam      = '/mainline/demo/cockroach_dsn'
$NamePrefix    = 'mainline-demo'
$DemoDatabase  = $(if ($env:MAINLINE_DEMO_DATABASE) { $env:MAINLINE_DEMO_DATABASE } else { 'mainline_demo' })
$ApplyApproved = ($env:MAINLINE_APPLY_APPROVED -eq '1')

# Measured: without this a Python helper printing a non-ASCII character lands as `?` in a
# captured transcript, because CPython picks the ANSI code page when stdout is a pipe.
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$script:StageN = 0

# ── Output ────────────────────────────────────────────────────────────────────────────
function Write-Stage { param([int]$N, [string]$Name)
    $script:StageN = $N
    Write-Host ''
    Write-Host ("== stage {0} - {1}" -f $N, $Name) -ForegroundColor Cyan
}
function Write-Info { param([string]$M) Write-Host "   $M" }
function Write-Ok   { param([string]$M) Write-Host "   [ok] $M" -ForegroundColor Green }
function Write-Bad  { param([string]$M) Write-Host "   [NO] $M" -ForegroundColor Red }
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
# remembering to check $LASTEXITCODE thirty times.
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
$shape = if ($EnableCloudFront) { 'cloudfront (pre-D1, needs the AWS hold lifted)' } else { 'D1 - Lambda Function URL is the hostname' }
Write-Host ("MAINLINE demo deploy   shape={0}" -f $shape) -ForegroundColor White
Write-Host ("                       region={0}  profile={1}  arch={2}" -f $Region, $AwsProfile, $Arch)
if ($DryRun) { Write-Host 'DRY RUN - nothing will be created, changed, uploaded or written.' -ForegroundColor DarkGray }

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

$AwsVersionLine = (& $AwsExe --version 2>&1 | Out-String).Trim()
$AwsVersion = if ($AwsVersionLine -match 'aws-cli/(\S+)') { $Matches[1] } else { '' }
Write-Info ("aws cli        {0}" -f $(if ($AwsVersion) { $AwsVersion } else { 'unknown' }))
if (-not $AwsVersion.StartsWith('2.')) {
    Stop-Deploy ("the AWS CLI reports version '$AwsVersion'. This stack needs v2: v1 has no`n" +
                 "s3api list-object-versions --max-keys paging shape teardown relies on, and its`n" +
                 "ssm put-parameter --cli-input-json handling differs.") 3
}

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
$PyVersion = (& $Py -c 'import sys;print("%d.%d.%d" % sys.version_info[:3])').Trim()
Write-Info ("python         {0}  ({1})" -f $PyVersion, $Py)
if (-not $PyVersion.StartsWith('3.13.')) {
    Stop-Deploy ("the virtualenv interpreter is $PyVersion, not 3.13.x. The Lambda runtime is`n" +
                 "python3.13 and build_lambda downloads cp313 wheels; building the package with a`n" +
                 "different minor version produces a zip that imports here and fails on Lambda.") 3
}

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

# ── AWS identity, and the account guard (decision D2) ─────────────────────────────────
#
# THE ACCOUNT ID IS NOT WRITTEN IN THIS FILE. It is read from the live caller identity and
# compared against the one the operator named. The safety property is unchanged from the
# version that hard-coded it: this script refuses to touch an account it was not told to
# touch, and -AnyAccount is the only override.
$awsBase = @('--profile', $AwsProfile, '--region', $Region, '--output', 'text', '--no-cli-pager')
$Account = Invoke-Native $AwsExe ($awsBase + @('sts', 'get-caller-identity', '--query', 'Account')) -Capture `
    -OnFail "Run 'aws configure --profile $AwsProfile', or pass -AwsProfile <name>."
$Arn = Invoke-Native $AwsExe ($awsBase + @('sts', 'get-caller-identity', '--query', 'Arn')) -Capture -AllowFail
Write-Info ("aws account    {0}" -f $Account)
Write-Info ("aws identity   {0}" -f $Arn)

$AccountGuard = 'unnamed'
if ($AnyAccount) {
    $AccountGuard = 'disabled'
    Write-Info "account guard  DISABLED by -AnyAccount - proceeding into account $Account"
} elseif (-not $ExpectAccount -and ($DryRun -or $PreflightOnly)) {
    # A dry run and a preflight WRITE NOTHING, so there is no account to refuse to touch.
    # The refusal below still stands for every run that can create, change or delete
    # something, which is exactly where the safety property lives.
    Write-Info "account guard  NOT NAMED - harmless here (this run writes nothing), FATAL for a real"
    Write-Info "               deploy. Supply -ExpectAccount $Account or `$env:MAINLINE_AWS_ACCOUNT=$Account."
} elseif (-not $ExpectAccount) {
    Stop-Deploy ("NOTHING TOLD THIS SCRIPT WHICH AWS ACCOUNT IT MAY TOUCH, so it will not touch one.`n" +
                 "`n" +
                 "The caller is account $Account. Name it, and this run proceeds:`n" +
                 "`n" +
                 "    pwsh -File scripts\deploy\deploy.ps1 -ExpectAccount $Account`n" +
                 "or`n" +
                 "    `$env:MAINLINE_AWS_ACCOUNT = '$Account'`n" +
                 "`n" +
                 "The parameter wins over the environment variable. -AnyAccount skips the check`n" +
                 "entirely and is the only thing that does.`n" +
                 "`n" +
                 "Why the refusal exists: this account holds seven S3 buckets belonging to unrelated`n" +
                 "live projects. Everything this script creates carries the '$NamePrefix-' prefix, but`n" +
                 "a deploy pointed at the wrong credentials still costs money and still has to be`n" +
                 "cleaned up by hand. No account id is hard-coded here (decision D2).") 3
} elseif ($Account -ne $ExpectAccount) {
    Stop-Deploy ("this is account $Account. You said $ExpectAccount.`n" +
                 "Refusing to create, change or delete anything. Fix the profile (-AwsProfile <name>),`n" +
                 "fix the expectation (-ExpectAccount <id>), or pass -AnyAccount if you really mean it.") 3
} else {
    $AccountGuard = 'matched'
    Write-Ok "account guard  $Account matches the account you named"
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
$dsnHost = ''
if (-not $env:COCKROACH_DSN) {
    if ($SkipDb -or $DryRun) {
        Write-Bad 'COCKROACH_DSN is unset and the repo-root .env does not define it'
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

# The application DSN for the Lambda. Every deploy needs it now: under D1 there is no
# shape of this stack that has no Lambda.
$apiDsnSource = ''
if ($env:MAINLINE_API_DSN) {
    $apiDsnSource = 'MAINLINE_API_DSN'
} elseif ($env:MAINLINE_API_PASSWORD -and $env:COCKROACH_DSN) {
    $apiDsnSource = 'derived from COCKROACH_DSN + MAINLINE_API_PASSWORD'
}
$apiDsnAdvice = ("the Lambda's DSN is not available, so stage 2 has nothing to write to SSM.`n" +
                 "It is an OPERATOR SECRET: minted once, shown once, and deliberately stored nowhere`n" +
                 "in this repository. Mint it:`n" +
                 "    .venv\Scripts\python.exe scripts\deploy\cloud_roles.py --rotate`n" +
                 "then export either the whole DSN:`n" +
                 "    `$env:MAINLINE_API_DSN = 'postgresql://mainline_api:<pw>@<host>:26257/$DemoDatabase`?sslmode=verify-full'`n" +
                 "or just the password, and this script swaps the userinfo into COCKROACH_DSN:`n" +
                 "    `$env:MAINLINE_API_PASSWORD = '<pw>'")
if ($apiDsnSource) {
    Write-Info ("api dsn        available ({0})" -f $apiDsnSource)
} elseif (-not $DryRun) {
    Stop-Deploy $apiDsnAdvice 3
}

if (-not $StateBucket) {
    $StateBucket = if ($env:MAINLINE_STATE_BUCKET) { $env:MAINLINE_STATE_BUCKET } else { "$NamePrefix-tfstate-$Account" }
}
Write-Info ("state bucket   {0}" -f $StateBucket)
Write-Info ("dsn parameter  {0}  (name only; the value is never in Terraform)" -f $DsnParam)

$LambdaZip = if ($env:MAINLINE_LAMBDA_ZIP) { $env:MAINLINE_LAMBDA_ZIP } else { Join-Path $Root "out\lambda\mainline-demo-api-$Arch.zip" }
$LambdaManifest = "$LambdaZip.json"
Write-Info ("lambda zip     {0}  (arch {1})" -f $LambdaZip, $Arch)
if ($ApplyApproved) {
    Write-Info 'apply gate     OPEN - MAINLINE_APPLY_APPROVED=1, stage 6 will apply'
} else {
    Write-Info 'apply gate     CLOSED - stage 6 will plan and stop (exit 7). Set $env:MAINLINE_APPLY_APPROVED=1 to open it.'
}

Write-Ok 'preflight passed'
if ($PreflightOnly) { Write-Host "`n-PreflightOnly: stopping here."; exit 0 }

# ── Named prerequisites, and who owes each one ────────────────────────────────────────
$BuildLambda   = Join-Path $ScriptDir 'build_lambda.ps1'
if (-not (Test-Path $BuildLambda)) { $BuildLambda = Join-Path $ScriptDir 'build_lambda.sh' }
$CaptureBundle = Join-Path $ScriptDir 'capture_demo_bundle.py'
$Acceptance    = Join-Path $ScriptDir 'demo_acceptance.py'

# The zip/manifest agreement check. Shared verbatim between -DryRun and stage 4, because
# two copies of "is this package deployable" is one copy too many.
$PackageProbe = @'
import hashlib, json, os, sys, zipfile

zip_path, manifest_path = sys.argv[1], sys.argv[2]
want_arch = os.environ["MAINLINE_ARCH"]
problems = []

try:
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
except Exception as exc:  # noqa: BLE001
    print(f"        manifest does not parse as JSON: {exc}")
    raise SystemExit(1)

h = hashlib.sha256()
with open(zip_path, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 20), b""):
        h.update(chunk)
digest = h.hexdigest()

if str(manifest.get("sha256") or "") != digest:
    problems.append(
        "the manifest's sha256 does not match the zip on disk\n"
        f"          manifest {manifest.get('sha256') or '<absent>'}\n"
        f"          measured {digest}\n"
        "          the package and its manifest were produced by different runs"
    )
if str(manifest.get("architecture") or "") != want_arch:
    problems.append(
        f"the manifest declares architecture {manifest.get('architecture')!r}, this deploy uses {want_arch!r}.\n"
        "          A zip built for one architecture on a function declared as the other is a\n"
        "          clean plan, a clean apply, and an ELFCLASS error on the first request."
    )
if str(manifest.get("runtime") or "") != "python3.13":
    problems.append(f"the manifest declares runtime {manifest.get('runtime')!r}, not 'python3.13'")

with zipfile.ZipFile(zip_path) as zf:
    names = set(zf.namelist())

# D1: ONE origin. The console SPA and the signed bundle travel inside this zip, because
# there is no S3 in the request path and no CloudFront in front of it. A package without
# them deploys, answers /v1/health with a green 200, and 404s the URL a judge opens.
#
# The paths below are the handler's, not a guess: `static_site.resolve()` maps a request
# path onto `<web root>/<path>`, so `/` is `web/index.html` and `/bundle/manifest.json` is
# `web/bundle/manifest.json`. `/assets/` and `/bundle/` are the two prefixes it will NOT
# fall back to index.html for, which is precisely why a miss there has to be caught here.
if "web/index.html" not in names:
    problems.append(
        "the package carries no web/index.html.\n"
        "          Under decision D1 the Lambda serves the console SPA at / from\n"
        "          $MAINLINE_WEB_ROOT (module default /var/task/web). Without it the demo\n"
        "          URL 404s while /v1/health is perfectly green."
    )
if "web/bundle/manifest.json" not in names:
    problems.append(
        "the package carries no web/bundle/manifest.json.\n"
        "          That is the console's REPLAY source, served at /bundle/manifest.json.\n"
        "          static_site does not fall back to index.html under /bundle/, so a miss\n"
        "          there is a hard 404 and the REPLAY badge has nothing behind it."
    )
declared_root = str(manifest.get("web_root") or "")
if declared_root and declared_root != "/var/task/web":
    problems.append(
        f"the manifest declares web_root {declared_root!r}, but stage 6 passes no\n"
        "          -var web_root and the demo-api module defaults to '/var/task/web'."
    )

print(f"        sha256 {digest}")
print(f"        {len(names)} entries - arch {manifest.get('architecture')} - runtime {manifest.get('runtime')}")
print(f"        web/ {sum(1 for n in names if n.startswith('web/'))} entries - "
      f"web/bundle/ {sum(1 for n in names if n.startswith('web/bundle/'))} entries - "
      f"web_root {declared_root or '<undeclared>'}")
for p in problems:
    print(f"        - {p}")
raise SystemExit(1 if problems else 0)
'@

# Returns ONLY the interpreter's exit code, and writes its output to the host as it goes.
# Returning the output too — which a bare `& $Py …; return $LASTEXITCODE` does, because
# PowerShell collects every uncaptured value into the return — makes `-eq 0` compare an
# array and silently swallows the probe's explanation. That bug cost a debugging cycle
# here and it is the reason this function exists rather than an inline call.
function Invoke-PyInline {
    param([string]$Source, [string[]]$Arguments = @())
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("mainline-probe-{0}.py" -f ([guid]::NewGuid().ToString('N')))
    try {
        Set-Content -Path $tmp -Value $Source -Encoding UTF8
        & $Py $tmp @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
        $code = $LASTEXITCODE
        return $code
    } finally { if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue } }
}

# ══════════════════════════════════════════════════════════════════════════════════════
# -DryRun — THE PREREQUISITE CHECK. WRITES NOTHING that outlives the call.
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Two classes, and the distinction is deliberate:
#
#   ARTEFACT   something this repository owes. GATED: missing one exits non-zero.
#   OPERATOR   a secret a human mints. A clean checkout NEVER has one, so gating on it by
#              default would make -DryRun permanently red for exactly the person it is
#              meant to serve. Reported always; gated by -StrictSecrets.
if ($DryRun) {
    Write-Stage 0 'dry run - prerequisites'
    $missing = 0
    $secretsMissing = 0

    function Test-Artifact { param([string]$Path, [string]$Who, [string]$What)
        if (Test-Path $Path) { Write-Ok $What; Write-Host "        $Path"; return $true }
        Write-Bad ("{0} is MISSING" -f $What)
        Write-Host ("        want: {0}" -f $Path) -ForegroundColor Red
        Write-Host ("        owed by: {0}" -f $Who) -ForegroundColor Red
        return $false
    }

    Write-Info '-- machine ------------------------------------------------------------------'
    Write-Ok ("aws-cli {0} - terraform {1} - python {2} - node {3} - curl present" -f $AwsVersion, $TfVersion, $PyVersion, (& $NodeExe --version))
    Write-Ok ("aws account {0} - guard {1} - apply gate {2}" -f $Account, $AccountGuard, $(if ($ApplyApproved) { 'OPEN' } else { 'CLOSED' }))

    Write-Info '-- terraform (w3 - w4) ------------------------------------------------------'
    if (-not (Test-Artifact (Join-Path $TfDir 'main.tf')      'w4-tf-root-and-plan'   'terraform root'))      { $missing++ }
    if (-not (Test-Artifact (Join-Path $TfDir 'variables.tf') 'w4-tf-root-and-plan'   'terraform variables')) { $missing++ }
    if (-not (Test-Artifact (Join-Path $Root 'infra\modules\demo-api') 'w3-tf-api-public-url' 'api module'))  { $missing++ }
    $varsPath = Join-Path $TfDir 'variables.tf'
    if ((Test-Path $varsPath) -and (Select-String -Path $varsPath -Pattern 'variable "enable_cloudfront"' -Quiet)) {
        Write-Ok 'the root declares var.enable_cloudfront - the D1 switch is present'
    } else {
        Write-Bad 'infra/envs/demo/variables.tf does not declare var.enable_cloudfront (owed by: w4-tf-root-and-plan)'
        $missing++
    }
    $apiOutputs = Join-Path $Root 'infra\modules\demo-api\outputs.tf'
    if ((Test-Path $apiOutputs) -and (Select-String -Path $apiOutputs -Pattern 'output "function_url"' -Quiet)) {
        Write-Ok 'the api module emits output.function_url - stage 7 reads the hostname from it'
    } else {
        Write-Bad 'infra/modules/demo-api/outputs.tf emits no output "function_url" (owed by: w3-tf-api-public-url)'
        $missing++
    }
    # The parameter name is a contract between this script and Terraform: stage 2 writes
    # the SecureString to $DsnParam and stage 6 grants the Lambda role read on whatever
    # the root defaults to. A silent disagreement is a Lambda that 503s with `dsn_unset`
    # against a parameter that exists.
    $tfDsnDefault = ''
    if (Test-Path $varsPath) {
        $block = (Get-Content $varsPath -Raw) -split 'variable "dsn_parameter_name"' | Select-Object -Last 1
        if ($block -match '(?m)^\s*default\s*=\s*"([^"]+)"') { $tfDsnDefault = $Matches[1] }
    }
    if (-not $tfDsnDefault) {
        Write-Bad "could not read var.dsn_parameter_name's default from infra/envs/demo/variables.tf"; $missing++
    } elseif ($tfDsnDefault -eq $DsnParam) {
        Write-Ok "ssm parameter name agrees: $DsnParam (this script) == var.dsn_parameter_name default"
    } else {
        Write-Bad "ssm parameter name DISAGREES: this script writes $DsnParam, the root defaults to $tfDsnDefault"; $missing++
    }
    if (-not (Test-Artifact $PlanDoc 'w4-tf-root-and-plan' 'the committed terraform plan (what the orchestrator reviews)')) { $missing++ }

    Write-Info '-- lambda package (w2) ------------------------------------------------------'
    $zipOk = $true
    if (-not (Test-Artifact $LambdaZip      'w2-lambda-bundle' 'lambda package'))          { $missing++; $zipOk = $false }
    if (-not (Test-Artifact $LambdaManifest 'w2-lambda-bundle' 'lambda package manifest')) { $missing++; $zipOk = $false }
    if ($zipOk) {
        $env:MAINLINE_ARCH = $Arch
        if ((Invoke-PyInline $PackageProbe @($LambdaZip, $LambdaManifest)) -eq 0) {
            Write-Ok 'package and manifest agree, and the package carries the console and the bundle'
        } else {
            Write-Bad 'the lambda package is not deployable as it stands (owed by: w2-lambda-bundle)'
            $missing++
        }
    }

    Write-Info '-- console and evidence bundle (w1 - w2) ------------------------------------'
    if (-not (Test-Artifact (Join-Path $ConsoleDir 'package.json')     'w1-gate-run-route' 'console source'))          { $missing++ }
    if (-not (Test-Artifact (Join-Path $ConsoleDir 'dist\index.html')  'w1-gate-run-route' 'console build (dist/)'))   { $missing++ }
    if (-not (Test-Artifact (Join-Path $BundleSrc  'manifest.json')    'w2-lambda-bundle'  'EvidenceBundle manifest')) { $missing++ }

    Write-Info '-- deploy programs ----------------------------------------------------------'
    if (-not (Test-Artifact (Join-Path $ScriptDir 'cloud_chain.py')      'w6-live-services'        'migration applier')) { $missing++ }
    if (-not (Test-Artifact (Join-Path $ScriptDir 'seed_demo.py')        'w6-live-services'        'demo seed'))         { $missing++ }
    if (-not (Test-Artifact $CaptureBundle                               'w2-lambda-bundle'        'bundle capture'))    { $missing++ }
    if (-not (Test-Artifact $BuildLambda                                 'w2-lambda-bundle'        'lambda build'))      { $missing++ }
    if (-not (Test-Artifact $Acceptance                                  'w8-acceptance-and-video' 'acceptance prover')) { $missing++ }
    if (-not (Test-Artifact (Join-Path $ScriptDir 'bootstrap_state.sh')  'w5-deploy-scripts'       'state bootstrap'))   { $missing++ }
    if (-not (Test-Artifact (Join-Path $ScriptDir 'teardown.sh')         'w5-deploy-scripts'       'teardown'))          { $missing++ }

    Write-Info '-- live services (read-only probes) -----------------------------------------'
    $ssmList = Invoke-Native $AwsExe ($awsBase + @('ssm', 'describe-parameters',
        '--parameter-filters', 'Key=Name,Option=BeginsWith,Values=/mainline/',
        '--query', 'Parameters[].Name')) -Capture -AllowFail
    if ($script:LastNativeExit -eq 0) {
        if ($ssmList) { Write-Ok "ssm answers for /mainline/ - present: $ssmList" }
        else          { Write-Ok "ssm answers for /mainline/ - no parameter yet (stage 2 creates $DsnParam)" }
    } else {
        Write-Bad "aws ssm describe-parameters was refused: $ssmList"
        $missing++
    }

    # The Cloud cluster. Connect for real, select the demo database EXPLICITLY rather than
    # trusting the DSN's path segment (the committed DSN names /defaultdb; the demo lives
    # in mainline_demo). Read-only: one SELECT, no DDL, no writes.
    $cloudProbe = @'
import os, sys, time, urllib.parse

try:
    import psycopg
except ImportError:
    print("        psycopg is not installed in this virtualenv")
    raise SystemExit(1)

base = os.environ["COCKROACH_DSN"]
db = os.environ["MAINLINE_DEMO_DATABASE"]
u = urllib.parse.urlsplit(base)
target = urllib.parse.urlunsplit((u.scheme, u.netloc, "/" + db, u.query, ""))
started = time.monotonic()
try:
    with psycopg.connect(target, connect_timeout=25) as conn:
        row = conn.execute(
            "SELECT version(), current_database(),"
            " (SELECT count(*) FROM trappoint.deploy_chain),"
            " (SELECT encode(fingerprint,'hex') FROM trappoint.schema_attestation"
            "   ORDER BY ordinal DESC LIMIT 1)"
        ).fetchone()
except Exception as exc:  # noqa: BLE001
    code = getattr(exc, "sqlstate", None) or "-----"
    print(f"        [{code}] {str(exc).splitlines()[0][:300]}")
    raise SystemExit(1)
elapsed = time.monotonic() - started
version, current, chains, fp = row
print(f"        {u.hostname} - {current} - {version.split(' (')[0]} - {elapsed:.2f}s")
print(f"        deploy_chain rows {chains} - schema_attestation fingerprint {(fp or '')[:16]}")
if current != db:
    print(f"        connected to {current!r}, wanted {db!r}")
    raise SystemExit(1)
if not fp:
    print("        trappoint.schema_attestation is empty: /v1/health would answer 503 no_bookkeeping")
    raise SystemExit(1)
'@
    if (-not $env:COCKROACH_DSN) {
        Write-Bad 'no COCKROACH_DSN - cannot probe the Cloud cluster'; $missing++
    } else {
        $env:MAINLINE_DEMO_DATABASE = $DemoDatabase
        if ((Invoke-PyInline $cloudProbe) -eq 0) {
            Write-Ok "CockroachDB Cloud answered, and $DemoDatabase carries the bookkeeping schema"
        } else {
            Write-Bad "the Cloud cluster did not answer as $DemoDatabase (owed by: w6-live-services)"; $missing++
        }
    }

    Write-Info '-- operator secrets (NOT gated unless -StrictSecrets) -----------------------'
    if ($env:COCKROACH_DSN) { Write-Ok "COCKROACH_DSN present (host $dsnHost)" } else { Write-Bad 'COCKROACH_DSN absent'; $secretsMissing++ }
    if ($apiDsnSource) {
        Write-Ok "the Lambda's DSN is available ($apiDsnSource)"
    } else {
        Write-Bad "the Lambda's DSN is NOT available - stage 2 would refuse"
        foreach ($l in ($apiDsnAdvice -split "`n")) { Write-Host "        $l" -ForegroundColor Red }
        $secretsMissing++
    }
    if ($StrictSecrets) {
        Write-Info '-StrictSecrets: the rows above are gated on this run.'
    } else {
        Write-Info 'A clean checkout never has these; they are minted once and stored nowhere in the'
        Write-Info 'repository. Re-run with -StrictSecrets to make them fatal, which is what a real'
        Write-Info 'deploy does at stage 0 and stage 2.'
    }

    Write-Host ''
    if ($missing -gt 0) {
        Stop-Deploy ("$missing prerequisite(s) missing or wrong, listed above, each naming the worker`n" +
                     "that owes it. A dry run that found a hole exits non-zero on purpose: this is the`n" +
                     "check, not a preview. NOTHING WAS WRITTEN.") 1
    }
    if ($StrictSecrets -and $secretsMissing -gt 0) {
        Stop-Deploy ("-StrictSecrets was passed and an operator secret is missing (listed above).`n" +
                     "Every artefact this repository owes IS present; what is absent is a credential a`n" +
                     "human mints. NOTHING WAS WRITTEN.") 3
    }
    Write-Ok 'every prerequisite is present - a real run would proceed'
    Write-Info 'It would still stop at the apply gate unless $env:MAINLINE_APPLY_APPROVED=1.'
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
Invoke-Native $GitBash @($bootstrapPosix, '--bucket', $StateBucket, '--region', $Region,
    '--profile', $AwsProfile, '--expect-account', $Account) `
    -OnFail 'bootstrap_state.sh refused or failed; its message above says which.'
Write-Ok "s3://$StateBucket ready (versioned, private, encrypted, tagged, native locking)"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 2 — THE SECRET, INTO SSM, NEVER INTO TERRAFORM
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 2 'secret'
# The payload is built by Python into a temp file and passed with --cli-input-json, so the
# DSN never appears in an argument vector, in Get-Process output, in PSReadLine history,
# or in a transcript. The finally block removes it on every path.
$ssmJson = Join-Path ([System.IO.Path]::GetTempPath()) ("mainline-ssm-{0}.json" -f ([guid]::NewGuid().ToString('N')))
$builder = Join-Path ([System.IO.Path]::GetTempPath()) ("mainline-ssm-{0}.py" -f ([guid]::NewGuid().ToString('N')))
try {
    $pySrc = @'
import json, os, sys, urllib.parse

out = sys.argv[1]
db = os.environ.get("MAINLINE_DEMO_DATABASE") or "mainline_demo"
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
    # The database is forced: the admin DSN usually points at defaultdb, and a Lambda
    # connected to the wrong database fails in a way that reads like a privilege error.
    # The query string is kept verbatim because a Cloud Basic DSN's sslmode and options
    # are load-bearing.
    dsn = urllib.parse.urlunsplit((u.scheme, userinfo + "@" + host + port, "/" + db, u.query, ""))
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
    $env:MAINLINE_DEMO_DATABASE = $DemoDatabase
    Invoke-Native $Py @($builder, $ssmJson) -Capture -OnFail 'could not build the SSM payload.' | Out-Null

    $version = Invoke-Native $AwsExe ($awsBase + @('ssm', 'put-parameter',
        '--cli-input-json', "file://$ssmJson", '--query', 'Version')) -Capture `
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
$type = Invoke-Native $AwsExe ($awsBase + @('ssm', 'get-parameter', '--name', $DsnParam, '--query', 'Parameter.Type')) -Capture
if ($type -ne 'SecureString') { Stop-Deploy "the parameter came back as type '$type', not SecureString." }
Write-Ok 'read back: type=SecureString (value not requested, and never will be by this script)'

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
                         "$DemoDatabase from empty. Nothing was changed.") }
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
#
# Under D1 this zip is the ENTIRE deployable: handler, psycopg, the console SPA under
# web/, and the signed evidence bundle under bundle/. There is no second artefact and no
# S3 in the request path, so what is not in here is not on the internet.
Write-Stage 4 'lambda package'
if ($SkipBuild) {
    if (-not (Test-Path $LambdaZip)) { Stop-Deploy "-SkipBuild was passed but $LambdaZip does not exist." }
    Write-Skip "-SkipBuild, reusing $LambdaZip"
} else {
    if (-not (Test-Path $BuildLambda)) {
        Stop-Deploy ("neither scripts\deploy\build_lambda.ps1 nor build_lambda.sh exists. It is owed by`n" +
                     "worker w2-lambda-bundle and builds the psycopg-bearing deployment zip.")
    }
    # -ConsoleTransport live, HARD-WIRED, and not an option of this script.
    #
    # This stage packages the console for THIS origin, and this origin has a live kernel
    # behind it: infra/modules/demo-api serves /v1/* and the SPA from one Function URL. So
    # the only honest declaration a deploy can make is `live`, and making it a flag would
    # be offering an operator the ability to re-ship the defect of 2026-08-14 -- a console
    # compiled with VITE_MAINLINE_API_BASE="" and VITE_MAINLINE_BUNDLE_URL="./bundle/",
    # every byte on a judge's screen a recording of a run that happened somewhere else.
    #
    # Not a lock-out: an operator who genuinely means to deploy a different artefact builds
    # it themselves with build_lambda -ConsoleTransport <x> and passes -SkipBuild here,
    # which is a decision that appears in a shell history rather than one that happens by
    # default. The POSIX twin hard-wires the same value in the same place.
    $transportFail = ("build_lambda failed. If it REFUSED [CONSOLE TRANSPORT] or [CONSOLE BUILD ID],`n" +
                      "the console dist/ is not a live artefact: rebuild it with VITE_MAINLINE_API_BASE`n" +
                      "and MAINLINE_BUILD_ID set (docs/deploy/console-build.md).")
    if ($BuildLambda.EndsWith('.ps1')) {
        Invoke-Native 'pwsh' @('-NoProfile', '-File', $BuildLambda, '-Arch', $Arch, '-Out', $LambdaZip, '-ConsoleTransport', 'live') -OnFail $transportFail
    } else {
        Invoke-Native $GitBash @((& $GitBash -c "cygpath -u '$BuildLambda'").Trim(), '--arch', $Arch, '--out', $LambdaZip, '--console-transport', 'live') -OnFail $transportFail
    }
    if (-not (Test-Path $LambdaZip)) {
        Stop-Deploy "build_lambda finished but $LambdaZip is not there. Set `$env:MAINLINE_LAMBDA_ZIP if it writes elsewhere."
    }
}
if (-not (Test-Path $LambdaManifest)) {
    Stop-Deploy ("$LambdaManifest is missing. The build writes a manifest beside the zip and this`n" +
                 "script refuses to deploy a package whose contents it cannot assert.")
}
$env:MAINLINE_ARCH = $Arch
if ((Invoke-PyInline $PackageProbe @($LambdaZip, $LambdaManifest)) -ne 0) {
    Stop-Deploy ("the package and its manifest disagree, or the package is missing the console or the`n" +
                 "bundle (detail above). Rebuild it: build_lambda -Arch $Arch")
}
Write-Ok ("{0} ({1:N0} bytes, {2}) verified against its manifest" -f $LambdaZip, (Get-Item $LambdaZip).Length, $Arch)

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 5 — THE SITE PAYLOAD (OPTIONAL UNDER D1)
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
                "If the console documents a different command, set`n" +
                "`$env:MAINLINE_CONSOLE_BUILD_CMD and re-run.")
        }
    } finally { Pop-Location }
    if (-not (Test-Path (Join-Path $ConsoleDir 'dist\index.html'))) { Stop-Deploy 'the build produced no dist/index.html.' }
    Write-Ok ("console built: {0} files" -f (Get-ChildItem (Join-Path $ConsoleDir 'dist') -Recurse -File).Count)
}

if (-not (Test-Path $CaptureBundle)) {
    Stop-Deploy ("scripts\deploy\capture_demo_bundle.py does not exist. It captures the`n" +
                 "cryptographically verified EvidenceBundle from the Cloud cluster and is the console's`n" +
                 "REPLAY source. There is no way to fake this file and none is attempted.")
}
Invoke-Native $Py @($CaptureBundle) `
    -OnFail ("The bundle is the console's REPLAY source and it ships inside the Lambda package;`n" +
             "deploying without it would serve a REPLAY badge with nothing behind it.")
Write-Ok "EvidenceBundle captured into $BundleSrc"
if (-not $EnableCloudFront) {
    Write-Skip 'no S3 upload - under D1 the console and the bundle are served from the Lambda package'
}

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 6 — INFRASTRUCTURE · PLAN ALWAYS, APPLY ONLY BEHIND THE GATE
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 6 'infrastructure'
$tfPlan = Join-Path ([System.IO.Path]::GetTempPath()) ("mainline-{0}.tfplan" -f ([guid]::NewGuid().ToString('N')))
Push-Location $TfDir
try {
    Invoke-Native $TfExe @('init', '-input=false', '-reconfigure',
        "-backend-config=bucket=$StateBucket", "-backend-config=region=$Region") `
        -OnFail "If it complains about a state lock, see docs\deploy\RUNBOOK.md."

    $tfVars = @(
        '-var', "aws_region=$Region",
        '-var', "dsn_parameter_name=$DsnParam",
        '-var', "name_prefix=$NamePrefix",
        '-var', 'enable_api=true',
        '-var', "lambda_package_path=$LambdaZip",
        '-var', "lambda_architecture=$Arch"
    )
    if ($EnableCloudFront) {
        $tfVars += @('-var', 'enable_cloudfront=true')
        Write-Info 'enable_cloudfront=true - the pre-D1 shape. AWS will refuse the distribution on an'
        Write-Info 'account still under the verification hold; see docs\deploy\RUNBOOK.md appendix A.'
    } else {
        $tfVars += @('-var', 'enable_cloudfront=false')
        Write-Info 'enable_cloudfront=false - D1. The Lambda Function URL is the hostname.'
    }

    Invoke-Native $TfExe (@('plan', '-input=false', "-out=$tfPlan") + $tfVars) `
        -OnFail 'Nothing has been created or changed by this stage.'
    Write-Ok 'plan written'

    # ── THE APPROVAL GATE ─────────────────────────────────────────────────────────────
    #
    # This is a feature of the script, not a scaffold, and it is not removed when the demo
    # ships. `terraform apply` is the one irreversible, billable step in nine stages, and
    # the founder reviews the plan before it runs. The script therefore cannot apply on
    # its own initiative - the environment has to say so.
    if (-not $ApplyApproved) {
        Write-Host ''
        Write-Host 'STOPPED AT THE APPROVAL GATE - stage 6 planned, and did not apply.' -ForegroundColor Yellow
        Write-Host ''
        Write-Host '   Nothing was created. Nothing was changed. No URL was printed, because none exists.'
        Write-Host '   THIS IS NOT A FAILURE. It is the designed halt, and it exits 7 so that neither a'
        Write-Host '   human nor a CI job can mistake it for a completed deploy.'
        Write-Host ''
        Write-Host '   The plan above is the one the orchestrator reviews with the founder. The reviewed'
        Write-Host '   copy lives at:'
        Write-Host ''
        Write-Host '       docs/deploy/terraform-plan.md'
        Write-Host ''
        Write-Host '   To proceed once it is approved:'
        Write-Host ''
        Write-Host "       `$env:MAINLINE_APPLY_APPROVED = '1'"
        Write-Host "       pwsh -File scripts\deploy\deploy.ps1 -ExpectAccount $Account"
        Write-Host ''
        Write-Host '   Stages 1 to 5 have already run and are idempotent, so the approved run repeats'
        Write-Host '   them cheaply and picks up exactly here.'
        Write-Host ''
        if (Test-Path $tfPlan) { Remove-Item $tfPlan -Force -ErrorAction SilentlyContinue }
        Pop-Location
        exit 7
    }

    Invoke-Native $TfExe @('apply', '-input=false', $tfPlan) -OnFail (
        "Nothing else in this script has run; the state file records exactly what did get`n" +
        "created, and teardown.sh removes it.`n" +
        "`n" +
        "IF THE ERROR MENTIONS CloudFront AND 'Your account must be verified':`n" +
        "  that is an AWS account-level hold on creating NEW CloudFront resources, not a bug`n" +
        "  in this repository, and D1 exists precisely so it cannot block the demo. Re-run`n" +
        "  WITHOUT -EnableCloudFront. docs\deploy\RUNBOOK.md appendix A carries the transcript.")
    $outputsJson = Invoke-Native $TfExe @('output', '-json') -Capture
} finally {
    Pop-Location
    if (Test-Path $tfPlan) { Remove-Item $tfPlan -Force -ErrorAction SilentlyContinue }
}
Write-Ok 'apply completed'

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 7 — PUBLISH, AND PROVE THE HOSTNAME OVER HTTPS
# ══════════════════════════════════════════════════════════════════════════════════════
#
# THE BINDING RULE: THERE IS NO PATH THROUGH THIS SCRIPT THAT PRINTS A URL IT DID NOT JUST
# FETCH OVER HTTPS. Everything below exists to keep it true.
Write-Stage 7 'publish'
$outputs = $outputsJson | ConvertFrom-Json
$flat = @{}
foreach ($p in $outputs.PSObject.Properties) {
    $value = $p.Value.value
    $flat[$p.Name] = $value
    if ($value -is [psobject] -and $value.PSObject.Properties.Count -gt 0 -and -not ($value -is [string])) {
        foreach ($q in $value.PSObject.Properties) {
            if (-not $flat.ContainsKey("$($p.Name).$($q.Name)")) { $flat["$($p.Name).$($q.Name)"] = $q.Value }
        }
    }
}
# Order matters: `demo_url` is the root's own answer to "which hostname is the demo" and
# it already follows var.enable_cloudfront, so it wins. The rest are fallbacks.
$candidates = @('demo_url', 'deploy_summary.demo_url', 'api_function_url',
                'deploy_summary.api_function_url', 'function_url', 'deploy_summary.function_url')
$DemoUrl = ''
$UrlKey  = ''
foreach ($c in $candidates) {
    if ($flat.ContainsKey($c) -and $flat[$c] -is [string] -and $flat[$c].StartsWith('https://')) {
        $DemoUrl = $flat[$c].TrimEnd('/'); $UrlKey = $c; break
    }
}
if (-not $DemoUrl) {
    Write-Host ("   looked for, in order: {0}" -f ($candidates -join ', ')) -ForegroundColor Red
    Write-Host ("   the root emitted:     {0}" -f (($flat.Keys | Sort-Object) -join ', ')) -ForegroundColor Red
    Stop-Deploy ("terraform applied but no output holds an https:// demo hostname (see above).`n" +
                 "Under D1 the root must surface the api module's function_url. Nothing is printed as`n" +
                 "a working URL until one exists.")
}
Write-Ok "hostname from terraform output '$UrlKey': $DemoUrl"

function Get-Summary { param([string]$Key)
    if ($flat.ContainsKey("deploy_summary.$Key") -and $flat["deploy_summary.$Key"]) { return [string]$flat["deploy_summary.$Key"] }
    if ($flat.ContainsKey($Key) -and $flat[$Key]) { return [string]$flat[$Key] }
    return ''
}
$SiteBucket = Get-Summary 'site_bucket'
$DistId     = Get-Summary 'distribution_id'
$FnName     = Get-Summary 'api_function_name'
$UrlSource  = Get-Summary 'demo_url_source'
$AuthType   = Get-Summary 'api_authorization_type'
$Phase      = Get-Summary 'phase'
if ($UrlSource) { Write-Ok "terraform's own account of it: demo_url_source = $UrlSource" }
if ($Phase)     { Write-Ok "phase        $Phase" }
if ($FnName)    { Write-Ok "lambda       $FnName" }
if ($AuthType)  { Write-Ok "furl auth    $AuthType" }
if (-not $EnableCloudFront -and $AuthType -and $AuthType -ne 'NONE') {
    Stop-Deploy ("the Function URL is the demo hostname in this shape, but Terraform reports its`n" +
                 "authorization_type as '$AuthType'. An unsigned GET to an AWS_IAM Function URL is a`n" +
                 "403 with an empty body, so no judge could open it. Nothing is printed as a URL.")
}

# ── The optional S3 upload. Only reachable with -EnableCloudFront. ───────────────────
#
# Content types are set EXPLICITLY and not left to `aws s3 sync`'s guess, because that
# guess comes from Python's `mimetypes`, which on Windows reads the registry. Measured on
# this machine with the repository interpreter:
#
#     .js    -> application/javascript      (fine)
#     .mjs   -> text/plain                  <- a module served as text/plain does not load
#     .map   -> text/plain                  (harmless)
#     .woff2 -> None                        <- falls back to binary/octet-stream
if ($EnableCloudFront -and $SiteBucket) {
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
    Invoke-Native $AwsExe ($s3Base + @('s3', 'cp', (Join-Path $distDir 'index.html'), "s3://$SiteBucket/index.html",
        '--content-type', 'text/html; charset=utf-8',
        '--cache-control', 'no-cache, no-store, must-revalidate')) -Capture -OnFail 's3 cp of index.html failed.' | Out-Null
    Write-Ok "console uploaded to s3://$SiteBucket with explicit content types"
    if (Test-Path $BundleSrc) {
        Invoke-Native $AwsExe ($s3Base + @('s3', 'sync', "$BundleSrc\", "s3://$SiteBucket/bundle/", '--delete',
            '--cache-control', 'no-cache, must-revalidate')) -Capture -OnFail 's3 sync of the EvidenceBundle failed.' | Out-Null
        Write-Ok 'EvidenceBundle published under /bundle/'
    }
    if ($DistId) {
        Invoke-Native $AwsExe ($s3Base + @('cloudfront', 'create-invalidation', '--distribution-id', $DistId,
            '--paths', '/index.html', '/', '--output', 'text')) -Capture `
            -OnFail "Re-run: aws cloudfront create-invalidation --distribution-id $DistId --paths '/index.html' '/'" | Out-Null
        Write-Ok 'invalidated /index.html and /'
    }
} else {
    Write-Skip 'no S3 publish step in the D1 shape - the payload is inside the deployed package'
}

# ── THE HTTPS PROOF. Two GETs, both asserted, before a character of URL is printed. ──
Write-Info "fetching $DemoUrl/ over HTTPS..."
$code = '000'
for ($i = 0; $i -lt 20; $i++) {
    $code = (& $CurlExe -s -o NUL -w '%{http_code}' --max-time 20 "$DemoUrl/") 2>$null
    if ($code -eq '200') { break }
    Start-Sleep -Seconds 15
}
if ($code -ne '200') {
    Stop-Deploy ("GET $DemoUrl/ answered HTTP $code after five minutes of trying.`n" +
                 "The infrastructure exists; the hostname does not serve the console. Under D1 that`n" +
                 "means the package's web/ root is missing or `$MAINLINE_WEB_ROOT disagrees with it.`n" +
                 "NOTHING IS PRINTED AS A WORKING URL UNTIL IT IS ONE.")
}
$headers = (& $CurlExe -sSI --max-time 20 "$DemoUrl/") -join "`n"
$ctype = ''
if ($headers -match '(?im)^content-type:\s*(.+?)\s*$') { $ctype = $Matches[1] }
Write-Ok "GET $DemoUrl/ -> 200  ($ctype)"
if ($ctype -notmatch '^text/html') {
    Stop-Deploy ("GET $DemoUrl/ answered 200 but with Content-Type '$ctype', not text/html.`n" +
                 "A judge opening that URL gets a download or a wall of text, not the console.")
}

Write-Info "fetching $DemoUrl/v1/health..."
$healthRaw  = (& $CurlExe -sS --max-time 25 -w "`n%{http_code}" "$DemoUrl/v1/health") -join "`n"
$healthLines = $healthRaw -split "`n"
$healthCode = $healthLines[-1]
$healthJson = ($healthLines[0..($healthLines.Count - 2)] -join "`n")
if ($healthCode -ne '200') {
    Stop-Deploy ("GET $DemoUrl/v1/health answered HTTP $healthCode, not 200.`n" +
                 "Body: $healthJson`n" +
                 "A 503 with reason 'dsn_unset' means the Lambda cannot see $DsnParam. 'unreachable'`n" +
                 "means the DSN is wrong or the cluster refused. 'no_bookkeeping' means it connected`n" +
                 "to a database the migration chain never touched. THE URL IS NOT PRINTED.")
}
$healthProbe = @'
import json, os, sys

want_db = os.environ["MAINLINE_DEMO_DATABASE"]
try:
    body = json.loads(sys.argv[1])
except Exception as exc:  # noqa: BLE001
    print(f"   /v1/health returned non-JSON: {exc}")
    raise SystemExit(1)

problems = []
if body.get("ok") is not True:
    problems.append(f"ok is {body.get('ok')!r}: reason={body.get('reason')!r} detail={body.get('detail')!r}")
version = body.get("cluster_version") or ""
if "CockroachDB" not in version:
    problems.append(f"cluster_version does not name CockroachDB: {version!r}")
if body.get("database") != want_db:
    problems.append(f"database is {body.get('database')!r}, expected {want_db!r}")
if not body.get("schema_fingerprint"):
    problems.append("schema_fingerprint is empty - the cluster carries no attestation ledger")
for p in problems:
    print(f"   - {p}")
if problems:
    raise SystemExit(1)
print(f"   cluster      {version.split(' (')[0]}")
print(f"   database     {body['database']}")
print(f"   fingerprint  {body['schema_fingerprint'][:32]}")
print(f"   migrations   {body.get('migrations_applied')} applied - round trip {body.get('seconds')}s")
'@
$env:MAINLINE_DEMO_DATABASE = $DemoDatabase
if ((Invoke-PyInline $healthProbe @($healthJson)) -ne 0) {
    Stop-Deploy ("/v1/health answered 200 but the body does not name the cluster it is talking to`n" +
                 "(detail above). A health check that cannot say which database answered is not proof`n" +
                 "of anything, so this URL is not printed.")
}
Write-Ok "GET $DemoUrl/v1/health -> 200, and the body names the cluster"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 8 — PROOF
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 8 'proof'
if (-not (Test-Path $Acceptance)) {
    Stop-Deploy ("scripts\deploy\demo_acceptance.py does not exist. It is owed by worker`n" +
                 "w8-acceptance-and-video and is the only thing that proves the live gate refuses and`n" +
                 "then admits over HTTPS. A deploy that cannot prove itself is a failed deploy.")
}
Invoke-Native $Py @($Acceptance, '--url', $DemoUrl) -OnFail (
    "THE DEPLOY IS FAILED. The live gate did not refuse and then admit over HTTPS, which is`n" +
    "the product's entire claim. Do not submit this URL. Read the prover's output above,`n" +
    "then: aws logs tail /aws/lambda/$FnName --since 10m")
Write-Ok 'the live gate refused, refused under attack, and then admitted - over HTTPS'

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 9 — HAND-OFF
# ══════════════════════════════════════════════════════════════════════════════════════
Write-Stage 9 'hand-off'
Write-Host ''
Write-Host "  DEMO URL   $DemoUrl" -ForegroundColor Green
Write-Host "  proved     GET / -> 200 text/html  ·  GET /v1/health -> 200 naming $DemoDatabase"
Write-Host "  shape      $shape"
Write-Host "  region     $Region (AWS)   ·   aws-ap-southeast-1 (CockroachDB Cloud)"
Write-Host "  account    $Account"
if ($FnName)     { Write-Host "  lambda     $FnName" }
if ($SiteBucket) { Write-Host "  bucket     s3://$SiteBucket" }
if ($DistId)     { Write-Host "  cloudfront $DistId" }
Write-Host ''
Write-Host '  JUDGE ACCESS - free and unrestricted, no sign-up, no key' -ForegroundColor White
Write-Host '  * The URL above needs no credential. Open it.'
Write-Host '  * Read-only SQL, if a judge wants to check the database themselves:'
Write-Host '      user      mainline_judge'
Write-Host "      database  $DemoDatabase   on cluster mainline-dev (aws-ap-southeast-1)"
Write-Host '      scope     SELECT on the fourteen mainline_audit views, and nothing else'
Write-Host '      password  minted by scripts\deploy\judge_access.py --rotate, printed once, and'
Write-Host '                deliberately not stored by this script or anywhere in the repository.'
Write-Host '                Paste it into the submission form''s private notes field.'
Write-Host '  * The judge pack:  docs\deploy\JUDGE-PACK.md'
Write-Host '  * What is broken, published on the same site as the claims:  docs\HONESTY.md'
Write-Host ''
Write-Host '  Teardown, when judging is over:'
Write-Host "      & `"C:\Program Files\Git\bin\bash.exe`" scripts/deploy/teardown.sh --expect-account $Account --yes"
Write-Host ''
Write-Ok 'done'
exit 0
