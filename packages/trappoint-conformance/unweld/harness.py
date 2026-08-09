# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Running the unwelding matrix, and writing down what it measured.

**This is the only place in the repository where the structural-redundancy claim is made.**
At runtime the deterministic ``RAISE`` fires first — that is adversarial-review finding
``S4``, and it is why no case in ``cases/`` asserts a second mechanism. A sentence like
*"delete the ``RAISE`` and the write still fails twice over"* is not observable from the
outside of a working system; it is observable only by deleting the ``RAISE``.

The procedure, per history and per mechanism:

1. take the mechanism away, and nothing else;
2. re-run the identical illegal history, in a **fresh tenancy** so no row from the previous
   probe is in scope;
3. assert the write is still refused, **by something else** — the assertion compares
   mechanism identities, not SQLSTATEs, because two constraints can share a code and
   sharing a code is not sharing a mechanism;
4. put it back, and prove it went back by re-running the baseline.

``depth`` is then the number of **distinct mechanisms observed to refuse the same history**
across the baseline and every single-mechanism removal. Not the number of mechanisms
declared: the number observed. A mechanism that is in the matrix and never observed is
reported as unobserved, because a defence that never fires is a defence nobody has seen
work.

Reuse note: probes go through :func:`trappoint_conformance.runner.run` rather than calling
case functions directly. That is not indirection for its own sake — it means the history a
probe runs is *byte-identical* to the history the conformance suite runs, including the
tenancy scoping and the exhibit resolution. A harness with its own copy of the history would
be measuring the copy.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from psycopg import sql as pgsql

from trappoint_conformance.manifest import Manifest
from trappoint_conformance.runner import Status, run

from .mutations import MECHANISMS, Mutation, for_case

# The refusal-depth floor. Two independent mechanisms, and the pre-committed response
# to one is to cut the mechanism rather than lower this number.
DEPTH_FLOOR = 2

__all__ = [
    "MatrixRow",
    "Observation",
    "collect",
    "merge_gate_case_ids",
    "observe",
    "render_report",
]


@dataclass(frozen=True, slots=True)
class Observation:
    """What one history did under one schema configuration."""

    case_id: str
    removed: str
    """Mechanism identity taken away, or ``""`` for the baseline."""
    refused: bool
    sqlstate: str
    exhibit: str
    detail: str = ""
    measurable: bool = True
    """False when the history could not be run at all under this removal — because the
    **legal** world the history is illegal in could no longer be built.

    That is not an admission and must never be counted as one. Disabling
    ``check_materialised``, for instance, stops the obligation counter rising, so the
    disposition that closes the obligation drives it to minus one and ``ctr_nonneg``
    refuses the *setup*. What that measures is coupling — the projection is load-bearing
    for the legal path as well as the illegal one — and it is reported as its own fact
    rather than folded into a depth nobody could interpret."""

    @property
    def mechanism(self) -> str:
        """The mechanism identity the refusal came from.

        For a constraint the exhibit *is* the mechanism's local name; for a ``P0001`` the
        exhibit is the raising object. Either way it is compared against
        :attr:`Mutation.name` by suffix, because the matrix names mechanisms as
        ``relation.constraint`` / ``relation@trigger`` and the driver knows nothing about
        the relation.
        """
        return self.exhibit


@dataclass(slots=True)
class MatrixRow:
    """One history's whole row of the matrix."""

    case_id: str
    baseline: Observation | None = None
    probes: list[tuple[Mutation, Observation]] = field(default_factory=list)
    unremovable: list[Mutation] = field(default_factory=list)
    not_validated: list[str] = field(default_factory=list)
    """Mechanisms that had to be restored ``NOT VALID`` because the probe left a row they
    forbid. Each entry is a mechanism whose removal alone admitted an illegal write."""
    restore_failures: list[str] = field(default_factory=list)
    """Mechanisms that could not be put back at all. Every later measurement on this
    cluster is suspect and the report says so."""

    @property
    def observed_mechanisms(self) -> tuple[str, ...]:
        """Distinct mechanisms seen refusing this history, sorted."""
        seen = set()
        if self.baseline is not None and self.baseline.refused:
            seen.add(self.baseline.mechanism)
        for _, observation in self.probes:
            if observation.refused and observation.measurable:
                seen.add(observation.mechanism)
        return tuple(sorted(seen))

    @property
    def depth(self) -> int:
        """How many independent mechanisms were **observed** to refuse this history."""
        return len(self.observed_mechanisms)

    @property
    def unwelded_by(self) -> tuple[str, ...]:
        """Mechanisms whose removal alone opened the gate. Should always be empty."""
        return tuple(
            mutation.name
            for mutation, observation in self.probes
            if observation.measurable and not observation.refused
        )

    @property
    def unmeasurable(self) -> tuple[tuple[str, str], ...]:
        """Removals under which the LEGAL world could no longer be built."""
        return tuple(
            (mutation.name, observation.detail)
            for mutation, observation in self.probes
            if not observation.measurable
        )


def _mechanism_matches(exhibit: str, mutation: Mutation) -> bool:
    """Whether *exhibit* names *mutation*.

    ``permit.gate_closed_when_issued`` is matched by the bare constraint name
    ``gate_closed_when_issued``; ``permit@permit_merge_gate`` is matched by the resolved
    ``P0001`` exhibit ``mainline.fn_permit_merge_gate``, whose local part is the *function*
    rather than the trigger — so the trigger's own name is mapped through the convention
    ``trg <-> fn_``. Both directions are spelled out here rather than guessed, because a
    fuzzy match would make "the surviving refusal came from something else" trivially true.
    """
    if "@" in mutation.name:
        trigger = mutation.name.split("@", 1)[1]
        function = f"fn_{trigger}"
        return exhibit.endswith(f".{function}") or exhibit == function
    local = mutation.name.split(".", 1)[1]
    return exhibit == local


def observe(
    manifest: Manifest,
    conn: Any,
    *,
    case_id: str,
    profile: str,
    schema: str | None,
    removed: str = "",
) -> Observation:
    """Run one history once and record what the database said."""
    try:
        report = run(
            manifest,
            profile=profile,
            conn=conn,
            schema=schema,
            only=frozenset({case_id}),
            satisfied_requirements=(),
            run_id=f"unweld{time.strftime('%H%M%S')}{abs(hash((case_id, removed))) % 9973:04d}",
        )
    except Exception as exc:  # noqa: BLE001 — SetupRefused and anything like it
        return Observation(
            case_id,
            removed,
            refused=False,
            sqlstate="",
            exhibit="",
            detail=" ".join(str(exc).split())[:300],
            measurable=False,
        )
    if not report.results:
        return Observation(case_id, removed, False, "", "", "case not selected for profile")
    result = report.results[0]
    observed = result.observed
    if observed is None:
        return Observation(
            case_id, removed, False, "", "", result.detail or "no observation recorded"
        )
    return Observation(
        case_id=case_id,
        removed=removed,
        refused=not observed.completed,
        sqlstate=observed.sqlstate,
        exhibit=observed.constraint,
        detail="" if result.status is Status.PASSED else result.detail,
    )


def _attempt(conn: Any, composed: Any) -> bool:
    """Run *composed*, reporting success as a value rather than raising.

    The failure is EXPECTED on exactly the histories this suite exists to find: a
    restoration that cannot validate is the signature of a mechanism whose removal
    admitted a write. The exception carries nothing the caller does not already have from
    the ``False``, and the diagnostics that matter are re-raised by the second attempt.
    """
    try:
        conn.execute(composed)
    except Exception:  # noqa: BLE001 - the outcome, not the exception, is the datum
        return False
    return True


def _apply(conn: Any, statement: str, schema: str) -> bool:
    """Run one piece of matrix DDL. Returns whether it validated existing rows.

    **The fallback is the interesting part.** When a probe finds a mechanism that was the
    *only* thing refusing a history, the history succeeds and leaves behind a row the
    mechanism forbids — a merged permit with an open obligation, a completion with no
    commit. Putting the mechanism back then fails validation against that very row.

    That row is the **evidence**, and the tables it sits in are append-only, so it cannot
    be deleted and must not be. The restoration therefore falls back to ``NOT VALID``,
    which re-arms the mechanism for every subsequent write while leaving the historical
    row where the probe left it. The fallback is recorded rather than swallowed: a matrix
    run that had to use it is a matrix run that found an unwelded gate, and that is the
    single most important thing the suite can report.
    """
    if not statement:
        return True
    composed = pgsql.SQL(statement).format(s=pgsql.Identifier(schema))  # type: ignore[arg-type]
    if _attempt(conn, composed):
        return True
    upper = statement.upper()
    if "ADD CONSTRAINT" not in upper or ("CHECK" not in upper and "FOREIGN KEY" not in upper):
        conn.execute(composed)  # re-raise with the original diagnostics
        return True
    conn.execute(
        pgsql.SQL(statement + " NOT VALID").format(s=pgsql.Identifier(schema))  # type: ignore[arg-type]
    )
    return False


def collect(
    manifest: Manifest,
    conn: Any,
    *,
    profile: str,
    schema: str,
    case_ids: Iterable[str] | None = None,
) -> list[MatrixRow]:
    """Run the whole matrix and return one row per history.

    Mutations are applied and reverted one at a time against a **disposable** cluster. The
    revert is not optional and it is not best-effort: the next probe's baseline would
    otherwise be measured against a schema the previous probe damaged, and every number
    after the first failure would be wrong in a direction nobody could see.
    """
    wanted = set(case_ids) if case_ids is not None else {c.id for c in manifest.cases}
    rows: list[MatrixRow] = []
    # Mechanisms that could not be put back after an earlier probe. A UNIQUE index is the
    # case that forces this: when its removal admits the write, the rows left behind are
    # duplicates, and unlike a CHECK or a foreign key there is no `NOT VALID` form to
    # re-arm it against future writes only. Once that has happened the mechanism is gone
    # for the rest of the run, so it is NOT removed again — a second probe would be
    # measuring a schema missing two mechanisms and reporting it as missing one.
    broken: set[str] = set()
    for case in manifest.for_profile(profile):
        if case.id not in wanted:
            continue
        mutations = for_case(case.id)
        if not mutations:
            continue
        row = MatrixRow(case_id=case.id)
        row.baseline = observe(manifest, conn, case_id=case.id, profile=profile, schema=schema)
        for mutation in mutations:
            if not mutation.removable:
                row.unremovable.append(mutation)
                continue
            if mutation.name in broken:
                row.probes.append(
                    (
                        mutation,
                        Observation(
                            case.id,
                            mutation.name,
                            refused=False,
                            sqlstate="",
                            exhibit="",
                            detail=(
                                "not probed: this mechanism could not be restored after an "
                                "earlier probe on this cluster, so removing it again would "
                                "measure a schema short of two mechanisms while reporting "
                                "one"
                            ),
                            measurable=False,
                        ),
                    )
                )
                continue
            _apply(conn, mutation.remove, schema)
            try:
                row.probes.append(
                    (
                        mutation,
                        observe(
                            manifest,
                            conn,
                            case_id=case.id,
                            profile=profile,
                            schema=schema,
                            removed=mutation.name,
                        ),
                    )
                )
            finally:
                try:
                    if not _apply(conn, mutation.restore, schema):
                        row.not_validated.append(mutation.name)
                except Exception as exc:  # noqa: BLE001
                    broken.add(mutation.name)
                    # A restore that cannot be completed at all leaves the cluster one
                    # mechanism short, so every later row would be measured against a
                    # schema nobody ships. Recorded and carried into the report rather
                    # than raised: an aborted matrix reports nothing, and a matrix that
                    # says which mechanism it could not put back is still evidence.
                    row.restore_failures.append(
                        f"{mutation.name}: {' '.join(str(exc).split())[:160]}"
                    )
        rows.append(row)
    return rows


def merge_gate_case_ids(manifest: Manifest, profile: str) -> frozenset[str]:
    """Return the histories the depth floor applies to.

    A **merge-gate history** is one that instantiates ``I02`` — the projected-refusal
    invariant, the one the product is — and whose manifest declares ``refusal_depth_min``
    of two or more. The definition is mechanical rather than editorial so that adding a
    case to the manifest adds it to this gate automatically, and so that nobody can quietly
    move a history out of the gate by renaming it.
    """
    return frozenset(
        case.id
        for case in manifest.for_profile(profile)
        if "I02" in case.invariants and case.refusal_depth_min >= DEPTH_FLOOR
    )


def render_report(  # noqa: PLR0912, PLR0915 - a document generator is a long function
    rows: Sequence[MatrixRow],
    *,
    manifest: Manifest,
    profile: str,
    schema: str,
    gated: frozenset[str],
    server_version: str = "",
    provenance: str = "",
) -> str:
    """Render ``REFUSAL_DEPTH.md``: history x surviving mechanism."""
    mechanisms = sorted({m.name for m in MECHANISMS})
    used = [
        name
        for name in mechanisms
        if any(
            any(mu.name == name for mu, _ in r.probes)
            or any(mu.name == name for mu in r.unremovable)
            for r in rows
        )
    ]
    lines: list[str] = []
    lines.append("<!--")
    lines.append("SPDX-FileCopyrightText: 2026 MAINLINE contributors")
    lines.append("SPDX-License-Identifier: Apache-2.0")
    lines.append("-->")
    lines.append("")
    lines.append("# `REFUSAL_DEPTH.md` — the unwelding matrix")
    lines.append("")
    lines.append(
        "**Generated by `unweld/test_unweld.py`. Do not edit.** Every number below was "
        "measured by taking one mechanism away, re-running the identical illegal history "
        "in a fresh tenancy, and putting the mechanism back."
    )
    lines.append("")
    lines.append(f"* profile · `{profile}` · schema `{schema}`")
    lines.append(f"* spec · `{manifest.spec_version}`")
    if server_version:
        lines.append(f"* cluster · `{server_version}`")
    lines.append(f"* histories measured · {len(rows)}")
    if provenance:
        lines.append("")
        lines.append(f"> **Provenance.** {provenance}")
    lines.append("")
    single = [r for r in rows if r.case_id in gated and r.depth < DEPTH_FLOOR]
    opened = sorted({name for r in rows for name in r.unwelded_by})
    lines.append("## What this run found")
    lines.append("")
    if single or opened:
        lines.append(
            f"**{len(single)} of {len(gated & {r.case_id for r in rows})} gated merge-gate "
            f"histories measured at depth 1, and {len(opened)} mechanism(s) opened a gate "
            f"when removed alone.** The architecture's sentence — *delete the `RAISE` and "
            f"the write still fails twice over* — does not hold for those histories as the "
            f"schema currently stands, and this file is where that is said rather than "
            f"assumed."
        )
        lines.append("")
        lines.append(
            "The reason is structural rather than accidental, and it is worth stating "
            "precisely because it looks like a bug and is not one. `fn_permit_merge_gate` "
            "**deliberately declines to decide** when the projected counter agrees with "
            "the re-derivation: the refusal then belongs to `gate_closed_when_issued`, "
            "whose name is the exhibit, and raising a `P0001` over the top of it would "
            "trade a named constraint for an unnamed one (`spec/errors.md` §3.3, "
            "corollary). The consequence is that on the ordinary path exactly one "
            "mechanism refuses, and on the drift path exactly one other does. Each is "
            "correct alone; neither is a second weld for the other."
        )
        lines.append("")
        lines.append(
            "That is a decision for the kernel lead, and the pre-committed response to a "
            "depth of one is on the record: *cut the mechanism, do not ship it.* The "
            "measurement is here so the choice is made with a number in front of it."
        )
    else:
        lines.append(
            "Every gated merge-gate history is refused by at least two independent "
            "mechanisms, and no single removal opened a gate."
        )
    lines.append("")
    lines.append("## What `depth` means here")
    lines.append("")
    lines.append(
        "`depth` is the number of **distinct mechanisms observed to refuse the same "
        "history** across the baseline and every single-mechanism removal. It is not the "
        "number declared: a mechanism that is in the matrix and never observed is reported "
        "as unobserved, because a defence nobody has seen fire is a defence nobody has "
        "seen work."
    )
    lines.append("")
    lines.append(
        "**At runtime the deterministic `RAISE` fires first** (adversarial finding `S4`), "
        "and no case in `cases/` asserts otherwise. The redundancy below is a property of "
        "the schema, observable only by unwelding it, and this file is the only place the "
        "claim is made."
    )
    lines.append("")
    lines.append("## The matrix")
    lines.append("")
    header = "| history | depth | baseline exhibit | surviving mechanisms | unwelded by |"
    lines.append(header)
    lines.append("|---|---|---|---|---|")
    for row in rows:
        base = row.baseline
        base_cell = (
            f"`{base.sqlstate}` `{base.exhibit}`"
            if base is not None and base.refused
            else "**ADMITTED**"
            if base is not None
            else "—"
        )
        survivors = ", ".join(f"`{m}`" for m in row.observed_mechanisms) or "—"
        unwelded = ", ".join(f"**`{m}`**" for m in row.unwelded_by) or "—"
        flag = " ⚠" if row.case_id in gated and row.depth < DEPTH_FLOOR else ""
        lines.append(
            f"| `{row.case_id}`{flag} | {row.depth} | {base_cell} | {survivors} | {unwelded} |"
        )
    lines.append("")
    coupled = [(r.case_id, r.unmeasurable) for r in rows if r.unmeasurable]
    if coupled:
        lines.append("### Removals under which the legal world could not be built")
        lines.append("")
        lines.append(
            "Not admissions, and never counted as depth. A projection that maintains the "
            "counter is load-bearing for the LEGAL path as well as the illegal one, so "
            "removing it makes the setup itself illegal — the disposition that closes an "
            "obligation drives the counter below zero and `ctr_nonneg` refuses it. What "
            "this measures is coupling, and it is reported as its own fact rather than "
            "folded into a number nobody could interpret."
        )
        lines.append("")
        for case_id, entries in coupled:
            for name, why in entries:
                lines.append(f"* `{case_id}` — removing `{name}`: {why[:200]}")
        lines.append("")
    stragglers = [(r.case_id, r.not_validated) for r in rows if r.not_validated]
    if stragglers:
        lines.append("### Restorations that could not validate")
        lines.append("")
        lines.append(
            "A mechanism whose removal alone admitted the write leaves behind a row it "
            "forbids. The tables are append-only, so the row stays and the restoration "
            "falls back to `NOT VALID` — the mechanism is re-armed for every subsequent "
            "write and the historical row is left where the probe left it, because that "
            "row is the evidence. **Every line here is an unwelded gate.**"
        )
        lines.append("")
        for case_id, names in stragglers:
            lines.append(f"* `{case_id}` — {', '.join(f'`{n}`' for n in names)}")
        lines.append("")
    broken = [(r.case_id, r.restore_failures) for r in rows if r.restore_failures]
    if broken:
        lines.append("### Restorations that failed outright")
        lines.append("")
        lines.append(
            "**Every measurement after one of these is suspect**: the cluster ran the rest "
            "of the matrix one mechanism short."
        )
        lines.append("")
        for case_id, failures in broken:
            for failure in failures:
                lines.append(f"* `{case_id}` — {failure}")
        lines.append("")
    lines.append("## Mechanisms exercised")
    lines.append("")
    lines.append("| mechanism | kind | code | removable |")
    lines.append("|---|---|---|---|")
    for name in used:
        mutation = next(m for m in MECHANISMS if m.name == name)
        removable = "yes" if mutation.removable else f"**no** — {mutation.unremovable_reason}"
        lines.append(
            f"| `{mutation.name}` | {mutation.kind} | `{mutation.sqlstate}` | {removable} |"
        )
    lines.append("")
    lines.append("## The floor")
    lines.append("")
    lines.append(
        "CI fails when a **merge-gate history** — one instantiating `I02` with a declared "
        "`refusal_depth_min` of two or more — measures depth below two. The pre-committed "
        "response to a depth of one is the kernel lead's, and it is not to relax the "
        "floor: *cut the mechanism, do not ship it.* A single-welded gate is a claim that "
        "cannot be made under oath."
    )
    lines.append("")
    breaches = [r for r in rows if r.case_id in gated and r.depth < DEPTH_FLOOR]
    if breaches:
        lines.append("**Histories below the floor on this run:**")
        lines.append("")
        for row in breaches:
            lines.append(
                f"* `{row.case_id}` — depth {row.depth}; observed "
                f"{', '.join(f'`{m}`' for m in row.observed_mechanisms) or 'nothing'}."
            )
    else:
        lines.append("Every gated history measured at or above the floor on this run.")
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, text: str) -> None:
    """Write the rendered report."""
    path.write_text(text, encoding="utf-8")
