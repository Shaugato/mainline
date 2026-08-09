# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 3r — the reflow injector: what the 2016 retypeset did, measured rather than asserted.

``injectors/retypeset.py`` emits the schedule the renderer needs — one row per clause with the
label and ordinal on both sides of the 2016 house change — and it stamps every row
``identity_held: true``.  That boolean is a constant the generator wrote.  In a repository whose
first principle is that **a projection is enforced, never trusted** (P2), a survival claim
carried by a field the claimant filled in is exactly the defect class the product exists to
punish: it looks right and it was never derived from anything.

This stage replaces that boolean with three things a reader can check:

1. **A re-derivation.**  Every pair's ``clause_uuid`` is recomputed from the clause's *birth*
   natural key — ``uuid5(CORPUS_NS, "clause:<site>/<doc>/<birth label>")`` — and compared.  A
   reflow record that minted a fresh identity on the generation-2 side fails here.
2. **A refutation.**  The same mint is applied to the clause's **post-reflow printed label**.
   Where the label moved, that value must *not* equal the clause's identity.  This is the
   falsifiable half: if identity were a function of the printed label, a retypeset would destroy
   it, and the corpus's whole claim would be circular.
3. **A scoreboard.**  Four registers are run over the reflow boundary — keyed on printed label,
   on ordinal, on control class, and on clause identity — and each is scored against the carried
   identity.  The measured result is the sentence beat 1 says out loud.

── WHAT IS MEASURED HERE AND WHAT IS NOT (§11.7 must-not-claim) ──────────────────────────────

The scoreboard measures **what a register keyed the wrong way loses when a document is
retypeset**.  It does not measure MAINLINE's clause linker, and the identity-keyed row scores
perfectly *by construction* — the corpus carries the identity, so a register keyed on it cannot
miss.  That row is a control, not evidence.  ``reflow_scoreboard.json`` carries this caveat in
its own payload, as a field, so a number lifted out of the file cannot travel without it.

── READ THE MODULES IN THIS ORDER ────────────────────────────────────────────────────────────

``params``     thresholds, the four register keys, and the caveat strings, in one place.
``measure``    label grammars, Kendall tau distance, footrule displacement.
``matchers``   a register keyed on one field, run over the reflow boundary, and scored.
``model``      the emitted shapes.
``verify``     fourteen checks, each capable of failing for a stated reason.
``nemesis``    five deliberate defects that must turn those checks red — PL-2, executable.
``build``      orchestration and emission.

``nemesis`` is not optional decoration.  ``verify.py`` and the generator it audits live in the
same package: fourteen green checks in that situation are a coincidence nobody has tested.  Every
build applies all five mutations and writes ``reflow_nemesis.json``; a mutation the checks fail to
refuse exits ``3``, which ranks above a failing check, because a failing check is the audit
working and a surviving mutation is the audit not working.

Nothing here calls a model, a clock, a network or a database.  The world is rebuilt in memory
from ``mainline_corpus.blame.build``; ``--answer-key`` cross-checks it against the committed
tree rather than reading from it, for the reason stage 1b gives: a stage that can only be
produced from another worker's output *directory* cannot demonstrate its own reproducibility.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
