// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Provenance lookup — the envelope's own claim about where a value came from.
 *
 * `contracts/common.schema.json` is explicit, and the sentence is the design:
 *
 *   > A pointer absent from this list has NO chip and is rendered without one — an
 *   > unclaimed provenance is better than a comfortable default.
 *
 * So this module never invents a chip. It answers one question — *what did the emitter
 * declare about this JSON pointer?* — with one of three answers: a declared kind, a kind
 * declared on an ancestor pointer (reported as such, with the ancestor named), or
 * nothing.
 *
 * The ancestor rule is not a loophole. `contracts/permit.schema.json`'s fixture declares
 * `db:constraint` on `/constraints` — the whole array — because every constraint name in
 * it came from the catalog. Refusing to honour that would force the emitter to enumerate
 * fourteen pointers, and a contract nobody can satisfy economically is a contract that
 * gets left empty. The UI shows WHICH pointer carried the claim, so an ancestor-derived
 * chip is visibly weaker than an exact one.
 */

import type { ProvenanceChip as PayloadChipKind } from '../../data/types.generated';
import { isProvenanceKind, type ProvenanceKind } from '../../design/provenance';

export type { PayloadChipKind };

export interface ProvenanceEntry {
  readonly pointer: string;
  readonly chip: PayloadChipKind;
}

export type ProvenanceLookup =
  /** The emitter declared this exact pointer. */
  | { readonly kind: 'exact'; readonly chip: PayloadChipKind; readonly pointer: string }
  /** The emitter declared an ancestor of it. Weaker, and displayed as weaker. */
  | { readonly kind: 'inherited'; readonly chip: PayloadChipKind; readonly pointer: string }
  /** The emitter declared nothing. Rendered as an absence, never as a default. */
  | { readonly kind: 'undeclared'; readonly pointer: string };

/**
 * RFC 6901 pointer containment: `/constraints` contains `/constraints/0/constraint`,
 * and `/counter` does NOT contain `/counters/open_blocking`. The trailing separator is
 * what makes the second case false, and it is the case a naive `startsWith` gets wrong.
 */
function contains(ancestor: string, pointer: string): boolean {
  return pointer === ancestor || pointer.startsWith(`${ancestor}/`);
}

export function lookupProvenance(
  provenance: readonly ProvenanceEntry[] | undefined,
  pointer: string,
): ProvenanceLookup {
  if (provenance === undefined) return { kind: 'undeclared', pointer };

  for (const entry of provenance) {
    if (entry.pointer === pointer) {
      return { kind: 'exact', chip: entry.chip, pointer };
    }
  }

  // Longest declared ancestor wins: a claim about `/checks/0` is more specific than one
  // about `/checks`, and the more specific claim is the one the emitter meant.
  let best: ProvenanceEntry | null = null;
  for (const entry of provenance) {
    if (!contains(entry.pointer, pointer)) continue;
    if (best === null || entry.pointer.length > best.pointer.length) best = entry;
  }
  if (best !== null) {
    return { kind: 'inherited', chip: best.chip, pointer: best.pointer };
  }

  return { kind: 'undeclared', pointer };
}

/**
 * `derived` is in the wire contract and NOT in the design package's closed vocabulary
 * (`src/design/provenance.ts` declares four kinds; `contracts/common.schema.json`
 * declares five). Rather than silently dropping the fifth — which would hide a claim the
 * emitter made — the gate surface renders it with its own chip and this predicate is how
 * the two components split the work.
 */
export function isDesignChipKind(chip: PayloadChipKind): chip is ProvenanceKind {
  return isProvenanceKind(chip);
}

/** RFC 6901 escaping, so a pointer built from a key containing `/` or `~` stays valid. */
export function pointer(...segments: readonly (string | number)[]): string {
  return segments
    .map((segment) => `/${String(segment).replaceAll('~', '~0').replaceAll('/', '~1')}`)
    .join('');
}
