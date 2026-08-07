// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The provenance vocabulary — CLOSED, and closed is the point.
 *
 * `docs/leads/ui.md` D5: the console never computes a gate condition and never writes an
 * evidentiary row. It reads, it POSTs to the kernel's procedures, and every gate-relevant
 * number is rendered verbatim beside a chip saying how the console came to believe it.
 *
 *   `db:column`      a column value, read and rendered unchanged
 *   `db:constraint`  the name of a constraint the database reported
 *   `recomputed`     this browser re-derived it from signed bytes (D6)
 *   `staged`         it exists only in this browser — nothing written, nothing refused,
 *                    nobody has signed anything
 *
 * There is no `computed`, no `derived` and no `estimated`. A number that is none of the
 * four above has no business on an evidentiary surface, and the absence of a chip for it
 * is how that gets noticed rather than absorbed.
 *
 * Split from `ProvenanceChip.tsx` because a module that exports both a component and a
 * constant defeats React Fast Refresh, and the console's ESLint config warns on it under
 * `--max-warnings 0`.
 */

export const PROVENANCE_KINDS = ['db:column', 'db:constraint', 'recomputed', 'staged'] as const;

export type ProvenanceKind = (typeof PROVENANCE_KINDS)[number];

/** How each kind is spoken to assistive technology. */
export const PROVENANCE_SPOKEN: Readonly<Record<ProvenanceKind, string>> = Object.freeze({
  'db:column': 'read from a database column',
  'db:constraint': 'reported by a database constraint',
  recomputed: 'recomputed in this browser from signed bytes',
  staged: 'staged in this browser only — not written, not refused, not signed',
});

export function isProvenanceKind(value: unknown): value is ProvenanceKind {
  return (PROVENANCE_KINDS as readonly unknown[]).includes(value);
}
