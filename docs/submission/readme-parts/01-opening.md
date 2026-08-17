**Read the story below knowing it is invented.** Kestrel Resources is fictional, Marrindal is
fictional, `INC-2013-044` never happened. The mechanism is real; the inputs are authored.[^src-fiction]

In 2011 a gas plant sets the alarm on a compressor seal to 150 °C. On 2013-06-12 that seal catches
fire and two contractors are burned. On 2013-08-04 an engineer lowers the alarm to 135 °C. The
revision history carries one line: *"Lowered 150 → 135 after seal fire INC-2013-044 — two contractors
burned."*[^src-story]

Then ordinary things happen to the clause. In 2016 it is retypeset and renumbered from 7.3 to 5.2.1.
In 2019 it moves into a different standard and becomes 9.2.1. In 2021 the engineer leaves the company.

Today someone proposes putting the alarm back to 150 °C. They are not careless. The manufacturer
specifies 150, and the alarm trips on hot afternoons. The clause on their screen reads *"shall be set
at 135 °C"* and gives no reason. The fire is two documents and three clause numbers away, written by
somebody who no longer works there.

**Every permit-to-work system on the market approves that change.** Each checks the world as it is
now — isolation in place, gas test valid, signature present. None can answer *why is this limit
here*. The answer existed and somebody wrote it down. Nothing carried it to the person who needed it.

## What this is

MAINLINE holds a site's safety memory underneath the systems that site already uses. Every clause of a procedure
carries a pointer to the event that caused it to be written. We call that pointer **blame** — who wrote this line, and why.

A permit to work is then handled like a change to code, and issuing it is a merge. Before that merge lands, the
database looks up what wrote each clause the permit leans on. Any earlier event nobody has answered for becomes an
**obligation** — one open question attached to that permit. While an obligation is open, the permit cannot be issued.
A named competent person has to record a **disposition** first: a signed answer to that one question.

The load-bearing word is *cannot*. This is not a banner somebody dismisses, and not a check in application code that
a second program could skip. It is a rule held inside CockroachDB, applied to every writer including ours. Switch
the user interface off and the permit still will not issue.[^src-gate]

**The reminder is not shown beside the decision. It is a precondition of the decision.**

Two pages belong before the rest of this one. [`docs/HONESTY.md`](docs/HONESTY.md) sets out what is proven, what is
authored and what is not built; [`docs/submission/MUST-NOT-CLAIM.md`](docs/submission/MUST-NOT-CLAIM.md) lists the
flattering sentences this project is not entitled to say, beside the true ones.

<!-- FOOTNOTES FOR W7: move these three definitions into the layer-1 footnote block at the end of section C. Do not renumber the labels; the references above use them verbatim. -->

[^src-fiction]: This is `docs/submission/MUST-NOT-CLAIM.md` §3 in that section's own wording.
[^src-story]: Every date, label and setpoint above is transcribed from `verticals/mainline/fixtures/corpus/answer-key/spine.json` — `dates`, `revisions` and `proposed_2026`. The quoted revision-history line is `commit_message_2013` in `verticals/mainline/demo/script/CAMERA-STRINGS.yaml`, asserted byte-equal across four files by `tests/unit/corpus`.
[^src-gate]: `scripts/proof/gate_refusal.py` attempts the merge over SQL with no console and no application in the path, and records the refusal `23514 gate_closed_when_issued` [src: evidence/gate-refusal/proof-20260810T054407Z.json]. What that run does and does not entitle us to say is in the sections below.
