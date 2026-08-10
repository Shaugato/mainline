# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The CockroachDB image pin, read from ``compose.yaml`` and exported under every spelling.

``compose.yaml`` says of itself: *THE VERSION CONSTANT LIVES HERE AND ONLY HERE.* Measured
on 2026-08-10 that was not true of the test suite — **33 Python files defaulted to the
FLOATING tag ``cockroachdb/cockroach:latest-v26.2`` against 10 using the pinned
``v26.2.5``**. A floating tag is precisely the dev/CI version skew the schema fingerprint
exists to catch, introduced by the harness that is supposed to prevent it.

Every one of those files spells the default the same way::

    CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:latest-v26.2")

so the environment variable is the seam: export it and the hard-coded default is never
reached, and not one of those files has to be edited. Three spellings are in use across the
tree (``CRDB_IMAGE``, ``MAINLINE_CRDB_IMAGE``, ``TRAPPOINT_CRDB_IMAGE``), so all three are
exported to the same value.

The marker comment is parsed rather than the YAML, so this package needs no YAML dependency
for one string — the same decision, and the same regex, as
``trappoint_migrate.crdb.pinned_image``. The duplication is deliberate: this package must be
installable and usable on its own, and a testkit that cannot start until the migration
runner imports cleanly is a testkit that cannot help diagnose a migration runner that does
not import cleanly.
"""

from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path

__all__ = [
    "COMPOSE_FILENAMES",
    "IMAGE_ENV_NAMES",
    "IMAGE_PIN_MARKER",
    "PinNotFound",
    "export_pin",
    "find_compose",
    "pinned_image",
    "read_pin",
]

#: The comment that marks the one line carrying the version constant.
IMAGE_PIN_MARKER = "trappoint:crdb-image-pin"

#: Every spelling a fixture in this repository reads the image from. All are set to one value.
IMAGE_ENV_NAMES: tuple[str, ...] = (
    "CRDB_IMAGE",
    "MAINLINE_CRDB_IMAGE",
    "TRAPPOINT_CRDB_IMAGE",
)

#: Searched in this order, so a repository that renames the file keeps working.
COMPOSE_FILENAMES: tuple[str, ...] = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)

_IMAGE_LINE = re.compile(r"^\s*image:\s*(?P<image>\S+)\s*$")

#: How far below the marker the ``image:`` key may sit. Three lines allows a blank line and
#: one comment between them without allowing the marker to bind to an unrelated service.
_LOOKAHEAD = 3


class PinNotFound(RuntimeError):
    """No compose file, or a compose file with no marked ``image:`` line.

    Raised rather than defaulted: a testkit that invents a version when it cannot read one
    reintroduces exactly the skew this module exists to remove.
    """


def find_compose(start: Path | None = None) -> Path | None:
    """Return the nearest compose file at or above *start*, or ``None``.

    Args:
        start: directory to begin the upward walk. Defaults to the current directory.
    """
    origin = (start or Path.cwd()).resolve()
    if origin.is_file():
        origin = origin.parent
    for directory in [origin, *origin.parents]:
        for name in COMPOSE_FILENAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def read_pin(compose_path: Path) -> str:
    """Return the image pinned in *compose_path*.

    Raises:
        PinNotFound: the file is missing, or carries no marked ``image:`` line.
    """
    if not compose_path.is_file():
        raise PinNotFound(
            f"no compose file at {compose_path}: the CockroachDB version constant lives "
            "there and this module has nothing to read"
        )
    lines = compose_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if IMAGE_PIN_MARKER not in line:
            continue
        for candidate in lines[index + 1 : index + 1 + _LOOKAHEAD]:
            match = _IMAGE_LINE.match(candidate)
            if match is not None:
                return match.group("image")
    raise PinNotFound(
        f"{compose_path} carries no line marked '{IMAGE_PIN_MARKER}' followed within "
        f"{_LOOKAHEAD} lines by an 'image:' key; the version constant has moved or been "
        "deleted"
    )


def pinned_image(start: Path | None = None) -> str:
    """Return the pinned image, found by walking up from *start*.

    Raises:
        PinNotFound: no compose file above *start*, or no marked line in it.
    """
    compose_path = find_compose(start)
    if compose_path is None:
        raise PinNotFound(
            "no compose.yaml at or above "
            f"{(start or Path.cwd()).resolve()}: cannot read the CockroachDB version "
            "constant, and this module will not invent one"
        )
    return read_pin(compose_path)


def export_pin(
    env: MutableMapping[str, str] | None = None,
    *,
    pin: str | None = None,
    start: Path | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Publish the pin under every spelling; report the value and which names it claimed.

    An operator who has already exported one of these names keeps it — an explicit
    environment variable is a deliberate act and outranks a file. What the pin displaces is
    the *hard-coded default* inside each fixture, which is not a deliberate act by anyone
    still on the project.

    Args:
        env: the mapping to write into. Defaults to :data:`os.environ`.
        pin: the image to publish. Defaults to reading it from the compose file.
        start: where to begin the upward walk for the compose file.

    Returns:
        ``(pin, names_set)`` — the value in force, and the names this call actually wrote.
        A name already present in *env* is not in *names_set*.

    Raises:
        PinNotFound: *pin* was not given and no compose file could be read.
    """
    target = os.environ if env is None else env
    value = pin if pin is not None else pinned_image(start)
    claimed: list[str] = []
    for name in IMAGE_ENV_NAMES:
        if not target.get(name):
            target[name] = value
            claimed.append(name)
    return value, tuple(claimed)
