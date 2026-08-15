// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE REFUSAL LANDS IN THE SCREEN'S OWN BAND — the defect, reproduced and then pinned.
 *
 * `docs/leads/demo-story-plan.md` §0.4(i), measured on the live console 2026-08-15: a
 * reader pressed MERGE, the driver panel reported `beat 2 · merge · REFUSED · 23514 ·
 * gate_closed_when_issued`, and further down the SAME page the screen's own refusal band
 * still read **NO ATTEMPT — NOTHING HAS BEEN REFUSED** with **NO REASON SET** beside it.
 * R7 rules on it, in BOTH directions, and both directions are asserted here:
 *
 *   • **published run ⇒ the band is the refusal.** The constraint, the SQLSTATE, the
 *     `constraint_source`, the minimal unsatisfiable subset AND the nearest admissible
 *     alternative — the last of which appeared nowhere in the console before this.
 *   • **no run ⇒ nothing moves.** `NO ATTEMPT` and `NO REASON SET` render exactly as they
 *     did before any of this was wired: the same sentences, and no lead, no attribution
 *     line and no second band added around them. The console must never predict a refusal
 *     it has not seen.
 *
 * ── WHERE THE VALUES COME FROM ───────────────────────────────────────────────────
 *
 * The two refusal payloads are read out of `fixtures/bundles/demo-cloud/`, decoded from
 * captured response bodies — the seeded cloud's own bytes — and located by their own
 * `constraint_source` rather than by any identifier typed here. Nothing in this file
 * retypes `23514`, `gate_closed_when_issued`, `P0001`, an obligation id or the NAA
 * sentence; every expectation is read off the fixture, so a component that hardcoded any
 * of them would pass nothing.
 *
 * The four-beat run AROUND those payloads is assembled here, because the console holds no
 * captured `POST /v1/demo/gate-run` frame. That is a fixture and it is confined to this
 * file: the surface itself only ever renders what Contract B publishes.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { GateSurfaceRoot } from '../../../src/features/gate/GateSurfaceRoot';
import { GateTransportContext } from '../../../src/features/gate/transport-context';
import { publishLastGateRun, resetLastGateRun } from '../../../src/features/gate/last-run';
import type { GateRunBeat, GateRunData } from '../../../src/features/gate/beats';
import type { RefusalPayload } from '../../../src/data/types.generated';
import { bundleFiles, bundleTransport, permitId } from './_support';

// ── The captured exhibits ──────────────────────────────────────────────────

const RAW_FRAMES: Record<string, unknown> = import.meta.glob(
  '/fixtures/bundles/demo-cloud/frames/*.json',
  { query: '?raw', import: 'default', eager: true },
);

interface CapturedFrame {
  readonly response: { readonly body_b64: string };
}

interface CapturedInvoke {
  readonly data?: { readonly refusal?: RefusalPayload | null } | null;
}

function capturedRefusals(): readonly RefusalPayload[] {
  const found: RefusalPayload[] = [];
  for (const path of Object.keys(RAW_FRAMES).sort()) {
    const text = RAW_FRAMES[path];
    if (typeof text !== 'string') continue;
    const frame = JSON.parse(text) as CapturedFrame;
    const body = new TextDecoder('utf-8', { fatal: true }).decode(
      Uint8Array.from(atob(frame.response.body_b64), (character) => character.charCodeAt(0)),
    );
    const refusal = (JSON.parse(body) as CapturedInvoke).data?.refusal;
    if (refusal !== null && refusal !== undefined) found.push(refusal);
  }
  if (found.length === 0) {
    throw new Error(
      'tests/unit/gate/refusal-band.test.tsx: no captured demo-cloud frame carried a refusal, so ' +
        'every expectation below would be vacuous.',
    );
  }
  return found;
}

function refusalWithSource(source: 'reported' | 'parsed'): RefusalPayload {
  const match = capturedRefusals().find((refusal) => refusal.constraint_source === source);
  if (match === undefined) {
    throw new Error(`no captured demo-cloud frame carries constraint_source "${source}".`);
  }
  return match;
}

const REPORTED = refusalWithSource('reported');
const PARSED = refusalWithSource('parsed');

// ── The screen, and the run published beneath it ───────────────────────────

const files = bundleFiles();
const subject = permitId();

function beat(ordinal: number, name: string, over: Partial<GateRunBeat>): GateRunBeat {
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
    elapsed_ms: ordinal,
    statement: null,
    observed: {},
    note: null,
    refusal: null,
    ...over,
  };
}

/** The four beats, carrying the captured refusals, against the addressed permit. */
function measuredRun(): GateRunData {
  return {
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
    run_id: 'run-under-test',
    generated_at: '2026-08-15T00:00:00Z',
    outcome: 'completed',
    verdict: 'PROVEN',
    failures: [],
    persisted: false,
    elapsed_ms: 1658.5,
    transaction: {
      isolation: 'SERIALIZABLE',
      disposition: 'rolled_back',
      opened_logical_timestamp: '1',
      closed_logical_timestamp: '1',
      single_transaction: true,
      savepoints: [],
      retry_sqlstate: null,
      canonicalisation: 'rfc8785',
    },
    subject: {
      subject_kind: 'permit',
      subject_id: subject,
      external_ref: 'DEMO-PTW-0001',
      state: 'dispositioned',
      head_seq: 1,
      gate_epoch: 1,
      open_blocking: 1,
      open_blocking_derived: 1,
      blocking_check_id: null,
      exposure_receipt_id: null,
      site_code: 'site',
    },
    beats: [
      beat(1, 'read', { outcome: 'read', sqlstate: '00000' }),
      beat(2, 'merge', { label: 'merge the permit', refusal: REPORTED, elapsed_ms: 513.15 }),
      beat(3, 'projection_drift_attack', {
        label: 'forge the counter and merge',
        refusal: PARSED,
        elapsed_ms: 532.16,
      }),
      beat(4, 'admit', { outcome: 'admitted', sqlstate: '00000' }),
    ],
    persistence_check: {
      before: { row_counts: {}, subject_row_counts: {}, permit_row: null },
      after: { row_counts: {}, subject_row_counts: {}, permit_row: null },
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
  };
}

function mount(): void {
  render(
    <GateTransportContext.Provider value={bundleTransport(files)}>
      <GateSurfaceRoot />
    </GateTransportContext.Provider>,
  );
}

beforeEach(() => {
  resetLastGateRun();
  window.location.hash = `#/gate?permit=${subject}`;
});

afterEach(() => {
  resetLastGateRun();
  window.location.hash = '';
});

// ── R7, second direction: with no run, nothing moves ──────────────────────

describe('with no completed run, the band is exactly what it was', () => {
  it('says nothing has been refused, in the same words, with nothing added around it', async () => {
    mount();
    const bar = await screen.findByTestId('refusal-bar');

    expect(bar.dataset.state).toBe('none');
    expect(bar.textContent).toContain('no attempt — nothing has been refused');
    expect(bar.textContent).toContain(
      'This band shows a refusal only after the database has issued one.',
    );
    expect(bar.textContent).toContain('the console will not predict one');
    expect(bar.dataset.constraint).toBeUndefined();
    expect(bar.dataset.sqlstate).toBeUndefined();
    expect(bar.dataset.constraintSource).toBeUndefined();

    // Nothing this worker added appears when nothing has been run.
    expect(screen.queryByTestId('refusal-lead')).toBeNull();
    expect(screen.queryByTestId('refusal-from-run')).toBeNull();
    expect(screen.queryByTestId('run-absence')).toBeNull();
    expect(screen.queryByTestId('further-refusal')).toBeNull();
  });

  it('keeps NO REASON SET, and shows no reason set panel', async () => {
    mount();
    const absent = await screen.findByTestId('reason-set-absent');
    expect(absent.textContent).toContain('no reason set');
    expect(absent.textContent).toContain(
      'A minimal unsatisfiable subset exists only for a refusal that happened.',
    );
    expect(screen.queryByTestId('mus-panel')).toBeNull();
    expect(screen.queryByTestId('naa-panel')).toBeNull();
  });
});

describe('a run that drove another permit', () => {
  it('leaves the band alone and says whose run it declined to show', async () => {
    publishLastGateRun({
      ...measuredRun(),
      subject: { ...measuredRun().subject, subject_id: 'dec0de00-9999-4000-8000-000000000009' },
    });
    mount();

    const bar = await screen.findByTestId('refusal-bar');
    expect(bar.dataset.state).toBe('none');
    expect(screen.queryByTestId('mus-panel')).toBeNull();
    expect((await screen.findByTestId('run-absence')).dataset.absence).toBe('other-subject');
  });
});

// ── R7, first direction: the refusal reaches the band ─────────────────────

describe('beat 2 — the refusal lands in the screen’s own band', () => {
  beforeEach(() => {
    publishLastGateRun(measuredRun());
  });

  it('shows the constraint, the SQLSTATE and the constraint_source the payload carries', async () => {
    mount();
    const bar = await screen.findByTestId('refusal-bar');

    expect(bar.dataset.state).toBe('refused');
    expect(bar.dataset.constraint).toBe(REPORTED.constraint);
    expect(bar.dataset.sqlstate).toBe(REPORTED.sqlstate);
    expect(bar.dataset.constraintSource).toBe('reported');
    expect(screen.getByTestId('refusal-constraint').textContent).toContain(REPORTED.constraint);
    expect(screen.getByTestId('refusal-sqlstate').textContent).toContain(REPORTED.sqlstate);
    expect(screen.getByTestId('refusal-constraint-source').textContent).toBe('reported');
    // A reported exhibit is NOT announced as a weakened diagnosis.
    expect(screen.queryByTestId('refusal-parsed')).toBeNull();
  });

  it('renders the database’s own message, verbatim', async () => {
    mount();
    expect((await screen.findByTestId('refusal-message')).textContent).toBe(REPORTED.message);
  });

  it('shows the irreducible reason set — the obligation, its severity and its virulence', async () => {
    mount();
    const list = await screen.findByTestId('mus-list');
    const atom = REPORTED.mus[0];
    if (atom?.kind !== 'obligation') {
      throw new Error('the captured reported refusal no longer leads with an obligation atom');
    }
    expect(list.textContent).toContain(atom.obligation_id);
    expect(list.textContent).toContain(String(atom.severity));
    expect(list.textContent).toContain(String(atom.virulence));
    expect(list.textContent).toContain(String(atom.detail));
  });

  it('renders the nearest admissible alternative and every legal kind it names', async () => {
    mount();
    const naa = REPORTED.naa;
    if (naa?.kind !== 'dispose_obligations') {
      throw new Error('the captured reported refusal no longer carries a dispose_obligations naa');
    }
    expect((await screen.findByTestId('naa-description')).textContent).toBe(naa.description);
    const panel = screen.getByTestId('naa-panel');
    for (const kind of naa.legal_kinds ?? []) {
      expect(panel.textContent, kind).toContain(kind);
    }
    for (const id of naa.obligation_ids) {
      expect(panel.textContent, id).toContain(id);
    }
    expect(screen.getByTestId('naa-kind').textContent).toBe(naa.kind);
  });

  it('leads with plain language that quotes the payload rather than replacing it', async () => {
    mount();
    const lead = await screen.findByTestId('refusal-lead');
    const naa = REPORTED.naa;
    if (naa === null) throw new Error('the captured reported refusal lost its naa');
    expect(lead.textContent).toContain(REPORTED.constraint);
    expect(lead.textContent).toContain(naa.description);
    // The exhibit is still below the lead, unmoved.
    expect(screen.getByTestId('refusal-bar').textContent).toContain(REPORTED.constraint);
  });

  it('says the refusal came from a run, and that the run’s transaction was rolled back', async () => {
    mount();
    const line = await screen.findByTestId('refusal-from-run');
    expect(line.textContent).toContain('run-under-test');
    expect(line.textContent).toContain('beat 2');
    expect(line.textContent).toContain('rolled back');
  });
});

// ── Beat 3 — the second refusal, and it must look weaker ──────────────────

describe('beat 3 — refused again after the counter was forged', () => {
  beforeEach(() => {
    publishLastGateRun(measuredRun());
  });

  it('renders its own band with its own SQLSTATE and raising object', async () => {
    mount();
    const bar = await screen.findByTestId('refusal-bar-beat-3');
    expect(bar.dataset.sqlstate).toBe(PARSED.sqlstate);
    expect(bar.dataset.constraint).toBe(PARSED.constraint);
    expect(bar.dataset.constraintSource).toBe('parsed');
  });

  it('announces the parsed exhibit as a WEAKENED DIAGNOSIS', async () => {
    mount();
    const notice = await screen.findByTestId('refusal-parsed-beat-3');
    expect(notice.textContent).toContain('WEAKENED DIAGNOSIS');
    expect(notice.textContent).toContain('constraint_source');
    expect(screen.getByTestId('refusal-constraint-source-beat-3').textContent).toBe('parsed');
  });

  it('states naa_reason rather than inventing an alternative', async () => {
    mount();
    const absent = await screen.findByTestId('naa-absent-beat-3');
    expect(absent.dataset.naaReason).toBe(PARSED.naa_reason);
    expect(screen.queryByTestId('naa-beat-3')).toBeNull();
  });

  it('is attributed to its own beat, with the payload’s own elapsed_ms', async () => {
    mount();
    const panel = await screen.findByTestId('further-refusal');
    expect(panel.dataset.beat).toBe('3');
    expect(screen.getByTestId('further-refusal-elapsed').textContent).toBe('532.16');
  });

  it('gives the two reason sets different element ids, so neither steals the other’s label', async () => {
    mount();
    await screen.findByTestId('mus-panel');
    const ids = [...document.querySelectorAll('[id]')].map((node) => node.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

// ── Precedence: a reader’s own press is never displaced ───────────────────

/**
 * TWO real exchanges through the real verifier — the permit read and then the merge — so
 * this one case is given its own budget explicitly rather than being tuned by moving the
 * suite's default. `selectBand` pins the same precedence rule as a pure function in
 * `refusal-from-run.test.ts` and costs nothing; what this adds, and what is worth twenty
 * seconds, is that `GateScreen` HONOURS it against a transport that really hashes bytes.
 */
const TWO_REAL_EXCHANGES_MS = 20_000;

describe('when the reader presses the control on this screen', () => {
  it('keeps their own attempt on the headline band and demotes the run’s refusals', async () => {
    publishLastGateRun(measuredRun());
    mount();
    await screen.findByTestId('refusal-bar');

    // The control is disabled until the permit read lands — an attempt against a subject
    // this screen has not read would have no gate epoch to pin.
    const button = await screen.findByTestId('attempt-merge');
    await waitFor(
      () => {
        expect(button).toBeEnabled();
      },
      // The real verifier SHA-256s every file in the bundle before the permit read is
      // served, and under a full parallel suite that is well past the default second.
      { timeout: 8000 },
    );
    await userEvent.click(button);

    await waitFor(
      () => {
        // The bundle's own merge refusal — a different payload from the run's.
        expect(screen.getAllByTestId('further-refusal')).toHaveLength(2);
      },
      // The bundle verifier hashes every file before the merge frame is served, so this
      // exchange is genuinely slow. The wait is for the REAL transport, not a stub.
      { timeout: 8000 },
    );
    const beats = screen.getAllByTestId('further-refusal').map((node) => node.dataset.beat);
    expect(beats).toEqual(['2', '3']);
    expect(screen.queryByTestId('refusal-from-run')).toBeNull();
  }, TWO_REAL_EXCHANGES_MS);
});
