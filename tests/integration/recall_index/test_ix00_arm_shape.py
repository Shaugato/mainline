# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""IX-00 — the arm set's shape, asserted without a cluster.

This module answers the first half of the worker's completion test literally: *for a level-3
ancestor chain with four populated facets the generator emits ≤16 fully-literal-bound arms
plus the coarse sweep*. It also holds the assertions that keep the Managed-MCP claim honest —
the statement-length arithmetic — because those are properties of the generated text and need
no database to check.

Nothing here touches a cluster, so nothing here is ever skipped. That matters: it means the
part of the proof that is about *our* generator is always green or always red, and only the
part that is about *CockroachDB* depends on there being a CockroachDB.
"""

from __future__ import annotations

import re
import uuid

import pytest
from _support import CUE_SCOPED, CUE_SWEEP, FACETS, POPULATED_FACETS, policy, unit_vector
from trappoint_recall.arms import (
    MCP_MAX_STATEMENT_CHARS,
    AncestorChain,
    ArmKind,
    ArmPolicy,
    PlaceholderStyle,
    ScopeRef,
    SqlForm,
    SweepRequest,
    arm_sql,
    check_envelope,
    explain_sql,
    explain_union_sql,
    generate_arm_set,
    generate_arms,
    union_all_sql,
)
from trappoint_recall.arms.spec import ArmSet

pytestmark = pytest.mark.shape

SITE = uuid.UUID("11111111-1111-4111-8111-111111111111")
TENANT = uuid.UUID("22222222-2222-4222-8222-222222222222")


def _chain(name: str = "act-1") -> AncestorChain:
    return AncestorChain.of(
        name,
        {
            3: uuid.uuid5(uuid.NAMESPACE_URL, f"{name}/file"),
            2: uuid.uuid5(uuid.NAMESPACE_URL, f"{name}/series"),
            1: uuid.uuid5(uuid.NAMESPACE_URL, f"{name}/fonds"),
        },
    )


def _facet_vectors(facets=POPULATED_FACETS) -> dict[str, list[float]]:
    return {facet: unit_vector(1024, f"query/{facet}") for facet in facets}


def _sweep() -> SweepRequest:
    return SweepRequest(
        tenant=TENANT, query_vector=unit_vector(256, "query/coarse"), table=CUE_SWEEP
    )


def _arm_set(**kwargs) -> ArmSet:
    return generate_arms(
        site=SITE,
        chain=kwargs.pop("chain", _chain()),
        facet_vectors=kwargs.pop("facet_vectors", _facet_vectors()),
        policy=kwargs.pop("policy", policy()),
        scoped_table=CUE_SCOPED,
        sweep=kwargs.pop("sweep", _sweep()),
        **kwargs,
    )


# ── the completion test, stated literally ────────────────────────────────────────────────


def test_ix00_level3_chain_four_facets_emits_twelve_arms_plus_the_sweep() -> None:
    arm_set = _arm_set()
    assert len(arm_set.scoped) == 12, (
        "three archival levels × four populated facets is twelve constrained arms; "
        f"got {len(arm_set.scoped)}"
    )
    assert len(arm_set.scoped) <= policy().max_arms
    assert arm_set.sweep is not None, "the coarse sweep is the insurance against the taxonomy"
    assert arm_set.sweep.kind is ArmKind.COARSE
    assert len(arm_set) == 13
    assert not arm_set.degraded


def test_ix00_every_scoped_arm_binds_all_three_prefix_columns_to_a_literal() -> None:
    """The documented condition for the index to be used, asserted on the emitted SQL text.

    Not on the spec object — on the *text*. A spec that binds three columns and renders two
    would satisfy an object-level assertion and still produce an unindexed query.
    """
    arm_set = _arm_set()
    for arm in arm_set.scoped:
        text = arm_sql(arm, form=SqlForm.LITERAL).text
        where = text.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
        for column in CUE_SCOPED.prefix_columns:
            pattern = rf"\be\.{column} = '[^']+'"
            assert re.search(pattern, where), (
                f"arm {arm.arm_id} does not constrain {column} to a literal value.\n{where}"
            )
        assert ">=" not in where and "<=" not in where and " IN " not in where, (
            "a vector index is used only if EACH prefix column is constrained to a SPECIFIC "
            f"value; arm {arm.arm_id} carries a range or a set:\n{where}"
        )


def test_ix00_arms_carry_graded_k_and_their_own_weight_and_vector() -> None:
    arm_set = _arm_set()
    by_level: dict[int, set[int]] = {}
    for arm in arm_set.scoped:
        by_level.setdefault(arm.level, set()).add(arm.k)
    assert by_level == {3: {12}, 2: {12}, 1: {8}}, (
        "k is graded by archival level — file 12, series 12, fonds 8 — because the trees are "
        f"graded by level. Got {by_level}"
    )
    file_rt = arm_set.by_id("act-1:L3:recurrence_test")
    fonds_narr_weight = policy().weight_for(1, "narrative")
    assert file_rt.weight > fonds_narr_weight, (
        "a file-level recurrence_test hit must outweigh a fonds-level narrative hit; that is "
        "arithmetic, not a preference"
    )
    vectors = {arm.facet: arm.query_vector for arm in arm_set.scoped}
    assert len(set(vectors.values())) == len(POPULATED_FACETS), (
        "each arm must carry its own facet-specific query vector"
    )


def test_ix00_the_sweep_binds_only_the_constant_tenant() -> None:
    arm_set = _arm_set()
    sweep = arm_set.sweep
    assert sweep is not None
    assert len(sweep.prefix) == 1
    assert sweep.prefix[0].column == "tenant_id"
    text = arm_sql(sweep, form=SqlForm.LITERAL).text
    where = text.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert where.count("=") == 1, f"the sweep must bind exactly one column:\n{where}"
    assert "scope_id" not in where and "e.facet" not in where, (
        "the sweep is deliberately ONE unpartitioned tree: a taxonomy constraint on it would "
        f"partition exactly the insurance that exists because the taxonomy may be wrong:\n{where}"
    )
    assert CUE_SWEEP.qualified_name in text


# ── the cap, and the record that must never be a silent drop ─────────────────────────────


def test_ix00_cap_bites_and_returns_a_record_naming_every_dropped_arm() -> None:
    chains = [_chain(f"act-{i}") for i in range(3)]
    arm_set = generate_arm_set(
        site=SITE,
        chains=chains,
        facet_vectors=_facet_vectors(),
        policy=policy(),
        scoped_table=CUE_SCOPED,
        sweep=_sweep(),
    )
    assert len(arm_set) == policy().max_arms
    assert arm_set.degraded
    overflow = arm_set.cap_exceeded
    assert overflow is not None
    assert overflow.reason == "cap_exceeded"
    assert overflow.requested == 3 * 3 * 4 + 1
    assert overflow.emitted == policy().max_arms
    assert len(overflow.dropped) == overflow.requested - overflow.emitted, (
        "every arm that was not emitted must appear in the record. An arm that is neither "
        "emitted nor recorded is a silently unsearched region of the corpus."
    )
    arithmetic = overflow.arithmetic()
    assert arithmetic["cap"] == policy().max_arms
    assert all(entry["scope_id"] for entry in arithmetic["dropped"])
    assert all(entry["arm_id"] for entry in arithmetic["dropped"])


def test_ix00_the_cap_never_drops_the_sweep() -> None:
    chains = [_chain(f"act-{i}") for i in range(6)]
    arm_set = generate_arm_set(
        site=SITE,
        chains=chains,
        facet_vectors=_facet_vectors(FACETS),
        policy=policy(),
        scoped_table=CUE_SCOPED,
        sweep=_sweep(),
    )
    assert arm_set.sweep is not None, (
        "the sweep covers the failure of every other arm; a cap that could delete it would "
        "delete the insurance first"
    )
    assert len(arm_set.scoped) == policy().max_arms - 1


def test_ix00_highest_weight_arms_survive_the_cap() -> None:
    chains = [_chain(f"act-{i}") for i in range(3)]
    arm_set = generate_arm_set(
        site=SITE,
        chains=chains,
        facet_vectors=_facet_vectors(),
        policy=policy(),
        scoped_table=CUE_SCOPED,
        sweep=_sweep(),
    )
    overflow = arm_set.cap_exceeded
    assert overflow is not None
    kept_min = min(arm.weight for arm in arm_set.scoped)
    dropped_max = max(entry.weight for entry in overflow.dropped)
    assert kept_min >= dropped_max, (
        "the cap must keep the arms the policy weighted highest; otherwise the operator's "
        "declared ranking and the system's behaviour disagree silently"
    )


def test_ix00_generation_is_deterministic() -> None:
    first = union_all_sql(_arm_set(), form=SqlForm.LITERAL).text
    second = union_all_sql(_arm_set(), form=SqlForm.LITERAL).text
    assert first == second, (
        "two runs of the same policy over the same inputs must emit byte-identical SQL; "
        "otherwise the plan digest compares nothing"
    )


# ── the Managed-MCP envelope, measured rather than assumed ───────────────────────────────


def test_ix00_single_arm_explain_fits_the_mcp_statement_cap_with_headroom() -> None:
    arm_set = _arm_set()
    worst = max(
        (explain_sql(arm, form=SqlForm.EXPLAIN_MCP) for arm in arm_set.arms),
        key=lambda r: r.char_count,
    )
    check = check_envelope(worst.text)
    assert check.ok, check.violations
    assert check.statements == 1, "the surface accepts exactly one statement per call"
    assert check.within_margin, (
        f"the longest arm EXPLAIN is {check.chars} characters, over the "
        f"{check.margin_limit}-character working margin. A limit tested at 100 % of capacity "
        "breaches in front of an audience the first time the corpus grows."
    )
    print(
        f"\n[ix00] longest arm EXPLAIN: {check.chars} chars "
        f"({check.utilisation:.0%} of {MCP_MAX_STATEMENT_CHARS}), "
        f"headroom {check.headroom_chars}"
    )


def test_ix00_the_duplicated_vector_form_would_breach_the_cap() -> None:
    """The measurement that justifies the EXPLAIN_MCP rendering existing at all.

    At 1024 dimensions the literal form prints the query vector twice — once projected as
    `dist`, once in the ORDER BY — and that statement does not fit the endpoint. This is not
    a hypothetical to be argued about in review; it is a number, and it is asserted here so
    that anyone who "simplifies" the two renderings back into one gets a red test explaining
    why they exist.
    """
    arm = _arm_set().scoped[0]
    literal = explain_sql(arm, form=SqlForm.LITERAL)
    assert literal.char_count > MCP_MAX_STATEMENT_CHARS
    assert not check_envelope(literal.text).ok
    compact = explain_sql(arm, form=SqlForm.EXPLAIN_MCP)
    assert compact.char_count < MCP_MAX_STATEMENT_CHARS
    assert compact.char_count < literal.char_count / 1.8


def test_ix00_the_union_plan_is_never_offered_to_the_capped_endpoint() -> None:
    """One arm per call over MCP; the whole plan over pgwire. Asserted, not documented."""
    arm_set = _arm_set()
    union = explain_union_sql(arm_set, form=SqlForm.LITERAL)
    assert not check_envelope(union.text).ok, (
        "if the whole arm set ever fits the MCP statement cap, the one-arm-per-call rule "
        "still holds for the RESPONSE cap — but this assertion is the tripwire that says "
        "the arithmetic changed and the reasoning must be redone"
    )


def test_ix00_execute_form_uses_placeholders_and_stays_small() -> None:
    arm = _arm_set().scoped[0]
    rendered = arm_sql(arm, form=SqlForm.EXECUTE, placeholder_index=7)
    assert "$7::VECTOR(1024)" in rendered.text
    assert len(rendered.params) == 1
    assert rendered.params[0].startswith("[")
    assert rendered.char_count < 1000, (
        "the hot path must not send ten kilobytes of vector literal per arm per permit"
    )


def test_ix00_union_placeholders_are_numbered_in_emission_order() -> None:
    """One numbered parameter per arm, referenced twice, numbered in emission order.

    The vector appears twice in every executed arm — projected as `dist` and again in the
    ORDER BY — so a numbered placeholder is one parameter used twice while a pyformat
    placeholder is two parameters. Both arities are asserted, because the pyformat mistake
    surfaces as an argument-count error at run time and the numbered mistake surfaces as a
    query that binds the wrong vector and returns a plausible wrong answer.
    """
    arm_set = _arm_set()
    numbered = union_all_sql(arm_set, form=SqlForm.EXECUTE)
    assert len(numbered.params) == len(arm_set)
    markers = [int(m) for m in re.findall(r"\$(\d+)::VECTOR", numbered.text)]
    assert sorted(set(markers)) == list(range(1, len(arm_set) + 1))
    assert all(markers.count(n) == 2 for n in set(markers))

    pyformat = union_all_sql(
        arm_set, form=SqlForm.EXECUTE, placeholder_style=PlaceholderStyle.PYFORMAT
    )
    assert pyformat.text.count("%s::VECTOR") == 2 * len(arm_set)
    assert len(pyformat.params) == 2 * len(arm_set)


# ── refusals ─────────────────────────────────────────────────────────────────────────────


def test_ix00_a_partially_constrained_prefix_is_refused_at_construction() -> None:
    two_column = CUE_SCOPED.__class__(
        schema="mainline",
        table="event_cue_embedding",
        index="cue_scoped_idx",
        prefix_columns=("site_id", "scope_id"),
        vector_column="emb",
        id_column="cue_id",
        dimensions=1024,
    )
    with pytest.raises(ValueError, match="prefix columns"):
        generate_arms(
            site=SITE,
            chain=_chain(),
            facet_vectors=_facet_vectors(),
            policy=policy(),
            scoped_table=two_column,
            sweep=_sweep(),
        )


def test_ix00_a_non_finite_query_vector_is_refused() -> None:
    broken = _facet_vectors()
    broken["mechanism"] = [float("nan")] + broken["mechanism"][1:]
    with pytest.raises(ValueError, match="non-finite"):
        _arm_set(facet_vectors=broken)


def test_ix00_an_unknown_level_is_refused_rather_than_defaulted() -> None:
    chain = AncestorChain("act-deep", (ScopeRef(level=4, scope_id=uuid.uuid4()),))
    with pytest.raises(ValueError, match="level 4"):
        _arm_set(chain=chain)


def test_ix00_a_partial_arm_policy_document_is_refused() -> None:
    document = ArmPolicy.graded(facet_priority=FACETS).as_document()
    del document["facet_weight"]
    with pytest.raises(ValueError, match="facet_weight"):
        ArmPolicy.from_document(document)


def test_ix00_policy_round_trips_and_digests_stably() -> None:
    original = policy()
    parsed = ArmPolicy.from_document(original.as_document())
    assert parsed.digest() == original.digest()
    assert len(original.digest()) == 64
