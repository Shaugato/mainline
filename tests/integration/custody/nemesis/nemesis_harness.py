# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The nemesis lane's shared vocabulary: the reduced fixture, the context, the recorder.

**Why this module exists, and why it is not ``conftest.py``.**

Until 2026-08-10 the three attack modules in this directory reached these three names by
writing ``from conftest import NemesisContext, OutcomeRecorder``. Under pytest's default
``prepend`` import mode a ``conftest.py`` with no ``__init__.py`` beside it is imported
under the bare top-level name ``conftest``, and **every one of the repository's thirty-odd
conftest files claims that same name**. Whichever directory pytest reaches first wins
``sys.modules["conftest"]`` and the later ones silently replace it. Run
``31388699452`` measured the consequence exactly: the module-level import bound the right
module during collection, and by the time
``test_ledger_attacks.py::test_fixture_names_the_same_constraints_as_the_migrations``
executed its *function-level* ``from conftest import FIXTURE_DDL`` the name had been
rebound to ``packages/trappoint-sql/tests/conftest.py`` and the import failed.

The failure is the lucky case. The dangerous case is the one that does not raise: a
sibling conftest that happens to export a name we also export would have bound a
DIFFERENT object and the attack suite would have gone on passing against it. A test that
imports the wrong helper and passes is worse than one that fails.

So the shared vocabulary lives here, under a name that is unique in the repository, and
``conftest.py`` keeps only what pytest itself must own: fixtures and hooks. This module
sits beside ``attacks.py`` and ``matrix.py``, which are already imported by name from
this directory for the same reason — they are collaborators of the suite, not test
modules, and pytest does not collect them.

Nothing here touches a database or a fixture. It is the DDL string, the shape of one
seeded context, and the collector that the attack matrix is generated from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# =======================================================================================
# THE REDUCED FIXTURE SCHEMA
# =======================================================================================
#
# `verticals/mainline/db/migrations/**` is the datamodel lead's exclusive territory and is
# the authoritative DDL. This is a REDUCTION of it to the objects the fifteen attacks
# touch, so a disposable node stands up in a second rather than applying 200+ migrations
# that pull in enums, seeds, vector indexes and half the recall schema.
#
# THE REDUCTION IS GUARDED, NOT PROMISED. `test_ledger_attacks.py::
# test_fixture_names_the_same_constraints_as_the_migrations` reads BOTH this string and the
# migration files and fails if the constraint names on the three ledger tables diverge.
# Those names are an interface — CU-2's retry predicate matches on `ledger_leaf_pkey` and
# `ledger_linear` — and a fixture that drifted would let attacks pass against names the
# database does not use.
#
# WHAT IS REDUCED, and why each reduction is safe for what these attacks assert:
#
#   * `mainline.permit`, `blocking_check`, `disposition`, `permit_clause` keep only the
#     columns the merge gate reads. A13's assertion is that the gate REFUSES, that the
#     bypass SUCCEEDS after DISABLE TRIGGER, and that check 11 sees the difference — none
#     of which depends on the columns removed.
#   * `fn_permit_merge_gate` keeps step 1 (re-derive the open obligation count from the base
#     tables and refuse when the projection disagrees) and drops steps 2-4. Step 1 is the
#     mechanism A13 disables; the others refuse different writes and have their own lanes.
#   * `clause_blame_closure` drops the FK to `clause_version` and the inverted index. A10
#     attacks `max_severity`, and check 14 reads generations and severities only.
#   * `ledger_node` is absent: every Merkle proof in this lane is recomputed in Python from
#     the leaf hashes actually present, which is what a stranger's verifier does.
#   * The vertical's enum types are created here because `permit_event.from_state` needs
#     one; the values are copied from migration 0011 and 0013.

FIXTURE_DDL = """
CREATE SCHEMA IF NOT EXISTS mainline;
--
CREATE SCHEMA IF NOT EXISTS mainline_ops;
--
CREATE TYPE mainline.virulence_class AS ENUM ('routine', 'serious', 'blood_major', 'blood_fatal');
--
CREATE TYPE mainline.subject_state AS ENUM ('draft', 'proposed', 'permitted', 'merged', 'closed');
--
CREATE TABLE mainline.site (
  site_id      UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_code    STRING      NOT NULL,
  site_role    NAME        NOT NULL,
  tenant_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
  taxonomy_ver INT4        NOT NULL DEFAULT 1,
  opened_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT site_pk PRIMARY KEY (site_id),
  CONSTRAINT site_code_unique UNIQUE (site_code),
  CONSTRAINT site_role_unique UNIQUE (site_role),
  CONSTRAINT site_code_stated CHECK (site_code <> ''),
  CONSTRAINT site_code_is_lower_case CHECK (site_code = lower(site_code)),
  CONSTRAINT taxonomy_ver_positive CHECK (taxonomy_ver >= 1)
);
--
CREATE TABLE mainline.ledger_intake (
  entry_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_code   STRING      NOT NULL,
  entry_kind  STRING      NOT NULL,
  subject_id  UUID        NOT NULL,
  actor       STRING      NOT NULL,
  actor_kind  STRING      NOT NULL,
  payload     JSONB       NOT NULL,
  canon_bytes BYTES       NOT NULL,
  payload_ver INT2        NOT NULL,
  leaf_hash   BYTES       NOT NULL,
  is_sandbox  BOOL        NOT NULL DEFAULT false,
  hlc         DECIMAL     NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ledger_intake_pkey PRIMARY KEY (entry_id),
  CONSTRAINT intake_site_entry_unique UNIQUE (site_code, entry_id),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT actor_kind_known
    CHECK (actor_kind IN ('human', 'agent', 'service', 'external')),
  CONSTRAINT entry_kind_stated CHECK (entry_kind <> ''),
  CONSTRAINT actor_stated CHECK (actor <> ''),
  CONSTRAINT payload_ver_positive CHECK (payload_ver >= 1),
  CONSTRAINT canon_bytes_present CHECK (length(canon_bytes) > 0),
  CONSTRAINT leaf_hash_is_sha256 CHECK (length(leaf_hash) = 32),
  INDEX by_site_hlc (site_code, hlc ASC)
);
--
CREATE TABLE mainline.ledger_leaf (
  site_code      STRING NOT NULL,
  seq            INT8   NOT NULL,
  entry_id       UUID   NOT NULL,
  leaf_hash      BYTES  NOT NULL,
  prev_link_hash BYTES  NOT NULL,
  link_hash      BYTES  NOT NULL,
  batch_id       UUID   NOT NULL,
  CONSTRAINT ledger_leaf_pkey PRIMARY KEY (site_code, seq),
  CONSTRAINT ledger_linear UNIQUE (site_code, prev_link_hash),
  CONSTRAINT ledger_leaf_entry_unique UNIQUE (site_code, entry_id),
  CONSTRAINT fk_intake FOREIGN KEY (site_code, entry_id)
    REFERENCES mainline.ledger_intake (site_code, entry_id),
  CONSTRAINT seq_zero_based CHECK (seq >= 0),
  CONSTRAINT leaf_hash_is_sha256 CHECK (length(leaf_hash) = 32),
  CONSTRAINT prev_link_hash_is_sha256 CHECK (length(prev_link_hash) = 32),
  CONSTRAINT link_hash_is_sha256 CHECK (length(link_hash) = 32)
);
--
CREATE TABLE mainline.ledger_checkpoint (
  site_code        STRING      NOT NULL,
  tree_size        INT8        NOT NULL,
  root_hash        BYTES       NOT NULL,
  body             STRING      NOT NULL,
  beacon           JSONB       NOT NULL,
  log_sig          BYTES       NOT NULL,
  tsa_token        BYTES       NULL,
  s3_version       STRING      NULL,
  canon_src_sha256 BYTES       NOT NULL,
  admissible       BOOL        NOT NULL DEFAULT false,
  issued_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ledger_checkpoint_pkey PRIMARY KEY (site_code, tree_size),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT tree_size_non_negative CHECK (tree_size >= 0),
  CONSTRAINT root_hash_is_sha256 CHECK (length(root_hash) = 32),
  CONSTRAINT canon_src_is_sha256 CHECK (length(canon_src_sha256) = 32),
  CONSTRAINT body_stated CHECK (body <> ''),
  CONSTRAINT log_sig_present CHECK (length(log_sig) > 0),
  CONSTRAINT tsa_token_present_if_stated CHECK (tsa_token IS NULL OR length(tsa_token) > 0),
  CONSTRAINT s3_version_stated_if_present CHECK (s3_version IS NULL OR s3_version <> '')
);
--
CREATE TABLE mainline.cosignature (
  site_code    STRING      NOT NULL,
  tree_size    INT8        NOT NULL,
  witness_id   STRING      NOT NULL,
  trust_domain STRING      NOT NULL,
  adverse      BOOL        NOT NULL,
  sig          BYTES       NOT NULL,
  received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT cosignature_pkey PRIMARY KEY (site_code, tree_size, witness_id),
  CONSTRAINT fk_cp FOREIGN KEY (site_code, tree_size)
    REFERENCES mainline.ledger_checkpoint (site_code, tree_size),
  CONSTRAINT trust_domain_known
    CHECK (trust_domain IN ('regulator', 'insurer', 'union_hsr', 'external_auditor', 'operator')),
  CONSTRAINT operator_is_never_adverse
    CHECK (trust_domain <> 'operator' OR NOT adverse),
  CONSTRAINT witness_id_stated CHECK (witness_id <> ''),
  CONSTRAINT sig_present CHECK (length(sig) > 0)
);
--
CREATE TABLE mainline.clause_blame_closure (
  clause_uuid     UUID        NOT NULL,
  as_of_commit    BYTES       NOT NULL,
  closure_gen     INT8        NOT NULL,
  site_id         UUID        NOT NULL,
  ancestor_events UUID[]      NOT NULL,
  ancestor_count  INT4        NOT NULL,
  max_severity    INT2        NOT NULL,
  virulence       mainline.virulence_class NOT NULL,
  depth           INT4        NOT NULL,
  truncated       BOOL        NOT NULL DEFAULT false,
  computed_by     STRING      NOT NULL,
  projector_ver   STRING      NOT NULL,
  computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT clause_blame_closure_pk PRIMARY KEY (clause_uuid, as_of_commit, closure_gen),
  CONSTRAINT sev_range CHECK (max_severity BETWEEN 0 AND 5),
  CONSTRAINT gen_positive CHECK (closure_gen >= 0),
  CONSTRAINT depth_nonneg CHECK (depth >= 0),
  CONSTRAINT depth_within_cap CHECK (depth <= 64),
  CONSTRAINT ancestor_count_nonneg CHECK (ancestor_count >= 0),
  CONSTRAINT ancestor_count_within_cap CHECK (ancestor_count <= 512),
  CONSTRAINT truncation_is_declared
    CHECK (truncated = true OR (ancestor_count < 512 AND depth < 64)),
  CONSTRAINT count_matches_the_array
    CHECK (ancestor_count = coalesce(array_length(ancestor_events, 1), 0)),
  CONSTRAINT as_of_commit_is_sha256 CHECK (length(as_of_commit) = 32),
  CONSTRAINT computed_by_stated CHECK (computed_by <> ''),
  CONSTRAINT projector_ver_stated CHECK (projector_ver <> '')
);
--
CREATE TABLE mainline.permit (
  permit_id     UUID   NOT NULL DEFAULT gen_random_uuid(),
  site_code     STRING NOT NULL,
  state         mainline.subject_state NOT NULL DEFAULT 'draft',
  open_blocking INT8   NOT NULL DEFAULT 0,
  gate_epoch    INT8   NOT NULL DEFAULT 0,
  CONSTRAINT permit_pkey PRIMARY KEY (permit_id),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT open_blocking_nonneg CHECK (open_blocking >= 0)
);
--
CREATE TABLE mainline.blocking_check (
  check_id    UUID   NOT NULL DEFAULT gen_random_uuid(),
  permit_id   UUID   NOT NULL REFERENCES mainline.permit (permit_id),
  clause_uuid UUID   NOT NULL,
  severity    INT2   NOT NULL,
  origin      STRING NOT NULL,
  CONSTRAINT pk_blocking_check PRIMARY KEY (check_id),
  CONSTRAINT bc_severity_range CHECK (severity BETWEEN 0 AND 5)
);
--
CREATE TABLE mainline.disposition (
  disposition_id UUID        NOT NULL DEFAULT gen_random_uuid(),
  check_id       UUID        NOT NULL REFERENCES mainline.blocking_check (check_id),
  retracted_by   UUID        NULL,
  expires_at     TIMESTAMPTZ NULL,
  CONSTRAINT pk_disposition PRIMARY KEY (disposition_id)
);
--
CREATE TABLE mainline.permit_event (
  permit_id     UUID   NOT NULL,
  seq           INT8   NOT NULL,
  prev_seq      INT8   NOT NULL,
  from_state    mainline.subject_state NOT NULL,
  to_state      mainline.subject_state NOT NULL,
  subject_kind  STRING NOT NULL DEFAULT 'permit',
  actor_sub     STRING NOT NULL,
  payload       JSONB  NOT NULL,
  prev_digest   BYTES  NOT NULL,
  at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  chain_digest  BYTES  AS (digest(prev_digest || payload::STRING::BYTES, 'sha256')) STORED,
  CONSTRAINT permit_event_kind_pinned CHECK (subject_kind = 'permit'),
  CONSTRAINT permit_event_seq_ordered CHECK (seq > prev_seq AND prev_seq >= 0),
  CONSTRAINT permit_event_prev_digest_sized CHECK (length(prev_digest) = 32),
  CONSTRAINT permit_event_actor_stated CHECK (actor_sub <> ''),
  CONSTRAINT fk_permit_event_subject FOREIGN KEY (permit_id)
    REFERENCES mainline.permit (permit_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT pk_permit_event PRIMARY KEY (permit_id, seq),
  CONSTRAINT linear UNIQUE (permit_id, prev_seq)
);
--
CREATE FUNCTION mainline.fn_refuse_mutation() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='P0001',
    MESSAGE='MAINLINE: this table is append-only; write a new row';
END $$;
--
CREATE FUNCTION mainline.fn_permit_event_chain() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_existing INT8;
  v_expected BYTES;
BEGIN
  IF (NEW).seq = 0 THEN
    RETURN NEW;
  END IF;
  SELECT count(*) INTO v_existing
    FROM mainline.permit_event e0
   WHERE e0.permit_id = (NEW).permit_id;
  IF v_existing = 0 THEN
    RETURN NEW;
  END IF;
  SELECT e.chain_digest INTO v_expected
    FROM mainline.permit_event e
   WHERE e.permit_id = (NEW).permit_id
     AND e.seq = (NEW).prev_seq;
  IF v_expected IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no predecessor event for the declared prev_seq';
  END IF;
  IF v_expected IS DISTINCT FROM (NEW).prev_digest THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: prev_digest does not match the predecessor chain digest';
  END IF;
  RETURN NEW;
END $$;
--
CREATE FUNCTION mainline.fn_permit_merge_gate() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_subject   UUID;
  v_projected INT8;
  v_derived   INT8;
BEGIN
  v_subject   := (NEW).permit_id;
  v_projected := (NEW).open_blocking;
  SELECT count(*) INTO v_derived
    FROM mainline.blocking_check bc
   WHERE bc.permit_id = v_subject
     AND NOT EXISTS (
           SELECT 1 FROM mainline.disposition d
            WHERE d.check_id = bc.check_id
              AND d.retracted_by IS NULL
              AND (d.expires_at IS NULL OR d.expires_at > now()));
  IF v_derived <> 0 AND v_projected = 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: merge refused by mainline.fn_permit_merge_gate'
                || ' — re-derived open obligation count is '
                || v_derived::STRING || ' while the projected counter reads zero';
  END IF;
  IF v_derived <> 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: merge refused by mainline.fn_permit_merge_gate'
                || ' — ' || v_derived::STRING || ' open obligation(s) carry no live disposition';
  END IF;
  RETURN NEW;
END $$;
--
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON mainline.clause_blame_closure
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_refuse_mutation();
--
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON mainline.permit_event
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_refuse_mutation();
--
CREATE TRIGGER permit_event_chain BEFORE INSERT ON mainline.permit_event
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_permit_event_chain();
--
CREATE TRIGGER permit_merge_gate BEFORE UPDATE ON mainline.permit
  FOR EACH ROW WHEN ((NEW).state = 'merged' AND (OLD).state <> 'merged')
  EXECUTE FUNCTION mainline.fn_permit_merge_gate();
"""


#: The separator between statements in :data:`FIXTURE_DDL`. A bare ``;`` split would cut
#: every PL/pgSQL body in half, because a trigger function's body contains semicolons.
_DDL_SEPARATOR = "\n--\n"


def fixture_statements() -> list[str]:
    """Split the fixture DDL on its ``--`` separator lines.

    A ``;`` split would cut every PL/pgSQL body in half, so the separator is explicit.
    """
    chunks = FIXTURE_DDL.split(_DDL_SEPARATOR)
    return [chunk.strip().rstrip(";").strip() for chunk in chunks if chunk.strip()]


# =======================================================================================
# One seeded, attackable database
# =======================================================================================


@dataclass
class NemesisContext:
    """One throwaway database, seeded from the reference bundle, ready to be attacked."""

    conn: Any
    dsn: str
    site_code: str
    reference: dict[str, Any]
    provenance: str
    live_triggerdefs: dict[str, str] = field(default_factory=dict)

    def sql(self, statement: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """Execute one statement and return its rows, or ``[]`` when it returns none."""
        cur = self.conn.cursor()
        cur.execute(statement, params)
        return cur.fetchall() if cur.description else []

    def capture_triggerdefs(self) -> dict[str, str]:
        """Read the live trigger definitions straight out of the catalogue — ENABLED ONLY.

        GT-05 is answered: ``pg_get_triggerdef()`` works on CockroachDB v26.2.5, so check 11
        keeps per-trigger granularity and never falls back to ``SHOW CREATE TABLE``.

        ``tgenabled = 'D'`` is excluded, and that exclusion is the whole of A13's detection.
        ``ALTER TABLE … DISABLE TRIGGER`` leaves the row in ``pg_trigger`` with its
        definition text untouched, so a check that read ``pg_get_triggerdef()`` alone would
        report a gate that has stopped running as present and correct — a verifier that
        passes because it did not look.
        """
        rows = self.sql(
            "SELECT c.relname || '.' || t.tgname, t.tgenabled, pg_get_triggerdef(t.oid) "
            "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE NOT t.tgisinternal"
        )
        self.live_triggerdefs = {
            str(name): str(definition) for name, enabled, definition in rows if str(enabled) != "D"
        }
        return self.live_triggerdefs


# =======================================================================================
# The run record — what the matrix is generated FROM
# =======================================================================================


class OutcomeRecorder:
    """Collects one :class:`attacks.AttackOutcome` per attack and writes the run record.

    The matrix is generated from THIS, never from ``spec/custody/attacks.yaml``: the
    registry records what we expect, and an expectation printed as a result is the exact
    dishonesty the ATTACK-DEPTH artefact exists to remove.
    """

    def __init__(self) -> None:
        """Start with no outcomes and no environment facts."""
        self.outcomes: dict[str, dict[str, Any]] = {}
        self.environment: dict[str, Any] = {}

    def record(self, outcome: Any) -> None:
        """Store one attack outcome, keyed by its attack id."""
        self.outcomes[outcome.id] = outcome.as_dict()

    def write(self, destination: Path) -> None:
        """Write the run record to ``destination``, or do nothing if no attack ran.

        The destination is passed in rather than held here: this module holds the shape
        of the record and ``conftest.py`` — the half that knows it is inside a pytest
        session — holds where the session's evidence lands.
        """
        if not self.outcomes:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "attacks": [self.outcomes[key] for key in sorted(self.outcomes, key=_attack_sort_key)],
            "environment": self.environment,
            "schema_version": 1,
        }
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _attack_sort_key(attack_id: str) -> int:
    return int(attack_id.lstrip("A"))
