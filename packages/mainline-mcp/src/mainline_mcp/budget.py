# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The response-budget prober: measure every audit view, fail at 80 % of the cap.

The Managed MCP response cap is 10 240 bytes and the server **truncates** rather than
raising. So the size of an audit view is a *functional requirement*, not an operational
detail, and the way it is verified is by measuring the bytes that actually arrived.

The budget is 8 192 bytes — 80 % of the cap — for one reason, stated in the plan as risk
AR-6: *a limit tested at 100 % breaches in front of a judge the first time the corpus
grows.* Failing at 8 KiB means the alarm fires with 20 % of headroom left and the breach
lands in CI, on a day when someone can fix it.

Five things count as a breach, and the last three are the ones that make this a
verification rather than a size check:

``byte_budget``
    The measured response exceeded the budget.
``row_budget``
    More rows than the contract allows. An audit view is aggregate-first by design.
``row_count_undetermined``
    The rows could not be recovered from the response envelope. **This is a failure, not
    a skip.** A view whose row count cannot be measured has not been verified, and
    recording it as a pass would be exactly the kind of green-by-absence this repository
    refuses.
``truncation_flag_missing``
    The contract says this view carries a completeness flag and the returned rows do not
    have that column. In this product an aggregate that silently truncated is a safety
    defect, so the flag's absence is a defect in the surface, not a cosmetic gap.
``tool_error`` / ``response_cap``
    The server refused, or the response arrived at the cap and may already be a
    truncation rather than an answer.

The worst observed row is recorded on every measurement, breach or not, because the
accepted residual in AR-6 is that a single pathological row — one very long site code —
can spike one view, and the cause has to be nameable when it happens.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .catalogue import Catalogue, ViewSpec
from .client import Client
from .limits import (
    BUDGET_RESPONSE_BYTES,
    BUDGET_ROWS,
    MAX_RESPONSE_BYTES,
    McpClientError,
    ResponseTooLarge,
)

_SUMMARY_ROW: Final = "{view:<34} {rows:>6} {size:>8} {worst:>9}  {verdict}"
_HEADER_ROW: Final = _SUMMARY_ROW.format(
    view="view", rows="rows", size="bytes", worst="worst row", verdict="verdict"
)


def row_bytes(row: Mapping[str, Any]) -> int:
    """Bytes one row costs in a compact JSON encoding.

    Measured the same way for every row so the comparison between rows is meaningful.
    This is deliberately *not* how the server encodes the row — the response total is
    measured on the wire; this number exists only to rank rows against each other.
    """
    return len(
        json.dumps(dict(row), separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
    )


def row_key(row: Mapping[str, Any]) -> str:
    """Return a short, stable identifier for a row, so "the worst row" names something."""
    if not row:
        return "(empty row)"
    parts = [f"{name}={value!r}" for name, value in list(row.items())[:2]]
    return ", ".join(parts)


@dataclass(frozen=True, slots=True)
class Breach:
    """One budget breach, with the number that broke it."""

    limit: str
    budget: int | None
    observed: int | None
    detail: str

    def render(self) -> str:
        """One line naming the limit, the budget and the observation."""
        if self.budget is None or self.observed is None:
            return f"{self.limit}: {self.detail}"
        return f"{self.limit}: {self.observed} against a budget of {self.budget} — {self.detail}"


@dataclass(frozen=True, slots=True)
class WorstRow:
    """The largest row observed in a view's response."""

    index: int
    byte_count: int
    key: str


@dataclass(frozen=True, slots=True)
class ViewMeasurement:
    """What one contracted view actually cost, measured rather than assumed."""

    view: str
    statement: str
    response_bytes: int
    row_count: int | None
    worst_row: WorstRow | None
    truncation_flag: str | None
    truncation_flag_present: bool
    incomplete_rows: int | None
    elapsed_ms: float
    breaches: tuple[Breach, ...]

    @property
    def ok(self) -> bool:
        """Whether this view stayed inside every budget."""
        return not self.breaches

    @property
    def headroom_bytes(self) -> int:
        """Bytes remaining before the server's cap, which is the number that matters."""
        return MAX_RESPONSE_BYTES - self.response_bytes

    def render(self) -> str:
        """One table row for the report."""
        worst = "-" if self.worst_row is None else str(self.worst_row.byte_count)
        return _SUMMARY_ROW.format(
            view=self.view,
            rows="?" if self.row_count is None else self.row_count,
            size=self.response_bytes,
            worst=worst,
            verdict="ok" if self.ok else "BREACH " + ", ".join(b.limit for b in self.breaches),
        )


@dataclass(frozen=True, slots=True)
class BudgetReport:
    """Every measurement, and whether the surface as a whole is inside budget."""

    measurements: tuple[ViewMeasurement, ...]
    byte_budget: int
    row_budget: int
    cluster_id: str

    @property
    def ok(self) -> bool:
        """True only when every measured view is inside every budget."""
        return all(m.ok for m in self.measurements)

    @property
    def breached(self) -> tuple[ViewMeasurement, ...]:
        """The measurements that breached, in contract order."""
        return tuple(m for m in self.measurements if not m.ok)

    @property
    def worst_view(self) -> ViewMeasurement | None:
        """The largest response measured, which is where headroom will run out first."""
        if not self.measurements:
            return None
        return max(self.measurements, key=lambda m: m.response_bytes)

    def render(self) -> str:
        """Render a fixed-width table plus one line per breach, for a CI step summary."""
        lines = [
            f"MCP audit-surface budget — cluster {self.cluster_id}",
            (
                f"budget: {self.byte_budget} bytes / {self.row_budget} rows "
                f"(server cap {MAX_RESPONSE_BYTES} bytes)"
            ),
            "",
            _HEADER_ROW,
            "-" * len(_HEADER_ROW),
        ]
        lines.extend(m.render() for m in self.measurements)
        worst = self.worst_view
        if worst is not None:
            lines.append("")
            lines.append(
                f"largest response: {worst.view} at {worst.response_bytes} bytes, "
                f"{worst.headroom_bytes} bytes of headroom below the server cap"
            )
        if self.breached:
            lines.append("")
            lines.append("BREACHES")
            for measurement in self.breached:
                for breach in measurement.breaches:
                    lines.append(f"  {measurement.view}: {breach.render()}")
        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """Return a serialisable form, so a nightly run can be diffed against the last one."""
        return {
            "cluster_id": self.cluster_id,
            "byte_budget": self.byte_budget,
            "row_budget": self.row_budget,
            "server_cap_bytes": MAX_RESPONSE_BYTES,
            "ok": self.ok,
            "views": [
                {
                    "view": m.view,
                    "statement": m.statement,
                    "response_bytes": m.response_bytes,
                    "row_count": m.row_count,
                    "headroom_bytes": m.headroom_bytes,
                    "elapsed_ms": round(m.elapsed_ms, 3),
                    "truncation_flag": m.truncation_flag,
                    "truncation_flag_present": m.truncation_flag_present,
                    "incomplete_rows": m.incomplete_rows,
                    "worst_row": (
                        None
                        if m.worst_row is None
                        else {
                            "index": m.worst_row.index,
                            "bytes": m.worst_row.byte_count,
                            "key": m.worst_row.key,
                        }
                    ),
                    "breaches": [
                        {
                            "limit": b.limit,
                            "budget": b.budget,
                            "observed": b.observed,
                            "detail": b.detail,
                        }
                        for b in m.breaches
                    ],
                }
                for m in self.measurements
            ],
        }


def _worst_row(rows: Sequence[Mapping[str, Any]]) -> WorstRow | None:
    """Return the largest row in ``rows``, or ``None`` when there are none."""
    if not rows:
        return None
    index, row = max(enumerate(rows), key=lambda pair: row_bytes(pair[1]))
    return WorstRow(index=index, byte_count=row_bytes(row), key=row_key(row))


def _count_incomplete(rows: Sequence[Mapping[str, Any]], flag: str) -> int:
    """Count rows whose completeness flag is false — a truncated ancestry, surfaced."""
    return sum(1 for row in rows if row.get(flag) is False)


class BudgetProber:
    """Measures every contracted view over the live endpoint and reports the numbers."""

    def __init__(
        self,
        client: Client,
        catalogue: Catalogue,
        *,
        byte_budget: int = BUDGET_RESPONSE_BYTES,
        row_budget: int = BUDGET_ROWS,
    ) -> None:
        """Bind a client and a catalogue; nothing is measured until :meth:`run`."""
        self._client = client
        self._catalogue = catalogue
        self._byte_budget = byte_budget
        self._row_budget = row_budget

    def measure(self, view: ViewSpec) -> ViewMeasurement:
        """Issue one view's statement and measure what came back."""
        budget_bytes = min(view.byte_budget, self._byte_budget)
        budget_rows = min(view.row_cap, self._row_budget)
        breaches: list[Breach] = []
        try:
            # The cap check is disabled here on purpose: the prober's job is to MEASURE
            # an oversized response, not to be stopped by it. A response at the cap is
            # recorded as a `response_cap` breach two blocks below.
            result = self._client.select_query(
                view.statement,
                max_rows=view.row_cap,
                enforce_cap=False,
            )
        except ResponseTooLarge as exc:
            observed = exc.observed if isinstance(exc.observed, int) else MAX_RESPONSE_BYTES
            return ViewMeasurement(
                view=view.name,
                statement=view.statement,
                response_bytes=observed,
                row_count=None,
                worst_row=None,
                truncation_flag=view.truncation_flag,
                truncation_flag_present=False,
                incomplete_rows=None,
                elapsed_ms=self._client.last_elapsed_ms,
                breaches=(
                    Breach(
                        limit="response_cap",
                        budget=MAX_RESPONSE_BYTES,
                        observed=observed,
                        detail="response reached the server cap and may be a truncation",
                    ),
                ),
            )
        except McpClientError as exc:
            return ViewMeasurement(
                view=view.name,
                statement=view.statement,
                response_bytes=0,
                row_count=None,
                worst_row=None,
                truncation_flag=view.truncation_flag,
                truncation_flag_present=False,
                incomplete_rows=None,
                elapsed_ms=self._client.last_elapsed_ms,
                breaches=(
                    Breach(
                        limit="tool_error",
                        budget=None,
                        observed=None,
                        detail=f"{type(exc).__name__}: {exc}",
                    ),
                ),
            )

        elapsed = self._client.last_elapsed_ms
        rows = result.rows
        response_bytes = result.byte_count

        if result.is_error:
            breaches.append(
                Breach(
                    limit="tool_error",
                    budget=None,
                    observed=None,
                    detail=f"server returned an error result: {result.text[:200]}",
                )
            )
        if response_bytes >= MAX_RESPONSE_BYTES:
            breaches.append(
                Breach(
                    limit="response_cap",
                    budget=MAX_RESPONSE_BYTES,
                    observed=response_bytes,
                    detail="response reached the server cap and may be a truncation",
                )
            )
        elif response_bytes > budget_bytes:
            breaches.append(
                Breach(
                    limit="byte_budget",
                    budget=budget_bytes,
                    observed=response_bytes,
                    detail="aggregate further, or the view will truncate as the corpus grows",
                )
            )

        worst: WorstRow | None = None
        flag_present = False
        incomplete: int | None = None
        if rows is None:
            breaches.append(
                Breach(
                    limit="row_count_undetermined",
                    budget=budget_rows,
                    observed=None,
                    detail=(
                        "rows could not be recovered from the response envelope; a view "
                        "whose row count cannot be measured has not been verified"
                    ),
                )
            )
        else:
            worst = _worst_row(rows)
            if len(rows) > budget_rows:
                breaches.append(
                    Breach(
                        limit="row_budget",
                        budget=budget_rows,
                        observed=len(rows),
                        detail="an audit view is aggregate-first; this one is returning detail",
                    )
                )
            if view.truncation_flag is not None:
                flag_present = all(view.truncation_flag in row for row in rows) if rows else True
                if not flag_present:
                    breaches.append(
                        Breach(
                            limit="truncation_flag_missing",
                            budget=None,
                            observed=None,
                            detail=(
                                f"the contract says this view carries {view.truncation_flag!r}; "
                                "a reader cannot tell a complete answer from a truncated one "
                                "without it"
                            ),
                        )
                    )
                else:
                    incomplete = _count_incomplete(rows, view.truncation_flag)

        return ViewMeasurement(
            view=view.name,
            statement=view.statement,
            response_bytes=response_bytes,
            row_count=None if rows is None else len(rows),
            worst_row=worst,
            truncation_flag=view.truncation_flag,
            truncation_flag_present=flag_present,
            incomplete_rows=incomplete,
            elapsed_ms=elapsed,
            breaches=tuple(breaches),
        )

    def run(self) -> BudgetReport:
        """Measure every contracted view and return the report."""
        return BudgetReport(
            measurements=tuple(self.measure(view) for view in self._catalogue.views),
            byte_budget=self._byte_budget,
            row_budget=self._row_budget,
            cluster_id=self._client.cluster_id,
        )
