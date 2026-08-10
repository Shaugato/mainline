<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# QUICKSTART

Four commands. No account, no credential, no network after one image pull.

```bash
just doctor     # what is missing, and the exact command that fixes it
just setup      # installs uv if absent, then `uv sync --all-packages`
just up         # one CockroachDB node, pinned, aligned with Cloud's gc.ttlseconds
just prove      # the database refuses a permit merge, and says why
```

`just doctor` runs before anything is installed, so run it first and run it again
whenever something surprises you. If `just` itself is one of the missing things, the
doctor is a plain script and needs nothing:

```bash
python scripts/qa/doctor.py
```

It prints one table and, when a row says `FAIL`, a numbered remedy under it. It exits
`0` only when everything `just prove` depends on is present.

## What `just prove` prints

The migration chain, then three attempts at the same merge — refused, refused for a
second and different reason, admitted — and a verdict. Exit `0` means proven; exit `1`
means **not** proven and the evidence JSON under `evidence/gate-refusal/` says which
half failed. Publish either one.

```
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
VERDICT       PROVEN
```

The third line is not decoration. A gate that always refuses is a broken gate, not a
safe one.

## The rest

```bash
just --list          # every recipe, with what it does
just test            # the hermetic suite: no cluster, no credential, no network
just test-cluster    # the same suite with the cluster tests live, on the ONE node
just console         # the TypeScript console's own gate
just nuke            # stop the cluster and destroy its data, for a clean run
```
