// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE GATE RUN — one request, four beats, and no number this client composed.
 *
 * **R4, in the source file as the plan requires it to be: the ISSUE button calls
 * `POST /v1/demo/gate-run`. It never calls `POST /v1/permits/{id}/merge`.**
 *
 * That is not a style preference. `POST /v1/permits/{permit_id}/merge` against the seeded
 * subject answers **423 Locked** with `use_instead: POST /v1/demo/gate-run`
 * (`docs/deploy/gate-run-contract.md` §7) — the demo protecting itself, which is a
 * completely different sentence from "the gate refused this permit". Rendering that 423 as
 * a refusal would put a fabricated refusal on screen while every byte of it was real, which
 * is the most deniable kind of lie available here. There is no merge path in this module.
 *
 * WHAT ONE PRESS RETURNS (`contracts/gate-run.schema.json`): `run_id`, `generated_at`,
 * `outcome`, `verdict`, `failures`, `persisted`, `elapsed_ms`, `transaction`, `subject`,
 * four `beats`, `persistence_check`. Every per-beat duration a screen renders is that
 * beat's own `elapsed_ms`; every SQLSTATE is that beat's own `sqlstate`; the constraint
 * name and how it was obtained are `constraint` and `constraint_source`. This client
 * composes none of them (M11).
 *
 * `40001` IS AN UNDECIDED TRANSACTION AND MUST NEVER RENDER AS A REFUSAL.
 * `docs/deploy/gate-run-contract.md` §2: *"an undecided transaction has no reason set.
 * `outcome: "retry"` therefore carries no `refusal` payload, and the HTTP status is `503`,
 * never `409`."* So the 503 here is **not** an error path — it carries a full envelope with
 * the beats that did complete, and {@link classify} reports `undecided`. A screen that drew
 * a refusal banner on it would be claiming the gate said no when the database said "ask me
 * again". There is no automatic re-send in this module and there will not be one: a helper
 * that re-sent a merge because a socket closed is a helper that can issue a permit twice.
 * The caller decides whether to press the button again — a human pressing a button again is
 * a decision with an author.
 */

import { post, type Exchange, type RequestOptions } from './client';

import type { Beat, GateRun } from '../../data/types.generated';

/** The route. One press, one POST, one transaction, four beats, rolled back. */
const GATE_RUN_PATH = '/v1/demo/gate-run';

/** The envelope `resource` key this route answers with (`app.py` ROUTES, seventeenth). */
const GATE_RUN_RESOURCE = 'demo_gate_run';

/**
 * What this run turned out to be. Four outcomes, and they are four different sentences.
 */
export type RunClassification =
  /** Every beat matched, and the run proved it persisted nothing. */
  | 'proven'
  /** The run completed and something did not hold. `failures` says what, in the kernel's words. */
  | 'not_proven'
  /** `40001`. The transaction was undecided. **Not a refusal.** HTTP 503, envelope intact. */
  | 'undecided'
  /** No run happened: a problem body, a transport failure, or a body with no envelope. */
  | 'unavailable';

/** One press of the ISSUE button, and everything it produced. */
export interface GateRunResult {
  /** The exchange itself — status, headers, verbatim bytes, for the raw drawer (R18). */
  readonly exchange: Exchange<GateRun>;
  /** The payload, or null when `classification` is `unavailable`. */
  readonly run: GateRun | null;
  readonly classification: RunClassification;
  /** True exactly when `classification` is `undecided`. Never render this as a refusal. */
  readonly undecided: boolean;
  /** `transaction.retry_sqlstate` — `40001` or null. Never a refusal code. */
  readonly retrySqlstate: string | null;
  /** The beats, in payload order. Empty when no run happened. */
  readonly beats: readonly Beat[];
  /**
   * This CLIENT's own reading of the payload against the contract — not the kernel's
   * words, and labelled as such wherever it renders. Empty is the normal case. A non-empty
   * entry means the deployment sent something the contract does not allow, which is worth
   * seeing rather than smoothing over.
   */
  readonly anomalies: readonly string[];
}

function isGateRun(value: unknown): value is GateRun {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const row = value as Record<string, unknown>;
  return (
    (row.outcome === 'completed' || row.outcome === 'retry') &&
    Array.isArray(row.beats) &&
    typeof row.run_id === 'string'
  );
}

function classify(run: GateRun | null): RunClassification {
  if (run === null) {
    return 'unavailable';
  }
  if (run.outcome === 'retry') {
    return 'undecided';
  }
  return run.verdict === 'PROVEN' ? 'proven' : 'not_proven';
}

/**
 * Contract checks this client can make on what arrived. Cheap, and each one names a
 * property the demo actually depends on.
 */
function anomaliesOf(run: GateRun | null): readonly string[] {
  if (run === null) {
    return [];
  }
  const found: string[] = [];
  // Read as `unknown` on purpose. The contract types `persisted` as the literal `false`, so
  // the compiler believes the check is pointless — and the check is about what a SERVER
  // sent, which the compiler has no opinion about. A type is not a witness.
  const persisted: unknown = run.persisted;
  if (persisted !== false) {
    found.push(
      `the payload reports persisted=${JSON.stringify(persisted)}; the contract fixes it at false, ` +
        `because the whole transaction is rolled back.`,
    );
  }
  if (run.outcome === 'completed' && run.beats.length !== 4) {
    found.push(
      `a completed run carried ${run.beats.length} beats; the contract fixes it at four, in order.`,
    );
  }
  if (run.outcome === 'retry' && run.transaction.retry_sqlstate !== '40001') {
    found.push(
      `outcome is "retry" and transaction.retry_sqlstate is ` +
        `${JSON.stringify(run.transaction.retry_sqlstate)}; a retry is 40001 or it is not a retry.`,
    );
  }
  if (run.outcome === 'retry') {
    const withRefusal = run.beats.filter((beat) => beat.refusal !== null).length;
    if (withRefusal > 0 && run.beats.every((beat) => beat.outcome !== 'refused')) {
      found.push(
        `an undecided run carried ${withRefusal} refusal payload(s) on beats that were not ` +
          `refused; an undecided transaction has no reason set.`,
      );
    }
  }
  if (run.verdict === 'PROVEN' && run.failures.length > 0) {
    found.push(
      `verdict is PROVEN with ${run.failures.length} failure(s) listed; the contract makes ` +
        `failures empty exactly when the verdict is PROVEN.`,
    );
  }
  return found;
}

/**
 * Press the button. One real POST, one real transaction, four real beats.
 *
 * Never rejects. A 503 carrying an envelope is a run (undecided); a 503 carrying
 * `{"error":{"kind":"dsn_unset", …}}` is not a run and comes back `unavailable` with the
 * kernel's own sentence in `exchange.problem.detail`.
 *
 * `run_id` is deliberately NOT supplied. The route accepts one and generates its own when
 * it is absent; a client-chosen identifier would make two presses look like one run in a
 * capture, and r5-craft §6 has the second press proving the transport is live precisely
 * because `run_id`, `generated_at` and `opened_logical_timestamp` all move.
 */
export async function runGate(options?: RequestOptions): Promise<GateRunResult> {
  const exchange = await post<GateRun>(GATE_RUN_PATH, undefined, {
    ...options,
    expectResource: GATE_RUN_RESOURCE,
  });
  const run = isGateRun(exchange.data) ? exchange.data : null;
  const classification = classify(run);
  return {
    exchange,
    run,
    classification,
    undecided: classification === 'undecided',
    retrySqlstate: run?.transaction.retry_sqlstate ?? null,
    beats: run?.beats ?? [],
    anomalies: anomaliesOf(run),
  };
}

/**
 * True when this beat is a refusal the database issued.
 *
 * `refused` and only `refused`. `retry` is undecided, `skipped` is a precondition the API
 * refused to fabricate, `error` is a SQLSTATE outside the modelled taxonomy reported rather
 * than smoothed over. None of the three is a refusal, and the screens say so differently.
 */
export function isRefusal(beat: Beat): boolean {
  return beat.outcome === 'refused';
}

/** The beats the database refused, in order. */
export function refusedBeats(result: GateRunResult): readonly Beat[] {
  return result.beats.filter(isRefusal);
}

/**
 * R5's mandatory disclosure line, composed from values that are all real.
 *
 * *"one request · four beats · POST /v1/demo/gate-run · run_id <id> · response received
 * <ISO> · <n> bytes"* — with the beat count taken from the payload rather than written as
 * the word "four", because an undecided run carries fewer and a line that said four anyway
 * would be the first fabricated number on the screen. It reads "four beats" in every case
 * where there are four.
 *
 * Without this line the progressive reveal is faked latency (r4). It is not optional, and
 * building it here rather than in a screen is what stops it being composed wrongly in four
 * different places.
 */
export function disclosureLine(result: GateRunResult): string {
  const { exchange, run, beats } = result;
  const runId = run === null ? 'none — no run was returned' : run.run_id;
  return (
    `one request · ${beats.length} beats · POST ${GATE_RUN_PATH} · ` +
    `run_id ${runId} · response received ${exchange.receivedAt} · ${exchange.wireBytes} bytes`
  );
}
