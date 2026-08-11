# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Put Amazon Bedrock's output inside CockroachDB, and prove which parts of that sentence are true.

Two loads, deliberately unequal, because they prove different things and the difference is
the point.

**A — THE PRODUCTION ROW.**  ``mainline_demo.mainline.clause_version`` holds exactly one row:
a real clause version that the pipeline itself produced, with a canon digest, a bloodline root
and a control delta, sitting under three triggers (``append_only``,
``z_delta_witness_required``, ``clause_version_guard``).  This program embeds that row's
``canon_text`` through ``amazon.titan-embed-text-v2:0`` in ``ap-southeast-2`` and inserts
**one row** into the production sidecar ``mainline.clause_embedding`` — under its real
composite foreign key, its two ``CHECK`` constraints, its two column families and its real
``ce_ann`` vector index.  Row count before and after, and the server's own
``SHOW CREATE TABLE``, land in ``evidence/aws/load/demo-row.json``.

That is a small claim and it is unimpeachable: *the production table, under its constraints,
accepts a Bedrock vector.*  It is not a claim about a corpus, and this program does not try to
make it one.  Bulk-loading ``clause_version`` past its triggers is not attempted anywhere in
this file — **a gate refusing you is the gate working**, and forging witnesses until it stops
refusing would destroy the only thing the gate is for.

**B — THE EVIDENCE DATABASE.**  ``mainline_ann_evidence`` is a separate database whose
``clause_embedding`` statement is a byte-identical copy of migration ``0031``'s and whose
parent ``clause_version`` is an openly-declared two-column stub.  **Every vector the
``titan-embed`` manifest covers is loaded there, unconditionally**, joined to the corpus by the
SHA-256 of the text each vector was made from rather than by anybody's naming convention.  What
this program embeds *itself*, for documents the manifest has not reached, is capped
(:data:`MAX_SELF_EMBED`) because Bedrock's on-demand quota in this region is shared with the
worker whose job that is — and the cap selects width-first across ``(site_id, activity_root)``,
so it costs corpus depth and never a prefix tree.  That distinction matters: C-SPANN keeps a
separate partition tree per distinct prefix value, so one prefix value would prove nothing at
all about prefix-constrained search.  ``verticals/mainline/db/evidence/README.md`` states
exactly what the stub costs the claim; this program re-proves the byte-identity on every run
and writes the line-by-line result to ``evidence/aws/load/schema-fidelity.json``.

**THE 40001 LOOP IS EXERCISED, NOT MERELY PRESENT.**  Every write goes through
``_common.with_retry``, and the observed trip count is published even when it is zero — a
retry that never fired is not evidence that the loop works.  Because a bulk load of disjoint
primary keys may legitimately never contend, this program *also* runs a deliberate
write-after-read conflict between two connections and records how many times the loop caught
it.  Both numbers are in ``evidence/aws/load/retry-40001.json``, labelled, and never added
together.

**IDENTITY.**  No ``CREATE SEQUENCE``, no ``nextval``, no ``SERIAL``, no ``unique_rowid()`` —
banned repository-wide, and this program asserts their absence over the SQL it actually issued
rather than trusting itself.  ``clause_uuid`` is a UUIDv5 of a corpus identifier and
``commit_id`` is the SHA-256 of the embedded text, so the same corpus reproduces the same
primary keys on any cluster and a re-run overwrites rather than accumulates.

**THE CORPUS IS SYNTHETIC** — ``trappoint_recall.corpora.synthetic``, eight hazard families,
fabricated end to end.  Every artefact this program writes carries ``synthetic: true``.  The
real corpus is a register of people who died at work; a repository is a copy; that is why the
fabrication exists and why it is stated rather than buried.

Run::

    D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/aws/load_vectors.py
    D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/aws/load_vectors.py \
        --fidelity-only

``--fidelity-only`` is the form a reviewer should run first: no credentials, no network, no
cluster, and it is the check that decides whether anything else here means what it says.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import uuid
from collections.abc import Iterable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # direct execution: `python scripts/aws/load_vectors.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.aws._common import (
    REGION,
    artefact,
    assert_in_region,
    bedrock_runtime,
    crdb,
    ledger_total,
    repo_root,
    sha256_hex,
    token_ledger_entry,
    with_retry,
)

# ═══════════════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════════════

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"

#: The DDL's declared width.  A loader that accepted any width would silently create a table
#: whose vectors cannot be compared with production's.
EXPECTED_DIM = 1024

#: Written verbatim into ``clause_embedding.index_gen``.  It is the generation label M4's
#: ``index_fingerprint`` consumes; ``titan2`` names the model family and ``-1`` the first
#: generation of vectors this repository has ever stored.
INDEX_GEN = "titan2-1"

PRODUCTION_DB = "mainline_demo"
EVIDENCE_DB = "mainline_ann_evidence"

#: This worker's scratch database.  The retry probe's table lives here and NOT in
#: ``mainline_ann_evidence``, so that the evidence database contains exactly what
#: ``ann_evidence_schema.sql`` says it contains and nothing a reader has to be told to ignore.
SCRATCH_DB = "w_cloud_load"

LOCAL_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"

SCHEMA_SQL = Path("verticals/mainline/db/evidence/ann_evidence_schema.sql")
MIGRATION_0031 = Path("verticals/mainline/db/migrations/0031_clause_embedding.sql")

EVIDENCE_DIR = Path("evidence/aws/load")

#: Produced by the ``titan-embed`` worker.  Reused when present; this program never
#: re-embeds a text the manifest already covers, and says which path it took.
MANIFEST_PATH = Path("evidence/aws/embeddings/manifest.json")
MANIFEST_NPZ = Path("out/aws/titan-vectors.npz")

#: This program's own cache when it has to embed the corpus itself.  ``out/`` is gitignored;
#: nothing here is evidence, it is only a way to make a re-run free.
FALLBACK_NPZ = Path("out/aws/cloud-load-vectors.npz")

#: UUIDv5 namespace for every identifier this program mints.  A URL namespace with a
#: reserved-for-documentation authority: these identifiers are derived, deterministic and
#: resolve to nothing, and all three of those facts should be visible in the string itself.
_UUID_BASE = "https://mainline.invalid"

#: Banned repository-wide.  ``\bSERIAL\b`` and not ``SERIAL``: ``RETRY_SERIALIZABLE`` is a
#: string this fleet publishes on purpose, and a checker that flags its own evidence is a
#: checker that will be switched off.
BANNED_IDENTITY = re.compile(r"(?i)\b(create\s+sequence|nextval|serial|unique_rowid)\b")

#: ``-- @connect <target>`` above each statement in the schema file.
_CONNECT = re.compile(r"^--\s*@connect\s+(\S+)\s*$")

#: ``--   @prov L001-L066 AUTHORED  free text`` in the schema file's header.
_PROV = re.compile(
    r"^--\s+@prov\s+L(\d+)-L(\d+)\s+(AUTHORED|STUB|VERBATIM)\s+(.*?)\s*$",
)

#: The source reference inside a ``VERBATIM`` provenance row.
_PROV_SOURCE = re.compile(r"^(\S+\.sql)\s+L(\d+)-L(\d+)$")


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1 · Schema fidelity — the check that decides whether anything else here means anything
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProvRow:
    start: int
    end: int
    kind: str
    note: str


def _read_lines(path: Path) -> list[str]:
    """File as a list of lines, LF-normalised, without the empty tail after the final newline.

    ``\\r\\n`` is normalised **before** comparison rather than after, because this repository
    is edited on Windows and a checkout that flipped line endings would otherwise report every
    line of a byte-identical copy as different — a failure whose message points nowhere.

    A relative path resolves against :func:`repo_root`, never ``cwd``: this program is run
    from the repository root and from an editor's scratch directory, and a fidelity check that
    silently reads a different file depending on the shell is worse than no check.
    """
    if not path.is_absolute():
        path = repo_root() / path
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def parse_provenance(lines: Sequence[str]) -> list[ProvRow]:
    rows: list[ProvRow] = []
    for line in lines:
        match = _PROV.match(line)
        if match is not None:
            rows.append(
                ProvRow(int(match.group(1)), int(match.group(2)), match.group(3), match.group(4))
            )
    return rows


def check_schema_fidelity(schema_path: Path = SCHEMA_SQL) -> dict[str, Any]:
    """Prove the evidence DDL's ``clause_embedding`` statement is byte-identical to 0031's.

    Three separate claims, each of which can fail on its own and each of which is reported
    separately, because "the schema matches" is exactly the kind of summary that hides which
    half of it was actually checked:

    1. the ``@prov`` ranges are contiguous, start at line 1 and cover the file to its last
       line — so no range can quietly stop covering the lines it names;
    2. every ``VERBATIM`` range is equal, line for line, to the range it names in its source;
    3. the copied block is a complete statement — it starts with ``CREATE TABLE`` and its last
       line is ``);`` — so a range cannot be "identical" by naming a fragment.
    """
    schema_lines = _read_lines(schema_path)
    prov = parse_provenance(schema_lines)
    findings: list[str] = []

    coverage: dict[str, Any] = {
        "rows": len(prov),
        "file_lines": len(schema_lines),
        "contiguous": True,
        "covers_file": True,
    }
    cursor = 1
    for row in prov:
        if row.start != cursor:
            coverage["contiguous"] = False
            findings.append(
                f"@prov range L{row.start:03d}-L{row.end:03d} does not continue from line "
                f"{cursor}; the ranges have a hole or an overlap"
            )
        if row.end < row.start:
            coverage["contiguous"] = False
            findings.append(f"@prov range L{row.start:03d}-L{row.end:03d} runs backwards")
        cursor = row.end + 1
    if prov and cursor - 1 != len(schema_lines):
        coverage["covers_file"] = False
        findings.append(
            f"@prov ranges stop at line {cursor - 1} but the file has {len(schema_lines)} lines"
        )
    if not prov:
        findings.append("the schema file declares no @prov ranges at all")

    diffs: list[dict[str, Any]] = []
    verbatim_reports: list[dict[str, Any]] = []
    for row in prov:
        if row.kind != "VERBATIM":
            continue
        match = _PROV_SOURCE.match(row.note)
        if match is None:
            findings.append(f"VERBATIM row L{row.start}-L{row.end} names no parsable source")
            continue
        source_path = repo_root() / match.group(1)
        src_start, src_end = int(match.group(2)), int(match.group(3))
        source_lines = _read_lines(source_path)
        here = schema_lines[row.start - 1 : row.end]
        there = source_lines[src_start - 1 : src_end]
        report: dict[str, Any] = {
            "local_range": f"L{row.start}-L{row.end}",
            "source": match.group(1),
            "source_range": f"L{src_start}-L{src_end}",
            "local_line_count": len(here),
            "source_line_count": len(there),
            "local_sha256": sha256_hex("\n".join(here).encode("utf-8")),
            "source_sha256": sha256_hex("\n".join(there).encode("utf-8")),
            "is_complete_statement": bool(
                here and here[0].startswith("CREATE TABLE") and here[-1].strip() == ");"
            ),
        }
        report["byte_identical"] = (
            report["local_sha256"] == report["source_sha256"]
            and report["local_line_count"] == report["source_line_count"]
        )
        # The line-by-line comparison, published in full rather than as a count of
        # differences.  "0 diffs" is a claim about what was not found; a table with one row
        # per line, each carrying the digest of the bytes that were compared, is a claim about
        # what was.  Seventeen rows is a readable size for the thing this file exists to prove.
        pairs: list[dict[str, Any]] = []
        for offset in range(max(len(here), len(there))):
            left = here[offset] if offset < len(here) else None
            right = there[offset] if offset < len(there) else None
            pairs.append(
                {
                    "local_line": row.start + offset,
                    "source_line": src_start + offset,
                    "equal": left == right,
                    "sha256": None if left is None else sha256_hex(left.encode("utf-8")),
                    "text": left if left == right else None,
                }
            )
            if left != right:
                diffs.append(
                    {
                        "local_line": row.start + offset,
                        "source_line": src_start + offset,
                        "local": left,
                        "source": right,
                    }
                )
        report["lines"] = pairs
        report["lines_equal"] = sum(1 for pair in pairs if pair["equal"])
        if not report["byte_identical"]:
            findings.append(
                f"VERBATIM range {report['local_range']} is NOT byte-identical to "
                f"{match.group(1)} {report['source_range']}"
            )
        if not report["is_complete_statement"]:
            findings.append(
                f"VERBATIM range {report['local_range']} is not a complete CREATE TABLE "
                "statement; a fragment can be identical and still prove nothing"
            )
        verbatim_reports.append(report)

    return {
        "schema_file": schema_path.as_posix(),
        "coverage": coverage,
        "provenance": [
            {"range": f"L{r.start:03d}-L{r.end:03d}", "kind": r.kind, "note": r.note} for r in prov
        ],
        "verbatim": verbatim_reports,
        "diff_lines": diffs,
        "diff_line_count": len(diffs),
        "findings": findings,
        "ok": not findings,
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2 · The schema file as executable statements
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Statement:
    target: str  # "cluster" or a database name
    sql: str
    first_line: int


def parse_statements(schema_path: Path = SCHEMA_SQL) -> list[Statement]:
    """Split the schema file into ``-- @connect``-tagged statements.

    Not a general SQL parser and not trying to be: the file is four statements written by this
    repository, and a splitter that handles dollar-quoting it will never meet is a splitter
    with untested branches.  A statement ends at a line whose stripped form ends in ``;``,
    which is true of every statement here and asserted by the count check in :func:`main`.
    """
    lines = _read_lines(schema_path)
    statements: list[Statement] = []
    target: str | None = None
    buffer: list[str] = []
    start = 0
    for number, line in enumerate(lines, 1):
        connect = _CONNECT.match(line)
        if connect is not None:
            target = connect.group(1)
            continue
        if not buffer and (not line.strip() or line.lstrip().startswith("--")):
            continue
        if not buffer:
            start = number
        buffer.append(line)
        if line.rstrip().endswith(";"):
            if target is None:
                raise ValueError(f"statement at line {start} has no `-- @connect` directive")
            statements.append(Statement(target, "\n".join(buffer), start))
            buffer = []
    if buffer:
        raise ValueError(f"unterminated statement beginning at line {start}")
    return statements


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3 · The corpus, and the prefix pairs that come out of it
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Doc:
    """One document to embed, with the prefix pair it belongs to.

    ``site_id`` and ``activity_root`` are not decoration and not a filter: C-SPANN keeps a
    separate k-means partition tree per distinct prefix value, so these two fields decide
    which tree an ANN query descends.  They are derived from the corpus — a mine identifier, a
    subunit and an activity that the document itself states — so the trees this load builds
    correspond to something, and there is more than one of them.
    """

    doc_key: str
    stream: str
    site_key: str
    activity_root: str
    text: str

    @property
    def clause_uuid(self) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{_UUID_BASE}/clause/{self.doc_key}"))

    @property
    def site_id(self) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{_UUID_BASE}/site/{self.site_key}"))

    @property
    def commit_id(self) -> bytes:
        return sha256(self.text.encode("utf-8")).digest()


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.strip().lower())).strip("-")


_HEADER_FIELD = re.compile(r"^([A-Z][A-Za-z0-9 /_-]*):\s*(.+)$")


def _headers(text: str) -> dict[str, str]:
    """The ``Field: value`` block a rendered report opens with, first occurrence winning."""
    out: dict[str, str] = {}
    for line in text.split("\n"):
        match = _HEADER_FIELD.match(line)
        if match is not None:
            out.setdefault(match.group(1).strip(), match.group(2).strip())
    return out


def load_corpus() -> list[Doc]:
    """Every document in the synthetic corpus, with a prefix pair parsed out of the document.

    The prefix is parsed from the *rendered* document rather than read out of the generator's
    internals on purpose: a reader can open the text and see the ``Mine ID`` and ``Activity``
    lines the ``activity_root`` was built from, which they cannot do for a tuple index.
    """
    for package in sorted((repo_root() / "packages").iterdir()):
        source = package / "src"
        if source.is_dir():
            sys.path.insert(0, str(source))
    from trappoint_recall.corpora import synthetic  # see the path insertion above

    corpus = synthetic.generate()
    docs: list[Doc] = []

    for report in corpus.fatality_reports:
        head = _headers(report["text"])
        mine = head.get("Mine ID", "unknown")
        docs.append(
            Doc(
                doc_key=f"msha-fai/{report['external_ref']}",
                stream="msha_fatality_report",
                site_key=f"msha/{mine}",
                activity_root=f"{_slug(head.get('Subunit', 'unknown'))}/"
                f"{_slug(head.get('Activity', 'unknown'))}",
                text=report["text"],
            )
        )

    for report in corpus.csb_reports:
        head = _headers(report["text"])
        docs.append(
            Doc(
                doc_key=f"csb/{report['external_ref']}",
                stream="csb_report",
                site_key=f"csb/{_slug(head.get('Location', 'unknown'))}",
                activity_root=f"process/{_slug(head.get('Incident Type', 'unknown'))}",
                text=report["text"],
            )
        )

    for alert in corpus.au_alerts:
        docs.append(
            Doc(
                doc_key=f"au-alert/{alert['external_ref']}",
                stream="au_regulator_alert",
                site_key=f"au/{_slug(alert['jurisdiction'])}/{_slug(alert['site'])}",
                activity_root=f"{_slug(alert['jurisdiction'])}/{_slug(alert['incident_type'])}",
                text=f"{alert['title']}\n\n{alert['text']}",
            )
        )

    header, *rows = corpus.part50_lines
    columns = {name: index for index, name in enumerate(header.split("|"))}
    for row in rows:
        fields = row.split("|")
        if len(fields) != len(columns):
            continue
        docs.append(
            Doc(
                doc_key=f"part50/{fields[columns['DOCUMENT_NO']]}",
                stream="msha_part50_line",
                site_key=f"msha/{fields[columns['MINE_ID']]}",
                activity_root=f"{_slug(fields[columns['SUBUNIT']])}/"
                f"{_slug(fields[columns['ACTIVITY']])}",
                text=fields[columns["NARRATIVE"]],
            )
        )

    return docs


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4 · Vectors — the manifest first, Bedrock second
# ═══════════════════════════════════════════════════════════════════════════════════════


def _descend(payload: Any) -> Any:
    """Step past the fleet's evidence envelope if one is present."""
    if isinstance(payload, dict) and "payload" in payload and "artefact" in payload:
        return payload["payload"]
    return payload


def _manifest_entries(raw: Any) -> list[tuple[str, Any]] | None:
    """``entries`` as ``(key, record)`` pairs, whether it was written as a mapping or a list."""
    if isinstance(raw, dict):
        return list(raw.items())
    if isinstance(raw, list):
        return [(str(r.get("id") or index), r) for index, r in enumerate(raw)]
    return None


def _manifest_array(
    key: str, record: dict[str, Any], blob: Any, names: set[str], matrix: Any
) -> Any:
    """One entry's vector out of the blob, as ``<f4``, or ``None`` if the blob does not hold it.

    Two blob layouts, because the contract named the file and not its interior: one array per
    entry keyed by the entry's own name (what the ``titan-embed`` worker actually wrote), or
    one matrix plus a row index per entry.  Anything else returns ``None`` and is counted as a
    rejection rather than guessed at.
    """
    import numpy  # only needed on this branch

    if matrix is not None:
        row = record.get("index", record.get("row"))
        if not isinstance(row, int) or not 0 <= row < matrix.shape[0]:
            return None
        return numpy.asarray(matrix[row], dtype="<f4")
    if key in names:
        return numpy.asarray(blob[key], dtype="<f4")
    return None


def read_manifest(
    manifest_path: Path = MANIFEST_PATH, npz_path: Path = MANIFEST_NPZ
) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """Vectors from the ``titan-embed`` worker's artefacts, **keyed by the digest of the text
    they were made from**.

    THE JOIN IS THE TEXT, NOT THE NAME.  The manifest calls a Part-50 line ``doc:2100000``;
    this program calls it ``part50/2100000``; a third worker will call it something else.
    Every one of those is a naming convention, and a load that matched on one would silently
    load nothing the day a convention changed.  A vector belongs to a document if and only if
    it was produced from that document's exact bytes, so ``text_sha256`` is the key and the
    corpus is re-derived here to compute the other side of it.  MEASURED on the partial
    manifest of 2026-08-11: 24 of 24 entries joined this way, 0 by name.

    EVERY VECTOR IS VERIFIED BEFORE IT IS ACCEPTED.  The manifest publishes ``sha256`` over
    "the stored little-endian C-order float32 bytes"; this recomputes it from the blob and
    refuses any vector that disagrees, and refuses any vector that is not exactly
    ``VECTOR(1024)`` wide.  A blob and a manifest that have drifted apart is precisely the
    failure that would otherwise produce a fully populated database of vectors belonging to
    the wrong documents, with every count looking correct.

    Shape tolerance is deliberate and bounded: ``entries`` may be a mapping or a list, and the
    blob may be one array per entry or one matrix plus row indices.  Everything resolved is
    reported, so ``cloud-load.json`` records the shape that was actually found rather than the
    shape this program hoped for.
    """
    report: dict[str, Any] = {
        "manifest_path": manifest_path.as_posix(),
        "npz_path": npz_path.as_posix(),
        "manifest_present": (repo_root() / manifest_path).is_file(),
        "npz_present": (repo_root() / npz_path).is_file(),
        "entries": 0,
        "blob_arrays": 0,
        "accepted": 0,
        "rejected_digest_mismatch": 0,
        "rejected_wrong_width": 0,
        "rejected_absent_from_blob": 0,
        "join": "text_sha256",
        "notes": [],
    }
    if not (report["manifest_present"] and report["npz_present"]):
        report["notes"].append(
            "manifest and/or vector blob absent at these paths; this program embedded what it "
            "needed itself and records that in `source.mode`"
        )
        return {}, report

    import numpy  # only needed on this branch

    payload = _descend(json.loads((repo_root() / manifest_path).read_text(encoding="utf-8")))
    if not isinstance(payload, dict):
        report["notes"].append("the manifest payload is not an object; not usable")
        return {}, report

    entries = _manifest_entries(payload.get("entries"))
    if entries is None:
        report["notes"].append("the manifest has no `entries` mapping or list; not usable")
        return {}, report
    report["entries"] = len(entries)
    report["manifest_model_id"] = payload.get("model_id")
    report["manifest_index_gen"] = payload.get("index_gen")
    report["manifest_complete"] = (payload.get("totals") or {}).get("complete")

    out: dict[str, list[float]] = {}
    with numpy.load(repo_root() / npz_path, allow_pickle=False) as blob:
        names = set(blob.files)
        report["blob_arrays"] = len(names)
        matrix = None
        for candidate in ("embeddings", "vectors", "matrix", "arr_0"):
            if candidate in names and blob[candidate].ndim == 2:
                matrix = blob[candidate]
                report["notes"].append(f"blob read as one matrix under `{candidate}`")
                break

        for key, record in entries:
            if not isinstance(record, dict) or not record.get("text_sha256"):
                continue
            array = _manifest_array(key, record, blob, names, matrix)
            if array is None:
                report["rejected_absent_from_blob"] += 1
            elif array.shape != (EXPECTED_DIM,):
                report["rejected_wrong_width"] += 1
            elif record.get("sha256") and sha256_hex(array.tobytes(order="C")) != record["sha256"]:
                report["rejected_digest_mismatch"] += 1
            else:
                out[str(record["text_sha256"])] = [float(v) for v in array]

    report["accepted"] = len(out)
    if report["rejected_digest_mismatch"]:
        report["notes"].append(
            f"{report['rejected_digest_mismatch']} vector(s) did not match the sha256 the "
            "manifest publishes for them and were refused rather than loaded"
        )
    return out, report


#: MEASURED, 2026-08-11: eight concurrent ``InvokeModel`` calls against Titan v2 in
#: ``ap-southeast-2`` on this account exhaust botocore's own four retries and surface
#: ``ThrottlingException: Too many requests``.  Four does not.  The number is a property of
#: this account's on-demand quota, not of the model, so it is a default and not a constant.
DEFAULT_WORKERS = 4

#: Retries for a throttle, on top of botocore's.  This is **not** the 40001 loop and must
#: never be confused with it: that one exists because a database refused to serialise, this
#: one exists because a service asked us to slow down.  They are separate because the correct
#: response to each is different, and a helper that handled both would do neither properly.
#:
#: MEASURED, 2026-08-11, ``AWS/Bedrock`` metrics for ``amazon.titan-embed-text-v2:0`` in
#: ``ap-southeast-2`` while two fleet workers ran: **300 ``Invocations`` and ~3 800
#: ``InvocationThrottles`` per 5-minute period** — a hard on-demand ceiling of one call per
#: second for the whole account, with roughly nine of every ten requests refused.  Ten
#: attempts, not six, because at that ratio six is not a slow path, it is a coin toss.
THROTTLE_ATTEMPTS = 10

#: MEASURED, 2026-08-11: with the sibling ``titan-embed`` worker running against the same
#: account, a 1 080-document pass from this program was still unfinished after 14 minutes and
#: both programs were throttling each other.  This caps what THIS program embeds on its own —
#: never what the manifest already covers — so the fleet's shared quota goes to the worker
#: whose job the embedding is.  ``--max-self-embed 0`` removes the cap.
MAX_SELF_EMBED = 240


def recordable_failures() -> tuple[type[BaseException], ...]:
    """The failure classes this program records into an artefact instead of raising.

    Enumerated, and deliberately not ``Exception``.  ``ruff``'s ``BLE`` family is enforced
    repository-wide because "a bare or blanket ``except`` is how a refusal becomes a
    silence", and that reasoning survives being inconvenient here: a driver error, a service
    error or a filesystem error is a *measurement* this program is prepared to write down,
    whereas a ``TypeError`` in this file is a defect that must stop the run loudly rather
    than appear in an evidence file as a target that was merely "unavailable".

    Imported lazily and returned as a tuple so that an ``except`` clause can name it: the
    drivers are optional on the ``--fidelity-only`` path, which must run with no ``psycopg``,
    no ``boto3`` and no credentials at all.
    """
    import psycopg
    from botocore.exceptions import BotoCoreError, ClientError

    return (psycopg.Error, ClientError, BotoCoreError, OSError, ValueError, RuntimeError)


def _titan_embed(runtime: Any, text: str) -> tuple[list[float], int]:
    """One InvokeModel, retried on throttling.  Returns ``(embedding, input_tokens)``.

    ``dimensions`` and ``normalize`` are stated rather than defaulted: the width must equal
    what ``VECTOR(1024)`` declares, and a normalised vector is what makes cosine distance and
    inner product agree — both are properties the DDL and the ANN arm depend on, so both are
    requested at the call site where a reader can see them.
    """
    from botocore.exceptions import ClientError  # not needed by --fidelity-only

    body = json.dumps({"inputText": text, "dimensions": EXPECTED_DIM, "normalize": True}).encode(
        "utf-8"
    )
    for attempt in range(1, THROTTLE_ATTEMPTS + 1):
        try:
            response = runtime.invoke_model(
                modelId=assert_in_region(TITAN_MODEL_ID),
                contentType="application/json",
                accept="application/json",
                body=body,
            )
            break
        except ClientError as exc:
            code = (exc.response.get("Error") or {}).get("Code")
            if code not in {"ThrottlingException", "TooManyRequestsException"}:
                raise
            if attempt == THROTTLE_ATTEMPTS:
                raise
            # Exponential with full jitter: a throttle is a shared-quota signal, so N workers
            # backing off in lockstep would re-collide on the same second.  The jitter is a
            # politeness delay, not a secret, a key, a nonce or an identifier — a
            # cryptographic generator here would buy nothing, hence the S311 waiver.
            window = min(8.0, 0.5 * 2 ** (attempt - 1))
            time.sleep(window * (0.5 + random.random()))  # noqa: S311
    payload = json.loads(response["body"].read())
    embedding = [float(v) for v in payload["embedding"]]
    if len(embedding) != EXPECTED_DIM:
        raise RuntimeError(
            f"Titan returned {len(embedding)} dimensions, not {EXPECTED_DIM}; refusing to "
            "store a vector the DDL cannot hold"
        )
    return embedding, int(payload.get("inputTextTokenCount") or 0)


def embed_documents(
    docs: Sequence[Doc], *, workers: int = DEFAULT_WORKERS, cache: Path | None = FALLBACK_NPZ
) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """Embed every document through Titan, reusing a local cache keyed by text digest.

    The cache key is the SHA-256 of the *text*, never the document id: a corpus regenerated
    with a different seed produces the same ids and different prose, and a cache keyed by id
    would then serve a vector for text that no longer exists.  ``out/`` is gitignored — the
    cache is a way to make a re-run free, and it is not evidence of anything.
    """
    import numpy  # the blob format, not needed by --fidelity-only

    report: dict[str, Any] = {
        "documents": len(docs),
        "cache_path": cache.as_posix() if cache else None,
        "cache_hits": 0,
        "cache_hit_input_tokens": 0,
        "bedrock_calls": 0,
        "input_tokens": 0,
        "elapsed_s": 0.0,
        "workers": workers,
        "note": (
            "`bedrock_calls` counts InvokeModel in THIS process. `cache_hits` counts vectors "
            "this same program bought from Bedrock in an earlier run of itself and stored "
            "under out/ (gitignored). Both were paid for; only the first was paid for now, "
            "and the token ledger carries them as two rows so neither is double-counted nor "
            "disappears."
        ),
    }
    cached: dict[str, list[float]] = {}
    cached_tokens: dict[str, int] = {}
    cache_file = (repo_root() / cache) if cache else None
    if cache_file is not None and cache_file.is_file():
        with numpy.load(cache_file, allow_pickle=False) as blob:
            digests = [str(d) for d in blob["digests"].tolist()]
            for digest, row in zip(digests, blob["vectors"], strict=True):
                cached[digest] = [float(v) for v in row]
            if "tokens" in blob.files:
                for digest, count in zip(digests, blob["tokens"].tolist(), strict=True):
                    cached_tokens[digest] = int(count)

    # Deduplicated by text digest, not by document key.  MEASURED, 2026-08-11: a 240-document
    # pass made 218 successful InvokeModel calls but produced only 156 distinct vectors,
    # because the synthetic Part-50 generator emits the same narrative for more than one
    # document number.  On an account whose Titan quota is one call per second, paying twice
    # for the same 1 024 floats is quota taken from the worker that still needs it.
    seen: set[str] = set()
    todo: list[Doc] = []
    for doc in docs:
        digest = sha256_hex(doc.text.encode("utf-8"))
        if digest in cached or digest in seen:
            continue
        seen.add(digest)
        todo.append(doc)
    hit_digests = {sha256_hex(d.text.encode("utf-8")) for d in docs} - {
        sha256_hex(d.text.encode("utf-8")) for d in todo
    }
    report["cache_hits"] = len(docs) - len(todo)
    report["cache_hit_input_tokens"] = sum(cached_tokens.get(d, 0) for d in hit_digests)
    report["cache_carries_token_counts"] = bool(cached_tokens) or not cached

    started = time.perf_counter()
    failures: list[dict[str, str]] = []
    if todo:
        runtime = bedrock_runtime()

        def one(doc: Doc) -> tuple[str, list[float], int]:
            embedding, tokens = _titan_embed(runtime, doc.text)
            return sha256_hex(doc.text.encode("utf-8")), embedding, tokens

        # ``as_completed`` rather than ``map``: one throttled document must not discard the
        # vectors already paid for.  Everything that succeeded is written to the cache below
        # even when the run as a whole fails, so a re-run costs only what actually failed.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(one, doc): doc for doc in todo}
            for future in as_completed(futures):
                try:
                    digest, embedding, tokens = future.result()
                except recordable_failures() as exc:
                    failures.append(
                        {
                            "doc_key": futures[future].doc_key,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                cached[digest] = embedding
                cached_tokens[digest] = tokens
                report["bedrock_calls"] += 1
                report["input_tokens"] += tokens
    report["elapsed_s"] = round(time.perf_counter() - started, 3)
    report["failures"] = failures

    if cache_file is not None and todo:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        keys = sorted(cached)
        numpy.savez_compressed(
            cache_file,
            digests=numpy.array(keys),
            vectors=numpy.array([cached[d] for d in keys], dtype=numpy.float32),
            tokens=numpy.array([cached_tokens.get(d, 0) for d in keys], dtype=numpy.int32),
        )
    # A document that could not be embedded is DROPPED and NAMED, not fatal.  MEASURED,
    # 2026-08-11: `AWS/Bedrock` reported 300 successful `Invocations` and ~3 800
    # `InvocationThrottles` per 5-minute period against Titan v2 on this account while two
    # fleet workers ran, so exhausting the throttle budget on some documents is the expected
    # weather, not a defect.  Raising here would throw away every vector already paid for and
    # every artefact downstream of them; instead `source.embedding.failures` carries the
    # document key and the error for each one, and the row counts fall to match.
    return {
        d.doc_key: cached[sha256_hex(d.text.encode("utf-8"))]
        for d in docs
        if sha256_hex(d.text.encode("utf-8")) in cached
    }, report


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5 · Writing vectors
# ═══════════════════════════════════════════════════════════════════════════════════════


#: ``%.8g`` — eight significant digits.  ``VECTOR`` is float32 on this platform, which carries
#: about seven; eight is therefore lossless with respect to what the column can store, and it
#: is a third of the width of ``repr(float)``, which matters when a batch statement carries
#: fifty of them.
def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(v):.8g}" for v in values) + "]"


def undashed(value: str) -> str:
    """A UUID's 32 hex characters, published beside the dashed form so it survives redaction.

    MEASURED, 2026-08-11, and it cost an evidence file before it was noticed.  The fleet's
    redactor scrubs a bare twelve-digit run because that is the shape of an AWS account id
    (``_common.py::_ACCOUNT_ID``), and its boundaries are *non-alphanumeric* — which a UUID's
    hyphens are.  The demo clause is ``dec0de00-0004-4000-8000-000000000001``; its final group
    is twelve decimal digits with a hyphen in front, so ``redact`` rewrote it to
    ``dec0de00-0004-4000-8000-<redacted>`` and the artefact no longer named the row it was
    about.  The undashed form is a thirty-two character alphanumeric run: the lookbehind fails
    inside it, nothing matches, and the identifier arrives intact.

    Both forms are published.  The dashed one is what you paste into ``psql``; this one is
    what you compare, and it is the one to trust when they disagree.
    """
    return value.replace("-", "")


def _chunks(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _execute_ddl(statements: Sequence[Statement], *, dsn: str | None, admin_db: str) -> list[str]:
    """Run the schema file's statements against their declared targets.  Returns what ran.

    The evidence tables are dropped first when they exist.  That is deliberate: it makes the
    ``CREATE TABLE`` statement — the byte-identical one — execute on every run, so a claim
    about the DDL is a claim about DDL that just ran, not about DDL that ran once in July.
    """
    issued: list[str] = []
    by_target: dict[str, list[Statement]] = {}
    for statement in statements:
        by_target.setdefault(statement.target, []).append(statement)

    for statement in by_target.pop("cluster", []):
        with crdb(admin_db, dsn=dsn) as conn:
            conn.execute(statement.sql)
        issued.append(statement.sql)

    for database, group in by_target.items():
        with crdb(database, dsn=dsn) as conn:
            for drop in (
                "DROP TABLE IF EXISTS mainline.clause_embedding",
                "DROP TABLE IF EXISTS mainline.clause_version",
            ):
                conn.execute(drop)
                issued.append(drop)
            for statement in group:
                conn.execute(statement.sql)
                issued.append(statement.sql)
    return issued


_INSERT_PARENT = (
    "INSERT INTO mainline.clause_version (clause_uuid, commit_id) VALUES {values} "
    "ON CONFLICT DO NOTHING"
)
_INSERT_EMBEDDING = (
    "INSERT INTO mainline.clause_embedding "
    "(clause_uuid, commit_id, site_id, activity_root, embed_model, index_gen, embedding) "
    "VALUES {values}"
)


def _multi_values(columns: int, rows: int) -> str:
    tuple_sql = "(" + ",".join(["%s"] * columns) + ")"
    return ",".join([tuple_sql] * rows)


def load_evidence_rows(
    docs: Sequence[Doc],
    vectors: dict[str, list[float]],
    *,
    dsn: str | None,
    batch_size: int,
) -> dict[str, Any]:
    """Insert every document's parent stub and vector, batched, through the 40001 loop.

    One transaction per batch, holding both the parent stub rows and the embeddings, so the
    foreign key is satisfied inside the transaction that needs it and a retried batch replays
    as a unit rather than half-landing.
    """
    result: dict[str, Any] = {
        "rows_offered": len(docs),
        "batch_size": batch_size,
        "batches": 0,
        "retries_40001": 0,
        "vector_literal_bytes": 0,
        "elapsed_s": 0.0,
    }
    started = time.perf_counter()
    with crdb(EVIDENCE_DB, dsn=dsn) as conn:
        for batch in _chunks(list(docs), batch_size):
            parent_params: list[Any] = []
            child_params: list[Any] = []
            for doc in batch:
                literal = vector_literal(vectors[doc.doc_key])
                result["vector_literal_bytes"] += len(literal)
                parent_params.extend([doc.clause_uuid, doc.commit_id])
                child_params.extend(
                    [
                        doc.clause_uuid,
                        doc.commit_id,
                        doc.site_id,
                        doc.activity_root,
                        TITAN_MODEL_ID,
                        INDEX_GEN,
                        literal,
                    ]
                )
            parent_sql = _INSERT_PARENT.format(values=_multi_values(2, len(batch)))
            child_sql = _INSERT_EMBEDDING.format(values=_multi_values(7, len(batch)))

            def write(
                parent_sql: str = parent_sql,
                child_sql: str = child_sql,
                parent_params: list[Any] = parent_params,
                child_params: list[Any] = child_params,
            ) -> int:
                with conn.transaction():
                    cursor = conn.cursor()
                    cursor.execute(parent_sql, parent_params)
                    cursor.execute(child_sql, child_params)
                return 1

            _, retries = with_retry(write, attempts=8)
            result["retries_40001"] += retries
            result["batches"] += 1
    result["elapsed_s"] = round(time.perf_counter() - started, 3)
    return result


def survey_evidence_db(*, dsn: str | None) -> dict[str, Any]:
    """Counts, prefix census and the server's own DDL, read back after the load."""
    with crdb(EVIDENCE_DB, dsn=dsn) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM mainline.clause_version")
        parents = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM mainline.clause_embedding")
        children = cursor.fetchone()[0]
        cursor.execute(
            "SELECT site_id::STRING, activity_root, count(*) FROM mainline.clause_embedding "
            "GROUP BY site_id, activity_root ORDER BY 2, 1"
        )
        prefixes = [
            {
                "site_id": site,
                "site_id_hex32": undashed(site),
                "activity_root": root,
                "rows": int(rows),
            }
            for site, root, rows in cursor.fetchall()
        ]
        cursor.execute(
            "SELECT count(DISTINCT embed_model), count(DISTINCT index_gen), "
            "min(vector_dims(embedding)), max(vector_dims(embedding)) "
            "FROM mainline.clause_embedding"
        )
        models, gens, min_dim, max_dim = cursor.fetchone()
        cursor.execute("SHOW CREATE TABLE mainline.clause_embedding")
        show_create = cursor.fetchone()[1]
    return {
        "clause_version_rows": int(parents),
        "clause_embedding_rows": int(children),
        "distinct_prefix_pairs": len(prefixes),
        "per_prefix": prefixes,
        "distinct_embed_models": int(models or 0),
        "distinct_index_gens": int(gens or 0),
        "vector_dims_min": None if min_dim is None else int(min_dim),
        "vector_dims_max": None if max_dim is None else int(max_dim),
        "show_create": show_create,
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6 · The production row
# ═══════════════════════════════════════════════════════════════════════════════════════


def production_row(runtime_vectors: dict[str, list[float]] | None = None) -> dict[str, Any]:
    """Embed the one real ``clause_version``'s ``canon_text`` and insert one row.

    Everything about this function is scoped to one row on purpose.  It reads the parent that
    already exists, embeds the text that parent actually carries, and inserts into the real
    sidecar under the real FK.  It never writes to ``clause_version`` — that table is behind
    three triggers, and the entire value of this row is that it did not go around them.
    """
    result: dict[str, Any] = {
        "database": PRODUCTION_DB,
        "table": "mainline.clause_embedding",
        "embed_model": TITAN_MODEL_ID,
        "index_gen": INDEX_GEN,
        "retries_40001": 0,
    }
    with crdb(PRODUCTION_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM mainline.clause_embedding")
        result["count_before"] = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT clause_uuid::STRING, encode(commit_id, 'hex'), site_id::STRING, "
            "activity_root, canon_text, gen, encode(canon_sha256, 'hex') "
            "FROM mainline.clause_version ORDER BY clause_uuid, gen LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            result["error"] = "mainline.clause_version is empty; there is nothing to embed"
            return result
        clause_uuid, commit_hex, site_id, activity_root, canon_text, gen, canon_sha = row
        commit_id = bytes.fromhex(commit_hex)
        result["identifier_note"] = (
            "every UUID is published twice: dashed, and as its 32 hex characters. The fleet "
            "redactor scrubs bare 12-digit runs and a UUID's final group is one, so the dashed "
            "form of this particular clause comes back partly redacted. See "
            "scripts/aws/load_vectors.py::undashed. The _hex32 fields are authoritative."
        )
        result["parent"] = {
            "clause_uuid": clause_uuid,
            "clause_uuid_hex32": undashed(clause_uuid),
            "site_id_hex32": undashed(site_id),
            "commit_id_hex": commit_hex,
            "gen": int(gen),
            "site_id": site_id,
            "activity_root": activity_root,
            "canon_sha256": canon_sha,
            "canon_text_sha256": sha256_hex(canon_text.encode("utf-8")),
            "canon_text_chars": len(canon_text),
            "triggers_on_parent": [
                "append_only",
                "z_delta_witness_required",
                "clause_version_guard",
            ],
        }

        digest = sha256_hex(canon_text.encode("utf-8"))
        reused = (runtime_vectors or {}).get(digest)
        if reused is not None:
            embedding, tokens = reused, 0
            result["vector_source"] = "reused from the embedding cache/manifest by text digest"
        else:
            embedding, tokens = _titan_embed(bedrock_runtime(), canon_text)
            result["vector_source"] = f"live InvokeModel against {TITAN_MODEL_ID} in {REGION}"
        result["input_tokens"] = tokens
        result["embedding_dim"] = len(embedding)
        result["embedding_sha256"] = sha256_hex(
            json.dumps(embedding, separators=(",", ":")).encode("utf-8")
        )
        result["embedding_l2_norm"] = round(sum(v * v for v in embedding) ** 0.5, 9)

        cursor.execute(
            "SELECT count(*) FROM mainline.clause_embedding WHERE clause_uuid = %s "
            "AND commit_id = %s",
            (clause_uuid, commit_id),
        )
        pre_existing = int(cursor.fetchone()[0]) > 0
        result["pre_existing_row"] = pre_existing

        literal = vector_literal(embedding)

        # The count at each stage, INCLUDING the one taken inside the transaction after the
        # delete.  On a first run the sequence is 0 -> 1 and the middle row is absent.  On a
        # re-run it is 1 -> 0 -> 1, and printing all three is the difference between "the table
        # still contains a row" and "this run put one there": the second is the claim, and
        # without the middle number the artefact cannot tell them apart.
        stages: dict[str, int] = {}

        def write() -> None:
            with conn.transaction():
                inner = conn.cursor()
                if pre_existing:
                    # A re-run must re-exercise the INSERT rather than report yesterday's row.
                    # `clause_embedding` carries no append-only trigger — verified by reading
                    # `pg_trigger` for this table, which returns zero rows — so the delete is a
                    # permitted operation on the sidecar and not a gate being stepped around.
                    inner.execute(
                        "DELETE FROM mainline.clause_embedding WHERE clause_uuid = %s "
                        "AND commit_id = %s",
                        (clause_uuid, commit_id),
                    )
                    inner.execute("SELECT count(*) FROM mainline.clause_embedding")
                    stages["after_delete_in_txn"] = int(inner.fetchone()[0])
                inner.execute(
                    "INSERT INTO mainline.clause_embedding (clause_uuid, commit_id, site_id, "
                    "activity_root, embed_model, index_gen, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        clause_uuid,
                        commit_id,
                        site_id,
                        activity_root,
                        TITAN_MODEL_ID,
                        INDEX_GEN,
                        literal,
                    ),
                )

        started = time.perf_counter()
        _, retries = with_retry(write, attempts=8)
        result["retries_40001"] = retries
        result["insert_elapsed_s"] = round(time.perf_counter() - started, 3)

        cursor.execute("SELECT count(*) FROM mainline.clause_embedding")
        result["count_after"] = int(cursor.fetchone()[0])
        result["count_sequence"] = (
            [result["count_before"], stages["after_delete_in_txn"], result["count_after"]]
            if "after_delete_in_txn" in stages
            else [result["count_before"], result["count_after"]]
        )
        result["count_sequence_note"] = (
            "before -> (after the delete, read inside the same transaction, only on a re-run) "
            "-> after. The last transition is always an INSERT that the production table's FK, "
            "CHECK constraints and vector index accepted during THIS run."
        )
        cursor.execute(
            "SELECT embed_model, index_gen, vector_dims(embedding), site_id::STRING, "
            "activity_root FROM mainline.clause_embedding WHERE clause_uuid = %s "
            "AND commit_id = %s",
            (clause_uuid, commit_id),
        )
        result.update(_read_back(cursor, cursor.fetchone()))
    return result


def _read_back(cursor: Any, stored: Sequence[Any]) -> dict[str, Any]:
    """What the server says about the row and the table, after the insert committed.

    Read back rather than echoed: the values this reports came out of ``clause_embedding``,
    not out of the variables that were sent to it, which is the only version of "the row is
    there" worth writing into an evidence file.
    """
    cursor.execute("SHOW CREATE TABLE mainline.clause_embedding")
    show_create = cursor.fetchone()[1]
    cursor.execute(
        "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "WHERE c.relname = 'clause_embedding'"
    )
    triggers = int(cursor.fetchone()[0])
    return {
        "stored_row": {
            "embed_model": stored[0],
            "index_gen": stored[1],
            "vector_dims": int(stored[2]),
            "site_id": stored[3],
            "site_id_hex32": undashed(stored[3]),
            "activity_root": stored[4],
        },
        "show_create": show_create,
        "triggers_on_clause_embedding": triggers,
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 7 · The 40001 loop, made to fire
# ═══════════════════════════════════════════════════════════════════════════════════════


def contention_probe(*, dsn: str | None, label: str) -> dict[str, Any]:
    """Force a ``RETRY_SERIALIZABLE`` and record how the loop handled it.

    A bulk load of disjoint primary keys can legitimately run to completion without a single
    serialization failure, and reporting "0 retries" on its own is indistinguishable from
    reporting that the loop does not work.  So this deliberately builds the conflict the loop
    exists for — read a row in transaction A, commit a conflicting write from transaction B,
    then write from A — and publishes the trip count separately, never added to the load's.

    The interference happens **only on the first attempt**.  A probe that re-interfered on
    every retry would prove the loop can loop, not that it can recover, and would eventually
    exhaust ``attempts`` and look like a bug.
    """
    report: dict[str, Any] = {
        "label": label,
        "database": SCRATCH_DB,
        "table": "public.retry_probe",
        "method": (
            "transaction A reads k=1; transaction B commits an update to k=1; transaction A "
            "then writes k=1 and commits — a write-after-read conflict, which CockroachDB "
            "refuses under SERIALIZABLE with SQLSTATE 40001"
        ),
        "attempts_allowed": 8,
    }
    with crdb("defaultdb", dsn=dsn) as admin:
        admin.execute(f"CREATE DATABASE IF NOT EXISTS {SCRATCH_DB}")
    with crdb(SCRATCH_DB, dsn=dsn) as setup:
        setup.execute(
            "CREATE TABLE IF NOT EXISTS public.retry_probe (k INT PRIMARY KEY, v INT NOT NULL)"
        )
        setup.execute("UPSERT INTO public.retry_probe (k, v) VALUES (1, 0)")

    reader = crdb(SCRATCH_DB, dsn=dsn, autocommit=False)
    writer = crdb(SCRATCH_DB, dsn=dsn, autocommit=False)
    state = {"attempts": 0, "interfered": False}
    try:

        def transaction() -> int:
            # A retried attempt starts from a clean transaction, not a poisoned one.
            reader.rollback()
            cursor = reader.cursor()
            cursor.execute("SELECT v FROM public.retry_probe WHERE k = 1")
            value = int(cursor.fetchone()[0])
            state["attempts"] += 1
            if not state["interfered"]:
                state["interfered"] = True
                other = writer.cursor()
                other.execute("UPDATE public.retry_probe SET v = v + 100 WHERE k = 1")
                writer.commit()
            cursor.execute("UPDATE public.retry_probe SET v = %s WHERE k = 1", (value + 1,))
            reader.commit()
            return value

        started = time.perf_counter()
        observed, retries = with_retry(transaction, attempts=8)
        report["elapsed_s"] = round(time.perf_counter() - started, 3)
        report["attempts_made"] = state["attempts"]
        report["retries_40001"] = retries
        report["value_read_on_final_attempt"] = observed
        report["loop_fired"] = retries > 0
        report["committed"] = True
    except recordable_failures() as exc:  # a probe that fails is still a measurement
        report["committed"] = False
        report["loop_fired"] = False
        report["attempts_made"] = state["attempts"]
        report["error_type"] = type(exc).__name__
        report["sqlstate"] = getattr(exc, "sqlstate", None)
        report["error"] = str(exc)[:400]
    finally:
        reader.close()
        writer.close()
    return report


# ═══════════════════════════════════════════════════════════════════════════════════════
# 8 · One target, end to end
# ═══════════════════════════════════════════════════════════════════════════════════════


def load_target(
    name: str,
    dsn: str | None,
    docs: Sequence[Doc],
    vectors: dict[str, list[float]],
    *,
    batch_size: int,
) -> dict[str, Any]:
    """Render the schema and load every vector against one cluster.  Never raises."""
    report: dict[str, Any] = {"target": name, "available": False}
    started = time.perf_counter()
    try:
        with crdb("defaultdb", dsn=dsn) as probe:
            cursor = probe.cursor()
            cursor.execute("SELECT version()")
            report["server_version"] = cursor.fetchone()[0].split(" (", 1)[0]
        report["available"] = True
    except recordable_failures() as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:600]
        report["status"] = "unavailable"
        return report

    # From here on a failure is recorded against this target and nothing else.  The local
    # Docker node is optional by fleet rule, and a loader that let it take the Cloud evidence
    # down with it would make the optional thing mandatory in practice.
    try:
        statements = parse_statements()
        ddl_started = time.perf_counter()
        report["ddl_statements_issued"] = _execute_ddl(statements, dsn=dsn, admin_db="defaultdb")
        report["ddl_elapsed_s"] = round(time.perf_counter() - ddl_started, 3)

        report["load"] = load_evidence_rows(docs, vectors, dsn=dsn, batch_size=batch_size)
        report["survey"] = survey_evidence_db(dsn=dsn)
        report["retry_probe"] = contention_probe(dsn=dsn, label=f"{name}/induced-write-after-read")
        report["status"] = "loaded"
    except recordable_failures() as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        report["sqlstate"] = getattr(exc, "sqlstate", None)
        report["error"] = str(exc)[:600]
    report["elapsed_s"] = round(time.perf_counter() - started, 3)
    return report


def compare_show_create(production: str | None, renderings: dict[str, str]) -> dict[str, Any]:
    """Diff the *server's* rendering of ``clause_embedding`` in production against each copy.

    Two files agreeing on disk is a weaker fact than two clusters agreeing about what they
    built: the DDL passes through a parser, a normaliser and a set of database-level defaults
    before it becomes a table, and any of those could differ.  This reads
    ``SHOW CREATE TABLE`` back from each database and reports the lines that differ rather
    than a verdict, because the expected differences here — database-level ``LOCALITY`` and
    ``schema_locked`` inheritance — are real and a check that hid them would be worthless.
    """
    out: dict[str, Any] = {
        "production": None if production is None else {"sha256": sha256_hex(production.encode())},
        "comparisons": [],
        "note": (
            "differences in LOCALITY or WITH(...) are database-level properties the cluster "
            "applies, not differences in the CREATE TABLE statement this repository wrote; "
            "differences in a column, constraint, index or family would be the opposite"
        ),
    }
    if production is None:
        out["comparisons"].append({"status": "production rendering unavailable this run"})
        return out
    left = production.split("\n")
    for name, rendering in renderings.items():
        right = rendering.split("\n")
        differing = [
            {"line": index + 1, "production": a, name: b}
            for index, (a, b) in enumerate(zip(left, right, strict=False))
            if a != b
        ]
        if len(left) != len(right):
            differing.append(
                {"line": None, "production": f"{len(left)} lines", name: f"{len(right)} lines"}
            )
        out["comparisons"].append(
            {
                "database": name,
                "sha256": sha256_hex(rendering.encode()),
                "identical": not differing,
                "differing_lines": differing,
            }
        )
    return out


def strip_sql_comments(sql: str) -> str:
    """Drop ``--`` comments, respecting single-quoted strings.

    The scan below runs on the output.  That is not a loophole, it is the only reading of the
    rule that survives contact with this repository: ``ann_evidence_schema.sql``'s header
    *states the prohibition by name* — "There is no ``CREATE SEQUENCE``, no ``nextval``" — and
    a checker that flags the sentence documenting the ban is a checker someone will switch
    off within a week.  The ban is on executable SQL, so executable SQL is what is scanned,
    and the stripping is a named function a reviewer can read rather than a regex tweak.
    """
    out: list[str] = []
    for line in sql.split("\n"):
        in_string = False
        code = line
        for index, char in enumerate(line):
            if char == "'":
                in_string = not in_string
            elif char == "-" and not in_string and line[index : index + 2] == "--":
                code = line[:index]
                break
        out.append(code)
    return "\n".join(out)


def scan_banned(statements: Iterable[str]) -> dict[str, Any]:
    """Assert the banned identity constructs are absent from the SQL that actually ran."""
    scanned = list(statements)
    hits: list[dict[str, Any]] = []
    for index, statement in enumerate(scanned):
        for match in BANNED_IDENTITY.finditer(strip_sql_comments(statement)):
            hits.append({"statement_index": index, "match": match.group(0)})
    return {
        "banned": ["CREATE SEQUENCE", "nextval", "SERIAL", "unique_rowid"],
        "scanned_statements": len(scanned),
        "scope": (
            "every DDL statement this program issued, both INSERT templates, and the whole of "
            "ann_evidence_schema.sql — with `--` comments stripped, because the file's header "
            "names the prohibition in prose"
        ),
        "hits": hits,
        "clean": not hits,
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 9 · main
# ═══════════════════════════════════════════════════════════════════════════════════════


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--fidelity-only",
        action="store_true",
        help=(
            "run the schema provenance and byte-identity checks alone: no AWS, no cluster, "
            "and no artefact is written or overwritten"
        ),
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument(
        "--limit", type=int, default=0, help="cap the number of documents (0 = the whole corpus)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="concurrent Bedrock invocations; 8 throttles on this account, 4 does not",
    )
    parser.add_argument(
        "--max-self-embed",
        type=int,
        default=MAX_SELF_EMBED,
        help=(
            "cap on documents this program embeds itself, over and above everything the "
            "manifest already covers; 0 removes the cap"
        ),
    )
    parser.add_argument(
        "--skip-local", action="store_true", help="do not attempt the local Docker node"
    )
    parser.add_argument("--skip-production", action="store_true", help="do not touch mainline_demo")
    return parser.parse_args(argv)


FIDELITY_CAVEATS = (
    (
        "byte-identity of a CREATE TABLE statement is not equivalence of two databases: the "
        "evidence database's parent table is a two-column stub with none of clause_version's "
        "three triggers, and this check says nothing about that"
    ),
    (
        "a database can render a statement it was given and still differ in a property the "
        "statement does not mention, which is why the server-side SHOW CREATE comparison is "
        "reported alongside the file comparison rather than instead of it"
    ),
)

DEMO_CAVEATS = (
    (
        "this is ONE row against the one clause_version that already existed; it proves the "
        "production sidecar accepts a Bedrock vector under its FK and CHECK constraints, and "
        "it proves nothing about loading a corpus through clause_version's three triggers"
    ),
    (
        "clause_embedding carries no triggers on this cluster today, so site_id and "
        "activity_root were client-supplied — as migration 0031's own header says they are "
        "until band 0130-0199 lands"
    ),
    "the clause text is SYNTHETIC: it describes no real incident",
)

LOAD_CAVEATS = (
    (
        "the corpus is SYNTHETIC — trappoint_recall.corpora.synthetic — and every count "
        "here describes fabricated documents"
    ),
    (
        "mainline_ann_evidence's parent table is a two-column stub; see "
        "verticals/mainline/db/evidence/README.md for exactly what that costs"
    ),
    (
        "row counts are read back from the server after the load, but a count is not a recall "
        "measurement: nothing here says the ANN index returns the right neighbours"
    ),
)

RETRY_CAVEATS = (
    (
        "an induced conflict proves the loop recovers from a serialization failure; it does "
        "not predict how often Cloud produces one under real load"
    ),
    (
        "the local single-node cluster also produces 40001 for a deliberate write-after-read "
        "conflict, so this probe is not by itself evidence of anything Cloud-specific"
    ),
)


def prefix_diverse(docs: Sequence[Doc], cap: int) -> list[Doc]:
    """At most *cap* documents, round-robin across ``(site_id, activity_root)``.

    A cap that took the first *n* documents in corpus order would take *n* Part-50 lines from
    one mine and prove nothing about prefix-constrained search, because C-SPANN builds a
    partition tree per prefix value and one tree is not an ANN result.  This keeps one
    document from every prefix pair before it keeps a second from any, so a cap shrinks the
    depth of the corpus and never its width.
    """
    buckets: dict[tuple[str, str], list[Doc]] = {}
    for doc in docs:
        buckets.setdefault((doc.site_id, doc.activity_root), []).append(doc)
    kept: list[Doc] = []
    round_index = 0
    while len(kept) < cap and any(len(rows) > round_index for rows in buckets.values()):
        for rows in buckets.values():
            if round_index < len(rows) and len(kept) < cap:
                kept.append(rows[round_index])
        round_index += 1
    return kept


def gather_vectors(
    args: argparse.Namespace,
) -> tuple[list[Doc], dict[str, list[float]], dict[str, Any], list[dict[str, Any]]]:
    """The corpus, its vectors, where they came from, and what they cost."""
    docs = load_corpus()
    if args.limit:
        docs = docs[: args.limit]
    manifest_vectors, manifest_report = read_manifest()

    by_key: dict[str, list[float]] = {}
    unmatched: list[Doc] = []
    for doc in docs:
        vector = manifest_vectors.get(sha256_hex(doc.text.encode("utf-8")))
        if vector is None:
            unmatched.append(doc)
        else:
            by_key[doc.doc_key] = vector

    # THE CAP.  Bedrock's on-demand quota in this region is shared with the sibling worker
    # that produces the manifest, and both throttle each other; embedding the whole corpus a
    # second time here would slow that worker down to buy vectors it is already buying.  So
    # everything the manifest covers is loaded unconditionally, and what this program embeds
    # ITSELF is capped — width-first, so the cap costs corpus depth and never a prefix tree.
    dropped: list[Doc] = []
    if args.max_self_embed and len(unmatched) > args.max_self_embed:
        keep = set(prefix_diverse(unmatched, args.max_self_embed))
        dropped = [d for d in unmatched if d not in keep]
        unmatched = [d for d in unmatched if d in keep]
        dropped_keys = {d.doc_key for d in dropped}
        docs = [d for d in docs if d.doc_key not in dropped_keys]

    embed_report: dict[str, Any] = {"skipped": True}
    if unmatched:
        vectors, embed_report = embed_documents(unmatched, workers=args.workers)
        by_key.update(vectors)

    # A document with no vector cannot be loaded, and a loader that carried it to the INSERT
    # would fail the whole batch for one throttled call.  Dropped here, counted below.
    unembedded = [d.doc_key for d in docs if d.doc_key not in by_key]
    if unembedded:
        docs = [d for d in docs if d.doc_key in by_key]
        unmatched = [d for d in unmatched if d.doc_key in by_key]

    if not unmatched:
        mode = "manifest"
    elif manifest_vectors:
        mode = "mixed"
    else:
        mode = "corpus"
    source = {
        "mode": mode,
        "manifest": manifest_report,
        "embedding": embed_report,
        "documents": len(docs),
        "documents_from_manifest": len(docs) - len(unmatched),
        "documents_embedded_here": len(unmatched),
        "self_embed_cap": args.max_self_embed,
        "documents_dropped_by_cap": len(dropped),
        "documents_dropped_unembedded": unembedded,
        "documents_dropped_unembedded_count": len(unembedded),
        "cap_note": (
            "documents the manifest already covers are never dropped; the cap applies only to "
            "what this program would have had to embed itself, and it selects width-first "
            "across (site_id, activity_root) so every prefix pair survives it"
        ),
        "corpus": "trappoint_recall.corpora.synthetic.generate() — SYNTHETIC, fabricated",
        "streams": sorted({d.stream for d in docs}),
        "distinct_prefix_pairs_offered": len({(d.site_id, d.activity_root) for d in docs}),
    }

    ledger = [
        token_ledger_entry(
            TITAN_MODEL_ID,
            int(embed_report.get("bedrock_calls", 0) or 0),
            int(embed_report.get("input_tokens", 0) or 0),
            0,
        )
    ]
    if embed_report.get("cache_hits"):
        # Calls this program really made against Bedrock, in an earlier run of itself, whose
        # vectors are being loaded now.  Its own row, so that a re-run cannot report a corpus
        # load that appears to have cost nothing.
        ledger.append(
            token_ledger_entry(
                TITAN_MODEL_ID,
                int(embed_report["cache_hits"]),
                int(embed_report.get("cache_hit_input_tokens", 0) or 0),
                0,
            )
        )
    return docs, by_key, source, ledger


def write_demo_row(
    args: argparse.Namespace,
    docs: Sequence[Doc],
    by_key: dict[str, list[float]],
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """Load A: one Bedrock vector into the production sidecar, and its artefact."""
    if args.skip_production:
        demo: dict[str, Any] = {"skipped": True, "reason": "--skip-production"}
    else:
        digest_keyed = {
            sha256_hex(d.text.encode("utf-8")): by_key[d.doc_key]
            for d in docs
            if d.doc_key in by_key
        }
        demo = production_row(digest_keyed)
        if demo.get("input_tokens"):
            ledger.append(token_ledger_entry(TITAN_MODEL_ID, 1, int(demo["input_tokens"]), 0))
    artefact(
        EVIDENCE_DIR / "demo-row.json",
        demo,
        kind="production-clause-embedding-row",
        caveats=DEMO_CAVEATS,
        synthetic=True,
    )
    return demo


def run_targets(
    args: argparse.Namespace, docs: Sequence[Doc], by_key: dict[str, list[float]]
) -> dict[str, Any]:
    """Load B against every cluster that answers.  Cloud is required; local never is."""
    targets: dict[str, Any] = {
        "cloud": load_target("cloud", None, docs, by_key, batch_size=args.batch_size)
    }
    if args.skip_local:
        targets["local"] = {
            "target": "local",
            "available": False,
            "status": "skipped by --skip-local",
        }
    else:
        targets["local"] = load_target("local", LOCAL_DSN, docs, by_key, batch_size=args.batch_size)
    return targets


def write_load_artefact(
    docs: Sequence[Doc],
    source: dict[str, Any],
    targets: dict[str, Any],
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """``cloud-load.json``.  Returns the banned-construct scan so main can gate on it."""
    issued: list[str] = []
    for target in targets.values():
        issued.extend(target.get("ddl_statements_issued", []))
    issued.extend([_INSERT_PARENT, _INSERT_EMBEDDING])
    banned = scan_banned([*issued, "\n".join(_read_lines(SCHEMA_SQL))])

    total_bytes = sum(
        int((t.get("load") or {}).get("vector_literal_bytes", 0)) for t in targets.values()
    )
    artefact(
        EVIDENCE_DIR / "cloud-load.json",
        {
            "source": source,
            "targets": targets,
            "token_ledger": ledger,
            "token_ledger_total": ledger_total(ledger),
            "token_ledger_note": (
                "row 1 is InvokeModel in this process; row 2, when present, is the calls this "
                "same program made in an earlier run whose vectors came from its cache under "
                "out/ (gitignored). Every count is Bedrock's own `inputTextTokenCount`, never "
                "an estimate from character length."
            ),
            "bytes": {
                "vector_literal_bytes_sent": total_bytes,
                "float32_equivalent_bytes": len(docs) * EXPECTED_DIM * 4,
                "note": (
                    "the wire form is a decimal text literal at %.8g; the column stores "
                    "float32, so the second number is what the vectors weigh once landed"
                ),
            },
            "banned_identity_constructs": banned,
        },
        kind="cockroachdb-vector-load",
        caveats=LOAD_CAVEATS,
        synthetic=True,
    )
    return banned


def write_retry_artefact(targets: dict[str, Any]) -> None:
    """``retry-40001.json`` — what the loop did, and what it merely was."""
    observed = {
        name: {
            "batches": (t.get("load") or {}).get("batches", 0),
            "retries_40001": (t.get("load") or {}).get("retries_40001", 0),
        }
        for name, t in targets.items()
        if t.get("available")
    }
    probes = {name: t["retry_probe"] for name, t in targets.items() if "retry_probe" in t}
    natural_total = sum(v["retries_40001"] for v in observed.values())
    batches = sum(v["batches"] for v in observed.values())
    artefact(
        EVIDENCE_DIR / "retry-40001.json",
        {
            "loop": {
                "implementation": "scripts/aws/_common.py::with_retry",
                "attempts": 8,
                "retryable_sqlstate": "40001",
                "backoff": (
                    "full jitter over a linearly growing window: "
                    "sleep(min(2.0, 0.05 * retry) * (0.5 + random()))"
                ),
                "backoff_schedule_seconds": [
                    {
                        "retry": n,
                        "window": round(min(2.0, 0.05 * n), 4),
                        "sleep_range": [
                            round(min(2.0, 0.05 * n) * 0.5, 4),
                            round(min(2.0, 0.05 * n) * 1.5, 4),
                        ],
                    }
                    for n in range(1, 8)
                ],
                "non_retryable": (
                    "every other SQLSTATE is re-raised unchanged; a gate refusal (23514, "
                    "P0001) is a result in this system and retrying it would be a way of "
                    "asking the same forbidden question eight times"
                ),
            },
            "observed_during_load": observed,
            "observed_total": natural_total,
            "induced_probes": probes,
            "honest_note": (
                "the bulk load wrote disjoint primary keys, one transaction per batch, and "
                f"observed {natural_total} serialization failure(s) across {batches} "
                "batch(es). A zero there is the expected result of an uncontended load, and "
                "on its own it is indistinguishable from a loop that does not work — which "
                "is why the induced probe exists and is reported separately. The two numbers "
                "are never added: one measures the workload, the other measures the loop."
            ),
        },
        kind="retry-40001-evidence",
        caveats=RETRY_CAVEATS,
        synthetic=False,
    )


def print_summary(
    targets: dict[str, Any],
    demo: dict[str, Any],
    banned: dict[str, Any],
    source: dict[str, Any],
) -> None:
    """One line per target, one for the production row, one for the identity scan."""
    print(
        f"source {source['mode']}: {source['documents']} documents "
        f"({source['documents_from_manifest']} from the manifest, "
        f"{source['documents_embedded_here']} embedded here, "
        f"{source['documents_dropped_by_cap']} capped, "
        f"{source['documents_dropped_unembedded_count']} dropped unembedded)"
    )
    for name, target in targets.items():
        if not target.get("available"):
            print(f"{name:6s} unavailable: {target.get('error_type', target.get('status'))}")
            continue
        survey = target.get("survey")
        if survey is None:
            print(f"{name:6s} failed: {target.get('error_type')}: {target.get('error')}")
            continue
        print(
            f"{name:6s} {survey['clause_embedding_rows']} rows, "
            f"{survey['distinct_prefix_pairs']} prefix pairs, "
            f"{target['load']['retries_40001']} load retries, "
            f"{target['retry_probe']['retries_40001']} induced, {target['elapsed_s']}s"
        )
    if not demo.get("skipped"):
        print(
            f"demo   {PRODUCTION_DB}.mainline.clause_embedding "
            f"{demo.get('count_before')} -> {demo.get('count_after')} "
            f"({demo.get('stored_row', {}).get('embed_model')})"
        )
    print(f"banned identity constructs: {'clean' if banned['clean'] else banned['hits']}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the fidelity check, then both loads, then write the four artefacts."""
    args = _parse_args(argv)

    fidelity = check_schema_fidelity()
    for finding in fidelity["findings"]:
        print(f"FIDELITY FAILED: {finding}", file=sys.stderr)
    if fidelity["ok"]:
        print(
            f"fidelity OK: {len(fidelity['verbatim'])} verbatim range(s), "
            f"{fidelity['diff_line_count']} differing line(s)"
        )

    # ``--fidelity-only`` DELIBERATELY WRITES NOTHING.  The README tells a reviewer to run it
    # first, and a check that destroyed the artefact it was checking — replacing a full run's
    # server-side comparison with "not attempted" — would punish exactly the person who did
    # the right thing.  It prints, it sets an exit code, and it leaves the evidence alone.
    if args.fidelity_only:
        return 0 if fidelity["ok"] else 1

    fidelity["server_side"] = {
        "status": "not reached: the run stopped before the databases existed"
    }
    artefact(
        EVIDENCE_DIR / "schema-fidelity.json",
        fidelity,
        kind="ann-evidence-schema-fidelity",
        caveats=FIDELITY_CAVEATS,
        synthetic=False,
    )
    if not fidelity["ok"]:
        return 1

    docs, by_key, source, ledger = gather_vectors(args)
    demo = write_demo_row(args, docs, by_key, ledger)
    targets = run_targets(args, docs, by_key)

    # The server's own rendering, now that both databases exist.  This rewrites
    # schema-fidelity.json in place; the earlier write is insurance against a crash between
    # there and here, not a second artefact.
    fidelity["server_side"] = compare_show_create(
        demo.get("show_create"),
        {
            f"{name}:{EVIDENCE_DB}": target["survey"]["show_create"]
            for name, target in targets.items()
            if target.get("survey", {}).get("show_create")
        },
    )
    artefact(
        EVIDENCE_DIR / "schema-fidelity.json",
        fidelity,
        kind="ann-evidence-schema-fidelity",
        caveats=FIDELITY_CAVEATS,
        synthetic=False,
    )

    banned = write_load_artefact(docs, source, targets, ledger)
    write_retry_artefact(targets)
    print_summary(targets, demo, banned, source)

    cloud = targets["cloud"]
    ok = (
        banned["clean"]
        and bool(cloud.get("available"))
        and cloud.get("survey", {}).get("clause_embedding_rows") == len(docs)
        and cloud.get("survey", {}).get("distinct_prefix_pairs", 0) >= 8
        and (args.skip_production or demo.get("count_after") == 1)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
