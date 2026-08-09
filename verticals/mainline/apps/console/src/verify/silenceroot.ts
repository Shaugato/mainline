// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Proof of Exhausted Recall — the boundary check, recomputed in the browser.
 *
 * `mainline_meas.silence_receipt` (ARCHITECTURE.md §5.7) discloses `candidate_root`, θ,
 * *s*, *n* and a boundary pair with inclusion paths. Because the candidate leaves are
 * committed in **score-sorted order**, that disclosure establishes that every leaf beyond
 * position *s* scored below θ — *no item can be hand-excluded without breaking sortedness*
 * — while revealing nothing about the suppressed content itself. It is a cryptographically
 * enforced privilege log: the plaintiff learns the shape of the silence without the system
 * having to publish every warning it chose not to give.
 *
 * ── THE INDEXING, STATED ONCE, NORMATIVELY ────────────────────────────────────────
 *
 * The receipt counts in **1-based positions**: `s` is the number of candidates ADMITTED,
 * and `CHECK (s >= 0 AND s <= n)` means "none admitted" through "all admitted". Merkle
 * leaf indices are **0-based**. Therefore:
 *
 *     leaf_s          is Merkle index s - 1   — the LAST ADMITTED candidate
 *     leaf_s_plus_1   is Merkle index s       — the FIRST EXCLUDED candidate
 *
 * and the two must be adjacent. The check below asserts that relation against the `index`
 * each boundary leaf carries, rather than deriving the indices from `s` and trusting them,
 * so that a receipt whose indices disagree with its own `s` is a finding rather than a
 * silent re-interpretation.
 *
 * ── WHAT THIS PROVES, AND THE SENTENCE THAT MUST TRAVEL WITH IT ───────────────────
 *
 * ANN retrieval is approximate. **PER proves exhaustion of the retrieval that ran, not of
 * the corpus.** That is why `silence_receipt` carries `index_generation` and
 * `index_plan_digest`, why `contracts/silence.schema.json` makes the bounding sentence a
 * REQUIRED member rather than a caption, and why `verifyBoundary` refuses to return a
 * pass without one being present in the caller's payload. A proof that overclaims is
 * worse than none.
 *
 * Scores are compared as DECIMAL STRINGS, never parsed into doubles. A boundary that
 * turned on `0.45 > 0.44999999999999996` would be a boundary decided by IEEE-754, and the
 * arithmetic a court reads has to be the arithmetic that ran.
 */

import { digestFromHex, toHex } from './bytes';
import { verifyInclusion, type ProofOutcome } from './rfc6962';
import type { Sha256Oracle } from './sha256';

export interface BoundaryLeaf {
  readonly index: number;
  readonly leafHashHex: string;
  /** Decimal string. Never a double. */
  readonly score: string;
  readonly pathHex: readonly string[];
}

export interface SilenceBoundaryInput {
  readonly candidateRootHex: string;
  /** Decimal string, as recorded. */
  readonly theta: string;
  readonly s: number;
  readonly n: number;
  readonly leafS: BoundaryLeaf | null;
  readonly leafSPlusOne: BoundaryLeaf | null;
}

export type BoundaryStatus = 'pass' | 'fail';

export interface BoundaryFinding {
  readonly check: string;
  readonly detail: string;
}

export interface BoundaryOutcome {
  readonly status: BoundaryStatus;
  readonly findings: readonly BoundaryFinding[];
  /** The inclusion recomputations, so the surface can SHOW the arithmetic. */
  readonly inclusion: readonly { readonly which: string; readonly outcome: ProofOutcome }[];
  /** Verbatim, one line, for the seal. */
  readonly summary: string;
}

// ── Decimal comparison ─────────────────────────────────────────────────────

const DECIMAL = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;

/**
 * Compare two decimal strings exactly. Returns -1, 0 or 1.
 *
 * Written out rather than delegated to `Number()` because a threshold is the one number
 * on this screen that a court will read aloud. `0.1 + 0.2` is not `0.3` in IEEE-754, and
 * a silence boundary that moved by one representable step because of a parse would be
 * indefensible for a reason nobody in the room could see.
 */
export function compareDecimal(a: string, b: string): number {
  if (!DECIMAL.test(a)) throw new RangeError(`${JSON.stringify(a)} is not a plain decimal`);
  if (!DECIMAL.test(b)) throw new RangeError(`${JSON.stringify(b)} is not a plain decimal`);

  const negativeA = a.startsWith('-');
  const negativeB = b.startsWith('-');
  if (negativeA !== negativeB) return negativeA ? -1 : 1;

  const magnitude = compareMagnitude(negativeA ? a.slice(1) : a, negativeB ? b.slice(1) : b);
  return negativeA ? -magnitude : magnitude;
}

function compareMagnitude(a: string, b: string): number {
  const [aInt = '0', aFrac = ''] = a.split('.');
  const [bInt = '0', bFrac = ''] = b.split('.');

  const intA = aInt.replace(/^0+(?=\d)/, '');
  const intB = bInt.replace(/^0+(?=\d)/, '');
  if (intA.length !== intB.length) return intA.length < intB.length ? -1 : 1;
  if (intA !== intB) return intA < intB ? -1 : 1;

  const width = Math.max(aFrac.length, bFrac.length);
  const fracA = aFrac.padEnd(width, '0');
  const fracB = bFrac.padEnd(width, '0');
  if (fracA === fracB) return 0;
  return fracA < fracB ? -1 : 1;
}

// ── The check ──────────────────────────────────────────────────────────────

/**
 * Verify a PER boundary pair.
 *
 * Six assertions, each of which defeats a specific way of lying about what was not shown:
 *
 *   1. `0 <= s <= n` — the database CHECK is the first line; this is the second, for a
 *      payload that never met it.
 *   2. the pair is ADJACENT — a gap hides whatever sat between them.
 *   3. the carried indices agree with `s` — `leaf_s` is Merkle index `s − 1`.
 *   4. `score(leaf_s) >= theta > score(leaf_s+1)` — the boundary is where it claims.
 *   5. sortedness across the boundary — `score(leaf_s) >= score(leaf_s+1)`.
 *   6. both leaves are in the committed multiset — inclusion against `candidate_root`.
 *
 * (4) is the one that catches a hand-excluded item: drop a candidate scoring above θ and
 * move the boundary up, and the leaf now claimed to be the first excluded still scores
 * above θ.
 */
export async function verifyBoundary(
  oracle: Sha256Oracle,
  input: SilenceBoundaryInput,
): Promise<BoundaryOutcome> {
  const findings: BoundaryFinding[] = [];
  const inclusion: { which: string; outcome: ProofOutcome }[] = [];
  const { s, n, leafS, leafSPlusOne } = input;

  let root: Uint8Array;
  try {
    root = digestFromHex(input.candidateRootHex, 'candidate_root');
  } catch (error) {
    return settle(
      [{ check: 'candidate_root', detail: error instanceof Error ? error.message : String(error) }],
      inclusion,
    );
  }

  if (!Number.isInteger(s) || !Number.isInteger(n) || s < 0 || n < 0 || s > n) {
    findings.push({
      check: 'boundary_sane',
      detail:
        `s = ${s} and n = ${n} do not satisfy 0 <= s <= n. The database CHECK boundary_sane ` +
        'refuses this; a payload that reached a reader without meeting it did not come ' +
        'through that table.',
    });
    return settle(findings, inclusion);
  }

  if (s === 0) {
    if (leafS !== null) {
      findings.push({
        check: 'boundary_shape',
        detail:
          's = 0 means nothing was admitted, so there is no last-admitted leaf; the receipt ' +
          'nevertheless carries one. The two statements cannot both be true.',
      });
    } else {
      findings.push({
        check: 'boundary_shape',
        detail:
          's = 0: nothing was admitted, so there is no boundary pair to check and this ' +
          'receipt establishes nothing about sortedness. Reported rather than passed.',
      });
    }
    return settle(findings, inclusion);
  }

  if (leafS === null) {
    findings.push({
      check: 'boundary_shape',
      detail: `s = ${s} claims ${s} admitted candidate(s), but no leaf_s was supplied to check.`,
    });
    return settle(findings, inclusion);
  }

  if (leafS.index !== s - 1) {
    findings.push({
      check: 'boundary_index',
      detail:
        `leaf_s carries Merkle index ${leafS.index}; s = ${s} requires index ${s - 1} (positions ` +
        'in the receipt are 1-based, Merkle leaf indices are 0-based). An index that disagrees ' +
        'with s is a receipt describing a different boundary than the one it states.',
    });
  }

  if (s === n) {
    if (leafSPlusOne !== null) {
      findings.push({
        check: 'boundary_shape',
        detail:
          `s = n = ${n}: every candidate was surfaced, so there is no first-excluded leaf, but ` +
          'the receipt carries one.',
      });
    }
  } else if (leafSPlusOne === null) {
    findings.push({
      check: 'boundary_shape',
      detail:
        `s = ${s} and n = ${n}, so ${n - s} candidate(s) were silenced and a first-excluded leaf ` +
        'must be disclosed. Without it nothing constrains where the boundary was drawn.',
    });
  } else {
    if (leafSPlusOne.index !== leafS.index + 1) {
      findings.push({
        check: 'boundary_adjacent',
        detail:
          `the boundary pair is not adjacent: leaf_s is index ${leafS.index} and leaf_s_plus_1 is ` +
          `index ${leafSPlusOne.index}. A gap between them hides whatever sat there.`,
      });
    }
  }

  // Every decimal comparison in ONE guarded block, so a malformed score is reported once
  // and named, instead of once per comparison that happened to touch it.
  try {
    if (compareDecimal(leafS.score, input.theta) < 0) {
      findings.push({
        check: 'boundary_theta',
        detail:
          `the last ADMITTED candidate scored ${leafS.score}, which is below theta = ${input.theta}. ` +
          'The admitted set extends past the threshold it claims.',
      });
    }
    if (leafSPlusOne !== null) {
      if (compareDecimal(leafSPlusOne.score, input.theta) >= 0) {
        findings.push({
          check: 'boundary_theta',
          detail:
            `the first EXCLUDED candidate scored ${leafSPlusOne.score}, which is not below theta = ` +
            `${input.theta}. This is what a hand-excluded item looks like: drop a candidate that ` +
            'scored above the threshold, move the boundary up one, and the leaf now claimed to be ' +
            'the first excluded still scores above theta. No item can be hand-excluded without ' +
            'breaking sortedness.',
        });
      }
      if (compareDecimal(leafS.score, leafSPlusOne.score) < 0) {
        findings.push({
          check: 'boundary_sorted',
          detail:
            `sortedness fails across the boundary: leaf_s scored ${leafS.score} and ` +
            `leaf_s_plus_1 scored ${leafSPlusOne.score}. The multiset is committed in ` +
            'score-sorted order, and the whole proof rests on that order holding.',
        });
      }
    }
  } catch (error) {
    findings.push({
      check: 'boundary_score_format',
      detail:
        `a score or theta is not a plain decimal string: ${error instanceof Error ? error.message : String(error)}. ` +
        'Scores are compared exactly, as decimals; a boundary decided by IEEE-754 rounding is ' +
        'not a boundary a court can read.',
    });
  }

  for (const [which, leaf] of [
    ['leaf_s', leafS],
    ['leaf_s_plus_1', leafSPlusOne],
  ] as const) {
    if (leaf === null) continue;
    let leafHashBytes: Uint8Array;
    let path: Uint8Array[];
    try {
      leafHashBytes = digestFromHex(leaf.leafHashHex, `${which}.leaf_hash_hex`);
      path = leaf.pathHex.map((element, index) => digestFromHex(element, `${which}.path_hex[${index}]`));
    } catch (error) {
      findings.push({
        check: 'boundary_inclusion',
        detail: error instanceof Error ? error.message : String(error),
      });
      continue;
    }
    const outcome = await verifyInclusion(oracle, {
      seq: leaf.index,
      treeSize: n,
      leafHash: leafHashBytes,
      path,
      expectedRoot: root,
    });
    inclusion.push({ which, outcome });
    if (!outcome.ok) {
      findings.push({
        check: 'boundary_inclusion',
        detail:
          `${which} (index ${leaf.index}) is not in the multiset committed by candidate_root ` +
          `${toHex(root)}: ${outcome.reason}`,
      });
    }
  }

  return settle(findings, inclusion);
}

function settle(
  findings: readonly BoundaryFinding[],
  inclusion: readonly { readonly which: string; readonly outcome: ProofOutcome }[],
): BoundaryOutcome {
  if (findings.length === 0) {
    return {
      status: 'pass',
      findings,
      inclusion,
      summary:
        'The boundary pair is adjacent, both leaves are in the committed score-sorted multiset, ' +
        'and the threshold falls between them. This proves exhaustion of the RETRIEVAL THAT RAN, ' +
        'not of the corpus.',
    };
  }
  return {
    status: 'fail',
    findings,
    inclusion,
    summary: `${findings.length} boundary finding(s): ${findings.map((f) => f.check).join(', ')}.`,
  };
}
