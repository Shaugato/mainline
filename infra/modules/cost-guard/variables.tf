# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ══════════════════════════════════════════════════════════════════════════════════════
#  THE ARITHMETIC BEHIND EVERY THRESHOLD IN THIS FILE
# ══════════════════════════════════════════════════════════════════════════════════════
#
# A threshold nobody can reconstruct is a threshold nobody can argue with, and a number
# nobody can argue with is a number nobody has checked. Every default below is derived
# here, from measurements taken on 2026-08-13, and the derivation is written out so that a
# reader who disagrees can disagree with a STEP rather than with a preference.
#
# ── THE MEASUREMENTS ──────────────────────────────────────────────────────────────────
#
#   P1  the deployed package's served tree, read out of
#       `out/lambda/mainline-demo-api-arm64.zip` with `zipfile` on 2026-08-13:
#
#           web/ entries                114   1,274,342 B
#             of which .gz siblings      57     289,312 B
#             of which identity          57     985,030 B
#             of which source maps        0           0 B
#           largest identity object          433,396 B  web/assets/index-BjAGxrVJ.js
#           objects referenced by index.html      2     (one .js, one .css)
#
#       So ONE browser with a cold cache can pull AT MOST 57 objects out of this function,
#       because 57 is the whole identity tree. That is a bound, not an estimate, and it is
#       what the "objects per judge" term below uses.
#
#   P2  the account's Lambda concurrency ceiling in ap-southeast-1 is 10
#       (`aws lambda get-account-settings`; recorded in `infra/modules/demo-api/main.tf`
#       and in `scripts/deploy/kill_switch.sh`). It is `Adjustable: true` and nobody chose
#       it, which is the whole reason this module exists - but it is nonetheless the
#       PHYSICAL cap on how many invocations a window can contain, and every alarm here
#       has to sit under it or it cannot fire.
#
#   P3  the account has ZERO active cost allocation tags. Measured read-only 2026-08-13:
#
#           aws ce list-cost-allocation-tags --region us-east-1 --status Active
#             -> {"CostAllocationTags": []}
#           aws ce list-cost-allocation-tags --region us-east-1 \
#               --query "CostAllocationTags[?TagKey=='project']"
#             -> [{"TagKey": "project", "Type": "UserDefined", "Status": "Inactive", ...}]
#
#       The key EXISTS - AWS has seen `project` on resources in this account - and it is
#       INACTIVE. See `budget_service_filter_values` for what that forces.
#
#   P4  THE BEAT DURATIONS, AND THEY ARE THE MEASUREMENT THAT REWROTE THIS FILE.
#       `evidence/deploy/cost/latency-baseline.json`, driven over a real socket through the
#       real handler by `scripts/deploy/local_furl.py`. Workstation wall p50, warm:
#
#           429 refusal (rate-limited flood)   0.224 ms   evidence/deploy/cost/log-bytes.json
#                                                         (1,069,624 invocations / 30.0 s,
#                                                          8 threads -> 0.224 ms each)
#           index      4,655 B                 1.231 ms
#           asset_js   433,396 B id / 124,127 B gz   5.660 ms   <- the largest object that SHIPS
#           asset_map  1,554,168 B             14.106 ms   <- 0 maps ship; kept as a worst case
#           gate_run   in-region p50           1,392.4 ms  round_trip_model, corrected
#           gate_run   in-region p99           3,729.0 ms  round_trip_model, corrected
#
#       EVERY EARLIER NUMBER IN THIS FILE ASSUMED 100 ms. It is not 100 ms, and because
#       rate = concurrency / duration, that assumption understated what a 60-second window
#       can hold by a factor this header now computes rather than guesses.
#
#       THE WORKSTATION IS NOT A 256 MB LAMBDA and this file does not pretend it is.
#       `latency-baseline.json::cpu_share_probe` measured the handler's own hot CPU
#       operation against a throttled share of one core: at `core_share = 0.1429`
#       (`equivalent_lambda_memory_mb = 253`, i.e. the 256 MB the demo function is being
#       set to) the measured `slowdown_vs_full_core` is **3.944x**. Every workstation
#       duration above is multiplied by 3.944 before it is used below. That correction runs
#       in the direction that makes the flood look SMALLER and every up-margin look TIGHTER,
#       which is the direction a bound should err in.
#
#   P5  THE BUDGET'S OWN SLICE IS EMPTY, AND THE ACCOUNT AROUND IT IS NOT. Measured
#       read-only 2026-08-13 with the EXACT three-service filter `budget_service_filter_values`
#       carries:
#
#           aws ce get-cost-and-usage --time-period Start=2026-07-01,End=2026-08-14 \
#               --granularity MONTHLY --metrics UnblendedCost \
#               --filter '{"Dimensions":{"Key":"SERVICE","Values":[
#                          "AWS Lambda","AWS Data Transfer","AmazonCloudWatch"]}}'
#             -> 2026-07-01  0
#                2026-08-01  0
#
#       and, without the filter, the whole account:
#
#           July 2026            USD 34.86   (EC2 19.64, VPC 7.44, KMS 3.00, tax 3.17, ...)
#           August 1-13 2026     USD 13.54   (EC2 7.54, VPC 2.87, KMS 1.16, tax 1.22, ...)
#           aws budgets describe-budgets  ->  three existing budgets, ALL BREACHED:
#                 "My Monthly Cost Budget"            limit 10.00   actual 13.542  (135 %)
#                 "My Monthly Cost Budget - $5 limit" limit  5.00   actual 13.542  (271 %)
#                 "My Zero-Spend Budget"              limit  1.00   actual 13.542  (1354 %)
#
#       Read those two together and `budget_limit_usd` stops being a matter of taste. See
#       that variable.
#
# ── THE MODELLED JUDGING SESSION ──────────────────────────────────────────────────────
#
# Stated once here, used by three thresholds. Two sizes, because one number would hide
# which way the margin runs:
#
#   REALISTIC     8 judges. A hackathon panel is 3-8 people.
#   PESSIMISTIC  20 judges, all arriving in the same minute, all with cold caches. This is
#                2.5x to 6.7x a real panel and is not a thing that happens; it is here so
#                the margin is quoted against a session nobody can call optimistic.
#
#   per judge, worst single minute  = 57 objects (P1)  +  12 API calls  =  69 invocations
#                                     ^ the whole tree   ^ six demo beats, /v1/health,
#                                                          and room for retries
#
#   REALISTIC worst minute   =  8 x 69 =    552 invocations
#   PESSIMISTIC worst minute = 20 x 69 =  1,380 invocations
#
#   per judge, over one hour        = 5 page loads x 57  +  3 demo runs x 12  =  321
#   REALISTIC hour           =  8 x 321 =  2,568 invocations
#   PESSIMISTIC hour         = 20 x 321 =  6,420 invocations
#
#   AND OVER THE INGESTION ALARM'S 300-SECOND WINDOW, which is a DIFFERENT window and was
#   got wrong here until W3 checked it. An hourly rate converts to a 300-second count by
#   x 300/3600 = x 1/12, NOT by reading the hourly rate as a per-minute one and
#   multiplying by five:
#
#       REALISTIC    2,568/h  =  42.8 /min  =   214 invocations per 300 s
#       PESSIMISTIC  6,420/h  = 107.0 /min  =   535 invocations per 300 s
#
#   The previous text in `log_incoming_bytes_threshold` read "2,568/h = 214/min ... 1,070
#   invocations" and "6,420/h = 535/min ... 2,675 invocations" - a per-300-second figure
#   mislabelled as per-minute and then multiplied by five again. It was found by
#   `evidence/deploy/cost/log-bytes.json::derivation.false_positive_floor.
#   invocations_source_unit_slip`, which used the correct 535 and left this file alone
#   because this file is W4's. It is corrected here rather than quietly, and note the
#   direction: the corrected load is 5x SMALLER, so every margin below it got 5x BIGGER.
#   A correction that flatters is still a correction, and hiding it because it flatters
#   would be the same dishonesty as making it because it flatters.
#
# ── WHAT A THRESHOLD CAN PHYSICALLY SEE, AND WHAT A FLOOD ACTUALLY PRODUCES ───────────
#
# With C = 10 concurrent executions (P2), a window of W seconds cannot contain more than
#
#       N_max(W)  =  C * W / d          d = billed invocation duration, seconds
#
# invocations. Read the other way, an alarm at threshold T over window W is BLIND to any
# flood whose invocations are slower than
#
#       d_visible(T, W)  =  C * W / T
#
# That number is computed for each alarm below and printed into its `alarm_description`,
# because "this alarm cannot see that" is the sentence an operator needs at 3 a.m. and is
# the sentence a dashboard never says.
#
# THE SAME FORMULA WITH P4'S MEASURED DURATIONS IN IT, x 3.944 for the 256 MB core share:
#
#       flood path            d @ 256 MB        N_max(60 s)      N_max(3600 s)
#       429 refusal              0.883 ms          679,151         40,749,058
#       index                    4.855 ms          123,582          7,414,938
#       asset_js  (SHIPS)       22.323 ms           26,878          1,612,684
#       asset_map (does not)    55.634 ms           10,785            647,086
#       gate_run in-region p50   1,392 ms               43             25,855
#       gate_run in-region p99   3,729 ms               16              9,654
#
# `asset_js` is the binding row for both invocation alarms, because it is the LARGEST
# object that actually ships and therefore the SLOWEST static path a flood can choose, and
# a flood picks the row that costs the most per invocation. `asset_map` is carried one line
# below it as the worst case even though M3 measured ZERO source maps in the package: if a
# future build stops stripping them, that row is what the alarms would face.
#
# THE 100 ms ASSUMPTION EVERY EARLIER THRESHOLD HERE WAS SET AGAINST GAVE N_max(60 s) =
# 6,000. The measured, core-share-corrected figure is 26,878. The upper constraint on the
# burst threshold was therefore understated by 4.48x, and that single fact is what this
# revision of the file re-derives everything against.

# ── What is being guarded ──────────────────────────────────────────────────────────────

variable "guarded_function_name" {
  description = <<-EOT
    The name of the Lambda function this guard stops. There is no default and there must
    not be one: a responder that guesses a function name is a responder that can stop the
    wrong function, and the failure mode of a wrong guess is an outage somebody else has
    to diagnose. `infra/envs/demo` passes `module.demo_api` its own `function_name`.

    This is the ONLY function the responder's role may touch - the grant is built from
    this string into one exact ARN, with no wildcard anywhere in it.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{1,64}$", var.guarded_function_name))
    error_message = "guarded_function_name must be a bare Lambda function NAME (letters, digits, hyphen, underscore; 1-64 characters) - not an ARN and not a name with a version or alias suffix. The responder's IAM grant and its PutFunctionConcurrency call are both built from this string, and an ARN here would produce an ARN-inside-an-ARN that matches nothing."
  }
}

variable "guarded_log_group_name" {
  description = <<-EOT
    The CloudWatch log group whose ingestion the third alarm bounds. Empty means
    `/aws/lambda/<guarded_function_name>`, which is what `infra/modules/demo-api` creates
    and what Lambda would create on its own.

    It is a variable rather than a hard-coded derivation because the demo-api module sets
    `logging_config.log_group` explicitly and a future caller may point it somewhere else;
    an alarm on a log group nothing writes to is an alarm in INSUFFICIENT_DATA forever,
    which is a control that looks present and is not.
  EOT
  type        = string
  default     = ""
}

variable "account_concurrency_ceiling" {
  description = <<-EOT
    The account's Lambda `ConcurrentExecutions` quota in this region. MEASURED at 10
    (P2 in the header). Every reachability precondition in this module divides by it, so
    it is a variable rather than a literal: raise the quota and the preconditions
    recompute instead of going stale silently.

    It is NOT a control. AWS marks it `Adjustable: true`, nobody chose it, and a support
    ticket moves it. It is the denominator in "what can physically happen", nothing more.
  EOT
  type        = number
  default     = 10

  validation {
    condition     = var.account_concurrency_ceiling >= 1
    error_message = "account_concurrency_ceiling must be at least 1; it is the account's Lambda concurrency quota and appears as a factor in every reachability precondition in this module."
  }
}

variable "fastest_invocation_ms" {
  description = <<-EOT
    The shortest billed duration a single invocation of the guarded function can plausibly
    have, in milliseconds. Used ONLY as the numerator-side term in the reachability
    preconditions: `N_max(W) = ceiling * W / d`, so the FASTEST duration gives the LARGEST
    window count, which is the ceiling a threshold must sit under.

    10 ms, AND THE REASON PRINTED HERE UNTIL 2026-08-13 WAS FALSE. It read "10 ms is below
    anything W1 can plausibly report". P4 reports otherwise, measured: the `index` beat is
    1.231 ms, `asset_js` is 5.660 ms, and the 429 refusal path a flood is actually made of
    is 0.224 ms. Even after the 3.944x core-share correction only `asset_js` and slower
    clear 10 ms. The claim was wrong and is deleted rather than softened.

    THE VALUE STAYS AT 10 ANYWAY, and the reason is a direction argument that the wrong
    justification had backwards. `N_max = ceiling * W / d`, so:

      d TOO LARGE  -> N_max too SMALL -> the precondition refuses a threshold that IS
                      reachable. Cost: a plan that fails and a threshold forced DOWN.
      d TOO SMALL  -> N_max too LARGE -> the precondition ADMITS a threshold no flood can
                      reach. Cost: an alarm that is present, green, and cannot fire.

    The second is the exact defect this whole module exists to close, so the safe error is
    the large one. 10 ms sits above three of the four measured static paths, which makes
    every reachability precondition in this module STRICTER than physics - it can only ever
    force a threshold lower, never let an unreachable one through.

    WHAT THAT COSTS, SAID PLAINLY: the variable's NAME overstates what it holds. It is not
    the fastest invocation; it is the fastest invocation the preconditions are willing to
    assume. Renaming it is a caller-visible change and `infra/envs/demo` is another
    worker's file this wave, so the name stays and this paragraph is the correction. The
    true physical ceiling, if a reader wants it, is P4's table.
  EOT
  type        = number
  default     = 10

  validation {
    condition     = var.fastest_invocation_ms > 0
    error_message = "fastest_invocation_ms must be greater than zero; it is a divisor in the reachability arithmetic."
  }
}

variable "log_bytes_per_invocation_ceiling" {
  description = <<-EOT
    The most bytes ONE invocation can put into the log group, in bytes. Used only to
    compute the physical ceiling on `AWS/Logs IncomingBytes`, so that the ingestion alarm
    can be checked for reachability like the other two.

    5,261 B, MEASURED, and it replaces a round 16,384 that was nobody's measurement. This
    is an INPUT to arithmetic here and NOT a control - the control is the per-invocation
    log budget in `logbudget.py` (interface I5), which lives in the handler. Naming it here
    as a Terraform variable would produce a number that looks enforced by this module and
    is not, so the description says so instead.

    THE DERIVATION, from `evidence/deploy/cost/log-bytes.json`. Two terms, added:

      TERM 1 - the RUNTIME's own per-invocation bytes                 956 B  documented
        platform.start 317 + platform.report 267 + platform.runtimeDone 372, each already
        including CloudWatch's documented 26 B per event. No handler can suppress these.

      TERM 2 - the HANDLER's worst per-invocation wire bytes        4,305 B  MEASURED
        one `log.exception` per invocation (app.py:523) with a traceback that fills the
        allowance. The code bound behind it is DEFAULT_BUDGET_BYTES 4,096 + OVERRUN_BOUND
        947 = 5,043 MESSAGE bytes, which becomes 5,217 B on the wire once Lambda's 148 B
        JSON envelope and CloudWatch's 26 B are added. THE MEASURED 4,305 IS TAKEN RATHER
        THAN THE 5,217 CODE BOUND, because 4,305 is what the worst reachable call site
        actually emitted; the 5,043/5,217 pair is recorded here so a reader can see that
        the measurement sits under its own code bound rather than above it.

      TERM 1 + TERM 2                                               5,261 B  <- this variable

    The old description said "if W4's budget lands at a different figure, change this one
    to match". W3 measured the figure and the instruction is followed: 5,261 B, which is
    the runtime's own documented per-invocation term plus the handler's code ceiling
    carried to wire bytes. `log-bytes.json::derivation.reachability_precondition` names
    this same number and says W4 should set it.

    THE DIRECTION IS THE TIGHTENING ONE. 5,261 < 16,384, so the physical ceiling this feeds
    (`local.log_bytes_max_300s`) FALLS from 4.92 GB to 1.58 GB and the ingestion alarm's
    reachability precondition gets STRICTER, not looser. The threshold still clears it by
    94x, so nothing is forced; what changes is that the check now bounds against a measured
    quantity instead of a round one.

    NOT COVERED BY THIS NUMBER, and `log-bytes.json::residual_this_does_not_bound` measured
    it: records written on a logger the budget's filter is not attached to. 200 psycopg
    records reached a handler as 75,800 wire bytes and the budget charged ZERO for them.
    That is the one shape that decouples bytes from invocations without limit, and it is
    the reason alarm 3 exists at all rather than being a copy of alarm 1.
  EOT
  type        = number
  default     = 5261

  validation {
    condition     = var.log_bytes_per_invocation_ceiling > 0
    error_message = "log_bytes_per_invocation_ceiling must be greater than zero; it is a factor in the ingestion alarm's reachability precondition."
  }
}

# ── The three thresholds ───────────────────────────────────────────────────────────────

variable "invocations_burst_threshold" {
  description = <<-EOT
    ALARM 1 of 3, the MINUTES timescale. `AWS/Lambda Invocations`, Sum over 60 s, strictly
    greater than this. Breaching it publishes to the guard topic, which invokes the
    responder, which reserves the guarded function's concurrency at 0.

    3,000. THE NUMBER DID NOT MOVE AND THE REASON FOR IT DID. Both constraints below were
    recomputed against P4's measured durations rather than the 100 ms this file used to
    assume, and the result is that 3,000 is now justified by a constraint it was NOT
    justified by before. That is worth more than a new number would have been, and it is
    written out so a reader can check the claim rather than accept it.

    ── THE TWO CONSTRAINTS PULL OPPOSITE WAYS. BOTH ARE QUOTED AS RATIOS. ──────────────

    DOWNWARD - it must sit clear ABOVE a judging session, or the demo stops itself in
    front of the judges:

        PESSIMISTIC worst minute   1,380 invocations   3,000 / 1,380  =  2.17x
        REALISTIC   worst minute     552 invocations   3,000 /   552  =  5.43x

    UPWARD - it must sit clear BELOW what a flood puts into the same 60 seconds, or it is
    a control that is present, green, and cannot fire:

        asset_js  flood, 22.323 ms   26,878 /min   26,878 / 3,000  =  8.96x
        asset_map flood, 55.634 ms   10,785 /min   10,785 / 3,000  =  3.59x
        index     flood,  4.855 ms  123,582 /min                      41.19x
        429 path,         0.883 ms  679,151 /min                     226.38x

    THE GAP EXISTS AND IT IS 19.48x WIDE: 1,380 at the bottom, 26,878 at the top, and the
    binding upper row is `asset_js` because it is the largest object that ships and
    therefore the slowest static path a flood can pick. The geometric centre of that band
    is 6,090. THIS THRESHOLD SITS AT 0.49x THE CENTRE - deliberately biased toward the
    stopping end, by `docs/leads/cost-finish-plan.md` §0.5's ranking: an outage is
    recoverable by one command and a bill is not.

    ── WHAT THE MEASUREMENT CHANGED, WHICH IS THE WHOLE POINT ──────────────────────────

    Under the 100 ms assumption this file used to carry, N_max(60 s) was 6,000 and the band
    was 1,380 .. 6,000, a ratio of 4.35x. The threshold sat 2.17x above the floor and 2.00x
    below the roof - the two constraints were within a factor of two of colliding, and the
    old text's argument against 7,000 ("invisible to the exact flood the model describes")
    was correct ONLY under that assumption. With the measured durations the roof moves out
    4.48x and that argument evaporates: 7,000 would in fact be visible to an `asset_js`
    flood, at 3.84x margin. It is still not chosen, because the reason to stay low is now
    the DOWNWARD side and the coupling below, not the upward side.

    ── THE THIRD CONSTRAINT, WHICH IS MEASURED AND CAPS THIS NUMBER AT 3,510 ───────────

    `log_incoming_bytes_threshold` is derived FROM this variable:
    `evidence/deploy/cost/log-bytes.json` step 3 reads 3,000 out of this file and step 4
    turns it into 15,000 per 300 s. Both edges of that threshold's admissible band are
    proportional to this number, so moving it moves them:

        lower edge  =    4,780.005 B x burst     upper edge  =  26,305 B x burst
        16,777,216 B stays inside the band only for   638 < burst < 3,510

    3,000 is at 0.855x that cap and 4.70x that floor. RAISING THIS THRESHOLD ABOVE 3,510
    WOULD PUSH THE INGESTION THRESHOLD BELOW ITS OWN LOWER EDGE, at which point alarm 3
    fires on invocations alarm 1 deliberately permits and becomes a copy of alarm 1 at a
    lower number - the "a control that looks like two and is one" shape the hourly alarm's
    own precondition already forbids. Anyone raising this must raise
    `log_incoming_bytes_threshold` with it. The key
    `what_would_change_this_recommendation` in log-bytes.json says the same thing from the
    other side: "lowering invocations_burst_threshold: both edges fall proportionally".

    ── WHAT IT PERMITS, AND FOR HOW LONG - CORRECTED ──────────────────────────────────

    At 3,000 the alarm sees any flood whose invocations bill in under

        d_visible = 10 * 60 / 3000 = 200 ms

    which covers every static row of P4's table by at least 3.59x.

    The previous text said 2,999/min sustained is 4.32 M/day, 601 GB of egress and
    ~USD 54/day. THE ARITHMETIC IS RIGHT AND THE FRAMING WAS WRONG: nothing sustains that
    for a day, because the hourly alarm below is evaluated on a 3,600-second period and a
    caller pacing at exactly 3,000/min accumulates 180,000 invocations in one such period
    against a 15,000 threshold. So the burst line's permission lasts at most ONE hourly
    evaluation period, not a day, and costs at the 139,264 B wire ceiling (interface I2):

        egress    180,000 x 139,264 B = 25.07 GB x USD 0.09   =  USD 2.256
        requests  180,000 x USD 0.0000002                     =  USD 0.036
        compute   180,000 x 22.323 ms x 0.25 GB x 0.0000133334=  USD 0.013
                                                        total =  USD 2.31 per episode

    That is the honest bound on what this alarm alone lets through, and it is USD 2.31
    rather than USD 54. This alarm still does not claim to bound the slow burn: the HOURLY
    alarm bounds a caller pacing under this line, and the Budgets leg bounds a caller
    pacing under both. That is the whole point of three timescales.
  EOT
  type        = number
  default     = 3000

  validation {
    condition     = var.invocations_burst_threshold >= 1
    error_message = "invocations_burst_threshold must be at least 1."
  }
}

variable "invocations_hourly_threshold" {
  description = <<-EOT
    ALARM 2 of 3, the HOURS timescale. `AWS/Lambda Invocations`, Sum over 3600 s, strictly
    greater than this. Same topic, same responder, same stop.

    15,000. Like the burst line it does not move, and like the burst line the constraints
    were recomputed rather than inherited.

    ── THE TWO CONSTRAINTS, AS RATIOS IN BOTH DIRECTIONS ──────────────────────────────

    DOWNWARD, clear of a judging session:

        PESSIMISTIC session hour   6,420 invocations   15,000 / 6,420  =  2.34x
        REALISTIC   session hour   2,568 invocations   15,000 / 2,568  =  5.84x

    UPWARD, clear below what an hour of flood produces:

        what the BURST line permits per hour   3,000 x 60 = 180,000    =  12.00x
        asset_js flood at 22.323 ms                     1,612,684 /h   = 107.51x

    The 12.00x row is the one that matters and it is also the module's own
    `lifecycle.precondition` (`main.tf`, `invocations_hourly` second precondition): at or
    above `burst x 60` this alarm could only fire on traffic that already tripped alarm 1,
    so it would add no second timescale. 15,000/h averages 250/min, 8.3 % of the burst
    line, and that gap IS the alarm's job: a caller who paces at 3,000/min never trips
    alarm 1 and puts 180,000 into the period this one evaluates.

    ── WHAT IT CAN SEE, AND WHAT IT CANNOT - RE-DERIVED FROM MEASUREMENT ───────────────

    d_visible = 10 * 3600 / 15000 = 2,400 ms. Any flood whose invocations bill in under
    2.4 s reaches this threshold.

    THE PREVIOUS TEXT HERE WAS STALE IN TWO WAYS AND BOTH ARE CORRECTED. It reasoned about
    "a flood made ENTIRELY of ~3 s invocations - i.e. at the function timeout W6 is
    setting", giving 12,000/h. The timeout is not 3 s: `docs/leads/cost-finish-plan.md`
    §0.6 sets it to 14 s and records why 3 s was refused - it is 0.80x the corrected warm
    `gate_run` p99 and would truncate the headline beat, and because Lambda bills actual
    duration the timeout moves the bill by nothing. And the slow path is not hypothetical
    any more; P4 measured it. The corrected picture:

        gate_run in-region p50   1,392.4 ms  ->  25,855 /h   ABOVE 15,000 - CAUGHT
        gate_run in-region p99   3,729.0 ms  ->   9,654 /h   below 15,000 - NOT CAUGHT
        a flood at the 14 s timeout          ->   2,571 /h   below 15,000 - NOT CAUGHT

    So the honest statement is narrower and truer than the old one: a database-beat flood
    running at the MEDIAN in-region latency IS caught by this alarm; the same flood running
    at its 99th percentile is not, and neither is anything slower. That band - roughly 2.4 s
    to 14 s per invocation - is the residual under both invocation alarms.

    ── WHAT THE RESIDUAL COSTS, AT THE THRESHOLD RATHER THAN AT FLOOD RATE ────────────

    A caller under this alarm is BY DEFINITION not at flood rate, so this is costed at
    15,000/h and not at the 26,878/min the burst table shows. Two shapes, and the maximum
    of the two is the answer, not the product - a 14 s invocation is a database beat
    returning ~9,370 B and a 139,264 B response is a 22 ms static asset. Nobody gets both.

      SHAPE A, egress-maximal: 15,000/h of static assets at the 139,264 B wire ceiling
        egress    15,000 x 139,264 B = 2.089 GB x USD 0.09      =  USD 0.1880 /h
        requests  15,000 x USD 0.0000002                        =  USD 0.0030 /h
        compute   15,000 x 22.323 ms x 0.25 GB x 0.0000133334   =  USD 0.0011 /h
                                                          total =  USD 0.192 /h = 4.61 /day

      SHAPE B, compute-maximal: gate_run at the in-region p99, concurrency-capped to 9,654/h
        compute    9,654 x 3.729 s x 0.25 GB x 0.0000133334     =  USD 0.1200 /h
        egress     9,654 x 9,370 B = 0.090 GB x USD 0.09        =  USD 0.0081 /h
        requests   9,654 x USD 0.0000002                        =  USD 0.0019 /h
                                                          total =  USD 0.130 /h = 3.12 /day

    SHAPE A binds at USD 4.61/day. The old figure was USD 6.50/day and was computed from
    the 3 s timeout that is not the timeout; this one is computed from measured durations
    and the ceiling that is actually in force. It is what the Budgets leg is for, and
    `budget_limit_usd` carries the days-to-fire arithmetic.

    Producing the SHAPE B flood also requires a request path that genuinely bills seconds.
    A BUFFERED Function URL bills the HANDLER, not the client's read, so an attacker cannot
    stretch a static-asset response by reading it slowly; the only paths near a second are
    the database beats, which `ratelimit.py` bounds independently at 10 rps global.
  EOT
  type        = number
  default     = 15000

  validation {
    condition     = var.invocations_hourly_threshold >= 1
    error_message = "invocations_hourly_threshold must be at least 1."
  }
}

variable "log_incoming_bytes_threshold" {
  description = <<-EOT
    ALARM 3 of 3, the INGESTION bound. `AWS/Logs IncomingBytes`, Sum over 300 s, dimension
    `LogGroupName`, strictly greater than this many BYTES.

    Log ingestion has no native ceiling anywhere in AWS. A log group has RETENTION, which
    bounds storage; `infra/modules/demo-api` sets `log_retention_days = 7` and that is the
    only thing in this repository that has ever bounded logs. Ingestion is billed on
    arrival and 7-day retention does not refund it. This alarm is the first bound on the
    ingestion side that has ever existed here.

    16,777,216 B (16 MiB) per 300 s. THIS NUMBER IS NOT MINE. It is
    `evidence/deploy/cost/log-bytes.json::derivation.recommended_bytes`, produced by
    `scripts/deploy/measure_log_bytes.py` from a measurement of what this handler actually
    emits, and adopted here. What follows is that arithmetic, quoted, plus the two
    corrections it forced on this file.

    ── THE TERM NOBODY HAD MEASURED, AND IT IS ZERO ────────────────────────────────────

    A WORKING HANDLER EMITS NO BYTES OF ITS OWN. Measured across all five beats (480
    invocations) and across 2.1 million invocations of a sustained 429 flood at the code
    rate defaults: `handler_wire_bytes_per_invocation` p50 = 0, mean = 0.001. Ordinary
    ingestion here is ~100 % the runtime's fixed term, and the handler term appears only
    when something is already wrong. That is why the product below is a BAND and not a
    point, and it is the fact the old "~400 B/invocation" estimate got closest to and still
    got wrong in the wrong direction.

    ── THE ARITHMETIC, log-bytes.json steps 1-5 ────────────────────────────────────────

        step 1  the runtime's own per-invocation bytes             956 B   documented
                platform.start 317 + platform.report 267 + platform.runtimeDone 372,
                each already carrying CloudWatch's documented 26-byte per-event overhead:
                "the sum of all event messages in UTF-8, plus 26 bytes for each log event"
                (API_PutLogEvents, retrieved 2026-08-13). Cross-checked at 365 B measured
                off public.ecr.aws/lambda/python:3.13 through the Runtime Interface
                Emulator - a different (TEXT) format, so an order-of-magnitude check and
                not a substitute. The pessimistic reading is taken: W3 could not retrieve
                AWS's system-log-level event-mapping table and therefore counts
                platform.start and platform.report as PRESENT at system_log_level = WARN.
        step 2  the handler's own per-invocation bytes         0 .. 4,305 B   measured
        step 3  the count the BURST alarm permits per minute      3,000      read from
                                                                             this file
        step 4  the same count over THIS alarm's 300 s window     15,000     = 3,000 x 5
        step 5  the product, (step 1 + step 2) x step 4

            lower edge  (956.001) x 15,000  =  14,340,015 B    handler emitting nothing
            upper edge  (  5,261) x 15,000  =  78,915,000 B    every invocation a full
                                                               diagnostic

        16,777,216 sits at 1.170x the lower edge and 0.213x the upper edge.

    ── WHY THE LOWER END OF THE BAND, WHICH IS THE INCONVENIENT HALF ───────────────────

    The formula's headline output is the UPPER edge, 78,915,000 B. It is not adopted, and
    the reason is not that it is inconvenient - it is that 78,915,000 B per 300 s sustained
    is 22.73 GB/day, about USD 12.95/day at ap-southeast-1's ~USD 0.57/GB, against
    16,777,216 B's 4.83 GB/day and USD 2.75/day. Between two admissible values this
    repository's ranking picks the tighter one, for the reason `cost-finish-plan.md` §0.5
    gives: an outage is recoverable by one command and a bill is not. log-bytes.json
    publishes both edges precisely so that this choice is visible as a choice.

    WHAT THE TIGHTER END COSTS, NAMED. 16,777,216 B over 300 s is 1,118 B per invocation
    the burst alarm permits. The runtime term alone is 956 B, so about 162 B per invocation
    is left for the handler - far under the 4,096 B its own budget allows it. A caller
    pacing just under the burst alarm whose every invocation emits a full diagnostic
    therefore trips THIS alarm without tripping either invocation alarm. Both feed the same
    topic and the same responder, so the stop is identical; what it costs is only that the
    notification names alarm 3 instead of alarm 1.

    ── THE FALSE-POSITIVE FLOOR, WHICH IS THE NUMBER THAT MATTERS ON DEMO DAY ──────────

    A threshold at or below this fires on a LEGITIMATE pessimistic judging session in which
    every invocation is logging a full diagnostic - i.e. on a database outage DURING the
    demo. That converts an incident into an outage and deletes the logs you would have used
    to diagnose it.

        535 invocations per 300 s  x  5,261 B  =  2,814,635 B   -> clearance 5.96x

    ── AND THE TWO CORRECTIONS THIS FORCED ON THE FILE ─────────────────────────────────

    (1) THE UNIT SLIP. The text here used to read "2,568/h = 214/min ... 1,070
        invocations" and "6,420/h = 535/min ... 2,675 invocations". 2,568/h is 42.8/min,
        and 214 is the count over 300 SECONDS, not over a minute; the 1,070 and 2,675 were
        that mislabelling multiplied by five a second time. Found by
        `log-bytes.json::derivation.false_positive_floor.invocations_source_unit_slip`,
        which used the correct figures and deliberately left this file alone because this
        file is W4's. Corrected in the header's session block.

    (2) THE PER-INVOCATION TERM. "~400 B" is replaced by step 1's measured/documented
        956 B. Restating the modelled windows with both corrections:

        REALISTIC   300 s window   214 invocations x 956 B =   204,584 B -> margin 82.0x
        PESSIMISTIC 300 s window   535 invocations x 956 B =   511,460 B -> margin 32.8x

    THE MARGIN IS LARGE AND THAT IS NOT SLACK. Alarms 1 and 2 already bound the invocation
    COUNT. What this one uniquely catches is bytes DECOUPLED from invocations, and
    log-bytes.json measured that shape rather than imagining it: 200 psycopg records
    reached a handler as 75,800 wire bytes and the per-invocation budget charged ZERO for
    them, because a filter only sees the records its own logger creates. A library that
    starts logging per row is unbounded by anything in the handler, and it is the reason
    this alarm is not a copy of alarm 1.

    WHAT IT PERMITS. 16 MiB per 300 s sustained is 4.83 GB/day (4.50 GiB). CloudWatch Logs
    ingestion in ap-southeast-1 is ~USD 0.57/GB, so ~USD 2.75/day, ~USD 83 per 30 days -
    again bounded by the Budgets leg rather than by this alarm, and again said out loud
    rather than implied.

    WHAT WOULD INVALIDATE THIS NUMBER, from log-bytes.json's own list: a call site that
    loops or passes `stack_info=True` (the reachable per-invocation wire term rises from
    4,305 B to 19,786 B, measured, and both edges rise with it); raising
    `logbudget.DEFAULT_BUDGET_BYTES`, which requires raising this proportionally; and
    moving `invocations_burst_threshold` outside 638 .. 3,510, at which point 16,777,216
    leaves the band. There are three log call sites in this distribution - app.py:515,
    app.py:523 and ratelimit.py:526 - and today none of them loops or sets `stack_info`.
  EOT
  type        = number
  default     = 16777216

  validation {
    condition     = var.log_incoming_bytes_threshold >= 1
    error_message = "log_incoming_bytes_threshold must be at least 1 byte."
  }
}

# ── The Budgets leg ────────────────────────────────────────────────────────────────────

variable "budget_limit_usd" {
  description = <<-EOT
    The monthly limit, in USD, of the one `aws_budgets_budget` this module creates. The
    budget's ACTUAL-cost notification publishes to the same topic as the three alarms, so
    crossing this line stops the guarded function exactly as an alarm does.

    25.00, and P5 is why. "Almost none of it" used to stand where a measurement belongs;
    the measurement now exists and it is stronger than the estimate was.

    ── WHAT THIS BUDGET CAN DO ────────────────────────────────────────────────────────

    ITS SLICE IS EMPTY. Measured read-only 2026-08-13 with the EXACT three-service filter
    `budget_service_filter_values` carries - AWS Lambda, AWS Data Transfer, AmazonCloudWatch
    - the account spent 0 in July 2026 and 0 August-to-date. `aws lambda list-functions
    --region ap-southeast-1` returns `[]`; no Lambda has ever billed here. So the full
    25.00 is headroom for THIS demo and nothing else consumes any of it, and the founder's
    USD 25 cap lands on this line exactly rather than approximately.

    THE SERVICE FILTER IS WHAT MAKES 25.00 A BOUND RATHER THAN AN IMMEDIATE STOP, and this
    is the half that was never checked. The account around the slice is NOT quiet: USD 34.86
    in July and USD 13.54 in the first thirteen days of August, essentially all EC2, VPC,
    KMS and tax. `aws budgets describe-budgets` shows three budgets already in place and
    ALL THREE ALREADY BREACHED - limits of 10.00, 5.00 and 1.00 against an actual of 13.542.

    A 25.00 WHOLE-ACCOUNT BUDGET WOULD THEREFORE HAVE BEEN BREACHED WITHIN THE MONTH IT WAS
    CREATED - July closed at 34.86 - AND WOULD HAVE STOPPED THE DEMO AT THE FIRST COST
    EXPLORER REFRESH, on spend this project did not cause and cannot reduce. That is the
    fourth "control that looks present and is not" this module has had to design around,
    and the service filter is the thing that prevents it.

    ── WHAT THIS BUDGET CANNOT DO, AND IT IS THE MORE IMPORTANT HALF ──────────────────

    IT CANNOT STOP ANYTHING INSIDE A DAY. AWS Budgets evaluates against Cost Explorer, and
    Cost Explorer refreshes on a lag AWS documents as 8 to 24 hours. There is no setting
    that shortens it. A budget therefore cannot bound a flood - a flood is over, or has
    cost five figures, long before Cost Explorer has heard of it. THE TWO INVOCATION ALARMS
    AND THE INGESTION ALARM ARE THE BOUND; this is the backstop that catches what all three
    miss, and anything this project failed to model at all.

    It also cannot see spend outside its filter, by construction - and that is the same
    property that makes it usable here, so it is a trade and not a defect. And its
    notification is ACTUAL rather than FORECASTED (`main.tf`), so it fires on money already
    spent: later, and on a fact rather than on a prediction that might stop a live demo.

    ── THE BOUNDED EPISODE, ARITHMETIC RATHER THAN ADJECTIVE ──────────────────────────

    At the worst residual under both invocation alarms - SHAPE A in
    `invocations_hourly_threshold`, USD 4.61/day, recomputed there from measured durations
    and the 139,264 B wire ceiling:

        25.00 / 4.61 per day                 =  5.4 days to reach this line
        + up to 24 h of Cost Explorer lag    =  up to USD 4.61 of overshoot
                                     episode <=  USD 29.6, then the responder stops it

    Against the USD 229,759 / 30 days that `cost-finish-plan.md` §0.5 computes for an
    unguarded function at the MEASURED beat durations, that is the trade this module makes.
    README.md's residual table states it there rather than leaving it to be derived.
  EOT
  type        = number
  default     = 25.0

  validation {
    condition     = var.budget_limit_usd > 0
    error_message = "budget_limit_usd must be greater than zero. A zero or negative monthly limit produces a budget that is breached on creation, which would stop the guarded function the first time Cost Explorer refreshes."
  }
}

variable "budget_time_period_start" {
  description = <<-EOT
    The budget's `time_period_start`, in AWS's `YYYY-MM-DD_HH:MM` form.

    It is set explicitly, and pinned to a constant, because the provider computes a value
    when this is omitted and a computed start date is a value that can move between plans.
    A plan that shows a budget update nobody asked for is a plan whose noise is routine,
    and a plan whose noise is routine is a plan nobody reads.
  EOT
  type        = string
  default     = "2026-08-01_00:00"

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}:[0-9]{2}$", var.budget_time_period_start))
    error_message = "budget_time_period_start must be YYYY-MM-DD_HH:MM, for example 2026-08-01_00:00."
  }
}

variable "budget_service_filter_values" {
  description = <<-EOT
    The Cost Explorer SERVICE dimension values the budget's cost filter admits.

    ── WHY A SERVICE FILTER AND NOT A TAG FILTER, WHICH IS WHAT WAS ASKED FOR ──────────

    A `TagKeyValue` cost filter of `user:project$mainline` would scope this budget exactly
    to the resources this module and `demo-api` tag, and it is the right answer on an
    account where it works. It does not work on this one. MEASURED read-only 2026-08-13
    (P3 in the header):

        aws ce list-cost-allocation-tags --region us-east-1 --status Active
          -> {"CostAllocationTags": []}

    ZERO tags are active for cost allocation in this account. The key `project` is present
    in the account's tag inventory with `"Status": "Inactive"`. An inactive cost
    allocation tag matches NO cost records, so a `TagKeyValue` filter would produce a
    budget that is syntactically perfect, applies cleanly, appears in the console, and
    reports 0.00 USD forever - the exact "control that looks present and is not" defect
    this wave exists to close, wearing a billing hat.

    Activating a cost allocation tag is `ce:UpdateCostAllocationTagsStatus`, a MUTATING
    account-level call, which no worker in this wave may make. It is also not retroactive:
    AWS applies an activated tag from the activation date forward and takes up to 24 h to
    populate. So even after somebody activates it, the tag filter is wrong for the first
    day. `use_tag_cost_filter` below exists for the day after that.

    ── WHAT THE SERVICE NAMES ARE, AND WHICH ONE IS MEASURED ───────────────────────────

    Measured on this account, 2026-08-13:

        aws ce get-dimension-values --region us-east-1 \
            --time-period Start=2026-07-01,End=2026-08-13 --dimension SERVICE

      returned 19 values including "AmazonCloudWatch". It did NOT include "AWS Lambda" or
      "AWS Data Transfer", and the reason is that no Lambda function has ever billed in
      this account - `aws lambda list-functions --region ap-southeast-1` returns `[]`. The
      SERVICE dimension enumerates services that have PRODUCED cost, not services that
      exist.

      So exactly one of these three strings is confirmed against this account and two are
      AWS's documented canonical names, unverifiable here until the first bill. That is
      stated rather than smoothed over, and README.md carries the one command that settles
      it after the first invoice:

          aws ce get-dimension-values --dimension SERVICE --time-period ...

    ── WHY OVER-INCLUSION IS THE SAFE DIRECTION AND UNDER-INCLUSION IS NOT ─────────────

    "AmazonCloudWatch" also carries CloudWatch spend from anything else in the account, so
    this budget is WIDER than the demo. That means it can fire on somebody else's
    CloudWatch bill and stop the demo function - an availability cost, recoverable with
    `scripts/deploy/kill_switch.sh --restore`. The opposite error, a filter that matches
    nothing, is a bill with no bound at all and no way to notice. The wider error is
    recoverable and the narrower one is not, so the filter errs wide.
  EOT
  type        = list(string)
  default     = ["AWS Lambda", "AWS Data Transfer", "AmazonCloudWatch"]

  validation {
    condition     = length(var.budget_service_filter_values) > 0
    error_message = "budget_service_filter_values must name at least one Cost Explorer SERVICE value. An empty list would produce a budget over the entire account, which would stop the guarded function on unrelated spend."
  }
}

variable "use_tag_cost_filter" {
  description = <<-EOT
    Add a `TagKeyValue` cost filter alongside the service filter.

    FALSE, and turning it on before activating the tag TURNS THE BUDGET OFF. Multiple
    `cost_filter` blocks on one budget are ANDed by AWS, so `Service IN (...) AND
    TagKeyValue = user:project$mainline` against an inactive tag matches nothing at all -
    the budget would report 0.00 USD and never notify.

    The sequence that makes `true` correct, in order:

      1. activate the tag: Billing console -> Cost allocation tags -> `project` -> Activate
         (API: `ce update-cost-allocation-tags-status`) - a MUTATING call, not this wave's
      2. wait up to 24 h for AWS to populate it, and confirm:
             aws ce list-cost-allocation-tags --status Active
      3. set this variable to true and re-plan

    It defaults to false because a control that has to be right about an account setting
    nobody has made is a control that is wrong today.
  EOT
  type        = bool
  default     = false
}

variable "cost_allocation_tag_key" {
  description = <<-EOT
    The cost allocation tag KEY used when `use_tag_cost_filter` is true. `project`, which
    is what `infra/modules/demo-api` and this module both stamp on every resource they
    create, and which is what `scripts/deploy/teardown.sh` filters on.
  EOT
  type        = string
  default     = "project"
}

variable "cost_allocation_tag_value" {
  description = <<-EOT
    The cost allocation tag VALUE used when `use_tag_cost_filter` is true. `mainline`,
    matching the `project = "mainline"` tag both modules set and refuse to let a caller
    override.
  EOT
  type        = string
  default     = "mainline"
}

# ── The responder ──────────────────────────────────────────────────────────────────────

variable "responder_source_file" {
  description = <<-EOT
    Path to the responder's single Python source file. Empty means
    `scripts/deploy/cost_guard_responder.py`, resolved relative to this module.

    ONE FILE, ZIPPED BY `data.archive_file` AT PLAN TIME. The responder imports `boto3`
    and `json` and nothing else, and `boto3` ships in the managed python3.13 runtime, so
    there is no dependency tree, no build step and no wheel to get the architecture wrong.
    The zip is a function of this file's BYTES alone - see versions.tf for the measurement
    that establishes that.

    The file is under `scripts/deploy/` rather than inside this module because it is also
    a program a human can read, import and test: `tests/deploy/test_cost_guard_responder.py`
    imports it directly and proves the stop call with `botocore.stub.Stubber`. A responder
    that only exists as a string inside a Terraform file cannot be tested at all, and an
    untriggered action is indistinguishable from no action.
  EOT
  type        = string
  default     = ""
}

variable "responder_architecture" {
  description = <<-EOT
    Instruction set for the responder function. `arm64`: it is ~20 % cheaper per GB-second
    and the responder is pure Python calling one AWS API, so there is no native wheel that
    could be built for the wrong architecture - the class of defect
    `infra/modules/demo-api` guards against with a package-manifest precondition cannot
    arise here.
  EOT
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.responder_architecture)
    error_message = "responder_architecture must be \"arm64\" or \"x86_64\"."
  }
}

variable "responder_timeout" {
  description = <<-EOT
    Seconds. 15: one `PutFunctionConcurrency` call plus botocore's default retry chain
    (`max_attempts = 3`, standard mode) plus a cold `import boto3`, with room to spare.

    Short enough that a wedged responder cannot itself become a cost, long enough that a
    transient throttle on the control-plane API does not lose the stop. The stop is the
    one call in this repository that must not be lost to an impatient timeout.
  EOT
  type        = number
  default     = 15

  validation {
    condition     = var.responder_timeout >= 3 && var.responder_timeout <= 60
    error_message = "responder_timeout must be between 3 and 60 seconds. Below 3 a cold start plus one retried control-plane call does not reliably fit; above 60 a wedged responder is a cost of its own, and nothing it does takes a minute."
  }
}

variable "responder_memory_size" {
  description = <<-EOT
    MB. 128, the Lambda minimum. The responder parses one small JSON envelope and makes
    one API call; more memory buys CPU it cannot use and costs proportionally more per
    millisecond. At 128 MB and a ~1 s cold invocation the responder costs about
    USD 0.0000021 per firing.
  EOT
  type        = number
  default     = 128

  validation {
    condition     = var.responder_memory_size >= 128 && var.responder_memory_size <= 512
    error_message = "responder_memory_size must be between 128 and 512 MB. The responder makes one API call; anything above 512 is paying for CPU it cannot use."
  }
}

variable "responder_log_retention_days" {
  description = <<-EOT
    Retention on the responder's OWN log group. 30 rather than the demo function's 7: this
    log is the record of whether the stop fired, and it is read after an incident rather
    than during one. Seven days is long enough to debug a flood and too short to answer
    "has this ever fired?" a month later.

    Volume is negligible - a few hundred bytes per firing, and firings are rare by
    construction.
  EOT
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.responder_log_retention_days)
    error_message = "responder_log_retention_days must be one of CloudWatch Logs' accepted retention values (1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653)."
  }
}

variable "responder_log_level" {
  description = <<-EOT
    `logging_config.application_log_level` for the responder. INFO, deliberately louder
    than the demo function's WARN: every decision this responder makes - stopped, refused,
    ignored - is a line somebody will want after the fact, and there are at most a handful
    of them per incident.
  EOT
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"], var.responder_log_level)
    error_message = "responder_log_level must be one of TRACE, DEBUG, INFO, WARN, ERROR, FATAL - the levels Lambda's JSON logging_config accepts."
  }
}

# ── Naming, tags, and the human in the loop ────────────────────────────────────────────

variable "name_prefix" {
  description = <<-EOT
    Prefix for every name this module creates. Empty means `<guarded_function_name>-guard`,
    which produces `mainline-demo-api-guard` for the topic, budget and role, and
    `mainline-demo-api-guard-responder` for the function.

    The alarms are named `<guarded_function_name>-invocations-burst`,
    `-invocations-hourly` and `-log-ingestion` - deliberately NOT prefixed with `-guard`,
    because they are alarms ON the demo function and an operator scanning
    `describe-alarms` should find them next to `demo-api`'s own four
    (`-errors`, `-throttles`, `-duration-p99`, `-concurrency`). None of those four names
    collides with these three.
  EOT
  type        = string
  default     = ""
}

variable "notification_emails" {
  description = <<-EOT
    Email addresses to subscribe to the guard topic, so that a human learns the demo was
    stopped and can run `scripts/deploy/kill_switch.sh --restore`.

    EMPTY BY DEFAULT, AND AN UNCONFIRMED SUBSCRIPTION IS A CONTROL THAT LOOKS PRESENT AND
    IS NOT. `aws_sns_topic_subscription` with `protocol = "email"` creates a subscription
    in `PendingConfirmation`; AWS sends a confirmation link and delivers NOTHING until
    somebody clicks it. Terraform cannot click it and reports the resource as created
    either way. `infra/modules/demo-api/main.tf` says the same thing about its
    `alarm_actions` default and it is the same rule here.

    This list gates NOTHING in the stop path. The responder subscription below is
    unconditional; these are additional human-facing subscribers.
  EOT
  type        = list(string)
  default     = []
}

variable "tags" {
  description = <<-EOT
    Extra tags. Merged UNDER this module's own `project` / `component` / `managed_by`
    tags, so a caller cannot retag this stack out from under
    `scripts/deploy/teardown.sh`'s `project=mainline` filter - nor out from under this
    module's own budget filter, should `use_tag_cost_filter` ever be turned on.
  EOT
  type        = map(string)
  default     = {}
}
