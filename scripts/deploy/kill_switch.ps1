#!/usr/bin/env pwsh
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#Requires -Version 7.0

<#
.SYNOPSIS
    Stop the MAINLINE demo Lambda from being invoked, and put it back.

.DESCRIPTION
    Windows twin of scripts/deploy/kill_switch.sh. Same two API calls, same account guard,
    same refusals, same exit codes.

    WHY THIS FILE EXISTS
    The demo origin is a Lambda Function URL with authorization_type = NONE. The account
    ceiling of 10 concurrent executions is the ONLY real bound on what it can cost, and a
    30-day flood against it is worth USD 11,700-33,250. docs/deploy/COST-BOUND.md carries
    the measured arithmetic. This script is lever L9 of that document -- the floor under
    everything else -- and it exists so the first time anyone needs it is not also the
    first time anyone writes it.

    WHAT IT DOES
        -Stop      reserve 0 concurrent executions  -> the function stops being invoked
        -Restore   remove the reservation           -> back to the unreserved default

    -Stop is immediate. Lambda refuses new invocations as soon as the reservation lands; a
    Function URL caller gets HTTP 429 with no body from the handler. Spend goes to zero
    except for whatever is already in flight.

    THE -1 / DeleteFunctionConcurrency SUBTLETY -- read before editing
    Terraform writes `reserved_concurrent_executions = -1` to mean "no reservation". That
    is a TERRAFORM sentinel, not an API value. PutFunctionConcurrency will not accept -1;
    its minimum is 0. The API that removes a reservation is DeleteFunctionConcurrency, and
    that is what -Restore calls. A version of this script that restored by putting -1 would
    fail exactly when it was needed.

        -Stop     ->  aws lambda put-function-concurrency --reserved-concurrent-executions 0
        -Restore  ->  aws lambda delete-function-concurrency

    WHY RESERVING 0 IS ACCEPTED ON AN ACCOUNT THAT REFUSES 20
    This account's ConcurrentExecutions limit is 10 (measured; COST-BOUND.md I1). A
    positive reservation is refused because it would push UnreservedConcurrentExecutions
    below the floor AWS keeps back. Reserving ZERO takes nothing from the unreserved pool,
    so it is accepted. Documented AWS behaviour; NOT measured on this account, because
    measuring it needs a mutating call against a function that does not exist yet.

    WHICH AWS ACCOUNT (decision D2)
    No account id is written in this file, and this script never PRINTS one either -- the
    live account is shown masked (first four and last four digits), matching how the
    account id is masked across the tracked tree. Supply neither -ExpectAccount nor
    $env:MAINLINE_AWS_ACCOUNT and this script changes nothing (exit 3). -AnyAccount is the
    only override. -DryRun is exempt, because it changes nothing by construction.

.PARAMETER Stop
    Reserve 0 concurrent executions. Requires -Yes unless -DryRun is also given.

.PARAMETER Restore
    Remove the reservation (Terraform's -1). Requires -Yes unless -DryRun is also given.

.PARAMETER Status
    Read-only. Print what the reservation is right now and exit.

.PARAMETER DryRun
    Print the exact API call and make none. With neither -Stop nor -Restore, prints both.

.PARAMETER Yes
    The explicit confirmation. Without it, -Stop and -Restore refuse (exit 3).
    Named -Yes rather than -Confirm so it cannot collide with PowerShell's own
    common parameter of that name.

.PARAMETER ExpectAccount
    The account id you believe you are pointed at. Compared against the live caller.

.PARAMETER AnyAccount
    Disable the account guard. The only override.

.EXAMPLE
    scripts/deploy/kill_switch.ps1 -DryRun
    Show both API calls and make neither.

.EXAMPLE
    scripts/deploy/kill_switch.ps1 -Stop -ExpectAccount 123456789012 -Yes
    Stop the function.

.EXAMPLE
    scripts/deploy/kill_switch.ps1 -Restore -ExpectAccount 123456789012 -Yes
    Put it back.

.NOTES
    EXIT CODES
      0  the reservation is in the state you asked for, verified by re-reading AWS
      1  the call failed
      2  usage error
      3  a safety refusal: the account did not match, or none was named, or no -Yes
      4  ran against a function that does not exist
#>

[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Restore,
    [switch]$Status,
    [switch]$DryRun,
    [switch]$Yes,
    [string]$ExpectAccount = $env:MAINLINE_AWS_ACCOUNT,
    [switch]$AnyAccount,
    [string]$FunctionName = $(if ($env:MAINLINE_FUNCTION_NAME) { $env:MAINLINE_FUNCTION_NAME } else { 'mainline-demo-api' }),
    [string]$Region = 'ap-southeast-1',
    [string]$Profile = $(if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { 'mainline-dev' })
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# The AWS CLI writes progress to stderr and uses exit codes as INFORMATION. Let this
# script read $LASTEXITCODE itself rather than having PowerShell throw on any stderr byte.
$PSNativeCommandUseErrorActionPreference = $false

$Bold = ''; $Dim = ''; $Reset = ''
if (-not $env:NO_COLOR) { $Bold = "`e[1m"; $Dim = "`e[2m"; $Reset = "`e[0m" }

function Write-Step  { param([string]$m) Write-Host "`n$Bold== $m$Reset" }
function Write-Info  { param([string]$m) Write-Host "   $m" }
function Write-Ok    { param([string]$m) Write-Host "   $Bold[ok]$Reset $m" }
function Write-Would { param([string]$m) Write-Host "   ${Bold}WOULD RUN$Reset $m" }

function Invoke-Die {
    param([string]$m, [int]$code = 1)
    Write-Host "`nkill_switch: $m`n" -ForegroundColor Red
    exit $code
}
function Invoke-Refuse {
    param([string]$m)
    Write-Host "`n${Bold}kill_switch REFUSED$Reset`n   $m`n" -ForegroundColor Red
    exit 3
}
function Show-Usage {
    param([int]$code = 2)
    Get-Help $PSCommandPath -Detailed | Out-String | Write-Host
    exit $code
}

# ── Get-MaskedAccount — this script prints no raw account id, ever ────────────────────
#
# teardown.sh echoes the account back so an operator can copy it into --expect-account.
# This script does not, because its output is routinely pasted into an incident thread.
# The masked form matches the tracked tree's convention (first four, last four).
function Get-MaskedAccount {
    param([string]$Account)
    if ($Account.Length -lt 8) { return 'REDACTED' }
    return '{0}REDACTED{1}' -f $Account.Substring(0, 4), $Account.Substring($Account.Length - 4)
}

# ── Invoke-AwsQuery — an EMPTY answer and a FAILED call are not the same thing ────────
#
# Same rule as teardown.sh: swallowing a non-zero exit would report an expired token or a
# missing permission as "no reservation set", which in THIS script is the one wrong answer
# that matters -- it would tell an operator the kill switch is off when it is unknown.
function Invoke-AwsQuery {
    param([string]$Label, [string[]]$Arguments, [switch]$Tolerate)
    $out = & aws @Arguments 2>&1 | Out-String
    $out = $out.Trim()
    if ($LASTEXITCODE -ne 0) {
        if ($Tolerate) { return @{ Ok = $false; Out = $out } }
        Invoke-Die "$Label failed, and this script will not treat an unreadable answer as a known one:`n   $out"
    }
    if ($out -eq 'None') { $out = '' }
    return @{ Ok = $true; Out = $out }
}

# ── mode resolution ───────────────────────────────────────────────────────────────────
# The wrapping @( ) is load-bearing under Set-StrictMode: a pipeline that selects zero or
# one element returns $null or a scalar, and .Count on those throws rather than saying 0/1.
$modes = @(@($Stop, $Restore, $Status) | Where-Object { $_ })
if ($modes.Count -gt 1) {
    Write-Host 'kill_switch: choose one of -Stop, -Restore, -Status.' -ForegroundColor Red
    Show-Usage 2
}
$Mode = if ($Stop) { 'stop' } elseif ($Restore) { 'restore' } elseif ($Status) { 'status' } else { '' }
# $Mode is lowercase because the rest of the script compares against it; $ModeFlag is what
# an operator actually types, and messages must quote the flag they can retype verbatim.
$ModeFlag = if ($Mode) { $Mode.Substring(0, 1).ToUpper() + $Mode.Substring(1) } else { 'Stop' }

# -DryRun with no mode shows both calls. Any other empty mode is a usage error.
if (-not $Mode -and -not $DryRun) { Show-Usage 2 }

# A mutating mode needs -Yes. -DryRun and -Status never do.
if (($Mode -eq 'stop' -or $Mode -eq 'restore') -and -not $Yes -and -not $DryRun) {
    Invoke-Refuse @"
-$ModeFlag changes live AWS state and you did not pass -Yes.

   Add -Yes when you mean it, or -DryRun to see the exact API call and make none.
"@
}

$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region
$env:AWS_DEFAULT_REGION = $Region
$AwsBase = @('--profile', $Profile, '--region', $Region, '--output', 'text', '--no-cli-pager')

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Invoke-Die 'the AWS CLI is not on PATH.'
}

$ident = Invoke-AwsQuery 'sts get-caller-identity' ($AwsBase + @('sts', 'get-caller-identity', '--query', 'Account'))
$Account = $ident.Out
if (-not $Account) { Invoke-Die "aws sts get-caller-identity failed for profile '$Profile'." }
$AccountMasked = Get-MaskedAccount $Account

# ── THE ACCOUNT GUARD ─────────────────────────────────────────────────────────────────
if ($AnyAccount) {
    Write-Info 'account guard DISABLED by -AnyAccount'
}
elseif ($ExpectAccount -and $Account -ne $ExpectAccount) {
    Invoke-Refuse @"
this is account $AccountMasked, which is not the one you named. Changing nothing.
   Fix the profile (-Profile <name>) or the expectation (-ExpectAccount <id>).
"@
}
elseif (-not $ExpectAccount -and -not $DryRun -and $Mode -ne 'status') {
    Invoke-Refuse @"
NOTHING TOLD THIS SCRIPT WHICH AWS ACCOUNT IT MAY CHANGE, so it will not change
   one. The caller is account $AccountMasked. Name it in full:

       aws sts get-caller-identity --query Account --output text      # read it
       scripts/deploy/kill_switch.ps1 -$ModeFlag -ExpectAccount <id> -Yes
   or
       `$env:MAINLINE_AWS_ACCOUNT = '<id>'

   No account id is hard-coded in this file and none is printed by it (decision D2).
   -AnyAccount is the only override. -DryRun and -Status need none of this,
   because they change nothing.
"@
}

$dryTag = if ($DryRun) { '  (DRY RUN — changes nothing)' } else { '' }
Write-Host ("{0}MAINLINE demo kill switch{1}   account={2}  region={3}  function={4}{5}" -f `
        $Bold, $Reset, $AccountMasked, $Region, $FunctionName, $dryTag)

# ── the two calls, written once so the dry run and the real run cannot drift ──────────
$StopCall = "aws --profile $Profile --region $Region lambda put-function-concurrency ``
                 --function-name $FunctionName --reserved-concurrent-executions 0"
$RestoreCall = "aws --profile $Profile --region $Region lambda delete-function-concurrency ``
                 --function-name $FunctionName"

# ── read the current reservation ──────────────────────────────────────────────────────
#
# get-function-concurrency returns an empty projection when NO reservation is set, and the
# integer when one is. ResourceNotFoundException means the function is not deployed, which
# is a different thing again and gets its own exit code.
function Get-CurrentReservation {
    $r = Invoke-AwsQuery 'get-function-concurrency' `
    ($AwsBase + @('lambda', 'get-function-concurrency', '--function-name', $FunctionName,
            '--query', 'ReservedConcurrentExecutions')) -Tolerate
    if (-not $r.Ok) {
        if ($r.Out -match 'ResourceNotFoundException' -or $r.Out -match 'Function not found') {
            return 'absent'
        }
        Invoke-Die "reading the current reservation failed, and this script will not guess:`n   $($r.Out)"
    }
    if ([string]::IsNullOrWhiteSpace($r.Out)) { return 'unreserved' }
    return $r.Out
}

function Get-StateDescription {
    param([string]$State)
    switch ($State) {
        'absent' { 'the function does not exist in this account/region' }
        'unreserved' { "NO reservation (unreserved — Terraform's -1); the function is LIVE" }
        '0' { 'reserved concurrency 0 — the function is STOPPED' }
        default { "reserved concurrency $State — the function is LIVE" }
    }
}

Write-Step 'current state'
$Current = Get-CurrentReservation
Write-Info (Get-StateDescription $Current)

# ══════════════════════════════════════════════════════════════════════════════════════
#  DRY RUN — prints the exact calls and makes none
# ══════════════════════════════════════════════════════════════════════════════════════
if ($DryRun) {
    Write-Step 'dry run — the exact API calls, made by nobody'
    if (-not $Mode -or $Mode -eq 'stop') {
        Write-Host "`n   $Bold-Stop$Reset  (spend -> 0; callers get HTTP 429)"
        Write-Would $StopCall
    }
    if (-not $Mode -or $Mode -eq 'restore') {
        Write-Host "`n   $Bold-Restore$Reset  (back to unreserved; Terraform's -1)"
        Write-Would $RestoreCall
        Write-Host "   ${Dim}NOTE  restore is delete-function-concurrency, NOT a put of -1."
        Write-Host "         PutFunctionConcurrency has a minimum of 0 and rejects -1.$Reset"
    }
    Write-Host "`n   ${Dim}Nothing was called. Re-run with -$ModeFlag -ExpectAccount <id> -Yes to act.$Reset`n"
    exit 0
}

# ══════════════════════════════════════════════════════════════════════════════════════
#  STATUS — read-only
# ══════════════════════════════════════════════════════════════════════════════════════
if ($Mode -eq 'status') {
    if ($Current -eq 'absent') { exit 4 }
    exit 0
}

if ($Current -eq 'absent') {
    Invoke-Die "there is no function named '$FunctionName' in account`n   $AccountMasked, region $Region. Nothing to $Mode." 4
}

# ══════════════════════════════════════════════════════════════════════════════════════
#  MUTATE
# ══════════════════════════════════════════════════════════════════════════════════════
if ($Mode -eq 'stop') {
    if ($Current -eq '0') {
        Write-Ok 'already stopped — reserved concurrency is already 0. Nothing to do.'
        exit 0
    }
    Write-Step "stopping $FunctionName"
    Write-Info $StopCall
    $null = Invoke-AwsQuery 'put-function-concurrency' `
    ($AwsBase + @('lambda', 'put-function-concurrency', '--function-name', $FunctionName,
            '--reserved-concurrent-executions', '0'))
}
else {
    if ($Current -eq 'unreserved') {
        Write-Ok 'already restored — there is no reservation. Nothing to do.'
        exit 0
    }
    Write-Step "restoring $FunctionName to unreserved"
    Write-Info $RestoreCall
    $null = Invoke-AwsQuery 'delete-function-concurrency' `
    ($AwsBase + @('lambda', 'delete-function-concurrency', '--function-name', $FunctionName))
}

# ── VERIFY by re-reading AWS, not by trusting the call's exit code ─────────────────────
Write-Step 'verify'
$Current = Get-CurrentReservation
Write-Info (Get-StateDescription $Current)

if ($Mode -eq 'stop' -and $Current -eq '0') {
    Write-Ok "STOPPED. $FunctionName accepts no invocations in account $AccountMasked."
    Write-Info 'spend from this function is now zero. Restore with:'
    Write-Info '  scripts/deploy/kill_switch.ps1 -Restore -ExpectAccount <id> -Yes'
    exit 0
}
elseif ($Mode -eq 'restore' -and $Current -eq 'unreserved') {
    Write-Ok "RESTORED. $FunctionName is live and unreserved (Terraform's -1)."
    Write-Info 'the account ceiling of 10 concurrent executions is the only bound again.'
    Write-Info 'read docs/deploy/COST-BOUND.md before leaving it that way.'
    exit 0
}

$wanted = if ($Mode -eq 'stop') { '0' } else { 'unreserved' }
Invoke-Die "the call returned success but the reservation did not land as asked: wanted`n   $wanted, read back '$Current'."
