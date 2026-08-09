# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CU-7: no default path opens a socket — asserted in about 200 ms, not promised.

*"Requires no cooperation from us"* is the sentence the custody domain exists to make
true. A README cannot make it true. This file does: it replaces ``socket.socket``,
``socket.create_connection`` and ``socket.getaddrinfo`` with functions that raise, proves
the replacement bites, and then runs the **entire** check suite and the CLI end to end.

If any check ever reaches for the network on a default path, these tests stop being green.

The bundle under test is ``evidence/reference-ledger/bundle.json`` when the committed
reference ledger is present, and otherwise the frozen spec vectors from
``spec/wire/checkpoint.md`` §7 and ``spec/wire/receipt.md`` §5, assembled by
``test_structural_checks``. Which one was used is **printed**, because a test that
silently falls back to a weaker fixture is a test that stops meaning what its name says.
"""

from __future__ import annotations

import io
import json
import socket
import sys
from pathlib import Path

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_PACKAGE_ROOT / "src", _PACKAGE_ROOT / "tests"):
    if str(_entry) not in sys.path:  # pragma: no cover - import bootstrap
        sys.path.insert(0, str(_entry))

from test_structural_checks import spec_bundle_dict  # noqa: E402

from trappoint_verify import cli  # noqa: E402
from trappoint_verify.bundle import load_bundle  # noqa: E402
from trappoint_verify.checks import VerifyOptions, load_all, run_all  # noqa: E402
from trappoint_verify.report import EXIT_NOT_CHECKED, EXIT_OK, Verdict  # noqa: E402


class NetworkReached(RuntimeError):
    """Raised instead of opening a socket. Its traceback names the offender."""


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every socket-creating entry point raise, and prove that it does."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise NetworkReached(
            "trappoint-verify reached for the network on a default path. CU-7 says every "
            "online capability is opt-in behind --s3, --kms-pubkey or --tile-url."
        )

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    with pytest.raises(NetworkReached):
        socket.socket()


def _reference_bundle_path() -> Path | None:
    for candidate in [_PACKAGE_ROOT, *_PACKAGE_ROOT.parents]:
        bundle = candidate / "evidence" / "reference-ledger" / "bundle.json"
        if bundle.is_file():
            return bundle
    return None


@pytest.fixture
def bundle_path(tmp_path: Path) -> Path:
    """The committed reference bundle if it exists; the frozen spec vectors otherwise."""
    committed = _reference_bundle_path()
    if committed is not None:
        print(f"fixture: evidence/reference-ledger/bundle.json ({committed})")
        return committed
    written = tmp_path / "bundle.json"
    written.write_text(json.dumps(spec_bundle_dict(), indent=2), encoding="utf-8")
    print(
        "fixture: the frozen spec vectors (spec/wire/checkpoint.md §7, receipt.md §5). "
        "evidence/reference-ledger/bundle.json is not present in this checkout."
    )
    return written


@pytest.mark.usefixtures("no_network")
def test_the_full_check_suite_runs_with_every_socket_poisoned(bundle_path: Path):
    """Every registered check, over a real bundle, with the network physically unavailable."""
    load_all()
    bundle = load_bundle(bundle_path)
    report = run_all(bundle, VerifyOptions(), tool_version="test")
    assert report.outcomes, "the run produced no outcomes at all"
    raised = [o for o in report.outcomes if o.code == "check-raised"]
    assert not raised, [(o.check_id, o.detail) for o in raised]
    failures = [(o.check_id, o.code, o.headline) for o in report.failures]
    assert not failures, failures


@pytest.mark.usefixtures("no_network")
def test_the_cli_verifies_offline_and_reports_its_skips_loudly(bundle_path: Path):
    """The whole command, end to end, with no socket available to it."""
    stream = io.StringIO()
    code = cli.main(["verify", "--bundle", str(bundle_path), "--colour", "never"], stream=stream)
    text = stream.getvalue()
    assert code in (EXIT_OK, EXIT_NOT_CHECKED), text
    assert "this bundle records the preconditions" in text
    if code == EXIT_NOT_CHECKED:
        assert "NOT CHECKED" in text
        assert "A skipped check proves nothing" in text
    else:  # pragma: no cover - reachable only once every check module has landed
        assert "NOT CHECKED" not in text


@pytest.mark.usefixtures("no_network")
def test_receipt_audit_runs_offline_and_announces_that_it_is_a_selection(bundle_path: Path):
    """A narrowed run says so at the top; a quiet subset is how a report overstates itself."""
    stream = io.StringIO()
    code = cli.main(
        ["receipt-audit", "--bundle", str(bundle_path), "--colour", "never"], stream=stream
    )
    text = stream.getvalue()
    assert "SELECTED RUN" in text
    assert code in (EXIT_OK, EXIT_NOT_CHECKED), text


@pytest.mark.usefixtures("no_network")
def test_two_runs_produce_byte_identical_output(bundle_path: Path):
    """evidence-bundle.md §15.6. A process with no 'ordinarily' has no presumption to claim."""
    outputs = []
    for _ in range(2):
        stream = io.StringIO()
        cli.main(["verify", "--bundle", str(bundle_path), "--json"], stream=stream)
        outputs.append(stream.getvalue())
    assert outputs[0] == outputs[1]


@pytest.mark.usefixtures("no_network")
def test_explain_check_needs_no_bundle_and_no_network():
    """``explain-check`` is the command a stranger runs first, before they have anything."""
    stream = io.StringIO()
    assert cli.main(["explain-check", "14"], stream=stream) == EXIT_OK
    text = stream.getvalue()
    assert "closure_generation_monotone" in text
    assert "mass closure rewrite" in text


@pytest.mark.usefixtures("no_network")
def test_a_malformed_bundle_is_a_finding_about_the_file_not_about_the_log(tmp_path: Path):
    """Exit 3 is its own code so that 'your file is broken' never reads as 'your log is'."""
    broken = tmp_path / "broken.json"
    broken.write_text('{"bundle_version": 1}', encoding="utf-8")
    stream = io.StringIO()
    code = cli.main(["verify", "--bundle", str(broken)], stream=stream)
    assert code == 3
    assert "No check ran, so no check passed." in stream.getvalue()


class _NarrowStream:
    """A stdout that cannot encode this report — a Windows console at cp1252.

    Modelled rather than mocked: the real failure is ``codecs.charmap_encode`` raising
    from inside ``write``, which is what this reproduces.
    """

    encoding = "cp1252"

    def __init__(self) -> None:
        self.text: list[str] = []

    def write(self, text: str) -> int:
        text.encode(self.encoding)  # raises UnicodeEncodeError, exactly as a console does
        self.text.append(text)
        return len(text)

    def isatty(self) -> bool:
        return False


@pytest.mark.usefixtures("no_network")
def test_the_report_survives_a_console_that_cannot_encode_it(bundle_path: Path):
    """A verifier that dies of an encoding error has refused to report its findings."""
    stream = _NarrowStream()
    code = cli.main(["verify", "--bundle", str(bundle_path), "--colour", "never"], stream=stream)
    text = "".join(stream.text)
    assert code in (EXIT_OK, EXIT_NOT_CHECKED)
    assert "this bundle records the preconditions" in text
    # Everything that reached the stream is representable in the stream's own encoding —
    # which is what "it did not raise" has to mean for this to be a real assertion.
    text.encode(stream.encoding)


@pytest.mark.usefixtures("no_network")
def test_a_skip_can_never_be_read_as_a_pass(bundle_path: Path):
    """Every SKIP in a real run carries a reason, and the reason reaches the banner."""
    load_all()
    report = run_all(load_bundle(bundle_path), VerifyOptions(), tool_version="test")
    rendered = report.render(colour=False)
    for outcome in report.outcomes:
        if outcome.verdict is Verdict.SKIP:
            assert outcome.reason
            assert outcome.reason in rendered
    if report.skips:
        assert report.exit_code == EXIT_NOT_CHECKED
