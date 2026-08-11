# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The four assertions that keep ``evidence/aws/ann/`` honest, plus the four that keep it live.

``scripts/aws/ann_proof.py`` writes an artefact.  An artefact nobody re-derives is a
screenshot.  This module re-derives it, twice over and for two different readers:

**Live (marked ``requires_aws`` / ``requires_cluster``).**  Against Bedrock in
``ap-southeast-2`` and CockroachDB Cloud in ``aws-ap-southeast-1``, right now:

  a. the hinted plan contains a ``vector search`` node naming ``clause_embedding@ce_ann``;
  b. every vector the ANN query returns carries ``embed_model =
     'amazon.titan-embed-text-v2:0'`` — the index is searching *Bedrock's* vectors, not
     something a fixture wrote;
  c. dropping the prefix constraint on **either** column is **refused** by the server with
     SQLSTATE ``42809`` — which is how "both prefix columns must be bound to one value"
     stops being folklore and becomes a rule somebody else enforces;
  d. for one named query id, the top-1 row is the precursor the goldset says it is, with
     the query narrative embedded live through Titan in this process;
  e. the ``activity_root IN (...)`` form still *does* traverse the index on this release —
     the correction ``ann-proof.json`` publishes against ``0031_clause_embedding.sql`` —
     so that the correction cannot outlive the behaviour that justified it.

**Hermetic (no marker, no credential, no network).**  Against the committed files:
the plan digests in ``ann-proof.json`` match the plans in the two ``.txt`` files, every
rate carries its ``n`` and its interval, the caveats say the corpus is synthetic and the
parent table is a stub, and ``the-one-query.sql`` is self-contained.  These run on a
stranger's machine and are what stop the evidence directory drifting into decoration.

**How this file is meant to fail.**  Loudly.  There is no ``try: ... except: skip`` here.
A missing ``COCKROACH_DSN`` or ``AWS_PROFILE`` skips with a reason that names the variable;
anything else — a plan that stopped naming the index, a vector from the wrong model, a
precursor that stopped coming back first — is a failure, and the message says which of the
four claims died.  A green from this module with no credentials present is not available:
run it as ``pytest -m 'not requires_aws'`` and the live tests are reported as *deselected*,
which is a different sentence from *passed*.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = REPO_ROOT / "evidence" / "aws" / "ann"
ARTEFACT = EVIDENCE / "ann-proof.json"
HINTED_PLAN_FILE = EVIDENCE / "explain-hinted.txt"
UNHINTED_PLAN_FILE = EVIDENCE / "explain-unhinted.txt"
ONE_QUERY_FILE = EVIDENCE / "the-one-query.sql"

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
INDEX_NAME = "ce_ann"
#: CockroachDB draws EXPLAIN as a tree, so the node line reads
#: ``        └── • vector search`` — the prefix is box-drawing characters, not whitespace.
#: Written out here rather than imported so that the assertion and the program that writes
#: the artefact do not share one regex: a bug in the detector would otherwise agree with
#: itself. (There was one. ``^\s*•`` matched nothing.)
VECTOR_SEARCH_NODE = re.compile(r"^[\s│└├─┌┐┘]*•\s*vector search\s*$", re.MULTILINE)
INDEX_LINE = f"table: clause_embedding@{INDEX_NAME}"

#: The named query, fixed in this file rather than read from the artefact.
#:
#: Reading it from ``ann-proof.json`` would make assertion (d) circular: the artefact would
#: be checked against itself and would pass however the run went.  This query id and its
#: precursor are facts about a **committed goldset fixture**
#: (``tests/fixtures/recall/goldsets/g4_retro.{queries,qrels}.jsonl``), so the constant is a
#: claim about retrieval quality that a regression can break.
#:
#: **What it is.**  ``Q-G4-FAI-2011-142`` is a permit to work on instrument maintenance at
#: MINE-7700645, written 2011-02-02: *a boilermaker was cutting a section of pipe adjacent
#: to a gauge housing that had been tagged for removal*.  Nothing in that sentence names a
#: hazard.
NAMED_QUERY_ID = "Q-G4-FAI-2011-142"

#: The document ``g4_retro.qrels.jsonl`` grades 3 for that query — the one the investigator
#: cited.  ``FAI-2010-141`` is a fatality investigation from **eight months earlier at the
#: same operation**: *Accident Classification: Exposure to ionising radiation · Source of
#: Injury: Radioactive source · Equipment: Density gauge*.  The permit is about cutting pipe
#: next to a density gauge; the precursor is the death that a density gauge's sealed source
#: already caused there.
#:
#: Verified against the fixture by
#: :func:`test_named_query_and_precursor_are_what_the_goldset_says`, so a fixture edit fails
#: here rather than silently redefining what the live test is proving.
NAMED_EXPECTED_DOC_ID = "FAI-2010-141"

#: The provenance probe for assertion (b), written out rather than assembled.  Every
#: identifier is a literal so that the statement asserted against is the statement in this
#: file; ``ann_proof.py`` holds the ANN statements themselves for the same reason and the
#: live tests import them from there rather than retyping them.
PROVENANCE_OF_RETURNED_ROWS = """SELECT e.embed_model, e.index_gen, vector_dims(e.embedding)
  FROM mainline.clause_embedding@ce_ann AS e
 WHERE e.site_id = %(site)s AND e.activity_root = %(root)s
 ORDER BY e.embedding <=> %(vec)s LIMIT 25"""


# ═══════════════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def artefact_payload() -> dict[str, Any]:
    if not ARTEFACT.exists():
        pytest.fail(
            f"{ARTEFACT.relative_to(REPO_ROOT)} is missing. It is a committed artefact, "
            "not a build output: run scripts/aws/ann_proof.py and commit what it writes."
        )
    envelope: dict[str, Any] = json.loads(ARTEFACT.read_text(encoding="utf-8"))
    return envelope


@pytest.fixture(scope="module")
def cluster() -> Iterator[Any]:
    """A connection to the evidence database, or a skip that names what is missing."""
    if not (os.environ.get("COCKROACH_DSN") or (REPO_ROOT / ".env").exists()):
        pytest.skip("COCKROACH_DSN is not in the environment and there is no .env")
    from scripts.aws._common import crdb
    from scripts.aws.ann_proof import DEFAULT_DATABASE

    database = os.environ.get("MAINLINE_ANN_DATABASE", DEFAULT_DATABASE)
    connection = crdb(database)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(scope="module")
def titan() -> Any:
    """A live Bedrock runtime client, or a skip that names what is missing."""
    if not (
        os.environ.get("AWS_PROFILE")
        or os.environ.get("AWS_ACCESS_KEY_ID")
        or (Path.home() / ".aws" / "credentials").exists()
    ):
        pytest.skip("no AWS_PROFILE, no AWS_ACCESS_KEY_ID and no ~/.aws/credentials")
    from scripts.aws._common import bedrock_runtime

    return bedrock_runtime()


def _named_case() -> Any:
    from scripts.aws.ann_proof import load_goldset

    for case in load_goldset():
        if case.query_id == NAMED_QUERY_ID:
            return case
    pytest.fail(
        f"{NAMED_QUERY_ID} is not in g4_retro.queries.jsonl any more. That fixture is the "
        "definition of what this test proves; a query that vanished is a goldset change "
        "that has to be looked at, not routed around."
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# Hermetic — no credential, no network, always collected
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_named_query_and_precursor_are_what_the_goldset_says() -> None:
    """The constants above are still the fixture's own facts.

    Cheap, and it is the reason the live assertions are not circular: if somebody
    regenerates the goldset, this fails first and says so, instead of the live test
    quietly proving a different sentence.
    """
    case = _named_case()
    assert case.truth_doc_id == NAMED_EXPECTED_DOC_ID, (
        f"{NAMED_QUERY_ID}'s grade-3 truth precursor is {case.truth_doc_id!r} in the "
        f"fixture but this file says {NAMED_EXPECTED_DOC_ID!r}"
    )
    assert case.relevant.get(NAMED_EXPECTED_DOC_ID) == 3
    assert case.activity_path.startswith("/")


@pytest.mark.artefact
def test_committed_hinted_plan_traverses_the_named_index() -> None:
    """(a), as committed.  The plan file must show the C-SPANN tree being descended."""
    text = HINTED_PLAN_FILE.read_text(encoding="utf-8")
    assert VECTOR_SEARCH_NODE.search(text), (
        "explain-hinted.txt has no `• vector search` node. Without one the ANN arm is a "
        "scan, which in this product is a safety defect and not a performance regression."
    )
    assert INDEX_LINE in text, f"explain-hinted.txt does not name `{INDEX_LINE}`"
    assert "prefix spans:" in text, (
        "explain-hinted.txt has no `prefix spans:` line, so nothing shows which partition "
        "tree was searched"
    )


@pytest.mark.artefact
def test_committed_unhinted_plan_is_a_real_control() -> None:
    """The counterfactual exists, is the *same* statement, and differs from the hinted one.

    The one thing this must never be is a copy.  Whether the optimizer picks the index
    unhinted at this corpus size is a measurement recorded in the artefact; that the two
    files are different captures is a property of the evidence, and it is checked here.
    """
    hinted = HINTED_PLAN_FILE.read_text(encoding="utf-8")
    unhinted = UNHINTED_PLAN_FILE.read_text(encoding="utf-8")
    assert f"@{INDEX_NAME}" not in _statement_block(unhinted), (
        "explain-unhinted.txt's STATEMENT block still contains the index hint; it is not "
        "the control it claims to be"
    )
    assert f"@{INDEX_NAME}" in _statement_block(hinted)
    assert hinted != unhinted


def _statement_block(plan_file_text: str) -> str:
    """The ``STATEMENT`` section of a plan file, which is the only place the hint may
    legitimately appear or be absent — the surrounding prose discusses ``@ce_ann`` by name
    in both files, and a naive substring test over the whole file would read that prose."""
    match = re.search(r"^STATEMENT.*?\n-{10,}\n(.*?)\n-{10,}\nEXPLAIN", plan_file_text, re.S | re.M)
    assert match, "plan file has no STATEMENT block delimited the way write_explain_file writes it"
    return match.group(1)


@pytest.mark.artefact
def test_artefact_plan_digests_match_the_committed_plan_files() -> None:
    """The JSON and the two ``.txt`` files describe the same capture.

    Three files written by one run drift the moment one of them is regenerated alone.
    The digest is the link, and this is the assertion that makes the link load-bearing.
    """
    from scripts.aws.ann_proof import plan_digest

    payload = json.loads(ARTEFACT.read_text(encoding="utf-8"))["payload"]
    for key, path in (("hinted", HINTED_PLAN_FILE), ("unhinted", UNHINTED_PLAN_FILE)):
        plan = _explain_block(path.read_text(encoding="utf-8"))
        assert plan_digest(plan) == payload["plans"][key]["digest_sha256"], (
            f"the {key} plan digest in ann-proof.json does not match the plan in "
            f"{path.name}: one of the three files was regenerated without the others"
        )


def _explain_block(plan_file_text: str) -> str:
    match = re.search(
        r"^EXPLAIN\n-{10,}\n\n(.*?)\n\n-{10,}\nEXPLAIN ANALYZE",
        plan_file_text,
        re.S | re.M,
    )
    assert match, "plan file has no EXPLAIN block delimited the way write_explain_file writes it"
    return match.group(1)


@pytest.mark.artefact
def test_no_rate_is_reported_without_its_n_and_its_interval() -> None:
    """``docs/`` is ratcheted against bare point estimates.  So is this artefact.

    Every proportion in ``metrics`` must carry ``successes``, ``n``, a Wilson interval and
    a ``stated_as`` string that contains all three, so that a document quoting it has no
    way to quote only the number.
    """
    payload = json.loads(ARTEFACT.read_text(encoding="utf-8"))["payload"]
    queries_run = payload["queries_run"]
    assert queries_run >= 20, (
        f"the artefact reports {queries_run} retro queries; the floor for this evidence is 20"
    )
    assert len(payload["queries"]) == queries_run

    seen = 0
    for arm, metrics in payload["metrics"].items():
        for name, block in metrics.items():
            if name == "mrr_any_relevant":
                assert block["n"] == queries_run
                assert "note" in block, "an MRR with no note about zero-rank queries is a trap"
                continue
            seen += 1
            for field in ("successes", "n", "fraction", "wilson_lower", "wilson_upper"):
                assert field in block, f"{arm}.{name} has no {field}"
            # Headline rates are over every query run. The one conditional rate
            # (`..._reachable_only`) has a smaller, stated denominator on purpose — that is
            # what makes it a different measurement rather than a nicer version of the same
            # one — so it is checked for a stated n rather than for the full n.
            if name.endswith("_reachable_only"):
                assert 0 < block["n"] <= queries_run
                assert "why" in block["detail"]
            else:
                assert block["n"] == queries_run, (
                    f"{arm}.{name} reports n={block['n']} but {queries_run} queries were run"
                )
            assert block["wilson_lower"] <= block["fraction"] <= block["wilson_upper"]
            assert str(block["n"]) in block["stated_as"]
            assert str(block["successes"]) in block["stated_as"]
    assert seen >= 12, f"only {seen} proportions found; the artefact should report far more"


@pytest.mark.artefact
def test_the_time_wall_leak_is_reported_rather_than_absorbed() -> None:
    """The corpus contains each query's own source report, and the artefact must say so.

    Every retro permit in ``g4_retro`` is synthesised from one fatality investigation, and
    that investigation is a document in the same corpus.  It post-dates the permit, so a
    deployment could not have had it — but the ANN arm has no date column to exclude it
    with, and it is frequently the nearest neighbour.

    It never inflates a hit rate (it is not relevant in the goldset, so it *costs* rank),
    which is exactly why it would be easy to leave unmentioned.  This test refuses that:
    every rate must appear a second time with the post-wall rows dropped, the leak must be
    counted, and the caveats must name it.
    """
    envelope = json.loads(ARTEFACT.read_text(encoding="utf-8"))
    payload = envelope["payload"]
    caveats = " ".join(envelope["caveats"]).upper()
    assert "WALL" in caveats, "no caveat mentions the time wall"

    for arm, metrics in payload["metrics"].items():
        for k in (1, 3, 10):
            assert f"wall_filtered_truth_precursor_hit_at_{k}" in metrics, (
                f"{arm} reports a raw hit@{k} with no wall-filtered counterpart"
            )
            assert f"wall_filtered_any_relevant_hit_at_{k}" in metrics
        census = metrics["queries_whose_own_source_report_came_back"]
        assert census["n"] == payload["queries_run"]
        assert "why" in census["detail"]
        assert metrics["queries_with_a_post_wall_row_in_top_10"]["n"] == payload["queries_run"]

    # The exhibit prints both ranks, so a reader of the SQL alone cannot mistake the raw
    # rank for the one a deployment would see.
    sql = ONE_QUERY_FILE.read_text(encoding="utf-8")
    assert "rank once post-wall" in sql
    assert payload["the_one_query"]["wall_filtered_rank"] is not None


@pytest.mark.artefact
def test_caveats_name_the_synthetic_corpus_and_the_stub_parent() -> None:
    """The two disclosures the AWS-execution plan §2 refuses to let a reader discover."""
    envelope = json.loads(ARTEFACT.read_text(encoding="utf-8"))
    caveats = " ".join(envelope["caveats"]).upper()
    assert envelope["synthetic"] is True
    assert "SYNTHETIC" in caveats
    assert "STUB" in caveats
    sql = ONE_QUERY_FILE.read_text(encoding="utf-8").upper()
    assert "SYNTHETIC" in sql, (
        "the-one-query.sql is the file a judge reads on its own; it must carry the "
        "synthetic disclosure in its own header rather than relying on a sibling"
    )


@pytest.mark.artefact
def test_one_query_sql_is_self_contained_and_states_its_observed_rank() -> None:
    """A judge pastes this file and nothing else.  So it has to carry everything."""
    sql = ONE_QUERY_FILE.read_text(encoding="utf-8")
    payload = json.loads(ARTEFACT.read_text(encoding="utf-8"))["payload"]
    exhibit = payload["the_one_query"]

    # Comments are stripped before the shape assertions. The header *discusses* the
    # `activity_root IN (...)` trap by name, which is exactly the sentence a naive
    # whole-file grep would trip over — and a test that forces the file to stop explaining
    # the trap in order to pass has made the evidence worse.
    executable = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert f"@{INDEX_NAME}" in executable
    assert "site_id = '" in executable and "activity_root = '" in executable, (
        "both prefix columns must be bound to a single literal value in the committed SQL"
    )
    assert " IN (" not in executable.upper().replace("\n", " "), (
        "the committed exhibit must be the single-value form. On v26.2.5 an IN list does "
        "still traverse the index (see test_live_in_list_prefix_is_not_the_trap_...), but "
        "under one shared LIMIT across every tree — a different recall budget, and not the "
        "statement this file claims to be"
    )
    assert exhibit["query_id"] in sql
    assert str(exhibit["expected_doc_id"]) in sql
    assert exhibit["expected_clause_uuid"] in sql
    assert f"OBSERVED RANK ......... {exhibit['observed_rank']}" in sql, (
        "the committed SQL must state the rank that was actually observed, whatever it was"
    )
    # A 1024-float literal, inlined, so the statement needs no parameter binding.
    assert sql.count("<=>") >= 4
    assert len(re.findall(r"-?\d+\.\d{8}", sql)) >= 1024


# ═══════════════════════════════════════════════════════════════════════════════════════
# Live — deselected by `-m 'not requires_aws'`, skipped with a named reason otherwise
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.requires_cluster
def test_live_hinted_plan_names_clause_embedding_at_ce_ann(cluster: Any) -> None:
    """(a), live.  The plan is re-taken against the cluster in this process."""
    from scripts.aws.ann_proof import CORPUS_SITE_ID, ROOTS, hinted_statement

    params = {"vec": _zero_vector(), "site": CORPUS_SITE_ID, "root": ROOTS[0], "k": 10}
    with cluster.cursor() as cur:
        plan = "\n".join(
            str(row[0]) for row in cur.execute("EXPLAIN " + hinted_statement(hint=True), params)
        )
    assert VECTOR_SEARCH_NODE.search(plan), f"no vector search node in the live plan:\n{plan}"
    assert INDEX_LINE in plan, f"live plan does not name {INDEX_LINE}:\n{plan}"
    assert "prefix spans:" in plan


@pytest.mark.integration
@pytest.mark.requires_cluster
def test_live_every_returned_vector_was_produced_by_titan_v2(cluster: Any) -> None:
    """(b).  The rows the index hands back must be Bedrock's, and must say so in the row.

    ``embed_model`` is a column on ``clause_embedding`` with a ``CHECK (embed_model <> '')``
    behind it.  This asserts the stronger thing: that every row the ANN arm actually
    returns names the model that produced it, so no fixture vector can be hiding in the
    tree the query descends.
    """
    from scripts.aws.ann_proof import CORPUS_SITE_ID, ROOTS

    returned = 0
    with cluster.cursor() as cur:
        for root in ROOTS:
            rows = cur.execute(
                PROVENANCE_OF_RETURNED_ROWS,
                {"vec": _zero_vector(), "site": CORPUS_SITE_ID, "root": root},
            ).fetchall()
            assert rows, f"the {root!r} partition tree returned nothing"
            for model, gen, dims in rows:
                returned += 1
                assert model == TITAN_MODEL_ID, (
                    f"a row in the {root!r} tree carries embed_model={model!r}; the ANN "
                    "proof claims every vector under this site_id is Titan v2's"
                )
                assert gen, "index_gen is empty, which the DDL's CHECK is supposed to prevent"
                assert dims == 1024
    assert returned >= 60, f"only {returned} rows came back across {len(ROOTS)} trees"


@pytest.mark.integration
@pytest.mark.requires_cluster
def test_live_dropping_either_prefix_column_is_refused(cluster: Any) -> None:
    """(c).  The rule "every prefix column bound to one value" is measured, not recited.

    Same table, same hint, one thing changed: the ``site_id`` constraint removed, then the
    ``activity_root`` constraint removed.  Measured on v26.2.5, CockroachDB does not
    produce a worse plan for either — **it refuses the statement**, SQLSTATE ``42809``,
    ``index "ce_ann" cannot be used for this query``.

    That refusal is a much stronger control than a plan diff, and it is the half of the
    counterfactual that does not depend on the optimizer's cost model: whether the
    *unhinted* plan happens to pick ``ce_ann`` has already been observed to change, but a
    query carrying half a prefix cannot use a prefixed vector index at all, and the server
    says so before executing anything.
    """
    import psycopg

    from scripts.aws.ann_proof import (
        ANN_NO_ROOT,
        ANN_NO_SITE,
        CORPUS_SITE_ID,
        ROOTS,
        hinted_statement,
    )

    params = {"vec": _zero_vector(), "site": CORPUS_SITE_ID, "root": ROOTS[0], "k": 10}
    both = _plan(cluster, hinted_statement(hint=True), params)
    assert "prefix spans:" in both, (
        "the fully-constrained plan has no prefix span, so no single partition tree was "
        f"named:\n{both}"
    )

    # 42809 is `wrong_object_type`, which psycopg3 maps to WrongObjectType. Caught by class
    # AND re-checked by SQLSTATE: the class is psycopg's mapping and could change with the
    # driver, the five characters are the contract the server publishes.
    for label, statement in (("site_id", ANN_NO_SITE), ("activity_root", ANN_NO_ROOT)):
        with pytest.raises(psycopg.errors.WrongObjectType) as caught:
            _plan(cluster, statement, params)
        message = str(caught.value)
        assert "ce_ann" in message, (
            f"dropping the {label} constraint failed for some reason other than the index "
            f"being unusable: {message}"
        )
        assert caught.value.sqlstate == "42809", (
            f"expected SQLSTATE 42809 for a partially-constrained prefix, got "
            f"{caught.value.sqlstate}"
        )


def _plan(cluster: Any, statement: str, params: dict[str, Any]) -> str:
    with cluster.cursor() as cur:
        return "\n".join(str(row[0]) for row in cur.execute("EXPLAIN " + statement, params))


@pytest.mark.integration
@pytest.mark.requires_cluster
def test_live_in_list_prefix_is_not_the_trap_the_migration_header_describes(
    cluster: Any,
) -> None:
    """The unflattering measurement, asserted so it cannot quietly stop being true.

    ``0031_clause_embedding.sql`` states as a law that ``activity_root IN (...)`` does not
    use the vector index.  On v26.2.5 it does: the optimizer expands the list into one
    prefix span per value.  ``ann-proof.json`` publishes that correction, and this test is
    what stops the correction from outliving the behaviour that justified it — if a future
    release restores the documented behaviour, this fails and the artefact has to be
    rewritten rather than left standing as a stale rebuttal.
    """
    from scripts.aws.ann_proof import ANN_IN_LIST, CORPUS_SITE_ID, ROOTS

    plan = _plan(cluster, ANN_IN_LIST, {"vec": _zero_vector(), "site": CORPUS_SITE_ID, "k": 10})
    assert VECTOR_SEARCH_NODE.search(plan), (
        "the IN-list form no longer traverses the vector index. That is what "
        "0031_clause_embedding.sql says should happen — so the correction published in "
        f"evidence/aws/ann/ann-proof.json is now itself stale and must be withdrawn:\n{plan}"
    )
    assert INDEX_LINE in plan
    spans = plan.count("' - /'")
    assert spans >= len(ROOTS), (
        f"expected one prefix span per activity root ({len(ROOTS)}), found {spans}:\n{plan}"
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.requires_aws
@pytest.mark.requires_cluster
def test_live_named_query_returns_its_precursor_first(cluster: Any, titan: Any) -> None:
    """(d).  End to end, in one test, with nothing pre-computed.

    The permit narrative goes to Bedrock in this process; the vector that comes back goes
    into the hinted, prefix-constrained ANN query; the row that comes back first is
    resolved to a ``doc_id`` and compared with the goldset's grade-3 truth precursor.

    This is the whole submission in twenty lines.  If it fails, the claim is false, and the
    right response is to publish the number it actually produced — the artefact already
    reports the rate across all 96 queries with its interval, so a regression here is
    visible rather than fatal to the evidence.

    Note what is *not* asserted: that this happens often.  It does not.  Over the same 96
    queries the cited precursor reaches rank 1 rarely and the top ten about three times in
    ten, and ``ann-proof.json`` publishes both with their intervals.  This test asserts one
    query, because one query is what ``the-one-query.sql`` commits, and a committed exhibit
    that has quietly stopped working is the failure mode with no other alarm on it.
    """
    from scripts.aws.ann_proof import (
        ANN_HINTED,
        CORPUS_SITE_ID,
        Embedder,
        build_corpus,
        vector_literal,
    )

    case = _named_case()
    docs = {d.doc_id: d for d in build_corpus()}
    expected = docs[NAMED_EXPECTED_DOC_ID]
    by_uuid = {d.clause_uuid: d for d in docs.values()}

    embedder = Embedder(titan)
    embedder.load_cache()
    vector = embedder.embed_many([case.text], workers=1)[0]
    assert len(vector) == 1024

    with cluster.cursor() as cur:
        rows = cur.execute(
            ANN_HINTED,
            {
                "vec": vector_literal(vector),
                "site": CORPUS_SITE_ID,
                "root": case.activity_root,
                "k": 10,
            },
        ).fetchall()

    assert rows, f"{NAMED_QUERY_ID} returned no rows from the {case.activity_root!r} tree"
    ranked = [by_uuid[str(r[0])].doc_id for r in rows]
    assert ranked[0] == NAMED_EXPECTED_DOC_ID, (
        f"{NAMED_QUERY_ID}: expected precursor {NAMED_EXPECTED_DOC_ID} at rank 1; got "
        f"{ranked[0]} (full ranking {ranked}). The expected document is "
        f"{expected.text[:120]!r}"
    )
    assert float(rows[0][2]) < float(rows[1][2]), "rank 1 and rank 2 are equidistant"


@pytest.mark.integration
@pytest.mark.requires_cluster
def test_live_row_count_matches_the_committed_artefact(
    cluster: Any, artefact_payload: dict[str, Any]
) -> None:
    """The artefact describes *these* rows, not rows that used to be here.

    ``mainline_ann_evidence`` is shared with ``scripts/aws/load_vectors.py``, whose loader
    issues ``DROP TABLE IF EXISTS mainline.clause_embedding``.  A count that has moved is
    not necessarily wrong, but it means the committed evidence is describing a table that
    no longer exists, and that has to fail rather than pass quietly.
    """
    from scripts.aws.ann_proof import CORPUS_SITE_ID, COUNT_UNDER_SITE

    with cluster.cursor() as cur:
        live = int(cur.execute(COUNT_UNDER_SITE, (CORPUS_SITE_ID,)).fetchone()[0])
    recorded = artefact_payload["payload"]["vectors"]["rows_searched"]
    assert live == recorded, (
        f"{recorded} rows under this site_id when ann-proof.json was written, {live} now. "
        "Re-run scripts/aws/ann_proof.py and commit what it writes."
    )


def _zero_vector() -> str:
    """A fixed probe vector for the plan tests.

    All-zero would be degenerate for a cosine index, so this is a fixed unit-ish ramp: the
    plan tests care about the *shape of the plan*, which does not depend on the vector, and
    a constant here keeps those tests free of a Bedrock call.
    """
    values = [((i % 97) + 1) / 1000.0 for i in range(1024)]
    norm = sum(v * v for v in values) ** 0.5
    return "[" + ",".join(f"{v / norm:.8f}" for v in values) + "]"
