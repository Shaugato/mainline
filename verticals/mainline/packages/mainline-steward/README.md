<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-steward`

The Steward's attestation emitter: every scheduled ops run becomes one hashed
`ops_attestation`, and the only write path in this distribution is `insert_rows` on
`mainline_meas.external_attestation`.

> **An LLM ops report is evidence that a review occurred, not evidence of a condition.**

That sentence is the only claim a Steward run supports, and this package exists to make
the weaker claim *checkable*. Every finding carries the exact statement that produced it
and the SHA-256 of the rows that came back, so a reader who distrusts the narrative
entirely can re-run the SQL against CockroachDB's own public endpoint, canonicalise the
rows, and compare 32 bytes.

The sentence is also in
`verticals/mainline/apps/steward/runbooks/steward-operations.md` and in
`mainline_steward/attestation.py`'s module docstring;
`tests/integration/steward/test_evidence_sentence.py` greps all three, so it cannot be
quietly dropped from one of them.

## The shape, in four properties

**The model does not produce the evidence.** `StewardRun` issues every contracted read
itself, through `mainline_mcp.Client`, and hashes the rows. The headless Claude Code
session that consumed the pinned CockroachDB Agent Skills produces *narrative*, matched
onto findings that already exist. `Finding.with_narrative` is the only mutator on a
finding and it reaches exactly one field — a statement and a result hash are unreachable
from anything a model wrote.

**Statements are generated, never authored.** A finding is built from a contracted
`ViewSpec`, whose statement is `SELECT * FROM <view> LIMIT <cap>` produced by
`spec/mcp/audit-surface.contract.yaml`, or from a `CcloudPage` whose command this package
assembled from typed methods. There is no constructor that takes free text.

**There is no severity field.** Severity comes from a coded field, a regulator
classification, or a signed human; a model-rated severity never arms the gate. A Steward
finding that carried one would be one refactor away from being read as one.

**`outcome` reports run completeness, never a condition.** `verified` means every
contracted read answered — not that anything is healthy. `indeterminate` means at least
one did not, so the rest is not coverage. The payload carries `outcome_means` in words,
because the three column values invite the wrong reading.

## The one write path

```python
Client.insert_external_attestation(rows)  # no parameter names a table
```

`mainline_mcp.client.Client` has no method that can name a target table, so "insert
somewhere else" is not a call this package can express.
`tests/integration/steward/test_no_other_write_path.py` walks this distribution's AST and
fails on a pgwire driver import, an AWS SDK import, a model SDK import, an import of
`probe_insert_rows_unbound`, or a second MCP write verb appearing anywhere.

The dependency list is the security boundary and it is three entries: `mainline-mcp`,
`trappoint-jcs`, `pyyaml`.

## Commands

```
mainline-steward schedules  [--json]                    the declarative calendar
mainline-steward prompt     <schedule> <ts> [--version-only]
mainline-steward skills     commit                      the single pinned upstream commit
mainline-steward skills     verify --skills-root R [--schedule-id S] [--record PATH]
mainline-steward skills     stage  --schedule-id S --skills-root R --destination D
mainline-steward allowlist  [--mcp-only]                settings.json's permissions.allow
mainline-steward attest     <schedule> <ts> [--send]    read, hash, write the one row
```

`attest` exits **0** on an already-attested occurrence: EventBridge Scheduler is
at-least-once, and a redelivery that does nothing is correct behaviour that must not page
anybody. `--send` is opt-in, because `insert_rows` is a real append to a real evidentiary
table.

## What is verified, and what is not

Exercised offline with no CockroachDB Cloud organisation and no AWS credentials: the
schedule loader, the skill-pin verifier, the prompt renderer, the finding builders, the
payload canonicalisation and leaf hash, the emitter's single write path, the `ccloud`
parsing and its missing-field refusal, and the capability-boundary assertions.

Not verified from this machine, and marked as such at each site: whether Managed-MCP
`insert_rows` accepts a `BYTES` column as a `\x`-prefixed hex string (isolated in
`BytesEncoding`, two members, one place to change) and whether it fires server-side
triggers (`GT-09` — safe either way, because `external_attestation` is trigger-free by
construction).

The consumed skills are pinned to upstream commit
`e14e86d23ce8ee2e7e40a34ce2944c2502b6eadd` of `cockroachlabs/cockroachdb-skills`, read
from the public repository on 2026-08-04. Their `expected_sha256` fields ship as `null`
and are recorded by `skills verify --record` against a real checkout, because the build
machine had the commit and not the bytes, and a digest we had not computed would have been
an invented fact in an evidentiary file.
