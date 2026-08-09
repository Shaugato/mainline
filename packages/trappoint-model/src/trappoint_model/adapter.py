# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The other half of the differential: the same eight operations, against the real gate.

Every method returns the same :class:`~trappoint_model.model.Verdict` vocabulary the
oracle returns, so the machine's assertion is one ``==``. Three rules hold this module
honest:

1. **Nothing here decides.** No method inspects the database and then chooses whether to
   attempt the write. It attempts, and reports what the database said. A harness that
   pre-checked would be asserting its own logic and would agree with a gate that had no
   constraints at all.
2. **Every projected column is supplied wrong.** ``severity``, ``virulence``,
   ``subject_kind``, ``signer_rank`` and the rest go in with values a liar would choose,
   and the projection triggers overwrite them. P-2 is therefore exercised on every single
   generated step rather than in one dedicated case.
3. **The exhibit is recovered, never assumed.** ``constraint`` comes from
   ``diag.constraint_name`` where the driver reports one, and from the substrate's own
   ``refused by <schema>.<object>`` clause where it does not — the same two tiers
   ``trappoint_core.errors.diagnose`` uses. This package does not import
   ``trappoint_core``: the import-linter contract keeps the model side free of the
   substrate, and duplicating twelve lines of regular expression is the price.

``sign_disposition`` issues its own exposure receipt with ``issued_at`` an hour in the
past. That is not a shortcut around a control: it makes ``reading_floor_met`` project
**true**, which keeps ``unmet_floor_count`` at zero and keeps the reading-rate floor —
a priced consequence, not a refusal — out of a differential that is about the gate.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Final

import psycopg

from .model import Accept, Refuse, Verdict
from .refschema import SCHEMA, Fixture

__all__ = ["Adapter", "verdict_of"]

_EXHIBIT_RE: Final = re.compile(r"\brefused by ([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)")
_RAISER_RE: Final = re.compile(r"^[A-Z][A-Z0-9_]*: ")

#: Which PL/pgSQL object raised, recovered from the message when the substrate does not
#: use the `refused by` form. ``spec/errors.md`` §2.5 requires the form on the *merge*
#: path only; the projection family raises a bare sentence, so the sentence is the key.
#: Every entry is a verbatim substring of a rendered migration, and
#: ``tests/test_adapter_messages.py`` asserts each one still occurs in the tree.
_BY_MESSAGE: Final[tuple[tuple[str, str], ...]] = (
    ("precursor arrived after issue", f"{SCHEMA}.fn_check_materialised"),
    ("the gate has no subject to close", f"{SCHEMA}.fn_check_materialised"),
    ("a blocking check names no gated subject", f"{SCHEMA}.fn_check_materialised"),
    ("no such blocking check", f"{SCHEMA}.fn_disposition_project"),
    ("blame closure absent", f"{SCHEMA}.fn_disposition_project"),
    ("exposure receipt absent or expired", f"{SCHEMA}.fn_disposition_project"),
    ("no competency record", f"{SCHEMA}.fn_disposition_project"),
    ("append-only except for a single retraction", f"{SCHEMA}.fn_disposition_retract_only"),
    ("only retracted_by may change", f"{SCHEMA}.fn_disposition_retract_only"),
    ("nothing to re-open", f"{SCHEMA}.fn_disposition_retract_only"),
    ("nothing to close", f"{SCHEMA}.fn_disposition_close"),
    ("this table is append-only", f"{SCHEMA}.fn_refuse_mutation"),
)

_RATIONALE: Final = (
    "The ancestral control was written by an incident in which an isolation point was "
    "assumed dead and was not; the compensating measure named below is verbatim from the "
    "recommendation and has been verified in the field today."
)


def verdict_of(exc: psycopg.Error) -> Refuse:
    """Turn a driver exception into the exhibit-carrying verdict the oracle speaks.

    Raises:
        AssertionError: the SQLSTATE is outside ``{40001, 23514, 23503, 23505, P0001}``.
            Refusal-taxonomy totality is an assertion, not a filter: a code nobody
            modelled means the database refused for a reason nobody modelled, and
            swallowing it here is how that discovery gets lost.
    """
    sqlstate = exc.sqlstate or ""
    diag = exc.diag
    message = (diag.message_primary if diag is not None else None) or str(exc)
    # S101: an `assert` on purpose. This module is a TEST INSTRUMENT and the
    # assertion is the finding — a code outside the taxonomy must stop the run it is
    # observed in, not be converted into a return value a caller can ignore.
    assert sqlstate in {"40001", "23514", "23503", "23505", "P0001"}, (  # noqa: S101
        f"{sqlstate} is outside the refusal taxonomy — the database refused for a reason "
        f"nobody modelled. Message: {message}"
    )
    reported = (diag.constraint_name if diag is not None else None) or ""
    if reported:
        return Refuse(sqlstate, reported)
    named = _EXHIBIT_RE.search(message)
    if named is not None:
        return Refuse(sqlstate, named.group(1))
    body = _RAISER_RE.sub("", message)
    for fragment, obj in _BY_MESSAGE:
        if fragment in body:
            return Refuse(sqlstate, obj)
    return Refuse(sqlstate, "")


class Adapter:
    """Executes the model's operations against a real cluster, one statement per call."""

    def __init__(
        self,
        conn: psycopg.Connection[Any],
        fixture: Fixture,
        setup_conn: psycopg.Connection[Any] | None = None,
    ) -> None:
        """Bind an autocommit connection and the tenancy its writes land in.

        Args:
            conn: the connection every GATE operation runs on. Its isolation level is the
                one under test.
            fixture: the tenancy.
            setup_conn: where AUTHORITY-SOURCE rows are seeded — the clause version and
                its blame closure. Defaults to *conn*.

                It exists because of a measured platform limit, and separating the two is
                the only honest way to run the downgrade differential. Writing a blame
                closure fires ``fn_closure_guard``, which records the closure in the
                custody ledger in the same transaction using
                ``cluster_logical_timestamp()``, and that builtin raises
                ``0A000 unsupported in READ COMMITTED isolation`` on CockroachDB v26.2.5
                (measured 2026-08-09). Seeding on a SERIALIZABLE connection keeps the
                READ COMMITTED run about the GATE rather than about the ledger's clock —
                and the gate path itself, on this binding, calls no such builtin.
        """
        self.conn = conn
        self.fixture = fixture
        self.setup_conn = setup_conn if setup_conn is not None else conn

    # ── plumbing ───────────────────────────────────────────────────────────────────
    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> Verdict:
        try:
            self.conn.execute(sql, params)
        except psycopg.Error as exc:
            return verdict_of(exc)
        return Accept()

    def _clause_version(self) -> tuple[uuid.UUID, bytes]:
        from .refschema import seed_clause_version

        return seed_clause_version(self.setup_conn, self.fixture)

    def _record_transition(self, sid: uuid.UUID, frm: str, to: str, guard: str = "true") -> Verdict:
        """Append the subject-state transition a gate SERVICE records, and move the head.

        Nothing in the kernel moves ``permit.state`` except ``merge_permit`` itself — the
        column is the application's record of where the subject is, and ``legal_edge`` is
        the database's opinion of whether that record is reachable. So the differential
        has to play the service, and it does so with the from-state and the guard written
        as a SQL predicate rather than as a Python ``if``: a statement that matches no row
        writes nothing, so the decision stays in the database and this module keeps its
        promise never to pre-check a gated write.

        Two transitions, and only two, matching the oracle exactly:

        * ``draft → checks_materialised`` when the first obligation lands. Entry into the
          gated zone.
        * ``checks_materialised → dispositioned`` when the last one is cleared.

        The re-opening edge ``dispositioned → checks_materialised`` is legal in
        ``subject_transition`` and is DELIBERATELY not recorded. That is what makes an
        obligation arriving after clearance meet ``gate_closed_when_issued`` — the
        projected counter alone standing between an open obligation and a merge, which is
        conformance case CF-01 and the whole claim of the product.
        """
        appended = self._run(
            f"INSERT INTO {SCHEMA}.permit_event (permit_id, seq, prev_seq, from_state, "  # noqa: S608
            "to_state, subject_kind, actor_sub, payload, prev_digest) "
            f"SELECT p.permit_id, p.head_seq + 1, p.head_seq, p.state, '{to}', 'permit', "
            "%s, '{}'::JSONB, coalesce((SELECT e.chain_digest "
            f"  FROM {SCHEMA}.permit_event e "
            "   WHERE e.permit_id = p.permit_id AND e.seq = p.head_seq), "
            "  decode(repeat('00', 32), 'hex')) "
            f"FROM {SCHEMA}.permit p "
            f"WHERE p.permit_id = %s AND p.state = '{frm}' AND ({guard})",
            (self.fixture.signer_sub, sid),
        )
        if isinstance(appended, Refuse):
            return appended
        return self._run(
            f"UPDATE {SCHEMA}.permit AS p SET state = '{to}', head_seq = p.head_seq + 1 "  # noqa: S608
            f"WHERE p.permit_id = %s AND p.state = '{frm}' AND ({guard})",
            (sid,),
        )

    # ── the eight operations ───────────────────────────────────────────────────────
    def create_subject(self, sid: uuid.UUID, parent: uuid.UUID | None = None) -> Verdict:
        """INSERT a permit in ``draft``. ``parent`` non-null is ``fork_child``."""
        return self._run(
            f"INSERT INTO {SCHEMA}.permit (permit_id, site_id, site_role, external_ref, "  # noqa: S608
            "ref_name, parent_permit_id, horizon_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, now() + INTERVAL '30 days')",
            (
                sid,
                self.fixture.site_id,
                self.fixture.site_role,
                f"ext-{sid}",
                f"refs/permits/{sid}",
                parent,
            ),
        )

    def materialise_check(self, sid: uuid.UUID, cid: uuid.UUID) -> Verdict:
        """INSERT a blocking check. ``severity`` and ``virulence`` go in deliberately wrong."""
        clause_uuid, commit_id = self._clause_version()
        armed = self._run(
            f"INSERT INTO {SCHEMA}.blocking_check (check_id, subject_kind, permit_id, site_id, "  # noqa: S608
            "clause_uuid, commit_id, origin, severity, virulence, closure_gen, evidence_summary) "
            # severity 0 / 'routine' / gen 99 is what a writer talking its obligation down
            # would supply. fn_check_project overwrites all three, unconditionally.
            "VALUES (%s, 'permit', %s, %s, %s, %s, 'blame_ancestry', 0, 'routine', 99, %s)",
            (
                cid,
                sid,
                self.fixture.site_id,
                clause_uuid,
                commit_id,
                "generated by the differential",
            ),
        )
        if isinstance(armed, Refuse):
            return armed
        return self._record_transition(sid, "draft", "checks_materialised")

    def sign_disposition(self, cid: uuid.UUID, did: uuid.UUID, *, expired: bool = False) -> Verdict:
        """Issue an exposure receipt, render the obligation onto it, and sign.

        ``expired=True`` signs a verdict whose ``expires_at`` is already in the past. That
        is legal at insert — ``ttl_enforced`` bounds the far end of the window, not the
        near one — and it is the cheapest deterministic way to produce the case the
        counter cannot see: ``open_blocking`` reads zero while the anti-join reads one.
        """
        receipt = uuid.uuid4()
        issued = self._run(
            f"INSERT INTO {SCHEMA}.exposure_receipt (receipt_id, subject_kind, permit_id, "  # noqa: S608
            "actor_sub, issued_at, issued_hlc, expires_at, corpus_root, silence_receipt_id, "
            "policy_version, total_tokens, receipt_digest) "
            "SELECT %s, 'permit', bc.permit_id, %s, now() - INTERVAL '1 hour', 0, "
            "now() + INTERVAL '1 hour', %s, %s, %s, 100, %s "
            f"FROM {SCHEMA}.blocking_check bc WHERE bc.check_id = %s",
            (
                receipt,
                self.fixture.signer_sub,
                b"\x33" * 32,
                uuid.uuid4(),
                self.fixture.policy_version,
                b"\x44" * 32,
                cid,
            ),
        )
        if isinstance(issued, Refuse):
            return issued
        # A failure here means the obligation does not exist, so no line could be rendered.
        # It is DELIBERATELY not returned: the refusal the product owes for signing against
        # a non-existent obligation is the disposition's own, and reporting the fixture's
        # foreign key instead would make the differential agree on a code the gate never
        # raised. Attempt the signature and report what the gate says.
        self._run(
            f"INSERT INTO {SCHEMA}.exposure_line (receipt_id, check_id, payload_digest, tokens) "  # noqa: S608
            "VALUES (%s, %s, %s, 100)",
            (receipt, cid, b"\x55" * 32),
        )
        signed = self._sign(cid, did, receipt, expired=expired)
        if isinstance(signed, Refuse):
            return signed
        return self._record_transition(
            self.subject_of(cid), "checks_materialised", "dispositioned", "p.open_blocking = 0"
        )

    def subject_of(self, cid: uuid.UUID) -> uuid.UUID:
        """Return the subject an obligation blocks, read from the row the trigger projected.

        Read rather than remembered: the disposition's ``permit_id`` is a projection of the
        obligation's, so a harness that carried its own copy could record a transition
        against a subject the database never associated with the signature.
        """
        row = self.conn.execute(
            f"SELECT permit_id FROM {SCHEMA}.blocking_check WHERE check_id = %s",  # noqa: S608
            (cid,),
        ).fetchone()
        # Two assertions, not one: "no such check" and "a check naming no permit" are
        # different faults and a combined message would name neither.
        assert row is not None, (  # noqa: S101
            f"no blocking check {cid}: the signature was accepted against an obligation "
            "the database does not hold, which the projection trigger makes impossible"
        )
        assert row[0] is not None, (  # noqa: S101
            f"blocking check {cid} names no permit, but the signature was accepted; "
            "`exactly_one_subject` makes that row unrepresentable"
        )
        return uuid.UUID(str(row[0]))

    def _sign(
        self, cid: uuid.UUID, did: uuid.UUID, receipt: uuid.UUID, *, expired: bool
    ) -> Verdict:
        expires = "now() - INTERVAL '1 hour'" if expired else "NULL"
        return self._run(
            f"INSERT INTO {SCHEMA}.disposition (disposition_id, check_id, receipt_id, "  # noqa: S608
            "subject_kind, permit_id, site_id, kind, virulence, closure_gen, defeater_code, "
            "defeater_vocab_sha256, rationale, evidence_sha256, signer_sub, signer_rank, "
            "signer_org, signer_credential_id, signature_alg, authenticator_data, "
            "client_data_json, user_verified, competency_snapshot, competency_source_id, "
            "competency_sha256, req_compensating, req_second_signer, req_foreign_org, "
            "req_predicate, req_reassert, min_signer_rank, expires_at, deliberation_seconds, "
            "evidence_opened, prior_override_count, severity_snapshot) "
            # Every projected column below is supplied as a LIE and overwritten: subject
            # 'change_request', virulence 'routine', signer_rank 9, min_signer_rank 1,
            # every requirement false. If any projection stopped firing, one of the
            # composite keys or the rank floor would refuse and the differential would see
            # a disagreement rather than a silent pass.
            "VALUES (%s, %s, %s, 'change_request', %s, %s, 'applied', 'routine', 0, 'DEF-1', "
            f"%s, %s, %s, %s, 9, 'nowhere', %s, 'ES256', %s, %s, true, '{{}}', %s, %s, "
            f"false, false, false, false, false, 1, {expires}, 0, true, 0, 0)",
            (
                did,
                cid,
                receipt,
                None,
                self.fixture.site_id,
                b"\x66" * 32,
                _RATIONALE,
                b"\x77" * 32,
                self.fixture.signer_sub,
                self.fixture.credential_id,
                b"\x01",
                b"\x02",
                uuid.uuid4(),
                b"\x88" * 32,
            ),
        )

    def retract(self, did: uuid.UUID, by: uuid.UUID) -> Verdict:
        """Apply the single permitted UPDATE: re-open the obligation, move the epoch."""
        return self._run(
            f"UPDATE {SCHEMA}.disposition SET retracted_by = %s WHERE disposition_id = %s",  # noqa: S608
            (by, did),
        )

    def suspend(self, sid: uuid.UUID) -> Verdict:
        """Append the merged → suspended event and move the head. 23503 from anywhere else."""
        appended = self._run(
            f"INSERT INTO {SCHEMA}.permit_event (permit_id, seq, prev_seq, from_state, "  # noqa: S608
            "to_state, subject_kind, actor_sub, payload, prev_digest) "
            "SELECT p.permit_id, p.head_seq + 1, p.head_seq, p.state, 'suspended', 'permit', "
            "%s, '{}'::JSONB, coalesce((SELECT e.chain_digest "
            f"  FROM {SCHEMA}.permit_event e "
            "   WHERE e.permit_id = p.permit_id AND e.seq = p.head_seq), "
            "  decode(repeat('00', 32), 'hex')) "
            f"FROM {SCHEMA}.permit p WHERE p.permit_id = %s",
            (self.fixture.signer_sub, sid),
        )
        if isinstance(appended, Refuse):
            return appended
        return self._run(
            f"UPDATE {SCHEMA}.permit SET state = 'suspended', head_seq = head_seq + 1 "  # noqa: S608
            "WHERE permit_id = %s",
            (sid,),
        )

    def attempt_merge(self, sid: uuid.UUID) -> Verdict:
        """``CALL trappoint_ref.merge_permit(...)`` — one round trip, one transaction."""
        return self._run(
            f"CALL {SCHEMA}.merge_permit(%s, %s, %s, 'service', %s, %s, 1::INT2, %s)",
            (
                sid,
                uuid.uuid4().bytes + uuid.uuid4().bytes,
                self.fixture.signer_sub,
                "{}",
                b"\x00",
                b"\x00" * 32,
            ),
        )
