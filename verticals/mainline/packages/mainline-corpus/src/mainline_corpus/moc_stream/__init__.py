# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1c — the MOC stream's declared scope and its lifecycle.

Stage 1 emitted the change register: three hundred and forty entries with sites, dates, intents
and terminal states.  Stage 1b authored causality over clause revisions.  Between them they left
one relation unwritten, and it is the one the change-request half of the gate reads.

``mainline.cr_clause`` is *what a change request declares it changes*.  Without it,
``open_blocking`` counts nothing, the MOC Ancestry Audit walks nothing, and finding S16 — the
repository is the protected branch and the permit is one of its refs — has no enforcement surface
on the document side.  Before this stage, two anchored spine revisions were the only place in the
corpus where a clause change pointed at a change record.

Read the modules in this order:

``params``      the windows, weights and the transition paths, in one place.
``model``       the emitted shapes, and the two columns only the database may fill.
``scope``       five bases for a declaration, four of them read rather than drawn.
``lifecycle``   the ordered acts — a PLAN, deliberately not a chain of ``cr_event`` rows.
``dossier``     one row per change request, including what the gate should refuse.
``verify``      every check the database would eventually run, run here first.
``build``       orchestration and emission.

── THE TWO REFUSALS THIS STAGE MAKES OF ITSELF ──────────────────────────────────────────────────
**It does not mint commits.** ``cr_clause`` pins a clause *version*, so its foreign key needs a
``commit_id`` that is sha256 over a JCS envelope. That is emitted null and registered pending
with the natural key of the revision whose commit closes it.

**It does not mint the event chain.** ``cr_event.chain_digest`` is computed by the server and
``fn_cr_event_chain`` verifies every ``prev_digest`` against the stored predecessor. A corpus
that authored those bytes would either be refused or — worse — would have reimplemented the
server's JSONB normaliser and made the digest chain stop proving that the server saw the payload
it hashed. So the output is ``cr_transition_plan.jsonl``, an ordered plan of acts with
``execute_via`` naming the surface each must be performed through, and the chain is minted in the
only place it can honestly be minted.

Nothing here calls a model, a clock, a network or a database.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
