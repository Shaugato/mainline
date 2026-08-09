#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Generate the four-column honesty card from measured artefacts.

    python verticals/mainline/demo/honesty/gen_card.py
    python verticals/mainline/demo/honesty/gen_card.py --allow-fixtures
    python verticals/mainline/demo/honesty/gen_card.py --check
    python verticals/mainline/demo/honesty/gen_card.py --json

**No number on this card is ever typed by hand.** That is the design, and it is a
design about incentives rather than tidiness. A hand-typed honesty card drifts one
corpus regeneration after it is written, and a drifted honesty card is worse than
none: it is a document whose entire value is its accuracy, being inaccurate, full
screen, for eight seconds. So every number is pulled through :func:`fact` from one
of two generated inputs, and a missing path is a hard failure that names the path
rather than a blank cell or a plausible zero:

* ``corpus.lock.json`` — emitted by ``corpusgen freeze``. Counts, the severity
  histogram, the **renderer census**, and embedding provenance.
* the **G1 ground-truth attestation** — emitted by the day-1 probe run and shaped
  by ``attestation.schema.json``. Cluster product, version, edition, tier, region,
  ``gc.ttlseconds`` where it was measured, and one entry per probed capability.

Two further inputs supply text, never numbers:

* ``demo/script/CAMERA-STRINGS.yaml`` — the on-camera prose. Exactly one string
  reaches this card: the 2013 commit message, which ``tests/unit/corpus`` asserts
  byte-equal across the authored fixture, ``VO.md``, ``SHOT-LIST.yaml`` and the
  card this program writes.
* ``honesty/disclosures.yaml`` — the fourth column and the limits. These are
  statements about what we chose not to build and what we decline to claim; no
  probe can measure them. **The attestation outranks this file wherever both carry
  the same fact**, and the card's own provenance table names which one won.

The renderer census is why the card cannot lie about how much prose a model wrote:
it is *counted by the generator*, not asserted by the author, so "written by hand"
over a corpus a model wrote is not a sentence this program can emit.

**Fixtures are visible, never silent.** ``--allow-fixtures`` substitutes shipped
stand-ins for inputs that do not exist, but the banner is driven by the DATA
(``_fixture`` in either document), not by the flag — so a fixture cannot reach
camera by omitting an argument. A fixture-built card carries a full-width banner
reading NOT FOR CAMERA and exits 3.

**Three assertions the card enforces about itself.** The fourth column must name
``M14 SHEPARD`` (BUILD_PLAN §5.1; finding S3 exists because an earlier script
filmed it). The limits must state the rubber-stamp limit. And no hexadecimal run
of seven or more characters may appear anywhere in the output, because a commit id
is a sha256 over the JCS envelope that nobody can choose in advance — so a SHA on
the card is a promise the DAG has not made.

Exit status: ``0`` real inputs and card written; ``1`` ``--check`` found drift;
``2`` an input was missing, unparseable or internally inconsistent; ``3`` at least
one input was a fixture.
"""

# ruff: noqa: T201 - this file is a CLI entry point and stdout IS its interface.
# ruff.toml exempts **/cli.py for exactly this reason; these scripts are the same
# shape under a different name, and a report nobody can read is not a control.

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]

DEFAULT_LOCK = REPO_ROOT / "verticals/mainline/fixtures/corpus/corpus.lock.json"
DEFAULT_ATTESTATION = REPO_ROOT / "packages/trappoint-sql/g1-attestation.json"
CAMERA_STRINGS = REPO_ROOT / "verticals/mainline/demo/script/CAMERA-STRINGS.yaml"
DISCLOSURES = HERE / "disclosures.yaml"
SCHEMA = HERE / "attestation.schema.json"
FIXTURE_LOCK = HERE / "fixtures/corpus.lock.fixture.json"
FIXTURE_ATTESTATION = HERE / "fixtures/g1-attestation.fixture.json"
DEFAULT_OUT = HERE / "card.html"

LOCK_OWNER = "the corpus-freeze-load worker (`corpusgen freeze`)"
ATTESTATION_OWNER = "the G1 day-1 verification run"

REQUIRED_NOT_BUILT = "M14"
REQUIRED_LIMIT = "rubber-stamp"

#: Seven or more hex characters in a row. Matches the repository-wide claim-hygiene
#: rule, so a card this program writes can never fail that scan.
HEXRUN = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{7,}(?![0-9a-fA-F])")
#: A dashed UUID is derived and quotable; a commit id is not. Masked before the scan.
UUID_SHAPE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")

STATUS_IS_A_PASS = {"PASS"}
STATUS_IS_NOT_A_PASS = {"FAIL", "ABSENT", "SKIPPED"}


class Missing(Exception):
    """An input, or a path inside one, that the card needs and does not have."""


# ── the provenance ledger ────────────────────────────────────────────────────


@dataclass(slots=True)
class Entry:
    label: str
    value: Any
    source: str


@dataclass(slots=True)
class Ledger:
    """Every value the card prints, with where it came from.

    Not bookkeeping for its own sake: the claim "no number here was typed by hand"
    is only checkable if the card carries its own provenance, so the ledger is
    rendered into the artefact as a fine-print table and emitted by ``--json`` for
    the test suite to walk.
    """

    entries: list[Entry] = field(default_factory=list)

    def record(self, label: str, value: Any, source: str) -> Any:
        self.entries.append(Entry(label=label, value=value, source=source))
        return value

    def as_json(self) -> list[dict[str, Any]]:
        return [{"label": e.label, "value": e.value, "source": e.source} for e in self.entries]


def fact(document: Any, path: str, *, origin: str) -> Any:
    """Fetch ``path`` (dotted) out of ``document`` or raise, naming the path.

    A default here would be a lie with a shape: the card would render a plausible
    zero and nobody would learn the input never carried the value.
    """
    node: Any = document
    for part in path.split("."):
        if isinstance(node, list):
            try:
                node = node[int(part)]
                continue
            except (ValueError, IndexError) as exc:
                raise Missing(f"{origin}: no element {part!r} on the way to {path!r}") from exc
        if not isinstance(node, dict) or part not in node:
            raise Missing(f"{origin}: missing required path {path!r}")
        node = node[part]
    return node


def maybe(document: Any, path: str) -> Any | None:
    try:
        return fact(document, path, origin="")
    except Missing:
        return None


# ── inputs ───────────────────────────────────────────────────────────────────


def _read_json(path: Path, owner: str, flag: str) -> dict[str, Any]:
    if not path.is_file():
        raise Missing(
            f"{path.relative_to(REPO_ROOT).as_posix()} does not exist. It is produced by "
            f"{owner}. Pass --allow-fixtures for a clearly-marked stand-in card, or point "
            f"{flag} at the real artefact."
        )
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Missing(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise Missing(f"{path.name} is not a JSON object")
    return loaded


def _read_yaml(path: Path, what: str) -> dict[str, Any]:
    if not path.is_file():
        raise Missing(f"{path.relative_to(REPO_ROOT).as_posix()} does not exist ({what})")
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - PyYAML is a declared dep
        raise Missing(f"PyYAML is required to read {path.name}") from exc
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise Missing(f"{path.name} is not a mapping")
    return loaded


def validate_attestation(document: dict[str, Any]) -> list[str]:
    """Validate against the shipped schema, and say so when the check was weaker.

    ``jsonschema`` is a declared dependency of ``mainline-corpus``. When it is not
    importable the structural fallback runs instead and the returned note says so —
    a validation that silently degraded is indistinguishable from one that passed,
    which is the failure mode this entire file exists to avoid.

    The note it returns is a **run note**, not a card note, and the difference is
    load-bearing rather than tidy. A card note describes the *inputs* and belongs in
    the artefact; a run note describes the *toolchain* and must not, because a card
    whose bytes change with which optional packages happen to be installed makes
    ``--check`` fail on a clean checkout for a reason that has nothing to do with
    the card. Determinism of the artefact is the point; the operator still learns
    that the validation was weaker, on stderr and in ``--json``.
    """
    notes: list[str] = []
    required = (
        "attestation_version",
        "gate",
        "generated_at",
        "generated_by",
        "cluster",
        "capabilities",
        "unmeasured",
    )
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        notes.append(
            "attestation validated STRUCTURALLY only — jsonschema is not importable, so "
            "attestation.schema.json was not applied"
        )
        for key in required:
            if key not in document:
                # `from None`: the ImportError is not the diagnosis. The diagnosis is
                # that the attestation is missing a key, and chaining an unrelated
                # import failure onto it would send a reader looking in the wrong place.
                raise Missing(f"attestation is missing required key {key!r}") from None
        return notes

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "<root>"
        raise Missing(f"attestation fails attestation.schema.json at {where}: {first.message}")
    return notes


# ── rendering helpers ────────────────────────────────────────────────────────


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _cell(text: str, source: str) -> str:
    return f'<li data-source="{_e(source)}">{text}</li>'


def _tidy(value: Any) -> str:
    """Collapse a folded YAML block into one line of prose."""
    return " ".join(str(value).split())


# ── the card ─────────────────────────────────────────────────────────────────


def build_card(  # noqa: PLR0912, PLR0915 - one linear render; splitting it hides the order
    lock: dict[str, Any],
    attestation: dict[str, Any],
    camera: dict[str, Any],
    disclosures: dict[str, Any],
    ledger: Ledger,
    *,
    notes: list[str],
) -> str:
    # Short handles for the four provenance origins; they appear in every source string.
    lock_src, att_src = "corpus.lock.json", "g1-attestation.json"
    cam_src, dis_src = "CAMERA-STRINGS.yaml", "disclosures.yaml"

    def lf(path: str, label: str) -> Any:
        return ledger.record(label, fact(lock, path, origin=lock_src), f"{lock_src}#{path}")

    def af(path: str, label: str) -> Any:
        return ledger.record(label, fact(attestation, path, origin=att_src), f"{att_src}#{path}")

    def cf(path: str, label: str) -> Any:
        return ledger.record(label, fact(camera, path, origin=cam_src), f"{cam_src}#{path}")

    def df(path: str, label: str) -> Any:
        return ledger.record(label, fact(disclosures, path, origin=dis_src), f"{dis_src}#{path}")

    lock_is_fixture = bool(lock.get("_fixture", False))
    att_is_fixture = bool(attestation.get("_fixture", False))

    # ── REAL ─────────────────────────────────────────────────────────────────
    product = af("cluster.product", "cluster product")
    edition = af("cluster.edition", "cluster edition")
    version = af("cluster.version", "cluster version")
    tier = af("cluster.tier", "cluster tier")
    db_region = af("cluster.cloud_region", "database region")
    gate = af("gate", "attestation gate")
    generated_at = af("generated_at", "attestation date")

    capabilities = af("capabilities", "probed capabilities")
    if not isinstance(capabilities, dict) or not capabilities:
        raise Missing("the attestation probed no capabilities")
    n_probed = ledger.record(
        "capabilities probed", len(capabilities), f"{att_src}#capabilities|length"
    )
    n_pass = ledger.record(
        "capabilities measured PASS",
        sum(1 for c in capabilities.values() if str(c.get("status")) in STATUS_IS_A_PASS),
        f"{att_src}#capabilities[status=PASS]",
    )
    n_not_pass = ledger.record(
        "capabilities measured FAIL, ABSENT or SKIPPED",
        sum(1 for c in capabilities.values() if str(c.get("status")) in STATUS_IS_NOT_A_PASS),
        f"{att_src}#capabilities[status in FAIL,ABSENT,SKIPPED]",
    )
    n_open = ledger.record(
        "questions recorded as unmeasured",
        len(af("unmeasured.known_open", "open questions")),
        f"{att_src}#unmeasured.known_open|length",
    )

    # Residency: the attestation wins; disclosures.yaml is the standing fallback.
    inference_region = maybe(attestation, "inference.region")
    if inference_region is not None:
        inf_region = ledger.record(
            "inference region", inference_region, f"{att_src}#inference.region"
        )
        inf_label = maybe(attestation, "inference.provider") or "the model provider"
        residency_statement = _tidy(df("residency.statement", "residency statement"))
        residency_src = f"{att_src}#inference.region + {dis_src}#residency.statement"
    else:
        inf_region = df("residency.inference_region", "inference region")
        inf_label = df("residency.inference_region_label", "inference region label")
        residency_statement = _tidy(df("residency.statement", "residency statement"))
        residency_src = f"{dis_src}#residency ({df('residency.source', 'residency source')})"
        notes.append(
            "the attestation carries no `inference` block, so the residency split was read "
            "from disclosures.yaml on the authority of ADR 0002 F5"
        )
    if df("residency.end_to_end_australian", "end-to-end AU residency") is not False:
        raise Missing(
            "disclosures.yaml claims end-to-end Australian residency. ADR 0002 F5 measured the "
            "database in aws-ap-southeast-1; this card will not print that claim."
        )

    # gc.ttlseconds: same precedence, and the arithmetic is done here, not typed.
    measured_ttl = maybe(attestation, "cluster.gc_ttlseconds")
    if measured_ttl is not None:
        gc_ttl = int(
            ledger.record("gc.ttlseconds", measured_ttl, f"{att_src}#cluster.gc_ttlseconds")
        )
        ttl_src = f"{att_src}#cluster.gc_ttlseconds"
    else:
        gc_ttl = int(df("time_travel.gc_ttlseconds", "gc.ttlseconds"))
        ttl_src = f"{dis_src}#time_travel ({df('time_travel.source', 'gc.ttlseconds source')})"
        notes.append(
            "the attestation carries no `cluster.gc_ttlseconds`, so the time-travel window "
            "was read from disclosures.yaml on the authority of ADR 0002 GT-07"
        )
    gc_minutes = ledger.record("time-travel window, minutes", gc_ttl // 60, f"{ttl_src} ÷ 60")
    time_travel_statement = _tidy(df("time_travel.statement", "time-travel statement"))

    # ── SYNTHETIC ────────────────────────────────────────────────────────────
    seed = lf("seed", "corpus seed")
    generator = lf("generator_version", "generator version")
    n_sites = int(lf("counts.site", "sites"))
    n_people = int(lf("counts.person", "people"))
    n_docs = int(lf("counts.doc", "documents"))
    n_clauses = int(lf("counts.clause", "clauses"))
    n_versions = int(lf("counts.clause_version", "clause versions"))
    n_events = int(lf("counts.event", "events"))
    n_edges = int(lf("counts.blame_edge", "blame edges"))
    sev4 = int(lf("severity_histogram.4", "severity-4 events"))
    sev5 = int(lf("severity_histogram.5", "severity-5 events"))

    authored = int(lf("renderer_census.authored", "documents rendered: authored"))
    by_model = int(lf("renderer_census.bedrock", "documents rendered: by a model"))
    templated = int(lf("renderer_census.template", "documents rendered: template"))
    authored_words = int(lf("renderer_census.authored_words", "hand-authored words"))
    model_words = int(lf("renderer_census.bedrock_words", "model-written words"))
    on_camera_tier = lf("renderer_census.on_camera_tier", "on-camera renderer tier")

    encoder = lf("embeddings.encoder_id", "embedding encoder")
    dims = int(lf("embeddings.target_dimension", "embedding dimension"))
    dtype = lf("embeddings.dtype_on_disk", "embedding dtype on disk")

    census_total = authored + by_model + templated
    if census_total <= 0:
        raise Missing("the renderer census sums to zero — the corpus rendered nothing")
    model_share = ledger.record(
        "share of documents written by a model, %",
        round(by_model / census_total * 100, 1),
        f"{lock_src}#renderer_census (bedrock ÷ total)",
    )
    if on_camera_tier != "authored":
        raise Missing(
            f"renderer_census.on_camera_tier is {on_camera_tier!r}. Every word on camera comes "
            "from the authored tier; a card saying otherwise would be accurate and the film "
            "would be wrong, which is not a trade this program makes."
        )

    # ── STAGED ───────────────────────────────────────────────────────────────
    permit_ref = lf("demo_row.permit_external_ref", "staged permit")
    permit_state = lf("demo_row.expected_state", "staged permit state")
    open_blocking = lf("demo_row.expected_open_blocking", "staged permit open_blocking")
    commit_message = cf("commit_message_2013", "the 2013 commit message")
    incident_ref = cf("incident_ref", "the incident reference")
    operator = cf("operator", "the fictional operator")
    watermark = cf("banners.watermark", "the watermark")

    # ── NOT BUILT YET ────────────────────────────────────────────────────────
    att_not_built = maybe(attestation, "not_built")
    if isinstance(att_not_built, list) and att_not_built:
        not_built = ledger.record("not-built-yet items", len(att_not_built), f"{att_src}#not_built")
        nby_rows = att_not_built
        nby_src = f"{att_src}#not_built"
    else:
        nby_rows = df("not_built_yet", "not-built-yet list")
        not_built = ledger.record("not-built-yet items", len(nby_rows), f"{dis_src}#not_built_yet")
        nby_src = f"{dis_src}#not_built_yet"
        notes.append(
            "the attestation carries no `not_built` list, so the fourth column was read from "
            "disclosures.yaml"
        )
    ids = {str(item.get("id", "")) for item in nby_rows if isinstance(item, dict)}
    if REQUIRED_NOT_BUILT not in ids:
        raise Missing(
            f"the fourth column does not name {REQUIRED_NOT_BUILT} (SHEPARD). BUILD_PLAN §5.1 "
            "puts it in NOT-BUILT-YET explicitly, and finding S3 exists because an earlier "
            "script filmed it. This card will not render without it."
        )

    limits = df("limits", "stated limits")
    limit_ids = [str(item.get("id", "")) for item in limits if isinstance(item, dict)]
    if REQUIRED_LIMIT not in limit_ids:
        raise Missing(
            f"disclosures.yaml states no {REQUIRED_LIMIT!r} limit. Naming the limit you cannot "
            "engineer away is the cheapest credibility available in this film."
        )
    rubber = next(item for item in limits if item.get("id") == REQUIRED_LIMIT)

    # ── the four columns ─────────────────────────────────────────────────────
    real_items = [
        _cell(
            f"Every SQL result on screen executed live against <b>{_e(product)} {_e(edition)} "
            f"{_e(version)}</b>, {_e(tier)} tier, in "
            f"<span class='mono'>{_e(db_region)}</span>.",
            f"{att_src}#cluster",
        ),
        _cell(
            "The refusal is a database constraint — <span class='mono'>23514</span> on "
            "<span class='mono'>gate_closed_when_issued</span> — not application code. "
            "It refuses a cluster admin over raw SQL in the same way.",
            "demo/REFUSAL-STRINGS.yaml#R1-GATE-CLOSED",
        ),
        _cell(
            "The MCP session is CockroachDB's public managed endpoint, read-only, and not our "
            "code. The <span class='mono'>EXPLAIN</span> output is unedited.",
            "demo/REFUSAL-STRINGS.yaml#explain_fragment",
        ),
        _cell(
            f"Model inference runs in <span class='mono'>{_e(inf_region)}</span> "
            f"({_e(inf_label)}). <b>{_e(residency_statement)}</b>",
            residency_src,
        ),
        _cell(
            f"{gate} probe run of {_e(generated_at)}: <b>{n_probed}</b> capabilities probed, "
            f"<b>{n_pass}</b> measured as working, <b>{n_not_pass}</b> measured as failing, "
            f"absent or unmeasurable, and <b>{n_open}</b> questions recorded as unanswered "
            "rather than assumed.",
            f"{att_src}#capabilities, {att_src}#unmeasured",
        ),
    ]

    synthetic_items = [
        _cell(
            f"Operator, sites, people, incidents and documents are generated: "
            f"<b>{n_sites}</b> sites, <b>{n_people}</b> people, <b>{n_docs}</b> documents, "
            f"<b>{n_clauses}</b> clauses across <b>{n_versions}</b> versions.",
            f"{lock_src}#counts",
        ),
        _cell(
            f"<b>{n_events}</b> events and <b>{n_edges}</b> blame edges; <b>{sev4}</b> events at "
            f"severity 4 and <b>{sev5}</b> at severity 5. No real incident and no real person "
            "appears anywhere in this corpus.",
            f"{lock_src}#counts, {lock_src}#severity_histogram",
        ),
        _cell(
            f"Seed <span class='mono'>{_e(seed)}</span>, generator "
            f"<span class='mono'>{_e(generator)}</span>. The corpus regenerates byte-identically "
            "from that seed.",
            f"{lock_src}#seed, {lock_src}#generator_version",
        ),
        _cell(
            f"<b>Renderer census:</b> {authored} authored, {by_model} written by a model, "
            f"{templated} templated — <b>{model_share}%</b> of documents were model-written and "
            f"<b>{model_words}</b> model-written words exist in the corpus. All "
            f"<b>{authored_words}</b> words that appear on camera are hand-authored.",
            f"{lock_src}#renderer_census",
        ),
        _cell(
            f"Embeddings are offline fixtures from <span class='mono'>{_e(encoder)}</span>, "
            f"lifted to {dims} dimensions and stored as {_e(dtype)}. They are not Titan, and "
            "this card says so rather than letting the demo imply otherwise.",
            f"{lock_src}#embeddings",
        ),
    ]

    staged_items = [
        _cell(
            f"Permit <span class='mono'>{_e(permit_ref)}</span> is pre-seeded to "
            f"<span class='mono'>{_e(permit_state)}</span> with "
            f"<span class='mono'>open_blocking = {_e(open_blocking)}</span>, so the beat fits "
            "three minutes.",
            f"{lock_src}#demo_row",
        ),
        _cell(
            f"Ingestion of the {_e(incident_ref)} report ran earlier and is shown at 4x as an "
            "inset. It is sped up, never re-timed or re-ordered.",
            f"{cam_src}#incident_ref",
        ),
        _cell(
            f"<b>{_e(time_travel_statement)}</b> <span class='mono'>gc.ttlseconds</span> is "
            f"<b>{gc_ttl}</b> here — a <b>{gc_minutes}-minute</b> window.",
            ttl_src,
        ),
        _cell(
            f"The 2013 commit message reads <i>“{_e(commit_message)}”</i>. It is authored "
            f"fixture text about a fictional event at {_e(operator)}.",
            f"{cam_src}#commit_message_2013",
        ),
    ]

    nby_items = [
        _cell(
            f"<b>{_e(item.get('name'))}</b> — {_e(item.get('milestone', 'deferred'))}. "
            f"{_e(_tidy(item.get('statement', '')))}",
            nby_src,
        )
        for item in nby_rows
        if isinstance(item, dict)
    ]

    limit_rows = "\n".join(
        f"<tr><td class='mono'>{_e(item.get('id'))}</td>"
        f"<td>{_e(_tidy(item.get('statement', '')))}</td>"
        f"<td>{_e(_tidy(item.get('what_we_do_instead', '')))}</td></tr>"
        for item in limits
        if isinstance(item, dict)
    )

    provenance_rows = "\n".join(
        f"<tr><td>{_e(e.label)}</td><td class='mono'>{_e(e.value)}</td>"
        f"<td class='mono src'>{_e(e.source)}</td></tr>"
        for e in ledger.entries
    )

    banner = ""
    if lock_is_fixture or att_is_fixture:
        which = [
            n
            for n, on in (("corpus lock", lock_is_fixture), ("G1 attestation", att_is_fixture))
            if on
        ]
        banner = (
            "<div class='banner'>NOT FOR CAMERA — built from a fixture "
            f"({_e(' and '.join(which))}). Regenerate against the frozen corpus and a real "
            "probe run before capture.</div>"
        )

    note_block = ""
    if notes:
        note_block = "<ul class='notes'>" + "".join(f"<li>{_e(n)}</li>" for n in notes) + "</ul>"

    return f"""<!DOCTYPE html>
<meta charset="utf-8">
<title>MAINLINE — real / synthetic / staged / not built yet</title>
<!--
  GENERATED by verticals/mainline/demo/honesty/gen_card.py. Do not hand-edit.
  Every value is traceable: the provenance table at the foot of this document
  lists each one with the exact path it was read from.
-->
<style>
  :root {{
    --paper:#FAF8F3; --ink:#171310; --rule:#D8D0C2; --accent:#8C1D18; --muted:#6B6156;
    --mono:"JetBrains Mono","Cascadia Mono","DejaVu Sans Mono",ui-monospace,monospace;
    --ui:Inter,"Segoe UI",system-ui,-apple-system,"Helvetica Neue",sans-serif;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink); font-family:var(--ui);
         font-size:15px; line-height:1.45; }}
  .sheet {{ width:1920px; min-height:1080px; padding:52px 60px; margin:0 auto; }}
  @media (max-width:1980px) {{ .sheet {{ width:100%; }} }}
  h1 {{ font-size:30px; margin:0 0 4px; letter-spacing:-0.01em; }}
  .sub {{ color:var(--muted); font-size:15px; margin:0 0 20px; }}
  .banner {{ background:var(--accent); color:#fff; font-weight:700; letter-spacing:.02em;
             padding:12px 18px; margin:0 0 18px; font-family:var(--mono); font-size:15px; }}
  .cols {{ display:grid; grid-template-columns:repeat(4,1fr); gap:22px; align-items:start; }}
  .col {{ border-top:3px solid var(--rule); padding-top:14px; }}
  .col.real {{ border-top-color:var(--ink); }}
  .col.nby {{ border-top-color:var(--accent); }}
  .col h2 {{ font-size:14px; letter-spacing:.14em; text-transform:uppercase; margin:0 0 10px; }}
  .col.nby h2 {{ color:var(--accent); }}
  ul {{ margin:0; padding-left:18px; }}
  li {{ margin:0 0 10px; }}
  .mono {{ font-family:var(--mono); font-size:.94em; }}
  .limits {{ margin-top:28px; border-top:3px solid var(--accent); padding-top:14px; }}
  .limits h2 {{ font-size:14px; letter-spacing:.14em; text-transform:uppercase;
                margin:0 0 8px; color:var(--accent); }}
  table {{ border-collapse:collapse; width:100%; }}
  td, th {{ text-align:left; vertical-align:top; padding:5px 12px 5px 0;
            border-bottom:1px solid var(--rule); }}
  .headline {{ font-size:19px; margin:6px 0 14px; }}
  .prov {{ margin-top:30px; color:var(--muted); font-size:12px; }}
  .prov h2 {{ font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }}
  .src {{ word-break:break-all; }}
  .notes li {{ color:var(--accent); }}
  .mark {{ margin-top:24px; font-family:var(--mono); font-size:13px; color:var(--muted);
           letter-spacing:.06em; }}
</style>
<div class="sheet">
{banner}
  <h1>What is real, what is synthetic, what is staged, and what is not built yet</h1>
  <p class="sub">Generated from <span class="mono">corpus.lock.json</span> and the
     {gate} ground-truth attestation. No number on this card was typed by hand.</p>
{note_block}
  <div class="cols">
    <div class="col real"><h2>Real</h2><ul>{"".join(real_items)}</ul></div>
    <div class="col"><h2>Synthetic</h2><ul>{"".join(synthetic_items)}</ul></div>
    <div class="col"><h2>Staged</h2><ul>{"".join(staged_items)}</ul></div>
    <div class="col nby"><h2>Not built yet ({not_built})</h2><ul>{"".join(nby_items)}</ul></div>
  </div>

  <div class="limits" id="limits">
    <h2>The limits we cannot engineer away</h2>
    <p class="headline"><b>{_e(_tidy(rubber.get("statement", "")))}</b>
       {_e(_tidy(rubber.get("what_we_do_instead", "")))}</p>
    <table>
      <tr><th>Limit</th><th>What is not claimed</th><th>What we do instead</th></tr>
      {limit_rows}
    </table>
  </div>

  <div class="prov">
    <h2>Provenance — every value on this card, and where it was read from</h2>
    <table>
      <tr><th>Value</th><th>Rendered</th><th>Source</th></tr>
      {provenance_rows}
    </table>
  </div>

  <p class="mark">{_e(watermark)}</p>
</div>
"""


# ── entry point ──────────────────────────────────────────────────────────────


def generate(
    *, lock_path: Path, attestation_path: Path, allow_fixtures: bool
) -> tuple[str, Ledger, bool, list[str]]:
    # Card notes describe the INPUTS and are rendered into the artefact. Run notes
    # describe the TOOLCHAIN and are printed only — see validate_attestation.
    notes: list[str] = []
    run_notes: list[str] = []
    if allow_fixtures and not lock_path.is_file():
        lock_path = FIXTURE_LOCK
        notes.append("corpus lock substituted from the shipped fixture")
    if allow_fixtures and not attestation_path.is_file():
        attestation_path = FIXTURE_ATTESTATION
        notes.append("G1 attestation substituted from the shipped fixture")

    lock = _read_json(lock_path, LOCK_OWNER, "--lock")
    attestation = _read_json(attestation_path, ATTESTATION_OWNER, "--attestation")
    run_notes.extend(validate_attestation(attestation))
    camera = _read_yaml(CAMERA_STRINGS, "the on-camera prose")
    disclosures = _read_yaml(DISCLOSURES, "the fourth column and the limits")

    ledger = Ledger()
    card = build_card(lock, attestation, camera, disclosures, ledger, notes=notes)
    notes = notes + run_notes

    stray = HEXRUN.search(UUID_SHAPE.sub("<uuid>", card))
    if stray:
        raise Missing(
            f"the rendered card contains the hex literal {stray.group(0)!r}. A commit id is a "
            "sha256 over the JCS envelope that nobody can choose in advance, so no digest is "
            "written on this card."
        )
    is_fixture = bool(lock.get("_fixture")) or bool(attestation.get("_fixture"))
    return card, ledger, is_fixture, notes


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911 - one return per exit code
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--attestation", type=Path, default=DEFAULT_ATTESTATION)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--allow-fixtures",
        action="store_true",
        help="substitute shipped stand-ins for missing inputs; the card says so and exits 3",
    )
    parser.add_argument("--check", action="store_true", help="fail if the committed card is stale")
    parser.add_argument("--json", action="store_true", help="print the provenance ledger")
    args = parser.parse_args(argv)

    try:
        card, ledger, is_fixture, notes = generate(
            lock_path=args.lock,
            attestation_path=args.attestation,
            allow_fixtures=args.allow_fixtures,
        )
    except Missing as exc:
        print(f"gen_card: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps({"fixture": is_fixture, "notes": notes, "facts": ledger.as_json()}, indent=2)
        )
        return 3 if is_fixture else 0

    if args.check:
        if not args.out.is_file():
            print(f"gen_card: {args.out.name} does not exist", file=sys.stderr)
            return 1
        if args.out.read_text(encoding="utf-8") != card:
            print(f"gen_card: {args.out.name} is stale — regenerate it", file=sys.stderr)
            return 1
        print(f"{args.out.name} is current ({len(ledger.entries)} traced values)")
        return 3 if is_fixture else 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(card, encoding="utf-8")
    for note in notes:
        print(f"note: {note}", file=sys.stderr)
    print(
        f"wrote {args.out.relative_to(REPO_ROOT).as_posix()} — {len(ledger.entries)} traced values"
    )
    if is_fixture:
        print("BUILT FROM A FIXTURE — not for camera", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
