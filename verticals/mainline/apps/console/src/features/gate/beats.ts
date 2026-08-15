// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * THE BEAT MODEL — what `POST /v1/demo/gate-run` answers, and the order it is read in.
 *
 * Pure. No React, no DOM, no styles, no transport. Everything here is a total function
 * of a payload, which is why `tests/unit/gate/beats.test.ts` can exercise the whole
 * reveal without rendering anything, and why `last-run.ts` can publish the payload to a
 * subscriber in another subtree without dragging a component module along with it.
 *
 * ── WHY THE TYPES MOVED HERE ─────────────────────────────────────────────────────
 *
 * They used to live in `src/features/gate/DemoDriver.tsx`, beside the component that
 * rendered them. `docs/leads/demo-story-plan.md` §7.1 Contract B makes the payload a
 * value this worker PUBLISHES and another worker CONSUMES, and a consumer that had to
 * import the driver in order to name its type would pull a lazily-loaded component chunk
 * into whatever imported it. A type in a leaf module costs nothing at runtime.
 * `DemoDriver.tsx` re-exports every name below, so nothing that already imported them
 * from there had to move.
 *
 * ── R11, WHICH IS WHY `revealPlan` EXISTS AT ALL ─────────────────────────────────
 *
 * `docs/leads/demo-story-plan.md` R11: the four beats arrive TOGETHER, in one
 * already-rolled-back `SERIALIZABLE` transaction. Revealing them one after another is a
 * READING AID over a completed exchange, and the panel says so in words next to the
 * paragraph that states the transaction discipline.
 *
 * That ruling has one mechanical consequence and this module is built around it:
 *
 *   **A REVEAL DELAY IS NOT A MEASUREMENT, AND MUST NEVER BE RENDERED AS ONE.**
 *
 * So {@link BeatCue} keeps the two numbers apart by name and by type. `delayMs` is a
 * presentation offset this console chose; it is handed to CSS as a step INDEX and never
 * to a text node. `elapsedText` reads `beat.elapsed_ms` — the payload's own measurement —
 * and is the only function here that produces something a reader sees as a duration.
 * `tests/unit/gate/beats.test.ts` asserts that a plan whose delays and elapsed values
 * disagree renders the payload's, which is the only way round that check is worth
 * writing.
 *
 * ── D18, ENFORCED BY WHAT THIS MODULE DOES NOT CONTAIN ───────────────────────────
 *
 * Nothing below compares a SQLSTATE or a constraint name against a literal, and nothing
 * below composes a sentence about what the database said. {@link revealPlan} reads
 * `ordinal` and `outcome` — the payload's own ordering and its own enumerated result —
 * and produces indices. An index is a position, not a diagnosis.
 */

import type { MusAtom, RefusalPayload } from '../../data/types.generated';

// ── The payload ────────────────────────────────────────────────────────────

/**
 * A STRUCTURAL reading of `gate-run.schema.json`, not a re-declaration of it.
 *
 * The normative contract is `verticals/mainline/apps/demo-api/contracts/gate-run.schema.json`
 * (`$id` `…/contracts/1.0/gate-run.schema.json`) and it is enforced by the transport, in
 * `finishExchange`, before any of this is read. What is declared here is only the subset
 * this feature reads — the same discipline `src/app/refusal.ts` applies to the refusal
 * wire payload, and for the same reason: a module that re-declares a whole contract is a
 * second copy of it that can drift.
 */
export interface GateRunBeat {
  readonly ordinal: number;
  readonly name: string;
  readonly label: string;
  readonly expected: {
    readonly outcome: string;
    readonly sqlstate?: string;
    readonly constraint?: string;
  };
  readonly outcome: string;
  readonly sqlstate: string | null;
  readonly constraint: string | null;
  readonly constraint_source: 'reported' | 'parsed' | 'absent' | null;
  readonly message: string | null;
  readonly matched_expectation: boolean;
  /**
   * THE BEAT'S OWN MEASUREMENT, in milliseconds, as the driver recorded it. It is the
   * only duration this feature is allowed to print beside a beat. Measured on the live
   * URL 2026-08-15: `0.011`, `527.051`, `472.401`, `392.347` — four different numbers,
   * which is precisely why substituting a uniform reveal delay for them would be a lie a
   * reader could not detect.
   */
  readonly elapsed_ms: number;
  readonly statement: string | null;
  readonly observed: Readonly<Record<string, unknown>>;
  readonly note: string | null;
  /**
   * The `spec/wire/refusal.md` payload a refusing beat carried, UNCHANGED — the schema
   * `$ref`s the normative refusal schema, so the generated `RefusalPayload` is the right
   * type and not a second opinion about it. Measured 2026-08-15: beats 2 AND 3 both carry
   * one, each with its own `mus` and `naa`.
   *
   * Optional rather than required, although the contract requires it, because fixtures
   * written before this member existed are other workers' files and a type is not the
   * place to break them. A beat that did not refuse carries `null`.
   */
  readonly refusal?: RefusalPayload | null;
}

export interface GateRunTransaction {
  readonly isolation: string;
  readonly disposition: string;
  readonly opened_logical_timestamp: string;
  readonly closed_logical_timestamp: string | null;
  readonly single_transaction: boolean;
  readonly savepoints: readonly string[];
  readonly retry_sqlstate: string | null;
  readonly canonicalisation: string;
}

export interface GateRunSubject {
  readonly subject_kind: string;
  readonly subject_id: string;
  readonly external_ref: string;
  readonly state: string;
  readonly head_seq: number;
  readonly gate_epoch: number;
  readonly open_blocking: number;
  readonly open_blocking_derived: number;
  readonly blocking_check_id: string | null;
  readonly exposure_receipt_id: string | null;
  readonly site_code: string;
}

/**
 * The permit row's own columns, as a fingerprint reads them. `null` when the subject was
 * absent at that end of the run.
 *
 * These columns are here rather than a count because BEAT 3 IS A COLUMN EDIT: it forces
 * `open_blocking` to zero out of band, which moves nothing a `count(*)` can see. A
 * persistence check made only of counts would report `identical: true` over the one write
 * this demo exists to talk about.
 */
export interface GateRunPermitRow {
  readonly state: string;
  readonly head_seq: number;
  readonly gate_epoch: number;
  readonly open_blocking: number;
  readonly unmet_floor_count: number;
  readonly countersigned_count: number;
  readonly merged_commit: string | null;
}

export interface GateRunFingerprint {
  /** Every table the four beats can write, counted WHOLE — unscoped, deliberately. */
  readonly row_counts: Readonly<Record<string, number>>;
  /** The same question asked of THIS permit only. */
  readonly subject_row_counts: Readonly<Record<string, number>>;
  readonly permit_row: GateRunPermitRow | null;
}

/**
 * The run-scoped readings `self_persisted` is computed from — carried in the payload, the
 * contract says, "so that a reader can recompute the verdict rather than take it".
 * Rendering them is what makes that sentence true of the screen as well.
 */
export interface GateRunSelfEvidence {
  readonly minted_disposition_id: string | null;
  readonly minted_disposition_rows_after_rollback: number;
  readonly subject_row_counts_before: Readonly<Record<string, number>>;
  readonly subject_row_counts_after: Readonly<Record<string, number>>;
  readonly permit_row_identical: boolean;
}

/**
 * `identical` is a statement about THE DATABASE — every one of those tables, counted
 * whole. `self_persisted` is the statement about THIS RUN, and it is what the verdict
 * keys on, because a whole-table count cannot distinguish "I persisted something" from
 * "somebody else did". Both are carried, and the screen shows both.
 */
export interface GateRunPersistence {
  readonly before: GateRunFingerprint;
  readonly after: GateRunFingerprint;
  readonly identical: boolean;
  readonly self_persisted: boolean;
  readonly self_evidence: GateRunSelfEvidence;
  /**
   * `null` when `identical` is true. Otherwise the tables whose unscoped count moved
   * while this run was open, each as `[before, after]` — ANOTHER caller's rows, reported
   * rather than blamed on the run.
   */
  readonly concurrent_writes: Readonly<Record<string, readonly [number, number]>> | null;
  readonly tables: readonly string[];
  readonly note: string;
}

export interface GateRunData {
  readonly schema_id: string;
  readonly run_id: string;
  readonly generated_at: string;
  readonly outcome: string;
  readonly verdict: string;
  readonly failures: readonly string[];
  readonly persisted: boolean;
  readonly elapsed_ms: number;
  readonly transaction: GateRunTransaction;
  readonly subject: GateRunSubject;
  readonly beats: readonly GateRunBeat[];
  readonly persistence_check: GateRunPersistence;
}

// ── What a control reveals ─────────────────────────────────────────────────

/** Which beats a control reveals. `all` is every beat plus the run's own witnesses. */
export type Reveal = 2 | 3 | 4 | 'all';

// ── The reveal, which is presentation and is labelled as such ──────────────

/**
 * The pause between one beat appearing and the next, in milliseconds.
 *
 * **It MUST equal `--tp-duration-evidence` in `src/design/tokens.css`, and a test says so
 * rather than an import.** `tests/unit/gate/beats.test.ts` asserts
 * `REVEAL_STEP_MS === DURATION_MS.evidence`, and `tests/unit/design/motion.test.ts`
 * already asserts that `DURATION_MS.evidence` equals the token the stylesheet declares.
 * The two assertions chain: the step a reader waits, the step `demo-driver.module.css`
 * expresses as `var(--tp-duration-evidence)`, and the number reported here cannot drift
 * apart without one of them going red.
 *
 * ── WHY IT IS NOT IMPORTED FROM THE MOTION POLICY ────────────────────────────────
 *
 * Because the register boundary forbids it, and the boundary is right. `eslint.config.js`
 * denies every EVIDENCE directory — `src/features/gate/**` included — any import whose
 * path ends in a segment named `motion`, so an EVIDENCE feature cannot reach
 * `src/design/motion.ts` at all. That rule exists to stop this directory acquiring an
 * animation dependency by degrees, and routing around it with an `eslint-disable` to save
 * one number would be worse than declaring the number and checking it.
 *
 * So this is the repository's usual shape for that situation: the CONSTANT is checked
 * against the SOURCE, in a test, in that direction and never the reverse.
 *
 * **This number never reaches a text node.** See the module header.
 */
export const REVEAL_STEP_MS = 120;

/**
 * One beat, plus where it sits in the reading order. Every member is derived from the
 * payload except `stepIndex` and `delayMs`, which are presentation and are named so.
 */
export interface BeatCue {
  readonly beat: GateRunBeat;
  /** 0-based position in the revealed sequence. The payload's `ordinal` is not renumbered. */
  readonly stepIndex: number;
  /**
   * `stepIndex * REVEAL_STEP_MS`. A PRESENTATION offset, handed to CSS as a step index
   * and never rendered as text. It is not this beat's duration and is not related to it.
   */
  readonly delayMs: number;
  /**
   * 0-based position of this beat among the REFUSING beats of the revealed sequence, or
   * `null` when this beat did not refuse.
   *
   * It exists because the second refusal is the rarer claim, and the demonstration's
   * whole argument turns on it: the first refusal is a CHECK constraint doing its job;
   * the second happened after the counter that CHECK reads had been forced to zero. That
   * distinction is a fact about ORDER and OUTCOME — both the payload's own — so the
   * screen can give it its own weight without any branch reading a SQLSTATE or composing
   * a sentence (D18).
   */
  readonly refusalIndex: number | null;
}

/** The payload's word for a beat the database refused. Compared to `outcome`, never to a code. */
const REFUSED = 'refused';

/**
 * The beats a control reveals, in ORDINAL ORDER, each with its step in the reading.
 *
 * The sort is on the payload's own `ordinal`; the emitter's array order is not trusted to
 * carry it, because "the beats came back in order" is an assumption and `ordinal` is a
 * statement. A `reveal` naming one beat produces a one-element plan whose single step is
 * zero — a control that shows one beat has nothing to stagger.
 */
export function revealPlan(
  beats: readonly GateRunBeat[],
  reveal: Reveal,
): readonly BeatCue[] {
  const selected = (reveal === 'all' ? [...beats] : beats.filter((beat) => beat.ordinal === reveal))
    .slice()
    .sort((left, right) => left.ordinal - right.ordinal);

  let refusals = 0;
  return selected.map((beat, stepIndex) => ({
    beat,
    stepIndex,
    delayMs: stepIndex * REVEAL_STEP_MS,
    refusalIndex: beat.outcome === REFUSED ? refusals++ : null,
  }));
}

/**
 * THE BEAT'S OWN DURATION, as text.
 *
 * `beat.elapsed_ms` verbatim, with the unit the contract names it in. No rounding, no
 * humanising, no thresholding — `0.011` stays `0.011`, because a beat that took eleven
 * microseconds and a beat that took half a second are the difference between a read and
 * a round trip through a gate function, and rounding both to "0 ms" and "1 s" would erase
 * the one comparison this row is for.
 *
 * It takes the beat rather than a number so that no call site can hand it a delay.
 */
export function elapsedText(beat: GateRunBeat): string {
  return `${beat.elapsed_ms} ms`;
}

/**
 * The first clause identifier any refusing beat's reason set names, or `null`.
 *
 * `MusAtom` is a discriminated union and only two of its five kinds carry a clause, so
 * the member is reached by presence rather than by cast: an atom that has no clause is
 * not a defect, it is an `authority_gap` or a `capability_gap`, and asking it for one
 * would be this module inventing a field the emitter did not send.
 */
export function clauseIdFromRun(beats: readonly GateRunBeat[]): string | null {
  for (const beat of beats) {
    for (const atom of beat.refusal?.mus ?? []) {
      const clauseId = clauseIdOf(atom);
      if (clauseId !== null) return clauseId;
    }
  }
  return null;
}

function clauseIdOf(atom: MusAtom): string | null {
  return 'clause_id' in atom ? (atom.clause_id ?? null) : null;
}
