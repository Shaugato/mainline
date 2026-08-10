# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The release tree: properties of the repository as a stranger will clone it.

Everything under ``tests/release/`` asserts something about the repository itself — that no
two test modules claim one import name, that the ratchets have not slipped, that the gate
refusal was actually produced. Several workers write here, so this conftest does the least
it can: it registers the marker and locates the clone. It does not decide anything on
another module's behalf.

The ``release`` marker is applied automatically rather than written on each test, because a
marker that has to be remembered is a marker that will be forgotten by the file that most
needed it. ``pytest -m release`` then runs exactly this tree from anywhere in the repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "release: a property of the repository as cloned, checked before a tag is cut",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every item collected from this directory ``release``."""
    for item in items:
        path = getattr(item, "path", None)
        if path is None:
            continue
        try:
            resolved = Path(str(path)).resolve()
        except OSError:  # pragma: no cover - a path that cannot be resolved is not ours
            continue
        if resolved.parent == HERE or HERE in resolved.parents:
            item.add_marker(pytest.mark.release)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The clone's root, found by the two files that identify it rather than by counting ``..``.

    ``Path(__file__).parents[2]`` is the same answer until someone moves this file, at which
    point it is silently the wrong answer. Marker files fail loudly instead.
    """
    for parent in [HERE, *HERE.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "compose.yaml").is_file():
            return parent
    raise RuntimeError(f"cannot locate the repository root above {HERE}")
