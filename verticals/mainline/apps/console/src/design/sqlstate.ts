// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The SQLSTATE taxonomy, from `spec/errors.md` §1.
 *
 * The code set a conformant implementation may produce on the gate path is **closed**:
 *
 *     {40001, 23514, 23503, 23505, P0001}
 *
 * Anything else is a defect, not an edge case — it means the database refused for a
 * reason nobody modelled. `42501` sits outside the taxonomy BY DEFINITION rather than by
 * exception: the writer was refused by the grant graph or by a row-level-security policy
 * *before* any gate condition was evaluated, so it is an authorisation error and must
 * never be surfaced as a gate refusal.
 *
 * `00000` is not an error. It appears here because the conformance manifest gives every
 * case a uniform expectation, including the cases whose whole point is that a correct
 * history is *not* refused.
 *
 * This module classifies. It deliberately does NOT translate a code into prose: the
 * expectation class is a fact about the code, the human meaning is a fact about the
 * refusal payload, and `docs/leads/ui.md` D18 says the payload carries its own words.
 *
 * Split from `Sqlstate.tsx` so that module exports only a component (React Fast Refresh).
 */

/** `spec/errors.md` §1 — the four expectation classes, plus everything outside them. */
export type SqlstateClass = 'retry' | 'refuse' | 'deny' | 'admit' | 'unmodelled';

const CLASS_OF: Readonly<Record<string, SqlstateClass>> = Object.freeze({
  '40001': 'retry',
  '23514': 'refuse',
  '23503': 'refuse',
  '23505': 'refuse',
  P0001: 'refuse',
  '42501': 'deny',
  '00000': 'admit',
});

/** The codes the gate path is closed over. */
export const GATE_PATH_CODES: readonly string[] = ['40001', '23514', '23503', '23505', 'P0001'];

export const CLASS_LABEL: Readonly<Record<SqlstateClass, string>> = Object.freeze({
  retry: 'RETRY — undecided',
  refuse: 'REFUSE — the gate decided no',
  deny: 'DENY — refused before the gate',
  admit: 'ADMIT — not an error',
  unmodelled: 'OUTSIDE THE TAXONOMY',
});

/** The expectation class of a code, or `unmodelled` for anything `spec/errors.md` closes out. */
export function sqlstateClass(code: string): SqlstateClass {
  return CLASS_OF[code] ?? 'unmodelled';
}
