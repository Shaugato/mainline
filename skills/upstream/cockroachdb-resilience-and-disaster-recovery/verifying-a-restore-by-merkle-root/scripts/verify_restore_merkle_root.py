#!/usr/bin/env python3
"""Verify that a restored table reproduces a Merkle root committed before the backup.

Two phases, one script.

    # BEFORE the backup: commit to the table's contents, and store this outside the cluster
    cockroach sql --url "$DSN" --format=tsv \
      --execute "SELECT id, ts, payload FROM audit_log ORDER BY id" \
      | python verify_restore_merkle_root.py --emit-checkpoint --tsv - > checkpoint.json

    # AFTER the restore: recompute and require root, height and head to match
    cockroach sql --url "$DSN" --format=tsv \
      --execute "SELECT id, ts, payload FROM audit_log ORDER BY id" \
      | python verify_restore_merkle_root.py --checkpoint checkpoint.json --tsv -

    # prove the checker can fail, with no database and no network
    python verify_restore_merkle_root.py --self-test

Exit status: 0 verified, 1 the restore does not reproduce the checkpoint, 2 the arguments or
the input were unusable (never reported as a successful verification).

Standard library only.

WHY HEIGHT AND HEAD ARE CHECKED SEPARATELY. A hash chain verified only forward -- walking
prev_hash links from the first row -- proves every surviving link is intact and proves
nothing at all about rows missing from the END. Every check passes; the table is short.
`chain_links_intact` below implements that insufficient check on purpose, and the self-test
uses it to demonstrate the trap rather than assert it in a comment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"
EMPTY_PREFIX = b"\x02"
FIELD_SEPARATOR = b"\x1f"
DEFAULT_SEGMENT = 1024
NULL_SENTINEL = b"\x00NULL"


def _say(text: str = "") -> None:
    """Write one line to stdout through a single funnel."""
    sys.stdout.write(text + "\n")


class InputProblem(RuntimeError):
    """The input could not be read or understood — exit 2, never exit 0."""


# ── hashing ──────────────────────────────────────────────────────────────────────────────


def canonical_row(fields: list[Any]) -> bytes:
    """Encode one row as bytes whose field boundaries are recoverable.

    Each field is length-prefixed and separated, so ``("ab", "c")`` and ``("a", "bc")``
    cannot produce the same encoding. ``None`` gets a sentinel distinct from the empty
    string: a NULL and an empty string are different facts and must not hash alike.
    """
    parts: list[bytes] = []
    for field in fields:
        raw = NULL_SENTINEL if field is None else str(field).encode("utf-8")
        parts.append(str(len(raw)).encode("ascii") + b":" + raw)
    return FIELD_SEPARATOR.join(parts)


def leaf_hash(payload: bytes) -> bytes:
    """Hash a leaf with its domain-separation prefix."""
    return hashlib.sha256(LEAF_PREFIX + payload).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """Hash an internal node with its domain-separation prefix."""
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    """Fold leaf hashes into a root, promoting an odd node rather than duplicating it.

    Duplicating the last node of an odd level lets two different leaf sets produce the
    same root, which turns a passing verification into a statement about nothing.
    """
    if not leaves:
        return hashlib.sha256(EMPTY_PREFIX).digest()
    level = list(leaves)
    while len(level) > 1:
        nxt: list[bytes] = []
        for index in range(0, len(level) - 1, 2):
            nxt.append(node_hash(level[index], level[index + 1]))
        if len(level) % 2 == 1:
            nxt.append(level[-1])
        level = nxt
    return level[0]


def chain_links_intact(rows: list[tuple[bytes, bytes]]) -> bool:
    """Walk (prev_hash, row_hash) pairs forward and report whether every link holds.

    **This check is deliberately insufficient and is exported so that fact is visible.**
    It cannot see rows missing from the end of the table: every remaining link is valid,
    nothing is inconsistent, and the data is gone. Bind the height and the head hash.
    """
    previous = b"\x00" * 32
    for prev_hash, row_hash in rows:
        if prev_hash != previous:
            return False
        previous = row_hash
    return True


# ── the checkpoint ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Checkpoint:
    """The triple committed before the backup, plus optional localisation data."""

    root: str
    height: int
    head: str
    segment_size: int
    segment_roots: list[str]
    label: str

    def to_json(self) -> str:
        """Render the checkpoint for storage outside the cluster."""
        return json.dumps(
            {
                "algorithm": "sha256-merkle-v1",
                "leaf_prefix": "0x00",
                "node_prefix": "0x01",
                "odd_node": "promoted",
                "root": self.root,
                "height": self.height,
                "head": self.head,
                "segment_size": self.segment_size,
                "segment_roots": self.segment_roots,
                "label": self.label,
            },
            indent=2,
            sort_keys=True,
        )

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> Checkpoint:
        """Load a checkpoint, refusing one that is missing any of the three bindings."""
        missing = [key for key in ("root", "height", "head") if key not in data]
        if missing:
            raise InputProblem(
                "the checkpoint is missing " + ", ".join(missing) + ". A checkpoint carrying "
                "only a root cannot detect truncation once anybody replaces the tree rebuild "
                "with a forward chain walk, which is why all three are required here."
            )
        return Checkpoint(
            root=str(data["root"]),
            height=int(data["height"]),
            head=str(data["head"]),
            segment_size=int(data.get("segment_size", DEFAULT_SEGMENT)),
            segment_roots=[str(item) for item in data.get("segment_roots", [])],
            label=str(data.get("label", "")),
        )


def build_checkpoint(leaves: list[bytes], *, segment: int, label: str) -> Checkpoint:
    """Compute the committed triple, plus one root per segment so a mismatch can be located."""
    segment_roots = [
        merkle_root(leaves[start : start + segment]).hex()
        for start in range(0, len(leaves), segment)
    ]
    return Checkpoint(
        root=merkle_root(leaves).hex(),
        height=len(leaves),
        head=leaves[-1].hex() if leaves else "",
        segment_size=segment,
        segment_roots=segment_roots,
        label=label,
    )


@dataclass(frozen=True)
class Report:
    """The outcome of comparing recomputed leaves against a checkpoint."""

    ok: bool
    lines: list[str]


def verify(leaves: list[bytes], checkpoint: Checkpoint) -> Report:
    """Compare root, height and head, and localise a mismatch when the checkpoint allows it."""
    observed_root = merkle_root(leaves).hex()
    observed_head = leaves[-1].hex() if leaves else ""
    lines: list[str] = []
    ok = True

    if observed_root == checkpoint.root:
        lines.append(f"root    OK  {observed_root}")
    else:
        ok = False
        lines.append(f"root    MISMATCH expected {checkpoint.root} observed {observed_root}")

    if len(leaves) == checkpoint.height:
        lines.append(f"height  OK  {len(leaves)}")
    else:
        ok = False
        delta = checkpoint.height - len(leaves)
        shape = f"{delta} row(s) short" if delta > 0 else f"{-delta} row(s) extra"
        lines.append(
            f"height  MISMATCH expected {checkpoint.height} observed {len(leaves)} ({shape})"
        )

    if observed_head == checkpoint.head:
        lines.append(f"head    OK  {observed_head or '<empty table>'}")
    else:
        ok = False
        lines.append(f"head    MISMATCH expected {checkpoint.head} observed {observed_head}")

    if not ok:
        lines.extend(_localise(leaves, checkpoint))
    return Report(ok, lines)


def _localise(leaves: list[bytes], checkpoint: Checkpoint) -> list[str]:
    if not checkpoint.segment_roots:
        return [
            (
                "        the checkpoint carries no segment roots, so the first divergence "
                "cannot be located. Emit checkpoints with --segment so the next drill can "
                "answer 'which rows', not only 'different'."
            )
        ]
    size = checkpoint.segment_size
    for index, expected in enumerate(checkpoint.segment_roots):
        window = leaves[index * size : (index + 1) * size]
        observed = merkle_root(window).hex()
        if observed != expected:
            first = index * size
            where = (
                f"rows {first}.. are ABSENT"
                if not window
                else f"rows {first}..{first + len(window) - 1}"
            )
            return [
                f"        first divergent segment {index}: {where}",
                f"        expected {expected}",
                f"        observed {observed}",
                (
                    "        a tail-only difference means truncation; a difference at segment "
                    "0 with matching height usually means the encoding differs, not the data"
                ),
            ]
    return [
        (
            f"        every segment root matches but the table is {len(leaves)} rows long "
            f"against {checkpoint.height} committed: rows are missing from the END, past the "
            "last segment boundary. This is the case a forward chain walk cannot see."
        )
    ]


# ── input ────────────────────────────────────────────────────────────────────────────────


def _open(path: str) -> Any:
    if path == "-":
        return sys.stdin
    return Path(path).open(encoding="utf-8")


def read_tsv(path: str, *, header: bool, leaf_column: int | None) -> list[bytes]:
    """Read tab-separated rows and return one leaf hash per row."""
    leaves: list[bytes] = []
    handle = _open(path)
    try:
        for number, line in enumerate(handle):
            text = line.rstrip("\n").rstrip("\r")
            if header and number == 0:
                continue
            if not text:
                continue
            fields: list[Any] = [None if cell == "NULL" else cell for cell in text.split("\t")]
            leaves.append(_leaf_from(fields, leaf_column, number))
    finally:
        if handle is not sys.stdin:
            handle.close()
    return leaves


def read_jsonl(path: str, *, leaf_column: int | None) -> list[bytes]:
    """Read one JSON array per line and return one leaf hash per row.

    Preferred over TSV whenever a value may contain a tab or a newline, because TSV cannot
    represent those unambiguously and a verifier that guesses is a verifier that lies.
    """
    leaves: list[bytes] = []
    handle = _open(path)
    try:
        for number, line in enumerate(handle):
            text = line.strip()
            if not text:
                continue
            try:
                fields = json.loads(text)
            except json.JSONDecodeError as exc:
                raise InputProblem(f"line {number + 1} is not JSON: {exc}") from exc
            if not isinstance(fields, list):
                raise InputProblem(f"line {number + 1} is not a JSON array of column values")
            leaves.append(_leaf_from(fields, leaf_column, number))
    finally:
        if handle is not sys.stdin:
            handle.close()
    return leaves


def _leaf_from(fields: list[Any], leaf_column: int | None, number: int) -> bytes:
    if leaf_column is None:
        return leaf_hash(canonical_row(fields))
    if leaf_column >= len(fields):
        raise InputProblem(
            f"line {number + 1} has {len(fields)} column(s); --leaf-column {leaf_column} "
            "is out of range"
        )
    raw = str(fields[leaf_column]).strip().removeprefix("\\x").removeprefix("0x")
    try:
        digest = bytes.fromhex(raw)
    except ValueError as exc:
        raise InputProblem(
            f"line {number + 1}: --leaf-column names a column whose value is not hex. When "
            "the table already stores a per-row digest, select THAT column; otherwise drop "
            "--leaf-column and let this script canonicalise the row."
        ) from exc
    return digest


# ── self-test ────────────────────────────────────────────────────────────────────────────


def self_test() -> int:
    """Prove the checker detects truncation, tampering and reordering, with no database.

    The first case is the important one: it shows a forward chain walk accepting a table
    whose tail is gone, and this verifier refusing the same table.
    """
    rows = [[index, f"payload-{index}", None if index % 7 == 0 else "note"] for index in range(50)]
    leaves = [leaf_hash(canonical_row(row)) for row in rows]
    checkpoint = Checkpoint.from_mapping(
        json.loads(build_checkpoint(leaves, segment=8, label="self-test").to_json())
    )

    cases: list[tuple[str, list[bytes], bool]] = [
        ("an identical table verifies", list(leaves), True),
        ("18 rows missing from the END are caught", leaves[:32], False),
        ("one row altered in the middle is caught", _tamper(leaves, 21), False),
        ("two rows swapped are caught", _swap(leaves, 5, 6), False),
        ("one extra row appended is caught", [*leaves, leaf_hash(b"extra")], False),
    ]

    failed = 0
    for name, candidate, expect_ok in cases:
        report = verify(candidate, checkpoint)
        ok = report.ok == expect_ok
        failed += 0 if ok else 1
        _say(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not expect_ok:
            for line in report.lines:
                if "MISMATCH" in line or "divergent" in line or "missing" in line:
                    _say(f"        {line.strip()}")

    # The trap, demonstrated rather than described.
    chain = _synthetic_chain(rows)
    truncated_walk = chain_links_intact(chain[:32])
    truncated_root = verify(leaves[:32], checkpoint).ok
    trap_ok = truncated_walk and not truncated_root
    failed += 0 if trap_ok else 1
    _say(
        f"[{'PASS' if trap_ok else 'FAIL'}] a forward chain walk ACCEPTS the truncated table "
        f"({truncated_walk}) while the root check REFUSES it ({truncated_root})"
    )

    # Canonicalisation must not be ambiguous across field boundaries.
    boundary_ok = canonical_row(["ab", "c"]) != canonical_row(["a", "bc"])
    null_ok = canonical_row([None]) != canonical_row([""])
    odd_ok = merkle_root([leaf_hash(b"a")]) != merkle_root([leaf_hash(b"a"), leaf_hash(b"a")])
    for label, condition in (
        ("field boundaries cannot be shifted without changing the encoding", boundary_ok),
        ("NULL does not hash as an empty string", null_ok),
        ("an odd node is promoted, not duplicated", odd_ok),
    ):
        failed += 0 if condition else 1
        _say(f"[{'PASS' if condition else 'FAIL'}] {label}")

    _say("")
    _say("self-test: " + ("OK" if failed == 0 else f"{failed} case(s) wrong"))
    return 0 if failed == 0 else 1


def _tamper(leaves: list[bytes], index: int) -> list[bytes]:
    altered = list(leaves)
    altered[index] = leaf_hash(b"tampered")
    return altered


def _swap(leaves: list[bytes], left: int, right: int) -> list[bytes]:
    swapped = list(leaves)
    swapped[left], swapped[right] = swapped[right], swapped[left]
    return swapped


def _synthetic_chain(rows: list[list[Any]]) -> list[tuple[bytes, bytes]]:
    chain: list[tuple[bytes, bytes]] = []
    previous = b"\x00" * 32
    for row in rows:
        digest = hashlib.sha256(previous + canonical_row(row)).digest()
        chain.append((previous, digest))
        previous = digest
    return chain


# ── entry point ──────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a restored table against a Merkle root committed before the backup.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--tsv", metavar="PATH", help="tab-separated rows, or - for stdin")
    source.add_argument("--jsonl", metavar="PATH", help="one JSON array per line, or - for stdin")
    parser.add_argument("--checkpoint", help="the checkpoint JSON to verify against")
    parser.add_argument(
        "--emit-checkpoint", action="store_true", help="print a checkpoint for these rows"
    )
    parser.add_argument("--label", default="", help="free text recorded in an emitted checkpoint")
    parser.add_argument(
        "--segment",
        type=int,
        default=DEFAULT_SEGMENT,
        help="rows per segment root, so a future mismatch can be located (default 1024)",
    )
    parser.add_argument(
        "--leaf-column",
        type=int,
        default=None,
        metavar="N",
        help="0-based column already holding a hex row digest; skips canonicalisation",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="the TSV input has no header line (cockroach sql --format=tsv emits one)",
    )
    parser.add_argument("--self-test", action="store_true", help="run the built-in fixtures")
    return parser


def _use_utf8_io() -> None:
    """Force UTF-8 on stdout and stderr, whatever the console's code page says.

    A checkpoint redirected to a file on a machine whose default encoding is not UTF-8
    comes back mangled, and a verifier that reads a mangled checkpoint reports a mismatch
    that has nothing to do with the restore.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, read rows, and either emit or verify a checkpoint."""
    _use_utf8_io()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.tsv and not args.jsonl:
        parser.error("one of --tsv or --jsonl is required (or use --self-test)")
    if not args.emit_checkpoint and not args.checkpoint:
        parser.error("--checkpoint is required unless --emit-checkpoint is given")

    try:
        if args.jsonl:
            leaves = read_jsonl(args.jsonl, leaf_column=args.leaf_column)
        else:
            leaves = read_tsv(args.tsv, header=not args.no_header, leaf_column=args.leaf_column)
        if args.emit_checkpoint:
            _say(build_checkpoint(leaves, segment=args.segment, label=args.label).to_json())
            return 0
        raw = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
        checkpoint = Checkpoint.from_mapping(raw)
    except InputProblem as problem:
        _say(f"INPUT: {problem}")
        return 2
    except OSError as problem:
        _say(f"INPUT: {problem}")
        return 2
    except json.JSONDecodeError as problem:
        _say(f"INPUT: the checkpoint is not valid JSON: {problem}")
        return 2

    report = verify(leaves, checkpoint)
    for line in report.lines:
        _say(line)
    _say("")
    _say(
        "VERIFIED" if report.ok else "NOT VERIFIED — the restore does not reproduce the checkpoint"
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
