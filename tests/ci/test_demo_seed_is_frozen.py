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
#: ``SEED_FILES``, in the order it applies them - and their SHA-256 as measured on
#: 2026-08-13 by the worker that wrote this test:
#:
#:     $ python -c "import hashlib, pathlib
#:     > for p in sorted(pathlib.Path('verticals/mainline/db/seeds/demo').glob('*.sql')):
#:     >     print(p.name, hashlib.sha256(p.read_bytes()).hexdigest())"
#:     demo_permit.sql 198d44ef…
#:     demo_world.sql  50535d1d…
#:
#: Recorded over the bytes on disk, with no normalisation: ``.gitattributes`` sets
#: ``* -text``, so what is committed is what is applied, and a line-ending change to a file
#: the deployment feeds to a database is exactly as much of a change as any other.
#:
#: PROVENANCE OF THESE TWO VALUES, stated because it matters. They were measured on a
#: working tree in which the demo-suite lead had 144 uncommitted added lines in
#: ``demo_world.sql`` - the ``change_request`` gated subject argued in
#: ``docs/decisions/demo-change-request.md``. The baseline is therefore the seed as this
#: wave intends to land it, not as ``073dfea`` committed it. If that addition changes shape
#: before it lands, this hash must be re-measured **in the same commit**, and the sentence
#: below applies to that re-measurement exactly as it applies to any other.
FROZEN: Final[dict[str, str]] = {
    "demo_world.sql": "50535d1db0babf78a3cb4f50ec3d682b4034a5068fefcbb148c61950cfc07aee",
    "demo_permit.sql": "198d44ef6e843fa6ddaec3620ad7c668f800a1ab5b7ef37cf73d63dcdf66dcc6",
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
        "to stay. If the change you are re-baselining is of that shape, revert it instead."
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
