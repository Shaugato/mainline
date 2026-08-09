# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``mainline-cartographer`` — the blame resolver.

MAINLINE's product sentence is that **every clause of a procedure, setpoint or critical
control carries a blame pointer to the incident that wrote it.** This package is the two
halves of that pointer:

* :mod:`mainline_cartographer.resolve` — **following** a pointer. Deterministic, no
  model, no driver. It is handed the projected closure row and the ancestor events and
  it returns the ancestry, or it refuses. Four refusals, each one a nameable failure: no
  closure row, an ancestor that does not resolve, a projection below an observed
  severity, and an inferred edge that got somewhere it may not go.
* :mod:`mainline_cartographer.propose` / :mod:`mainline_cartographer.verify` —
  **proposing** a pointer that is not yet recorded. One zero-tool, schema-constrained
  Bedrock call (§8.4 row 2, the Cartographer), followed by a deterministic verifier that
  binds every quote by exact search into the source text and discards anything that does
  not bind.

Read these four sentences before using it:

1. *An inferred link is a claim about the past.* Every edge this package builds carries
   ``basis='inferred_semantic'`` and ``state='provisional'``, and the type
   :class:`~mainline_cartographer.types.ProvisionalBlameEdge` cannot be constructed with
   any other pair. Making an inferred link block a permit would convert every model
   error into a rubber stamp.
2. *We compute the offsets; we never trust a model-reported offset.* The model copies a
   span; :func:`~mainline_cartographer.verify.bind_quote` finds it, exactly and uniquely,
   or the link is dropped with a named reason.
3. *A refusal is not an empty result.* ``ModelRefused`` propagates; the caller writes a
   ``silence_ledger`` row with ``source='blame_lapse'``. A precursor the model declined
   to reason about must still block the merge.
4. *Nothing here holds a driver or a credential.* :mod:`mainline_cartographer.emit`
   returns statements and parameters. The caller holds the SQL role.

And one thing this package does **not** claim: it does not band. ``max_severity`` and
``virulence`` are projections written by the Projector from ``clause_blame_closure``;
this package reads them verbatim and refuses when they contradict the ancestry in the
unsafe direction. A second banding implementation would be a second answer to a question
that must have exactly one.
"""

from __future__ import annotations

from .emit import (
    CLAUSE_BLAME_CLOSURE_SQL,
    CLAUSE_BLAME_EDGES_SQL,
    INSERT_BLAME_EDGE_SQL,
    ancestor_events_sql,
    insert_blame_edge,
)
from .errors import (
    AncestryUnresolvable,
    BlameClosureAbsent,
    CartographerError,
    ClosureInconsistent,
    ClosureMismatch,
    FloatInEvidentiaryPayload,
    InferenceActivated,
    QuoteAmbiguous,
    QuoteUnbound,
    StaleClosure,
)
from .profile import BLAME_LINK, BlameLinkProposal, ProposedLink
from .propose import (
    BLAME_SILENCE_SOURCE,
    blame_silence_row,
    compose_untrusted,
    mint_candidates,
    propose_and_verify,
    propose_blame_links,
    trusted_context_for,
)
from .resolve import order_ancestry, resolve_blame_pointer
from .types import (
    EVENT_KINDS,
    MAX_SEVERITY,
    MIN_SEVERITY,
    SEVERITY_BASES,
    BlameBasis,
    BlameEdgeRow,
    BlameState,
    ClauseCandidate,
    ClosureRow,
    EventRow,
    ProvisionalBlameEdge,
    ResolvedBlame,
    VirulenceClass,
    assert_float_free,
)
from .verify import (
    CONFIDENCE_P_LINK_MILLI,
    DROP_REASONS,
    DroppedLink,
    VerifiedBlame,
    attribution_for,
    bind_quote,
    verify_links,
)

__version__ = "0.1.0"

__all__ = [
    "BLAME_LINK",
    "BLAME_SILENCE_SOURCE",
    "CLAUSE_BLAME_CLOSURE_SQL",
    "CLAUSE_BLAME_EDGES_SQL",
    "CONFIDENCE_P_LINK_MILLI",
    "DROP_REASONS",
    "EVENT_KINDS",
    "INSERT_BLAME_EDGE_SQL",
    "MAX_SEVERITY",
    "MIN_SEVERITY",
    "SEVERITY_BASES",
    "AncestryUnresolvable",
    "BlameBasis",
    "BlameClosureAbsent",
    "BlameEdgeRow",
    "BlameLinkProposal",
    "BlameState",
    "CartographerError",
    "ClauseCandidate",
    "ClosureInconsistent",
    "ClosureMismatch",
    "ClosureRow",
    "DroppedLink",
    "EventRow",
    "FloatInEvidentiaryPayload",
    "InferenceActivated",
    "ProposedLink",
    "ProvisionalBlameEdge",
    "QuoteAmbiguous",
    "QuoteUnbound",
    "ResolvedBlame",
    "StaleClosure",
    "VerifiedBlame",
    "VirulenceClass",
    "__version__",
    "ancestor_events_sql",
    "assert_float_free",
    "attribution_for",
    "bind_quote",
    "blame_silence_row",
    "compose_untrusted",
    "insert_blame_edge",
    "mint_candidates",
    "order_ancestry",
    "propose_and_verify",
    "propose_blame_links",
    "resolve_blame_pointer",
    "trusted_context_for",
    "verify_links",
]
