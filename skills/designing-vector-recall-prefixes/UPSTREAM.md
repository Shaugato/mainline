<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Filing notes — `designing-vector-recall-prefixes`

Not part of the skill. This file records what is known, what is assumed, and what must be
re-checked before anything is filed, so that none of it has to be reconstructed later.

## What this skill is shaped for

An upstream contribution to [`cockroachlabs/cockroachdb-skills`](https://github.com/cockroachlabs/cockroachdb-skills)
(Apache-2.0, Agent Skills Specification format), in a **performance-and-scaling** domain
directory. The skill is deliberately free of any application-domain vocabulary: it is about
prefix-constrained vector indexes on CockroachDB and nothing else, so it reads as a
contribution rather than as an advertisement.

## The destination directory is UNCONFIRMED and must be checked before filing

Two sources inside this project disagree, and the disagreement is recorded rather than
resolved by preference:

* the architecture document describes **10 domain directories, four of them empty**, and names
  `performance-and-scaling` among them;
* the deep-verification note, which enumerated the repository by direct inspection on
  2026-08-02, lists **9 domain directories and 34 skills**, with
  `cost-and-usage-management/`, `integrations-and-ecosystem/` and
  `resilience-and-disaster-recovery/` as the `.gitkeep`-only ones. `performance-and-scaling`
  does not appear in that enumeration.

**Before filing:** enumerate `skills/` in the upstream repository at HEAD and place this skill
in the performance-and-scaling directory if it exists, or in whichever empty domain best fits
if it does not. Being the *first* skill in an empty domain is a materially stronger
contribution than the thirteenth in the most crowded one. Do not name a specific directory in
a README, a deck or a video until it has been confirmed at HEAD.

Both sources agree on the finding that actually motivates the contribution: **there is no skill
anywhere in that repository about vector indexes, C-SPANN, or ANN query design.** This lands in
genuinely empty territory whichever directory it goes in.

## Claim the filing, never the merge

Two earlier community PRs (#15, #17) had no maintainer engagement for weeks, while the
repository itself is active (PR #18 merged 2026-07-22). So: *"these two PRs have not been
engaged with"*, never *"the repository is unmaintained"* — and the claim made anywhere
externally is **the filing**, never the merge. Upstream acceptance is not on any critical path.

## Pre-filing checklist

- [ ] `python scripts/assert_prefix_index_used.py --self-test` exits 0.
- [ ] Frontmatter validates against the Agent Skills Specification (`name` ≤64 chars,
      `description` ≤1024 chars).
- [ ] Every documented claim in `references/cspann-prefix-rules.md` still resolves at the cited
      URL, and every number that is **ours** is still labelled as ours (the sizing table, the
      ≥80 %-of-peak knee rule, the 1.7 latency-ratio ceiling).
- [ ] The `EXPLAIN` fragment matches what the current version actually prints — re-capture it
      rather than copying the documentation example, and update the reference if they differ.
- [ ] No application-domain vocabulary anywhere in `SKILL.md`, `references/` or `scripts/`.
- [ ] The script runs on a machine with no third-party packages installed (stdlib only, except
      the optional `--dsn` path, which reports psycopg's absence rather than crashing).

## Provenance of the claims

Documented platform behaviour is cited inline in `references/cspann-prefix-rules.md`. The
`optimizer_span_limit` wording was re-verified against the v25.4 release notes on 2026-08-07.
The `EXPLAIN` fragment shape (`vector search` / `table:` / `target count:` / `prefix spans:`)
comes from the stable vector-index documentation's own example; **it has not yet been captured
from a live cluster by this project**, because no CockroachDB was reachable on the authoring
machine. `tests/integration/recall_index/test_ix02_plan_pgwire.py` captures the real output the
first time it runs against one, and any difference between the documented example and the
observed output should be reflected here before filing.
