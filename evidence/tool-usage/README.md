<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `evidence/tool-usage/`

Two machine-written censuses that back every number in
[`docs/TOOL-USAGE.md`](../../docs/TOOL-USAGE.md), the hackathon's *"which CockroachDB and
AWS services did you use, and how"* document.

| file | what it holds |
|---|---|
| `crdb-features.json` | one row per CockroachDB tool or engine feature — where it appears, how it is used, and whether it has actually run |
| `aws-services.json` | one row per AWS service — same shape, same verdict column |

## The one command that regenerates both

```bash
python scripts/submission/capture_tool_evidence.py
```

Standard library only — no `uv sync`, no `pip install`. No network. No credential, and no
environment variable holding one. A document about which cloud services a project uses
must not require those cloud services in order to check it, or the reader is trusting the
same credential the claim is about.

Two more modes:

```bash
python scripts/submission/capture_tool_evidence.py --check   # exit 1 if these files are stale
python scripts/submission/capture_tool_evidence.py --print   # census to stdout, writes nothing
```

## Why there is no timestamp in either file

Deliberate, and it is the property everything else here rests on. Both documents are a
**pure function of the source tree**, so `--check` is a real test: byte-identical output
means the committed evidence still describes the committed code, and one differing byte
means `docs/TOOL-USAGE.md` is quoting a number that no longer holds. A `generated_at`
field would make every run differ from every other and would quietly destroy that. When
these bytes changed, and who changed them, is a question `git log` answers better than a
string the program writes about itself.

**Caveat, stated because it will bite someone.** While other work is landing in the tree,
`--check` can go red for a reason that is not a defect: a file appeared or disappeared
between the write and the check. That is the mode working. Re-run the write, and read the
diff — it names the row and the count that moved.

## How to read a row

```jsonc
{
  "key": "crdb_vector_index",
  "name": "C-SPANN vector index (VECTOR INDEX, prefix-constrained ANN)",
  "kind": "feature",                       // tool | feature | service
  "verdict": "EXERCISED",                  // EXERCISED | DESIGNED | NOT-AVAILABLE
  "verdict_basis": "…",                    // WHY that verdict, naming the artefact
  "how": "…",                              // the mechanism, not the feature name
  "anchor": "…/0031_clause_embedding.sql:149",
  "anchor_resolved": { "resolves": true, "line_text": "VECTOR INDEX ce_ann (…)" },
  "file_count": 115,
  "files_by_category": { "migration": 41, "python": 30, … },
  "representative_paths": [ … 3 paths … ],
  "search": { "pattern": "VECTOR INDEX|vector_index|…", "case_sensitive": false }
}
```

### The three verdicts, and why the third one exists

| verdict | means |
|---|---|
| `EXERCISED` | it ran, and a committed artefact or a check in this repository records the result |
| `DESIGNED` | the code or configuration is complete and on disk; nothing recorded has run it end to end |
| `NOT-AVAILABLE` | checked on this platform and absent; no dependency was taken on it |

A services list that quietly omits what you checked for and could not have is a list
nobody can audit. `NOT-AVAILABLE` is there so Bedrock Rerank appears in
`aws-services.json` as a row with a reason, rather than as a silence.

On `aws-services.json`, `DESIGNED` dominates and that is the honest answer: most of this
infrastructure is written and unapplied. See
[`docs/HONESTY.md`](../../docs/HONESTY.md) — the S3 object-lock comparison is one of the
seven cryptographic checks in the custody bundle that **did not run**.

### `file_count` counts mentions, not only uses

It is the number of scanned files whose text matches `search.pattern` — which counts
where a feature is *used* and where it is *discussed*. That is why every row also carries
an `anchor`: one hand-checked file and line where the thing actually happens, with the
line's text quoted into `anchor_resolved.line_text` so a later reorganisation that moves
the code shows up as a diff instead of leaving a confidently wrong citation behind. The
census **refuses to write** (exit 2) if any anchor no longer resolves.

`search.pattern` is published verbatim so the count is reproducible with any tool. Two
patterns are narrower than the obvious one, on purpose:

* `aws_bedrock_rerank` does **not** match a bare `/rerank/`, because that also matches
  CockroachDB's own `vector_search_rerank_multiplier` and every discussion of listwise
  reranking. A `NOT-AVAILABLE` row inflated by unrelated hits is exactly the number this
  census exists to prevent.
* `crdb_check_constraints` searches for the literal constraint name
  `gate_closed_when_issued` rather than the phrase "CHECK constraint", because the
  constraint *name* is the deliverable in this repository, not the keyword.

### The scan set, and why it will not match `git grep`

The census is a **filesystem walk**, not a pass over the git index, because a judge checks
out a working tree. The two disagree in both directions and the JSON says so in
`scan.method`:

* files present but not yet committed are counted here and not by `git grep`;
* files git tracks inside pruned directories (`out_mainline/`, `out_trappoint_ref/`,
  `.hypothesis-corpus/`) are counted by `git grep` and not here.

Measured once, on `2026-08-10`: `git grep -l gate_closed_when_issued` returned `134`
files while the census returned `152` — `22` present-but-uncommitted, `4`
tracked-but-pruned, and the two sets differ in both directions. Those exact figures move as
the tree does and are quoted as an illustration, not a claim; the *shape* of the
discrepancy is what to remember.

`scan.excluded_dir_names` and `scan.excluded_relpaths` are printed into both files. Three
of the exclusions are self-reference:

* `evidence/tool-usage/` — the census must not count its own output;
* `docs/TOOL-USAGE.md` — otherwise writing the document inflates the counts the document
  cites;
* `scripts/submission/capture_tool_evidence.py` — the search patterns are string literals
  inside it, so without this the program would count itself as a use of every feature it
  looks for.

A number that rises because you described it is not a measurement.

## What these files are not

They are a census of the **tree**, not of a cluster or an AWS account. `EXERCISED` points
at the artefact that did the running — usually
[`evidence/gate-refusal/`](../gate-refusal/) or `qa/test-state.json` — and the artefact,
not this file, is the evidence. Nothing here should ever be hand-edited; edit the row
definitions in `scripts/submission/capture_tool_evidence.py` and re-run.
