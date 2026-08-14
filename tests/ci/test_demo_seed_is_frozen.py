# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The two seed files the demo deploys are FROZEN, because one of them was once reshaped.

THE STORY THIS TEST EXISTS TO KEEP TOLD.

``verticals/mainline/db/seeds/demo/demo_world.sql`` line 124 enrols the demo's signing
credential as ``digest('mainline-demo/credential/demo.signer', 'sha256')``. In August 2026
``mainline_demo_api.gate_run`` bound a DIFFERENT 32-byte value into the same column - it
computed ``sha256(b"credsigner")`` from two hardcoded words - and
``mainline.disposition.signer_credential_id`` is a FOREIGN KEY onto
``mainline.signing_credential (credential_id)``. So beat 4 of the demo failed
``23503 disposition_signer_credential_id_fkey`` against the database that is actually
deployed, in front of a judge, while 291 tests were green.

A worker sent to fix it edited **this seed file** to enrol the constant the application
derived - making the SEED match the CODE. That is the wrong repair, and the reason is not
a matter of taste: the database owns ``credential_id``, because the foreign key says so
and because in the product the value arrives from a WebAuthn enrolment and is derivable by
nobody. So the code had to RESOLVE the value (it now does, in
``mainline_demo_api.credentials.resolve_credential_id``) and the seed had to stay exactly
as it was. Three independent negative controls caught the edit; one of them,
``verticals/mainline/apps/demo-api/tests/test_credentials.py``
``::test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive``, said so in
as many words - *"the seed has been reshaped to match an application constant"*. The edit
was reverted.

WHY THAT IS NOT ENOUGH, AND WHY THIS FILE IS HERE.

Every one of those three controls is marked ``requires_cluster``. Measured at HEAD
``073dfea`` on 2026-08-13:

    $ pytest verticals/mainline/apps/demo-api/tests --crdb=none  -q
    258 passed, 186 skipped
    $ grep -rn "demo-api" .github/workflows/
    (no matches, in any file)

The controls skip in every lane this repository had, and a skip is the same green tick as
a pass on a dashboard. So on the day the seed was reshaped, **nothing in CI could see it**.
``.github/workflows/cluster-tests.yml`` closes that by running the suite against a real
node, and ``.github/workflows/cluster-lane-bites.yml`` proves that lane can fail - it
plants this exact edit and asserts the cluster lane goes red while the hermetic lane stays
green.

This test is the cheap half of the same guard, and it is deliberately of a different KIND
from those controls: they are behavioural and need a database; this one is a file hash and
needs nothing. It cannot tell you that a seed is *wrong*. It tells you that a seed
*changed*, in a lane that runs on every push in under a second, which is what turns a
quiet edit into a conversation.

**A RED HERE IS NOT A BUG - IT IS A QUESTION.** These files are meant to grow: a new gated
subject, a new clause, a new site are all legitimate. Re-baselining is therefore expected
and allowed, on one condition: the commit that changes the hash **says what changed in the
seed and why**, and a reviewer reads that sentence. What must never happen again is an
edit to these bytes made in order to turn a test green. If that is what you are about to
do, the answer is in the paragraph above: ask which side owns the value.

The second test below never needs a re-baseline. It asserts the one property the incident
was about - the credential is DERIVED FROM ITS NAME IN THE SEED and the value the
application used to compute appears nowhere in the file - and it survives every legitimate
growth of the seed, because growth does not touch that line.

================================================================================
THE RE-BASELINE OF 2026-08-14, AND THE NEGATIVE CONTROL THAT RAN BEFORE IT
================================================================================

Both seed files changed in ``eefae1c`` and the freeze was not re-measured in that commit,
so from ``eefae1c`` until this commit the two hash assertions were red at a CLEAN tree.
``.github/workflows/cluster-lane-bites.yml`` run **31735341050** is where that surfaced:
its steps 1-18 all passed - all four cells of the 2x2, the inventory-cannot-suppress
control, and *"The frozen-seed guard is RED against this edit"* - and step 19,
*"The frozen-seed guard is GREEN again"*, which runs AFTER the revert on a tree the same
job had just proved byte-for-byte clean, reported ``2 failed, 1 passed in 0.17s``. A guard
that is red with the plant AND red without it discriminates nothing, so this file's own
sixth assertion had quietly stopped being a proof.

Re-baselining a hash to turn a red test green is the exact shape of the edit that put
``23503`` in front of a judge. So the re-baseline below was gated on a four-part negative
control that ran BEFORE the constants were touched, whose whole job was to give this commit
a way to come out "revert the seed instead". It came back clean on all four. Measured
2026-08-14 on TRAPPOINT at HEAD ``eefae1c``, working tree clean of tracked changes:

1.  NO CREDENTIAL LINE MOVED IN THE SEED CHANGE BEING RE-BASELINED.

        $ git diff 8e6a195..eefae1c -- \\
              verticals/mainline/db/seeds/demo/demo_world.sql \\
              verticals/mainline/db/seeds/demo/demo_permit.sql \\
          | grep -E '^[+-]' | grep -vE '^(\\+\\+\\+|---)' \\
          | grep -cE "signing_credential|credential_id|digest\\('mainline-demo/credential/"
        0

    650 changed lines (619 insertions, 31 deletions) across the two files, and **zero** of
    them mention ``signing_credential``, ``credential_id`` or the credential digest
    expression. What did change: ``demo_world.sql`` gained a ``change_request`` gated
    subject with its ``cr_clause``/``cr_event``/``blocking_check``/``cosignature`` rows and
    a ledger intake/node/checkpoint chain; ``demo_permit.sql`` gained the RFC 6962
    single-leaf boundary proof for ``silence_receipt``. Growth, in the sense this file's
    header calls legitimate - not a reshaping of the enrolment.

2.  THE CONTROL THAT CANNOT BE RE-BASELINED IS GREEN AT HEAD.

        $ .venv/Scripts/python.exe -m pytest tests/ci/test_demo_seed_is_frozen.py \\
              --crdb=none -q -p no:cacheprovider
        2 failed, 1 passed in 0.45s

    The 2 failed are the two hash assertions this commit re-baselines. **The 1 passed is
    ``test_the_seed_derives_the_demo_credentials_from_their_names``** - run on its own,
    ``1 passed in 0.37s``. That is the test below that names the shape of the damage
    instead of a hash. It was passing before the re-baseline and is passing after it,
    which is what makes the hash edit a re-measurement rather than a repair.

3.  THE CLUSTER-BACKED CREDENTIAL CONTROLS PASS IN FULL, INCLUDING THE ONE THAT CAUGHT THE
    ORIGINAL RESHAPING.

        $ .venv/Scripts/python.exe -m pytest \\
            verticals/mainline/apps/demo-api/tests/test_credentials.py \\
            --crdb=reuse -q -p no:cacheprovider --junitxml=<report>
        tests=17 failures=0 errors=0 skipped=0        (read from the JUnit, not the scroll)

    Among those 17 is
    ``test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive``, the control
    whose message is *"the seed has been reshaped to match an application constant"*, and
    the one the bites lane's plant declares as its ``caught_by``.

4.  THE SEED STILL DERIVES EXACTLY ONE SIGNER FROM ITS NAME.

        $ grep -n "digest('mainline-demo/credential/" \\
              verticals/mainline/db/seeds/demo/demo_world.sql
        124:    digest('mainline-demo/credential/demo.signer', 'sha256'),
        132:    digest('mainline-demo/credential/demo.countersigner', 'sha256'),
        $ derived=$(python -c "import hashlib
        > print(hashlib.sha256(b'credsigner').hexdigest())")
        $ grep -c "${derived}" verticals/mainline/db/seeds/demo/demo_world.sql
        0

    One signer enrolment, one countersigner enrolment, both still written as a digest OF A
    NAME; and the 32-byte constant ``gate_run`` once derived appears nowhere in the file.

Had any of the four come back otherwise, the answer was to revert the seed and NOT to touch
the constants below. They did not, so the hashes were re-measured. The `FROZEN` values
before this commit - `50535d1db0babf78a3cb4f50ec3d682b4034a5068fefcbb148c61950cfc07aee` for
``demo_world.sql`` and `198d44ef6e843fa6ddaec3620ad7c668f800a1ab5b7ef37cf73d63dcdf66dcc6`
for ``demo_permit.sql`` - are kept here rather than deleted, because a replaced number that
leaves no trace teaches nobody what moved.

================================================================================
HOW TO RE-BASELINE - the procedure, and its precondition
================================================================================

THE PRECONDITION IS THE FOUR-PART NEGATIVE CONTROL ABOVE, RUN BEFORE THE CONSTANTS ARE
TOUCHED. It is not a formality and it is not satisfied by reading it. Run all four, paste
the outputs into this docstring under a new dated heading, and if ANY of them fails, STOP:
the seed change is of the shape this file exists to refuse, and the repair is to revert the
seed. A negative control run after the edit is not a control, it is a description.

Then, and only then:

1.  Re-measure both files, over the bytes on disk, with no normalisation::

        $ python -c "import hashlib, pathlib
        > for p in sorted(pathlib.Path('verticals/mainline/db/seeds/demo').glob('*.sql')):
        >     b = p.read_bytes(); print(p.name, len(b), hashlib.sha256(b).hexdigest())"

2.  Replace the two constants in ``FROZEN``, and keep the superseded pair visible in this
    docstring beside the reading that replaced it.
3.  Land it **IN THE SAME COMMIT as the seed change**, and make the commit message say what
    changed in the seed and why. THIS COMMIT IS ITSELF AN EXCEPTION TO THAT RULE and says
    so: the seed changed in ``eefae1c`` and the re-baseline is arriving afterwards. The
    four-part control above is what stands in for the same-commit review that ``eefae1c``
    did not get. Do not read that exception as the rule relaxing - it is the more expensive
    way to do this, and it exists because the guard was left red at a clean tree.
4.  Check that ``pytest tests/ci/test_demo_seed_is_frozen.py --crdb=none`` is **3 passed**
    at a clean tree, and that the bites lane's step 17 - the guard RED against the plant -
    still fails as it must. Green in both halves is the failure mode; this guard is only a
    guard when it is red with the plant and green without it.

THIS WILL BE NEEDED AGAIN SHORTLY, AND THAT IS CORRECT RATHER THAN CHURN. ``demo_world.sql``
owes rows to ``mainline.defeater_option``: the table holds zero today, so
``test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements``
fails on an empty ``defeater_options`` set and a judge cannot choose a defeater, which is
the last beat of the demo. The lead who lands those rows WILL break this freeze, and should
- a freeze that did not notice new rows arriving in a deployed seed would be worth nothing.
That lead runs the four-part control, re-measures, and lands both halves together. The cost
of this file is one re-measurement per legitimate seed change; the thing it buys is that a
quiet edit to a deployed seed becomes a conversation, and it has already been that once.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

import pytest

#: ``tests/ci/<this file>`` -> the repository root. Asserted rather than assumed: a wrong
#: root would make every path below miss, and a test that hashes nothing passes.
REPO_ROOT: Final = Path(__file__).resolve().parents[2]

SEEDS_DIR: Final = REPO_ROOT / "verticals/mainline/db/seeds/demo"

#: The files ``scripts/deploy/seed_demo.py`` applies to the deployed database - its
#: ``SEED_FILES``, in the order it applies them - and their SHA-256, RE-MEASURED at
#: ``eefae1c`` on 2026-08-14 after the four-part negative control in the module docstring
#: came back clean on all four parts:
#:
#:     $ python -c "import hashlib, pathlib
#:     > for p in sorted(pathlib.Path('verticals/mainline/db/seeds/demo').glob('*.sql')):
#:     >     b = p.read_bytes(); print(p.name, len(b), hashlib.sha256(b).hexdigest())"
#:     demo_permit.sql 28889 df3470cb…
#:     demo_world.sql  55980 e2aa9706…
#:
#: Recorded over the bytes on disk, with no normalisation: ``.gitattributes`` sets
#: ``* -text``, so what is committed is what is applied, and a line-ending change to a file
#: the deployment feeds to a database is exactly as much of a change as any other.
#:
#: SUPERSEDED, KEPT RATHER THAN DELETED, because a number replaced in place teaches nobody
#: what moved. The 2026-08-13 reading was ``demo_permit.sql 198d44ef…`` /
#: ``demo_world.sql 50535d1d…``, measured on a working tree in which the demo-suite lead
#: had 144 uncommitted added lines in ``demo_world.sql`` - the ``change_request`` gated
#: subject argued in ``docs/decisions/demo-change-request.md``. That addition landed in
#: ``eefae1c`` at a different shape (512 added lines in ``demo_world.sql``, 138 in
#: ``demo_permit.sql``), exactly the case that comment predicted would need a
#: re-measurement, and the re-measurement did not arrive with it. That is why the guard
#: stood red at a clean tree until this commit, and why ``cluster-lane-bites`` run
#: 31735341050 failed at its LAST step with all four cells of its 2x2 green.
FROZEN: Final[dict[str, str]] = {
    "demo_world.sql": "e2aa9706ffca80f269edaa77e1dc8224b26b52ef6c4b666c74076bcc173787bf",
    "demo_permit.sql": "df3470cb26659b4bb8a4b565447b279a1417ef773988843951aa9817259c2d35",
}

#: The expression the seed uses to enrol the demo signer's credential. Written here as the
#: literal the seed contains - this test's job is to be able to DISAGREE with the file, and
#: an expectation imported from the thing under test can never disagree with it.
SEED_CREDENTIAL_EXPRESSIONS: Final = (
    "digest('mainline-demo/credential/demo.signer', 'sha256')",
    "digest('mainline-demo/credential/demo.countersigner', 'sha256')",
)


def _derived_credential_hex() -> str:
    """``sha256(b"credsigner")`` - the value ``gate_run`` used to bind, as lowercase hex.

    Derived rather than restated, for the same reason ``test_credentials.py:94`` derives
    it: a 32-byte constant copied into a second file is a constant nobody can check, and
    this file is the last place that mistake should be repeated.
    """
    return hashlib.sha256(b"credsigner").hexdigest()


def _seed(name: str) -> Path:
    path = SEEDS_DIR / name
    assert path.is_file(), (
        f"{path} does not exist. This test freezes the files the demo deployment applies; "
        "if one was renamed or moved, this list must move with it in the same commit."
    )
    return path


@pytest.mark.frozen
@pytest.mark.parametrize("name", sorted(FROZEN))
def test_the_deployed_seed_files_have_not_changed(name: str) -> None:
    """Each deployed seed file hashes to the value recorded when this test was written."""
    path = _seed(name)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = FROZEN[name]
    assert digest == expected, (
        f"{path.relative_to(REPO_ROOT).as_posix()} has changed: it hashes {digest}, and "
        f"this test records {expected}.\n"
        "\n"
        "THIS IS A QUESTION, NOT A VERDICT. These files are meant to grow, and a "
        "re-baseline is allowed - replace the hash in tests/ci/test_demo_seed_is_frozen.py "
        "IN THE SAME COMMIT as the seed change, and make that commit message say what "
        "changed in the seed and why.\n"
        "\n"
        "WHAT IS NOT ALLOWED is editing these bytes to make a failing test pass. That has "
        "happened here once: the credential enrolment on line 124 was replaced with the "
        "constant the application derived, so that the SEED matched the CODE. The database "
        "owns that value - mainline.disposition.signer_credential_id is a FOREIGN KEY onto "
        "mainline.signing_credential - so the application had to read it and the seed had "
        "to stay. If the change you are re-baselining is of that shape, revert it instead.\n"
        "\n"
        "HOW TO TELL THOSE TWO APART, without arguing about it: run the four-part negative "
        "control written out under 'HOW TO RE-BASELINE' in this module's docstring, BEFORE "
        "you touch the constants. It reads the seed diff for moved credential lines, runs "
        "the derivation control below, runs "
        "verticals/mainline/apps/demo-api/tests/test_credentials.py under --crdb=reuse, and "
        "counts the enrolments in the file. All four must come back clean. If any of them "
        "does not, the answer is to revert the seed, and this red is what stopped you."
    )


@pytest.mark.frozen
def test_the_seed_derives_the_demo_credentials_from_their_names() -> None:
    """The one property the incident was about, asserted without a hash to re-baseline.

    ``test_the_deployed_seed_files_have_not_changed`` above goes red for any change at all,
    including the legitimate ones, and a check that is re-baselined routinely eventually
    gets re-baselined without being read. This one cannot be: it names the exact shape of
    the damage, so it stays green through every honest edit to these files and red only for
    the edit that has actually been made here once.
    """
    text = _seed("demo_world.sql").read_text(encoding="utf-8")

    for expression in SEED_CREDENTIAL_EXPRESSIONS:
        assert text.count(expression) == 1, (
            f"demo_world.sql no longer enrols exactly one credential as {expression}. The "
            "demo's signing credentials are derived from their NAMES in the seed, which is "
            "what makes them values the application cannot compute and must read. An "
            "enrolment written as a literal is one an application constant can be made to "
            "match, which is how beat 4 came to fail against the deployed database while "
            "the suite was green."
        )

    derived = _derived_credential_hex()
    assert derived.lower() not in text.lower(), (
        "demo_world.sql contains the 32-byte value mainline_demo_api.gate_run used to "
        "DERIVE as signer_credential_id (sha256 of b'credsigner'). The seed has been "
        "reshaped to match an application constant. That is the reconciliation three "
        "negative controls already rejected once: the database owns credential_id, so "
        "mainline_demo_api.credentials.resolve_credential_id reads it and this file stays "
        "as it is. If a cluster-backed test is red because the code derives a credential, "
        "fix the code."
    )
