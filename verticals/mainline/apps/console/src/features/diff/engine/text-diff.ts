// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The token diff over two `canon_text` values.
 *
 * This is the one computation in the whole console that produces something a reader will
 * treat as a claim about a record, so it is written to one rule above all others:
 *
 *     concat(segments where kind ≠ added)   === the parent's canon_text
 *     concat(segments where kind ≠ removed) === the version's canon_text
 *
 * exactly, for every input, INCLUDING the degraded path. A diff renderer that loses a
 * sentence while showing a confident "2 changes" header is undetectable by eye and would
 * put a procedure on screen that the database does not hold. `engine.test.ts` checks the
 * two equations on every pair in this repository, which is why they are stated here as
 * the contract rather than as a nice property.
 *
 * ── Why longest-common-subsequence and not Myers ─────────────────────────────────
 *
 * Myers is asymptotically better and is what a source-control diff should use. Here the
 * inputs are ONE CLAUSE — `canon_text` is capped at 65 536 characters by the contract and
 * is in practice a paragraph — and the pair is trimmed to its differing middle before any
 * table is allocated. LCS over the trimmed middle is a few thousand cells for a real
 * clause edit, it is trivially deterministic, and its backtrack has no tie-breaking
 * subtleties that could reorder segments between two runs. Determinism is worth more than
 * asymptotics on a surface whose screenshots are a conformance artefact (D12).
 *
 * ── Why there is a budget ────────────────────────────────────────────────────────
 *
 * Two 65 536-character texts with nothing in common would demand a table with more cells
 * than a browser tab should allocate. Rather than freeze the screen or silently sample,
 * the engine REFUSES to compute a token-level diff, emits the two texts as one removed
 * block and one added block, and records `degraded` with the budget and the demand. The
 * reader is told the granularity they are looking at. Both equations still hold.
 */

import type { DiffDegradation, TextDiff, TextSegment, Token } from '../model';
import { tokenise } from './tokenise';

/**
 * The default table budget, in cells.
 *
 * 4 000 000 cells is a 16 MB `Uint32Array` — a few hundred milliseconds of work in the
 * worst case and comfortably inside D13's interaction budget for the far commoner case
 * of a trimmed middle in the low thousands. It is exported so a test can assert the
 * default is large enough to leave a real clause edit exact.
 */
export const MAX_DIFF_CELLS = 4_000_000;

export interface DiffOptions {
  /** Overrides `MAX_DIFF_CELLS`. Present so the degraded path is testable. */
  readonly maxCells?: number;
}

type OpKind = 'equal' | 'removed' | 'added';

interface Op {
  readonly kind: OpKind;
  /** Index into the parent token array, or `null` for an addition. */
  readonly from: number | null;
  /** Index into the version token array, or `null` for a removal. */
  readonly to: number | null;
}

/** How many leading tokens are textually identical. */
function commonPrefix(a: readonly Token[], b: readonly Token[]): number {
  const limit = Math.min(a.length, b.length);
  let index = 0;
  while (index < limit && a[index]?.text === b[index]?.text) index += 1;
  return index;
}

/** How many trailing tokens are textually identical, not overlapping the prefix. */
function commonSuffix(a: readonly Token[], b: readonly Token[], prefix: number): number {
  const limit = Math.min(a.length, b.length) - prefix;
  let index = 0;
  while (index < limit && a[a.length - 1 - index]?.text === b[b.length - 1 - index]?.text) {
    index += 1;
  }
  return index;
}

/**
 * Longest common subsequence over the trimmed middle, as an operation list.
 *
 * `table[i * (m + 1) + j]` is the LCS length of `a[i…]` and `b[j…]`. The forward walk
 * that follows breaks every tie the SAME way — a removal is emitted before an addition —
 * so the operation list is a function of the inputs alone.
 */
function lcsOps(
  a: readonly Token[],
  b: readonly Token[],
  aOffset: number,
  bOffset: number,
): readonly Op[] {
  const n = a.length;
  const m = b.length;
  const width = m + 1;
  const table = new Uint32Array((n + 1) * width);

  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      table[i * width + j] =
        a[i]?.text === b[j]?.text
          ? (table[(i + 1) * width + (j + 1)] ?? 0) + 1
          : Math.max(table[(i + 1) * width + j] ?? 0, table[i * width + (j + 1)] ?? 0);
    }
  }

  const ops: Op[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i]?.text === b[j]?.text) {
      ops.push({ kind: 'equal', from: aOffset + i, to: bOffset + j });
      i += 1;
      j += 1;
      continue;
    }
    // The tie-break: when dropping from either side costs the same, drop from the
    // PARENT first. It makes a replacement read as "was X, now Y" in every case.
    if ((table[(i + 1) * width + j] ?? 0) >= (table[i * width + (j + 1)] ?? 0)) {
      ops.push({ kind: 'removed', from: aOffset + i, to: null });
      i += 1;
    } else {
      ops.push({ kind: 'added', from: null, to: bOffset + j });
      j += 1;
    }
  }
  while (i < n) {
    ops.push({ kind: 'removed', from: aOffset + i, to: null });
    i += 1;
  }
  while (j < m) {
    ops.push({ kind: 'added', from: null, to: bOffset + j });
    j += 1;
  }
  return ops;
}

/** Every token from `start` (inclusive) to `end` (exclusive) as one operation each. */
function block(kind: 'removed' | 'added', start: number, end: number): readonly Op[] {
  const ops: Op[] = [];
  for (let index = start; index < end; index += 1) {
    ops.push(
      kind === 'removed' ? { kind, from: index, to: null } : { kind, from: null, to: index },
    );
  }
  return ops;
}

/**
 * Collapses the operation list into segments, merging runs of the same kind.
 *
 * The merge is what makes a segment a HIGHLIGHT rather than a token: five removed tokens
 * in a row are one struck-through phrase on screen and one `<del>` element in the DOM,
 * which is also what a screen reader needs to announce it once instead of five times.
 */
function toSegments(
  ops: readonly Op[],
  fromTokens: readonly Token[],
  toTokens: readonly Token[],
): readonly TextSegment[] {
  const segments: TextSegment[] = [];

  let index = 0;
  while (index < ops.length) {
    const kind = ops[index]?.kind;
    if (kind === undefined) break;

    let end = index;
    while (end < ops.length && ops[end]?.kind === kind) end += 1;

    const run = ops.slice(index, end);
    const fromIndices = run.map((op) => op.from).filter((value): value is number => value !== null);
    const toIndices = run.map((op) => op.to).filter((value): value is number => value !== null);

    const firstFrom = fromIndices[0];
    const lastFrom = fromIndices[fromIndices.length - 1];
    const firstTo = toIndices[0];
    const lastTo = toIndices[toIndices.length - 1];

    const fromStart = firstFrom === undefined ? null : (fromTokens[firstFrom]?.start ?? null);
    const fromEnd = lastFrom === undefined ? null : (fromTokens[lastFrom]?.end ?? null);
    const toStart = firstTo === undefined ? null : (toTokens[firstTo]?.start ?? null);
    const toEnd = lastTo === undefined ? null : (toTokens[lastTo]?.end ?? null);

    // The text is taken from whichever side carries it. For `equal` both sides carry
    // identical text by construction; the parent is used so that a future change to the
    // equality predicate cannot make the two sides disagree without a test noticing.
    const text =
      fromIndices.length > 0
        ? fromIndices.map((tokenIndex) => fromTokens[tokenIndex]?.text ?? '').join('')
        : toIndices.map((tokenIndex) => toTokens[tokenIndex]?.text ?? '').join('');

    if (text !== '') {
      segments.push({ kind, text, fromStart, fromEnd, toStart, toEnd });
    }
    index = end;
  }

  return segments;
}

/**
 * Diffs two `canon_text` values.
 *
 * Pure: no clock, no randomness, no locale. Two calls with the same arguments produce
 * models that serialise byte-identically, which `engine.test.ts` asserts directly.
 */
export function diffCanonText(
  parentText: string,
  versionText: string,
  options: DiffOptions = {},
): TextDiff {
  const maxCells = options.maxCells ?? MAX_DIFF_CELLS;

  const fromTokens = tokenise(parentText);
  const toTokens = tokenise(versionText);

  const prefix = commonPrefix(fromTokens, toTokens);
  const suffix = commonSuffix(fromTokens, toTokens, prefix);

  const fromMiddle = fromTokens.slice(prefix, fromTokens.length - suffix);
  const toMiddle = toTokens.slice(prefix, toTokens.length - suffix);

  const demanded = (fromMiddle.length + 1) * (toMiddle.length + 1);
  const degraded: DiffDegradation | null =
    demanded > maxCells
      ? { reason: 'diff_budget_exhausted', budget: maxCells, demanded }
      : null;

  const ops: Op[] = [];
  for (let index = 0; index < prefix; index += 1) {
    ops.push({ kind: 'equal', from: index, to: index });
  }

  if (degraded === null) {
    ops.push(...lcsOps(fromMiddle, toMiddle, prefix, prefix));
  } else {
    ops.push(...block('removed', prefix, fromTokens.length - suffix));
    ops.push(...block('added', prefix, toTokens.length - suffix));
  }

  for (let index = 0; index < suffix; index += 1) {
    ops.push({
      kind: 'equal',
      from: fromTokens.length - suffix + index,
      to: toTokens.length - suffix + index,
    });
  }

  const segments = toSegments(ops, fromTokens, toTokens);

  let equalChars = 0;
  let removedChars = 0;
  let addedChars = 0;
  for (const segment of segments) {
    if (segment.kind === 'equal') equalChars += segment.text.length;
    else if (segment.kind === 'removed') removedChars += segment.text.length;
    else addedChars += segment.text.length;
  }

  return {
    segments,
    equalChars,
    removedChars,
    addedChars,
    parentLength: parentText.length,
    versionLength: versionText.length,
    // Compared as strings, not as token lists: two texts that tokenise identically but
    // differ in a character the tokeniser groups are NOT identical, and saying they are
    // would be the console overruling the column.
    identical: parentText === versionText,
    degraded,
  };
}
