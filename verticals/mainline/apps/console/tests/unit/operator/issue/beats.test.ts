// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE FOUR BEATS ARE READ, NOT COMPOSED.
 *
 * The payloads below are TRANSCRIBED from a measured run — `evidence/deploy/live-gate-run.json`,
 * taken 2026-08-14 against the deployed Function URL, verdict PROVEN — and they are typed
 * `satisfies GateRun` against `src/data/types.generated.ts`, which is generated from
 * `contracts/gate-run.schema.json`. So a fixture that drifted from the contract stops
 * compiling rather than quietly testing a shape the kernel never emits.
 *
 * What these tests are for: proving that every SQLSTATE, constraint name, predicate,
 * duration and digest the screen renders came OUT of a payload, and that the module reports
 * an absence where the payload carries none instead of supplying a plausible value.
 */

import { describe, expect, it } from 'vitest';

import {
  GATE_RUN_METHOD,
  GATE_RUN_PATH,
  admissionReading,
  beatViews,
  checkPredicate,
  counterForge,
  exhibitIsWeakened,
  formatMs,
  nearestAdmissible,
  observedOutstanding,
  outstandingLine,
  persistenceReading,
  precursorEvents,
  raisedBy,
  readRun,
  reasonAtomLine,
  toBeatView,
} from '../../../../src/operator/issue/beats';

import type { Beat, GateRun } from '../../../../src/data/types.generated';

// ───────────────────────────────────────────────────────────────────────────────────────
// Fixtures — a transcription of a measured run
// ───────────────────────────────────────────────────────────────────────────────────────

const PERMIT = 'dec0de00-0006-4000-8000-000000000001';
const OBLIGATION = 'dec0de00-0007-4000-8000-000000000001';
const PRECURSOR = 'dec0de00-0005-4000-8000-000000000001';

const READ_BEAT = {
  ordinal: 1,
  name: 'read',
  label: 'The permit, and the obligation that is still open on it.',
  expected: { outcome: 'read' },
  outcome: 'read',
  sqlstate: '00000',
  constraint: null,
  constraint_source: null,
  message: null,
  matched_expectation: true,
  elapsed_ms: 0.011,
  statement: 'SELECT … FROM mainline.permit JOIN mainline.site …',
  refusal: null,
  observed: {
    state: 'dispositioned',
    gate_epoch: 1,
    head_seq: 2,
    open_blocking_projected: 1,
    open_blocking_derived: 1,
    blocking_check_id: OBLIGATION,
    counters_agree: true,
  },
  note: null,
} satisfies Beat;

const MERGE_BEAT = {
  ordinal: 2,
  name: 'merge',
  label: 'MERGE the permit. One open obligation, no signed disposition.',
  expected: {
    outcome: 'refused',
    sqlstate: '23514',
    constraint: 'gate_closed_when_issued',
    constraint_source: 'reported',
  },
  outcome: 'refused',
  sqlstate: '23514',
  constraint: 'gate_closed_when_issued',
  constraint_source: 'reported',
  message:
    "failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))",
  matched_expectation: true,
  elapsed_ms: 572.251,
  statement: 'CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)',
  refusal: {
    spec_version: '1.0.0-rc.1',
    refusal_id: '7d0dd6bd-acab-4dcf-ba71-a08dd7d59bc8',
    observed_at: '2026-08-14T22:10:33Z',
    profile: 'mainline',
    class: 'gate',
    sqlstate: '23514',
    constraint: 'gate_closed_when_issued',
    constraint_source: 'reported',
    message:
      "failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))",
    subject_kind: 'permit',
    subject_id: PERMIT,
    gate_epoch: 1,
    diagnosis: 'declarative',
    probe_calls: 0,
    mus: [
      {
        kind: 'obligation',
        obligation_id: OBLIGATION,
        origin: 'blame_ancestry',
        clause_id: 'dec0de00-0004-4000-8000-000000000001',
        event_id: PRECURSOR,
        severity: 4,
        virulence: 'blood_major',
        detail: 'open at gate_epoch 1; no live disposition',
      },
    ],
    naa: {
      kind: 'dispose_obligations',
      obligation_ids: [OBLIGATION],
      cardinality: 1,
      legal_kinds: ['applied', 'mitigated', 'mechanism_absent', 'escalated', 'emergency_override'],
      description:
        '1 obligation(s) remain open on this subject; disposing of exactly those restores admissibility',
    },
    naa_reason: null,
  },
  observed: {},
  note: null,
} satisfies Beat;

const ATTACK_BEAT = {
  ordinal: 3,
  name: 'projection_drift_attack',
  label: 'THE ATTACK: force the projected counter to zero out of band, then merge again.',
  expected: {
    outcome: 'refused',
    sqlstate: 'P0001',
    constraint: 'mainline.fn_permit_merge_gate',
    constraint_source: 'parsed',
  },
  outcome: 'refused',
  sqlstate: 'P0001',
  constraint: 'mainline.fn_permit_merge_gate',
  constraint_source: 'parsed',
  message:
    'MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero',
  matched_expectation: true,
  elapsed_ms: 564.509,
  statement:
    'UPDATE mainline.permit SET open_blocking = 0 WHERE permit_id = %s; CALL mainline.merge_permit(%s, %s)',
  refusal: {
    spec_version: '1.0.0-rc.1',
    refusal_id: '868322e7-95b3-44d9-9b43-2254a9ad32a6',
    observed_at: '2026-08-14T22:10:34Z',
    profile: 'mainline',
    class: 'gate',
    sqlstate: 'P0001',
    constraint: 'mainline.fn_permit_merge_gate',
    constraint_source: 'parsed',
    message:
      'MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero',
    subject_kind: 'permit',
    subject_id: PERMIT,
    gate_epoch: 1,
    diagnosis: 'none',
    probe_calls: 0,
    mus: [
      {
        kind: 'capability_gap',
        capability: 'mainline.fn_permit_merge_gate',
        detail: 'outside the declarative decomposition',
      },
    ],
    naa: null,
    naa_reason: 'not_computable',
  },
  observed: {
    attack: 'mainline.permit.open_blocking set out of band — what a careless UPDATE leaves behind',
    counter_forced_to: 0,
    open_blocking_derived: 1,
  },
  note: null,
} satisfies Beat;

const ADMIT_BEAT = {
  ordinal: 4,
  name: 'admit',
  label: 'Sign one disposition against the obligation, then merge again.',
  expected: { outcome: 'admitted', sqlstate: '00000' },
  outcome: 'admitted',
  sqlstate: '00000',
  constraint: null,
  constraint_source: null,
  message: null,
  matched_expectation: true,
  elapsed_ms: 516.003,
  statement: 'INSERT INTO mainline.disposition (…) VALUES (…); CALL mainline.merge_permit(…)',
  refusal: null,
  observed: {
    disposition_id: 'd2da1bd4-f020-433b-b554-0aa151044dcd',
    disposition_kind: 'applied',
    open_blocking_after_signature: 0,
    merge_record: {
      clearance_digest: 'c49c82df9d40fb12d7d0322a70ec2ea0ec0e3a166fdf2a9f87e3b3ab6282a8f5',
      merged_commit: '4fbbd37106cf5e02b03a49ce2ba5c4aa4fbbd37106cf5e02b03a49ce2ba5c4aa',
      gate_epoch: 1,
      merged_at: '2026-08-14T22:10:33.293842+00:00',
      permit_state: 'merged',
      permit_open_blocking: 0,
      permit_head_seq: 3,
    },
  },
  note: null,
} satisfies Beat;

const FINGERPRINT = {
  row_counts: { 'mainline.merge_record': 0, 'mainline.permit_event': 2 },
  subject_row_counts: {
    'mainline.disposition': 0,
    'mainline.merge_record': 0,
    'mainline.permit_event': 2,
  },
  permit_row: {
    state: 'dispositioned',
    head_seq: 2,
    gate_epoch: 1,
    open_blocking: 1,
    unmet_floor_count: 0,
    countersigned_count: 0,
    merged_commit: null,
  },
} as const;

const RUN = {
  schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
  run_id: 'judge-walk',
  generated_at: '2026-08-14T22:10:33Z',
  outcome: 'completed',
  verdict: 'PROVEN',
  failures: [],
  persisted: false,
  elapsed_ms: 1857.405,
  transaction: {
    isolation: 'SERIALIZABLE',
    disposition: 'rolled_back',
    opened_logical_timestamp: '1786745433293875086.0000000000',
    closed_logical_timestamp: '1786745433293875086.0000000000',
    single_transaction: true,
    savepoints: ['gate_run_beat_2', 'gate_run_beat_3', 'gate_run_beat_4'],
    retry_sqlstate: null,
    canonicalisation: 'mainline_demo_api.gate_run.canonical_json',
  },
  subject: {
    subject_kind: 'permit',
    subject_id: PERMIT,
    external_ref: 'DEMO-PTW-0001',
    state: 'dispositioned',
    head_seq: 2,
    gate_epoch: 1,
    open_blocking: 1,
    open_blocking_derived: 1,
    blocking_check_id: OBLIGATION,
    exposure_receipt_id: 'dec0de00-0008-4000-8000-000000000001',
    site_code: 'dec0de00-0001-4000-8000-000000000001',
  },
  beats: [READ_BEAT, MERGE_BEAT, ATTACK_BEAT, ADMIT_BEAT],
  persistence_check: {
    before: FINGERPRINT,
    after: FINGERPRINT,
    identical: true,
    self_persisted: false,
    self_evidence: {
      minted_disposition_id: 'd2da1bd4-f020-433b-b554-0aa151044dcd',
      minted_disposition_rows_after_rollback: 0,
      subject_row_counts_before: FINGERPRINT.subject_row_counts,
      subject_row_counts_after: FINGERPRINT.subject_row_counts,
      permit_row_identical: true,
    },
    concurrent_writes: null,
    tables: ['mainline.permit', 'mainline.merge_record'],
    note: 'Row counts over every table the four beats can write.',
  },
} satisfies GateRun;

/** The same run as the kernel abandons it when SQLSTATE 40001 lands. */
const UNDECIDED_RUN = {
  ...RUN,
  outcome: 'retry',
  verdict: 'NOT PROVEN',
  failures: ['the run was abandoned as undecided'],
  transaction: { ...RUN.transaction, closed_logical_timestamp: null, retry_sqlstate: '40001' },
  beats: [
    READ_BEAT,
    { ...MERGE_BEAT, outcome: 'retry', sqlstate: '40001', refusal: null, matched_expectation: false },
    { ...ATTACK_BEAT, outcome: 'skipped', refusal: null, matched_expectation: false },
    { ...ADMIT_BEAT, outcome: 'skipped', matched_expectation: false },
  ],
} satisfies GateRun;

function facts(run: GateRun | null, status = 200): {
  status: number;
  wireBytes: number;
  receivedAt: string;
  data: GateRun | null;
} {
  return { status, wireBytes: 24_137, receivedAt: '2026-08-14T22:10:35.412Z', data: run };
}

function at<T>(items: readonly T[], index: number): T {
  const item = items[index];
  if (item === undefined) throw new Error(`the fixture has no item at index ${index}`);
  return item;
}

// ───────────────────────────────────────────────────────────────────────────────────────

describe('the one path the ISSUE button posts to', () => {
  it('is the demo gate-run route and never the permit merge route (R4)', () => {
    expect(GATE_RUN_METHOD).toBe('POST');
    expect(GATE_RUN_PATH).toBe('/v1/demo/gate-run');
    expect(GATE_RUN_PATH).not.toContain('/merge');
  });
});

describe('readRun', () => {
  it('reads a completed run into four beat views, in the payload’s order', () => {
    const reading = readRun(facts(RUN));
    expect(reading.kind).toBe('completed');
    if (reading.kind !== 'completed') return;
    expect(reading.beats.map((beat) => beat.ordinal)).toEqual([1, 2, 3, 4]);
    expect(reading.beats.map((beat) => beat.outcome)).toEqual([
      'read',
      'refused',
      'refused',
      'admitted',
    ]);
  });

  it('renders NO gate-run reading when no payload came back', () => {
    const reading = readRun(facts(null, 503));
    expect(reading.kind).toBe('unreadable');
  });

  it('reads a 40001 run as UNDECIDED, carrying the payload’s own retry sqlstate', () => {
    const reading = readRun(facts(UNDECIDED_RUN, 503));
    expect(reading.kind).toBe('undecided');
    if (reading.kind !== 'undecided') return;
    expect(reading.retrySqlstate).toBe(UNDECIDED_RUN.transaction.retry_sqlstate);
    expect(reading.httpStatus).toBe(503);
  });

  it('does not turn an undecided run into refused beats', () => {
    const views = beatViews(UNDECIDED_RUN);
    expect(views.some((beat) => beat.isRefusal)).toBe(false);
    expect(at(views, 1).isUndecided).toBe(true);
    expect(at(views, 1).refusal).toBeNull();
  });
});

describe('every duration rendered per beat is the payload’s own elapsed_ms', () => {
  it('copies elapsed_ms verbatim for all four beats', () => {
    const views = beatViews(RUN);
    expect(views.map((beat) => beat.elapsedMs)).toEqual([
      READ_BEAT.elapsed_ms,
      MERGE_BEAT.elapsed_ms,
      ATTACK_BEAT.elapsed_ms,
      ADMIT_BEAT.elapsed_ms,
    ]);
  });

  it('formats without a locale so the number reads the same on every machine', () => {
    expect(formatMs(MERGE_BEAT.elapsed_ms)).toBe('572.3 ms');
    expect(formatMs(RUN.elapsed_ms)).toBe('1.86 s');
  });

  it('never rounds a real sub-millisecond measurement down to zero', () => {
    // The read beat genuinely takes tens of microseconds. `0.0 ms` on screen reads as a
    // number the client threw away.
    expect(formatMs(READ_BEAT.elapsed_ms)).toBe('0.011 ms');
    expect(formatMs(0)).toBe('0.000 ms');
  });
});

describe('the exhibits are copied, never composed', () => {
  it('carries the beat’s own sqlstate, constraint and source', () => {
    const view = toBeatView(MERGE_BEAT);
    expect(view.sqlstate).toBe(MERGE_BEAT.sqlstate);
    expect(view.constraint).toBe(MERGE_BEAT.constraint);
    expect(view.constraintSource).toBe(MERGE_BEAT.constraint_source);
    expect(view.message).toBe(MERGE_BEAT.message);
  });

  it('marks a recovered exhibit as weakened and a reported one as not', () => {
    expect(exhibitIsWeakened(toBeatView(ATTACK_BEAT))).toBe(true);
    expect(exhibitIsWeakened(toBeatView(MERGE_BEAT))).toBe(false);
  });

  it('lifts the CHECK predicate out of the database’s own message', () => {
    const predicate = checkPredicate(MERGE_BEAT.message);
    expect(predicate).not.toBeNull();
    expect(predicate?.from).toBe('message');
    expect(MERGE_BEAT.message).toContain(predicate?.text ?? ' ');
  });

  it('finds no predicate where the message carries none', () => {
    expect(checkPredicate(ATTACK_BEAT.message)).toBeNull();
    expect(checkPredicate(null)).toBeNull();
  });

  it('names the raising object from a qualified exhibit', () => {
    const source = raisedBy(toBeatView(ATTACK_BEAT));
    expect(source?.object).toBe(ATTACK_BEAT.constraint);
    expect(source?.schema).toBe(ATTACK_BEAT.constraint.split('.')[0]);
    expect(source?.how).toBe('constraint_field');
  });

  it('reports the ABSENCE rather than guessing a table for an unqualified CHECK', () => {
    // The driver reports a constraint's name, not the relation it was declared on, and no
    // other member of the beat carries it. A plausible table name is one identifier away;
    // typing it would be indistinguishable from reading it.
    expect(raisedBy(toBeatView(MERGE_BEAT))).toBeNull();
  });

  it('recovers the raising object from the kernel’s own refused-by clause', () => {
    const view = toBeatView({ ...ATTACK_BEAT, constraint: null });
    expect(raisedBy(view)?.how).toBe('message_clause');
    expect(ATTACK_BEAT.message).toContain(raisedBy(view)?.object ?? ' ');
  });
});

describe('the explanation the refusal carries with it', () => {
  it('reads a computed nearest admissible alternative', () => {
    const alternative = nearestAdmissible(MERGE_BEAT.refusal);
    expect(alternative?.kind).toBe('computed');
  });

  it('reports NOT COMPUTABLE with the payload’s own reason on the attack beat', () => {
    const alternative = nearestAdmissible(ATTACK_BEAT.refusal);
    expect(alternative?.kind).toBe('not_computed');
    if (alternative?.kind !== 'not_computed') return;
    expect(alternative.reason).toBe(ATTACK_BEAT.refusal.naa_reason);
  });

  it('prints a reason-set atom only from members the atom actually carries', () => {
    const line = reasonAtomLine(at(MERGE_BEAT.refusal.mus, 0));
    expect(line).toContain(OBLIGATION);
    expect(line).toContain(PRECURSOR);

    const atom = at(ATTACK_BEAT.refusal.mus, 0);
    expect(atom.kind).toBe('capability_gap');
    if (atom.kind !== 'capability_gap') return;
    const gap = reasonAtomLine(atom);
    expect(gap).toContain('capability gap');
    expect(gap).toContain(atom.capability);
    expect(gap).not.toContain(OBLIGATION);
  });

  it('names precursor events only when the reason set names them', () => {
    expect(precursorEvents(MERGE_BEAT.refusal)).toEqual([PRECURSOR]);
    expect(precursorEvents(ATTACK_BEAT.refusal)).toEqual([]);
    expect(precursorEvents(null)).toEqual([]);
  });
});

describe('the counters, and what the attack beat did to them', () => {
  it('reads the forged counter and the re-derived count from the payload', () => {
    const forge = counterForge(toBeatView(ATTACK_BEAT));
    expect(forge?.forcedTo).toBe(ATTACK_BEAT.observed.counter_forced_to);
    expect(forge?.derived).toBe(ATTACK_BEAT.observed.open_blocking_derived);
    expect(forge?.attack).toBe(ATTACK_BEAT.observed.attack);
  });

  it('detects the attack by what the beat observed, not by its position', () => {
    expect(counterForge(toBeatView(MERGE_BEAT))).toBeNull();
    expect(counterForge(toBeatView({ ...ATTACK_BEAT, ordinal: 2 }))).not.toBeNull();
    expect(counterForge(toBeatView({ ...ATTACK_BEAT, observed: {} }))).toBeNull();
  });

  it('prefers the re-derived count when reporting what the read saw', () => {
    expect(observedOutstanding(toBeatView(READ_BEAT))).toBe(
      READ_BEAT.observed.open_blocking_derived,
    );
    expect(observedOutstanding(toBeatView(MERGE_BEAT))).toBeNull();
  });
});

describe('the admission, and the claim that nothing persisted', () => {
  it('reads the server-computed clearance digest off beat 4', () => {
    const admission = admissionReading(toBeatView(ADMIT_BEAT));
    expect(admission?.clearanceDigest).toBe(ADMIT_BEAT.observed.merge_record.clearance_digest);
    expect(admission?.dispositionId).toBe(ADMIT_BEAT.observed.disposition_id);
    expect(admission?.openBlockingAfterSignature).toBe(0);
  });

  it('reads nothing from a beat that was not admitted', () => {
    expect(admissionReading(toBeatView(MERGE_BEAT))).toBeNull();
  });

  it('reports self_persisted, not identical, as the claim about THIS run', () => {
    const persistence = persistenceReading(RUN);
    expect(persistence.selfPersisted).toBe(RUN.persistence_check.self_persisted);
    expect(persistence.mintedRowsAfterRollback).toBe(0);
    expect(persistence.identical).toBe(true);
    expect(persistence.concurrentWrites).toEqual([]);
  });

  it('reports another caller’s writes as another caller’s, without blaming the run', () => {
    const moved = {
      ...RUN,
      persistence_check: {
        ...RUN.persistence_check,
        identical: false,
        concurrent_writes: { 'mainline.permit': [780, 781] },
      },
    } satisfies GateRun;
    const persistence = persistenceReading(moved);
    expect(persistence.selfPersisted).toBe(false);
    expect(persistence.identical).toBe(false);
    expect(persistence.concurrentWrites).toEqual([{ table: 'mainline.permit', counts: [780, 781] }]);
  });
});

describe('the standing line above the button', () => {
  it('agrees with the count and never invents one', () => {
    expect(outstandingLine(1)).toBe('1 obligation outstanding');
    expect(outstandingLine(2)).toBe('2 obligations outstanding');
    expect(outstandingLine(0)).toBe('0 obligations outstanding');
    expect(outstandingLine(null)).toBe('obligations outstanding · not read');
  });
});
