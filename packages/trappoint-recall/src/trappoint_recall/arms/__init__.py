# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Channel C: prefix-constrained ANN arms, and the proof that the index was used.

**The claim this package exists to make good on: the archival taxonomy IS the vector-index
prefix.** A C-SPANN index maintains a separate K-means tree per distinct prefix value, so
``(site, archival scope, facet)`` does not filter a result set — it *selects the tree that is
searched*. Writing one cue row per archival level (fonds, series, file) therefore turns "one
constrained arm per ancestor" from a slogan into a physical necessity: the levels are
different trees, graded in size, and the matching level becomes a retrieval feature rather
than a post-hoc score adjustment. Without that, an ancestor walk over a single inherited
prefix collapses to one arm and there is no diachronic recall — only similarity search with
extra steps.

Two facts about CockroachDB shape everything here:

* **A vector index is used only if EACH prefix column is constrained to a specific value.**
  ``WHERE a = 1 AND b >= 2`` does not use it. Not "uses it less well" — does not use it.
* **``optimizer_span_limit`` is a silent cliff.** Past it, an ``IN`` set stops being used to
  build a constrained scan, with no error. Which is why the arm set is bounded, why overflow
  is a logged record rather than a truncation, and why the tuple-``IN`` form is generated
  for nightly characterisation but never shipped.

Three layers of proof, and no layer substitutes for another:

1. **plan** — ``EXPLAIN`` shows ``vector search``, the expected ``table@index``, a non-empty
   ``prefix spans``, and no ``FULL SCAN``, asserted over pgwire *and* over the public Managed
   MCP ``explain_query`` path, so the claim is proven on CockroachDB's own endpoint rather
   than on ours;
2. **behaviour** — per-arm p50 latency across a doubling corpus stays under ``t(2n)/t(n) <
   1.7``, and a planted precursor comes back in top-k, because a silently unused index scales
   linearly however the plan text is formatted;
3. **characterisation** — the not-shipped tuple-``IN`` form, nightly, at span counts either
   side of the runtime value of ``optimizer_span_limit``, against brute force. It is expected
   to change across versions. That is its purpose.

This package holds **no database driver**. Every path that touches a cluster takes a callable
executor, which is what lets the same assertions run over pgwire, over a public tool endpoint
and over a recorded fixture without a second implementation to keep honest.
"""

from __future__ import annotations

from .binding import InvalidBinding, VectorTable
from .digest import PLAN_DIGEST_DOMAIN, index_plan_digest, plan_skeleton, skeleton_text
from .explain import (
    ExplainPlan,
    ExplainSource,
    PlanAssertion,
    PlanNode,
    UnionPlanAssertion,
    assert_arm_plan,
    assert_arm_set_plan,
    parse_explain,
)
from .generate import SweepRequest, generate_arm_set, generate_arms
from .mcp import (
    MCP_MAX_RESPONSE_BYTES,
    MCP_MAX_STATEMENT_CHARS,
    MCP_SELECT_ROW_CAP,
    MCP_TIMEOUT_SECONDS,
    EnvelopeCheck,
    check_envelope,
)
from .measure import (
    DEFAULT_SUBLINEARITY_LIMIT,
    DoublingRatio,
    IngestCurve,
    IngestSample,
    KneeEstimate,
    SublinearityVerdict,
    degradation_knee,
    sublinearity_verdict,
)
from .policy import ArmPolicy, InvalidArmPolicy
from .spec import (
    AncestorChain,
    ArmCapExceeded,
    ArmKind,
    ArmSet,
    ArmSpec,
    DroppedArm,
    PrefixBinding,
    ScopeRef,
    SqlForm,
)
from .sql import (
    PlaceholderStyle,
    RenderedSql,
    arm_sql,
    explain_sql,
    explain_union_sql,
    render_vector_literal,
    union_all_sql,
)

__all__ = [
    "DEFAULT_SUBLINEARITY_LIMIT",
    "MCP_MAX_RESPONSE_BYTES",
    "MCP_MAX_STATEMENT_CHARS",
    "MCP_SELECT_ROW_CAP",
    "MCP_TIMEOUT_SECONDS",
    "PLAN_DIGEST_DOMAIN",
    "AncestorChain",
    "ArmCapExceeded",
    "ArmKind",
    "ArmPolicy",
    "ArmSet",
    "ArmSpec",
    "DoublingRatio",
    "DroppedArm",
    "EnvelopeCheck",
    "ExplainPlan",
    "ExplainSource",
    "IngestCurve",
    "IngestSample",
    "InvalidArmPolicy",
    "InvalidBinding",
    "KneeEstimate",
    "PlaceholderStyle",
    "PlanAssertion",
    "PlanNode",
    "PrefixBinding",
    "RenderedSql",
    "ScopeRef",
    "SqlForm",
    "SublinearityVerdict",
    "SweepRequest",
    "UnionPlanAssertion",
    "VectorTable",
    "arm_sql",
    "assert_arm_plan",
    "assert_arm_set_plan",
    "check_envelope",
    "degradation_knee",
    "explain_sql",
    "explain_union_sql",
    "generate_arm_set",
    "generate_arms",
    "index_plan_digest",
    "parse_explain",
    "plan_skeleton",
    "render_vector_literal",
    "skeleton_text",
    "sublinearity_verdict",
    "union_all_sql",
]
