# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1b's own completion test, runnable with nothing else in the repository built.

``corpus-blame-key``'s ``done_when`` reads: *gs0.jsonl validates against gs0.schema.json; counts
satisfy negative_controls >= 200, decoys == 60, fleet_sibling_groups == 9, orphans == 12,
weakening_chains == 4; zero rows with basis='inferred_semantic' and state='active'; every true
edge carries a non-empty generative_reason; two runs byte-identical.*

Every one of those is a property of the emitted bytes, so every one of them is checked here::

    python -m mainline_corpus.blame.verify --repo-root .

The answer key is generated twice into throwaway directories and then **read back off disk**.
That distinction is the point: ``causality.py`` already re-checks basis-graded force over its own
objects, but a serialisation bug, a sort-key collision or a float that does not round-trip is
invisible from there and fatal downstream.  Everything below parses files.

── What is checked, and why each one is load-bearing ─────────────────────────────────────────

``BK-REPRO-*``  two generations agree file for file; LF-only UTF-8; every JSONL line equals its
                own canonical serialisation; every file strictly ascending under its declared
                sort key.
``BK-SCHEMA-*`` every ``gs0.jsonl`` row validates against the shipped schema — and the validator
                is shown to reject four specific malformed rows, because a validator that never
                rejects anything is a validator nobody should trust.
``BK-FORCE-*``  ``inference_never_blocks``, ``asserted_needs_quote`` and
                ``human_needs_signature`` re-derived from the emitted rows.  These are shipped
                ``CHECK`` constraints; a corpus that violates one is a corpus the loader refuses.
``BK-COUNT-*``  the injector counts the brief quotes, and the blame-edge ratio as a band.
``BK-SPINE-*``  one clause_uuid across 2011, 2013, 2016 and 2019; the labels ``anchors.yaml``
                declares; 150 then 135; one asserted, active edge to INC-2013-044; and the 2026
                weakening present as a PROPOSAL and absent from merged history.
``BK-PROJ-*``   no emitted row names a projected column, re-derived from the denylist rather
                than trusting the emitter that wrote the file; the pending register reconciles.
``BK-REF-*``    the published identity contract — ``sid("clause", clause_key)`` and friends —
                recomputed for every row, and every gold pair resolving to a real event.
``BK-TRACE-*``  the documentary-trace rate inside its band, and ``channel_a_visible`` true
                exactly when the basis is ``asserted_document``.
``BK-DECOY-01`` every decoy really does differ in hazard energy and failed control class.
``BK-DRIFT-01`` the drift set is honest: it contains pairs that DO share a content token.
``BK-SRC-01``   an AST scan of this lane for a wall clock, an unseeded PRNG, a uuid4 or Faker.

A ``warn`` records something the corpus cannot currently prove.  Nothing here upgrades a warn to
a pass on its own.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .. import gazetteer as gaz
from .. import rng
from ..skeleton.emit import canonical_json, projected_columns
from . import build, params

__all__ = ["Check", "Report", "main", "render", "run", "validate", "verify_answer_key"]

COMMAND = "blame-verify"
NAME = COMMAND
HELP = "Verify stage 1b: reproducibility, the schema, basis-graded force, the counts, the spine."

OUTCOME_OK: Final[str] = "pass"
OUTCOME_FAIL: Final[str] = "fail"
OUTCOME_WARN: Final[str] = "warn"

MAX_PROBLEMS_SHOWN: Final[int] = 5

FORBIDDEN_CALLS: Final[frozenset[str]] = frozenset(
    {
        "datetime.now",
        "datetime.utcnow",
        "datetime.today",
        "dt.datetime.now",
        "dt.datetime.utcnow",
        "dt.datetime.today",
        "date.today",
        "dt.date.today",
        "time.time",
        "time.time_ns",
        "time.monotonic",
        "os.urandom",
        "secrets.token_bytes",
        "secrets.token_hex",
        "uuid.uuid1",
        "uuid.uuid4",
        "random.random",
        "random.randint",
        "random.randrange",
        "random.choice",
        "random.choices",
        "random.shuffle",
        "random.sample",
        "random.gauss",
        "random.uniform",
        "random.seed",
        "random.expovariate",
    }
)
FORBIDDEN_IMPORTS: Final[frozenset[str]] = frozenset({"faker", "mimesis"})


@dataclass(frozen=True, slots=True)
class Check:
    check_id: str
    title: str
    status: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == OUTCOME_OK


@dataclass(frozen=True, slots=True)
class Report:
    checks: tuple[Check, ...]
    counts: Mapping[str, int]
    tree_sha256: str
    generator_version: str
    blame_ratio: float

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if check.status == OUTCOME_FAIL)

    @property
    def warnings(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if check.status == OUTCOME_WARN)

    def exit_code(self, *, strict: bool = False) -> int:
        if self.failures:
            return 1
        if strict and self.warnings:
            return 1
        return 0


@dataclass(frozen=True, slots=True)
class _Tree:
    root: Path
    raw: Mapping[str, bytes]
    rows: Mapping[str, tuple[Mapping[str, Any], ...]]
    docs: Mapping[str, Any]
    index: Mapping[str, Any]
    digests: Mapping[str, str]

    def table(self, filename: str) -> tuple[Mapping[str, Any], ...]:
        try:
            return self.rows[filename]
        except KeyError as exc:  # pragma: no cover - only on a truncated build
            raise KeyError(f"{filename} is absent from {self.root}") from exc


def _ok(check_id: str, title: str, detail: str) -> Check:
    return Check(check_id=check_id, title=title, status=OUTCOME_OK, detail=detail)


def _bad(check_id: str, title: str, detail: str) -> Check:
    return Check(check_id=check_id, title=title, status=OUTCOME_FAIL, detail=detail)


def _verdict(check_id: str, title: str, problems: Sequence[str], clean: str) -> Check:
    if problems:
        shown = "; ".join(problems[:MAX_PROBLEMS_SHOWN])
        remainder = len(problems) - MAX_PROBLEMS_SHOWN
        more = f" (+{remainder} more)" if remainder > 0 else ""
        return _bad(check_id, title, f"{len(problems)} problem(s): {shown}{more}")
    return _ok(check_id, title, clean)


def _read_tree(root: Path) -> _Tree:
    raw: dict[str, bytes] = {}
    rows: dict[str, tuple[Mapping[str, Any], ...]] = {}
    docs: dict[str, Any] = {}
    digests: dict[str, str] = {}
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix == ".license":
            continue
        payload = path.read_bytes()
        raw[path.name] = payload
        digests[path.name] = hashlib.sha256(payload).hexdigest()
        if path.suffix == ".jsonl":
            text = payload.decode("utf-8")
            rows[path.name] = tuple(json.loads(line) for line in text.splitlines() if line.strip())
        elif path.suffix == ".json":
            docs[path.name] = json.loads(payload.decode("utf-8"))
    if "index.json" not in docs:
        raise FileNotFoundError(
            f"{root} has no index.json. The emitter writes it last, so its absence means the "
            "build died partway and the tree is incomplete rather than plausibly complete."
        )
    return _Tree(
        root=root, raw=raw, rows=rows, docs=docs, index=docs["index.json"], digests=digests
    )


# ── BK-REPRO ─────────────────────────────────────────────────────────────────────────────────


def _check_reproducible(first: _Tree, second: _Tree) -> Check:
    title = "two independent generations are byte-identical"
    only_first = sorted(set(first.digests) - set(second.digests))
    only_second = sorted(set(second.digests) - set(first.digests))
    if only_first or only_second:
        return _bad(
            "BK-REPRO-01",
            title,
            f"file sets differ: only in run A {only_first}, only in run B {only_second}",
        )
    differing = sorted(
        name for name, digest in first.digests.items() if second.digests[name] != digest
    )
    if differing:
        return _bad("BK-REPRO-01", title, f"{len(differing)} file(s) differ: {differing[:5]}")
    return _ok(
        "BK-REPRO-01", title, f"{len(first.digests)} files, every sha256 equal across both runs"
    )


def _check_bytes(tree: _Tree) -> Check:
    title = "LF-only, UTF-8, newline-terminated, canonically serialised"
    problems: list[str] = []
    checked = 0
    for name, payload in sorted(tree.raw.items()):
        if b"\r" in payload:
            problems.append(f"{name} contains CR")
        if payload and not payload.endswith(b"\n"):
            problems.append(f"{name} does not end with a newline")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{name} is not valid UTF-8")
            continue
        if not name.endswith(".jsonl"):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            checked += 1
            if canonical_json(json.loads(line)) != line:
                problems.append(f"{name}:{number} is not key-sorted, tight-separator JSON")
                break
    return _verdict(
        "BK-REPRO-02",
        title,
        problems,
        f"{len(tree.raw)} files, {checked} rows re-serialising to identical bytes",
    )


def _check_sort_order(tree: _Tree) -> Check:
    title = "rows are strictly ascending under the declared sort key"
    problems: list[str] = []
    for spec in build._SPECS:  # the specs are the declaration; re-stating them here would drift
        rows = tree.rows.get(spec.filename)
        if rows is None:
            problems.append(f"{spec.filename} is absent")
            continue
        keys = [spec.sort_key(row) for row in rows]
        for position in range(1, len(keys)):
            if keys[position] <= keys[position - 1]:
                problems.append(f"{spec.filename}[{position}] does not exceed its predecessor")
                break
    return _verdict(
        "BK-REPRO-03",
        title,
        problems,
        f"{len(build._SPECS)} files, each a total order (no tie can leak emission order)",
    )


# ── BK-SCHEMA ────────────────────────────────────────────────────────────────────────────────


def validate(instance: object, schema: Mapping[str, Any], *, path: str = "$") -> list[str]:
    """Walk the JSON Schema keywords ``gs0.schema.json`` actually uses, and list the violations.

    Written here rather than pulled in as a dependency, for the same reason the recall lane
    writes its own: a schema check that cannot run because a library is missing is a schema check
    that does not run, and the corpus package must be verifiable from a bare checkout.
    """
    errors: list[str] = []
    branches = schema.get("anyOf")
    if isinstance(branches, list):
        if all(validate(instance, branch, path=path) for branch in branches):
            errors.append(f"{path}: matches no branch of anyOf")
        rest = {key: value for key, value in schema.items() if key != "anyOf"}
        if rest:
            errors.extend(validate(instance, rest, path=path))
        return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
    expected = schema.get("type")
    if isinstance(expected, str):
        types: Mapping[str, type | tuple[type, ...]] = {
            "object": dict,
            "array": list,
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "null": type(None),
        }
        wanted = types[expected]
        numeric = expected in ("integer", "number")
        if not isinstance(instance, wanted) or (numeric and isinstance(instance, bool)):
            errors.append(f"{path}: expected {expected}, got {type(instance).__name__}")
            return errors
    if isinstance(instance, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if isinstance(minimum, int) and len(instance) < minimum:
            errors.append(f"{path}: shorter than minLength {minimum}")
        if isinstance(maximum, int) and len(instance) > maximum:
            errors.append(f"{path}: longer than maxLength {maximum}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        low = schema.get("minimum")
        high = schema.get("maximum")
        if isinstance(low, (int, float)) and instance < low:
            errors.append(f"{path}: {instance} < minimum {low}")
        if isinstance(high, (int, float)) and instance > high:
            errors.append(f"{path}: {instance} > maximum {high}")
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []) or []:
            if name not in instance:
                errors.append(f"{path}: missing required property {name!r}")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: additional property {key!r} is not allowed")
        for key, value in instance.items():
            subschema = properties.get(key)
            if isinstance(subschema, dict):
                errors.extend(validate(value, subschema, path=f"{path}.{key}"))
    return errors


def _check_schema(tree: _Tree) -> Check:
    title = "every GS0 row validates against the shipped schema"
    schema = tree.docs.get("gs0.schema.json")
    if schema is None:
        return _bad("BK-SCHEMA-01", title, "gs0.schema.json is absent")
    problems: list[str] = []
    rows = tree.table("gs0.jsonl")
    for position, row in enumerate(rows):
        found = validate(row, schema, path=f"gs0.jsonl:{position + 1}")
        problems.extend(found)
        if len(problems) > MAX_PROBLEMS_SHOWN * 2:
            break
    return _verdict("BK-SCHEMA-01", title, problems, f"{len(rows)} rows, no violation")


def _check_schema_bites(tree: _Tree) -> Check:
    """Show the validator rejecting four specific malformations, not merely accepting good rows."""
    title = "the schema walk actually rejects malformed rows"
    schema = tree.docs.get("gs0.schema.json")
    rows = tree.table("gs0.jsonl")
    if schema is None or not rows:
        return _bad("BK-SCHEMA-02", title, "no schema or no rows to mutate")
    good = dict(next(row for row in rows if row["label"] == "true"))
    problems: list[str] = []
    cases = {
        "a true row with no basis": {**good, "basis": None},
        "a true row labelled decoy without decoy_of": {**good, "label": "decoy"},
        "an out-of-range severity": {**good, "severity_gate": 9},
        "an unexpected column": {**good, "surprise": 1},
        "an empty generative_reason": {**good, "generative_reason": ""},
    }
    for name, mutated in cases.items():
        if not validate(mutated, schema):
            problems.append(f"the walk accepted {name}")
    if validate(good, schema):
        problems.append("the walk rejected an unmodified row")
    return _verdict(
        "BK-SCHEMA-02", title, problems, f"{len(cases)} malformations rejected, the original kept"
    )


# ── BK-FORCE ─────────────────────────────────────────────────────────────────────────────────


def _check_basis_graded_force(tree: _Tree) -> Check:
    title = "basis-graded force holds over the emitted rows (three shipped CHECKs)"
    edges = tree.table("blame_edge.jsonl")
    registry = {
        (str(row["clause_uuid"]), str(row["event_ref"]), str(row["basis"])): row
        for row in tree.table("blame_edge_registry.jsonl")
    }
    problems: list[str] = []
    active_inferred = [
        row
        for row in edges
        if str(row["basis"]) == "inferred_semantic" and str(row["state"]) == "active"
    ]
    problems.extend(
        f"{row['clause_uuid']}/{row['event_id']} is inferred_semantic and active"
        for row in active_inferred
    )
    for row in edges:
        basis = str(row["basis"])
        if basis == "asserted_document" and row.get("evidence_doc_id") is None:
            problems.append(f"{row['clause_uuid']}: asserted_document with no evidence document")
        if basis == "asserted_human" and row.get("reviewed_by") is None:
            problems.append(f"{row['clause_uuid']}: asserted_human naming no reviewer")
        if basis not in ("asserted_document", "asserted_human") and row.get("state") == "active":
            problems.append(f"{row['clause_uuid']}: {basis} is active without a calibrated p_link")
    quoted = 0
    for key, row in registry.items():
        if key[2] == "asserted_document":
            if not row.get("quote_ref"):
                problems.append(f"{key[0]}: asserted_document with no quote_ref")
            else:
                quoted += 1
    return _verdict(
        "BK-FORCE-01",
        title,
        problems,
        f"{len(edges)} edges: 0 active inferences, {quoted} asserted quotes bound to a reference",
    )


def _check_gold_reasons(tree: _Tree) -> Check:
    title = "every gold row carries a non-empty generative reason"
    problems = [
        f"{row['clause_key']}/{row['event_ref']} ({row['label']}) has no generative_reason"
        for row in tree.table("gs0.jsonl")
        if not str(row.get("generative_reason", "")).strip()
    ]
    rows = tree.table("gs0.jsonl")
    return _verdict(
        "BK-FORCE-02",
        title,
        problems,
        f"{len(rows)} rows, every one able to say why it is judged the way it is",
    )


def _check_channel_labels(tree: _Tree) -> Check:
    title = "channel A visibility is exactly the asserted-document population"
    problems: list[str] = []
    for row in tree.table("gs0.jsonl"):
        visible = bool(row["channel_a_visible"])
        basis = row.get("basis")
        if visible and basis != "asserted_document":
            problems.append(f"{row['clause_key']}/{row['event_ref']}: visible with basis {basis!r}")
        if not visible and basis == "asserted_document":
            problems.append(f"{row['clause_key']}/{row['event_ref']}: asserted but invisible")
    visible_count = sum(1 for row in tree.table("gs0.jsonl") if row["channel_a_visible"])
    return _verdict(
        "BK-TRACE-01",
        title,
        problems,
        f"{visible_count} rows resolvable by the citation resolver; the rest are the residue "
        "capture-recapture estimates",
    )


def _check_trace_rate(tree: _Tree) -> Check:
    title = "the documentary-trace rate sits in its declared band"
    mean = float(tree.index["p_doc_trace_mean"])
    low, high = params.P_DOC_TRACE_MEAN_BAND
    if not low <= mean <= high:
        return _bad(
            "BK-TRACE-02",
            title,
            f"realised trace rate {mean:.3f} is outside [{low}, {high}]",
        )
    return _ok(
        "BK-TRACE-02",
        title,
        f"p_doc mean {mean:.3f} in [{low}, {high}] (decision D7 targets ~0.55)",
    )


# ── BK-COUNT ─────────────────────────────────────────────────────────────────────────────────


def _check_counts(tree: _Tree) -> Check:
    title = "the injector counts the brief quotes"
    counts = tree.index["injector_counts"]
    labels = tree.index["gold_label_histogram"]
    problems: list[str] = []
    exact = {
        "decoys": params.DECOY_TARGET,
        "fleet_sibling_groups": params.FLEET_GROUP_TARGET,
        "orphans": params.ORPHAN_TARGET,
        "weakening_chains": params.WEAKENING_CHAIN_TARGET,
        "split_documents": params.SPLIT_DOC_TARGET,
    }
    for name, wanted in exact.items():
        actual = int(counts.get(name, 0))
        if actual != wanted:
            problems.append(f"{name} = {actual}, expected {wanted}")
    negatives = int(labels.get("negative_control", 0))
    if negatives < params.NEGATIVE_CONTROL_FLOOR:
        problems.append(
            f"negative_control rows = {negatives}, floor is {params.NEGATIVE_CONTROL_FLOOR}"
        )
    if int(labels.get("decoy", 0)) != params.DECOY_TARGET:
        problems.append(f"decoy rows = {labels.get('decoy', 0)}")
    if int(labels.get("true", 0)) != len(tree.table("blame_edge.jsonl")):
        problems.append("true rows and blame edges are not one to one")
    ratio = float(tree.index["blame_ratio"])
    if not params.BLAME_RATIO_MIN <= ratio <= params.BLAME_RATIO_MAX:
        problems.append(
            f"blame_edges/clause_versions = {ratio}, outside "
            f"[{params.BLAME_RATIO_MIN}, {params.BLAME_RATIO_MAX}]"
        )
    return _verdict(
        "BK-COUNT-01",
        title,
        problems,
        f"decoys {counts.get('decoys')}, fleet groups {counts.get('fleet_sibling_groups')}, "
        f"orphans {counts.get('orphans')}, chains {counts.get('weakening_chains')}, "
        f"negative controls {negatives}, ratio {ratio}",
    )


def _check_retypeset(tree: _Tree) -> Check:
    title = "one retypeset per document, and identity survives every reflow"
    rows = tree.table("injector_retypeset.jsonl")
    problems: list[str] = []
    per_document: dict[tuple[str, str], set[str]] = {}
    unchanged = 0
    for row in rows:
        per_document.setdefault((str(row["site_code"]), str(row["doc_code"])), set()).add(
            str(row["revision_key"])
        )
        if str(row["g1_printed_label"]) == str(row["g2_printed_label"]):
            unchanged += 1
        if str(rng.sid("clause", str(row["clause_key"]))) != str(row["clause_uuid"]):
            problems.append(f"{row['clause_key']}: uuid is not sid('clause', key)")
    multiple = sorted(key for key, keys in per_document.items() if len(keys) > 1)
    problems.extend(f"{key} was retypeset more than once" for key in multiple)
    if unchanged:
        problems.append(
            f"{unchanged} clause(s) came out of the retypeset with an unchanged printed label; "
            "the reflow would then be a formatting tweak rather than a renumbering"
        )
    return _verdict(
        "BK-COUNT-02",
        title,
        problems,
        f"{len(rows)} clauses across {len(per_document)} documents, every label changed, every "
        "uuid held",
    )


def _check_decoys(tree: _Tree) -> Check:
    title = "every decoy differs in hazard energy and in failed control class"
    problems: list[str] = []
    true_pairs = {
        (str(row["clause_key"]), str(row["event_ref"]))
        for row in tree.table("gs0.jsonl")
        if row["label"] == "true"
    }
    for row in tree.table("injector_decoy.jsonl"):
        if str(row["decoy_hazard_energy"]) == str(row["twin_hazard_energy"]):
            problems.append(f"{row['decoy_event_ref']} shares its twin's hazard energy")
        overlap = set(row["decoy_control_classes"]) & set(row["twin_control_classes"])
        if overlap:
            problems.append(f"{row['decoy_event_ref']} shares failed controls {sorted(overlap)}")
        if not row["shared_assets"]:
            problems.append(f"{row['decoy_event_ref']} shares no asset with its twin")
        if (str(row["clause_key"]), str(row["decoy_event_ref"])) in true_pairs:
            problems.append(f"{row['decoy_event_ref']} is also a true edge on the same clause")
    return _verdict(
        "BK-DECOY-01",
        title,
        problems,
        f"{len(tree.table('injector_decoy.jsonl'))} decoys: same asset and era, different energy "
        "and disjoint failed controls",
    )


def _check_drift(tree: _Tree) -> Check:
    """Require the drift set to be honest about the pairs that DO overlap lexically."""
    title = "the vocabulary-drift set is honest about lexical overlap"
    pairs = tree.table("injector_drift_pair.jsonl")
    schedule = tree.table("injector_vocabulary_drift.jsonl")
    problems: list[str] = []
    if not pairs:
        problems.append("no drift pairs; the lexical-versus-semantic claim is untestable")
    overlapping = [row for row in pairs if row["shared_tokens"]]
    if not overlapping:
        problems.append(
            "every drift pair is lexically disjoint. A pair set with no overlap overstates the "
            "margin corpus-embed-lift measures, and phrases.yaml deliberately keeps 'near' and "
            "'change' across eras precisely so this is not the case."
        )
    eras = {str(row["era"]) for row in schedule}
    if len(eras) < 4:
        problems.append(f"the substitution schedule covers only {sorted(eras)}")
    first_era_rows = [row for row in schedule if row["era_index"] == 1]
    problems.extend(
        f"{row['concept']} claims to replace something in the first era"
        for row in first_era_rows
        if row["replaces"] is not None
    )
    return _verdict(
        "BK-DRIFT-01",
        title,
        problems,
        f"{len(pairs)} dated pairs across {len(eras)} eras, {len(overlapping)} of them sharing a "
        "content token",
    )


# ── BK-SPINE ─────────────────────────────────────────────────────────────────────────────────


def _check_spine(tree: _Tree) -> Check:
    title = "the spine: one uuid, four labels, 150 then 135, one asserted edge"
    spine = tree.docs.get("spine.json")
    if spine is None:
        return _bad("BK-SPINE-01", title, "spine.json is absent")
    anchors = gaz.as_mapping(gaz.load("anchors"), "spine", origin="anchors.yaml")
    problems: list[str] = []

    if spine["label_2011"] != str(anchors["clause_label_2011"]):
        problems.append(
            f"2011 label is {spine['label_2011']}, anchors say {anchors['clause_label_2011']}"
        )
    if spine["label_2016"] != str(anchors["clause_label_2016"]):
        problems.append(
            f"2016 label is {spine['label_2016']}, anchors say {anchors['clause_label_2016']}"
        )

    revisions = spine["revisions"]
    uuids = {spine["clause_uuid"]}
    dated = {row["effective_on"][:7]: row for row in revisions}
    for month in ("2011-03", "2013-08", "2016-11", "2019-02"):
        if month not in dated:
            problems.append(f"no spine revision in {month}")
    labels = {row["printed_label"] for row in revisions}
    if len(labels) < 3:
        problems.append(f"the spine carries only {sorted(labels)} across twenty-two years")
    if len(uuids) != 1:  # pragma: no cover - one document, one uuid by construction
        problems.append("the spine clause has more than one uuid")

    strengthen = [row for row in revisions if row["control_delta"] == "strengthen"]
    if len(strengthen) != 1:
        problems.append(f"{len(strengthen)} strengthening revisions, expected exactly one")
    elif strengthen[0]["setpoint_from"] != float(anchors["setpoint_oem"]) or strengthen[0][
        "setpoint_to"
    ] != float(anchors["setpoint_post_incident"]):
        problems.append(
            f"the 2013 edit moves {strengthen[0]['setpoint_from']} -> "
            f"{strengthen[0]['setpoint_to']}, anchors say "
            f"{anchors['setpoint_oem']} -> {anchors['setpoint_post_incident']}"
        )

    documents = {row["doc_code"] for row in revisions}
    if str(anchors["document_after_split"]) not in documents:
        problems.append("the spine clause never reaches the post-split document")

    edges = spine["blame_edges"]
    asserted = [edge for edge in edges if edge["basis"] == "asserted_document"]
    if len(edges) != 1 or not asserted:
        problems.append(
            f"the spine carries {len(edges)} blame edge(s); the film shows exactly one, asserted "
            "and active, to the 2013 seal fire"
        )
    elif asserted[0]["state"] != "active" or not asserted[0]["quote_ref"]:
        problems.append("the spine's edge is not active, or carries no quote reference")

    proposed = spine["proposed_2026"]
    if len(proposed) != 1 or proposed[0]["control_delta"] != "weaken":
        problems.append("there is no 2026 weakening proposal; beat 2 has nothing to refuse")
    else:
        merged = {
            (str(row["clause_key"]), str(row["revision_key"]))
            for row in tree.table("clause_revision.jsonl")
        }
        for row in tree.table("proposed_revision.jsonl"):
            if (str(row["clause_key"]), str(row["cr_external_ref"])) in merged:
                problems.append("a proposed revision also appears in merged history")
        if proposed[0]["setpoint_to"] != float(anchors["setpoint_oem"]):
            problems.append("the 2026 proposal does not restore the OEM setpoint")

    return _verdict(
        "BK-SPINE-01",
        title,
        problems,
        f"{spine['clause_uuid']} across {len(revisions)} revisions, labels "
        f"{spine['label_2011']} -> {spine['label_2016']} -> {spine['label_2019']}, "
        f"{anchors['setpoint_oem']} -> {anchors['setpoint_post_incident']}, one asserted edge",
    )


# ── BK-PROJ / BK-REF ─────────────────────────────────────────────────────────────────────────


def _check_projected_columns(tree: _Tree, repo_root: Path | None) -> Check:
    title = "no emitted row names a projected column"
    denied = projected_columns(repo_root)
    problems: list[str] = []
    for name, rows in sorted(tree.rows.items()):
        for position, row in enumerate(rows):
            offending = sorted(set(row) & denied)
            if offending:
                problems.append(f"{name}[{position}] names {offending}")
                break
    total = sum(len(rows) for rows in tree.rows.values())
    return _verdict(
        "BK-PROJ-01", title, problems, f"{total} rows checked against {len(denied)} denied names"
    )


def _check_pending(tree: _Tree) -> Check:
    title = "the pending register accounts for every deliberately-null column"
    problems: list[str] = []
    grouped: dict[tuple[str, str], set[str]] = {}
    reasons = tree.docs.get("pending_reasons.json") or {}
    for row in tree.table("pending.jsonl"):
        code = str(row.get("reason_code", ""))
        if not str(row.get("owner", "")).strip():
            problems.append(f"pending {row['table']}.{row['column']}/{row['key']} names no owner")
        entry = reasons.get(code)
        if entry is None:
            problems.append(f"pending row cites reason_code {code!r}, which resolves to nothing")
        elif not str(entry.get("reason", "")).strip():
            problems.append(f"reason_code {code!r} resolves to an empty reason")
        elif entry.get("table") != row["table"] or entry.get("column") != row["column"]:
            problems.append(f"reason_code {code!r} names a different column than the row it is on")
        grouped.setdefault((str(row["table"]), str(row["column"])), set()).add(str(row["key"]))

    clauses = {str(row["clause_uuid"]) for row in tree.table("clause.jsonl")}
    registry = {
        str(row["clause_uuid"]): str(row["clause_key"])
        for row in tree.table("clause_registry.jsonl")
    }
    birth = grouped.get(("mainline.clause", "birth_commit"), set())
    if birth != {registry[uuid] for uuid in clauses}:
        problems.append("birth_commit is not registered for exactly the clauses that exist")

    edges = tree.table("blame_edge_registry.jsonl")
    commits = grouped.get(("mainline.blame_edge", "commit_id"), set())
    expected = {f"{row['clause_key']}|{row['event_ref']}|{row['basis']}" for row in edges}
    if commits != expected:
        problems.append("commit_id is not registered for exactly the emitted edges")
    quotes = grouped.get(("mainline.blame_edge", "evidence_quote_sha256"), set())
    asserted = {
        f"{row['clause_key']}|{row['event_ref']}|{row['basis']}"
        for row in edges
        if row["basis"] == "asserted_document"
    }
    if quotes != asserted:
        problems.append("the quote-digest register is not exactly the asserted_document edges")
    links = grouped.get(("mainline.blame_edge", "p_link"), set())
    scored = {
        f"{row['clause_key']}|{row['event_ref']}|{row['basis']}"
        for row in edges
        if row["basis"] not in ("asserted_document", "asserted_human")
    }
    if links != scored:
        problems.append(
            "p_link is not registered for exactly the bases CHECK scored_needs_features bites on"
        )
    return _verdict(
        "BK-PROJ-02",
        title,
        problems,
        f"{len(tree.table('pending.jsonl'))} entries across {len(grouped)} (table, column) pairs, "
        "each reconciled to the rows it describes",
    )


def _check_identity(tree: _Tree) -> Check:
    title = "every id recomputes from its published natural key"
    problems: list[str] = []
    for row in tree.table("clause_registry.jsonl"):
        if str(rng.sid("clause", str(row["clause_key"]))) != str(row["clause_uuid"]):
            problems.append(f"clause {row['clause_key']} is not sid('clause', key)")
    for row in tree.table("gs0.jsonl"):
        if str(rng.sid("event", str(row["event_ref"]))) != str(row["event_id"]):
            problems.append(f"gs0 {row['event_ref']} is not sid('event', ref)")
        if str(rng.sid("site", str(row["site_code"]))) != str(row["site_id"]):
            problems.append(f"gs0 {row['site_code']} is not sid('site', code)")
    clauses = {str(row["clause_uuid"]) for row in tree.table("clause.jsonl")}
    stray = {
        str(row["clause_uuid"])
        for row in tree.table("blame_edge.jsonl")
        if str(row["clause_uuid"]) not in clauses
    }
    problems.extend(f"blame edge points at unknown clause {uuid}" for uuid in sorted(stray)[:3])
    return _verdict(
        "BK-REF-01",
        title,
        problems,
        f"{len(tree.table('clause_registry.jsonl'))} clauses, "
        f"{len(tree.table('gs0.jsonl'))} gold rows, every id recomputed from its key alone",
    )


# ── BK-SRC ───────────────────────────────────────────────────────────────────────────────────


def _lane_sources() -> list[Path]:
    package = Path(__file__).resolve().parent
    root = package.parent
    paths = [path for path in sorted(package.glob("*.py")) if path.name != Path(__file__).name]
    paths.extend(sorted((root / "injectors").glob("*.py")))
    return [path for path in paths if path.is_file()]


def _scan_source(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in FORBIDDEN_CALLS:
                found.append(f"{path.name}:{node.lineno} calls {name}()")
        elif isinstance(node, ast.Import):
            found.extend(
                f"{path.name}:{node.lineno} imports {alias.name}"
                for alias in node.names
                if alias.name.split(".")[0].lower() in FORBIDDEN_IMPORTS
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0].lower() in FORBIDDEN_IMPORTS:
                found.append(f"{path.name}:{node.lineno} imports from {node.module}")
    return found


def _check_no_ambient_entropy() -> Check:
    title = "no wall clock, unseeded PRNG, uuid4 or Faker anywhere in the lane"
    sources = _lane_sources()
    problems: list[str] = []
    for path in sources:
        problems.extend(_scan_source(path))
    return _verdict(
        "BK-SRC-01",
        title,
        problems,
        f"{len(sources)} modules parsed; every draw goes through a named rng stream and every "
        "timestamp through clock.EPOCH/NOW",
    )


def _check_no_model_provenance(tree: _Tree) -> Check:
    """No row may claim a model produced it, because no model ran in this stage."""
    title = "nothing in the answer key claims a model wrote it"
    problems: list[str] = []
    for row in tree.table("blame_edge.jsonl"):
        if row.get("model_id") is not None or row.get("prompt_version") is not None:
            problems.append(f"{row['clause_uuid']}: names a model that never ran")
    for row in tree.table("clause_revision.jsonl"):
        if str(row["delta_basis"]) == "lattice+model":
            problems.append(
                f"{row['revision_key']}#{row['clause_key']}: delta_basis 'lattice+model' would "
                "require model_named_when_model_used to name a model"
            )
    return _verdict(
        "BK-SRC-02",
        title,
        problems,
        "no model_id, no prompt_version, no 'lattice+model' delta basis anywhere",
    )


# ── driver ───────────────────────────────────────────────────────────────────────────────────


def _tree_digest(tree: _Tree) -> str:
    body = "".join(f"{name} {digest}\n" for name, digest in sorted(tree.digests.items()))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _collect(first: _Tree, second: _Tree, repo_root: Path | None) -> tuple[Check, ...]:
    return (
        _check_reproducible(first, second),
        _check_bytes(first),
        _check_sort_order(first),
        _check_schema(first),
        _check_schema_bites(first),
        _check_basis_graded_force(first),
        _check_gold_reasons(first),
        _check_channel_labels(first),
        _check_trace_rate(first),
        _check_counts(first),
        _check_retypeset(first),
        _check_decoys(first),
        _check_drift(first),
        _check_spine(first),
        _check_projected_columns(first, repo_root),
        _check_pending(first),
        _check_identity(first),
        _check_no_ambient_entropy(),
        _check_no_model_provenance(first),
    )


def verify_answer_key(*, repo_root: Path | None = None, work_dir: Path | None = None) -> Report:
    """Generate the answer key twice and interrogate the emitted bytes.  Returns, never raises."""
    if work_dir is not None:
        work_dir.mkdir(parents=True, exist_ok=True)
        scratch = work_dir
        cleanup = False
    else:
        scratch = Path(tempfile.mkdtemp(prefix="mainline-blame-verify-"))
        cleanup = True
    try:
        first_dir = scratch / "run-a"
        second_dir = scratch / "run-b"
        result = build.generate(first_dir, repo_root=repo_root)
        build.generate(second_dir, repo_root=repo_root)
        first = _read_tree(first_dir)
        second = _read_tree(second_dir)
        return Report(
            checks=_collect(first, second, repo_root),
            counts={
                name.removesuffix(".jsonl"): len(rows) for name, rows in sorted(first.rows.items())
            },
            tree_sha256=_tree_digest(first),
            generator_version=str(first.index["generator_version"]),
            blame_ratio=result.blame_ratio,
        )
    finally:
        if cleanup:
            shutil.rmtree(scratch, ignore_errors=True)


_GLYPH: Final[Mapping[str, str]] = {OUTCOME_OK: "PASS", OUTCOME_FAIL: "FAIL", OUTCOME_WARN: "WARN"}


def render(report: Report, *, strict: bool = False) -> str:
    lines = [
        "mainline-corpus stage 1b — answer-key verification",
        f"  generator      {report.generator_version}",
        f"  tree digest    {report.tree_sha256}",
        f"  clauses        {report.counts.get('clause', 0)}",
        f"  clause versions{report.counts.get('clause_revision', 0):>7}",
        f"  blame edges    {report.counts.get('blame_edge', 0)}  (ratio {report.blame_ratio})",
        f"  gold rows      {report.counts.get('gs0', 0)}",
        "",
    ]
    for check in report.checks:
        lines.append(f"  [{_GLYPH[check.status]}] {check.check_id}  {check.title}")
        lines.append(f"          {check.detail}")
    lines.append("")
    passed = sum(1 for check in report.checks if check.ok)
    lines.append(
        f"  {passed}/{len(report.checks)} passed, {len(report.warnings)} warned, "
        f"{len(report.failures)} failed"
    )
    if report.failures:
        lines.append("  REFUSED: the answer key is not sound.")
    elif report.warnings and strict:
        lines.append("  REFUSED under --strict: an unproven claim is not a proven one.")
    elif report.warnings:
        lines.append("  SOUND, with unproven claims recorded above.")
    else:
        lines.append("  SOUND.")
    return "\n".join(lines) + "\n"


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--repo-root", type=Path, default=None, metavar="DIR")
    parser.add_argument("--work-dir", type=Path, default=None, metavar="DIR")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", dest="as_json", action="store_true")
    return parser


configure = add_arguments


def run(args: argparse.Namespace) -> int:
    report = verify_answer_key(
        repo_root=getattr(args, "repo_root", None), work_dir=getattr(args, "work_dir", None)
    )
    strict = bool(getattr(args, "strict", False))
    if getattr(args, "as_json", False):
        payload = {
            "blame_ratio": report.blame_ratio,
            "checks": [
                {
                    "detail": check.detail,
                    "id": check.check_id,
                    "status": check.status,
                    "title": check.title,
                }
                for check in report.checks
            ],
            "counts": dict(report.counts),
            "generator_version": report.generator_version,
            "tree_sha256": report.tree_sha256,
        }
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render(report, strict=strict))
    return report.exit_code(strict=strict)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corpusgen blame-verify", description=HELP)
    add_arguments(parser)
    return run(parser.parse_args(list(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
