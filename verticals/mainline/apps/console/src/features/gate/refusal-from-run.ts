// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ADAPTER THAT CARRIES A RUN'S REFUSAL INTO THE SCREEN'S OWN REFUSAL BAND.
 *
 * ── THE DEFECT THIS FIXES ────────────────────────────────────────────────────────
 *
 * Measured on the live console, 2026-08-15. A reader addressed the seeded permit at
 * `#/gate?permit=<the seeded permit>` and pressed MERGE. The driver panel reported
 * `beat 2 · merge · REFUSED · SQLSTATE 23514 · gate_closed_when_issued`. At the
 * same moment, further down the SAME page, the screen's refusal band still read
 * *"NO ATTEMPT — NOTHING HAS BEEN REFUSED"* and the reason set read *"NO REASON SET"*.
 * The product's entire argument had happened and the component built to display it said
 * nothing had happened.
 *
 * `POST /v1/demo/gate-run` and `POST /v1/permits/{id}/merge` are two different exchanges,
 * and `useGateData` only ever watched the second. This module is the join: it reads the
 * run payload the driver already received and hands the band the shape it already
 * consumes. It is PURE — no React, no fetch, no clock, no `Math.random` — so every rule
 * below is decidable by a unit test rather than by opening a browser.
 *
 * ── THE FOUR RULES IT MAKES STRUCTURAL ───────────────────────────────────────────
 *
 *   • **Nothing is predicted.** With no run there is no refusal, and
 *     {@link refusalsFromRun} returns an empty list whose {@link RunRefusalModel.absence}
 *     is `no-run`. `GateScreen` then renders exactly what it renders today. R7 binds in
 *     both directions: the console must never show a refusal it has not seen.
 *   • **A run against another subject is not this screen's refusal.** The gate surface is
 *     about ONE permit. A run whose `subject.subject_id` is a different permit lands in
 *     `other-subject` and renders nothing on the band — attributing another subject's
 *     refusal to this one would be a fabrication with a real SQLSTATE attached to it.
 *   • **A refusing beat with no `refusal` object is a DEFECT, never a refusal.** The beat
 *     says it was refused and carries nothing to render; `readRefusal` narrows, and a
 *     payload that fails it becomes the band's `defect` state naming what is missing.
 *     `spec/wire/refusal.md` C-5.
 *   • **`admitted` is not `committed`.** Beat 4 succeeds and is then rolled back with the
 *     rest of the transaction (`gate-run.schema.json`: `persisted` is always `false`). The
 *     band's `committed` state claims the gate opened and the row moved. Mapping beat 4
 *     onto it would be this console's own invention, so this module never emits it — the
 *     admission is the driver panel's to report, and it does.
 *
 * ── WHAT IS CARRIED, AND FROM WHERE ──────────────────────────────────────────────
 *
 * Every field on {@link RunRefusal} is copied out of the beat it came from. Nothing here
 * composes a sentence about a record, chooses a SQLSTATE, or reconstructs a constraint
 * name. {@link refusalLead} is the one place prose is produced, it is the R9 on-ramp, and
 * every clause in it points at the payload member it was read from — which is what
 * {@link RefusalLead.basis} carries onto the screen.
 */

import type { GateRunBeat, GateRunData } from './beats';
import { readRefusal } from './model';
import type { RefusalBarState } from './RefusalBar';
import type { RefusalPayload } from '../../data/types.generated';

// ── One refusing beat, adapted ─────────────────────────────────────────────

/**
 * A single refusal a run produced, in the shape `RefusalBar` and `ReasonSet` consume.
 *
 * `state` is either `refused` (the payload narrowed) or `defect` (it did not). There is
 * deliberately no third possibility: a beat that was not refused never becomes one of
 * these.
 */
export interface RunRefusal {
  /** `beat.ordinal`, verbatim. The reveal order is the payload's, not this module's. */
  readonly ordinal: number;
  /** `beat.name`, verbatim — the vocabulary `gate-run.schema.json` declares. */
  readonly name: string;
  /** `beat.label`, verbatim. The driver's own words for what this beat did. */
  readonly label: string;
  /** What the band should render. `refused` or `defect`; never anything else. */
  readonly state: RefusalBarState;
  /** `beat.elapsed_ms` — the PAYLOAD's number, never a reveal delay (R11). */
  readonly elapsedMs: number;
  /** `beat.statement` — the parameterised SQL, so a reader can run it themselves. */
  readonly statement: string | null;
  /** `beat.matched_expectation`. A beat that surprised the driver says so. */
  readonly matchedExpectation: boolean;
  /** `beat.note`, when the emitter attached one. */
  readonly note: string | null;
}

/**
 * WHICH NOTHING THIS IS.
 *
 * `features/evidence/source.ts` states the console's rule for empty surfaces: *a surface
 * that shows nothing must say which of the several possible nothings it is*. Four of them
 * are reachable here and they are different claims, so they are different values.
 *
 *   `no-run`        nothing has been run in this session. The band keeps its NO ATTEMPT
 *                   state, byte for byte.
 *   `other-subject` a run answered, and it drove a different permit. Nothing about THIS
 *                   permit follows from it.
 *   `undecided`     SQLSTATE 40001 abandoned the run. An undecided transaction is not a
 *                   refusal and has no reason set.
 *   `no-refusal`    the run completed and no beat was refused. That is a fact about the
 *                   run, and it is not the same as not having run.
 */
export type RunAbsence = 'no-run' | 'other-subject' | 'undecided' | 'no-refusal';

/**
 * Everything the screen may say about the last run, and nothing it may not.
 *
 * The identifiers are carried so the screen can tie the band to ONE exchange — a reader
 * who sees `run_id` on the band and `run_id` on the driver panel can check that they are
 * looking at the same transaction rather than being told they are.
 */
export interface RunRefusalModel {
  /**
   * The refusing beats, sorted by the payload's own `ordinal`. Empty exactly when
   * {@link absence} is set. The sort is on `ordinal` rather than on array position because
   * *"the beats came back in order"* is an assumption and `ordinal` is a statement —
   * `beats.ts` `revealPlan` sorts the same way for the same reason.
   */
  readonly refusals: readonly RunRefusal[];
  /** Null exactly when `refusals` is non-empty. */
  readonly absence: RunAbsence | null;
  readonly runId: string | null;
  /** `subject.subject_id` — carried even for `other-subject`, so the screen can say so. */
  readonly subjectId: string | null;
  readonly externalRef: string | null;
  readonly generatedAt: string | null;
  /** `verdict`, verbatim — `PROVEN` or `NOT PROVEN`, never recomputed here. */
  readonly verdict: string | null;
  /** `transaction.disposition === 'rolled_back'`. R11: the band states this. */
  readonly rolledBack: boolean;
  /** `transaction.single_transaction` — a read-only witness, carried not asserted. */
  readonly singleTransaction: boolean | null;
  /** `transaction.retry_sqlstate`. `40001` or null; never a refusal code. */
  readonly retrySqlstate: string | null;
}

const EMPTY: RunRefusalModel = Object.freeze({
  refusals: [],
  absence: 'no-run',
  runId: null,
  subjectId: null,
  externalRef: null,
  generatedAt: null,
  verdict: null,
  rolledBack: false,
  singleTransaction: null,
  retrySqlstate: null,
});

/**
 * The band state for one beat the run reports as refused.
 *
 * A `refusal` of `null` on a refused beat is not survivable by guessing: there is no
 * constraint name, no SQLSTATE and no reason set to render, and inventing the shape would
 * be exactly the artefact `spec/wire/refusal.md` C-5 forbids. So it becomes the band's
 * `defect` state, which names the absence in the emitter's terms and renders no refusal.
 */
function stateForBeat(beat: GateRunBeat): RefusalBarState {
  const carried = beat.refusal ?? null;
  if (carried === null) {
    return {
      kind: 'defect',
      reason:
        `beat ${beat.ordinal} (${beat.name}) reports outcome "refused" and carries ` +
        '`refusal: null`. gate-run.schema.json makes the spec/wire refusal payload the ' +
        'exhibit for a refused beat, so there is no constraint name, no SQLSTATE and no ' +
        'reason set here — and this console will not compose one.',
    };
  }
  const read = readRefusal(carried);
  return read.ok
    ? { kind: 'refused', refusal: read.refusal }
    : { kind: 'defect', reason: read.reason };
}

/** The payload's word for a beat the database refused. Compared to `outcome`, never to a code. */
const REFUSED = 'refused';

/**
 * The refusals a completed run produced against THIS permit.
 *
 * @param run       the last completed gate-run payload, or `null` before any press.
 * @param permitId  the permit this screen is addressed to. A run against any other
 *                  subject contributes nothing to this screen.
 */
export function refusalsFromRun(run: GateRunData | null, permitId: string): RunRefusalModel {
  if (run === null) return EMPTY;

  const common = {
    runId: run.run_id,
    subjectId: run.subject.subject_id,
    externalRef: run.subject.external_ref,
    generatedAt: run.generated_at,
    verdict: run.verdict,
    rolledBack: run.transaction.disposition === 'rolled_back',
    singleTransaction: run.transaction.single_transaction,
    retrySqlstate: run.transaction.retry_sqlstate,
  } as const;

  if (run.subject.subject_id !== permitId) {
    return { ...common, refusals: [], absence: 'other-subject' };
  }

  const refusals: RunRefusal[] = run.beats
    // `filter` already returns a fresh array, so the sort below cannot reorder the
    // caller's — the payload published on Contract B is never mutated here.
    .filter((beat) => beat.outcome === REFUSED)
    .sort((left, right) => left.ordinal - right.ordinal)
    .map((beat) => ({
      ordinal: beat.ordinal,
      name: beat.name,
      label: beat.label,
      state: stateForBeat(beat),
      elapsedMs: beat.elapsed_ms,
      statement: beat.statement,
      matchedExpectation: beat.matched_expectation,
      note: beat.note,
    }));

  if (refusals.length > 0) return { ...common, refusals, absence: null };

  const undecided = run.outcome === 'retry' || run.transaction.retry_sqlstate !== null;
  return { ...common, refusals: [], absence: undecided ? 'undecided' : 'no-refusal' };
}

// ── Choosing what the one band shows ───────────────────────────────────────

/** Where the state on the primary band came from. The screen says which on the page. */
export type PrimarySource = 'attempt' | 'run' | 'none';

export interface BandSelection {
  /** What the primary `RefusalBar` renders. */
  readonly primary: RefusalBarState;
  readonly primarySource: PrimarySource;
  /** The run beat behind {@link primary}, when it came from a run. */
  readonly primaryBeat: RunRefusal | null;
  /** The run's remaining refusals, in ordinal order, each with its own band below. */
  readonly further: readonly RunRefusal[];
}

/**
 * THE PRECEDENCE RULE, IN ONE PLACE.
 *
 * A reader who pressed the control ON THIS SCREEN gets that answer on the headline band:
 * it is their own act against this subject, it is the exchange the button named, and
 * nothing may displace it. Only when this screen's own attempt is in the `none` state —
 * nothing pressed here — does the run's first refusal take the band, and the screen says
 * so beneath it.
 *
 * Either way the run's other refusals are not dropped. Beat 3 is the product's second
 * argument (the counter was forged and the gate refused ANYWAY) and a screen that showed
 * only the first refusal would be telling half of it.
 */
export function selectBand(
  attempt: RefusalBarState,
  model: RunRefusalModel,
): BandSelection {
  const [first, ...rest] = model.refusals;

  if (attempt.kind !== 'none') {
    return {
      primary: attempt,
      primarySource: 'attempt',
      primaryBeat: null,
      further: model.refusals,
    };
  }

  if (first === undefined) {
    return { primary: attempt, primarySource: 'none', primaryBeat: null, further: [] };
  }

  return { primary: first.state, primarySource: 'run', primaryBeat: first, further: rest };
}

// ── The R9 on-ramp ─────────────────────────────────────────────────────────

/**
 * The plain-language lead that goes ABOVE the band — never instead of it.
 *
 * R9: *the on-ramp is ADDITIVE; nothing precise is deleted or softened*. So this produces
 * two or three short sentences a reader who knows nothing can follow, every clause of
 * which points at a payload member named in {@link RefusalLead.basis}. The constraint
 * name, the SQLSTATE, the predicate, the provenance chips, the RFC citations and the
 * reason set are all still below it, unmoved and unreworded.
 *
 * It is a function of the payload rather than a constant because a lead that said
 * *"one obligation"* over a two-atom reason set would be this console lying quietly. The
 * count comes off `mus.length` and the alternative comes off `naa.description`, verbatim
 * and in quotation marks, because it is the database's sentence and not ours.
 */
export interface RefusalLead {
  readonly kicker: string;
  readonly sentences: readonly string[];
  /** The payload members the sentences were built from, in order. */
  readonly basis: readonly string[];
}

/** Plural agreement, so the lead can count without needing a sentence per case. */
function atoms(count: number): string {
  return count === 1 ? 'one thing' : `${count} things`;
}

export function refusalLead(refusal: RefusalPayload): RefusalLead {
  const sentences: string[] = [];
  const basis: string[] = [];

  sentences.push(
    'The database refused this transition, and it named the rule it refused under rather ' +
      `than describing it: ${refusal.constraint}.`,
  );
  basis.push('refusal.constraint');

  if (refusal.mus.length === 0) {
    sentences.push(
      'It carries no reason set, which the specification does not permit for this outcome — ' +
        'so read the panel below as a defect in the emitter, not as a refusal without a cause.',
    );
  } else {
    const one = refusal.mus.length === 1;
    sentences.push(
      `Below is the whole of what caused it: ${atoms(refusal.mus.length)} the database is ` +
        `still waiting on. Answer ${one ? 'it' : 'all of them'} and this same transition would ` +
        `have been allowed; leave ${one ? 'it' : 'any one of them'} and it would not.`,
    );
  }
  basis.push('refusal.mus');

  if (refusal.naa === null) {
    sentences.push(
      refusal.naa_reason === undefined || refusal.naa_reason === null
        ? 'The payload states no smallest way to make it allowed, and states no reason for ' +
          'that either — which is a defect in the emitter and is shown below as one.'
        : 'The payload states no smallest way to make it allowed, and says why in one word: ' +
          `${refusal.naa_reason}. The panel below quotes what the specification means by it.`,
    );
    basis.push('refusal.naa_reason');
  } else {
    sentences.push(
      `It also says what would make it allowed, in its own words: “${refusal.naa.description}”.`,
    );
    basis.push('refusal.naa.description');
  }

  return { kicker: 'what the database said, in plain language', sentences, basis };
}

/**
 * The one sentence that says where a band's refusal came from, when it came from a run.
 *
 * R11: the four beats arrive together in ONE already-rolled-back SERIALIZABLE
 * transaction. A reader who sees a refusal on this screen must not conclude that the
 * button on this screen produced it, and must not conclude that anything persisted.
 * Both facts are read off the payload — `transaction.disposition` and `run_id` — rather
 * than asserted here.
 */
export function runAttribution(model: RunRefusalModel, beat: RunRefusal): string {
  const rolled = model.rolledBack
    ? 'that transaction was rolled back in full, so nothing on this screen was changed by it'
    : 'the payload does not report that transaction as rolled back';
  return (
    `Read from beat ${beat.ordinal} of the demonstration run ${model.runId ?? 'with no id'} — ` +
    `the run's own words for it are “${beat.label}” — not from the control on this screen. ` +
    `The run's four beats share one SERIALIZABLE transaction and ${rolled}.`
  );
}

/**
 * The sentence for a run that produced no refusal for this screen.
 *
 * Each branch is a different claim and none of them is *nothing happened*. `no-run` is
 * the only one the screen renders as silence, because it is the only one where the
 * console has seen nothing at all.
 */
export const RUN_ABSENCE_SENTENCE: Readonly<Record<RunAbsence, string>> = Object.freeze({
  'no-run':
    'No demonstration run has answered in this session, so this band has nothing of its own ' +
    'to add and shows only what the control on this screen produced.',
  'other-subject':
    'The demonstration run that answered drove a different permit from the one this screen is ' +
    'addressed to. Nothing about this permit follows from it, so nothing from it is shown here.',
  undecided:
    'The demonstration run was abandoned as UNDECIDED by SQLSTATE 40001. An undecided ' +
    'transaction is not a refusal: it names no constraint and has no reason set, and this ' +
    'console does not re-send on a reader’s behalf.',
  'no-refusal':
    'The demonstration run completed and no beat was refused. That is a fact about the run, ' +
    'and it is not the same statement as never having run one.',
});
