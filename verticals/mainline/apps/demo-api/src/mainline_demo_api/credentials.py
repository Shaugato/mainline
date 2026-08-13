# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Which enrolled credential a subject signs with — READ from the table that owns it.

``mainline.disposition.signer_credential_id`` is a FOREIGN KEY onto
``mainline.signing_credential (credential_id)`` (migration ``0066_disposition.sql``,
lines 117-118, and again at 122-123 for the countersigner). The foreign key exists
because a credential is an authoritative row the DATABASE owns: in the product it
arrives from a WebAuthn enrolment and is not derivable by anybody, which is the entire
value of a signature bound to it. Application code that COMPUTES such a value has
asserted a fact about a row it did not write.

THE DEFECT THIS MODULE REPLACES, AND WHY IT IS A CLASS AND NOT AN INSTANCE
--------------------------------------------------------------------------
Until 2026-08-13 :mod:`mainline_demo_api.gate_run` bound
``sha256(b"cred" + b"signer")`` as ``signer_credential_id``. The deployed seed —
``verticals/mainline/db/seeds/demo/demo_world.sql``, applied to the cloud database by
``scripts/deploy/seed_demo.py`` — enrols ``digest('mainline-demo/credential/demo.signer',
'sha256')``. Two different 32-byte values for one column, so beat 4 of the demo failed
``23503 disposition_signer_credential_id_fkey`` against the database that is actually
deployed, and the run answered ``200`` carrying its own verdict as ``NOT PROVEN``.

Five files defined that constant and four of them agreed with each other: ``gate_run``,
``transitions``, the demo-api ``conftest`` seeder and ``scripts/proof/gate_refusal.py``
all called the same private ``_sha("cred", …)`` helper. The tests could not disagree with
the code because they read the same expression. **A test that cannot disagree with the
code it tests proves nothing**, and the fix for that is not a fifth agreeing constant: it
is to delete the derivation and read the row. One definition remains — the seed — and
this module resolves against whatever a given database actually enrolled, so the demo is
correct against ``demo_world.sql``, against the ``w3`` fixture world, and against a
customer's real enrolment without an edit here.

``scripts/deploy/capture_demo_bundle.py`` (lines 929-937) already read
``signing_credential`` by ``signer_sub`` and already refused to build a bundle when the
row was absent. The deployment tooling had treated the table as authoritative all along;
the application was the outlier.

WHY THE REFUSAL IS TYPED, AND WHY IT NAMES THE SUBJECT
------------------------------------------------------
A missing credential used to surface as ``23503`` raised by an INSERT nested inside beat
4's ``SAVEPOINT``, where it was caught, diagnosed as a refusal and reported as though the
GATE had spoken. It had not: nothing about the product was demonstrated by that row's
absence. :class:`CredentialNotEnrolled` is raised at resolve time instead, before the
beats' transaction is opened, and it names the ``signer_sub`` that has no credential and
the table that would have to hold one. It subclasses
:class:`mainline_demo_api.scenario.ScenarioNotSeeded` because that is exactly what the
condition is — the demo history is not in this database — and because
``transitions.handle_transition`` already answers that class with
``422 demo_history_not_seeded`` and the refusal's own detail, rather than a 500.

Ambiguity is refused rather than resolved. ``pk_signing_credential`` is on
``credential_id`` alone, so one subject may legitimately hold several credentials, and
``signing_credential_by_signer`` is partial on ``revoked_at IS NULL`` precisely because
"which credentials may this person sign with NOW" is the lookup the signing path performs.
A disposition names exactly ONE ``signer_credential_id``; picking the first of several
would make the demo's signature depend on row order. The statement orders by
``credential_id`` so the read is deterministic, and :class:`CredentialAmbiguous` says so
out loud when there is more than one.

NO CREDENTIAL VALUE APPEARS IN ANY MESSAGE THIS MODULE RAISES. The refusals name the
subject, the count and the table — never the bytes. A diagnostic that prints the thing it
is diagnosing is how a credential identifier ends up in a log, a step summary and an
evidence file, and none of those are places it belongs.

ROW SHAPE
---------
The one statement here is read BY POSITION through
:func:`mainline_demo_api.scenario.positional`, which sets the row factory on the CURSOR.
``db.connection()`` opens production connections with ``psycopg.rows.dict_row`` and tests
may hand this module a ``tuple_row`` connection; the statement declares the shape it was
written against instead of inheriting one. That keeps this module factory-agnostic in both
directions, which is the contract ``tests/test_row_factory_contract.py`` asserts for its
siblings.
"""

from __future__ import annotations

from typing import Any, Final

import psycopg

from .scenario import ENV_PREFIX, ScenarioNotSeeded, positional

__all__ = [
    "CREDENTIAL_ID_SOURCE",
    "CredentialAmbiguous",
    "CredentialNotEnrolled",
    "CredentialUnresolvable",
    "resolve_credential_id",
]

#: The table that owns a credential id, named once so every refusal below names the same
#: thing the foreign key does.
CREDENTIAL_ID_SOURCE: Final = "mainline.signing_credential"

#: The live credentials a subject may sign with, in a deterministic order.
#:
#: ``revoked_at IS NULL`` is the predicate of the partial index
#: ``signing_credential_by_signer`` (migration 0023), which exists for this exact lookup:
#: a revoked key must never be a candidate, and the revoked rows stay in the table forever
#: because a 2029 signature must still verify in 2036. ``ORDER BY credential_id`` makes a
#: multi-row answer stable so that :class:`CredentialAmbiguous` reports a fact about the
#: database rather than a fact about scan order.
#:
#: The table is spelled out rather than interpolated from :data:`CREDENTIAL_ID_SOURCE`: an
#: f-string here is a genuine ``S608`` shape, and a statement whose text depends on a
#: variable is one a reader has to assemble in their head. ``test_credentials.py`` asserts
#: the two agree, so the second literal cannot drift from the name every refusal prints.
_CREDENTIAL_SQL: Final = """
SELECT credential_id
  FROM mainline.signing_credential
 WHERE signer_sub = %s AND revoked_at IS NULL
 ORDER BY credential_id
"""

#: Both overrides are named in every refusal because this function is given a subject and
#: is not told which role it plays; a message that named only one would send half of its
#: readers to the wrong environment variable.
_SUBJECT_OVERRIDES: Final = f"{ENV_PREFIX}SIGNER_SUB / {ENV_PREFIX}COUNTERSIGNER_SUB"


class CredentialUnresolvable(ScenarioNotSeeded):
    """No single enrolled credential can be named for this subject.

    A :class:`mainline_demo_api.scenario.ScenarioNotSeeded`, deliberately: the condition
    is "this database does not hold the history the demo signs against", which is the
    finding that class exists to carry, and which ``transitions.handle_transition``
    already answers with ``422 demo_history_not_seeded`` rather than a 500.

    Attributes:
        signer_sub: the subject that was looked up. Present so a caller can act on the
            failure without parsing the message.
        table: the table that owns the value, i.e. :data:`CREDENTIAL_ID_SOURCE`.
        live: how many unrevoked credentials that subject actually has.
    """

    def __init__(self, detail: str, *, signer_sub: str, live: int) -> None:
        super().__init__(detail)
        self.signer_sub = signer_sub
        self.table = CREDENTIAL_ID_SOURCE
        self.live = live


class CredentialNotEnrolled(CredentialUnresolvable):
    """The subject has no unrevoked credential in ``mainline.signing_credential``."""


class CredentialAmbiguous(CredentialUnresolvable):
    """The subject has more than one unrevoked credential, and this API will not choose."""


def resolve_credential_id(conn: psycopg.Connection[Any], signer_sub: str) -> bytes:
    """Return the enrolled credential id *signer_sub* signs with, read from the database.

    Args:
        conn: any psycopg connection, in autocommit or not, opened with any row factory.
            The statement is read by position through :func:`scenario.positional`.
        signer_sub: the subject whose credential is wanted — ``Scenario.signer_sub`` or
            ``Scenario.countersigner_sub``, both overridable from the environment.

    Returns:
        The 32-byte ``credential_id``. Never derived, never defaulted, never cached: it is
        the value this database holds at the moment it was asked.

    Raises:
        CredentialNotEnrolled: the subject has no unrevoked credential. The message names
            the subject and the table, so the failure is diagnosable where it happens
            rather than as a ``23503`` inside a savepoint three statements later.
        CredentialAmbiguous: the subject has several, and one disposition names one.
    """
    rows = positional(conn, _CREDENTIAL_SQL, (signer_sub,)).fetchall()

    if not rows:
        raise CredentialNotEnrolled(
            f"{CREDENTIAL_ID_SOURCE} holds no unrevoked credential for signer_sub "
            f"{signer_sub!r} in this database. A disposition's signer_credential_id is a "
            f"FOREIGN KEY onto {CREDENTIAL_ID_SOURCE} (credential_id) and this API "
            "RESOLVES it rather than deriving one, so an unenrolled subject is refused "
            "here instead of failing as 23503 disposition_signer_credential_id_fkey "
            "inside the admission beat. Enrol the credential — the demo history does so "
            "in verticals/mainline/db/seeds/demo/demo_world.sql — or point "
            f"{_SUBJECT_OVERRIDES} at a subject this database has enrolled.",
            signer_sub=signer_sub,
            live=0,
        )

    if len(rows) > 1:
        raise CredentialAmbiguous(
            f"{CREDENTIAL_ID_SOURCE} holds {len(rows)} unrevoked credentials for "
            f"signer_sub {signer_sub!r}, and this API will not choose between them. A "
            "disposition names exactly one signer_credential_id, so picking the first "
            "would make a signature depend on row order. Revoke the credentials that are "
            "no longer current (revoked_at and revoke_reason are set together — "
            f"constraint credential_revocation_reasoned) or point {_SUBJECT_OVERRIDES} at "
            "a subject holding exactly one live credential.",
            signer_sub=signer_sub,
            live=len(rows),
        )

    credential_id = rows[0][0]
    if isinstance(credential_id, bytes):
        return credential_id
    # psycopg may hand back a `memoryview` for a BYTES column depending on the loader in
    # force. Copying it once here means every caller holds a value that can be bound,
    # compared and hashed without knowing which loader answered.
    return bytes(credential_id)
