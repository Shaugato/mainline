# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Level-Materialised Bonds: the row count is the design.

``depth x populated facets``, exactly, with distinct ``(scope_id, facet)`` pairs.  The
brief's two numbers are asserted literally — 12 for a depth-3 event with four populated
facets, 4 for a level-1-only event — because the arithmetic is what makes *"one constrained
ANN arm per ancestor"* a real query plan rather than a slogan, and under-emitting is not a
performance regression but an incident a whole class of arms can no longer reach.
"""

from __future__ import annotations

import pytest
from mainline_recall_agent.taxonomy import (
    LEVEL_FILE,
    LEVEL_FONDS,
    LEVEL_SERIES,
    ActivityNode,
    ArchivalPath,
    ArchivalPathError,
    CueEmissionError,
    EventRef,
    FacetValue,
    InMemoryNodeSource,
    LevelMaterialisedBondWriter,
    build_cue_rows,
    cue_params,
    derive_scope_id,
    resolve_path,
)
from mainline_recall_agent.taxonomy.sql import INSERT_EVENT_CUE

SITE = "11111111-1111-4111-8111-111111111111"
OTHER_SITE = "22222222-2222-4222-8222-222222222222"
ROOT = "MUE-05"
GEN_MODEL = "offline-rule-induction-1"
PROMPT = "mainline-cue-1"

FONDS_LABEL = "isolating stored energy before intrusive work"
SERIES_LABEL = "locking out and proving zero energy state"
FILE_LABEL = "applying personal locks to isolation points"


def _node(level: int, label: str, path: list[str], parent: str | None, site: str = SITE):
    return ActivityNode(
        scope_id=derive_scope_id(
            site_id=site, taxonomy_ver=7, level=level, label_path=path
        ),
        site_id=site,
        level=level,
        parent_scope=parent,
        label=label,
        activity_root=ROOT,
        taxonomy_ver=7,
        induced_by="icmm_mue" if level == LEVEL_FONDS else "llm_induced",
        frozen=level == LEVEL_FONDS,
    )


def _chain(site: str = SITE) -> tuple[ActivityNode, ActivityNode, ActivityNode]:
    fonds = _node(LEVEL_FONDS, FONDS_LABEL, [FONDS_LABEL], None, site)
    series = _node(
        LEVEL_SERIES, SERIES_LABEL, [FONDS_LABEL, SERIES_LABEL], fonds.scope_id, site
    )
    leaf = _node(
        LEVEL_FILE,
        FILE_LABEL,
        [FONDS_LABEL, SERIES_LABEL, FILE_LABEL],
        series.scope_id,
        site,
    )
    return fonds, series, leaf


def _four_facets() -> list[FacetValue]:
    return [
        FacetValue(facet="mechanism", text="stored pneumatic energy released axially"),
        FacetValue(facet="precondition", text="person inside the trajectory zone"),
        FacetValue(facet="control_failure", text="engineered exclusion absent"),
        FacetValue(
            facet="recurrence_test",
            text="recurs wherever a person can occupy the trajectory during inflation",
        ),
    ]


@pytest.fixture
def event() -> EventRef:
    return EventRef(
        event_id="33333333-3333-4333-8333-333333333333",
        site_id=SITE,
        severity_gate=5,
        severity_basis="regulator_class",
    )


def test_depth_three_with_four_facets_emits_exactly_twelve_rows(event: EventRef) -> None:
    fonds, series, leaf = _chain()
    emission = build_cue_rows(
        event=event,
        path=ArchivalPath((fonds, series, leaf)),
        facets=_four_facets(),
        gen_model=GEN_MODEL,
        prompt_version=PROMPT,
    )
    assert len(emission.rows) == 12

    pairs = emission.scope_facet_pairs()
    assert len(set(pairs)) == 12, "every (scope_id, facet) pair must be distinct"

    by_level = {LEVEL_FONDS: 0, LEVEL_SERIES: 0, LEVEL_FILE: 0}
    for row in emission.rows:
        by_level[row.scope_level] += 1
    assert by_level == {LEVEL_FONDS: 4, LEVEL_SERIES: 4, LEVEL_FILE: 4}

    assert {row.scope_id for row in emission.rows} == {
        fonds.scope_id,
        series.scope_id,
        leaf.scope_id,
    }
    # The unique constraint the table declares is satisfied by construction.
    assert len({row.dedupe_key for row in emission.rows}) == 12


def test_a_level_one_only_event_emits_exactly_four_rows(event: EventRef) -> None:
    fonds, _, _ = _chain()
    emission = build_cue_rows(
        event=event,
        path=ArchivalPath((fonds,)),
        facets=_four_facets(),
        gen_model=GEN_MODEL,
        prompt_version=PROMPT,
    )
    assert len(emission.rows) == 4
    assert {row.scope_level for row in emission.rows} == {LEVEL_FONDS}
    assert len(set(emission.scope_facet_pairs())) == 4


def test_insufficient_evidence_facets_produce_no_row_at_any_level(event: EventRef) -> None:
    fonds, series, leaf = _chain()
    facets = [
        *_four_facets()[:2],
        FacetValue(facet="control_failure", insufficient_evidence=True),
        FacetValue(facet="recurrence_test", insufficient_evidence=True),
    ]
    emission = build_cue_rows(
        event=event,
        path=ArchivalPath((fonds, series, leaf)),
        facets=facets,
        gen_model=GEN_MODEL,
        prompt_version=PROMPT,
    )
    assert len(emission.rows) == 6
    assert emission.populated_facets == ("mechanism", "precondition")
    assert emission.skipped_facets == ("control_failure", "recurrence_test")
    assert not emission.unindexed


def test_an_event_with_no_populated_facet_is_reported_as_unindexed(event: EventRef) -> None:
    fonds, series, leaf = _chain()
    emission = build_cue_rows(
        event=event,
        path=ArchivalPath((fonds, series, leaf)),
        facets=[FacetValue(facet=name, insufficient_evidence=True) for name in
                ("mechanism", "precondition", "control_failure", "recurrence_test")],
        gen_model=GEN_MODEL,
        prompt_version=PROMPT,
    )
    assert emission.rows == ()
    assert emission.unindexed, "an event in no vector tree must be visible, not silent"


def test_the_narrative_facet_is_the_only_undERived_row(event: EventRef) -> None:
    fonds, series, leaf = _chain()
    facets = [*_four_facets(), FacetValue(facet="narrative", text="the raw event text")]
    emission = build_cue_rows(
        event=event,
        path=ArchivalPath((fonds, series, leaf)),
        facets=facets,
        gen_model=GEN_MODEL,
        prompt_version=PROMPT,
    )
    assert len(emission.rows) == 15
    derived = {row.facet: row.is_derived for row in emission.rows}
    assert derived["narrative"] is False
    assert all(value for facet, value in derived.items() if facet != "narrative")


def test_a_blank_populated_facet_is_refused_rather_than_indexed() -> None:
    with pytest.raises(CueEmissionError):
        FacetValue(facet="mechanism", text="   ")


def test_a_duplicate_facet_is_refused_before_it_reaches_the_unique_constraint(
    event: EventRef,
) -> None:
    fonds, _, _ = _chain()
    facets = [
        FacetValue(facet="mechanism", text="one"),
        FacetValue(facet="mechanism", text="two"),
    ]
    with pytest.raises(CueEmissionError):
        build_cue_rows(
            event=event,
            path=ArchivalPath((fonds,)),
            facets=facets,
            gen_model=GEN_MODEL,
            prompt_version=PROMPT,
        )


def test_blank_provenance_is_refused(event: EventRef) -> None:
    fonds, _, _ = _chain()
    with pytest.raises(CueEmissionError):
        build_cue_rows(
            event=event,
            path=ArchivalPath((fonds,)),
            facets=_four_facets(),
            gen_model="",
            prompt_version=PROMPT,
        )


def test_a_path_from_another_site_is_refused(event: EventRef) -> None:
    fonds, series, leaf = _chain(site=OTHER_SITE)
    with pytest.raises(CueEmissionError) as excinfo:
        build_cue_rows(
            event=event,
            path=ArchivalPath((fonds, series, leaf)),
            facets=_four_facets(),
            gen_model=GEN_MODEL,
            prompt_version=PROMPT,
        )
    assert excinfo.value.context["path_site"] == OTHER_SITE


def test_the_writer_resolves_the_path_and_refuses_a_missing_ancestor(
    event: EventRef,
) -> None:
    """A caller cannot choose the prefix set; it is derived, and a hole in it is fatal."""
    fonds, series, leaf = _chain()
    writer = LevelMaterialisedBondWriter(
        source=InMemoryNodeSource([fonds, leaf]),  # the series is missing
        gen_model=GEN_MODEL,
        prompt_version=PROMPT,
    )
    with pytest.raises(ArchivalPathError) as excinfo:
        writer.emit(event=event, scope_id=leaf.scope_id, facets=_four_facets())
    assert excinfo.value.context["missing_scope_id"] == series.scope_id


def test_the_writer_emits_the_same_rows_as_the_pure_function(event: EventRef) -> None:
    fonds, series, leaf = _chain()
    source = InMemoryNodeSource([fonds, series, leaf])
    writer = LevelMaterialisedBondWriter(
        source=source, gen_model=GEN_MODEL, prompt_version=PROMPT
    )
    emitted = writer.emit(event=event, scope_id=leaf.scope_id, facets=_four_facets())
    direct = build_cue_rows(
        event=event,
        path=resolve_path(source, leaf.scope_id),
        facets=_four_facets(),
        gen_model=GEN_MODEL,
        prompt_version=PROMPT,
    )
    assert [row.to_dict() for row in emitted.rows] == [row.to_dict() for row in direct.rows]


def test_a_scope_the_node_table_does_not_know_is_refused() -> None:
    fonds, _, _ = _chain()
    with pytest.raises(ArchivalPathError):
        resolve_path(InMemoryNodeSource([fonds]), "99999999-9999-4999-8999-999999999999")


def test_the_activity_path_string_is_the_embedding_template_slot() -> None:
    fonds, series, leaf = _chain()
    path = ArchivalPath((fonds, series, leaf))
    assert path.activity_path_string() == f"{FONDS_LABEL} / {SERIES_LABEL} / {FILE_LABEL}"


def test_insert_parameters_match_the_statement(event: EventRef) -> None:
    fonds, _, _ = _chain()
    emission = build_cue_rows(
        event=event,
        path=ArchivalPath((fonds,)),
        facets=_four_facets(),
        gen_model=GEN_MODEL,
        prompt_version=PROMPT,
    )
    placeholders = INSERT_EVENT_CUE.count("%s")
    for row in emission.rows:
        assert len(cue_params(row)) == placeholders
    # cue_id and tsv are the database's, not ours.
    assert "cue_id" not in INSERT_EVENT_CUE
    assert "tsv" not in INSERT_EVENT_CUE


def test_a_path_that_skips_a_level_is_refused() -> None:
    fonds, _, leaf = _chain()
    with pytest.raises(ArchivalPathError):
        ArchivalPath((fonds, leaf))


def test_a_path_that_does_not_start_at_the_fonds_is_refused() -> None:
    _, series, leaf = _chain()
    with pytest.raises(ArchivalPathError):
        ArchivalPath((series, leaf))
