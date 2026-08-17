<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Link block — for the docs lead to paste

**This file is not for judges.** It is a handoff. The upstream-findings wave does not edit
`README.md`, `docs/submission/JUDGE-START.md`, or any other judge-facing document, because those
were being rewritten by other people in the same hour. Everything that wave needs those documents
to say is below, ready to paste.

Written 2026-08-17. Verified by
[`scripts/upstream/verify_field_notes.py`](../../scripts/upstream/verify_field_notes.py);
output at [`evidence/upstream/verification.json`](../../evidence/upstream/verification.json).

---

## ⚠ 1 · Two corrections that should land before anything else

These are not style notes. Two claims currently in judge-facing documents were **withdrawn** after
re-measurement, and one of them is contradicted by the very artefact it cites.

### 1a · The vector-index claim is struck

`README.md` line 220 and `docs/submission/readme-parts/05-findings.md` line 27 both carry this row:

> | the vector index is not chosen at demo scale | limit | At 5,200 rows, unless the index is named in the statement, the database scans and then filters. … |

**Delete the row.** It was re-measured twice and did not hold: at 0, 200, 1,100 and 5,300 rows the
query plan for the *unhinted* statement traverses the index. Worse, the row cites
`evidence/aws/ann/explain-unhinted.txt` as its proof, and a reader who opens that artefact finds
the plan that refutes the sentence pointing at it. Details and the plan output:
[`docs/upstream/STRIKE-LEDGER.md`](STRIKE-LEDGER.md) §2.

If a replacement row is wanted, this one is supported:

```markdown
| a struck claim, kept in the open | ours | We published that CockroachDB would not use our vector index unless we named it. We re-measured twice; both times it used the index unasked. The claim is withdrawn, and the withdrawal is written down rather than quietly deleted. | [`docs/upstream/STRIKE-LEDGER.md`](docs/upstream/STRIKE-LEDGER.md) §2 |
```

### 1b · The `has_function_privilege` claim is narrower than published

`README.md` line 217 (and the same row in `05-findings.md`) says the function answers `true`
*"for that login, for `root`, for `admin`, for `public`"* and that a check built on it **cannot
fail**. Measured properly, that is too broad: only the form that **names a role** is blind. The
form where a user asks about **itself** answers correctly. Suggested replacement for the
*"what we measured"* cell:

```markdown
On a throwaway database with `EXECUTE` revoked from everyone, calling the procedure was refused — `42501 … does not have EXECUTE privilege on procedure merge_permit`. Asked **about that user by name**, `has_function_privilege` still answered `true` — for that login, for `root`, for `admin`, for `public`. Asked by the user **about itself**, it answered `false`, correctly. So the blind form is the one a checking program has to use. `has_table_privilege` passed the identical control and tracked behaviour exactly.
```

Evidence: [`docs/upstream/findings/F01-has-function-privilege.md`](findings/F01-has-function-privilege.md).

---

## 2 · Paste into `README.md`

Drop this wherever the CockroachDB findings are discussed. It is self-contained.

```markdown
### Field notes we are sending to CockroachDB

We built on CockroachDB for several weeks and kept a list of the sharp edges we hit. Before
publishing it we re-ran every item from a cold shell and threw out the ones that did not hold up —
**six published, one struck, and six further sentences withdrawn from inside the six that
survived.**

- **[Field notes](docs/upstream/COCKROACHDB-FIELD-NOTES.md)** — the six, each with a program you
  can run, a version, and the hosting plan it was measured on.
- **[What worked](docs/upstream/WHAT-WORKED.md)** — the three platform features the product could
  not exist without, measured the same way. Read this first; a critique with no praise is a
  grievance.
- **[Strike ledger](docs/upstream/STRIKE-LEDGER.md)** — what we withdrew and what we saw instead.

To check all of it, including us:

    .venv/Scripts/python.exe scripts/upstream/verify_field_notes.py
```

---

## 3 · Paste into `docs/submission/JUDGE-START.md`

Shorter, for a reader who is triaging.

```markdown
**Upstream field notes.** Six measured findings about CockroachDB v26.2.5, one struck finding, and
three things that worked — each with a reproduction script and a transcript.
[`docs/upstream/COCKROACHDB-FIELD-NOTES.md`](../upstream/COCKROACHDB-FIELD-NOTES.md) is the front
door; [`docs/upstream/STRIKE-LEDGER.md`](../upstream/STRIKE-LEDGER.md) is the count of what we
could not demonstrate and threw out.
```

*(Check the relative depth of that path against wherever it is pasted — `JUDGE-START.md` lives in
`docs/submission/`, so `../upstream/…` is correct from there and `docs/upstream/…` is correct from
the repository root.)*

---

## 4 · One-liner, for a table of contents or an index page

```markdown
[Field notes for CockroachDB](docs/upstream/COCKROACHDB-FIELD-NOTES.md) — six measured findings, one struck, three things that worked, every one with a program that reproduces it.
```

---

## 5 · Every file this wave produced

| Path | What it is |
|---|---|
| [`docs/upstream/COCKROACHDB-FIELD-NOTES.md`](COCKROACHDB-FIELD-NOTES.md) | the front door — plain-language summary, then a table, then the links |
| [`docs/upstream/WHAT-WORKED.md`](WHAT-WORKED.md) | three things that carried the product, measured |
| [`docs/upstream/STRIKE-LEDGER.md`](STRIKE-LEDGER.md) | the struck finding and the withdrawn sentences |
| [`docs/upstream/findings/`](findings/) | one file per finding, F01–F07 |
| `scripts/upstream/repro_*.py` | four reproduction programs |
| [`scripts/upstream/verify_field_notes.py`](../../scripts/upstream/verify_field_notes.py) | the independent re-check that strikes findings |
| [`evidence/upstream/`](../../evidence/upstream/) | transcripts, one per finding, plus `verification.json` |

---

## 6 · Facts a judge-facing document may safely assert

Each of these is checkable in `evidence/upstream/verification.json`.

- Seven candidate findings; **six published, one struck**; six further sentences withdrawn from
  inside the survivors.
- All measurements on **CockroachDB CCL v26.2.5** (built 2026/07/28 18:56:00).
- Five findings carry `REPRODUCED-TODAY` (re-run 2026-08-17, local single-node); one carries
  `ARCHIVED-EVIDENCE`; F04 carries both, one per arm, labelled separately.
- The four reproduction programs were re-run from a cold shell and **all four exited 0**.
- The node held the **same number of databases after the verification as before it** — the wave
  left no scratch database and no role behind, which matters because F05 is a finding about
  orphaned scratch databases.
- **No CockroachDB Cloud cluster, no `mainline_demo` database, no AWS service and no credential
  was touched** by any program in this wave.

**Do not assert** that these findings have been sent to Cockroach Labs. They have not. This
document set is the thing we would send.
