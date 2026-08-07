<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: FSL-1.1-ALv2 -->

# Plan fixtures — what they are, and what they are not

These files are **hand-written from the documented `EXPLAIN` fragment**, not captured from a
live cluster. They exist to prove that the parser and the assertion in
`trappoint_recall.arms.explain` have teeth: the good fixtures must pass, and each bad fixture
must fail **for its own distinct reason**. That is a property of our code and needs no
database.

They are **not** evidence that CockroachDB produces this output. That claim is made only by
`test_ix02_plan_pgwire.py`, which EXPLAINs a real generated arm against a real cluster, and by
`test_ix03_plan_mcp.py`, which asserts the same thing over CockroachDB's own public endpoint.

When a live run happens, `test_ix02` writes the observed plan text to `captured/` (gitignored
by nothing — commit it if it is interesting) so the difference between what we imagined the
output looks like and what it actually looks like is visible rather than assumed.
