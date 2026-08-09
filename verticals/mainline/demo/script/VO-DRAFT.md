<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: FSL-1.1-ALv2 -->

# VO — draft, before the cut

This is the version read aloud against a stopwatch. It is kept so the cut is a
**visible diff** rather than a claim that a cut happened; `VO-CUT.diff` is the
unified diff between this file and `VO.md`, and its header carries the measured
reduction. `make_cut_diff.py` regenerates both numbers, so neither is typed.

Read at ~150 wpm this draft runs long against a 171-second cut with two silent
holds, which is exactly what a draft is for. The cut takes out qualifiers,
restatements of what the screen already shows, and every sentence that explains a
shot instead of letting it land.

[0:00] One number in a maintenance procedure. Nobody working at this site knows why it's 135.

[0:06] This week an engineer raised it to 150 — the manufacturer's number. Defensible. Documented. Approved.

[0:13] MAINLINE is institutional safety memory as a version-controlled repository, running on CockroachDB.

[0:18] Commits are written by incidents. Every clause carries a blame pointer to the event that wrote it.

[0:23] So before anything else, we ask the clause where it came from.

[0:33·hold] 2013. A gland seal fire. Two contractors burned. The alarm gave ninety seconds; 135 would have given six minutes. The author left in 2021.

[0:44] Retypeset in 2016, split into a new standard in 2019. The clause kept its identity, so the blame survived.

[0:51] Today's permit relies on that clause. The supervisor clicks merge and expects it to merge.

[0:58] Refused — not by a warning, not by a workflow rule. By a CHECK constraint: gate_closed_when_issued.

[1:05] Here is what matters. Cluster admin, raw SQL, our application bypassed entirely. The database still refuses.

[1:13] And the obligation itself is append-only. It cannot be deleted by anyone.

[1:18] An admin can drop the constraint. What they cannot do is drop it unobserved — the patrol writes it down.

[1:28] To proceed, someone puts their name to it. Accept the residual risk? There's no such verdict — and a foreign key says so.

[1:37] Severity four forces a compensating control and a second signature. We measure deliberation. We never accuse.

[1:45] Now it merges, carrying a signed record of what was known and who overrode it.

[1:50] Then the site register gains an activity. Nobody is touching the screen.

[1:55] He signed it away only while this stayed true.

[2:01] The permit suspends itself and forks a child permit.

[2:05] Now hand it to an auditor. CockroachDB's own managed MCP server — read-only, and not our code.

[2:13·hold] And because everyone asks whether the vector search is real — C-SPANN, on the named index.

[2:21] Then the question nobody else can answer: what did you not tell me?

[2:27] Single tenant by design. Row-level security. CockroachDB's audit log hashed into our ledger.

[2:32] Everything ran live: database in Singapore, inference in Sydney. The operator and incidents are synthetic.

[2:40] The honest limit: nothing here separates a considered disposition from a rubber stamp. So we measure it and log our silence.

[2:45] Repo, live demo, and a read-only endpoint for your own agent. Verify it yourself.
