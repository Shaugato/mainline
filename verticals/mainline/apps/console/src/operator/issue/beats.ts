// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE FOUR BEATS, READ — never composed.
 *
 * One `POST /v1/demo/gate-run` returns all four beats. This module turns that payload
 * into a render model and does nothing else: every SQLSTATE, constraint name, predicate,
 * message, digest and duration on screen is a value this file COPIED out of the response,
 * and there is not one of them written down here.
 *
 * ┌──────────────────────────────────────────────────────────────────────────────────┐
 * │ R4 — THE SINGLE MOST LIKELY WRONG TURN AVAILABLE TO A BUILDER OF THIS SCREEN.     │
 * │                                                                                   │
 * │ The ISSUE button calls `POST /v1/demo/gate-run`. It must NEVER call               │
 * │ `POST /v1/permits/{id}/merge`, which answers **423 Locked** on the seeded subject  │
 * │ with `use_instead` naming the gate-run route (docs/deploy/gate-run-contract.md §7, │
 * │ operator-systems-plan.md M8/R4, r3-operator §5.5). A 423 is the demo protecting    │
 * │ itself from being bricked by the first judge who presses a button — it is NOT a    │
 * │ gate refusal, its message is about a lock rather than about an obligation, and     │
 * │ rendering one inside a refusal banner would put a FABRICATED EXHIBIT in front of a │
 * │ judge. `GATE_RUN_PATH` below is the only path this screen posts to.                │
 * └──────────────────────────────────────────────────────────────────────────────────┘
 *
 * Two rules this file exists to keep:
 *
 *   1. **Every duration rendered per beat is the payload's own `elapsed_ms`.** Never a
 *      reveal delay, never a client stopwatch. The client's own round-trip clock lives
 *      in `pending.ts` and is labelled there as this browser's reading.
 *   2. **Nothing is inferred that the payload did not carry.** Where the response does
 *      not name a thing — the relation a CHECK was declared on, a nearest admissible
 *      alternative — this module reports the absence and says how it knows, rather than
 *      supplying a plausible value. See `raisedBy()` and `nearestAdmissible()`.
 *
 * Type-only imports from `src/data/types.generated.ts` are permitted by R1: types erase
 * to zero bytes, so the operator entry stays free of the console's runtime closure.
 */

import type {
  Beat,
  GateRun,
  MusAtom,
  Naa,
  Observed,
  RefusalPayload,
} from '../../data/types.generated';

/**
 * The only path the ISSUE button posts to. See the R4 box above.
 *
 * Built with `new URL(path, location.origin)` at the call site (R3): no absolute URL is
 * compiled in, so the screen is always a client of the origin that served it, and the
 * response headers — including `X-Mainline-Emulator` — are readable because there is no
 * cross-origin hop to strip them.
 */
export const GATE_RUN_PATH = '/v1/demo/gate-run';

/** The verb, kept beside the path so the disclosure line cannot disagree with the call. */
export const GATE_RUN_METHOD = 'POST';

// ───────────────────────────────────────────────────────────────────────────────────────
// What a caller hands this module
// ───────────────────────────────────────────────────────────────────────────────────────

/**
 * The facts about one HTTP exchange that the four-beat reading needs.
 *
 * Structurally a subset of the kernel client's `Exchange<GateRun>`, declared here as the
 * minimum so this module can be exercised against a payload without a transport. It is
 * NOT a second transport and it is not a place a payload can be invented: `data` is
 * whatever came back over the wire, `status` is the status the server returned.
 */
export interface GateRunResponseFacts {
  readonly status: number;
  readonly wireBytes: number;
  /** ISO instant from the CLIENT's clock. Rendered as such — it is not a server time. */
  readonly receivedAt: string;
  readonly data: GateRun | null;
}

// ───────────────────────────────────────────────────────────────────────────────────────
// The render model
// ───────────────────────────────────────────────────────────────────────────────────────

export interface BeatView {
  readonly ordinal: number;
  readonly name: Beat['name'];
  /** The driver's own one-line label for this beat. Never rewritten. */
  readonly label: string;
  readonly outcome: Beat['outcome'];
  readonly expectedOutcome: Beat['outcome'];
  readonly matchedExpectation: boolean;
  /** THE PAYLOAD'S OWN `elapsed_ms`. The only duration a beat may render. */
  readonly elapsedMs: number;
  readonly sqlstate: string | null;
  readonly constraint: string | null;
  readonly constraintSource: Beat['constraint_source'];
  readonly message: string | null;
  readonly statement: string | null;
  readonly note: string | null;
  readonly refusal: RefusalPayload | null;
  readonly observed: Observed;
  /** The gate said no and named what said it. */
  readonly isRefusal: boolean;
  /** The transition succeeded (inside the transaction that was then rolled back). */
  readonly isAdmission: boolean;
  /** SQLSTATE 40001. An UNDECIDED transaction — not a refusal, and never rendered as one. */
  readonly isUndecided: boolean;
}

export type RunReading =
  | {
      readonly kind: 'completed';
      readonly run: GateRun;
      readonly beats: readonly BeatView[];
      readonly facts: GateRunResponseFacts;
    }
  | {
      /**
       * `outcome: "retry"` — SQLSTATE 40001 aborted the run and the transaction was
       * rolled back UNDECIDED. It carries no refusal payload, the HTTP status is 503,
       * and there is no retry helper on this path and there will not be one: a helper
       * that re-sent a merge because a socket closed is a helper that can issue a permit
       * twice. Pressing the button again is a decision with an author.
       */
      readonly kind: 'undecided';
      readonly run: GateRun;
      /** From `transaction.retry_sqlstate`. Read, never compared to a constant. */
      readonly retrySqlstate: string | null;
      readonly httpStatus: number;
      readonly facts: GateRunResponseFacts;
    }
  | {
      /** No gate-run payload came back. Whatever happened, it was not a refusal. */
      readonly kind: 'unreadable';
      readonly httpStatus: number;
      readonly facts: GateRunResponseFacts;
    };

/** Turns one real response into the reading the screen renders. Pure. */
export function readRun(facts: GateRunResponseFacts): RunReading {
  const run = facts.data;
  if (run === null) {
    return { kind: 'unreadable', httpStatus: facts.status, facts };
  }
  if (run.outcome === 'retry') {
    return {
      kind: 'undecided',
      run,
      retrySqlstate: run.transaction.retry_sqlstate,
      httpStatus: facts.status,
      facts,
    };
  }
  return { kind: 'completed', run, beats: beatViews(run), facts };
}

/** One view per beat, in the payload's own order. */
export function beatViews(run: GateRun): readonly BeatView[] {
  return run.beats.map(toBeatView);
}

export function toBeatView(beat: Beat): BeatView {
  return {
    ordinal: beat.ordinal,
    name: beat.name,
    label: beat.label,
    outcome: beat.outcome,
    expectedOutcome: beat.expected.outcome,
    matchedExpectation: beat.matched_expectation,
    elapsedMs: beat.elapsed_ms,
    sqlstate: beat.sqlstate,
    constraint: beat.constraint,
    constraintSource: beat.constraint_source,
    message: beat.message,
    statement: beat.statement,
    note: beat.note,
    refusal: beat.refusal,
    observed: beat.observed,
    isRefusal: beat.outcome === 'refused',
    isAdmission: beat.outcome === 'admitted',
    isUndecided: beat.outcome === 'retry',
  };
}

// ───────────────────────────────────────────────────────────────────────────────────────
// Reading the database's own words out of the message
// ───────────────────────────────────────────────────────────────────────────────────────

/**
 * The CHECK expression, lifted out of the driver's message.
 *
 * The predicate is not carried in a field of its own on a beat, so it is recovered from
 * the message the database produced — the same technique, and the same weakening, that
 * `mainline_demo_api.refusal.diagnose` records as `constraint_source: "parsed"`. The
 * screen labels it as read from the message; it never presents it as a field.
 */
const CHECK_PREDICATE = /CHECK constraint\s+(\(.+\))/;

/** The kernel's own `refused by <schema>.<object>` clause (spec/errors.md §2.5). */
const REFUSED_BY = /refused by\s+([A-Za-z_][A-Za-z0-9_.$]*)/;

export interface Parsed {
  readonly text: string;
  /** Always `message`: this value was read out of the database's sentence, not a field. */
  readonly from: 'message';
}

/** The CHECK predicate when the message carries one; null when it does not. */
export function checkPredicate(message: string | null): Parsed | null {
  if (message === null) return null;
  const found = CHECK_PREDICATE.exec(message);
  const text = found?.[1];
  if (text === undefined) return null;
  return { text, from: 'message' };
}

export interface RaisedBy {
  /** The fully-qualified name, verbatim. */
  readonly object: string;
  /** The part before the first dot, when there is one. */
  readonly schema: string | null;
  /**
   * `constraint_field` — the beat's own `constraint` was already schema-qualified, which
   * is what the contract says the exhibit for a raised refusal is.
   * `message_clause` — recovered from the kernel's `refused by …` sentence.
   */
  readonly how: 'constraint_field' | 'message_clause';
}

/**
 * WHICH OBJECT PRODUCED THIS REFUSAL — and the honest answer when the payload does not say.
 *
 * When the kernel RAISES, the exhibit is the fully-qualified name of the raising object,
 * so the beat's own `constraint` answers it. A reported CHECK constraint name is
 * UNQUALIFIED — the driver hands over the constraint's name and not the relation it was
 * declared on, and no other member of the beat carries that relation either. So for a
 * CHECK this returns `null` and the banner renders the absence in words.
 *
 * That absence is deliberate and it is the whole ethic of this screen in one function:
 * the plausible table name is one identifier away and typing it would be indistinguishable
 * from reading it. `statement` — verbatim SQL, also from the payload — is rendered instead,
 * and it names the objects the beat actually addressed.
 */
export function raisedBy(beat: BeatView): RaisedBy | null {
  const named = beat.constraint;
  if (named?.includes('.') === true) {
    const dot = named.indexOf('.');
    return { object: named, schema: named.slice(0, dot), how: 'constraint_field' };
  }
  const found = beat.message === null ? null : REFUSED_BY.exec(beat.message);
  const object = found?.[1];
  if (object === undefined) return null;
  const dot = object.indexOf('.');
  return {
    object,
    schema: dot === -1 ? null : object.slice(0, dot),
    how: 'message_clause',
  };
}

/**
 * True when this exhibit was RECOVERED rather than reported — a weakened diagnosis, and
 * the screen must render it as one so a run whose exhibits were inferred never looks like
 * a run whose exhibits were reported.
 */
export function exhibitIsWeakened(beat: BeatView): boolean {
  return beat.constraintSource === 'parsed';
}

// ───────────────────────────────────────────────────────────────────────────────────────
// The explanation the refusal carries with it
// ───────────────────────────────────────────────────────────────────────────────────────

export type NearestAdmissible =
  | { readonly kind: 'computed'; readonly naa: Naa }
  /**
   * The engine that produced the refusal could not compute a nearest admissible
   * alternative and said so, with its reason, verbatim. A system reporting what it cannot
   * compute — on its best refusal — is the point, not a gap to paper over.
   */
  | { readonly kind: 'not_computed'; readonly reason: string | null };

export function nearestAdmissible(refusal: RefusalPayload | null): NearestAdmissible | null {
  if (refusal === null) return null;
  if (refusal.naa !== null) return { kind: 'computed', naa: refusal.naa };
  return { kind: 'not_computed', reason: refusal.naa_reason ?? null };
}

/** The minimal unsatisfiable subset, or an empty list when there is no refusal. */
export function reasonSet(refusal: RefusalPayload | null): readonly MusAtom[] {
  return refusal?.mus ?? [];
}

/**
 * One line per reason-set atom, built only from the atom's own members.
 *
 * The atoms are a discriminated union in the wire contract; each branch prints the
 * identifiers it actually carries. Nothing is looked up, joined or embellished.
 */
export function reasonAtomLine(atom: MusAtom): string {
  switch (atom.kind) {
    case 'obligation':
      return join([
        `obligation ${atom.obligation_id}`,
        atom.origin === undefined ? null : `origin ${atom.origin}`,
        atom.severity === undefined ? null : `severity ${atom.severity}`,
        atom.virulence === undefined ? null : `virulence ${atom.virulence}`,
        atom.clause_id === undefined ? null : `clause ${atom.clause_id}`,
        atom.event_id === undefined ? null : `precursor event ${atom.event_id}`,
        atom.detail ?? null,
      ]);
    case 'clause':
      return join([
        `clause ${atom.clause_id}`,
        atom.commit_id === undefined ? null : `commit ${atom.commit_id}`,
        atom.relation === undefined ? null : `relation ${atom.relation}`,
        atom.detail ?? null,
      ]);
    case 'event':
      return join([
        `event ${atom.event_id}`,
        atom.severity === undefined ? null : `severity ${atom.severity}`,
        atom.detail ?? null,
      ]);
    case 'authority_gap':
      return join([
        `authority gap on ${atom.relation}`,
        `key ${keyText(atom.key)}`,
        atom.detail ?? null,
      ]);
    case 'capability_gap':
      return join([`capability gap · ${atom.capability}`, atom.detail ?? null]);
  }
}

function keyText(key: Readonly<Record<string, string | number | null>>): string {
  return Object.entries(key)
    .map(([name, value]) => `${name}=${value === null ? 'null' : String(value)}`)
    .join(', ');
}

function join(parts: readonly (string | null)[]): string {
  return parts.filter((part): part is string => part !== null && part.length > 0).join(' · ');
}

/**
 * The precursor events named by this refusal's own reason set, deduplicated, in order.
 *
 * The operator sentence — "the precursor has never been answered for this permit" — names
 * these and nothing else. If the reason set carries no event, the sentence does not claim
 * one exists.
 */
export function precursorEvents(refusal: RefusalPayload | null): readonly string[] {
  const seen: string[] = [];
  for (const atom of reasonSet(refusal)) {
    const id =
      atom.kind === 'event' ? atom.event_id : atom.kind === 'obligation' ? atom.event_id : undefined;
    if (id !== undefined && !seen.includes(id)) seen.push(id);
  }
  return seen;
}

// ───────────────────────────────────────────────────────────────────────────────────────
// The counters, and what beat 3 did to them
// ───────────────────────────────────────────────────────────────────────────────────────

export interface CounterForge {
  /** What the projected counter was forced to, out of band. From `counter_forced_to`. */
  readonly forcedTo: number;
  /** What the gate got when it counted again from the obligations. From the payload. */
  readonly derived: number | null;
  /** The driver's own description of the attack, verbatim. */
  readonly attack: string | null;
}

/**
 * Beat 3, detected by what it OBSERVED rather than by its position in the array.
 *
 * `counter_forced_to` is present exactly on the beat that forced the projected counter out
 * of band. Reading the shape rather than the ordinal means a payload that ever stopped
 * carrying the attack stops rendering it, instead of rendering the sentence anyway.
 */
export function counterForge(beat: BeatView): CounterForge | null {
  const forcedTo = beat.observed.counter_forced_to;
  if (forcedTo === undefined || forcedTo === null) return null;
  return {
    forcedTo,
    derived: beat.observed.open_blocking_derived ?? null,
    attack: beat.observed.attack ?? null,
  };
}

/** The obligation count this beat observed, preferring the re-derived reading. */
export function observedOutstanding(beat: BeatView): number | null {
  return beat.observed.open_blocking_derived ?? beat.observed.open_blocking_projected ?? null;
}

// ───────────────────────────────────────────────────────────────────────────────────────
// Beat 4, and the claim that nothing persisted
// ───────────────────────────────────────────────────────────────────────────────────────

export interface AdmissionReading {
  /** Server-computed SHA-256 over the sorted (check_id, disposition_id) set. */
  readonly clearanceDigest: string | null;
  readonly mergedCommit: string | null;
  readonly mergedAt: string | null;
  readonly dispositionId: string | null;
  readonly dispositionKind: string | null;
  readonly openBlockingAfterSignature: number | null;
  readonly permitState: string | null;
}

export function admissionReading(beat: BeatView): AdmissionReading | null {
  if (!beat.isAdmission) return null;
  const record = beat.observed.merge_record ?? null;
  return {
    clearanceDigest: record?.clearance_digest ?? null,
    mergedCommit: record?.merged_commit ?? null,
    mergedAt: record?.merged_at ?? null,
    dispositionId: beat.observed.disposition_id ?? null,
    dispositionKind: beat.observed.disposition_kind ?? null,
    openBlockingAfterSignature: beat.observed.open_blocking_after_signature ?? null,
    permitState: record?.permit_state ?? null,
  };
}

export interface PersistenceReading {
  /**
   * DID THIS RUN PERSIST ANYTHING. This is the field the screen renders and the field the
   * verdict keys on. `identical` is a statement about the whole shared database and goes
   * false whenever ANY other caller commits a row, which is not this run's doing — it is
   * reported beside, never in place of, this reading.
   */
  readonly selfPersisted: boolean;
  readonly identical: boolean;
  readonly mintedDispositionId: string | null;
  readonly mintedRowsAfterRollback: number;
  readonly permitRowIdentical: boolean;
  /** Another caller's rows, as [before, after]. Empty when `identical` is true. */
  readonly concurrentWrites: readonly { readonly table: string; readonly counts: readonly number[] }[];
  readonly tables: readonly string[];
  readonly note: string;
}

export function persistenceReading(run: GateRun): PersistenceReading {
  const check = run.persistence_check;
  const concurrent = check.concurrent_writes;
  return {
    selfPersisted: check.self_persisted,
    identical: check.identical,
    mintedDispositionId: check.self_evidence.minted_disposition_id,
    mintedRowsAfterRollback: check.self_evidence.minted_disposition_rows_after_rollback,
    permitRowIdentical: check.self_evidence.permit_row_identical,
    concurrentWrites:
      concurrent === null
        ? []
        : Object.entries(concurrent).map(([table, counts]) => ({ table, counts })),
    tables: check.tables,
    note: check.note,
  };
}

// ───────────────────────────────────────────────────────────────────────────────────────
// Small, boring formatters
// ───────────────────────────────────────────────────────────────────────────────────────

/**
 * The standing line above the ISSUE button.
 *
 * The WORD is operator language; the NUMBER is data. When no count has been read, the line
 * says so rather than showing a zero, because a zero here reads as "nothing outstanding"
 * and that is a claim about a permit.
 */
export function outstandingLine(count: number | null): string {
  if (count === null) return 'obligations outstanding · not read';
  return `${count} ${count === 1 ? 'obligation' : 'obligations'} outstanding`;
}

/**
 * Fixed formatting, no locale: an evidentiary number must read the same on every machine.
 *
 * Sub-millisecond readings keep three decimals rather than rounding to `0.0 ms`. The read
 * beat really does take tens of microseconds, and a duration displayed as zero invites the
 * reading that the client rounded a measurement away.
 */
export function formatMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return ms < 1 ? `${ms.toFixed(3)} ms` : `${ms.toFixed(1)} ms`;
}
