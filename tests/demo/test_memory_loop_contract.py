# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this module makes no database claim. It replays bytes the deployed API sent on
#     2026-08-15 and checks them against the document that describes them.
"""Replay the captured memory loop offline and hold `memory-visible-CONTRACT.md` to it.

WHAT THIS SUITE IS FOR. `docs/demo/memory-visible-CONTRACT.md` is the factual spine of
`docs/demo/memory-visible-plan.md`: five other workers build `/memory.html` against its table
of `data-cell` → pointer → value → chip. A table like that decays the moment it is written,
because it is prose about JSON, and prose about JSON is checked by nobody. So the table is
*parsed* here and every row is resolved against the recording it names.

**THE NETWORK IS UNPLUGGED, ON PURPOSE AND BY FORCE.** :func:`_no_network` replaces
``socket.socket`` and ``socket.create_connection`` with functions that raise, for every test in
this module. A suite that replays fixtures but silently reaches the live URL when one is absent
would go green on a day the fixtures were wrong, which is the one day it exists for. It also
means this module runs in the hermetic lane, needs no cluster and needs no credential.

WHAT WOULD MAKE IT RED, and each of these is a thing we want to hear about loudly:

* a pointer in the contract that no longer resolves        -> the payload shape moved
* a value that no longer matches                           -> the seeded world moved
* a chip that no longer matches                            -> the emitter's claims moved
* a fixture whose bytes disagree with the manifest         -> a recording was edited by hand
* a `data-cell` id from plan §4 missing from the table     -> a cell was quietly dropped
* five chips in `envelope.py` becoming four, or vice versa -> R-M3's recorded discrepancy moved

The last one is not a mistake. R-M3 orders the five-chip/four-chip discrepancy RECORDED rather
than repaired, and a recorded fact nothing guards is a sentence that rots. If somebody
legitimately reconciles the two vocabularies, this test fails, they read the contract, and they
update it. That is the whole mechanism.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "demo" / "memory-visible-CONTRACT.md"
FIXTURES = REPO_ROOT / "verticals" / "mainline" / "apps" / "console" / "fixtures" / "memory-loop"
CAPTURE_TOOL = REPO_ROOT / "scripts" / "demo" / "capture_memory_loop.py"
ENVELOPE_PY = (
    REPO_ROOT
    / "verticals"
    / "mainline"
    / "apps"
    / "demo-api"
    / "src"
    / "mainline_demo_api"
    / "envelope.py"
)
PROVENANCE_TS = (
    REPO_ROOT / "verticals" / "mainline" / "apps" / "console" / "src" / "design" / "provenance.ts"
)

TABLE_BEGIN = "<!-- CONTRACT-TABLE-BEGIN -->"
TABLE_END = "<!-- CONTRACT-TABLE-END -->"

#: The captures the loop is built from. `subjects` supplies the addressing (R-M8) and is not
#: itself a cell source, but it is captured and checked so that a deployment that renamed a
#: subject key is caught here rather than in a browser.
CAPTURE_NAMES = ("subjects", "blocking-checks", "ancestry", "recall-run", "ledger", "gate-run")

#: `common.schema.json#/$defs/provenance_chip`, as `envelope.py` closes it. A chip outside this
#: set in the contract would be one this document invented, which R-M3 forbids in terms.
WIRE_CHIPS = frozenset({"db:column", "db:constraint", "recomputed", "staged", "derived"})

#: The one cell in the contract that no response contains: R-M7.1's client receipt time.
CLIENT_CELLS = frozenset({"meta.received_at"})

# ── the grammar of the table, as §1.4 of the contract states it ────────────────────────────
_CODE = re.compile(r"^`(?P<inner>.+)`$", re.DOTALL)
_EQUALITY_POINTER = re.compile(r"^`(?P<left>[^`]+)` == `(?P<right>[^`]+)`$")
_FIXTURE_PAIR = re.compile(r"^`(?P<left>[^`]+)` \+ `(?P<right>[^`]+)`$")
_DIGEST_VALUE = re.compile(r"^`sha256\(utf8\)=(?P<hex>[0-9a-f]{64}), (?P<bytes>\d+) B`$")
_VOLATILE_VALUE = re.compile(r"^volatile `(?P<literal>.+)`$")
_CHIP_EXACT = re.compile(r"^`(?P<chip>[^`]+)` exact$")
_CHIP_INHERITED = re.compile(r"^`(?P<chip>[^`]+)` inherited from `(?P<ancestor>[^`]+)`$")
_SELECTOR = re.compile(r"^\[(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\]]+)\]$")

#: R-M8's shape. Fixtures are recordings and are exempt; source files are not.
_UUID_LITERAL = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

#: The seeded world's id prefix, SPLIT so that this module does not fail its own check and does
#: not put a hit in front of W6's grep. Writing it whole here would be the literal R-M8 bans.
_SEED_ID_PREFIX = "dec0" + "de00"

# ── plan §4's enumeration, transcribed so a deleted row cannot pass unnoticed ───────────────
# Each family is expanded exactly as `memory-visible-plan.md` §4 lists it. A row may be ADDED
# to the contract without touching this list; a row may not be REMOVED.
_BEAT_FIELDS = ("name", "outcome", "sqlstate", "constraint", "constraint_source", "elapsed_ms")
REQUIRED_CELLS = frozenset(
    [
        *(
            f"store.event.{f}"
            for f in (
                "ref",
                "kind",
                "occurred_at",
                "severity_gate",
                "severity_basis",
                "title",
                "source_sha256",
            )
        ),
        *(f"store.edge.{f}" for f in ("basis", "state", "attribution")),
        *(
            f"store.closure.{f}"
            for f in (
                "gen",
                "ancestors",
                "max_severity",
                "virulence",
                "depth",
                "truncated",
                "computed_by",
                "projector_ver",
            )
        ),
        "store.leaf.ingested.entry_kind",
        "store.leaf.ingested.leaf_hash_hex",
        "store.leaf.closure.entry_kind",
        "store.leaf.closure.leaf_hash_hex",
        "retrieve.sql.view",
        "retrieve.sql.recall",
        *(
            f"retrieve.armed.{f}"
            for f in ("severity", "virulence", "closure_gen", "origin", "materialised_at")
        ),
        *(
            f"retrieve.recall.{f}"
            for f in (
                "started_at",
                "policy",
                "index_generation",
                "index_plan_digest",
                "n_candidates",
                "n_blocking",
                "n_advisory",
                "n_silenced",
                "n_deduped",
            )
        ),
        *(f"retrieve.match.{f}" for f in ("severity", "virulence", "closure_gen")),
        *(f"act.beat{n}.{f}" for n in (1, 2, 3, 4) for f in _BEAT_FIELDS),
        "act.verdict",
        "act.failures",
        "act.self_persisted",
        "act.single_transaction",
        "meta.received_at",
        "meta.generated_at",
        "meta.elapsed_ms",
    ]
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this module replays bytes from disk. None of them may open a socket."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "this suite replays captured fixtures; opening a socket would let it pass on live "
            "data and hide a stale recording"
        )

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# the recordings
# ═══════════════════════════════════════════════════════════════════════════════════════════


def _raw(name: str) -> bytes:
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        raise AssertionError(
            f"missing recording {path}; run `python scripts/demo/capture_memory_loop.py "
            f"--with-post` to capture the loop"
        )
    return path.read_bytes()


def _envelope(name: str) -> dict[str, Any]:
    return json.loads(_raw(name).decode("utf-8"))


def _manifest() -> dict[str, Any]:
    return json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════════════════════
# RFC 6901, plus the one `[key=value]` selector the contract's §1.3 defines
# ═══════════════════════════════════════════════════════════════════════════════════════════


def _tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise AssertionError(f"{pointer!r} is not an RFC 6901 pointer")
    return [t.replace("~1", "/").replace("~0", "~") for t in pointer.split("/")[1:]]


def resolve(document: Any, pointer: str) -> Any:
    """Resolve *pointer* against *document*, honouring `[key=value]` selectors."""
    current = document
    for token in _tokens(pointer):
        selector = _SELECTOR.match(token)
        if selector is not None:
            if not isinstance(current, list):
                raise AssertionError(f"{pointer}: selector {token} applied to a non-array")
            key, wanted = selector.group("key"), selector.group("value")
            hits = [
                i
                for i, item in enumerate(current)
                if isinstance(item, dict) and item.get(key) == wanted
            ]
            if len(hits) != 1:
                raise AssertionError(
                    f"{pointer}: selector {token} matched {len(hits)} elements; plan §4 requires "
                    "exactly one, found by key and never by index"
                )
            current = current[hits[0]]
            continue
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, dict):
            if token not in current:
                raise AssertionError(f"{pointer}: no member {token!r}")
            current = current[token]
        else:
            raise TypeError(f"{pointer}: cannot descend {token!r} into {type(current)}")
    return current


def concrete(document: Any, pointer: str) -> str:
    """*pointer* with every selector replaced by the index it resolved to.

    Chips are claimed on concrete pointers, so a selector must be collapsed before the
    provenance list is consulted.
    """
    current = document
    parts: list[str] = []
    for token in _tokens(pointer):
        selector = _SELECTOR.match(token)
        if selector is not None:
            key, wanted = selector.group("key"), selector.group("value")
            index = next(
                i
                for i, item in enumerate(current)
                if isinstance(item, dict) and item.get(key) == wanted
            )
            parts.append(str(index))
            current = current[index]
            continue
        parts.append(token)
        current = current[int(token)] if isinstance(current, list) else current[token]
    return "/" + "/".join(parts)


def _contains(ancestor: str, pointer: str) -> bool:
    """RFC 6901 containment, exactly as `console/src/features/gate/provenance.ts` defines it.

    Its comment names the case a naive `startsWith` gets wrong: ``/counter`` does NOT contain
    ``/counters/open_blocking``. The trailing separator is what makes that false.
    """
    return pointer == ancestor or pointer.startswith(f"{ancestor}/")


def chip_claim(envelope: dict[str, Any], envelope_pointer: str) -> str:
    """The chip the envelope claimed for *envelope_pointer*, rendered as the contract writes it.

    Returns ``"none claimed"``, ``"`chip` exact"`` or ``"`chip` inherited from `/ptr`"``.
    """
    if not envelope_pointer.startswith("/data"):
        # `provenance[]` addresses `data` alone (`envelope.py::Provenance.add` refuses anything
        # else), so nothing outside it can carry a chip. Contract §1.1.
        return "none claimed"
    inside = concrete(envelope, envelope_pointer)[len("/data") :]
    if inside == "":
        return "none claimed"
    entries = envelope.get("provenance") or []
    for entry in entries:
        if entry["pointer"] == inside:
            return f"`{entry['chip']}` exact"
    best: dict[str, str] | None = None
    for entry in entries:
        if not _contains(entry["pointer"], inside):
            continue
        if best is None or len(entry["pointer"]) > len(best["pointer"]):
            best = entry
    if best is not None:
        return f"`{best['chip']}` inherited from `{best['pointer']}`"
    return "none claimed"


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# the contract table
# ═══════════════════════════════════════════════════════════════════════════════════════════


class Row:
    """One parsed row of the contract table."""

    __slots__ = ("cell", "chip", "fixtures", "kind", "pointers", "value_cell")

    def __init__(
        self,
        cell: str,
        fixtures: tuple[str, ...],
        pointers: tuple[str, ...],
        value_cell: str,
        chip: str,
        kind: str,
    ) -> None:
        self.cell = cell
        self.fixtures = fixtures
        self.pointers = pointers
        self.value_cell = value_cell
        self.chip = chip
        self.kind = kind

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<Row {self.cell} {self.kind}>"


def _unbacktick(text: str) -> str:
    match = _CODE.match(text)
    if match is None:
        raise AssertionError(f"expected a `code` cell, got {text!r}")
    return match.group("inner")


def parse_table() -> list[Row]:
    """Parse the fenced table out of the contract. The document is the source of truth."""
    text = CONTRACT.read_text(encoding="utf-8")
    if TABLE_BEGIN not in text or TABLE_END not in text:
        raise AssertionError(f"{CONTRACT} has no {TABLE_BEGIN} / {TABLE_END} fence")
    body = text.split(TABLE_BEGIN, 1)[1].split(TABLE_END, 1)[0]

    rows: list[Row] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        columns = [c.strip() for c in stripped.strip("|").split("|")]
        if len(columns) != 5:
            raise AssertionError(f"row has {len(columns)} columns, expected 5: {stripped!r}")
        if columns[0] == "`data-cell`" or set(columns[0]) <= {"-", ":"}:
            continue

        cell = _unbacktick(columns[0])
        fixture_cell, pointer_cell, value_cell, chip_cell = columns[1:]

        if pointer_cell == "(client clock)":
            assert fixture_cell == "(none)", (
                f"{cell}: a client-clock row names no fixture, got {fixture_cell!r}"
            )
            rows.append(Row(cell, (), (), value_cell, chip_cell, "client"))
            continue

        equality = _EQUALITY_POINTER.match(pointer_cell)
        if equality is not None:
            pair = _FIXTURE_PAIR.match(fixture_cell)
            if pair is None:
                raise AssertionError(
                    f"{cell}: an equality row must name two fixtures, got {fixture_cell!r}"
                )
            rows.append(
                Row(
                    cell,
                    (pair.group("left"), pair.group("right")),
                    (equality.group("left"), equality.group("right")),
                    value_cell,
                    chip_cell,
                    "equality",
                )
            )
            continue

        rows.append(
            Row(
                cell,
                (_unbacktick(fixture_cell),),
                (_unbacktick(pointer_cell),),
                value_cell,
                chip_cell,
                "pointer",
            )
        )
    if not rows:
        raise AssertionError(f"{CONTRACT}: the fenced table is empty")
    return rows


ROWS = parse_table()
POINTER_ROWS = [r for r in ROWS if r.kind == "pointer"]
EQUALITY_ROWS = [r for r in ROWS if r.kind == "equality"]
CLIENT_ROWS = [r for r in ROWS if r.kind == "client"]


def _idify(row: Row) -> str:
    return row.cell


# ═══════════════════════════════════════════════════════════════════════════════════════════
# the recordings are the ones that were recorded
# ═══════════════════════════════════════════════════════════════════════════════════════════


def test_every_capture_is_present_and_answered_200() -> None:
    manifest = _manifest()
    rows = {row["name"]: row for row in manifest["captures"]}
    assert set(rows) == set(CAPTURE_NAMES), (
        f"manifest names {sorted(rows)}, the loop needs {sorted(CAPTURE_NAMES)}"
    )
    for name in CAPTURE_NAMES:
        assert rows[name]["http_status"] == 200, (
            f"{name} was captured at HTTP {rows[name]['http_status']}; the contract's values "
            "were read out of a body the API refused to give"
        )
    assert rows["gate-run"]["method"] == "POST"
    assert all(rows[n]["method"] == "GET" for n in CAPTURE_NAMES if n != "gate-run")


@pytest.mark.parametrize("name", CAPTURE_NAMES)
def test_fixture_bytes_match_the_manifest(name: str) -> None:
    """A recording edited by hand is a fabricated exhibit. The digest is what catches it."""
    row = next(r for r in _manifest()["captures"] if r["name"] == name)
    raw = _raw(name)
    assert len(raw) == row["byte_length"], (
        f"{name}.json is {len(raw)} B, manifest says {row['byte_length']} B"
    )
    assert hashlib.sha256(raw).hexdigest() == row["sha256_hex"], (
        f"{name}.json does not hash to the digest recorded when it was captured"
    )


@pytest.mark.parametrize("name", CAPTURE_NAMES)
def test_each_recording_is_a_version_1_envelope(name: str) -> None:
    envelope = _envelope(name)
    assert envelope["envelope_version"] == 1
    assert isinstance(envelope["data"], dict)
    assert isinstance(envelope.get("provenance", []), list)
    for entry in envelope.get("provenance") or []:
        assert entry["chip"] in WIRE_CHIPS, (
            f"{name} claims chip {entry['chip']!r}, which is outside the closed vocabulary "
            f"{sorted(WIRE_CHIPS)}"
        )
        assert entry["pointer"].startswith("/"), entry


# ═══════════════════════════════════════════════════════════════════════════════════════════
# every pointer in the contract resolves, and to the value the contract records
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("row", POINTER_ROWS, ids=_idify)
def test_pointer_resolves_to_the_recorded_value(row: Row) -> None:
    envelope = _envelope(row.fixtures[0])
    value = resolve(envelope, row.pointers[0])

    digest = _DIGEST_VALUE.match(row.value_cell)
    if digest is not None:
        assert isinstance(value, str), f"{row.cell}: a digest row must address a string"
        encoded = value.encode("utf-8")
        assert len(encoded) == int(digest.group("bytes")), (
            f"{row.cell}: {len(encoded)} B on the wire, contract records {digest.group('bytes')} B"
        )
        assert hashlib.sha256(encoded).hexdigest() == digest.group("hex"), (
            f"{row.cell}: the recorded sha256 is not the digest of the captured value"
        )
        return

    volatile = _VOLATILE_VALUE.match(row.value_cell)
    if volatile is not None:
        recorded = json.loads(volatile.group("literal"))
        assert _json_type(value) == _json_type(recorded), (
            f"{row.cell}: recorded a {_json_type(recorded)}, the capture holds a "
            f"{_json_type(value)}"
        )
        return

    expected = json.loads(_unbacktick(row.value_cell))
    assert value == expected, f"{row.cell} at {row.pointers[0]}: {value!r} != {expected!r}"


@pytest.mark.parametrize("row", POINTER_ROWS, ids=_idify)
def test_the_chip_is_the_one_the_envelope_claimed(row: Row) -> None:
    """R-M3: the chip is the emitter's, resolved by pointer. Never assigned, never defaulted."""
    envelope = _envelope(row.fixtures[0])
    assert chip_claim(envelope, row.pointers[0]) == row.chip, (
        f"{row.cell} at {row.pointers[0]}: the envelope claims "
        f"{chip_claim(envelope, row.pointers[0])!r}, the contract records {row.chip!r}"
    )


@pytest.mark.parametrize("row", EQUALITY_ROWS, ids=_idify)
def test_equality_rows_compare_two_independent_responses(row: Row) -> None:
    """R-M5.2: the armed check's severity IS the closure's, shown across two HTTP responses."""
    left_fixture, right_fixture = row.fixtures
    assert left_fixture != right_fixture, (
        f"{row.cell}: an equality marker across one response proves nothing"
    )
    left = resolve(_envelope(left_fixture), row.pointers[0])
    right = resolve(_envelope(right_fixture), row.pointers[1])
    verdict = "match" if left == right else "differs"
    assert verdict == json.loads(_unbacktick(row.value_cell)), (
        f"{row.cell}: {left!r} vs {right!r} is {verdict!r}, contract records {row.value_cell!r}"
    )
    assert row.chip == "none claimed", (
        f"{row.cell}: a comparison the client performs carries no chip (R-M4)"
    )


@pytest.mark.parametrize("row", CLIENT_ROWS, ids=_idify)
def test_client_rows_are_declared_and_chipless(row: Row) -> None:
    assert row.cell in CLIENT_CELLS, (
        f"{row.cell} claims to come from the client clock; only {sorted(CLIENT_CELLS)} may"
    )
    assert row.chip == "none claimed"


def test_the_declared_client_cells_are_all_present() -> None:
    assert {r.cell for r in CLIENT_ROWS} == set(CLIENT_CELLS)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# the table's shape
# ═══════════════════════════════════════════════════════════════════════════════════════════


#: The counts the contract states in prose (§2 preamble, §5 E-3, §6). A number written in a
#: sentence and guarded by nothing goes stale on the first edit; these are the guard.
EXPECTED_ROW_COUNTS = {"pointer": 76, "equality": 3, "client": 1}
EXPECTED_NO_CHIP_CELLS = 30
EXPECTED_ACT_CELLS = 28
EXPECTED_ACT_CELLS_WITH_A_CHIP = 6


def test_the_row_counts_the_contract_states_in_prose_are_true() -> None:
    counts = {kind: len([r for r in ROWS if r.kind == kind]) for kind in EXPECTED_ROW_COUNTS}
    assert counts == EXPECTED_ROW_COUNTS, (
        f"the table holds {counts}; memory-visible-CONTRACT.md §2 says {EXPECTED_ROW_COUNTS}. "
        "Update the sentence and this constant together."
    )


def test_the_unchipped_cell_count_the_contract_lists_is_true() -> None:
    """§6 enumerates every cell that renders with no chip. The count keeps the list honest."""
    unchipped = [r.cell for r in ROWS if r.chip == "none claimed"]
    assert len(unchipped) == EXPECTED_NO_CHIP_CELLS, sorted(unchipped)


def test_the_act_column_is_as_sparse_as_escalation_e3_says() -> None:
    act = [r for r in ROWS if r.cell.startswith("act.")]
    chipped = [r for r in act if r.chip != "none claimed"]
    assert len(act) == EXPECTED_ACT_CELLS
    assert len(chipped) == EXPECTED_ACT_CELLS_WITH_A_CHIP, sorted(r.cell for r in chipped)


def test_no_cell_id_appears_twice() -> None:
    cells = [row.cell for row in ROWS]
    duplicates = sorted({c for c in cells if cells.count(c) > 1})
    assert not duplicates, f"duplicated data-cell ids: {duplicates}"


def test_every_plan_section_4_cell_is_in_the_table() -> None:
    """A cell may be added to the contract; a cell from plan §4 may never be dropped."""
    missing = sorted(REQUIRED_CELLS - {row.cell for row in ROWS})
    assert not missing, (
        f"plan §4 names these cells and the contract no longer carries them: {missing}. "
        "R-M1 forbids dropping a cell silently — escalate instead."
    )


def test_every_chip_named_is_one_the_wire_vocabulary_holds() -> None:
    for row in ROWS:
        if row.chip == "none claimed":
            continue
        match = _CHIP_EXACT.match(row.chip) or _CHIP_INHERITED.match(row.chip)
        assert match is not None, f"{row.cell}: unreadable chip cell {row.chip!r}"
        assert match.group("chip") in WIRE_CHIPS, (
            f"{row.cell} names chip {match.group('chip')!r}, which the envelope's closed "
            "vocabulary does not contain"
        )


def test_the_network_guard_actually_refuses() -> None:
    """A guard that has never fired is decoration (PL-2). This one is asked to fire."""
    with pytest.raises(AssertionError, match="replays captured fixtures"):
        socket.socket()
    with pytest.raises(AssertionError, match="replays captured fixtures"):
        socket.create_connection(("127.0.0.1", 9))


def test_containment_matches_the_console_rule() -> None:
    """The case `provenance.ts` calls out by name, so the two implementations cannot drift."""
    assert _contains("/constraints", "/constraints/0/constraint")
    assert _contains("/counter", "/counter")
    assert not _contains("/counter", "/counters/open_blocking")


# ═══════════════════════════════════════════════════════════════════════════════════════════
# R-M8, and R-M3's recorded discrepancy
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("path", [CAPTURE_TOOL, Path(__file__), CONTRACT])
def test_no_uuid_literal_in_this_worker_s_source(path: Path) -> None:
    """R-M8: addressing comes from `/v1/demo/subjects`. Fixtures are recordings and are exempt."""
    text = path.read_text(encoding="utf-8")
    hits = sorted(set(_UUID_LITERAL.findall(text)))
    assert not hits, f"{path} carries UUID literals: {hits}"
    assert _SEED_ID_PREFIX not in text, f"{path} carries the seeded id prefix"


def test_the_five_chip_four_chip_discrepancy_is_still_true() -> None:
    """R-M3 orders this RECORDED, not repaired. This is what keeps the record honest.

    If somebody reconciles the two vocabularies, this fails and
    `docs/demo/memory-visible-CONTRACT.md` §4.1 must be rewritten to say what is true then.
    """
    envelope_line = ENVELOPE_PY.read_text(encoding="utf-8").splitlines()[92]  # line 93, 1-based
    assert envelope_line.startswith("Chip = Literal["), (
        f"envelope.py:93 is no longer the Chip literal; it reads {envelope_line!r}"
    )
    assert sorted(re.findall(r'"([^"]+)"', envelope_line)) == sorted(WIRE_CHIPS)

    ts_line = PROVENANCE_TS.read_text(encoding="utf-8").splitlines()[25]  # line 26, 1-based
    assert ts_line.startswith("export const PROVENANCE_KINDS = ["), (
        f"provenance.ts:26 is no longer the kinds array; it reads {ts_line!r}"
    )
    design_kinds = sorted(re.findall(r"'([^']+)'", ts_line))
    assert design_kinds == sorted(WIRE_CHIPS - {"derived"}), design_kinds
    assert "derived" not in design_kinds


def test_derived_is_really_on_the_wire_for_the_verdict() -> None:
    """The discrepancy in §4.1 is load-bearing, not academic: the ACT column's headline uses it."""
    assert chip_claim(_envelope("gate-run"), "/data/verdict") == "`derived` exact"


#: Contract §3.1, measured 2026-08-15: how many `statement_refs` each capture carries and how
#: many of them actually hand over the statement. R-M6 requires the gaps be STATED, so the size
#: of the gap is a number the contract publishes — and a published number wants a guard.
EXPECTED_STATEMENT_REFS = {
    "subjects": (9, 9),
    "blocking-checks": (5, 1),
    "ancestry": (9, 2),
    "recall-run": (1, 1),
    "ledger": (7, 1),
    "gate-run": (5, 0),
}


@pytest.mark.parametrize("name", CAPTURE_NAMES)
def test_the_statement_ref_gaps_are_the_size_the_contract_says(name: str) -> None:
    refs = _envelope(name).get("statement_refs") or []
    with_text = [r for r in refs if r.get("text")]
    assert (len(refs), len(with_text)) == EXPECTED_STATEMENT_REFS[name], (
        f"{name}: {len(refs)} refs, {len(with_text)} carrying text; contract §3.1 records "
        f"{EXPECTED_STATEMENT_REFS[name]}"
    )


def test_the_sql_reproduced_in_the_contract_is_byte_identical_to_the_wire() -> None:
    """§3 prints both statements for the eye. If prose and payload drift, the prose is a lie.

    R-M6 forbids retyping or reformatting a statement the server handed us. A document that
    reproduces one has taken on the same obligation, so the fenced blocks are compared
    character for character against the recordings.
    """
    fenced = re.findall(r"```sql\n(.*?)\n```", CONTRACT.read_text(encoding="utf-8"), re.DOTALL)
    assert len(fenced) == 2, f"contract §3 has {len(fenced)} sql blocks, expected 2"
    wire = [
        resolve(
            _envelope("ancestry"), "/statement_refs/[object=mainline.clause_blame_current]/text"
        ),
        resolve(_envelope("recall-run"), "/statement_refs/[object=mainline_meas.recall_run]/text"),
    ]
    for block, statement in zip(fenced, wire, strict=True):
        assert block == statement, (
            "a SQL block in memory-visible-CONTRACT.md §3 is not the statement the API "
            "returned; re-run the capture and paste the payload's text unchanged"
        )


def test_the_two_sql_cells_really_do_carry_their_statement() -> None:
    """R-M6's whole point: the retrieval path is the server's own SQL, not ours."""
    view = resolve(
        _envelope("ancestry"),
        "/statement_refs/[object=mainline.clause_blame_current]/text",
    )
    assert view.strip().startswith("SELECT")
    assert "FROM mainline.clause_blame_current" in view
    recall = resolve(
        _envelope("recall-run"),
        "/statement_refs/[object=mainline_meas.recall_run]/text",
    )
    assert recall.strip().startswith("SELECT")
    assert "FROM mainline_meas.recall_run" in recall


def test_statement_refs_can_carry_no_chip_by_construction() -> None:
    """Contract §1.1: `provenance[]` addresses `data` alone, so the SQL cells are unchippable."""
    for name in CAPTURE_NAMES:
        for entry in _envelope(name).get("provenance") or []:
            assert not entry["pointer"].startswith("/statement_refs"), (
                f"{name} claims a chip on {entry['pointer']}; contract §1.1 says the provenance "
                "pointer space is `data` and would need rewriting"
            )
