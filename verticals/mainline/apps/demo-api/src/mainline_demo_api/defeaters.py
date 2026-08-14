# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Which defeaters a check OFFERED — READ from the table that owns them.

``mainline.disposition.defeater_vocab_sha256`` is the digest of the option set a signer
was shown. Migration ``0064_defeater_option.sql`` states what that value means, in the
file that creates the table:

    ``vocab_sha256`` IS THE SAME VALUE ON EVERY ROW OF ONE GENERATION. It digests the
    whole option set, not the row, so a signature that pins it pins the ALTERNATIVES the
    signer declined as well as the one they chose.

``console/contracts/disposition.schema.json`` says the same thing from the other side:
*"Pins WHICH vocabulary was offered. A disposition records the same digest, so a later
regeneration cannot silently reinterpret a past signature."*

THE DEFECT THIS MODULE REPLACES, AND WHY IT IS THE SAME CLASS AS THE CREDENTIAL ONE
-----------------------------------------------------------------------------------
Until 2026-08-14 both signing paths in this package bound ``_sha("defeater-vocab")`` —
``gate_run.py:608`` and ``transitions.py:1065`` — which is ``sha256(b"defeater-vocab")``,
i.e. ``7ad8d49c2edd93f0a8fd3cd6b2a5d6cd225810805527a1a3f2f497aec819db3f``.
That constant is byte-for-byte the value the DEPLOYED CockroachDB Cloud recorded on its
one signed disposition: decode
``console/fixtures/bundles/demo-cloud/frames/GET-f116fc2724f1b968.json`` and read
``signed.defeater_vocab_sha256``. So the demo's signature pinned the SHA-256 of an ASCII
string. It pinned no vocabulary, it would have gone on pinning no vocabulary after the
rows landed, and both sentences quoted above were false of this code.

This is :mod:`mainline_demo_api.credentials` again, one column across. The remedy is the
one that was ratified there and is repeated here deliberately rather than reinvented:
**the database owns the value, the application RESOLVES it, nothing is recomputed and
nothing is defaulted.** A digest this module computed would agree with whatever fixture
shared the expression and with no seed that is deployed — which is exactly how a derived
credential id reached a judge as ``23503`` behind 291 green tests.

WHY AN EMPTY VOCABULARY REFUSES INSTEAD OF FALLING BACK
-------------------------------------------------------
``mainline.disposition`` has **no foreign key onto ``mainline.defeater_option``**.
``0066_disposition.sql`` carries ``defeater_code STRING NOT NULL`` with only
``CONSTRAINT disposition_defeater_code_stated CHECK (defeater_code <> '')``, so nothing in
the database will catch a code that was never offered, and nothing will catch a digest of
a vocabulary that does not exist. That absence is *why* an empty vocabulary never refused
anything and why the admission beat has been green over this defect since it was written.
A foreign key is not added here: migrations are rendered under a ``trappoint render
--check`` zero-diff assertion, and a new constraint moves ``migrations.lock.json``, the
schema fingerprint and the dev/demo/prod parity gate four days from a deadline. The gap is
closed by refusing in the application and by the assertions in
``tests/test_defeaters.py``, and it is recorded as a finding rather than left unwritten.

So :func:`resolve_defeater_vocabulary` RAISES when the table holds no row for the check.
It does not return ``None`` for a caller to substitute around, and it does not fall back
to a constant. **A silent fallback is exactly how this shipped**, and a resolver that can
answer "nothing, carry on" is a resolver that will be asked to.

More than one distinct ``vocab_sha256`` for one check is refused for the mirror-image
reason. 0064 says the digest is the same on every row of one generation; several distinct
values mean two generations are interleaved in the table, and a signature pinning either
of them would pin an option set that was never on one screen. The refusal names the count,
because "which generation" is the question a reader has to answer next.

NO VALUE THIS MODULE RAISES IS A SECRET, and none of them is elided either. The refusals
name the check, the table, the codes and the count. A defeater code is public product
vocabulary printed beside a prompt in the console; unlike a credential id there is nothing
here that must be kept out of a log, and a refusal that hid the offered set would send its
reader to the database to find out what it could have said.

ROW SHAPE
---------
The one statement here is read BY POSITION through
:func:`mainline_demo_api.scenario.positional`, which sets the row factory on the CURSOR.
``db.connection()`` opens production connections with ``psycopg.rows.dict_row`` and tests
may hand this module a ``tuple_row`` connection; the statement declares the shape it was
written against instead of inheriting one. That is the contract
``tests/test_row_factory_contract.py`` asserts for this module's siblings.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Final

import psycopg

from .scenario import ScenarioNotSeeded, positional

__all__ = [
    "DEFEATER_VOCABULARY_SOURCE",
    "DefeaterNotOffered",
    "DefeaterVocabulary",
    "DefeaterVocabularyAbsent",
    "DefeaterVocabularyAmbiguous",
    "DefeaterVocabularyUnresolvable",
    "resolve_defeater_vocabulary",
]

#: The table that owns the vocabulary and its digest, named once so every refusal below
#: names the same thing the statement reads.
DEFEATER_VOCABULARY_SOURCE: Final = "mainline.defeater_option"

#: Every option this check offers, in a deterministic order, with the digest each row
#: carries.
#:
#: ``ORDER BY defeater_code`` makes the offered set stable so that a refusal reports a fact
#: about the database rather than a fact about scan order — the same reason
#: ``credentials._CREDENTIAL_SQL`` orders by ``credential_id``. Both columns are selected
#: in one statement rather than the digest in a second: ``pk_defeater_option`` is
#: ``(check_id, defeater_code)``, so the rows are read together anyway, and two statements
#: would let a concurrent regeneration land between them and produce a code list from one
#: generation beside a digest from another.
#:
#: There is no ``LIMIT``. ``reads._DEFEATER_SQL`` caps its read at 32 because it is filling
#: a screen; this statement decides whether a SIGNATURE may name a code, and a cap here
#: would silently make the 33rd option unofferable to a signer while the console displayed
#: it. The table is spelled out rather than interpolated from
#: :data:`DEFEATER_VOCABULARY_SOURCE`: an f-string here is a genuine ``S608`` shape, and
#: ``test_defeaters.py`` asserts the two literals agree.
_DEFEATER_SQL: Final = """
SELECT defeater_code, vocab_sha256
  FROM mainline.defeater_option
 WHERE check_id = %s
 ORDER BY defeater_code
"""


class DefeaterVocabularyUnresolvable(ScenarioNotSeeded):
    """No single defeater vocabulary can be named for this check.

    A :class:`mainline_demo_api.scenario.ScenarioNotSeeded`, deliberately and for the
    reason :class:`mainline_demo_api.credentials.CredentialUnresolvable` is one: the
    condition is "this database does not hold the history the demo signs against", which
    is the finding that class exists to carry, and which
    ``transitions.handle_transition`` already answers with ``422
    demo_history_not_seeded`` and the refusal's own detail rather than a 500.

    Attributes:
        check_id: the obligation that was looked up. Present so a caller can act on the
            failure without parsing the message.
        table: the table that owns the vocabulary, i.e.
            :data:`DEFEATER_VOCABULARY_SOURCE`.
        options: how many rows that check actually has.
        generations: how many DISTINCT ``vocab_sha256`` values those rows carry.
    """

    def __init__(
        self, detail: str, *, check_id: uuid.UUID, options: int, generations: int
    ) -> None:
        super().__init__(detail)
        self.check_id = check_id
        self.table = DEFEATER_VOCABULARY_SOURCE
        self.options = options
        self.generations = generations


class DefeaterVocabularyAbsent(DefeaterVocabularyUnresolvable):
    """The check offers no defeater options at all, so a signature cannot pin one."""


class DefeaterVocabularyAmbiguous(DefeaterVocabularyUnresolvable):
    """The check's rows carry several digests: two generations, and this API will not pick."""


class DefeaterNotOffered(ValueError):
    """A signature named a defeater code this check never offered.

    A :class:`ValueError`, deliberately: ``transitions.handle_transition`` answers that
    class with ``422 unprocessable_request`` and the message below, which is the right
    diagnosis for "the caller asked wrongly". It is emphatically **not** a gate refusal —
    the database has no foreign key here and refused nothing — and dressing it as one
    would put an exhibit in front of a reader that no constraint produced.

    Attributes:
        check_id: the obligation whose vocabulary was consulted.
        defeater_code: the code that was named and is not in it.
        offered: the codes that are, in the order the table returned them.
    """

    def __init__(
        self, detail: str, *, check_id: uuid.UUID, defeater_code: str, offered: tuple[str, ...]
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.check_id = check_id
        self.defeater_code = defeater_code
        self.offered = offered


@dataclass(frozen=True, slots=True)
class DefeaterVocabulary:
    """One generation of one check's defeater options, as the database holds them.

    Attributes:
        check_id: the obligation these options belong to. The code is unique WITHIN a
            check and meaningless outside it (0064's ``PRIMARY KEY (check_id,
            defeater_code)`` rationale), so the identifier travels with the set.
        codes: every offered code, ordered by ``defeater_code``.
        vocab_sha256: the 32-byte digest every one of those rows carries. Read, never
            computed: this module has no hashing helper and must not acquire one.
    """

    check_id: uuid.UUID
    codes: tuple[str, ...]
    vocab_sha256: bytes

    def offers(self, defeater_code: str) -> bool:
        """Report whether *defeater_code* is one of the options this check offered."""
        return defeater_code in self.codes

    def require(self, defeater_code: str) -> str:
        """Return *defeater_code* if it was offered; raise :class:`DefeaterNotOffered` if not.

        This is the assertion that stands in for the foreign key
        ``mainline.disposition`` does not have. Without it a signature can name a code no
        screen ever displayed while recording the digest of the set that did not contain
        it — a disposition that is internally inconsistent and that nothing in the
        database would notice, which is a worse artefact than one that was simply refused.
        """
        if defeater_code in self.codes:
            return defeater_code
        raise DefeaterNotOffered(
            f"defeater_code {defeater_code!r} is not offered by check {self.check_id}. "
            f"{DEFEATER_VOCABULARY_SOURCE} offers {list(self.codes)} for it, and a "
            "disposition records the digest of that whole set — so a signature naming a "
            "code outside it would pin a vocabulary that never contained the choice it "
            "claims. mainline.disposition has no foreign key onto "
            f"{DEFEATER_VOCABULARY_SOURCE} (0066_disposition.sql carries only CONSTRAINT "
            "disposition_defeater_code_stated CHECK (defeater_code <> '')), so this is "
            "refused here or it is not refused at all.",
            check_id=self.check_id,
            defeater_code=defeater_code,
            offered=self.codes,
        )


def resolve_defeater_vocabulary(
    conn: psycopg.Connection[Any], check_id: uuid.UUID
) -> DefeaterVocabulary:
    """Return the vocabulary *check_id* offers, read from the database.

    Args:
        conn: any psycopg connection, in autocommit or not, opened with any row factory.
            The statement is read by position through :func:`scenario.positional`.
        check_id: the obligation a disposition is about to be signed against.

    Returns:
        The offered codes and the single distinct digest those rows carry. Never derived,
        never defaulted, never cached: it is what this database holds at the moment it was
        asked, which is the only thing a signature is entitled to pin.

    Raises:
        DefeaterVocabularyAbsent: the check offers nothing. The message names the check
            and the table, so the failure is diagnosable where it happens rather than as a
            signature that quietly pinned a constant.
        DefeaterVocabularyAmbiguous: the rows carry more than one distinct digest, which
            0064 says cannot be true of one generation.
    """
    rows = positional(conn, _DEFEATER_SQL, (check_id,)).fetchall()

    if not rows:
        raise DefeaterVocabularyAbsent(
            f"{DEFEATER_VOCABULARY_SOURCE} holds no row for check {check_id} in this "
            "database: this check offers no defeater vocabulary, so a signature cannot "
            "pin one. mainline.disposition.defeater_vocab_sha256 digests the option set a "
            "signer was SHOWN (0064_defeater_option.sql), and this API resolves that "
            "digest rather than deriving one — there is no constant to fall back to, "
            "because a constant pins nothing and a signature that pins nothing is the "
            "click-through with a signature on it that 0064's rationale exists to forbid. "
            "Seed the vocabulary for this check — the demo history does so in "
            "verticals/mainline/db/seeds/demo/demo_permit.sql for the permit's obligation "
            "and demo_world.sql for the change request's, each with its own generation "
            "because 0064 makes a code unique WITHIN a check and meaningless outside it — "
            "or sign against a check whose options this database actually carries.",
            check_id=check_id,
            options=0,
            generations=0,
        )

    codes = tuple(str(row[0]) for row in rows)
    # `bytes(...)`: psycopg may hand back a `memoryview` for a BYTES column depending on
    # the loader in force, and two memoryviews over equal bytes are not equal to a set.
    # Copying once here means the distinctness test below is a test about the DATABASE's
    # values rather than about which loader answered.
    digests = {bytes(row[1]) for row in rows}

    if len(digests) > 1:
        raise DefeaterVocabularyAmbiguous(
            f"{DEFEATER_VOCABULARY_SOURCE} holds {len(rows)} options for check {check_id} "
            f"carrying {len(digests)} distinct vocab_sha256 values, and this API will not "
            "choose between them. 0064_defeater_option.sql: the digest 'IS THE SAME VALUE "
            "ON EVERY ROW OF ONE GENERATION. It digests the whole option set, not the "
            "row' — so several distinct values mean two generations are interleaved in "
            "this table, and a signature pinning either would pin an option set that was "
            "never on one screen. That is a corrupt generation, not a choice: regenerate "
            f"the vocabulary for this check. Offered codes: {list(codes)}.",
            check_id=check_id,
            options=len(rows),
            generations=len(digests),
        )

    return DefeaterVocabulary(check_id=check_id, codes=codes, vocab_sha256=digests.pop())
