# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CockroachDB platform facts the runner depends on, in one place.

Everything here is a statement about the *platform*, not about our schema, and each one
has a citation or an honest note that it is unverified. Two of them are load-bearing:

* **There are no advisory locks.** ``trappoint.schema_lock`` is a real table with a
  real lease because ``pg_advisory_lock`` does not exist. This is the single fact that
  makes the runner's lock code look heavier than a PostgreSQL migrator's.
* **A DDL statement is a background job.** The statement returns before the schema
  change finishes, so the version may not advance until ``SHOW JOBS`` reaches terminal
  success (research/06-build/schema-migrations.md §2.2).
"""

from __future__ import annotations

import re
from pathlib import Path

from .errors import UsageError

__all__ = [
    "SCHEMA_CHANGE_JOB_TYPES",
    "TERMINAL_FAILURE_STATUSES",
    "TERMINAL_SUCCESS_STATUSES",
    "pinned_image",
]

# `SHOW JOBS` job types that a DDL statement can produce. Both spellings are polled:
# CockroachDB has carried the legacy declarative and the new declarative schema changer
# side by side, and which one a given statement uses is not something a migration
# runner should have to predict.
SCHEMA_CHANGE_JOB_TYPES: tuple[str, ...] = ("SCHEMA CHANGE", "NEW SCHEMA CHANGE")

# Terminal states. Anything not in either set is still running and is polled again.
TERMINAL_SUCCESS_STATUSES: frozenset[str] = frozenset({"succeeded"})
TERMINAL_FAILURE_STATUSES: frozenset[str] = frozenset(
    {"failed", "canceled", "cancelled", "revert-failed", "reverting"}
)

# `reverting` is listed as a FAILURE rather than as in-flight on purpose. A job that has
# begun reverting has already decided it is not going to succeed, and a runner that
# waits politely for it to finish reverting has waited to be told something it already
# knows. The version does not advance either way.

_IMAGE_PIN_MARKER = "trappoint:crdb-image-pin"
_IMAGE_LINE = re.compile(r"^\s*image:\s*(?P<image>\S+)\s*$")


def pinned_image(compose_path: Path) -> str:
    """Return the CockroachDB image pinned in *compose_path*.

    The version constant lives in ``compose.yaml`` and nowhere else, so ``just``, the CI
    workflows and this runner cannot disagree about which cluster the proof ran against.
    The line is found by the ``trappoint:crdb-image-pin`` marker comment immediately
    above it rather than by parsing YAML, which keeps this package free of a YAML
    dependency it would otherwise need for one string.

    Raises:
        UsageError: if the file is missing or carries no marked image line.
    """
    if not compose_path.is_file():
        raise UsageError(
            f"no compose file at {compose_path}: the CockroachDB version constant lives "
            "there and this command has nothing to read"
        )
    lines = compose_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if _IMAGE_PIN_MARKER not in line:
            continue
        for candidate in lines[index + 1 : index + 4]:
            match = _IMAGE_LINE.match(candidate)
            if match is not None:
                return match.group("image")
    raise UsageError(
        f"{compose_path} carries no line marked '{_IMAGE_PIN_MARKER}' followed by an "
        "'image:' key; the version constant has moved or been deleted"
    )
