# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A minimal, faithful reduction of the kernel's epoch pin, for the late-recall lane.

**This is fixture DDL, not a migration, and it is labelled as such on purpose.** The kernel
band that owns ``mainline.permit``, ``mainline.blocking_check`` and ``mainline.merge_record``
(migrations ``0050`` to ``0071``) is not on disk in this tree yet. The choice was therefore
between asserting nothing about the epoch pin until it lands, or asserting the mechanism
against a reduction that carries **exactly** the four objects the mechanism is made of, copied
from ARCHITECTURE 5.5 without alteration:

1. ``permit`` with ``UNIQUE (permit_id, gate_epoch)`` — the FK target;
2. ``merge_record`` with the composite FK ``epoch_pin_permit … ON UPDATE RESTRICT``;
3. ``fn_check_materialised``, which bumps ``gate_epoch`` on every new obligation;
4. ``gate_closed_when_issued``, the ``CHECK`` that makes the bump illegal on a merged row.

Everything omitted — the other five counters, the RLS scope token, the outbox insert, the
change-request mirror — is omitted because it takes no part in the refusal under test. When
the kernel band lands, this lane should be re-pointed at the real migrations and this module
deleted; ``test_late_recall.py`` asserts the same SQLSTATEs either way, so the swap is
mechanical.

What is *not* reduced is the claim. ``SERIALIZABLE`` orders writes; it does not prevent late
arrival. A precursor inserted at ``T+ε`` after a merge at ``T`` is a perfectly serializable
history, so the anomaly is unreachable by isolation level and the answer has to be structural.
"""

from __future__ import annotations

from typing import Final

__all__ = ["REWELD_RESTORE_RAISE", "SCHEMA_STATEMENTS", "UNWELD_REMOVE_RAISE"]

_FN_WITH_RAISE: Final = """
CREATE OR REPLACE FUNCTION mainline.fn_check_materialised() RETURNS TRIGGER
LANGUAGE PLpgSQL AS $$
DECLARE s STRING;
BEGIN
  SELECT state INTO s FROM mainline.permit WHERE permit_id = (NEW).permit_id FOR UPDATE;
  IF s = 'merged' THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: precursor arrived after issue - use the post-issue recall path';
  END IF;
  UPDATE mainline.permit
     SET open_blocking = open_blocking + 1,
         gate_epoch    = gate_epoch + 1
   WHERE permit_id = (NEW).permit_id;
  RETURN NEW;
END $$
""".strip()

#: The unwelding variant: identical, with the deterministic ``RAISE`` removed. ARCHITECTURE
#: 5.11's claim is that the write still fails twice over without it — the ``UPDATE`` drives
#: ``open_blocking > 0`` on a merged row (``23514``) *and* mutates a pinned ``gate_epoch``
#: (``23503``). A structural-redundancy sentence nobody executed is a sentence, so this is
#: executed.
UNWELD_REMOVE_RAISE: Final = """
CREATE OR REPLACE FUNCTION mainline.fn_check_materialised() RETURNS TRIGGER
LANGUAGE PLpgSQL AS $$
BEGIN
  UPDATE mainline.permit
     SET open_blocking = open_blocking + 1,
         gate_epoch    = gate_epoch + 1
   WHERE permit_id = (NEW).permit_id;
  RETURN NEW;
END $$
""".strip()

REWELD_RESTORE_RAISE: Final = _FN_WITH_RAISE

SCHEMA_STATEMENTS: Final[tuple[str, ...]] = (
    "CREATE SCHEMA IF NOT EXISTS mainline",
    """
CREATE TABLE mainline.permit (
  permit_id     UUID NOT NULL PRIMARY KEY,
  site_id       UUID NOT NULL,
  external_ref  STRING NOT NULL,
  state         STRING NOT NULL DEFAULT 'draft'
                CHECK (state IN ('draft','dispositioned','merged','suspended')),
  head_seq      INT8 NOT NULL DEFAULT 0,
  gate_epoch    INT8 NOT NULL DEFAULT 0,
  open_blocking INT8 NOT NULL DEFAULT 0,
  merged_commit BYTES NULL,
  CONSTRAINT ctr_nonneg CHECK (open_blocking >= 0),
  CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0),
  CONSTRAINT merge_evidence CHECK (state <> 'merged' OR merged_commit IS NOT NULL),
  UNIQUE (permit_id, gate_epoch)
)
""".strip(),
    """
CREATE TABLE mainline.blocking_check (
  check_id         UUID NOT NULL PRIMARY KEY,
  permit_id        UUID NOT NULL REFERENCES mainline.permit (permit_id),
  site_id          UUID NOT NULL,
  severity         INT2 NOT NULL,
  origin           STRING NOT NULL,
  evidence_summary STRING NOT NULL
)
""".strip(),
    """
CREATE TABLE mainline.merge_record (
  subject_kind STRING NOT NULL CHECK (subject_kind IN ('permit','change_request')),
  subject_id   UUID  NOT NULL,
  gate_epoch   INT8  NOT NULL,
  merged_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  merged_by    STRING NOT NULL,
  PRIMARY KEY (subject_kind, subject_id)
)
""".strip(),
    """
ALTER TABLE mainline.merge_record ADD CONSTRAINT epoch_pin_permit
  FOREIGN KEY (subject_id, gate_epoch) REFERENCES mainline.permit (permit_id, gate_epoch)
  ON UPDATE RESTRICT ON DELETE RESTRICT
""".strip(),
    _FN_WITH_RAISE,
    """
CREATE TRIGGER check_materialised AFTER INSERT ON mainline.blocking_check
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_check_materialised()
""".strip(),
)
