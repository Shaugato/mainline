// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SECOND REFUSAL, AND THE FOUR WAYS A BUILDER COULD HAVE FAKED IT.
 *
 * ── WHERE THE PAYLOADS BELOW CAME FROM, AND WHERE THEY DID NOT ───────────────────────
 *
 * **These are NOT captures, and that is stated rather than implied.** The MEMBER NAMES are
 * `cr-gate-run.schema.json`'s — the contract the demo API owns and this workspace holds a
 * pinned verbatim copy of. The VALUES are this file's, and almost every one of them is a
 * `…-UNDER-TEST` token that no database has ever produced.
 *
 * That is deliberate and it is the strongest form this suite could take. A fixture carrying
 * `23514` and `cr_gate_closed_when_merged` would pass identically against a renderer that
 * had those two strings compiled into it — which is precisely the failure worth catching.
 * A fixture carrying `STATE-TWO-UNDER-TEST` cannot: the only way those characters reach the
 * screen is if the module printed the member it was handed. The complementary half is the
 * grep in `screen.test.ts`, which asserts that no SQLSTATE literal appears anywhere in
 * `src/operator/change/**` in the first place.
 *
 * ── THE FOUR LIES ────────────────────────────────────────────────────────────────────
 *
 *  1. print a refusal the payload did not carry — closed by the tokens above;
 *  2. re-state `persisted: false` as a conclusion with no readings behind it — closed by
 *     asserting the before/after table is rendered and that a reading which MOVED is marked
 *     rather than swallowed;
 *  3. render an undecided transaction (`40001`, `outcome: "retry"`) as a refusal — closed by
 *     asserting the undecided sentence and the ABSENCE of refusal chrome;
 *  4. treat "did not raise" as "passed" — closed by asserting a run whose verdict is not
 *     PROVEN renders its own `failures` list verbatim.
 */

import { describe, expect, it } from 'vitest';

import {
  isUndecided,
  readCrGateRun,
  renderCrGateRun,
} from '../../../../src/operator/change/cr-gate';

/** Member names from the contract; values from this file. See the note above. */
const RUN = {
  run_id: 'RUN-UNDER-TEST',
  generated_at: '2026-08-16T09:00:00.000000Z',
  outcome: 'completed',
  verdict: 'VERDICT-UNDER-TEST',
  persisted: false,
  elapsed_ms: 1234,
  failures: [],
  admission_beat: null,
  admission_absent_reason: 'ADMISSION-REASON-UNDER-TEST',
  admission_proved_by: 'PROVED-BY-UNDER-TEST',
  beats: [
    {
      ordinal: 1,
      name: 'read',
      label: 'LABEL-ONE-UNDER-TEST',
      outcome: 'observed',
      sqlstate: 'STATE-ONE-UNDER-TEST',
      constraint: null,
      constraint_source: null,
      message: null,
      statement: 'STATEMENT-ONE-UNDER-TEST',
      matched_expectation: true,
      elapsed_ms: 11,
      refusal: null,
    },
    {
      ordinal: 2,
      name: 'merge',
      label: 'LABEL-TWO-UNDER-TEST',
      outcome: 'refused',
      sqlstate: 'STATE-TWO-UNDER-TEST',
      constraint: 'CONSTRAINT-UNDER-TEST',
      constraint_source: 'SOURCE-UNDER-TEST',
      message: 'MESSAGE-UNDER-TEST',
      statement: 'STATEMENT-TWO-UNDER-TEST',
      matched_expectation: true,
      elapsed_ms: 22,
      refusal: { sqlstate: 'STATE-TWO-UNDER-TEST', constraint: 'CONSTRAINT-UNDER-TEST' },
    },
  ],
  persistence_check: {
    before: { change_request: { open_blocking: 1, state: 'STATE-BEFORE-UNDER-TEST' }, cr_event: 1 },
    after: { change_request: { open_blocking: 1, state: 'STATE-BEFORE-UNDER-TEST' }, cr_event: 1 },
    identical: true,
    self_persisted: false,
    note: 'NOTE-UNDER-TEST',
  },
};

function view(data: unknown, status = 200, raw = 'RAW-UNDER-TEST'): HTMLElement {
  return renderCrGateRun({ run: readCrGateRun(data), line: 'LINE-UNDER-TEST', raw, status });
}

describe('readCrGateRun — a payload is read, never assumed', () => {
  it('reads the beats, the failures and the fingerprint the payload carried', () => {
    const run = readCrGateRun(RUN);
    expect(run).not.toBeNull();
    expect(run?.beats).toHaveLength(2);
    expect(run?.beats[1]?.constraint).toBe('CONSTRAINT-UNDER-TEST');
    expect(run?.beats[1]?.carriedRefusal).toBe(true);
    expect(run?.beats[0]?.carriedRefusal).toBe(false);
    expect(run?.persisted).toBe(false);
    expect(run?.readings.map((reading) => reading.name)).toEqual([
      'change_request/open_blocking',
      'change_request/state',
      'cr_event',
    ]);
  });

  it('returns null for anything that is not a run, rather than an empty run', () => {
    // "We could not read it" and "the run carried no beats" are different sentences and
    // the caller has to be able to tell them apart.
    expect(readCrGateRun(null)).toBeNull();
    expect(readCrGateRun('a string')).toBeNull();
    expect(readCrGateRun({ error: { kind: 'no_route' } })).toBeNull();
    expect(readCrGateRun({ beats: 'not an array' })).toBeNull();
    expect(readCrGateRun({ beats: [] })?.beats).toEqual([]);
  });

  it('treats a member of the wrong type exactly as a missing one', () => {
    const run = readCrGateRun({ ...RUN, verdict: 7, persisted: 'false' });
    expect(run?.verdict).toBeNull();
    expect(run?.persisted).toBeNull();
  });

  it('carries every other scalar member of the payload through, unrenamed', () => {
    const run = readCrGateRun(RUN);
    const members = new Map(run?.otherMembers ?? []);
    expect(members.get('admission_beat')).toBe('null');
    expect(members.get('admission_absent_reason')).toBe('ADMISSION-REASON-UNDER-TEST');
    expect(members.get('admission_proved_by')).toBe('PROVED-BY-UNDER-TEST');
  });
});

describe('renderCrGateRun — lie 1: a refusal the payload did not carry', () => {
  it('prints the SQLSTATE, the constraint and how it was reported, from the payload', () => {
    const text = view(RUN).textContent ?? '';
    for (const token of [
      'STATE-ONE-UNDER-TEST',
      'STATE-TWO-UNDER-TEST',
      'CONSTRAINT-UNDER-TEST',
      'SOURCE-UNDER-TEST',
      'MESSAGE-UNDER-TEST',
      'STATEMENT-TWO-UNDER-TEST',
    ]) {
      expect(text).toContain(token);
    }
  });

  it('renders an absence for a beat member the payload left null', () => {
    const text = view(RUN).textContent ?? '';
    // Beat one carries no constraint. The cell says so; it does not borrow beat two's.
    expect(text).toContain('none');
    expect(text).toContain('not stated');
  });

  it('shows the verbatim bytes and claims nothing when the body is not a run', () => {
    const rendered = view({ error: { kind: 'no_route', status: 404 } }, 404, 'BYTES-UNDER-TEST');
    expect(rendered.querySelector('pre.moc-raw')?.textContent).toBe('BYTES-UNDER-TEST');
    expect(rendered.textContent).toContain('is not a gate run this page can read');
    expect(rendered.querySelectorAll('table')).toHaveLength(0);
  });
});

describe('renderCrGateRun — lie 2: persisted:false with nothing behind it', () => {
  it('renders BOTH fingerprints as columns beside the conclusion', () => {
    const rendered = view(RUN);
    const rows = [...rendered.querySelectorAll('table')]
      .flatMap((table) => [...table.querySelectorAll('tbody tr')])
      .map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent));
    expect(rows).toContainEqual(['change_request/open_blocking', '1', '1', 'no']);
    expect(rendered.textContent).toContain('persistence_check.identical');
    expect(rendered.textContent).toContain('NOTE-UNDER-TEST');
  });

  it('MARKS a reading that moved rather than letting the summary swallow it', () => {
    const moved = {
      ...RUN,
      persistence_check: {
        ...RUN.persistence_check,
        after: { change_request: { open_blocking: 0, state: 'STATE-AFTER-UNDER-TEST' }, cr_event: 1 },
      },
    };
    const rendered = view(moved);
    expect(rendered.querySelectorAll('tr.moc-moved')).toHaveLength(2);
    expect(rendered.textContent).toContain('2 readings moved');
    expect(rendered.textContent).not.toContain('No reading in the fingerprint moved');
  });

  it('says there is no fingerprint rather than implying one, when none arrived', () => {
    const rendered = view({ ...RUN, persistence_check: undefined });
    expect(rendered.textContent).toContain('carried no before/after fingerprint');
  });
});

describe('renderCrGateRun — lie 3: an undecided transaction dressed as a refusal', () => {
  const undecided = { ...RUN, outcome: 'retry', verdict: null, beats: [RUN.beats[0]] };

  it('classifies it as undecided and says so in words', () => {
    const run = readCrGateRun(undecided);
    expect(run).not.toBeNull();
    expect(run === null ? false : isUndecided(run)).toBe(true);
    const text = view(undecided).textContent ?? '';
    expect(text).toContain('left undecided');
    expect(text).toContain('not a refusal');
  });

  it('does not print a verdict line for it, because there is no reason set', () => {
    const text = view(undecided).textContent ?? '';
    expect(text).not.toContain('verdict ');
  });
});

describe('renderCrGateRun — lie 4: "did not raise" rendered as "passed"', () => {
  it('lists the run’s own failures, verbatim, when the verdict is not proven', () => {
    const notProven = {
      ...RUN,
      verdict: 'NOT PROVEN',
      failures: ['FAILURE-ONE-UNDER-TEST', 'FAILURE-TWO-UNDER-TEST'],
    };
    const rendered = view(notProven);
    expect([...rendered.querySelectorAll('li.moc-route-missing')].map((li) => li.textContent)).toEqual(
      ['FAILURE-ONE-UNDER-TEST', 'FAILURE-TWO-UNDER-TEST'],
    );
    expect(rendered.textContent).toContain('NOT PROVEN');
  });

  it('prints matched_expectation as the payload stated it, for every beat', () => {
    const mixed = {
      ...RUN,
      beats: [RUN.beats[0], { ...RUN.beats[1], matched_expectation: false }],
    };
    const cells = [...view(mixed).querySelectorAll('tbody tr')].map((tr) =>
      [...tr.querySelectorAll('td')].map((td) => td.textContent),
    );
    expect(cells[0]?.[6]).toBe('true');
    expect(cells[1]?.[6]).toBe('false');
  });
});
