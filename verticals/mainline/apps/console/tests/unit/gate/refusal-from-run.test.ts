// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ADAPTER THAT PUTS A RUN'S REFUSAL ON THE SCREEN'S BAND, AGAINST CAPTURED BYTES.
 *
 * ── WHERE THE EXHIBITS COME FROM ─────────────────────────────────────────────────
 *
 * `docs/leads/ui.md` §1.5 names the one assertion this domain must get right: the refusal
 * bar renders `gate_closed_when_issued` and SQLSTATE `23514` **taken from the bundle, not
 * from a literal in the test**. A test that retypes the string it expects passes just as
 * happily against an adapter that retypes the string it emits, and the pair of them assert
 * nothing at all.
 *
 * `fixtures/bundles/demo-cloud/` carries three captured `POST …/merge` frames from the
 * seeded cloud, and two of them are exactly the two refusals the four-beat run reproduces:
 *
 *   • one with `constraint_source: "reported"` — an obligation MUS and a
 *     `dispose_obligations` NAA;
 *   • one with `constraint_source: "parsed"` — a `capability_gap` MUS, `naa: null` and a
 *     stated `naa_reason`.
 *
 * Both are located BY THEIR OWN `constraint_source`, never by a UUID or a SQLSTATE typed
 * here. So the suite keeps working if the capture is retaken, and goes red the moment the
 * capture stops carrying one of the two cases this screen has to tell apart.
 *
 * ── WHAT IS ASSEMBLED HERE, AND WHY THAT IS NOT AN INVENTION ─────────────────────
 *
 * The console holds no captured `POST /v1/demo/gate-run` frame — the demo endpoint is not
 * in `fixtures/bundles/demo-cloud/manifest.json`. So the BEAT SCAFFOLDING around those two
 * refusals is assembled here, from `src/features/gate/beats.ts`'s structural reading of
 * `gate-run.schema.json`. The refusal payloads inside it are the captured bytes, untouched
 * and unreformatted.
 *
 * That is a fixture, not evidence, and the difference is enforced rather than promised:
 * nothing assembled in this file is rendered anywhere, and the two cases that would let an
 * invention reach a screen — a `null` run, and a beat that says `refused` while carrying no
 * payload — are pinned below as producing NO refusal at all.
 */

import { describe, expect, it } from 'vitest';

import { forbiddenWordsIn } from '../../../src/design/primitives';
import type { GateRunBeat, GateRunData } from '../../../src/features/gate/beats';
import {
  RUN_ABSENCE_SENTENCE,
  refusalLead,
  refusalsFromRun,
  runAttribution,
  selectBand,
} from '../../../src/features/gate/refusal-from-run';
import type { RefusalPayload } from '../../../src/data/types.generated';

// ── The captured refusals ──────────────────────────────────────────────────

const RAW_FRAMES: Record<string, unknown> = import.meta.glob(
  '/fixtures/bundles/demo-cloud/frames/*.json',
  { query: '?raw', import: 'default', eager: true },
);

interface CapturedFrame {
  readonly response: { readonly body_b64: string };
}

/**
 * The frame glob matches every captured frame, not only the three `POST …/merge` ones. A
 * `GET` envelope's `data` carries no `refusal` member at all, so absence and explicit
 * `null` are both filtered here rather than mistaken for a payload.
 */
interface CapturedInvoke {
  readonly data?: { readonly refusal?: RefusalPayload | null } | null;
}

function decodeBase64(value: string): string {
  return new TextDecoder('utf-8', { fatal: true }).decode(
    Uint8Array.from(atob(value), (character) => character.charCodeAt(0)),
  );
}

/** Every refusal payload the captured demo-cloud frames carry, in path order. */
function capturedRefusals(): readonly RefusalPayload[] {
  const paths = Object.keys(RAW_FRAMES).sort();
  if (paths.length === 0) {
    throw new Error(
      'tests/unit/gate/refusal-from-run.test.ts: the demo-cloud frame glob matched nothing, so ' +
        'every expectation below would be vacuous. Expected captured frames under ' +
        'fixtures/bundles/demo-cloud/frames/.',
    );
  }
  const found: RefusalPayload[] = [];
  for (const path of paths) {
    const text = RAW_FRAMES[path];
    if (typeof text !== 'string') continue;
    const frame = JSON.parse(text) as CapturedFrame;
    const envelope = JSON.parse(decodeBase64(frame.response.body_b64)) as CapturedInvoke;
    const refusal = envelope.data?.refusal;
    if (refusal !== null && refusal !== undefined) found.push(refusal);
  }
  if (found.length === 0) {
    throw new Error(
      `tests/unit/gate/refusal-from-run.test.ts: ${String(paths.length)} captured frame(s) were ` +
        'read and none carried a refusal payload. Every expectation below would be vacuous.',
    );
  }
  return found;
}

function refusalWithSource(source: 'reported' | 'parsed'): RefusalPayload {
  const match = capturedRefusals().find((refusal) => refusal.constraint_source === source);
  if (match === undefined) {
    throw new Error(
      `no captured demo-cloud frame carries constraint_source "${source}". This suite exists to ` +
        'distinguish a reported exhibit from a parsed one and cannot do so without both.',
    );
  }
  return match;
}

const REPORTED = refusalWithSource('reported');
const PARSED = refusalWithSource('parsed');
const SUBJECT = REPORTED.subject_id;

// ── The scaffolding this file owns ─────────────────────────────────────────

function beat(ordinal: number, name: string, over: Partial<GateRunBeat> = {}): GateRunBeat {
  return {
    ordinal,
    name,
    label: `beat ${ordinal}`,
    expected: { outcome: 'refused' },
    outcome: 'refused',
    sqlstate: null,
    constraint: null,
    constraint_source: null,
    message: null,
    matched_expectation: true,
    elapsed_ms: 1.5 * ordinal,
    statement: null,
    observed: {},
    note: null,
    refusal: null,
    ...over,
  };
}

const TRANSACTION: GateRunData['transaction'] = {
  isolation: 'SERIALIZABLE',
  disposition: 'rolled_back',
  opened_logical_timestamp: '1755000000.0000000000',
  closed_logical_timestamp: '1755000000.0000000000',
  single_transaction: true,
  savepoints: ['beat_merge', 'beat_attack', 'beat_admit'],
  retry_sqlstate: null,
  canonicalisation: 'rfc8785',
};

const FINGERPRINT: GateRunData['persistence_check']['before'] = {
  row_counts: {},
  subject_row_counts: {},
  permit_row: null,
};

/** A run carrying the given beats, with the contract's own scaffolding around them. */
function runAround(beats: readonly GateRunBeat[], over: Partial<GateRunData> = {}): GateRunData {
  return {
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
    run_id: 'run-under-test',
    generated_at: '2026-08-15T00:00:00Z',
    outcome: 'completed',
    verdict: 'PROVEN',
    failures: [],
    persisted: false,
    elapsed_ms: 1658.5,
    transaction: TRANSACTION,
    subject: {
      subject_kind: 'permit',
      subject_id: SUBJECT,
      external_ref: 'DEMO-PTW-0001',
      state: 'dispositioned',
      head_seq: 1,
      gate_epoch: 1,
      open_blocking: 1,
      open_blocking_derived: 1,
      blocking_check_id: null,
      exposure_receipt_id: null,
      site_code: 'dec0de00-0001-4000-8000-000000000001',
    },
    beats,
    persistence_check: {
      before: FINGERPRINT,
      after: FINGERPRINT,
      identical: true,
      self_persisted: false,
      self_evidence: {
        minted_disposition_id: null,
        minted_disposition_rows_after_rollback: 0,
        subject_row_counts_before: {},
        subject_row_counts_after: {},
        permit_row_identical: true,
      },
      concurrent_writes: null,
      tables: [],
      note: '',
    },
    ...over,
  };
}

/** The four beats as measured: read, refused, refused under a forged counter, admitted. */
function fourBeatRun(over: Partial<GateRunData> = {}): GateRunData {
  return runAround(
    [
      beat(1, 'read', { outcome: 'read', sqlstate: '00000', elapsed_ms: 0.013 }),
      beat(2, 'merge', {
        label: 'merge the permit',
        sqlstate: REPORTED.sqlstate,
        constraint: REPORTED.constraint,
        constraint_source: 'reported',
        refusal: REPORTED,
        statement: 'CALL trappoint.merge_permit($1, $2, $3)',
        elapsed_ms: 513.15,
      }),
      beat(3, 'projection_drift_attack', {
        label: 'forge the counter and merge',
        sqlstate: PARSED.sqlstate,
        constraint: PARSED.constraint,
        constraint_source: 'parsed',
        refusal: PARSED,
        elapsed_ms: 532.16,
      }),
      beat(4, 'admit', { outcome: 'admitted', sqlstate: '00000', elapsed_ms: 437.01 }),
    ],
    over,
  );
}

// ── The fixture is the fixture this suite thinks it is ─────────────────────

describe('the captured exhibits', () => {
  it('carries a reported refusal and a parsed one, and they are different refusals', () => {
    expect(REPORTED.constraint_source).toBe('reported');
    expect(PARSED.constraint_source).toBe('parsed');
    expect(PARSED.constraint).not.toBe(REPORTED.constraint);
    expect(PARSED.sqlstate).not.toBe(REPORTED.sqlstate);
  });

  it('carries the two nearest-admissible cases the screen has to tell apart', () => {
    expect(REPORTED.naa).not.toBeNull();
    expect(REPORTED.mus.length).toBeGreaterThan(0);
    expect(PARSED.naa).toBeNull();
    expect(PARSED.naa_reason).not.toBeNull();
    expect(PARSED.naa_reason).not.toBeUndefined();
  });
});

// ── R7, first direction: with no run, nothing is predicted ─────────────────

describe('with no run, the console predicts nothing', () => {
  it('returns no refusals, and names which nothing this is', () => {
    const model = refusalsFromRun(null, SUBJECT);
    expect(model.refusals).toEqual([]);
    expect(model.absence).toBe('no-run');
    expect(model.runId).toBeNull();
    expect(model.subjectId).toBeNull();
    expect(model.verdict).toBeNull();
  });

  it('leaves the band in whatever state this screen’s own attempt is in', () => {
    const selection = selectBand({ kind: 'none' }, refusalsFromRun(null, SUBJECT));
    expect(selection.primary).toEqual({ kind: 'none' });
    expect(selection.primarySource).toBe('none');
    expect(selection.primaryBeat).toBeNull();
    expect(selection.further).toEqual([]);
  });

  it('has a distinct sentence for every absence, and none of them is “nothing happened”', () => {
    const sentences = Object.values(RUN_ABSENCE_SENTENCE);
    expect(new Set(sentences).size).toBe(sentences.length);
    expect(RUN_ABSENCE_SENTENCE['no-refusal']).toContain('not the same statement');
    expect(RUN_ABSENCE_SENTENCE.undecided).toContain('40001');
  });
});

describe('a run that drove another subject is not this screen’s refusal', () => {
  it('contributes nothing to a screen addressed to a different permit', () => {
    const model = refusalsFromRun(fourBeatRun(), 'dec0de00-9999-4000-8000-000000000009');
    expect(model.refusals).toEqual([]);
    expect(model.absence).toBe('other-subject');
    // The identifiers survive, so the screen can say WHOSE run it declined to show.
    expect(model.subjectId).toBe(SUBJECT);
    expect(model.runId).toBe('run-under-test');
  });
});

// ── The reported refusal, carried through verbatim ─────────────────────────

describe('beat 2 — a reported refusal reaches the band', () => {
  it('adapts exactly the beats the run reports as refused, in ordinal order', () => {
    const model = refusalsFromRun(fourBeatRun(), SUBJECT);
    expect(model.absence).toBeNull();
    expect(model.refusals.map((refusal) => refusal.ordinal)).toEqual([2, 3]);
    expect(model.refusals.map((refusal) => refusal.name)).toEqual([
      'merge',
      'projection_drift_attack',
    ]);
  });

  it('sorts on the payload’s ordinal rather than trusting the array’s order', () => {
    const scrambled = fourBeatRun();
    const model = refusalsFromRun(
      { ...scrambled, beats: [...scrambled.beats].reverse() },
      SUBJECT,
    );
    expect(model.refusals.map((refusal) => refusal.ordinal)).toEqual([2, 3]);
  });

  it('carries the captured constraint, SQLSTATE and constraint_source unchanged', () => {
    const [first] = refusalsFromRun(fourBeatRun(), SUBJECT).refusals;
    if (first?.state.kind !== 'refused') throw new Error('beat 2 did not narrow to a refusal');
    expect(first.state.refusal.constraint).toBe(REPORTED.constraint);
    expect(first.state.refusal.sqlstate).toBe(REPORTED.sqlstate);
    expect(first.state.refusal.constraint_source).toBe('reported');
  });

  it('carries the minimal unsatisfiable subset the payload holds, atom for atom', () => {
    const [first] = refusalsFromRun(fourBeatRun(), SUBJECT).refusals;
    if (first?.state.kind !== 'refused') throw new Error('beat 2 did not narrow to a refusal');
    expect(first.state.refusal.mus).toEqual(REPORTED.mus);
  });

  it('carries the nearest admissible alternative — the answer to the judge’s question', () => {
    const [first] = refusalsFromRun(fourBeatRun(), SUBJECT).refusals;
    if (first?.state.kind !== 'refused') throw new Error('beat 2 did not narrow to a refusal');
    expect(first.state.refusal.naa).toEqual(REPORTED.naa);
  });

  it('reports the payload’s own elapsed_ms, never a reveal delay (R11)', () => {
    const model = refusalsFromRun(fourBeatRun(), SUBJECT);
    expect(model.refusals[0]?.elapsedMs).toBe(513.15);
    expect(model.refusals[1]?.elapsedMs).toBe(532.16);
  });

  it('follows the payload when the constraint changes — nothing is hardcoded', () => {
    const renamed: RefusalPayload = { ...REPORTED, constraint: 'boundary_certified_when_issued' };
    expect(renamed.constraint).not.toBe(REPORTED.constraint);
    const [only] = refusalsFromRun(
      runAround([beat(2, 'merge', { refusal: renamed })]),
      SUBJECT,
    ).refusals;
    if (only?.state.kind !== 'refused') throw new Error('the renamed refusal did not narrow');
    expect(only.state.refusal.constraint).toBe(renamed.constraint);
  });
});

// ── The parsed refusal stays a weakened diagnosis ──────────────────────────

describe('beat 3 — a parsed exhibit must not look like a reported one', () => {
  it('carries constraint_source parsed through unchanged, and never upgrades it', () => {
    const second = refusalsFromRun(fourBeatRun(), SUBJECT).refusals[1];
    if (second?.state.kind !== 'refused') throw new Error('beat 3 did not narrow to a refusal');
    expect(second.state.refusal.constraint_source).toBe('parsed');
    expect(second.state.refusal.sqlstate).toBe(PARSED.sqlstate);
    expect(second.state.refusal.constraint).toBe(PARSED.constraint);
  });

  it('carries naa null with its stated reason, rather than an invented alternative', () => {
    const second = refusalsFromRun(fourBeatRun(), SUBJECT).refusals[1];
    if (second?.state.kind !== 'refused') throw new Error('beat 3 did not narrow to a refusal');
    expect(second.state.refusal.naa).toBeNull();
    expect(second.state.refusal.naa_reason).toBe(PARSED.naa_reason);
  });
});

// ── A refusal the payload did not contain is never rendered as one ─────────

describe('a refused beat that carries no payload is a defect, not a refusal', () => {
  it('names the beat and refuses to render it as a refusal', () => {
    const [only] = refusalsFromRun(
      runAround([beat(2, 'merge', { refusal: null })]),
      SUBJECT,
    ).refusals;
    expect(only?.state.kind).toBe('defect');
    if (only?.state.kind !== 'defect') return;
    expect(only.state.reason).toContain('refusal: null');
    expect(only.state.reason).toContain('merge');
  });

  it('treats an absent refusal member the same as an explicit null', () => {
    const withoutMember = { ...beat(2, 'merge') } as Record<string, unknown>;
    delete withoutMember.refusal;
    const [only] = refusalsFromRun(
      runAround([withoutMember as unknown as GateRunBeat]),
      SUBJECT,
    ).refusals;
    expect(only?.state.kind).toBe('defect');
  });

  it('lands a payload missing a required field in the defect state, naming the field', () => {
    const broken = { ...(REPORTED as unknown as Record<string, unknown>) };
    delete broken.constraint;
    const [only] = refusalsFromRun(
      runAround([beat(2, 'merge', { refusal: broken as unknown as RefusalPayload })]),
      SUBJECT,
    ).refusals;
    expect(only?.state.kind).toBe('defect');
    if (only?.state.kind !== 'defect') return;
    expect(only.state.reason).toContain('constraint');
  });
});

// ── Beat 4 is admitted, and admitted is not committed ──────────────────────

describe('an admitted beat never becomes a committed band', () => {
  it('contributes no band state at all — the whole transaction was rolled back', () => {
    const model = refusalsFromRun(
      runAround([beat(4, 'admit', { outcome: 'admitted', sqlstate: '00000' })]),
      SUBJECT,
    );
    expect(model.refusals).toEqual([]);
    expect(model.absence).toBe('no-refusal');
    expect(model.rolledBack).toBe(true);
  });
});

describe('an undecided run is not a refusal', () => {
  it('names 40001 as undecided rather than as an outcome of the gate', () => {
    const model = refusalsFromRun(
      runAround([beat(1, 'read', { outcome: 'read' })], {
        outcome: 'retry',
        transaction: { ...TRANSACTION, retry_sqlstate: '40001', closed_logical_timestamp: null },
      }),
      SUBJECT,
    );
    expect(model.refusals).toEqual([]);
    expect(model.absence).toBe('undecided');
    expect(model.retrySqlstate).toBe('40001');
  });
});

// ── Precedence: a reader’s own press is never displaced ────────────────────

describe('selectBand', () => {
  it('gives the band to the run’s first refusal when nothing was pressed here', () => {
    const selection = selectBand({ kind: 'none' }, refusalsFromRun(fourBeatRun(), SUBJECT));
    expect(selection.primarySource).toBe('run');
    expect(selection.primaryBeat?.ordinal).toBe(2);
    expect(selection.further.map((refusal) => refusal.ordinal)).toEqual([3]);
  });

  it('keeps this screen’s own attempt on the band, and drops none of the run’s', () => {
    const selection = selectBand({ kind: 'attempting' }, refusalsFromRun(fourBeatRun(), SUBJECT));
    expect(selection.primary).toEqual({ kind: 'attempting' });
    expect(selection.primarySource).toBe('attempt');
    expect(selection.primaryBeat).toBeNull();
    expect(selection.further.map((refusal) => refusal.ordinal)).toEqual([2, 3]);
  });
});

// ── R9: the on-ramp is additive, and every clause points at a field ────────

describe('the plain-language lead', () => {
  it('names the constraint the payload named, and counts the reason set it carries', () => {
    const lead = refusalLead(REPORTED);
    const joined = lead.sentences.join(' ');
    expect(joined).toContain(REPORTED.constraint);
    expect(joined).toContain(REPORTED.mus.length === 1 ? 'one thing' : `${REPORTED.mus.length} things`);
    expect(lead.basis).toContain('refusal.constraint');
    expect(lead.basis).toContain('refusal.mus');
  });

  it('quotes the nearest admissible alternative in the database’s own words', () => {
    const naa = REPORTED.naa;
    if (naa === null) throw new Error('the reported fixture lost its naa');
    const lead = refusalLead(REPORTED);
    expect(lead.sentences.join(' ')).toContain(naa.description);
    expect(lead.basis).toContain('refusal.naa.description');
  });

  it('states the reason when there is no alternative, and does not invent one', () => {
    const lead = refusalLead(PARSED);
    const joined = lead.sentences.join(' ');
    expect(joined).toContain(String(PARSED.naa_reason));
    expect(joined).not.toContain('restores admissibility');
    expect(lead.basis).toContain('refusal.naa_reason');
  });

  it('follows the reason set’s size rather than asserting one', () => {
    const two: RefusalPayload = { ...REPORTED, mus: [...REPORTED.mus, ...REPORTED.mus] };
    expect(refusalLead(two).sentences.join(' ')).toContain(`${two.mus.length} things`);
  });

  it('uses none of the forbidden words in any sentence this module composes', () => {
    const model = refusalsFromRun(fourBeatRun(), SUBJECT);
    const first = model.refusals[0];
    if (first === undefined) throw new Error('the run carried no refusal');
    const composed = [
      ...refusalLead(REPORTED).sentences,
      ...refusalLead(PARSED).sentences,
      ...refusalLead({ ...REPORTED, mus: [] }).sentences,
      ...refusalLead({ ...REPORTED, naa: null, naa_reason: null }).sentences,
      ...Object.values(RUN_ABSENCE_SENTENCE),
      runAttribution(model, first),
    ];
    for (const sentence of composed) {
      expect(forbiddenWordsIn(sentence), sentence).toEqual([]);
    }
  });
});

describe('the run attribution (R11)', () => {
  it('says which run, which beat, and that the transaction was rolled back', () => {
    const model = refusalsFromRun(fourBeatRun(), SUBJECT);
    const first = model.refusals[0];
    if (first === undefined) throw new Error('the run carried no refusal');
    const sentence = runAttribution(model, first);
    expect(sentence).toContain('run-under-test');
    expect(sentence).toContain('beat 2');
    expect(sentence).toContain('rolled back');
    expect(sentence).toContain(first.label);
  });

  it('does not claim a rollback the payload did not report', () => {
    const model = refusalsFromRun(
      fourBeatRun({ transaction: { ...TRANSACTION, disposition: 'committed' } }),
      SUBJECT,
    );
    const first = model.refusals[0];
    if (first === undefined) throw new Error('the run carried no refusal');
    expect(model.rolledBack).toBe(false);
    expect(runAttribution(model, first)).toContain('does not report');
  });
});
