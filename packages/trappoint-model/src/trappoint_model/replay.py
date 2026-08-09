# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Replaying a recorded counterexample, deterministically, forever.

**Why this exists, and it is a correction to the obvious design.** Hypothesis's
``DirectoryBasedExampleDatabase`` is a *cache of currently-failing examples*: the moment a
counterexample stops reproducing — which is the moment you fix the bug — Hypothesis
deletes the entry. Committing that directory therefore preserves nothing about the bugs
you have already fixed, which is precisely the set an assurance case cares about. Measured
directly: three shrunk counterexamples were in ``.hypothesis-corpus/`` while the model was
wrong, and the directory was empty on the first green run.

So the corpus has two halves and they do different jobs:

``.hypothesis-corpus/<hash>/``
    Hypothesis's own, live, self-pruning. It replays the currently-failing example first
    and it is uploaded as a CI artefact. It is *not* the regression record.

``.hypothesis-corpus/counterexamples.jsonl``
    The regression record. One JSON object per line, each a shrunk history with the
    verdict every step is expected to produce. This module replays them against the
    oracle, and against a cluster when one is reachable — deterministically, with no
    generation, so a fixed bug stays fixed and a reader can see the history that found
    it without running anything.

The expectation is written down per step rather than left as "model and cluster agree",
and that is deliberately stronger than the differential: two implementations that made the
same mistake would agree, and a recorded verdict catches them.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapter import Adapter
from .model import Accept, Model, Refuse, Verdict

__all__ = ["CORPUS_FILE", "Counterexample", "Step", "load_corpus", "replay"]

#: The committed regression record. Beside Hypothesis's own directory, not inside it.
CORPUS_FILE = Path(__file__).resolve().parents[4] / ".hypothesis-corpus" / "counterexamples.jsonl"

#: A recorded refusal is ``[sqlstate, constraint]`` and nothing else. Named because the
#: pair IS the verdict: a one-element form would record a code without its exhibit.
_REFUSAL_FIELDS = 2

_OPS = frozenset(
    {
        "create_subject",
        "fork_child",
        "materialise_check",
        "sign_disposition",
        "expire_override",
        "retract",
        "attempt_merge",
        "suspend",
    }
)


@dataclass(frozen=True, slots=True)
class Step:
    """One operation of a recorded history, with the verdict it must produce.

    Handles are small integers rather than UUIDs so a recorded history is readable and
    stable: ``{"op": "retract", "disposition": 2, "by": 1}`` says what happened, and a
    file full of UUIDs would not.
    """

    op: str
    args: dict[str, int]
    expect: Verdict

    @staticmethod
    def from_json(raw: dict[str, Any]) -> Step:
        """Parse one recorded step.

        Raises:
            ValueError: the operation is not one of the eight, or the expectation is
                malformed. A corpus entry that cannot be parsed is a corpus entry that
                silently stops asserting, so it fails loudly instead.
        """
        op = raw["op"]
        if op not in _OPS:
            raise ValueError(f"{op!r} is not one of the eight operations: {sorted(_OPS)}")
        expectation = raw["expect"]
        if expectation == "accept":
            expect: Verdict = Accept()
        elif isinstance(expectation, list) and len(expectation) == _REFUSAL_FIELDS:
            expect = Refuse(str(expectation[0]), str(expectation[1]))
        else:
            raise ValueError(
                f"expectation {expectation!r} must be 'accept' or [sqlstate, constraint]"
            )
        args = {k: int(v) for k, v in raw.items() if k not in {"op", "expect"}}
        return Step(op=op, args=args, expect=expect)


@dataclass(frozen=True, slots=True)
class Counterexample:
    """One recorded history: what it found, when, and the exact steps."""

    id: str
    summary: str
    found: str
    diagnosis: str
    steps: tuple[Step, ...]

    @staticmethod
    def from_json(raw: dict[str, Any]) -> Counterexample:
        """Parse one line of the corpus file."""
        return Counterexample(
            id=str(raw["id"]),
            summary=str(raw["summary"]),
            found=str(raw["found"]),
            diagnosis=str(raw["diagnosis"]),
            steps=tuple(Step.from_json(step) for step in raw["steps"]),
        )


def load_corpus(path: Path = CORPUS_FILE) -> list[Counterexample]:
    """Read every recorded counterexample.

    Raises:
        FileNotFoundError: the corpus file is missing. Not skipped: an assurance artefact
            that can vanish without failing anything is not an assurance artefact.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"the counterexample corpus is not at {path}. It is committed to git on "
            "purpose; a missing corpus is a deleted regression suite, not an empty one."
        )
    entries = [
        Counterexample.from_json(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("//")
    ]
    seen = [entry.id for entry in entries]
    if len(set(seen)) != len(seen):
        raise ValueError(f"duplicate counterexample ids in {path}: {sorted(seen)}")
    return entries


class _Handles:
    """Small integers to UUIDs, allocated on first use and stable within one replay."""

    def __init__(self) -> None:
        self._by_kind: dict[str, dict[int, uuid.UUID]] = {}

    def get(self, kind: str, index: int) -> uuid.UUID:
        """Return the UUID for ``(kind, index)``, minting one the first time."""
        return self._by_kind.setdefault(kind, {}).setdefault(index, uuid.uuid4())


def _dispatch(  # noqa: PLR0911 - one return per operation; a dict of bound methods
    target: Model | Adapter,  # would hide the eight names this module exists to map
    handles: _Handles,
    step: Step,
    *,
    is_model: bool,
) -> Verdict:
    def h(kind: str, index: int) -> Any:
        value = handles.get(kind, index)
        return str(value) if is_model else value

    a = step.args
    if step.op == "create_subject":
        return target.create_subject(h("subject", a["subject"]))
    if step.op == "fork_child":
        return target.create_subject(h("subject", a["subject"]), h("subject", a["parent"]))
    if step.op == "materialise_check":
        return target.materialise_check(h("subject", a["subject"]), h("check", a["check"]))
    if step.op == "sign_disposition":
        return target.sign_disposition(h("check", a["check"]), h("disposition", a["disposition"]))
    if step.op == "expire_override":
        return target.sign_disposition(
            h("check", a["check"]), h("disposition", a["disposition"]), expired=True
        )
    if step.op == "retract":
        return target.retract(h("disposition", a["disposition"]), h("disposition", a["by"]))
    if step.op == "attempt_merge":
        return target.attempt_merge(h("subject", a["subject"]))
    return target.suspend(h("subject", a["subject"]))


def replay(
    entry: Counterexample, *, model: Model | None = None, adapter: Adapter | None = None
) -> Iterator[tuple[Step, Verdict, Verdict | None]]:
    """Replay *entry*, yielding ``(step, model_verdict, adapter_verdict)`` per step.

    Both sides share one handle allocator, so step *n* addresses the same logical subject
    in the oracle and on the cluster. The caller does the asserting: this function reports
    and never judges, so a failure message can name the step, the expectation and both
    answers at once.

    Args:
        entry: the recorded history.
        model: the oracle. A fresh :class:`~trappoint_model.model.Model` when omitted.
        adapter: the cluster side. ``None`` replays against the oracle alone, which is
            what happens when no cluster is reachable — weaker, and the caller says so.
    """
    oracle = model if model is not None else Model()
    handles = _Handles()
    for step in entry.steps:
        want = _dispatch(oracle, handles, step, is_model=True)
        got = _dispatch(adapter, handles, step, is_model=False) if adapter is not None else None
        yield (step, want, got)
