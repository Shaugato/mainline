#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Assert that a CockroachDB query plan really uses a prefix-constrained vector index.

Standalone and dependency-light: the parser and the assertion are pure standard library, so
this runs anywhere Python 3.10+ runs. ``psycopg`` is needed only for ``--dsn``, and its
absence is reported rather than assumed.

    # From plan text you already have
    cockroach sql --execute "EXPLAIN SELECT ..." --format=raw \
      | python assert_prefix_index_used.py --index items@items_customer_id_embedding_idx

    # Straight from a cluster
    python assert_prefix_index_used.py --dsn "$DSN" \
      --index items@items_customer_id_embedding_idx \
      --statement "SELECT id FROM items WHERE customer_id = 1
                   ORDER BY embedding <-> '[1,2,3]' LIMIT 10"

    # Prove the assertion itself works before trusting it
    python assert_prefix_index_used.py --self-test

Exit status: 0 the plan uses the index as asserted · 1 it does not · 2 the arguments or the
environment were wrong.

FOUR THINGS ARE CHECKED, AND THE FOURTH IS THE ONE PEOPLE FORGET:

1. a ``vector search`` node exists;
2. it reads the expected ``table@index``;
3. its ``prefix spans`` line is present and **non-empty** — a vector index is used only if
   every prefix column is constrained to a specific value;
4. **no node anywhere in the plan is a full scan.** A plan can contain a perfectly good vector
   search *and* read the whole table beside it, when a predicate could not be pushed into the
   prefix. An assertion that stops at "is the phrase 'vector search' present" passes that plan.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field

VECTOR_SEARCH_NODE = "vector search"
FULL_SCAN_MARKER = "FULL SCAN"
_GLYPHS = "│├└─┌┐┘┴┬┼|`+-"
_BULLET = "•"
_FIELD = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9 _\-]*?)\s*:\s*(?P<value>.*)$")
_EMPTY_SPANS = frozenset({"", "[]", "-", "none", "<empty>"})


@dataclass
class Node:
    node_type: str
    depth: int
    fields: dict = field(default_factory=dict)

    @property
    def table(self):
        return self.fields.get("table")

    @property
    def prefix_spans(self):
        return self.fields.get("prefix spans")

    @property
    def target_count(self):
        raw = self.fields.get("target count")
        if raw is None:
            return None
        try:
            return int(raw.strip())
        except ValueError:
            return None

    @property
    def is_full_scan(self) -> bool:
        return any(FULL_SCAN_MARKER in str(v).upper() for v in self.fields.values())


def parse_plan(text: str) -> list:
    """Parse EXPLAIN output into nodes. Handles the flat and the glyph-tree renderings."""
    raw: list = []
    current = None
    for line in text.splitlines():
        if not line.strip():
            continue
        bullet = line.find(_BULLET)
        if bullet != -1:
            current = {}
            raw.append((line[bullet + 1 :].strip(), bullet, current))
            continue
        stripped = line.strip().lstrip(_GLYPHS).strip()
        match = _FIELD.match(stripped) if stripped else None
        if match is None or current is None:
            continue
        key = match.group("key").strip().lower()
        if key not in current:
            current[key] = match.group("value").strip()
    columns = sorted({column for _, column, _ in raw})
    depth_of = {column: i for i, column in enumerate(columns)}
    return [Node(t, depth_of[c], f) for t, c, f in raw]


def assert_index_used(
    nodes: list, *, expected_index: str, expected_target_count=None, require_exact_target=False
) -> dict:
    """Return a structured verdict. Every component is reported, not just the conjunction."""
    failures = []
    searches = [n for n in nodes if n.node_type == VECTOR_SEARCH_NODE]
    if not searches:
        failures.append(
            "no `vector search` node: the optimizer did not use a vector index. Node types "
            f"present: {sorted({n.node_type for n in nodes})}"
        )
    node = searches[0] if searches else None
    observed = node.table if node else None
    if node is not None and observed != expected_index:
        failures.append(f"vector search reads {observed!r}, expected {expected_index!r}")
    spans = node.prefix_spans if node else None
    spans_ok = spans is not None and spans.strip().lower() not in _EMPTY_SPANS
    if node is not None and not spans_ok:
        failures.append(
            f"prefix spans are {spans!r}: at least one prefix column was NOT constrained to a "
            "specific value, so this query is not searching the partition it looks like it is"
        )
    target = node.target_count if node else None
    if node is not None and target is None:
        failures.append("the vector search node prints no `target count:` line")
    if (
        node is not None
        and require_exact_target
        and expected_target_count is not None
        and target != expected_target_count
    ):
        failures.append(f"target count is {target}, expected {expected_target_count}")
    scans = [n for n in nodes if n.is_full_scan]
    if scans:
        failures.append(
            "the plan contains a FULL SCAN (" + ", ".join(n.node_type for n in scans) + ")"
        )
    return {
        "ok": not failures,
        "expected_index": expected_index,
        "observed_index": observed,
        "vector_search_nodes": len(searches),
        "target_count": target,
        "prefix_spans": spans,
        "prefix_spans_nonempty": spans_ok,
        "full_scan": bool(scans),
        "failures": failures,
    }


# ── self-test fixtures ───────────────────────────────────────────────────────────────────

_GOOD = """  distribution: local
  vectorized: true

  • vector search
    table: items@items_customer_id_embedding_idx
    target count: 10
    prefix spans: [/1 - /1]
"""

_NO_INDEX = """  • top-k
  │ order: +dist
  │
  └── • scan
        estimated row count: 100,000 (100% of the table)
        table: items@items_pkey
        spans: FULL SCAN
"""

_UNCONSTRAINED = """  • vector search
    table: items@items_customer_id_embedding_idx
    target count: 10
    prefix spans: []
"""

_SCAN_BESIDE_IT = """  • hash join
  │
  ├── • vector search
  │     table: items@items_customer_id_embedding_idx
  │     target count: 10
  │     prefix spans: [/1 - /1]
  │
  └── • scan
        table: item_meta@item_meta_pkey
        spans: FULL SCAN
"""

_INDEX = "items@items_customer_id_embedding_idx"


def self_test() -> int:
    """Prove the assertion can fail before trusting it to pass.

    An assertion that has never been red asserts nothing. Each negative fixture must fail for
    its own distinct reason, which is checked here rather than asserted in a comment.
    """
    cases = [
        ("constrained vector search", _GOOD, True, None),
        ("no vector search at all", _NO_INDEX, False, "no `vector search` node"),
        ("prefix not constrained", _UNCONSTRAINED, False, "prefix spans"),
        ("full scan beside a real vector search", _SCAN_BESIDE_IT, False, "FULL SCAN"),
    ]
    failed = 0
    for name, text, expect_ok, expect_reason in cases:
        verdict = assert_index_used(parse_plan(text), expected_index=_INDEX)
        ok = verdict["ok"] == expect_ok
        if ok and expect_reason is not None:
            ok = any(expect_reason in f for f in verdict["failures"])
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{status}] {name}: {verdict['failures'] or 'accepted'}")
    print("\nself-test:", "OK" if not failed else f"{failed} case(s) wrong")
    return 0 if not failed else 1


# ── entry point ──────────────────────────────────────────────────────────────────────────


def _plan_from_cluster(dsn: str, statement: str) -> str:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError:
        print(
            "--dsn needs psycopg 3 (`pip install 'psycopg[binary]'`). Without it, pipe the "
            "output of `cockroach sql --execute 'EXPLAIN ...' --format=raw` into this script "
            "instead — the parser and the assertion need nothing but the standard library.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    body = statement.strip().rstrip(";")
    if not body.upper().startswith("EXPLAIN"):
        body = "EXPLAIN " + body
    if "ANALYZE" in body.upper():
        print(
            "refusing to run EXPLAIN ANALYZE: this asserts which plan was CHOSEN, which the "
            "non-analyzing form answers without executing the query.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(body).fetchall()
    return "\n".join(" ".join(str(cell) for cell in row) for row in rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Assert a CockroachDB plan uses a prefix-constrained vector index.",
        epilog="Reads EXPLAIN output from stdin unless --plan-file or --dsn is given.",
    )
    parser.add_argument("--index", help="expected `table@index`, exactly as EXPLAIN prints it")
    parser.add_argument("--plan-file", help="file holding EXPLAIN output")
    parser.add_argument("--dsn", help="connect and EXPLAIN --statement yourself (needs psycopg)")
    parser.add_argument("--statement", help="the query to EXPLAIN when --dsn is used")
    parser.add_argument("--statement-file", help="read --statement from a file")
    parser.add_argument("--expect-target-count", type=int, default=None)
    parser.add_argument(
        "--require-exact-target-count",
        action="store_true",
        help="fail when `target count` differs from --expect-target-count. Off by default: "
        "the documented examples show it equal to the query's LIMIT, but whether it is ever "
        "inflated for re-ranking is not documented, so it is reported rather than required.",
    )
    parser.add_argument("--json", action="store_true", help="print the verdict as JSON")
    parser.add_argument("--self-test", action="store_true", help="run the built-in fixtures")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.index:
        parser.error("--index is required (or use --self-test)")

    if args.dsn:
        statement = args.statement
        if args.statement_file:
            with open(args.statement_file, encoding="utf-8") as handle:
                statement = handle.read()
        if not statement:
            parser.error("--dsn requires --statement or --statement-file")
        text = _plan_from_cluster(args.dsn, statement)
    elif args.plan_file:
        with open(args.plan_file, encoding="utf-8") as handle:
            text = handle.read()
    else:
        # Decode stdin as UTF-8 explicitly. EXPLAIN draws its plan with `•` and `└──`, and on
        # a machine whose locale encoding is not UTF-8 the default stdin decoding turns every
        # node marker into mojibake — which parses as a plan with zero nodes and reports
        # "the index was not used" for entirely the wrong reason.
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")

    if not text.strip():
        print("no plan text to read", file=sys.stderr)
        return 2

    nodes = parse_plan(text)
    if not nodes:
        print(
            "no plan nodes were found in the input. EXPLAIN output marks each node with a "
            "'•' bullet; this input has none, so it is probably not EXPLAIN output (or it "
            "lost its encoding on the way here). Refusing to report 'the index was not used' "
            "on the strength of an unreadable plan.",
            file=sys.stderr,
        )
        return 2

    verdict = assert_index_used(
        nodes,
        expected_index=args.index,
        expected_target_count=args.expect_target_count,
        require_exact_target=args.require_exact_target_count,
    )
    if args.json:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    elif verdict["ok"]:
        print(
            f"OK  vector search on {verdict['observed_index']}, "
            f"target count {verdict['target_count']}, prefix spans {verdict['prefix_spans']}"
        )
    else:
        print("FAIL")
        for failure in verdict["failures"]:
            print(f"  - {failure}")
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
