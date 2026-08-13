# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``SEC-ACCOUNT-ID`` knows a byte count from an account id — and only by position.

On 2026-08-13 one literal was holding three jobs of the ``aws-evidence`` lane red:
``evidence/deploy/verify/aws-quota-and-cost.json`` records
``"AccountLimit.TotalCodeSize": 322122547200`` — Lambda's 300 GiB code-storage quota,
300 * 1024**3, twelve digits — because a live ``lambda get-account-settings`` returned it.
The third job was the expensive one: the mutation harness refuses to grade its planted
defects while an *unmutated* copy of ``evidence/`` already fails, so a single false
positive had switched off a whole anti-vacuity family.

**Neither of the two easy fixes was available.**  Editing the artefact would have forged a
measurement.  Allow-listing the literal would have been the mistake
``evidence/deploy/deploy-dry-run.json`` already names — *"a scanner carrying an exception
for one such literal would carry it for any."*  So the detector was taught the one thing
that actually separates the two: an account id is an **identifier** and lives in a JSON
string (or an ARN, or prose); a byte count is a **quantity** and is a bare JSON number.

Every test below exists to keep that distinction honest in both directions, and the pair
that matters most is :func:`test_the_quota_literal_in_prose_still_fires` against
:func:`test_the_quota_literal_as_a_json_number_does_not_fire`: the *same twelve digits*,
one reported and one not, which is only possible if the rule is about position and not
about the value.  If a later change swaps them for an allow-list, the first of those two
goes green-by-blindness and this file goes red.

Nothing here touches AWS, and every twelve-digit literal in this module is fabricated.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    # `tests/unit` carries no `__init__.py`, so pytest's prepend import mode puts
    # `tests/unit` on sys.path and not the repository root. `scripts` is a namespace
    # package; this is what makes `scripts.aws.verify_evidence` importable here.
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.aws.verify_evidence import (  # noqa: E402 - after the sys.path bootstrap above
    Verifier,
    _secret_plants,
)

#: Fabricated. Never an account this project has ever held.
FAKE_ACCOUNT = "123456789012"

#: The real recorded quantity, quoted here because the point of this module is that the
#: scanner treats it differently in two positions rather than tolerating it everywhere.
QUOTA_BYTES = 322122547200
QUOTA_FILE = "evidence/deploy/verify/aws-quota-and-cost.json"


def _scan(tmp_path: Path, files: dict[str, str]) -> Verifier:
    """Run ``check_secrets`` and nothing else over a throwaway evidence tree.

    Only the secret family is invoked: a two-file tree cannot satisfy the envelope,
    cross-reference, census or README families, and a test that had to tolerate their
    failures could not tell a real ``SEC-ACCOUNT-ID`` from noise.
    """
    evidence = tmp_path / "evidence"
    for name, body in files.items():
        target = evidence / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    verifier = Verifier(_REPO_ROOT, evidence)
    verifier.check_secrets()
    return verifier


def _account_findings(verifier: Verifier) -> list[str]:
    return [str(f) for f in verifier.result.failures if f.invariant == "SEC-ACCOUNT-ID"]


# ── it still bites ────────────────────────────────────────────────────────────────────


def test_an_account_id_quoted_as_a_json_string_fires(tmp_path: Path) -> None:
    """The shape STS itself returns: ``{"Account": "123456789012"}``."""
    verifier = _scan(tmp_path, {"probe.json": json.dumps({"caller": {"Account": FAKE_ACCOUNT}})})
    findings = _account_findings(verifier)
    assert findings, "a quoted account id in a JSON artefact was not reported"
    assert FAKE_ACCOUNT in findings[0]
    assert "probe.json:1" in findings[0], f"the finding must name the file and line: {findings[0]}"


def test_an_account_id_used_as_a_json_key_fires(tmp_path: Path) -> None:
    """A key is a string token too, so a per-account map is not a hiding place."""
    verifier = _scan(tmp_path, {"probe.json": json.dumps({FAKE_ACCOUNT: {"role": "deployer"}})})
    assert _account_findings(verifier), "an account id used as a JSON key was not reported"


def test_an_account_id_in_prose_fires(tmp_path: Path) -> None:
    """Markdown keeps the raw byte scan; nothing about the fix is suffix-blind."""
    body = "The apply ran in account 123456789012 and the plan was byte-identical.\n"
    verifier = _scan(tmp_path, {"notes.md": body})
    findings = _account_findings(verifier)
    assert findings, "an account id written in prose was not reported"
    assert "notes.md:1" in findings[0]


def test_an_account_id_in_a_json_file_that_does_not_parse_fires(tmp_path: Path) -> None:
    """A ``.json`` extension is a claim. When the claim fails, read every byte.

    Otherwise ``mv leak.txt leak.json`` would be a way to smuggle a leak past the scan.
    """
    body = '{"caller": ' + FAKE_ACCOUNT + "  <- truncated, not valid JSON\n"
    verifier = _scan(tmp_path, {"broken.json": body})
    assert _account_findings(verifier), "a .json file that does not parse must be scanned raw"


def test_a_bare_number_under_an_account_key_fires(tmp_path: Path) -> None:
    """The narrowed blind spot: unquoted digits whose own key claims to be an account."""
    verifier = _scan(tmp_path, {"probe.json": '{\n  "account_id": 123456789012\n}\n'})
    findings = _account_findings(verifier)
    assert findings, "twelve bare digits under 'account_id' were not reported"
    assert "account_id" in findings[0]
    assert "probe.json:2" in findings[0]


def test_the_quota_literal_in_prose_still_fires(tmp_path: Path) -> None:
    """The value is not exempt anywhere — only its position in JSON excuses it.

    This is the assertion that distinguishes the fix from an allow-list. If someone ever
    replaces the positional rule with ``if value == 322122547200: continue``, this test is
    the one that goes red.
    """
    verifier = _scan(tmp_path, {"notes.md": f"the ceiling was {QUOTA_BYTES} bytes\n"})
    assert _account_findings(verifier), (
        "322122547200 must still be reported in prose; if it is not, the detector is "
        "carrying an exception for a literal rather than reading a position"
    )


def test_the_quota_literal_quoted_in_json_still_fires(tmp_path: Path) -> None:
    """Same value, same file type, quoted — and therefore reported."""
    verifier = _scan(tmp_path, {"quota.json": json.dumps({"limit": str(QUOTA_BYTES)})})
    assert _account_findings(verifier), "a quoted 322122547200 must still be reported"


# ── and it stops biting the measurement ───────────────────────────────────────────────


def test_the_quota_literal_as_a_json_number_does_not_fire(tmp_path: Path) -> None:
    """The recorded measurement, in the shape AWS returned it."""
    body = json.dumps(
        {
            "measured_lambda_get_account_settings": {
                "ap-southeast-1": {
                    "AccountLimit.ConcurrentExecutions": 10,
                    "AccountLimit.TotalCodeSize": QUOTA_BYTES,
                }
            }
        },
        indent=2,
    )
    verifier = _scan(tmp_path, {"quota.json": body})
    assert _account_findings(verifier) == [], (
        "a bare JSON number under a byte-quantity key is a quantity, not an account id"
    )


def test_a_key_that_merely_contains_the_word_account_is_not_an_account_key(
    tmp_path: Path,
) -> None:
    """``AccountLimit.TotalCodeSize`` contains "Account" and is not an account key.

    The keyed-number rule matches the whole normalised key, never a substring. A substring
    test would have re-created the exact false positive this module exists to remove.
    """
    verifier = _scan(tmp_path, {"quota.json": '{"AccountLimit.TotalCodeSize": 322122547200}'})
    assert _account_findings(verifier) == []


def test_an_account_id_written_with_json_escapes_fires(tmp_path: Path) -> None:
    """An id spelled ``\\u0031\\u0032…`` is an id to every reader of the artefact.

    Its bytes contain no run of twelve digits at all, so neither the raw-byte rule that
    shipped before this fix nor a span-restricted raw scan could see it. The scanner reads
    each string token decoded, which is why this is reported — and why the positional fix
    is strictly more sensitive than the rule it replaced rather than a relaxation of it.
    """
    escaped = "".join(f"\\u003{d}" for d in "123456789012")
    body = '{"caller": "' + escaped + '"}'
    assert FAKE_ACCOUNT not in body, "the fixture must not contain the id in plain digits"
    assert json.loads(body)["caller"] == FAKE_ACCOUNT, "the fixture must decode to the id"
    assert _account_findings(_scan(tmp_path, {"probe.json": body})), (
        "an account id hidden behind JSON escapes was not reported"
    )


def test_escaped_quotes_do_not_desynchronise_the_string_scanner(tmp_path: Path) -> None:
    """The tokeniser is the whole fix, so its one hard case is asserted directly.

    A ``\\"`` inside a string does not close it. If the scanner thought otherwise, every
    span after that point would be inverted — quantities would start reading as identifiers
    and, far worse, identifiers as quantities.
    """
    body = json.dumps(
        {
            "quoted": 'he said "no" twice',
            "leak": FAKE_ACCOUNT,
            "AccountLimit.TotalCodeSize": QUOTA_BYTES,
        },
        indent=2,
    )
    assert '\\"' in body, "the fixture must actually contain an escaped quote"
    findings = _account_findings(_scan(tmp_path, {"probe.json": body}))
    assert len(findings) == 1, f"expected exactly the quoted id, got {findings}"
    assert FAKE_ACCOUNT in findings[0]


# ── and it is not vacuous ─────────────────────────────────────────────────────────────


def test_the_scan_counts_every_file_it_looked_at(tmp_path: Path) -> None:
    """A scanner that reports nothing because it read nothing is not a clean scan."""
    verifier = _scan(
        tmp_path,
        {"quota.json": json.dumps({"bytes": QUOTA_BYTES}), "notes.md": "nothing here\n"},
    )
    scanned = verifier.result.checked.get("SEC-ACCOUNT-ID", 0)
    assert scanned == 2, f"expected both files to be scanned, counter says {scanned}"
    assert _account_findings(verifier) == []


def test_an_empty_tree_reports_the_scan_as_vacuous(tmp_path: Path) -> None:
    """The counter is load-bearing: zero files scanned is itself a failure."""
    verifier = _scan(tmp_path, {})
    assert verifier.result.checked.get("SEC-ACCOUNT-ID", 0) == 0
    assert any("vacuous" in f.detail for f in verifier.result.failures)


# ── the real tree, and the harness that proves the detector is alive ──────────────────


def test_the_committed_evidence_tree_is_clean_and_still_holds_the_measurement() -> None:
    """Both halves in one place: the lane is green *and* the artefact was not edited.

    Asserting only that the scan passes would also pass if someone had deleted the number
    from the recorded measurement, which is the failure mode this whole task exists to
    avoid. So the literal is asserted present in the committed file at the same time.
    """
    quota = _REPO_ROOT / QUOTA_FILE
    assert quota.is_file(), f"{QUOTA_FILE} is missing"
    assert f": {QUOTA_BYTES}" in quota.read_text(encoding="utf-8"), (
        "the recorded lambda get-account-settings quota is no longer in the artefact; "
        "the scanner was fixed by editing the evidence, which forges a measurement"
    )

    verifier = Verifier(_REPO_ROOT)
    verifier.check_secrets()
    assert _account_findings(verifier) == [], "\n".join(_account_findings(verifier))
    assert verifier.result.checked["SEC-ACCOUNT-ID"] > 0


@pytest.mark.parametrize(
    "label",
    [
        "an account id is written into evidence/",
        "an account id is quoted in a JSON artefact",
        "a bare number sits under an account key",
    ],
)
def test_every_planted_account_leak_still_trips_the_detector(tmp_path: Path, label: str) -> None:
    """The mutation harness's own plants, run here rather than taken on trust.

    ``--self-test`` is the mechanism that proves this detector is alive; the plant that
    predates the fix (a ``.txt`` leak) plus the two the fix required (a quoted id and a
    keyed bare number) cover all three code paths ``SEC-ACCOUNT-ID`` now has.
    """
    plants = {
        name: mutate
        for name, invariant, mutate in _secret_plants()
        if invariant == "SEC-ACCOUNT-ID"
    }
    assert label in plants, f"the plant named {label!r} has disappeared from _secret_plants()"

    sandbox = tmp_path / "evidence"
    shutil.copytree(_REPO_ROOT / "evidence", sandbox)

    clean = Verifier(_REPO_ROOT, sandbox)
    clean.check_secrets()
    assert _account_findings(clean) == [], (
        "the unmutated copy is already red, so nothing below proves its plant"
    )

    plants[label](sandbox)
    mutated = Verifier(_REPO_ROOT, sandbox)
    mutated.check_secrets()
    assert _account_findings(mutated), f"planting {label!r} did not make SEC-ACCOUNT-ID fire"
