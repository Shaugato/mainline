// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The silence ledger's model — the arithmetic behind everything the system declined to say.
 *
 * This surface answers the plaintiff's actual question — *"your system knew about event X
 * and did not show it"* — with arithmetic instead of an adverse inference. Its dark side,
 * named in ARCHITECTURE.md §5.7, is that it is a complete list of every warning we chose
 * not to give. The console renders it in full rather than as a count, and the functions
 * here are what make "in full" mean something specific.
 *
 * Three rules are implemented as REFUSALS rather than as formatting, because a rule that
 * degrades to a nicer rendering is a rule that stops being one:
 *
 *   1. **A score is not displayable without its threshold and its policy version.** A
 *      number like `0.31` with nothing beside it is an invitation to read it as a
 *      probability of something. `0.31 against a threshold of 0.45 under policy
 *      BLK-07/recall@2026-07-18` is a fact. `scoreDisplay` returns `withheld` — naming
 *      exactly which companion is missing — rather than rendering the bare number.
 *
 *   2. **A raw similarity is not displayable without a calibrated `p_relevant` beside
 *      it.** `recall_candidate.p_relevant` is a CALIBRATED value and the DDL comment is
 *      blunt: *raw cosine never reaches a human*. A cosine of 0.58 looks like 58% of
 *      something to every reader who has not spent a week with the calibration curve.
 *      `arithmeticView` marks the raw leaves inadmissible when no calibrated value is
 *      present, and the renderer withholds their values.
 *
 *   3. **PER is bounded, and the bound travels with it.** `PER_LIMIT_SENTENCE` is
 *      reproduced on every rendering of a receipt, in addition to the receipt's own
 *      `bound.statement`, which is rendered verbatim from the payload.
 *
 * Nothing here reads a clock. Nothing here decides a gate. The one derivation performed —
 * adding four columns and comparing the sum to a fifth — is the derivation the reader is
 * being invited to check, and it is chipped `recomputed` where it appears.
 */

import type {
  JsonObject,
  JsonValue,
  RecallRun,
  SilenceEntry,
  SilenceReceipt,
  SubjectKind,
  Uuid,
} from '../../data/types.generated';

// ── The honest limit ─────────────────────────────────────────────────────────────

/**
 * THE SENTENCE. Rendered on every PER commitment, verbatim, and grep-able in CI.
 *
 * Proof of Exhausted Recall establishes that nothing scoring at or above theta was
 * withheld FROM THE SET THAT WAS RETURNED. Approximate nearest-neighbour search is
 * approximate: an item the index never surfaced was never in the candidate multiset, so no
 * Merkle argument over that multiset can speak about it. Stating anything stronger would
 * be the single most dangerous sentence this product could put on a screen, because it is
 * the sentence a plaintiff would enjoy reading back to a court.
 *
 * It is a constant rather than prose inside a component so that a CI grep has one target
 * and a rewording is a deliberate edit to a named export rather than a copy edit.
 */
export const PER_LIMIT_SENTENCE =
  'PER proves exhaustion of the retrieval that ran, not of the corpus.';

/**
 * THE GLOSS. It sits BESIDE the sentence above, never in place of it (R8).
 *
 * The bounding sentence is exact and it is also, for a first-time reader, eleven words of
 * vocabulary they have not been given: *exhaustion*, *retrieval*, *corpus*. A reader who
 * cannot decode it will read past it, and reading past it is precisely how the stronger
 * claim — "nothing was withheld" — gets made on our behalf by somebody else.
 *
 * So the sentence is rendered verbatim, in the mono face, in its own verbatim well, and
 * this restates the same boundary in the reader's words next to it. It does not widen the
 * claim by a millimetre: "did not hold back what it found" and "looked everywhere" are two
 * different promises, and this gloss names both in order to say which one is being made.
 *
 * It is a constant beside `PER_LIMIT_SENTENCE`, and for the same reason: a rewording is a
 * deliberate edit to a named export rather than a copy edit inside a component, and a CI
 * grep has one target. `PerPanel` and the use-case walkthrough render this same string, so
 * the two cannot drift.
 */
export const PER_BOUND_GLOSS =
  'In plain words: this proves the search that ran did not hold back anything it found at or ' +
  'above the threshold. It does not prove the search looked everywhere. Those are two ' +
  'different promises, and the receipt is deliberately making only the first one.';

// ── Conservation: the identity the reader can add up ─────────────────────────────

export interface ConservationTerm {
  /** The column name, spelled as `mainline_meas.recall_run` spells it. */
  readonly column: string;
  readonly value: number;
}

export interface ConservationIdentity {
  readonly constraint: 'candidates_conserved';
  readonly total: ConservationTerm;
  readonly terms: readonly ConservationTerm[];
  /** The sum this browser computed from the four terms. */
  readonly sum: number;
  /** `n_candidates − sum`. Zero when the identity holds. */
  readonly residual: number;
  readonly balances: boolean;
}

/**
 * `CHECK (n_candidates = n_blocking + n_advisory + n_silenced + n_deduped)` — MI17.
 *
 * The console adds the four terms and shows the addition. That is not the console
 * computing a gate value (D5): the constraint is the database's, the columns are the
 * database's, and the arithmetic is offered so a reader can check it rather than believe
 * it. If the sum ever disagreed the screen says so loudly — a payload that violates a
 * CHECK the database enforces means the payload did not come from that database, which is
 * a far more interesting finding than a rounding error.
 */
export function conservationOf(run: RecallRun): ConservationIdentity {
  const counts = run.counts;
  const terms: readonly ConservationTerm[] = [
    { column: 'n_blocking', value: counts.n_blocking },
    { column: 'n_advisory', value: counts.n_advisory },
    { column: 'n_silenced', value: counts.n_silenced },
    { column: 'n_deduped', value: counts.n_deduped },
  ];
  const sum = terms.reduce((total, term) => total + term.value, 0);
  return {
    constraint: 'candidates_conserved',
    total: { column: 'n_candidates', value: counts.n_candidates },
    terms,
    sum,
    residual: counts.n_candidates - sum,
    balances: counts.n_candidates === sum,
  };
}

export interface BondedIdentity {
  readonly constraint: 'bonded_fatalities_all_blocking';
  readonly bonded: ConservationTerm;
  readonly blocking: ConservationTerm;
  readonly holds: boolean;
}

/**
 * `CHECK (n_bonded_sev5_blocking = n_bonded_sev5)` — MI16.
 *
 * *"A fatality in your fonds is always recalled"*, as a POSITIVE INVARIANT enforced by a
 * constraint rather than as a score hack. It is rendered as an equality with the
 * constraint's own name beside it, because the claim's whole strength is that it is not a
 * threshold anybody can tune.
 */
export function bondedOf(run: RecallRun): BondedIdentity {
  const counts = run.counts;
  return {
    constraint: 'bonded_fatalities_all_blocking',
    bonded: { column: 'n_bonded_sev5', value: counts.n_bonded_sev5 },
    blocking: { column: 'n_bonded_sev5_blocking', value: counts.n_bonded_sev5_blocking },
    holds: counts.n_bonded_sev5 === counts.n_bonded_sev5_blocking,
  };
}

// ── Score display: never a bare number ───────────────────────────────────────────

export type ScoreDisplay =
  /** The row carries no score. Nothing to show and nothing withheld. */
  | { readonly kind: 'absent' }
  /**
   * A score is present but a companion is not. The number is WITHHELD and the missing
   * companions are named, because a bare score is the most misreadable object on this
   * screen.
   */
  | { readonly kind: 'withheld'; readonly missing: readonly string[] }
  | {
      readonly kind: 'shown';
      readonly score: number;
      readonly threshold: number;
      readonly policyVersion: string;
      /** True when the score cleared the threshold — displayed, never used as a gate. */
      readonly atOrAboveThreshold: boolean;
    };

export function scoreDisplay(entry: SilenceEntry): ScoreDisplay {
  const score = entry.score ?? null;
  if (score === null) return { kind: 'absent' };

  const threshold = entry.threshold ?? null;
  const policyVersion = entry.policy_version ?? null;

  const missing: string[] = [];
  if (threshold === null) missing.push('threshold');
  if (policyVersion === null || policyVersion === '') missing.push('policy_version');
  if (missing.length > 0) return { kind: 'withheld', missing };

  // Narrowed by the two checks above; restated for the type system rather than asserted.
  if (threshold === null || policyVersion === null) return { kind: 'withheld', missing: ['unknown'] };

  return {
    kind: 'shown',
    score,
    threshold,
    policyVersion,
    atOrAboveThreshold: score >= threshold,
  };
}

// ── The arithmetic blob, expanded readably ───────────────────────────────────────

export type ArithmeticKind =
  | 'raw_similarity'
  | 'calibrated'
  | 'threshold'
  | 'weight'
  | 'contribution'
  | 'model'
  | 'plain';

export interface ArithmeticLeaf {
  /** Path segments from the root of `arithmetic`. */
  readonly path: readonly string[];
  /** RFC 6901 pointer, relative to the `arithmetic` object. */
  readonly pointer: string;
  readonly value: JsonValue;
  readonly kind: ArithmeticKind;
}

const RAW_EXACT = new Set([
  'cosine',
  'similarity',
  'inner_product',
  'dot',
  'dot_product',
  'logit',
  'raw',
  'raw_score',
  'fused_raw',
  'distance',
]);

const RAW_SUFFIX = ['_cosine', '_similarity', '_logit', '_raw', '_distance'];

const CALIBRATED_EXACT = new Set(['p_relevant', 'p_rel', 'calibrated', 'calibrated_score']);

const THRESHOLD_EXACT = new Set(['tau', 'theta', 'threshold', 'tau_applied']);

const MODEL_EXACT = new Set([
  'calibrator',
  'calibration_commit',
  'model',
  'model_version',
  'embed_model',
  'gen_model',
  'index_generation',
  'prompt_version',
]);

export function classifyKey(key: string): ArithmeticKind {
  const lower = key.toLowerCase();
  if (CALIBRATED_EXACT.has(lower)) return 'calibrated';
  if (RAW_EXACT.has(lower) || RAW_SUFFIX.some((suffix) => lower.endsWith(suffix))) {
    return 'raw_similarity';
  }
  if (THRESHOLD_EXACT.has(lower)) return 'threshold';
  if (lower === 'weight') return 'weight';
  if (lower === 'contribution') return 'contribution';
  if (MODEL_EXACT.has(lower)) return 'model';
  return 'plain';
}

function escapeSegment(segment: string): string {
  return segment.replaceAll('~', '~0').replaceAll('/', '~1');
}

/**
 * Depth-first flatten. Arrays index numerically, objects by key, and an empty container is
 * itself a leaf — an empty `channels: {}` is a fact worth seeing rather than a row to drop.
 *
 * A `tau` object is flattened like anything else, so `tau/severity_5: 0` appears as its own
 * row. That matters: a severity-5 threshold of zero is the numeric form of *a fatality is
 * always recalled*, and burying it inside a collapsed blob would hide the most important
 * number in the ledger.
 */
export function flattenArithmetic(value: JsonValue, path: readonly string[] = []): ArithmeticLeaf[] {
  const pointer = path.map((segment) => `/${escapeSegment(segment)}`).join('');
  const key = path.length === 0 ? '' : (path[path.length - 1] ?? '');

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return [{ path, pointer, value, kind: classifyKey(key) }];
    }
    return value.flatMap((item, index) => flattenArithmetic(item, [...path, String(index)]));
  }

  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return [{ path, pointer, value, kind: classifyKey(key) }];
    }
    return entries.flatMap(([childKey, childValue]) =>
      flattenArithmetic(childValue, [...path, childKey]),
    );
  }

  return [{ path, pointer, value, kind: classifyKey(key) }];
}

export interface ArithmeticView {
  readonly leaves: readonly ArithmeticLeaf[];
  readonly rawSimilarities: readonly ArithmeticLeaf[];
  /** The calibrated probability, from the blob or from the row's own `score` column. */
  readonly calibrated: { readonly source: 'arithmetic' | 'column'; readonly value: number } | null;
  /** The calibration artefact's identifier — the "calibration commit". */
  readonly calibrator: string | null;
  readonly policyVersion: string | null;
  /**
   * THE RULE. False when the blob contains a raw similarity and no calibrated value
   * accompanies it; the renderer then withholds every raw value and says why.
   */
  readonly rawAdmissible: boolean;
}

function findLeaf(
  leaves: readonly ArithmeticLeaf[],
  predicate: (leaf: ArithmeticLeaf) => boolean,
): ArithmeticLeaf | null {
  return leaves.find(predicate) ?? null;
}

export function arithmeticView(
  arithmetic: JsonObject,
  entry: Pick<SilenceEntry, 'score' | 'policy_version'>,
): ArithmeticView {
  const leaves = flattenArithmetic(arithmetic);

  const rawSimilarities = leaves.filter((leaf) => leaf.kind === 'raw_similarity');

  const calibratedLeaf = findLeaf(
    leaves,
    (leaf) => leaf.kind === 'calibrated' && typeof leaf.value === 'number',
  );
  const columnScore = entry.score ?? null;

  const calibrated =
    calibratedLeaf !== null && typeof calibratedLeaf.value === 'number'
      ? ({ source: 'arithmetic', value: calibratedLeaf.value } as const)
      : columnScore !== null
        ? ({ source: 'column', value: columnScore } as const)
        : null;

  const calibratorLeaf = findLeaf(
    leaves,
    (leaf) =>
      typeof leaf.value === 'string' &&
      (leaf.path[leaf.path.length - 1] === 'calibrator' ||
        leaf.path[leaf.path.length - 1] === 'calibration_commit'),
  );

  return {
    leaves,
    rawSimilarities,
    calibrated,
    calibrator: typeof calibratorLeaf?.value === 'string' ? calibratorLeaf.value : null,
    policyVersion: entry.policy_version ?? null,
    rawAdmissible: rawSimilarities.length === 0 || calibrated !== null,
  };
}

// ── The PER commitment ───────────────────────────────────────────────────────────

export interface BoundaryPair {
  readonly theta: number;
  /** Position s: the last leaf at or above theta. */
  readonly atS: { readonly index: number; readonly score: number; readonly leafHash: string };
  /** Position s+1: the first leaf below it. `null` when s = n and there is no next leaf. */
  readonly atSPlusOne: {
    readonly index: number;
    readonly score: number;
    readonly leafHash: string;
  } | null;
  /**
   * True when `score(s) >= theta > score(s+1)` — the bracket the commitment claims.
   *
   * This is a comparison of two numbers printed on the screen against a third, and it is
   * chipped `recomputed`. It is NOT the inclusion-proof recomputation: verifying the two
   * Merkle paths against `candidate_root` belongs to the in-browser verifier (`src/verify`,
   * ui W8) and has not run here. The screen says so where the seal would otherwise go.
   */
  readonly bracketsTheta: boolean;
  /** True when there is no `s+1` because the boundary sits at the end of the multiset. */
  readonly boundaryAtEnd: boolean;
}

export function boundaryPairOf(receipt: SilenceReceipt): BoundaryPair {
  const leafS = receipt.boundary_proof.leaf_s;
  const next = receipt.boundary_proof.leaf_s_plus_1;

  return {
    theta: receipt.theta,
    atS: { index: leafS.index, score: leafS.score, leafHash: leafS.leaf_hash_hex },
    atSPlusOne:
      next === null
        ? null
        : { index: next.index, score: next.score, leafHash: next.leaf_hash_hex },
    bracketsTheta:
      leafS.score >= receipt.theta && (next === null || next.score < receipt.theta),
    boundaryAtEnd: next === null,
  };
}

/** `s <= n` is `CHECK boundary_sane` on `mainline_meas.silence_receipt`. */
export function boundarySane(receipt: SilenceReceipt): boolean {
  return receipt.s >= 0 && receipt.s <= receipt.n;
}

// ── Ordering ─────────────────────────────────────────────────────────────────────

/**
 * Severity first, then the nearest miss.
 *
 * Within a severity band the entry that came CLOSEST to being surfaced is the one a reader
 * needs first: it is the row where the threshold did the most work, and therefore the row
 * where a calibration argument would land hardest. Rows with no score sort last within
 * their band, ordered by their own id so the list is deterministic — cinema mode requires
 * a stable order, and so does a screenshot in an exhibit bundle.
 *
 * Nothing in this comparator reads a person-shaped field; the silence ledger carries none,
 * and `tests/unit/silence/model.test.ts` asserts the ordering is a pure function of
 * severity, score and id.
 */
export function compareSilenceEntries(a: SilenceEntry, b: SilenceEntry): number {
  if (a.severity !== b.severity) return b.severity - a.severity;

  const scoreA = a.score ?? null;
  const scoreB = b.score ?? null;
  if (scoreA !== null && scoreB !== null && scoreA !== scoreB) return scoreB - scoreA;
  if (scoreA !== null && scoreB === null) return -1;
  if (scoreA === null && scoreB !== null) return 1;

  return a.silence_id.localeCompare(b.silence_id);
}

/** Source and reason tallies, for the census above the ledger. Deterministic order. */
export function tally(
  entries: readonly SilenceEntry[],
  field: 'source' | 'reason',
): readonly (readonly [string, number])[] {
  const counts = new Map<string, number>();
  for (const entry of entries) {
    const key = entry[field];
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

// ── The whole view ───────────────────────────────────────────────────────────────

export interface SilenceData {
  readonly subject_kind: SubjectKind;
  readonly subject_id: Uuid;
  readonly entries: readonly SilenceEntry[];
  readonly receipt: SilenceReceipt | null;
}
