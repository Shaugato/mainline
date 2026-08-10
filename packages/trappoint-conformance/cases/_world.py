# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Building the legal world an illegal history is illegal *in*.

Every case in this corpus has the same shape and the shape is the argument:

1. **Setup** — a world that is entirely legal, built statement by statement in autocommit,
   outside the history. If a setup statement is refused, the case is broken, not the
   database, and it says so in those words.
2. **The history** — the illegal part, in one transaction, through
   :meth:`trappoint_conformance.harness.Harness.run_history`.
3. **The assertion** — an exact SQLSTATE and an exact exhibit, made by the runner from the
   manifest. Where the manifest also declares ``asserts_stored_row``, the case reads the
   row back and puts what it found in :attr:`HistoryOutcome.stored`.

**Nothing here writes a projected column and expects it to survive.** Where a builder
accepts a value for a projected column — ``claim_severity``, ``claim_virulence``,
``claim_signer_rank`` — the argument exists precisely so a case can prove the value did
*not* survive. That is the difference between testing a constraint and testing the weld.

**Identifiers are deterministic.** Every id is ``uuid5`` of the case's ``site_id`` and a
tag, so a case re-run on its own lands on exactly the rows it left behind — which is the
whole point of :mod:`trappoint_conformance.site` and is lost the moment a builder reaches
for ``uuid4``.

**Nothing is torn down.** Several tables under test are append-only; a builder that
cleaned up would be exercising a delete path the product refuses to have. Disposal is the
container's job.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import sql as pgsql

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import SetupRefused
from trappoint_conformance.site import CONFORMANCE_NAMESPACE, SiteScope

from ._exhibit import normalise

__all__ = [
    "CONFORMANCE_TENANT_ID",
    "Disposition",
    "SetupRefused",
    "World",
    "digest32",
    "fail_stored",
    "long_rationale",
    "refusal",
    "table_columns",
]

# ``substantive CHECK (length(rationale) >= 120)``. A vertical policy with a number the
# customer signs, so the corpus carries one string that clears it and one that does not.
_RATIONALE = (
    "The isolation boundary was walked end to end with the responsible engineer, every "
    "stored-energy source was proved dead at the point of work, and the residual is "
    "recorded against the compensating control cited below."
)


# ``SetupRefused`` is imported from :mod:`trappoint_conformance.runner` and re-exported
# here, so every ``from ._world import SetupRefused`` in the corpus keeps working. It moved
# because the runner is the only thing that can turn it into a *result*, and a runner that
# could not name the type caught ``psycopg.Error`` and nothing else — one unbuildable world
# then aborted the entire suite. The class is declared beside the result taxonomy it feeds.

#: The deployment's tenancy. ``mainline.site.tenant_id`` is documented as CONSTANT per
#: deployment — it is the coarse-sweep vector prefix, and a C-SPANN index is used only when
#: every prefix column is constrained to a single value — so the whole corpus shares one,
#: derived deterministically from the suite's own namespace rather than minted per case.
CONFORMANCE_TENANT_ID = uuid.uuid5(CONFORMANCE_NAMESPACE, "tenant")

# Probed once per (database, schema, table) and cached: `information_schema.columns` does
# not change under a conformance run, and 71 cases asking the same question 71 times would
# be 71 round trips to learn one fact.
_COLUMNS: dict[tuple[str, str, str], frozenset[str]] = {}


def table_columns(harness: Harness, schema: str, table: str) -> frozenset[str]:
    """Return the column names ``<schema>.<table>`` actually has, or the empty set.

    **The binding decides the column list, not the corpus.** ``mainline.site`` (0020a)
    carries ``tenant_id UUID NOT NULL`` and ``taxonomy_ver INT4 NOT NULL``;
    ``trappoint_ref.site`` (``trappoint_model.refschema``) carries neither.
    ``trappoint_ref.clause`` carries ``site_id NOT NULL``; the builder used to write
    ``clause_uuid`` alone, and against the reference vertical that is a ``23502``. A
    builder that hard-codes either shape breaks the other binding, and a conformance
    runner that only works against one binding is not a conformance runner. So the shape
    is read from the catalogue once per run and the INSERT is composed from what is there.

    The empty set means the binding declares no such relation, and the builder method that
    asked is then a no-op — the case that needed the row fails on the missing relation it
    actually needs, which is the honest outcome.
    """
    try:
        database = str(harness.conn.info.dbname)
    except Exception:  # noqa: BLE001 — a stub connection has no `info`; cache per schema
        database = "<unknown>"
    key = (database, schema, table)
    cached = _COLUMNS.get(key)
    if cached is not None:
        return cached
    with harness.conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (schema, table),
        )
        present = frozenset(str(row[0]) for row in cur.fetchall())
    _COLUMNS[key] = present
    return present


def digest32(label: str) -> bytes:
    """Return a deterministic 32-byte value for a ``BYTES`` column with a length ``CHECK``."""
    return hashlib.sha256(label.encode("utf-8")).digest()


def long_rationale(suffix: str = "") -> str:
    """Return a rationale that clears the ``substantive`` floor."""
    return f"{_RATIONALE} {suffix}".strip()


def fail_stored(outcome: HistoryOutcome, detail: str) -> HistoryOutcome:
    """Turn a stored-row mismatch into a red result carrying its own diagnosis.

    A case cannot raise: the runner catches only driver errors around an implementation,
    so an ``AssertionError`` would escape as a crash and a red case would stop looking
    like a red case. Instead the exhibit is replaced by a sentence that cannot equal any
    manifest value, and the assertion the runner makes fails naming the real reason.
    """
    outcome.constraint = f"STORED-ROW MISMATCH — {detail}"
    return outcome


def refusal(
    harness: Harness,
    case_id: str,
    steps: tuple[Step, ...],
    *,
    relation: str = "",
) -> HistoryOutcome:
    """Run *steps* as one history and resolve the exhibit if it was a ``P0001``.

    *relation* is the table the history's failing statement targeted. It is only consulted
    where two rendered copies of one function raise byte-identical messages; supplying it
    everywhere costs nothing and makes the case self-describing.
    """
    outcome = harness.run_history(case_id, steps)
    normalise(outcome, relation=relation)
    return outcome


@dataclass(slots=True)
class Disposition:
    """Every column of a ``disposition`` INSERT, with the projected ones marked.

    The defaults describe a signature that clears every requirement the *strictest*
    projection can impose — rank 9, a foreign-org countersigner on a different credential,
    a compensating clause, a predicate and a reassertion date. That is deliberate: it is
    the only way to reach ``fk_clearance``, because every ``CHECK`` on the table is
    evaluated before the foreign keys and a disposition that trips one of them never gets
    far enough to be judged by the clearance lattice. Each case then *removes* exactly the
    one thing it is about.
    """

    check_id: uuid.UUID
    receipt_id: uuid.UUID
    signer_sub: str
    signer_credential_id: bytes
    kind: str = "mechanism_absent"
    disposition_id: uuid.UUID | None = None
    countersigner_sub: str | None = None
    countersigner_credential_id: bytes | None = None
    compensating_clause_uuid: uuid.UUID | None = None
    predicate_id: uuid.UUID | None = None
    reassert_by: datetime | None = None
    expires_at: datetime | None = None
    rationale: str = field(default_factory=long_rationale)
    user_verified: bool = True
    evidence_opened: bool = True
    required_anchors: int = 0
    defeater_code: str = "MECHANISM_ABSENT_PROVED"
    # ▼ PROJECTED. Supplied so the corpus can prove they do not survive the trigger.
    claim_signer_rank: int = 9
    claim_virulence: str = "routine"
    claim_severity: int = 0
    claim_min_signer_rank: int = 1
    claim_deliberation_seconds: int = 0
    claim_prior_override_count: int = 0
    # ▲

    def step(self, world: World, label: str) -> Step:
        """Render the INSERT as one :class:`Step`."""
        return world.disposition_step(self, label=label)


@dataclass(slots=True)
class World:
    """A builder bound to one case's tenancy.

    Every method executes immediately, in autocommit, and returns the identifiers the
    case needs. Nothing is batched: a setup failure must name the statement that failed.
    """

    harness: Harness
    scope: SiteScope
    schema: str

    # ── plumbing ─────────────────────────────────────────────────────────────

    @property
    def site_id(self) -> uuid.UUID:
        """The tenancy this case runs in."""
        return self.scope.site_id

    def uid(self, tag: str) -> uuid.UUID:
        """Return a deterministic identifier for *tag* within this case's tenancy."""
        return uuid.uuid5(self.site_id, tag)

    def actor(self, name: str) -> str:
        """Return a subject identifier scoped to this case.

        ``person`` and ``signing_credential`` are NOT keyed by ``site_id`` — identity is a
        substrate concern and a person is a person in every tenancy — so two cases using
        the bare string ``"signer"`` would collide on the primary key and the second would
        fail in setup. Scoping the *subject* is how the tenancy isolation reaches a table
        that has no tenancy column.
        """
        return f"{self.scope.case_id.lower()}:{name}:{str(self.site_id)[:8]}"

    def sql(self, text: str) -> pgsql.Composed:
        """Bind ``{s}`` in *text* to the profile's schema as a quoted identifier.

        The schema can arrive from ``--schema``, so it is input. It is interpolated as an
        IDENTIFIER and never as text; every value below it is a bound parameter. A
        conformance runner that could be made to execute arbitrary SQL by a command-line
        flag would be a poor advertisement for a product about refusing bad writes.
        """
        return pgsql.SQL(text).format(s=pgsql.Identifier(self.schema))  # type: ignore[arg-type]

    def run(self, label: str, text: str, params: tuple[Any, ...] = ()) -> None:
        """Execute one setup statement, or explain why the world could not be built."""
        self.run_composed(label, self.sql(text), params)

    def run_composed(
        self, label: str, statement: pgsql.Composed | pgsql.SQL, params: tuple[Any, ...] = ()
    ) -> None:
        """Execute one setup statement whose *column list* had to be composed.

        :meth:`site_row` is the only caller that needs this: its column list comes from the
        catalogue, so it cannot be a literal in a format string.
        """
        try:
            with self.harness.conn.cursor() as cur:
                cur.execute(statement, params)
        except Exception as exc:
            raise SetupRefused(
                f"{self.scope.case_id}: building the LEGAL world failed at {label!r}. "
                f"The world a case is illegal in must itself be legal, so this is a "
                f"broken case or an unmigrated schema, not a refusal. Cause: {exc}"
            ) from exc

    def read(self, text: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """Read rows back, for ``asserts_stored_row``."""
        with self.harness.conn.cursor() as cur:
            cur.execute(self.sql(text), params)
            return list(cur.fetchall())

    def scalar(self, text: str, params: tuple[Any, ...] = ()) -> Any:
        """Read exactly one value, or ``None`` when the row is absent."""
        rows = self.read(text, params)
        return rows[0][0] if rows else None

    # ── the vertical's own tables, where the substrate names them ────────────

    @property
    def site_code(self) -> str:
        """Return this case's ledger partition key: lower case, and per case.

        ``mainline.site`` carries ``CONSTRAINT site_code_is_lower_case CHECK (site_code =
        lower(site_code))``. The builder used to write ``f"CONF-{…}"``, which that CHECK
        refuses with ``23514`` — so against MAINLINE *every* case that needed a site row
        died in setup. The hex of a UUID is already lower case; the prefix is spelled to
        match.
        """
        return f"conf-{str(self.site_id)[:8]}"

    @property
    def site_role(self) -> str:
        """Return this case's RLS scope token: lower case, and per case.

        The second defect, and it only becomes visible once the first is fixed.
        ``mainline.site`` carries ``CONSTRAINT site_role_unique UNIQUE (site_role)``, and
        the builder wrote the literal ``'conf_role'`` for every case under ``ON CONFLICT DO
        NOTHING``. The first case's site row therefore inserted and *every subsequent
        case's was silently discarded* — no error, no row, and then a dozen foreign keys
        failing for a reason that has nothing to do with what the case is about. A silent
        ``ON CONFLICT`` is exactly as expensive as a wrong answer and much harder to see.

        ``NAME`` is what ``CURRENT_USER`` has, and ``site_role_is_lower_case`` compares
        through the cast, so the token is lower case here too. It is not a role that
        exists on the cluster and does not need to be: the corpus runs as an admin, and
        the cases that assert *role* behaviour (``CF-47``, ``CF-48``, ``CF-69``) provision
        their own through ``cases/_privilege.py``.
        """
        return f"conf_{str(self.site_id).replace('-', '_')[:12]}"

    def site_row(self) -> None:
        """Insert the vertical's ``site`` row, where the binding has one.

        The substrate does not own ``site`` — MR-1's object test puts it outside — but
        ``fn_closure_guard`` and ``fn_site_role`` read it, so a case that writes a closure
        needs one. Absent in a binding that does not declare the relation, in which case
        this is a no-op and the case that needed it fails on the missing relation, which
        is the honest outcome.

        **The column list is read from the catalogue, not written here.** See
        :func:`site_columns`: ``mainline.site`` requires ``tenant_id`` and
        ``taxonomy_ver`` and ``trappoint_ref.site`` does not have either, so a fixed list
        breaks one of the two bindings whichever list you pick.
        """
        # `opened_at` is deliberately not offered: MAINLINE's 0020a defaults it and its own
        # header says the default is a fixture convenience, so supplying one would be the
        # corpus asserting a commissioning date it does not know.
        self.adaptive_insert(
            "site",
            {
                "site_id": self.site_id,
                "site_code": self.site_code,
                "site_role": self.site_role,
                "tenant_id": CONFORMANCE_TENANT_ID,
                "taxonomy_ver": 1,
            },
        )

    def adaptive_insert(self, table: str, values: dict[str, Any]) -> None:
        """INSERT the subset of *values* whose columns ``<schema>.<table>`` actually has.

        Used only where the two bindings genuinely disagree about a table's shape and the
        disagreement is in columns the corpus can supply a correct value for. It is **not**
        a general escape hatch: a table whose required columns the corpus cannot fill
        honestly must fail loudly in setup — as :meth:`clause_version` does against
        MAINLINE — rather than insert a partial row and let the ``NOT NULL`` be the
        diagnosis somebody else has to trace.
        """
        present = table_columns(self.harness, self.schema, table)
        if not present:
            return
        names = [name for name in values if name in present]
        if not names:
            return
        statement = pgsql.SQL(
            "INSERT INTO {s}.{t} ({cols}) VALUES ({vals}) ON CONFLICT DO NOTHING"
        ).format(
            s=pgsql.Identifier(self.schema),
            t=pgsql.Identifier(table),
            cols=pgsql.SQL(", ").join(pgsql.Identifier(name) for name in names),
            vals=pgsql.SQL(", ").join(pgsql.Placeholder() for _ in names),
        )
        self.run_composed(table, statement, tuple(values[name] for name in names))

    def clause_row(self, tag: str = "clause") -> uuid.UUID:
        """Insert a ``clause`` row — the target of ``disposition.compensating_clause_uuid``.

        ``site_id`` is written where the binding has the column. ``trappoint_ref.clause``
        declares it ``NOT NULL`` and this builder used to omit it, so ``CF-07``, ``CF-23``
        and ``CF-71`` — the three cases that cite a compensating clause — died in setup
        with ``23502`` on the reference vertical, which is the binding the suite is
        supposed to be green against.
        """
        clause_uuid = self.uid(tag)
        self.adaptive_insert("clause", {"clause_uuid": clause_uuid, "site_id": self.site_id})
        return clause_uuid

    # ── the substrate ────────────────────────────────────────────────────────

    def clause_version(
        self, tag: str = "cv", *, control_delta: str = "weaken"
    ) -> tuple[uuid.UUID, bytes]:
        """Insert a clause version: the foreign-key target of every obligation."""
        clause_uuid = self.uid(f"{tag}:clause")
        commit_id = digest32(f"{self.site_id}:{tag}:commit")
        self.run(
            "clause_version",
            "INSERT INTO {s}.clause_version "
            "(clause_uuid, commit_id, site_id, control_delta, body_sha256) "
            "VALUES (%s, %s, %s, %s, %s)",
            (clause_uuid, commit_id, self.site_id, control_delta, digest32(f"{tag}:body")),
        )
        return clause_uuid, commit_id

    def closure(
        self,
        clause_uuid: uuid.UUID,
        commit_id: bytes,
        *,
        max_severity: int = 5,
        virulence: str = "blood_fatal",
        closure_gen: int = 0,
        ancestor_count: int = 1,
    ) -> None:
        """Write the authority source: what the blame closure actually holds for this clause.

        This is the row ``fn_check_project`` reads, and the reason a check's severity is
        not the inserter's opinion.
        """
        self.run(
            "clause_blame_closure",
            "INSERT INTO {s}.clause_blame_closure "
            "(clause_uuid, as_of_commit, closure_gen, site_id, ancestor_events, "
            " ancestor_count, max_severity, virulence, depth, computed_by, projector_ver) "
            "VALUES (%s, %s, %s, %s, ARRAY[%s]::UUID[], %s, %s, %s, 1, 'conformance', 'v1')",
            (
                clause_uuid,
                commit_id,
                closure_gen,
                self.site_id,
                self.uid(f"ancestor:{clause_uuid}"),
                ancestor_count,
                max_severity,
                virulence,
            ),
        )

    def permit(self, tag: str = "p", *, horizon_days: int = 7) -> uuid.UUID:
        """Open a permit in ``draft``: the protected branch, before anything is asked of it."""
        permit_id = self.uid(f"{tag}:permit")
        self.run(
            "permit",
            "INSERT INTO {s}.permit "
            "(permit_id, site_id, site_role, external_ref, ref_name, horizon_at) "
            "VALUES (%s, %s, %s, %s, %s, now() + (%s::INT8 * INTERVAL '1 day'))",
            (
                permit_id,
                self.site_id,
                # The SAME token as the site row's. `permit.site_role` is a denormalised
                # copy of it, and `fn_site_role` overwrites whatever a writer supplies from
                # `site` — in a binding that welds it. In MAINLINE the function ships
                # deliberately unwelded on the gated subjects (the trigger slot belongs to
                # the merge gate), so the value written here is the value that stays, and
                # writing a token that names no site row would put a forged scope token in
                # the one column this repository has a migration about not forging.
                self.site_role,
                f"{self.scope.external_ref}-{tag}",
                f"refs/permits/{self.scope.case_id.lower()}-{tag}",
                horizon_days,
            ),
        )
        return permit_id

    def change_request(self, tag: str = "cr") -> uuid.UUID:
        """Open a change request: the other gated subject, and the reason MI30 exists."""
        cr_id = self.uid(f"{tag}:cr")
        self.run(
            "change_request",
            "INSERT INTO {s}.change_request "
            "(cr_id, site_id, site_role, external_ref, ref_name, target_ref) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                cr_id,
                self.site_id,
                self.site_role,  # same reasoning as `permit`, above
                f"{self.scope.external_ref}-{tag}",
                f"refs/changes/{self.scope.case_id.lower()}-{tag}",
                "refs/heads/main",
            ),
        )
        return cr_id

    def cite(
        self,
        permit_id: uuid.UUID,
        clause_uuid: uuid.UUID,
        commit_id: bytes,
        *,
        relation: str = "weakens",
    ) -> None:
        """Cite a clause version from the permit. The merge gate reads this to fail closed."""
        self.run(
            "permit_clause",
            "INSERT INTO {s}.permit_clause (permit_id, clause_uuid, commit_id, relation) "
            "VALUES (%s, %s, %s, %s)",
            (permit_id, clause_uuid, commit_id, relation),
        )

    def cite_cr(
        self,
        cr_id: uuid.UUID,
        clause_uuid: uuid.UUID,
        commit_id: bytes,
        *,
        relation: str = "edits",
    ) -> None:
        """Cite a clause version from the change request."""
        self.run(
            "cr_clause",
            "INSERT INTO {s}.cr_clause (cr_id, clause_uuid, commit_id, relation) "
            "VALUES (%s, %s, %s, %s)",
            (cr_id, clause_uuid, commit_id, relation),
        )

    def person(
        self,
        sub: str,
        *,
        rank: int = 9,
        org: str = "conf-operator",
        authorisations: tuple[str, ...] = ("ISOLATION_AUTHORITY",),
    ) -> str:
        """Enrol a competency record. Absence of one refuses the signature (MI27, CF-20)."""
        snapshot = json.dumps({"authorisations": list(authorisations), "rank": rank})
        self.run(
            "person",
            "INSERT INTO {s}.person "
            "(signer_sub, effective_from, org, rank, competency_source_id, "
            " competency_sha256, competency_snapshot, identity_source, enrolment_assurance) "
            "VALUES (%s, now() - INTERVAL '1 day', %s, %s, %s, %s, %s::JSONB, %s, %s)",
            (
                sub,
                org,
                rank,
                self.uid(f"competency:{sub}"),
                digest32(f"competency:{sub}:{rank}:{org}"),
                snapshot,
                "conformance-corpus",
                "hr_system_of_record",
            ),
        )
        return sub

    def credential(self, sub: str, *, tag: str = "k") -> bytes:
        """Enrol a signing credential. ``distinct_credential`` is why a case may need two."""
        credential_id = digest32(f"{self.site_id}:{sub}:{tag}")
        self.run(
            "signing_credential",
            "INSERT INTO {s}.signing_credential "
            "(credential_id, signer_sub, public_key_cose, aaguid, transports, attachment, "
            " enrolment_assurance) "
            "VALUES (%s, %s, %s, %s, ARRAY['usb']::STRING[], 'cross-platform', %s)",
            (
                credential_id,
                sub,
                digest32(f"cose:{sub}:{tag}"),
                digest32(f"aaguid:{tag}")[:16],
                "hr_system_of_record",
            ),
        )
        return credential_id

    def check(
        self,
        *,
        clause_uuid: uuid.UUID,
        commit_id: bytes,
        permit_id: uuid.UUID | None = None,
        cr_id: uuid.UUID | None = None,
        origin: str = "weaken_over_blood",
        claim_severity: int = 1,
        claim_virulence: str = "routine",
        precursor_event_id: uuid.UUID | None = None,
        subject_kind: str | None = None,
        tag: str = "bc",
    ) -> uuid.UUID:
        """Materialise one obligation, and let the projection overwrite what it claims.

        ``claim_severity`` and ``claim_virulence`` are what the *inserter* says. They are
        supplied on purpose and they are supposed to be thrown away: ``fn_check_project``
        rewrites both from the blame closure before the row lands.
        """
        check_id = self.uid(f"{tag}:check")
        kind = subject_kind or ("permit" if permit_id is not None else "change_request")
        self.run(
            "blocking_check",
            "INSERT INTO {s}.blocking_check "
            "(check_id, subject_kind, permit_id, cr_id, site_id, clause_uuid, commit_id, "
            " precursor_event_id, origin, severity, virulence, closure_gen, evidence_summary) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)",
            (
                check_id,
                kind,
                permit_id,
                cr_id,
                self.site_id,
                clause_uuid,
                commit_id,
                precursor_event_id,
                origin,
                claim_severity,
                claim_virulence,
                f"conformance {self.scope.case_id}: one precursor",
            ),
        )
        return check_id

    def check_step(
        self,
        label: str,
        *,
        clause_uuid: uuid.UUID,
        commit_id: bytes,
        permit_id: uuid.UUID | None = None,
        cr_id: uuid.UUID | None = None,
        origin: str = "weaken_over_blood",
        claim_severity: int = 1,
        claim_virulence: str = "routine",
        precursor_event_id: uuid.UUID | None = None,
        subject_kind: str | None = None,
        check_id: uuid.UUID | None = None,
        on_conflict_skip: bool = False,
    ) -> Step:
        """Render the same INSERT, as a history step rather than as setup."""
        kind = subject_kind or ("permit" if permit_id is not None else "change_request")
        tail = " ON CONFLICT (dedupe_key) DO NOTHING" if on_conflict_skip else ""
        return Step(
            label=label,
            sql=self.sql(
                "INSERT INTO {s}.blocking_check "
                "(check_id, subject_kind, permit_id, cr_id, site_id, clause_uuid, commit_id, "
                " precursor_event_id, origin, severity, virulence, closure_gen, evidence_summary) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)" + tail
            ),
            params=(
                check_id or uuid.uuid4(),
                kind,
                permit_id,
                cr_id,
                self.site_id,
                clause_uuid,
                commit_id,
                precursor_event_id,
                origin,
                claim_severity,
                claim_virulence,
                f"conformance {self.scope.case_id}: one precursor",
            ),
        )

    def receipt(
        self,
        *,
        actor_sub: str,
        permit_id: uuid.UUID | None = None,
        cr_id: uuid.UUID | None = None,
        issued_ago_seconds: int = 3600,
        expires_in_seconds: int = 3600,
        total_tokens: int = 1,
        tag: str = "r",
    ) -> uuid.UUID:
        """Issue a receipt: what the substrate showed this actor, and when the server showed it.

        ``issued_ago_seconds`` defaults to an hour for one reason and it is not
        cosmetic. ``fn_disposition_project`` computes ``reading_floor_met`` as
        ``now() - issued_at >= tau0 + tokens/rho``; a receipt issued in the same
        statement as the signature therefore reads *floor unmet*, which projects
        ``unmet_floor_count`` onto the subject and makes ``reading_floor_when_issued``
        refuse every merge in the corpus for a reason unrelated to the case under test.
        A world in which the human plausibly read the evidence is the world the other
        cases mean to be illegal in. ``CF-05`` sets it to zero, which is the point of
        ``CF-05``.
        """
        receipt_id = self.uid(f"{tag}:receipt")
        kind = "permit" if permit_id is not None else "change_request"
        self.run(
            "exposure_receipt",
            "INSERT INTO {s}.exposure_receipt "
            "(receipt_id, subject_kind, permit_id, cr_id, actor_sub, issued_at, issued_hlc, "
            " expires_at, corpus_root, silence_receipt_id, policy_version, total_tokens, "
            " receipt_digest) "
            "VALUES (%s, %s, %s, %s, %s, now() - (%s::INT8 * INTERVAL '1 second'), 1.0, "
            "        now() + (%s::INT8 * INTERVAL '1 second'), %s, %s, %s, %s, %s)",
            (
                receipt_id,
                kind,
                permit_id,
                cr_id,
                actor_sub,
                issued_ago_seconds,
                expires_in_seconds,
                digest32(f"corpus:{tag}"),
                self.uid(f"{tag}:silence"),
                "rp-1.0",
                total_tokens,
                digest32(f"receipt:{tag}"),
            ),
        )
        return receipt_id

    def line(self, receipt_id: uuid.UUID, check_id: uuid.UUID, *, tokens: int = 1) -> None:
        """Record that this obligation was rendered to that actor, in that receipt.

        The composite ``fk_exposure`` key points here, so this row is the difference
        between a session and evidence.
        """
        self.run(
            "exposure_line",
            "INSERT INTO {s}.exposure_line (receipt_id, check_id, payload_digest, tokens) "
            "VALUES (%s, %s, %s, %s)",
            (receipt_id, check_id, digest32(f"line:{check_id}"), tokens),
        )

    # ── the disposition, which every clearance case is a variation on ────────

    _DISPOSITION_SQL = (
        "INSERT INTO {s}.disposition "
        "(disposition_id, check_id, receipt_id, subject_kind, permit_id, cr_id, site_id, "
        " kind, virulence, closure_gen, defeater_code, defeater_vocab_sha256, rationale, "
        " evidence_sha256, signer_sub, signer_rank, signer_org, signer_credential_id, "
        " countersigner_sub, countersigner_rank, countersigner_org, "
        " countersigner_credential_id, signature_alg, authenticator_data, client_data_json, "
        " user_verified, competency_snapshot, competency_source_id, competency_sha256, "
        " req_compensating, req_second_signer, req_foreign_org, req_predicate, req_reassert, "
        " min_signer_rank, max_ttl_hours, compensating_clause_uuid, predicate_id, "
        " reassert_by, expires_at, required_anchors, deliberation_seconds, evidence_opened, "
        " prior_override_count, severity_snapshot) "
        "VALUES (%s, %s, %s, %s, NULL, NULL, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, "
        "        %s, NULL, NULL, %s, 'ES256', %s, %s, %s, '{{}}'::JSONB, %s, %s, "
        "        false, false, false, false, false, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )

    def disposition_params(self, draft: Disposition) -> tuple[Any, ...]:
        """Bind one :class:`Disposition` to the INSERT above."""
        return (
            draft.disposition_id or self.uid(f"disposition:{draft.check_id}:{draft.kind}"),
            draft.check_id,
            draft.receipt_id,
            # subject_kind / site_id are PROJECTED from the check; a deliberately wrong
            # value here is how CF-07's sibling claims are checked.
            "permit",
            self.site_id,
            draft.kind,
            draft.claim_virulence,
            draft.defeater_code,
            digest32("vocab:conformance"),
            draft.rationale,
            digest32(f"evidence:{draft.check_id}"),
            draft.signer_sub,
            draft.claim_signer_rank,
            "claimed-org",
            draft.signer_credential_id,
            draft.countersigner_sub,
            draft.countersigner_credential_id,
            digest32("authenticator"),
            digest32("clientdata"),
            draft.user_verified,
            self.uid("competency-source-claimed"),
            digest32("competency-claimed"),
            draft.claim_min_signer_rank,
            draft.compensating_clause_uuid,
            draft.predicate_id,
            draft.reassert_by,
            draft.expires_at,
            draft.required_anchors,
            draft.claim_deliberation_seconds,
            draft.evidence_opened,
            draft.claim_prior_override_count,
            draft.claim_severity,
        )

    def disposition_step(self, draft: Disposition, *, label: str) -> Step:
        """Render the disposition INSERT as a history step."""
        return Step(
            label=label,
            sql=self.sql(self._DISPOSITION_SQL),
            params=self.disposition_params(draft),
        )

    def sign(self, draft: Disposition, *, label: str = "disposition") -> uuid.UUID:
        """Insert a disposition as **setup**, and return its id."""
        params = self.disposition_params(draft)
        self.run(label, self._DISPOSITION_SQL, params)
        return params[0]  # type: ignore[return-value]

    # ── a fully-cleared subject: the legal baseline several cases start from ──

    def cleared_permit(
        self,
        *,
        max_severity: int = 1,
        virulence: str = "routine",
        kind: str = "applied",
        signer_rank: int = 4,
        tag: str = "cleared",
    ) -> dict[str, Any]:
        """Build a permit with one obligation and one live disposition covering it.

        The state a merge is *supposed* to be attempted from. Cases that need a legal
        merge (CF-09, CF-40, CF-44) start here, so the thing they then do wrong is the
        only thing wrong.
        """
        clause_uuid, commit_id = self.clause_version(tag)
        self.closure(clause_uuid, commit_id, max_severity=max_severity, virulence=virulence)
        permit_id = self.permit(tag)
        signer = self.person(self.actor(f"signer-{tag}"), rank=signer_rank)
        credential = self.credential(signer)
        check_id = self.check(
            clause_uuid=clause_uuid, commit_id=commit_id, permit_id=permit_id, tag=tag
        )
        receipt_id = self.receipt(actor_sub=signer, permit_id=permit_id, tag=tag)
        self.line(receipt_id, check_id)
        disposition_id = self.sign(
            Disposition(
                check_id=check_id,
                receipt_id=receipt_id,
                signer_sub=signer,
                signer_credential_id=credential,
                kind=kind,
                claim_signer_rank=signer_rank,
            )
        )
        self.walk_to_dispositioned(permit_id)
        return {
            "clause_uuid": clause_uuid,
            "commit_id": commit_id,
            "permit_id": permit_id,
            "signer": signer,
            "credential": credential,
            "check_id": check_id,
            "receipt_id": receipt_id,
            "disposition_id": disposition_id,
        }

    def walk_to_dispositioned(self, permit_id: uuid.UUID) -> None:
        """Walk a permit up to ``dispositioned``, chain and all.

        ``merge_permit`` appends ``(state -> 'merged')`` to the event chain, and
        ``legal_edge`` is a foreign key into ``subject_transition``: ``(permit, draft,
        merged)`` is **not** in the seed, so a permit that has never been walked cannot be
        merged through the procedure. That is ``CF-13`` working, and it means every case
        that needs a *legal* merge has to build a legal lifecycle first rather than
        teleporting the subject to the state it wants.

        The direct-UPDATE spelling (:meth:`merge_step`) does not go through the chain and
        does not need this — which is exactly why the table's own ``CHECK`` constraints,
        and not the transition table, are what the product rests on.
        """
        self.append_event(
            "walk: draft -> checks_materialised",
            permit_id,
            seq=1,
            prev_seq=0,
            from_state="draft",
            to_state="checks_materialised",
        )
        self.append_event(
            "walk: checks_materialised -> dispositioned",
            permit_id,
            seq=2,
            prev_seq=1,
            from_state="checks_materialised",
            to_state="dispositioned",
            prev_digest=self.chain_digest(permit_id, 1),
        )
        self.run(
            "walk: move the head",
            "UPDATE {s}.permit SET state = 'dispositioned', head_seq = 2 WHERE permit_id = %s",
            (permit_id,),
        )

    def armed_permit(
        self,
        *,
        tag: str,
        max_severity: int = 1,
        virulence: str = "routine",
        signer_rank: int = 4,
        signer_org: str = "alpha-operations",
        countersigner_org: str | None = "beta-assurance",
        countersigner_rank: int = 9,
        authorisations: tuple[str, ...] = ("ISOLATION_AUTHORITY",),
        receipt_kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a permit with one open obligation, an exposure receipt, and two signers ready.

        The starting point for every clearance-lattice case: everything the disposition
        needs *except* the one thing the case is about. The countersigner is enrolled by
        default and on a different credential, because ``distinct_credential`` and
        ``needs_foreign_org`` must be satisfiable by the cases that are not about them.
        """
        clause_uuid, commit_id = self.clause_version(tag)
        self.closure(clause_uuid, commit_id, max_severity=max_severity, virulence=virulence)
        permit_id = self.permit(tag)
        signer = self.person(
            self.actor(f"signer-{tag}"),
            rank=signer_rank,
            org=signer_org,
            authorisations=authorisations,
        )
        signer_key = self.credential(signer, tag="signer")
        countersigner = None
        counter_key = None
        if countersigner_org is not None:
            countersigner = self.person(
                self.actor(f"counter-{tag}"),
                rank=countersigner_rank,
                org=countersigner_org,
                authorisations=authorisations,
            )
            counter_key = self.credential(countersigner, tag="counter")
        check_id = self.check(
            clause_uuid=clause_uuid, commit_id=commit_id, permit_id=permit_id, tag=tag
        )
        receipt_id = self.receipt(
            actor_sub=signer, permit_id=permit_id, tag=tag, **(receipt_kwargs or {})
        )
        self.line(receipt_id, check_id)
        return {
            "clause_uuid": clause_uuid,
            "commit_id": commit_id,
            "permit_id": permit_id,
            "signer": signer,
            "signer_key": signer_key,
            "countersigner": countersigner,
            "counter_key": counter_key,
            "check_id": check_id,
            "receipt_id": receipt_id,
        }

    # ── the event chain ──────────────────────────────────────────────────────

    GENESIS_DIGEST = b"\x00" * 32
    """What the merge procedures use when a subject has no predecessor event. The chain
    starts somewhere and the starting point is a stated constant, not a NULL."""

    def _event_sql(self, table: str, key: str) -> str:
        # S608 is about interpolating *input* into SQL. `table` and `key` are
        # chosen from a two-element literal map five lines above; every VALUE is a
        # bound parameter and the schema arrives as a quoted identifier.
        return (
            f"INSERT INTO {{s}}.{table} "  # noqa: S608
            f"({key}, seq, prev_seq, from_state, to_state, subject_kind, actor_sub, "
            f" payload, prev_digest) "
            f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s::JSONB, %s)"
        )

    def event_step(
        self,
        label: str,
        subject_id: uuid.UUID,
        *,
        seq: int,
        prev_seq: int,
        from_state: str,
        to_state: str,
        prev_digest: bytes | None = None,
        payload: str = "{}",
        kind: str = "permit",
    ) -> Step:
        """One row of a subject's event chain, as a history step."""
        table, key = ("permit_event", "permit_id") if kind == "permit" else ("cr_event", "cr_id")
        return Step(
            label=label,
            sql=self.sql(self._event_sql(table, key)),
            params=(
                subject_id,
                seq,
                prev_seq,
                from_state,
                to_state,
                kind,
                f"conformance:{self.scope.case_id}",
                payload,
                prev_digest if prev_digest is not None else self.GENESIS_DIGEST,
            ),
        )

    def append_event(self, label: str, subject_id: uuid.UUID, **kw: Any) -> None:
        """Run the same insert, as setup."""
        step = self.event_step(label, subject_id, **kw)
        try:
            with self.harness.conn.cursor() as cur:
                cur.execute(step.sql, step.params)
        except Exception as exc:
            raise SetupRefused(
                f"{self.scope.case_id}: building the LEGAL event chain failed at {label!r}: {exc}"
            ) from exc

    def chain_digest(self, subject_id: uuid.UUID, seq: int, *, kind: str = "permit") -> bytes:
        """Read a predecessor's ``chain_digest`` back.

        Read, never recomputed. The column is a ``STORED`` generated value the server
        derives; a case that recomputed it in Python would be asserting agreement between
        two implementations of the same formula rather than following the chain.
        """
        table, key = ("permit_event", "permit_id") if kind == "permit" else ("cr_event", "cr_id")
        # Same reasoning as `_event_sql`: `table` and `key` come from a literal map,
        # never from a caller.
        value = self.scalar(
            f"SELECT chain_digest FROM {{s}}.{table} WHERE {key} = %s AND seq = %s",  # noqa: S608
            (subject_id, seq),
        )
        return bytes(value) if value is not None else self.GENESIS_DIGEST

    # ── the merge, in both spellings ─────────────────────────────────────────

    def merge_step(
        self,
        permit_id: uuid.UUID,
        *,
        label: str = "attempt the merge",
        merged_commit: bytes | None = None,
        omit_commit: bool = False,
    ) -> Step:
        """Render the completing UPDATE, straight at the table.

        This is the spelling that proves the claim: the refusal belongs to the *table*,
        so it holds for a writer who never heard of ``merge_permit`` — a DBA at a psql
        prompt, a migration, a future service nobody has written yet.
        """
        if omit_commit:
            return Step(
                label=label,
                sql=self.sql("UPDATE {s}.permit SET state = 'merged' WHERE permit_id = %s"),
                params=(permit_id,),
            )
        return Step(
            label=label,
            sql=self.sql(
                "UPDATE {s}.permit SET state = 'merged', merged_commit = %s WHERE permit_id = %s"
            ),
            params=(merged_commit or digest32("merged"), permit_id),
        )

    def merge_cr_step(
        self,
        cr_id: uuid.UUID,
        *,
        label: str = "attempt the change-request merge",
        merged_commit: bytes | None = None,
    ) -> Step:
        """Render the completing UPDATE on a change request. MI30, and the whole of CF-31."""
        return Step(
            label=label,
            sql=self.sql(
                "UPDATE {s}.change_request SET state = 'merged', merged_commit = %s "
                "WHERE cr_id = %s"
            ),
            params=(merged_commit or digest32("merged"), cr_id),
        )

    def call_merge_permit(self, permit_id: uuid.UUID, *, label: str = "CALL merge_permit") -> Step:
        """Render the procedure spelling: event append, epoch pin and head CAS in one call."""
        return Step(
            label=label,
            sql=self.sql(
                "CALL {s}.merge_permit(%s, %s, %s, 'service', '{{}}'::JSONB, %s, 1::INT2, %s)"
            ),
            params=(
                permit_id,
                digest32("merged"),
                f"conformance:{self.scope.case_id}",
                b"\x00",
                digest32("leaf"),
            ),
        )

    def call_merge_cr(self, cr_id: uuid.UUID, *, label: str = "CALL merge_change_request") -> Step:
        """Render the procedure spelling, for a change request."""
        return Step(
            label=label,
            sql=self.sql(
                "CALL {s}.merge_change_request(%s, %s, %s, 'service', '{{}}'::JSONB, %s, "
                "1::INT2, %s)"
            ),
            params=(
                cr_id,
                digest32("merged"),
                f"conformance:{self.scope.case_id}",
                b"\x00",
                digest32("leaf"),
            ),
        )

    # ── a second writer ──────────────────────────────────────────────────────

    def sibling_connection(self, *, isolation: Any = None) -> Any:
        """Open a second connection to the same cluster.

        Four cases genuinely need two writers — the materialised conflict (``CF-43``), the
        parallel merge (``CF-44``), the isolation downgrade (``CF-45``) and the unwelding
        harness — and none of them can be expressed on one connection, because the whole
        claim is about what happens when two transactions overlap.

        The DSN is taken from the connection the runner supplied, so a sibling reaches the
        same cluster as the suite by construction and there is no second place to
        configure. Callers close what they open.
        """
        import psycopg

        conn = psycopg.connect(
            self.harness.conn.info.dsn,
            autocommit=True,
            application_name="trappoint-conform:sibling",
        )
        if isolation is not None:
            conn.isolation_level = isolation
        return conn

    # ── time ─────────────────────────────────────────────────────────────────

    @staticmethod
    def soon(seconds: int = 3600) -> datetime:
        """Return a bounded future instant, for ``expires_at`` and ``reassert_by``."""
        return datetime.now(UTC) + timedelta(seconds=seconds)

    @staticmethod
    def past(seconds: int = 3600) -> datetime:
        """Return a past instant, for the expiry cases."""
        return datetime.now(UTC) - timedelta(seconds=seconds)
