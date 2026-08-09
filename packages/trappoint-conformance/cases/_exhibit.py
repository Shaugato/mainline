# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Recovering the exhibit for a ``P0001``, from a registry that cannot silently rot.

``spec/errors.md`` §3.1 fixes the exhibit for each code. For ``23514``/``23503``/``23505``
the driver reports ``diag.constraint_name`` and there is nothing to do. For ``P0001`` that
field is **empty by construction** — a deliberate ``RAISE`` has no constraint — and the
exhibit is instead *the fully-qualified name of the raising object*, "which the message
convention makes recoverable".

Recoverable is doing a lot of work in that sentence, so this module does the work.

**The registry is the mechanism.** :data:`SITES` declares, for every ``RAISE EXCEPTION`` in
both migration trees, which object raises it and the verbatim fragment of its message.
Resolution is a lookup, never a guess, and it refuses on ambiguity rather than picking.
``tests/test_raise_sites.py`` scans ``verticals/mainline/db/migrations`` and
``packages/trappoint-sql/refvertical/sql`` and fails if a registered pair is not in the
tree, or if a message in the tree is not in the registry. A registry that drifted from the
SQL would be worse than no registry: it would confer confidence on a stale mapping.

**Two disambiguators, both structural.**

``prefix``
    ``fn_refuse_mutation`` and ``fn_refusal_ledger_guard`` raise the byte-identical
    sentence *"this table is append-only; write a new row"*. They are told apart by the
    message prefix, which is the binding's (``MAINLINE:`` / ``TRAPPOINT_REF:``) for the
    rendered family and the substrate's (``TRAPPOINT:``) for the refusal ledger.

``relation``
    ``fn_permit_event_chain`` and ``fn_cr_event_chain`` are the same code rendered twice
    and their messages are identical in every byte. Nothing in the message can separate
    them, so the *case* supplies the relation it wrote to — which it knows, because it
    issued the statement — and the registry narrows on that. A case that omits the
    discriminator gets :class:`ExhibitUnresolved`, never an arbitrary winner.

**What is asserted, exactly.** The manifest names every ``P0001`` exhibit in MAINLINE's
namespace (``mainline.fn_permit_merge_gate``) for *every* profile, because the manifest is
one document and the schema is a property of the binding. :func:`normalise` therefore
asserts the **raising object** exactly and re-homes the schema prefix into the manifest's
namespace. Nothing is lost:
``tests/test_raise_sites.py::test_observed_schema_is_the_profile_schema``
asserts separately that the schema the database actually named is the profile's own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "BINDING_PREFIXES",
    "MANIFEST_NAMESPACE",
    "SITES",
    "ExhibitUnresolved",
    "RaiseSite",
    "normalise",
    "observed_schema",
    "resolve_object",
    "split_message",
]

# The namespace the manifest writes every P0001 exhibit in, whatever the profile.
MANIFEST_NAMESPACE = "mainline"

# A binding's own prefix. Rendered SQL carries the vertical's name; the substrate's own
# objects (the refusal ledger guard, explain_refusal) carry TRAPPOINT.
BINDING_PREFIXES = ("MAINLINE", "TRAPPOINT_REF")
SUBSTRATE_PREFIX = "TRAPPOINT"

# `merge refused by <schema>.<object>` — the merge gate and the two procedures name
# themselves in the message. Where this matches, the exhibit is reported rather than
# inferred, and `normalise` records that.
_SELF_NAMING = re.compile(r"merge refused by ([a-z0-9_]+)\.([a-z0-9_]+)")


class ExhibitUnresolved(Exception):
    """The raising object could not be determined from the message.

    A conformance failure, never a harness error: the database refused, the message was
    read, and the message did not identify a registered raise site. Either the SQL grew a
    ``RAISE`` nobody registered, or two sites collided and the case did not supply the
    discriminator that separates them.
    """


@dataclass(frozen=True, slots=True)
class RaiseSite:
    """One ``RAISE EXCEPTION`` in the migration tree, and the object that owns it."""

    obj: str
    """Local name of the raising function or procedure, without a schema."""

    prefix: str
    """``"binding"`` for MAINLINE / TRAPPOINT_REF, ``"substrate"`` for TRAPPOINT."""

    fragment: str
    """A verbatim substring of the message body, after the ``PREFIX: `` separator."""

    relation: str = ""
    """The relation whose trigger owns this site, where two sites share a message. Empty
    means the fragment alone identifies the object."""


# ─────────────────────────────────────────────────────────────────────────────
# THE REGISTRY. Grounded against both trees by tests/test_raise_sites.py.
# ─────────────────────────────────────────────────────────────────────────────

SITES: tuple[RaiseSite, ...] = (
    # ── projection band (0100-0109) ──────────────────────────────────────────
    RaiseSite("fn_check_project", "binding", "no blame closure for this clause version"),
    RaiseSite("fn_check_materialised", "binding", "no permit row for this blocking check"),
    RaiseSite("fn_check_materialised", "binding", "no change_request row for this blocking check"),
    RaiseSite("fn_check_materialised", "binding", "precursor arrived after issue"),
    RaiseSite("fn_check_materialised", "binding", "a blocking check names no gated subject"),
    RaiseSite("fn_disposition_project", "binding", "no such blocking check"),
    RaiseSite("fn_disposition_project", "binding", "blame closure absent"),
    RaiseSite("fn_disposition_project", "binding", "exposure receipt absent or expired"),
    RaiseSite("fn_disposition_project", "binding", "no competency record for this signer"),
    RaiseSite("fn_disposition_project", "binding", "no competency record for this countersigner"),
    RaiseSite(
        "fn_disposition_close", "binding", "a disposition names no gated subject — nothing to close"
    ),
    RaiseSite(
        "fn_disposition_retract_only",
        "binding",
        "dispositions are append-only except for a single retraction",
    ),
    RaiseSite(
        "fn_disposition_retract_only", "binding", "only retracted_by may change on a disposition"
    ),
    RaiseSite(
        "fn_disposition_retract_only",
        "binding",
        "a disposition names no gated subject — nothing to re-open",
    ),
    # The two event-chain functions are byte-identical. `relation` is the only separator.
    RaiseSite(
        "fn_permit_event_chain",
        "binding",
        "no predecessor event for the declared prev_seq",
        "permit_event",
    ),
    RaiseSite(
        "fn_permit_event_chain",
        "binding",
        "prev_digest does not match the predecessor chain digest",
        "permit_event",
    ),
    RaiseSite(
        "fn_cr_event_chain", "binding", "no predecessor event for the declared prev_seq", "cr_event"
    ),
    RaiseSite(
        "fn_cr_event_chain",
        "binding",
        "prev_digest does not match the predecessor chain digest",
        "cr_event",
    ),
    RaiseSite("fn_refuse_mutation", "binding", "this table is append-only; write a new row"),
    RaiseSite(
        "fn_closure_guard",
        "binding",
        "the first closure generation for a clause version must be zero",
    ),
    RaiseSite("fn_closure_guard", "binding", "closure generations must be dense and monotone"),
    RaiseSite(
        "fn_closure_guard",
        "binding",
        "closure severity may not decrease without a signed severity revision",
    ),
    RaiseSite("fn_closure_guard", "binding", "no site row for this closure"),
    RaiseSite("fn_site_role", "binding", "no site row for this record"),
    # ── merge band (0115-0119). These name themselves; _SELF_NAMING gets them first. ──
    RaiseSite("fn_permit_merge_gate", "binding", "fn_permit_merge_gate"),
    RaiseSite("fn_cr_merge_gate", "binding", "fn_cr_merge_gate"),
    RaiseSite("merge_permit", "binding", "merge refused by mainline.merge_permit"),
    RaiseSite("merge_permit", "binding", "merge refused by trappoint_ref.merge_permit"),
    RaiseSite("merge_change_request", "binding", "merge refused by mainline.merge_change_request"),
    RaiseSite(
        "merge_change_request", "binding", "merge refused by trappoint_ref.merge_change_request"
    ),
    # ── the substrate's own objects (TRAPPOINT prefix) ───────────────────────
    RaiseSite("fn_refusal_ledger_guard", "substrate", "this table is append-only; write a new row"),
    RaiseSite("fn_refusal_ledger_guard", "substrate", "the reason set is not an array"),
    RaiseSite("fn_refusal_ledger_guard", "substrate", "the reason set is empty"),
    RaiseSite(
        "fn_refusal_ledger_guard", "substrate", "a reason-set atom names no modelled fact family"
    ),
    RaiseSite(
        "fn_refusal_ledger_guard",
        "substrate",
        "a reason-set atom carries a key outside the closed vocabulary",
    ),
    RaiseSite("explain_refusal", "substrate", "a refusal with no exhibit is not evidence"),
    RaiseSite("explain_refusal", "substrate", "a refusal with no subject cannot be diagnosed"),
    RaiseSite("explain_refusal", "substrate", "no such subject — a refusal cannot be diagnosed"),
    RaiseSite(
        "explain_refusal",
        "substrate",
        "projected counter disagrees with the re-derived witness set",
    ),
    RaiseSite("explain_refusal", "substrate", "the projected counter is zero"),
    # ── MAINLINE-only guards (vertical bands 0110-0114, 0140-0146) ───────────
    RaiseSite(
        "fn_candidate_project", "binding", "no such event — a recall candidate cannot be typed"
    ),
    RaiseSite("fn_recall_policy_anchored", "binding", "recall policy is not anchored"),
    RaiseSite(
        "fn_recall_policy_anchored",
        "binding",
        "recall policy anchor is not inside a cosigned checkpoint",
    ),
    RaiseSite(
        "fn_cue_prefix_project",
        "binding",
        "no parent cue — cannot place a vector in a prefix tree",
        "event_cue_embedding",
    ),
    RaiseSite(
        "fn_cue_coarse_project",
        "binding",
        "no parent cue — cannot place a vector in a prefix tree",
        "event_cue_coarse",
    ),
    RaiseSite(
        "fn_delta_witness_guard",
        "binding",
        "a lattice weakening must carry its minimal witness set",
    ),
    RaiseSite(
        "fn_delta_witness_guard",
        "binding",
        "a lattice weakening carries witnesses but none is minimal",
    ),
    RaiseSite(
        "fn_cbm_account_guard", "binding", "cbm account generations must be dense and monotone"
    ),
    RaiseSite(
        "fn_cbm_account_guard", "binding", "cbm account refused — blame closure not materialised"
    ),
    RaiseSite(
        "fn_cbm_account_guard",
        "binding",
        "cbm account refused — the commit it accounts for does not exist",
    ),
    RaiseSite("fn_clause_version_guard", "binding", "blame ancestry never shrinks"),
    RaiseSite(
        "fn_clause_version_guard",
        "binding",
        "a clause version may not declare itself its own parent",
    ),
    RaiseSite("fn_clause_version_guard", "binding", "blood_root changed while blood_size did not"),
    RaiseSite("fn_clause_version_guard", "binding", "the parent clause version is not readable"),
    # The CBM (commit-blame-material) accounting guards. `merge refused — …` here does NOT
    # match _SELF_NAMING, which requires the schema-qualified form `merge refused by
    # <schema>.<object>`; the em-dash spelling is a different sentence and is resolved by
    # fragment plus relation, exactly as the event-chain pair is.
    RaiseSite("fn_residue_project", "binding", "residue refused — the commit has no first parent"),
    RaiseSite(
        "fn_residue_project",
        "binding",
        "residue refused — no blame closure for the ancestor clause",
    ),
    RaiseSite(
        "fn_cbm_gate_permit",
        "binding",
        "merge refused — blame accounting absent for a cited commit",
        "permit",
    ),
    RaiseSite(
        "fn_cbm_gate_permit",
        "binding",
        "merge refused — blame accounting is stale for a cited commit",
        "permit",
    ),
    RaiseSite(
        "fn_cbm_gate_cr",
        "binding",
        "merge refused — blame accounting absent for a cited commit",
        "change_request",
    ),
    RaiseSite(
        "fn_cbm_gate_cr",
        "binding",
        "merge refused — blame accounting is stale for a cited commit",
        "change_request",
    ),
)


def split_message(message: str) -> tuple[str, str]:
    """Split ``PREFIX: body`` into its two halves.

    Returns ``("", message)`` when the convention was not followed, which is itself a
    finding: ``spec/errors.md`` §3.2 makes the prefix mandatory, so a message without one
    resolves to no object and the case fails naming the message.
    """
    head, sep, tail = message.strip().partition(":")
    head = head.strip()
    if not sep:
        return "", message.strip()
    if head in BINDING_PREFIXES or head == SUBSTRATE_PREFIX:
        return head, tail.strip()
    return "", message.strip()


def _family(prefix: str) -> str:
    if prefix in BINDING_PREFIXES:
        return "binding"
    if prefix == SUBSTRATE_PREFIX:
        return "substrate"
    return ""


def resolve_object(message: str, *, relation: str = "") -> tuple[str, bool]:
    """Return ``(local object name, self_named)`` for a ``P0001`` *message*.

    ``self_named`` is True when the message spelled the object out — the merge gate and
    the two merge procedures do — which makes the exhibit *reported* rather than inferred
    and is recorded as such.

    Raises:
        ExhibitUnresolved: the message matches no registered site, or matches sites owned
            by more than one object and *relation* did not separate them.
    """
    prefix, body = split_message(message)

    named = _SELF_NAMING.search(body)
    if named is not None:
        return named.group(2), True

    family = _family(prefix)
    if not family:
        raise ExhibitUnresolved(
            f"the message carries no recognised prefix, so no exhibit can be recovered: "
            f"{message!r}. spec/errors.md §3.2 requires '<PREFIX>: <one sentence>'."
        )

    hits = {
        site.obj
        for site in SITES
        if site.prefix == family
        and site.fragment in body
        and (not site.relation or not relation or site.relation == relation)
    }
    if relation:
        narrowed = {
            site.obj
            for site in SITES
            if site.prefix == family and site.fragment in body and site.relation == relation
        }
        if narrowed:
            hits = narrowed

    if len(hits) == 1:
        return hits.pop(), False
    if not hits:
        raise ExhibitUnresolved(
            f"no registered raise site matches {body!r}. Either the SQL grew a RAISE that "
            f"cases/_exhibit.py does not know about — tests/test_raise_sites.py is the "
            f"guard that should have caught it — or the message was edited without the "
            f"registry."
        )
    raise ExhibitUnresolved(
        f"{body!r} is raised by more than one object ({', '.join(sorted(hits))}) and the "
        f"case supplied relation={relation!r}, which does not separate them. The corpus "
        f"refuses to pick: an exhibit chosen by tie-break is not an exhibit."
    )


def observed_schema(message: str) -> str:
    """Return the schema the database itself named, where the message named one.

    Empty when the message did not spell out a qualified object. Used by
    ``tests/test_raise_sites.py`` to assert the profile's schema separately, so that
    re-homing the prefix in :func:`normalise` gives nothing away.
    """
    named = _SELF_NAMING.search(message)
    return named.group(1) if named is not None else ""


def normalise(outcome: object, *, relation: str = "") -> None:
    """Fill in the exhibit on a ``P0001`` outcome, in place.

    *outcome* is a :class:`trappoint_conformance.harness.HistoryOutcome`; it is typed
    loosely here so this module stays importable without the driver. Non-``P0001``
    outcomes are left exactly as the driver reported them — for those codes the driver
    *does* supply the constraint name and inventing one would be a forgery.

    On failure the exhibit becomes a sentence beginning ``EXHIBIT UNRESOLVED``, which
    cannot equal any manifest value, so the case goes red carrying its own diagnosis
    rather than raising through the runner.
    """
    sqlstate = getattr(outcome, "sqlstate", "")
    if sqlstate != "P0001":
        return
    message = getattr(outcome, "message", "") or ""
    try:
        obj, self_named = resolve_object(message, relation=relation)
    except ExhibitUnresolved as exc:
        outcome.constraint = f"EXHIBIT UNRESOLVED — {exc}"  # type: ignore[attr-defined]
        outcome.exhibit_weakened = True  # type: ignore[attr-defined]
        return
    outcome.constraint = f"{MANIFEST_NAMESPACE}.{obj}"  # type: ignore[attr-defined]
    # Reported by the object naming itself; inferred where the registry supplied it.
    outcome.exhibit_weakened = not self_named  # type: ignore[attr-defined]
