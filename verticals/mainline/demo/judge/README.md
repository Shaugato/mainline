<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# `demo/judge/` — the Tier-3 question pack, and the machinery that keeps it true

[`../VERIFY.md`](../VERIFY.md) tells a judge what to paste. It is the right document and it
is not enough on its own, because it cannot tell anyone — including us — whether what it
says to paste is **still legal, still names columns that exist, and still fails where it
must**. Three things rot underneath a paste-ready prompt, and every one of them is
discovered in front of the judge unless something checks it first:

1. **a column is renamed** in a migration and the prompt now selects a column the view does
   not project. The judge gets an error where the page promised an answer.
2. **the statement drifts past a Managed-MCP limit.** At the limit the server **truncates
   rather than raising**, so a partial answer about how much is currently blocked arrives
   looking exactly like a complete one. In a product whose deliverable is a refusal, a
   silently truncated aggregate is the defect class.
3. **a negative stops being negative.** The four statements at the bottom of the pack must
   fail. A negative suite that has quietly gone green is the worst artefact in a
   repository, because it reads as the strongest one in it.

So the prompts live here as **data** — [`QUESTIONS.yaml`](QUESTIONS.yaml) — and everything
else in this directory exists to refuse a prompt that has stopped being true.

## What is here

| File | What it is |
|---|---|
| `QUESTIONS.yaml` | the pack: the ask, the exact statement, the view behind it, what a green answer proves and — mandatorily — what it does not |
| `PACK.md` | **generated** from that file; the page a judge reads. `render --check` fails when the two disagree |
| `envelope.py` | the Managed-MCP limits, re-implemented standalone, plus the vector-literal size model |
| `pack.py` | the pack loaded and made strict |
| `drift.py` | agreement with the migrations, `VERIFY.md`, `REFUSAL-STRINGS.yaml` and the claim-hygiene rules |
| `render.py` | the deterministic renderer |
| `runner.py` | execution over MCP or over a local SQL connection, which exits non-zero when it had nothing to talk to |
| `selftest.py` | one planted violation per family, so the validator has been red |
| `FALLBACK.md` | what this tier degrades to if publishing a key to anonymous verifiers is outside the sponsor's terms |

## Running it

Nothing needs to be installed but PyYAML. `psycopg` is needed only for `run --via sql`, and
`packages/mainline-mcp` only for `run --via mcp`; both report their absence as a NOT-RUN.

```bash
python verticals/mainline/demo/judge/cli.py validate        # envelope, negatives, drift
python verticals/mainline/demo/judge/cli.py self-test        # prove the validator goes red
python verticals/mainline/demo/judge/cli.py render --check   # PACK.md matches QUESTIONS.yaml
python verticals/mainline/demo/judge/cli.py envelope         # limits, bound lengths, cross-check
python verticals/mainline/demo/judge/cli.py list
python verticals/mainline/demo/judge/cli.py run --via sql    # needs TRAPPOINT_DSN
python verticals/mainline/demo/judge/cli.py run --via mcp    # needs a published key
```

**Exit codes are three-valued on purpose.** `0` checked and correct · `1` checked and wrong ·
`2` the pack could not be loaded · `3` **NOT RUN**, nothing was checked. A judge, a CI job
and an operator all need "we could not check" to be distinguishable from "we checked and it
is wrong", and one non-zero code makes that impossible.

## The five checks that earn this directory

**Every column a prompt selects exists in the shipped view.** `drift.py` parses the outer
projection out of the `CREATE VIEW` in `db/migrations/` and compares it against the prompt's
select list. This is the check most likely to fire during the build, and the only acceptable
place for it to fire is CI.

**Every statement is legal before anybody pastes it.** One statement per call, at most
16 384 characters, no `EXPLAIN ANALYZE`, no unreachable schema, and an explicit `LIMIT` no
larger than the server's page. The explicit `LIMIT` is ours rather than the server's: with
no `LIMIT` the server applies a silent page of 25 and a truncated page is indistinguishable
from a complete answer, whereas with `LIMIT 25` written down, *exactly 25 rows* is a signal
the runner acts on.

**Every negative is refused, by the refusal it names.** Each negative declares which
refusal it expects — `never_mcp_schema`, `forbidden_schema` — and the validator asserts that
exact class fired rather than merely that something raised. Over the wire the negatives are
sent through `probe_select_unscreened`, which deliberately turns our client-side screen off
so the **server** is the thing that refuses: a control that lives only in our client is a
control an attacker skips by not using our client.

**The bound `EXPLAIN` is measured, not assumed.** The vector width is read from the
`CREATE TABLE`, a worst-case literal is substituted, and the resulting statement is measured
against the character cap. Widening the embedding column turns this page red instead of
turning the take red.

**The validator has been red.** `self-test` plants one realistic violation per family — a
renamed column, a negative made legal, a dropped index hint, a prefix widened to `IN (...)`,
a completeness column that is never selected, a `defined_in` pointing nowhere, a prompt
dropped from the pack while `VERIFY.md` still shows it — and fails if any goes unnoticed.

## What this pack does not do

- **It does not replace Tier 2.** Reproducing the merge refusal on your own laptop needs no
  credential of ours and is the stronger claim. This tier is the *interesting* one, not the
  load-bearing one.
- **It does not measure the MCP response body.** `run --via sql` reports the bytes of a JSON
  serialisation of the rows, which is a proxy used to spot a view that has outgrown the
  budget. It is never presented as the size of a response nobody measured.
- **It does not verify the limits against the live endpoint.** No MCP service-account key
  exists on this machine, so the numbers in `envelope.py` are documentation-derived. Where
  they could be wrong, this implementation is the stricter of the two by construction: it
  refuses at or below every documented threshold and never above one.
- **It does not own a single file it checks against.** The migrations, `VERIFY.md` and
  `REFUSAL-STRINGS.yaml` belong to other workers. When one of them disagrees with this pack,
  the message names which file is the authority and which is the copy — and for a statement
  carrying `transcribed_from`, the copy is the one in this directory.

## Cross-check that is not wired yet

`scripts/demo/claim_hygiene.py` scans `verticals/mainline/demo/*.md` without recursion, so
this directory is outside its globs. Until that file's owner adds
`verticals/mainline/demo/judge/*.md` and `.../judge/*.yaml`, the pack scans **itself** by
importing that script's rule table and running it over this directory — so the coverage
exists today, and it exists in the one place that would otherwise be a hole.
