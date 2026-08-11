# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Support for the index-truth suite: bindings, corpora, timing, and the two explain sources.

The MAINLINE vocabulary lives **here**, not in ``trappoint_recall.arms``. The substrate
package is Apache-2.0 and holds no table names, no facet names and no schema; this module
supplies them, which is also what proves the substrate is genuinely parameterised rather than
parameterised-in-principle.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from trappoint_recall.arms import ArmPolicy, VectorTable

# ── repository layout ────────────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent


def repo_root() -> Path:
    for parent in [HERE, *HERE.parents]:
        if (parent / "verticals" / "mainline" / "db" / "migrations").is_dir():
            return parent
    raise RuntimeError(f"cannot locate verticals/mainline/db/migrations above {HERE}")


ROOT = repo_root()
MIGRATIONS_DIR = ROOT / "verticals" / "mainline" / "db" / "migrations"

#: The recall band's reserved migration numbers, as ranges rather than as a copied list: the
#: DDL worker owns the exact membership, and a hard-coded copy here would drift the first time
#: they add a file. Ranges are the interface; the files found inside them are theirs.
RESERVED_RANGES: tuple[range, ...] = (
    range(40, 47),
    range(80, 89),
    range(112, 115),
    range(136, 140),
)

#: Without these five the suite is not testing anything: the cue entity, both vector sidecars,
#: the projection function and the trigger that fires it.
REQUIRED_MIGRATIONS: frozenset[int] = frozenset({40, 41, 42, 114, 138})

#: Owned by `recall-ddl-triggers`. Read, never written, so that the two suites cannot disagree
#: about what the consumed tables look like.
PREREQ_CONSUMED = (
    ROOT / "tests" / "integration" / "recall_schema" / "prereq" / "00_consumed_tables.sql"
)

FIXTURES = HERE / "fixtures"
ARTEFACTS = HERE / "artefacts"


def recall_migration_files() -> list[Path]:
    reserved = {n for r in RESERVED_RANGES for n in r}
    found: dict[int, Path] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        head = path.name.split("_", 1)[0]
        if head.isdigit() and int(head) in reserved:
            found[int(head)] = path
    missing = sorted(REQUIRED_MIGRATIONS - set(found))
    if missing:
        raise RuntimeError(
            "the recall band is missing migrations this suite cannot run without: "
            + ", ".join(f"{n:04d}" for n in missing)
        )
    return [found[n] for n in sorted(found)]


# ── statement splitting (dollar-quote aware) ─────────────────────────────────────────────

_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def split_statements(sql: str) -> list[str]:
    """Split on top-level semicolons; aware of comments, quoted strings and ``$$`` bodies."""
    statements: list[str] = []
    start = 0
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "-" and sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end == -1 else end + 1
        elif ch == "/" and sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif ch == "'":
            i += 1
            while i < n:
                if sql[i] == "'":
                    if sql.startswith("''", i):
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
        elif ch == "$":
            match = _DOLLAR_TAG.match(sql, i)
            if match is None:
                i += 1
                continue
            tag = match.group(0)
            end = sql.find(tag, match.end())
            i = n if end == -1 else end + len(tag)
        elif ch == ";":
            statements.append(sql[start:i])
            i += 1
            start = i
        else:
            i += 1
    statements.append(sql[start:])
    return [s for s in statements if _has_code(s)]


def _has_code(fragment: str) -> bool:
    stripped = re.sub(r"/\*.*?\*/", " ", fragment, flags=re.DOTALL)
    stripped = re.sub(r"--[^\n]*", " ", stripped)
    return bool(stripped.strip())


# ── the MAINLINE bindings ────────────────────────────────────────────────────────────────

CUE_SCOPED = VectorTable(
    schema="mainline",
    table="event_cue_embedding",
    index="cue_scoped_idx",
    prefix_columns=("site_id", "scope_id", "facet"),
    vector_column="emb",
    id_column="cue_id",
    dimensions=1024,
)

CUE_SWEEP = VectorTable(
    schema="mainline",
    table="event_cue_coarse",
    index="cue_sweep_idx",
    prefix_columns=("tenant_id",),
    vector_column="emb_coarse",
    id_column="cue_id",
    dimensions=256,
)

CUE_STAGE = VectorTable(
    schema="mainline",
    table="event_cue_stage",
    # The staging mirror carries NO vector index — that is its entire reason for existing.
    # The binding names the live index because `create_vector_index_sql` against this binding
    # is the rejected import-then-index fallback, and the suite measures what it costs.
    index="cue_scoped_idx",
    prefix_columns=("site_id", "scope_id", "facet"),
    vector_column="emb",
    id_column="cue_id",
    dimensions=1024,
)

#: The closed facet vocabulary, in fusion priority order: a file-level `recurrence_test` hit
#: is the strongest evidence the channel can produce, and `narrative` is the safety net.
FACETS: tuple[str, ...] = (
    "recurrence_test",
    "mechanism",
    "precondition",
    "control_failure",
    "narrative",
)

#: The four facets a well-formed exposure cue populates. `narrative` is emitted by the cue
#: synthesiser too, but the completion test this suite answers is stated over four.
POPULATED_FACETS: tuple[str, ...] = FACETS[:4]


def policy() -> ArmPolicy:
    return ArmPolicy.graded(facet_priority=FACETS)


# ── deterministic vectors ────────────────────────────────────────────────────────────────


def unit_vector(dimensions: int, seed: str) -> list[float]:
    """A deterministic, L2-normalised vector derived from a seed string.

    Deterministic on purpose: an ANN result that changes between runs because the fixture
    changed is indistinguishable from one that changes because the index changed, and this
    suite exists to tell those two apart.
    """
    out: list[float] = []
    counter = 0
    while len(out) < dimensions:
        digest = hashlib.sha256(f"{seed}/{counter}".encode()).digest()
        out.extend(byte / 255.0 - 0.5 for byte in digest)
        counter += 1
    values = out[:dimensions]
    norm = sum(v * v for v in values) ** 0.5 or 1.0
    return [v / norm for v in values]


def near_vector(base: Sequence[float], *, seed: str, jitter: float = 0.02) -> list[float]:
    """A vector close to ``base`` — used to plant a precursor that top-k must return."""
    noise = unit_vector(len(base), seed)
    mixed = [b + jitter * n for b, n in zip(base, noise, strict=True)]
    norm = sum(v * v for v in mixed) ** 0.5 or 1.0
    return [v / norm for v in mixed]


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


# ── the corpus ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Taxonomy:
    site_id: uuid.UUID
    tenant_id: uuid.UUID
    fonds: uuid.UUID
    series: uuid.UUID
    file: uuid.UUID

    @property
    def levels(self) -> dict[int, uuid.UUID]:
        return {3: self.file, 2: self.series, 1: self.fonds}


@dataclass
class CorpusState:
    taxonomy: Taxonomy
    vectors_written: int = 0
    events_written: int = 0
    planted_cue_id: uuid.UUID | None = None
    planted_vector: tuple[float, ...] | None = None


def create_taxonomy(conn: object) -> Taxonomy:
    """One site with a frozen level-1 fonds and an induced series and file beneath it."""
    execute = _executor(conn)
    site_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    fonds, series, file_ = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    execute(
        """
        INSERT INTO mainline.activity_node
          (scope_id, site_id, level, parent_scope, label, activity_root, taxonomy_ver,
           induced_by, frozen)
        VALUES (%s, %s, 1, NULL, %s, 'ISOLATION-OF-STORED-ENERGY', 1, 'icmm_mue', true)
        """,
        (fonds, site_id, f"uncontrolled release of stored energy {fonds}"),
    )
    execute(
        """
        INSERT INTO mainline.activity_node
          (scope_id, site_id, level, parent_scope, label, activity_root, taxonomy_ver,
           induced_by, frozen)
        VALUES (%s, %s, 2, %s, %s, 'ISOLATION-OF-STORED-ENERGY', 1, 'llm_induced', false)
        """,
        (series, site_id, fonds, f"energy isolation {series}"),
    )
    execute(
        """
        INSERT INTO mainline.activity_node
          (scope_id, site_id, level, parent_scope, label, activity_root, taxonomy_ver,
           induced_by, frozen)
        VALUES (%s, %s, 3, %s, %s, 'ISOLATION-OF-STORED-ENERGY', 1, 'llm_induced', false)
        """,
        (file_, site_id, series, f"intrusive work on a pressurised assembly {file_}"),
    )
    return Taxonomy(site_id=site_id, tenant_id=tenant_id, fonds=fonds, series=series, file=file_)


#: How many rows go in one multi-row INSERT while building a corpus. Deliberately modest: the
#: documented guidance is that large batch vector inserts degrade, and test_ix06 measures where
#: that starts. Until it has run on the target cluster this number is a conservative guess and
#: is labelled as one — the corpus builder is not the thing being measured.
CORPUS_BATCH = 100


def grow_corpus(
    conn: object,
    state: CorpusState,
    *,
    target_vectors: int,
    facets: Sequence[str] = POPULATED_FACETS,
    seed_prefix: str = "corpus",
) -> CorpusState:
    """Grow the corpus to ``target_vectors`` scoped embeddings, adding only what is missing.

    One event contributes one cue row **per archival level per facet** — the level-materialised
    bond — so a corpus of E events over three levels and four facets holds 12·E scoped vectors
    spread across 12 K-means trees. Growth is additive so that 5k → 10k → 20k is three
    measurements on one growing corpus rather than three unrelated corpora.
    """
    execute = _executor(conn)
    levels = state.taxonomy.levels
    while state.vectors_written < target_vectors:
        cue_rows: list[tuple[object, ...]] = []
        emb_rows: list[tuple[object, ...]] = []
        coarse_rows: list[tuple[object, ...]] = []
        while len(emb_rows) < CORPUS_BATCH and state.vectors_written < target_vectors:
            event_id = uuid.uuid4()
            index = state.events_written
            severity = 5 if index % 97 == 0 else (index % 4) + 1
            execute(
                """
                INSERT INTO mainline.event
                  (event_id, site_id, external_ref, occurred_at, kind, title, narrative,
                   source_object_key, source_sha256, severity_actual, severity_potential,
                   severity_gate, severity_basis, canon_version)
                VALUES (%s, %s, %s, now() - INTERVAL '3000 days', 'incident',
                        'stored energy release during intrusive work',
                        'A contractor was struck when stored energy was released during an '
                        'intrusive task on an assembly that had not been proved dead.',
                        %s, %s, %s, %s, %s, 'coded_field', 1)
                """,
                (
                    event_id,
                    state.taxonomy.site_id,
                    f"INC-{event_id.hex[:10]}",
                    f"s3://mainline-raw/{event_id}",
                    hashlib.sha256(event_id.bytes).digest(),
                    severity,
                    severity,
                    severity,
                ),
            )
            state.events_written += 1
            for level, scope_id in levels.items():
                for facet in facets:
                    cue_id = uuid.uuid4()
                    seed = f"{seed_prefix}/{index}/{level}/{facet}"
                    cue_rows.append(
                        (
                            cue_id,
                            event_id,
                            state.taxonomy.site_id,
                            scope_id,
                            level,
                            facet,
                            f"recurs where {facet} at level {level} is not proved dead ({index})",
                        )
                    )
                    emb_rows.append(
                        (
                            cue_id,
                            state.taxonomy.site_id,
                            scope_id,
                            facet,
                            vector_literal(unit_vector(1024, seed)),
                        )
                    )
                    if level == 3 and facet == facets[0]:
                        coarse_rows.append(
                            (
                                cue_id,
                                state.taxonomy.tenant_id,
                                vector_literal(unit_vector(256, seed + "/coarse")),
                            )
                        )
                    state.vectors_written += 1
        _insert_many(
            execute,
            "INSERT INTO mainline.event_cue (cue_id, event_id, site_id, scope_id, scope_level,"
            " facet, taxonomy_ver, cue_text, is_derived, gen_model, prompt_version) VALUES ",
            "(%s, %s, %s, %s, %s, %s, 1, %s, true, 'claude-opus-5', 'cue-v1')",
            cue_rows,
        )
        _insert_many(
            execute,
            "INSERT INTO mainline.event_cue_embedding (cue_id, site_id, scope_id, facet,"
            " embed_model, index_gen, emb) VALUES ",
            "(%s, %s, %s, %s, 'bge-large-en-v1.5@pinned', 'gen-0', %s::VECTOR(1024))",
            emb_rows,
        )
        if coarse_rows:
            _insert_many(
                execute,
                "INSERT INTO mainline.event_cue_coarse (cue_id, tenant_id, severity_gate,"
                " embed_model, index_gen, emb_coarse) VALUES ",
                "(%s, %s, 0, 'bge-large-en-v1.5@pinned+pca256', 'gen-0', %s::VECTOR(256))",
                coarse_rows,
            )
    return state


def plant_precursor(
    conn: object,
    state: CorpusState,
    *,
    query_vector: Sequence[float],
    facet: str,
    level: int = 3,
) -> uuid.UUID:
    """Write one cue whose vector is deliberately near the query, and return its id.

    The behavioural test asserts this cue comes back in top-k. Plan text can be perfect while
    the executor returns the wrong neighbours; a planted precursor is the assertion that the
    answer, not merely the plan, is the one the gate depends on.
    """
    execute = _executor(conn)
    event_id = uuid.uuid4()
    execute(
        """
        INSERT INTO mainline.event
          (event_id, site_id, external_ref, occurred_at, kind, title, narrative,
           source_object_key, source_sha256, severity_actual, severity_potential,
           severity_gate, severity_basis, canon_version)
        VALUES (%s, %s, %s, now() - INTERVAL '4200 days', 'incident',
                'planted precursor', 'A planted precursor for the behavioural assertion.',
                %s, %s, 5, 5, 5, 'coded_field', 1)
        """,
        (
            event_id,
            state.taxonomy.site_id,
            f"INC-PLANTED-{event_id.hex[:8]}",
            f"s3://mainline-raw/{event_id}",
            hashlib.sha256(event_id.bytes).digest(),
        ),
    )
    cue_id = uuid.uuid4()
    scope_id = state.taxonomy.levels[level]
    execute(
        """
        INSERT INTO mainline.event_cue
          (cue_id, event_id, site_id, scope_id, scope_level, facet, taxonomy_ver, cue_text,
           is_derived, gen_model, prompt_version)
        VALUES (%s, %s, %s, %s, %s, %s, 1, 'planted precursor cue', true, 'claude-opus-5',
                'cue-v1')
        """,
        (cue_id, event_id, state.taxonomy.site_id, scope_id, level, facet),
    )
    planted = near_vector(query_vector, seed=f"planted/{cue_id}")
    execute(
        """
        INSERT INTO mainline.event_cue_embedding
          (cue_id, site_id, scope_id, facet, embed_model, index_gen, emb)
        VALUES (%s, %s, %s, %s, 'bge-large-en-v1.5@pinned', 'gen-0', %s::VECTOR(1024))
        """,
        (cue_id, state.taxonomy.site_id, scope_id, facet, vector_literal(planted)),
    )
    state.planted_cue_id = cue_id
    state.planted_vector = tuple(planted)
    state.vectors_written += 1
    return cue_id


def _insert_many(
    execute: Callable[..., object], head: str, row_sql: str, rows: Sequence[tuple[object, ...]]
) -> None:
    if not rows:
        return
    statement = head + ", ".join([row_sql] * len(rows))
    flat: list[object] = [value for row in rows for value in row]
    execute(statement, tuple(flat))


def _executor(conn: object) -> Callable[..., object]:
    execute = getattr(conn, "execute", None)
    if execute is None:  # pragma: no cover - a connection without execute is a caller bug
        raise TypeError(f"{conn!r} has no .execute")
    return execute


# ── explain sources ──────────────────────────────────────────────────────────────────────


def pgwire_explain_source(conn: object) -> Callable[[str], str]:
    """Turn a psycopg connection into the callable ``trappoint_recall.arms`` expects."""
    execute = _executor(conn)

    def source(statement: str) -> str:
        cursor = execute(statement)
        rows = cursor.fetchall()  # type: ignore[attr-defined]
        return "\n".join(" ".join(str(cell) for cell in row) for row in rows)

    return source


@dataclass(frozen=True)
class Timing:
    samples: tuple[float, ...]

    @property
    def milliseconds(self) -> list[float]:
        return [s * 1000.0 for s in self.samples]


def time_query(
    conn: object, statement: str, params: Sequence[object] = (), *, repeats: int = 20
) -> Timing:
    """Execute a statement ``repeats`` times, returning wall-clock seconds per execution.

    Results are consumed each time. A latency measurement that never reads the rows measures
    the parser.
    """
    execute = _executor(conn)
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        cursor = execute(statement, tuple(params)) if params else execute(statement)
        cursor.fetchall()  # type: ignore[attr-defined]
        samples.append(time.perf_counter() - started)
    return Timing(samples=tuple(samples))


def warm(conn: object, statement: str, params: Sequence[object] = (), *, repeats: int = 3) -> None:
    """Run a statement a few times and discard the results, so the first sample is not cold."""
    time_query(conn, statement, params, repeats=repeats)


# ── environment ──────────────────────────────────────────────────────────────────────────


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def env_sizes(name: str, default: Sequence[int]) -> tuple[int, ...]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return tuple(default)
    return tuple(int(part) for part in raw.replace(" ", "").split(",") if part)


def read_setting(conn: object, setting: str) -> str | None:
    """``SHOW <setting>`` — read at runtime, never assumed.

    Returns ``None`` when the cluster does not know the setting, which is information: it
    means this CockroachDB predates it, and the characterisation test says so rather than
    silently characterising a default that does not exist.
    """
    execute = _executor(conn)
    try:
        cursor = execute(f"SHOW {setting}")
        rows: Iterable[Sequence[object]] = cursor.fetchall()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - an unknown setting raises; that is the answer
        return None
    for row in rows:
        if row:
            return str(row[0])
    return None
