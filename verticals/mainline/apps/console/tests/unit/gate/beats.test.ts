// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * THE BEAT MODEL, AND THE ONE LIE IT IS BUILT TO MAKE IMPOSSIBLE.
 *
 * `docs/leads/demo-story-plan.md` R11 permits the four beats to be revealed one after
 * another and forbids the reveal from ever being mistaken for the run. The failure mode
 * that ruling exists to prevent is specific and would be undetectable on a screenshot:
 *
 *   a panel that staged the beats 120 ms apart and then printed "120 ms" beside each one.
 *
 * Every reader would take those numbers for measurements. They would be this console's
 * own pacing, rendered as though the database had reported it. So the fixtures below give
 * the beats elapsed values that are DELIBERATELY NOT the reveal step and not each other —
 * a module that printed a delay instead of a measurement would produce four identical
 * strings, and §2 fails on exactly that.
 *
 * The rest is what R12 makes checkable: the step is the EVIDENCE register's own token and
 * is under its ceiling, the order is the payload's `ordinal` rather than the array's, and
 * the second refusal is identified by POSITION rather than by any code (D18).
 */

import { describe, expect, it } from 'vitest';

import {
  REVEAL_STEP_MS,
  clauseIdFromRun,
  elapsedText,
  revealPlan,
  type GateRunBeat,
} from '../../../src/features/gate/beats';
import { DURATION_MS, EVIDENCE_CEILING_MS } from '../../../src/design/motion';
import type { RefusalPayload } from '../../../src/data/types.generated';
import { nodeFs } from '../data/_support';

const MODULE = 'src/features/gate/beats.ts';

// ── Fixtures ───────────────────────────────────────────────────────────────

/**
 * Elapsed values chosen to be hostile to the defect this file is about.
 *
 * None of them is 0, 120, 240 or 360 — the four numbers a reveal-delay leak would
 * produce — and no two are equal, so a plan that substituted a uniform value could not
 * survive a comparison against the payload.
 */
const ELAPSED: Readonly<Record<number, number>> = { 1: 0.011, 2: 527.051, 3: 472.401, 4: 392.347 };

function beat(ordinal: number, outcome: string, over: Partial<GateRunBeat> = {}): GateRunBeat {
  return {
    ordinal,
    name: `beat_${ordinal}`,
    label: `beat ${ordinal}, as the fixture describes it`,
    expected: { outcome },
    outcome,
    sqlstate: null,
    constraint: null,
    constraint_source: null,
    message: null,
    matched_expectation: true,
    elapsed_ms: ELAPSED[ordinal] ?? ordinal,
    statement: null,
    observed: {},
    note: null,
    ...over,
  };
}

/** The four-beat shape the demonstration produces: read, refuse, refuse again, admit. */
function fourBeats(): readonly GateRunBeat[] {
  return [beat(1, 'read'), beat(2, 'refused'), beat(3, 'refused'), beat(4, 'admitted')];
}

/**
 * A refusal payload carrying one `mus` atom of the requested kind.
 *
 * Built through the GENERATED `RefusalPayload` type rather than a local shape, so a
 * change to `spec/wire/refusal.md` breaks this fixture at type-check time instead of
 * letting it drift into a second opinion about the wire.
 */
function refusalWith(mus: RefusalPayload['mus']): RefusalPayload {
  return {
    spec_version: '1.0',
    refusal_id: '00000000-0000-4000-8000-00000000000f',
    observed_at: '2026-08-15T00:00:00Z',
    class: 'gate',
    sqlstate: '23514',
    constraint: 'planted_constraint_not_the_real_one',
    constraint_source: 'reported',
    message: 'PLANTED REFUSAL MESSAGE',
    subject_kind: 'permit',
    subject_id: '00000000-0000-4000-8000-000000000001',
    gate_epoch: 1,
    diagnosis: 'declarative',
    probe_calls: 0,
    mus,
    naa: null,
    naa_reason: 'not_computable',
  };
}

// ── 1. The step is the register's own, and under its ceiling ───────────────

describe('the reveal step', () => {
  it('equals the EVIDENCE duration token — the weld the register boundary forces', () => {
    // `src/features/gate/**` may not import `src/design/motion.ts`: eslint.config.js
    // denies every EVIDENCE directory any specifier ending in a segment named `motion`,
    // to stop this directory acquiring an animation dependency by degrees. So the step is
    // DECLARED in beats.ts and CHECKED here, in that direction.
    //
    // This assertion is one link of a chain, not a lone number: `motion.test.ts` already
    // pins DURATION_MS.evidence against `--tp-duration-evidence` in tokens.css, and
    // `demo-driver.test.tsx` §10 reads demo-driver.module.css and requires every step to
    // be expressed as that same token. Break any link and one of the three goes red.
    expect(REVEAL_STEP_MS).toBe(DURATION_MS.evidence);
  });

  it('is under the EVIDENCE ceiling, so no step outlives the register’s law', () => {
    // docs/leads/ui.md §1.1 — no easing over 160 ms on an EVIDENCE surface, and
    // demo-story-plan R12 restates it for this reveal specifically.
    expect(REVEAL_STEP_MS).toBeLessThanOrEqual(EVIDENCE_CEILING_MS);
    expect(REVEAL_STEP_MS).toBeGreaterThan(0);
  });

  it('spaces every consecutive pair by exactly one step', () => {
    const cues = revealPlan(fourBeats(), 'all');
    const gaps = cues.slice(1).map((cue, index) => cue.delayMs - (cues[index]?.delayMs ?? 0));
    expect(gaps).toEqual([REVEAL_STEP_MS, REVEAL_STEP_MS, REVEAL_STEP_MS]);
    for (const gap of gaps) expect(gap).toBeLessThanOrEqual(EVIDENCE_CEILING_MS);
  });
});

// ── 2. A delay is not a measurement ────────────────────────────────────────

describe('the number a reader sees is the payload’s, never the reveal’s', () => {
  it('renders each beat’s own elapsed_ms verbatim, with no rounding', () => {
    for (const cue of revealPlan(fourBeats(), 'all')) {
      expect(elapsedText(cue.beat)).toBe(`${cue.beat.elapsed_ms} ms`);
    }
    // 0.011 must survive as 0.011. A beat that took eleven microseconds and one that took
    // half a second are the difference between a read and a round trip through the gate
    // function, and rounding both would erase the only comparison the row is for.
    expect(elapsedText(beat(1, 'read'))).toBe('0.011 ms');
    expect(elapsedText(beat(2, 'refused'))).toBe('527.051 ms');
  });

  it('produces four DIFFERENT durations, which a leaked delay could not', () => {
    const rendered = revealPlan(fourBeats(), 'all').map((cue) => elapsedText(cue.beat));
    expect(new Set(rendered).size).toBe(4);
  });

  it('never renders a delay: no cue’s text equals its own delay', () => {
    // The direct statement of the defect. If `elapsedText` ever read `delayMs`, every
    // one of these would match and the panel would be printing its own pacing as though
    // the database had reported it.
    for (const cue of revealPlan(fourBeats(), 'all')) {
      expect(elapsedText(cue.beat)).not.toBe(`${cue.delayMs} ms`);
    }
  });

  it('is a function of the beat alone — a re-ordered plan changes no duration', () => {
    const forwards = revealPlan(fourBeats(), 'all').map((cue) => elapsedText(cue.beat));
    const backwards = revealPlan([...fourBeats()].reverse(), 'all').map((cue) =>
      elapsedText(cue.beat),
    );
    expect(backwards).toEqual(forwards);
  });
});

// ── 3. Ordinal order, taken from the payload and not from the array ────────

describe('the reading order', () => {
  it('is the payload’s ordinal, even when the array arrived shuffled', () => {
    const shuffled = [beat(3, 'refused'), beat(1, 'read'), beat(4, 'admitted'), beat(2, 'refused')];
    const cues = revealPlan(shuffled, 'all');
    expect(cues.map((cue) => cue.beat.ordinal)).toEqual([1, 2, 3, 4]);
    expect(cues.map((cue) => cue.stepIndex)).toEqual([0, 1, 2, 3]);
  });

  it('does not renumber the payload — ordinals are carried, steps are computed', () => {
    // A plan that showed one beat must still report the ordinal the emitter gave it.
    const cues = revealPlan(fourBeats(), 3);
    expect(cues).toHaveLength(1);
    expect(cues[0]?.beat.ordinal).toBe(3);
    expect(cues[0]?.stepIndex).toBe(0);
    expect(cues[0]?.delayMs).toBe(0);
  });

  it('mutates nothing it was handed', () => {
    const beats = fourBeats();
    const before = beats.map((each) => each.ordinal);
    revealPlan([...beats].reverse(), 'all');
    revealPlan(beats, 'all');
    expect(beats.map((each) => each.ordinal)).toEqual(before);
  });

  it('selects exactly the named beat for a single-beat control', () => {
    for (const reveal of [2, 3, 4] as const) {
      const cues = revealPlan(fourBeats(), reveal);
      expect(cues.map((cue) => cue.beat.ordinal)).toEqual([reveal]);
    }
  });

  it('answers an empty plan for an empty payload rather than throwing', () => {
    expect(revealPlan([], 'all')).toEqual([]);
    expect(revealPlan([], 2)).toEqual([]);
  });
});

// ── 4. The second refusal is a POSITION, never a code (D18) ────────────────

describe('the refusal index', () => {
  it('counts refusals in reading order and leaves every other beat null', () => {
    const cues = revealPlan(fourBeats(), 'all');
    expect(cues.map((cue) => cue.refusalIndex)).toEqual([null, 0, 1, null]);
  });

  it('is derived from outcome alone — the demo’s own codes change nothing', () => {
    // The exhibits are planted as values no beat of this demonstration produces. If the
    // index were being chosen from a SQLSTATE or a constraint name, this plan would
    // disagree with the one above; it does not, because neither is read.
    const planted = [
      beat(1, 'read', { sqlstate: '01000' }),
      beat(2, 'refused', { sqlstate: '42501', constraint: 'planted_not_the_real_one' }),
      beat(3, 'refused', { sqlstate: 'P0002', constraint: 'planted.fn_not_the_real_one' }),
      beat(4, 'admitted', { sqlstate: '02000' }),
    ];
    expect(revealPlan(planted, 'all').map((cue) => cue.refusalIndex)).toEqual([null, 0, 1, null]);
  });

  it('restarts at zero for a control that reveals one refusing beat', () => {
    // A single-beat reveal has one refusal and it is the first one SHOWN. The heavier
    // rule belongs to the second refusal of a sequence; a lone beat has no sequence.
    expect(revealPlan(fourBeats(), 3)[0]?.refusalIndex).toBe(0);
  });

  it('handles a run where nothing refused', () => {
    const cues = revealPlan([beat(1, 'read'), beat(4, 'admitted')], 'all');
    expect(cues.map((cue) => cue.refusalIndex)).toEqual([null, null]);
  });
});

// ── 5. The clause identifier, read by presence and not by cast ─────────────

describe('the clause a reason set names', () => {
  it('reads the first clause_id any refusing beat carries', () => {
    const beats = [
      beat(1, 'read'),
      beat(2, 'refused', {
        refusal: refusalWith([
          {
            kind: 'obligation',
            obligation_id: '00000000-0000-4000-8000-000000000007',
            clause_id: '00000000-0000-4000-8000-000000000004',
          },
        ]),
      }),
    ];
    expect(clauseIdFromRun(beats)).toBe('00000000-0000-4000-8000-000000000004');
  });

  it('answers null for atom kinds that carry no clause, rather than inventing one', () => {
    // `authority_gap` genuinely has no clause. Asking it for one would be this module
    // asserting a field the emitter did not send — R10, no invention anywhere.
    const beats = [
      beat(2, 'refused', {
        refusal: refusalWith([
          { kind: 'authority_gap', relation: 'mainline.signer', key: { site_id: null } },
        ]),
      }),
    ];
    expect(clauseIdFromRun(beats)).toBeNull();
  });

  it('answers null for a run with no refusal at all', () => {
    expect(clauseIdFromRun(fourBeats())).toBeNull();
    expect(clauseIdFromRun([])).toBeNull();
  });
});

// ── 6. D18, enforced by what the module does not contain ───────────────────

describe('the module chooses nothing from a code', () => {
  it('compares no SQLSTATE and no constraint name against a literal', async () => {
    const fs = await nodeFs();
    const code = fs
      .readFileSync(MODULE, 'utf8')
      .split(/\r?\n/)
      .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
      .join('\n');

    expect(code).not.toMatch(/\bsqlstate\b\s*[=!]==\s*['"]/i);
    expect(code).not.toMatch(/\bconstraint\b\s*[=!]==\s*['"]/i);
    expect(code).not.toMatch(/[=!]==\s*['"](?:23514|P0001|00000)['"]/);
    expect(code).not.toMatch(/\.(?:includes|startsWith|match)\(\s*['"](?:23514|P0001)['"]/);
  });

  it('declares exactly one duration, so there is one thing for the weld to hold', async () => {
    const fs = await nodeFs();
    const code = fs
      .readFileSync(MODULE, 'utf8')
      .split(/\r?\n/)
      .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
      .join('\n');

    // A second duration typed anywhere in this module would be one the assertion above
    // does not cover — a millisecond count that could drift away from the token in
    // silence. `REVEAL_STEP_MS` is the only one, and every other pace on the screen is
    // derived from it by multiplication.
    expect(code).toMatch(/export const REVEAL_STEP_MS = \d+;/);
    expect(code.match(/\b\d{2,}\b/g) ?? []).toEqual([String(REVEAL_STEP_MS)]);
  });

  it('imports nothing the EVIDENCE register forbids it to import', async () => {
    // The reason the constant is declared rather than imported, restated as a check.
    // eslint.config.js denies this directory any specifier ending in a `motion` segment;
    // an `eslint-disable` added to save one number would defeat the boundary quietly, and
    // this fails loudly instead.
    const fs = await nodeFs();
    const source = fs.readFileSync(MODULE, 'utf8');

    // Scoped to code, because the docstring EXPLAINS why an `eslint-disable` would be the
    // wrong fix and has to be able to name it. Same reason `demo-driver.test.tsx` scopes
    // its 404 scan to the prose a reader is shown rather than the whole file.
    const code = source
      .split(/\r?\n/)
      .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
      .join('\n');
    expect(code).not.toMatch(/eslint-disable/);

    for (const match of source.matchAll(/from\s+['"]([^'"]+)['"]/g)) {
      const specifier = match[1] ?? '';
      expect(specifier.split('/').pop(), specifier).not.toBe('motion');
      expect(specifier.startsWith('@react-three/'), specifier).toBe(false);
    }
  });
});
