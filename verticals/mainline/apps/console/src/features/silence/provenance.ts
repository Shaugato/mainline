// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * What the emitter claimed about one JSON pointer — and nothing more.
 *
 * `contracts/common.schema.json` is explicit and the sentence is the design:
 *
 *   > A pointer absent from this list has NO chip and is rendered without one — an
 *   > unclaimed provenance is better than a comfortable default.
 *
 * So this module never invents a chip. It answers one question with one of three answers:
 * the emitter declared this exact pointer, the emitter declared an ancestor of it (weaker,
 * and shown as weaker with the ancestor named), or the emitter declared nothing.
 *
 * Duplicated rather than shared with `src/features/propagation/provenance.ts` and
 * `src/features/gate/provenance.ts` for one reason: a feature directory must stay
 * `rm -r`-able (BUILD_PLAN §10.2), and a cross-feature import would make deleting one
 * surface break another. The right long-term home is the register-neutral `src/design/`
 * package, which belongs to another worker; recorded as a cross-domain note.
 */

import type { ProvenanceChip as PayloadChipKind } from '../../data/types.generated';
import { isProvenanceKind, type ProvenanceKind } from '../../design/provenance';

export type { PayloadChipKind };

export interface ProvenanceEntry {
  readonly pointer: string;
  readonly chip: PayloadChipKind;
}

export type ProvenanceLookup =
  | { readonly kind: 'exact'; readonly chip: PayloadChipKind; readonly pointer: string }
  | { readonly kind: 'inherited'; readonly chip: PayloadChipKind; readonly pointer: string }
  | { readonly kind: 'undeclared'; readonly pointer: string };

/**
 * RFC 6901 containment: `/entries` contains `/entries/0/score`, and `/entry` does NOT
 * contain `/entries/0`. The trailing separator makes the second case false, and it is the
 * case a naive `startsWith` gets wrong.
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
    if (entry.pointer === pointer) return { kind: 'exact', chip: entry.chip, pointer };
  }

  let best: ProvenanceEntry | null = null;
  for (const entry of provenance) {
    if (!contains(entry.pointer, pointer)) continue;
    if (best === null || entry.pointer.length > best.pointer.length) best = entry;
  }
  return best === null
    ? { kind: 'undeclared', pointer }
    : { kind: 'inherited', chip: best.chip, pointer: best.pointer };
}

/**
 * `derived` is in the wire contract and NOT in the design package's closed vocabulary.
 * Dropping the fifth kind would hide a claim the emitter made, so the surface renders it
 * with its own chip and this predicate is how the two renderings split the work.
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
