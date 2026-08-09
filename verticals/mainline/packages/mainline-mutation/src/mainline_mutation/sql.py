# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Write a run into ``mainline_meas.mutation_run`` / ``mutation_result``.

The statements and their parameter tuples are built here, in pure Python, with
no driver import at module scope.  Two reasons, and neither is portability:

* the harness must produce its published number on a machine with **no cluster**
  (PL-1), so a database dependency on the import path would make the artefact
  unproducible for a stranger;
* the statements are then **testable without a cluster**.
  ``tests/e2e/mutation/test_sql_shape.py`` asserts that every column this module
  names exists in ``0049y``/``0049z`` and that the closed vocabularies in the
  Python match the ``CHECK`` constraints in the SQL — the drift that would
  otherwise be found by a `23514` in a nightly job three weeks later.

:func:`record_run` takes any object with ``execute(sql, params)``: a
``psycopg`` cursor, or a recorder in a test.  It is a protocol and not an import.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Final, Protocol

from mainline_domain.canon.version import CANON_VERSION
from mainline_domain.cat.extract import extractor_version
from mainline_domain.identity.candidates import DEFAULT_BANDS, RESCORE_VERSION
from mainline_domain.identity.candidates.minhash import default_params
from mainline_domain.lattice.version import LATTICE_VERSION, rule_catalogue_fingerprint
from mainline_domain.registry import ENCODING_VERSION

from .catalogue import confidence, operator_fingerprint
from .metrics import (
    false_identity_change_rate,
    false_weaken_rate,
    summarise,
)
from .model import KILL, SURVIVE
from .paraphrase import provenance_label
from .residue import RESIDUE_SOURCE
from .resources import catalogue_sha256
from .runner import RunOutput
from .version import HARNESS_VERSION

__all__ = [
    "CASCADE_S4_DRIVEN",
    "CBM_EXERCISED",
    "INSERT_RESULT",
    "INSERT_RUN",
    "PATH_B_CONSULTED",
    "RESULT_COLUMNS",
    "RUN_COLUMNS",
    "Executor",
    "record_run",
    "result_params",
    "run_params",
]


#: Three honesty flags, written out as constants so that the day one of them
#: becomes ``True`` is a one-line diff in this file rather than an invisible
#: change in a tuple. Path B is never consulted (the published figure is the
#: model-free floor); the CBM ledger is not exercised (it needs a cluster, a
#: commit DAG and blame closure rows); cascade S4 is not driven (it needs
#: embeddings and a cluster, and PL-3 forbids a dated path on either).
PATH_B_CONSULTED: Final[bool] = False
CBM_EXERCISED: Final[bool] = False
CASCADE_S4_DRIVEN: Final[bool] = False


class Executor(Protocol):
    """Anything that can run a parameterised statement.  A cursor, or a recorder."""

    def execute(self, statement: str, parameters: tuple[Any, ...]) -> object: ...


RUN_COLUMNS: Final[tuple[str, ...]] = (
    "run_id",
    "seed",
    "arm",
    "disabled_lattice_rules",
    "harness_version",
    "catalogue_sha256",
    "operator_fingerprint",
    "policy_sha256",
    "lattice_rule_fingerprint",
    "canon_version",
    "cat_extractor_version",
    "lattice_version",
    "minhash_version",
    "rescore_version",
    "registry_encoding_version",
    "kill_trials",
    "kill_killed",
    "kill_rate_wilson_lower",
    "kill_rate_point",
    "kill_rate_wilson_upper",
    "survive_trials",
    "survive_preserved",
    "survive_rate_wilson_lower",
    "survive_rate_point",
    "survive_rate_wilson_upper",
    "false_identity_change_rate",
    "false_weaken_rate",
    "confidence",
    "skipped_pairings",
    "path_b_consulted",
    "residue_source",
    "paraphrase_provenance",
    "cbm_exercised",
    "cascade_s4_driven",
    "artefact_path",
)

RESULT_COLUMNS: Final[tuple[str, ...]] = (
    "run_id",
    "mutant_id",
    "kind",
    "class_id",
    "fixture_id",
    "family",
    "outcome",
    "success",
    "outcome_reason",
    "ancestor_canon_sha256",
    "descendant_canon_sha256",
    "ancestor_cat_key",
    "descendant_cat_key",
    "ancestor_cat_confidence",
    "descendant_cat_confidence",
    "delta",
    "delta_basis",
    "delta_force",
    "ratchet_delta_without_oracle",
    "witness_rule_ids",
    "residue_reasons",
    "identity_recovered",
    "match_stage",
    "match_score",
    "anchors_considered",
    "chain_length",
    "chain_adjacent_max_force",
)


def _insert(table: str, columns: tuple[str, ...]) -> str:
    # S608: the only interpolated values are this module's own frozen column
    # tuples and two literal table names. Every VALUE is a `%s` placeholder bound
    # by the driver; nothing a caller supplies reaches the statement text. The
    # statement is built rather than written out so that RUN_COLUMNS and the
    # parameter tuple in `run_params` cannot drift apart, which is the failure
    # this shape exists to prevent.
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"  # noqa: S608


INSERT_RUN: Final[str] = _insert("mainline_meas.mutation_run", RUN_COLUMNS)
INSERT_RESULT: Final[str] = _insert("mainline_meas.mutation_result", RESULT_COLUMNS)

#: `DECIMAL(9,6)` in the DDL. Quantising here rather than letting the driver
#: round means the value in the database is the value in the JSON artefact, and
#: a reader comparing the two never has to wonder which one was rounded.
_RATE = Decimal("0.000001")


def _rate(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_RATE)


def run_params(
    output: RunOutput,
    *,
    run_id: uuid.UUID,
    artefact_path: str | None = None,
) -> tuple[Any, ...]:
    """The parameter tuple for one ``mutation_run`` row, in :data:`RUN_COLUMNS` order."""
    level = confidence()
    kill = summarise(output.results, kind=KILL, confidence=level)
    survive = summarise(output.results, kind=SURVIVE, confidence=level)
    return (
        str(run_id),
        output.seed,
        "crippled" if output.disabled_rules else "intact",
        list(output.disabled_rules),
        HARNESS_VERSION,
        catalogue_sha256(),
        operator_fingerprint(),
        DEFAULT_BANDS.fingerprint().hex(),
        rule_catalogue_fingerprint().hex(),
        CANON_VERSION,
        extractor_version(),
        LATTICE_VERSION,
        default_params().minhash_version,
        RESCORE_VERSION,
        ENCODING_VERSION,
        kill.trials,
        kill.successes,
        _rate(kill.interval.lower),
        _rate(kill.interval.point),
        _rate(kill.interval.upper),
        survive.trials,
        survive.successes,
        _rate(survive.interval.lower),
        _rate(survive.interval.point),
        _rate(survive.interval.upper),
        _rate(false_identity_change_rate(output.results)),
        _rate(false_weaken_rate(output.results)),
        level,
        len(output.skips),
        # Honesty columns. Every one is the pessimistic value; see the constants.
        PATH_B_CONSULTED,
        RESIDUE_SOURCE,
        provenance_label(),
        CBM_EXERCISED,
        CASCADE_S4_DRIVEN,
        artefact_path,
    )


def result_params(output: RunOutput, *, run_id: uuid.UUID) -> list[tuple[Any, ...]]:
    """One parameter tuple per mutant, in :data:`RESULT_COLUMNS` order."""
    rows: list[tuple[Any, ...]] = []
    for result in output.results:
        pipeline = result.pipeline
        rows.append(
            (
                str(run_id),
                result.mutant_id,
                result.kind,
                result.class_id,
                result.fixture_id,
                result.family,
                result.outcome,
                result.success,
                result.outcome_reason,
                pipeline.ancestor_canon_sha256,
                pipeline.descendant_canon_sha256,
                pipeline.ancestor_cat_key,
                pipeline.descendant_cat_key,
                pipeline.ancestor_cat_confidence,
                pipeline.descendant_cat_confidence,
                pipeline.delta,
                pipeline.delta_basis,
                pipeline.delta_force,
                pipeline.ratchet_delta_without_oracle,
                list(pipeline.witness_rule_ids),
                list(pipeline.residue_reasons),
                pipeline.identity_recovered,
                pipeline.match_stage,
                None if pipeline.match_score is None else _rate(pipeline.match_score),
                pipeline.anchors_considered,
                result.chain_length,
                output.adjacent_max_force.get(result.mutant_id),
            )
        )
    return rows


def record_run(
    cursor: Executor,
    output: RunOutput,
    *,
    run_id: uuid.UUID | None = None,
    artefact_path: str | None = None,
) -> uuid.UUID:
    """Insert the run row and every result row.  Returns the ``run_id``.

    The run row is written FIRST because ``mutation_result.fk_run`` references
    it and CockroachDB checks foreign keys per statement — there is no
    ``DEFERRABLE`` on this platform, which is the same measured limit
    ``0049a_delta_witness.sql`` records for the witness ordering contract.

    The caller owns the transaction.  A harness that opened its own would be a
    harness that could half-write a run, and a run whose results do not add up to
    its own counts is worse than no run.
    """
    identifier = run_id or uuid.uuid4()
    cursor.execute(INSERT_RUN, run_params(output, run_id=identifier, artefact_path=artefact_path))
    for row in result_params(output, run_id=identifier):
        cursor.execute(INSERT_RESULT, row)
    return identifier
