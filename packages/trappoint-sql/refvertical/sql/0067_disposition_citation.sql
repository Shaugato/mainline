-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0067_disposition_citation.sql
-- CREATE TABLE trappoint_ref.disposition_citation — gist may accuse, only verbatim may acquit
--
-- MI: MI11
-- I: I11
-- COUNSEL-GATED: yes
-- RATIONALE: The evidentiary asymmetry, expressed as a table. A citation that claims to be
--            verbatim must carry an immutable object key and a span digest, so a quotation
--            can be re-fetched and re-hashed by someone who does not trust us; a gist
--            citation carries neither and is therefore never counted towards the verbatim
--            floor that a mechanism_absent or mitigated verdict has to clear.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0066_disposition.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- verbatim_needs_anchor IS THE ASYMMETRY (case CF-37). A verbatim citation asserts "the
-- source says exactly this", and that assertion is only checkable if the bytes can be
-- fetched again and re-hashed: `object_key` names the S3 Object Lock object, and
-- `span_sha256` digests the exact span. A gist citation asserts "the source is about
-- this", which is a claim about meaning that no digest can settle — so it may accuse and
-- may never acquit. `disposition.verbatim_floor` counts only the verbatim rows.
--
-- byte_range IS `INT8[]` WITH A PAIR CHECK, NOT `INT8[2]`. MEASURED, NOT ASSUMED: on
-- CockroachDB v26.2.5, `CREATE TABLE t (br INT8[2])` is accepted and `SHOW CREATE
-- TABLE` reports the column as plain `INT8[]` — the dimension bound is parsed and
-- dropped, so writing it would be a constraint that reads as enforced and is not.
-- `array_length(byte_range, 1) = 2` is the same claim, actually enforced, and it is how
-- migrations 0033 and 0035 already state it for `severity_span` and `evidence_span`.
--
-- THE CITATION IS MANDATORY, NOT OPTIONAL (ADR 0001, conservative reading). Nothing in
-- THIS table can require a row to exist — an empty table satisfies every constraint on
-- it — so the requirement is enforced where it can be: `verbatim_floor` on the
-- disposition compares a projected count against a projected floor, and the projection
-- reads this table. A CHECK here would be a comment with a semicolon after it.
--
-- clause_uuid AND commit_id ARE NULLABLE AND CARRY NO COMPOSITE FOREIGN KEY. A citation
-- may point at an S3 object that is not a clause in this repository at all — a
-- regulator's bulletin, a coroner's finding, a supplier's manual. Requiring a clause
-- version would make the most probative citations unrepresentable.

CREATE TABLE trappoint_ref.disposition_citation (
  disposition_id UUID NOT NULL REFERENCES trappoint_ref.disposition (disposition_id),
  citation_ord   INT2 NOT NULL,
  kind           STRING NOT NULL,
  object_key     STRING NULL,
  byte_range     INT8[] NULL,
  span_sha256    BYTES NULL,
  clause_uuid    UUID NULL,
  commit_id      BYTES NULL,
  CONSTRAINT citation_kind_known CHECK (kind IN ('verbatim', 'gist')),
  CONSTRAINT verbatim_needs_anchor
    CHECK (kind <> 'verbatim' OR (object_key IS NOT NULL AND span_sha256 IS NOT NULL)),
  CONSTRAINT citation_ord_positive CHECK (citation_ord >= 1),
  CONSTRAINT citation_byte_range_is_a_pair
    CHECK (byte_range IS NULL OR array_length(byte_range, 1) = 2),
  CONSTRAINT citation_span_is_sha256 CHECK (span_sha256 IS NULL OR length(span_sha256) = 32),
  CONSTRAINT citation_commit_id_is_sha256 CHECK (commit_id IS NULL OR length(commit_id) = 32),
  CONSTRAINT citation_object_key_stated CHECK (object_key IS NULL OR object_key <> ''),
  CONSTRAINT pk_disposition_citation PRIMARY KEY (disposition_id, citation_ord)
);
