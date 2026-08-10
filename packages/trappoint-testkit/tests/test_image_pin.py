# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The version constant is one constant, and it is not floating.

``compose.yaml`` says of itself that the version constant lives there and only there. On
2026-08-10 that was false of the test suite: **33 Python files defaulted to
``cockroachdb/cockroach:latest-v26.2``, a FLOATING tag, against 10 using the pinned
``v26.2.5``**. A floating tag is exactly the dev/CI version skew that the schema fingerprint
exists to catch, introduced by the harness that is supposed to prevent it.

The first test in this module is the one that matters: it fails the day the marked line in
``compose.yaml`` stops naming an exact patch version.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from trappoint_testkit import image

HERE = Path(__file__).resolve().parent

#: `repo:name:vMAJOR.MINOR.PATCH`. `latest-v26.2` does not match, and that is the whole point.
EXACT_VERSION = re.compile(r"^[\w./-]+:v\d+\.\d+\.\d+$")


def test_the_repository_pin_is_an_exact_patch_version_not_a_floating_tag() -> None:
    compose = image.find_compose(HERE)
    assert compose is not None, "no compose.yaml at or above the testkit's tests"
    pin = image.read_pin(compose)
    assert EXACT_VERSION.match(pin), (
        f"{compose} pins {pin!r}, which is not an exact patch version. A floating tag such as "
        "`latest-v26.2` means the cluster CI proved a fingerprint against and the cluster a "
        "laptop runs are not knowably the same build."
    )


def test_the_pin_is_found_by_walking_up_from_anywhere_inside_the_repository() -> None:
    """`pinned_image` must not depend on the caller's working directory."""
    from_tests = image.pinned_image(HERE)
    from_src = image.pinned_image(HERE.parent / "src" / "trappoint_testkit")
    assert from_tests == from_src


def test_export_publishes_one_value_under_every_spelling_a_fixture_reads() -> None:
    env: dict[str, str] = {}
    value, claimed = image.export_pin(env, pin="cockroachdb/cockroach:v26.2.5")
    assert value == "cockroachdb/cockroach:v26.2.5"
    assert claimed == image.IMAGE_ENV_NAMES
    assert set(env) == set(image.IMAGE_ENV_NAMES)
    assert len(set(env.values())) == 1, "the three spellings must not be allowed to disagree"


def test_export_does_not_overrule_a_variable_an_operator_already_set() -> None:
    """An explicit environment variable is a deliberate act; a hard-coded default is not."""
    env = {"MAINLINE_CRDB_IMAGE": "cockroachdb/cockroach:v26.1.9"}
    value, claimed = image.export_pin(env, pin="cockroachdb/cockroach:v26.2.5")
    assert value == "cockroachdb/cockroach:v26.2.5"
    assert env["MAINLINE_CRDB_IMAGE"] == "cockroachdb/cockroach:v26.1.9"
    assert "MAINLINE_CRDB_IMAGE" not in claimed
    assert env["CRDB_IMAGE"] == "cockroachdb/cockroach:v26.2.5"


def test_the_marker_binds_to_the_image_line_below_it_and_not_to_a_later_service(
    tmp_path: Path,
) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  other:\n"
        "    image: postgres:17\n"
        "  crdb:\n"
        "    # trappoint:crdb-image-pin\n"
        "    image: cockroachdb/cockroach:v26.2.5\n"
        "  later:\n"
        "    image: redis:7\n",
        encoding="utf-8",
    )
    assert image.read_pin(compose) == "cockroachdb/cockroach:v26.2.5"


def test_a_marker_too_far_above_the_image_line_is_refused_rather_than_guessed(
    tmp_path: Path,
) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  crdb:\n"
        "    # trappoint:crdb-image-pin\n"
        "    container_name: a\n"
        "    restart: 'no'\n"
        "    stop_grace_period: 60s\n"
        "    image: cockroachdb/cockroach:v26.2.5\n",
        encoding="utf-8",
    )
    with pytest.raises(image.PinNotFound, match="crdb-image-pin"):
        image.read_pin(compose)


def test_a_compose_file_with_no_marker_raises_rather_than_defaulting(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  crdb:\n    image: cockroachdb/cockroach:v26.2.5\n", "utf-8")
    with pytest.raises(image.PinNotFound, match="carries no line marked"):
        image.read_pin(compose)


def test_a_missing_compose_file_raises_rather_than_defaulting(tmp_path: Path) -> None:
    with pytest.raises(image.PinNotFound, match="no compose file at"):
        image.read_pin(tmp_path / "nothing.yaml")


def test_find_compose_returns_none_above_the_filesystem_root_rather_than_looping(
    tmp_path: Path,
) -> None:
    """A directory with no compose file above it must answer, not search forever."""
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    # tmp_path is outside the repository, so the walk terminates at the drive root.
    assert image.find_compose(deep) is None
