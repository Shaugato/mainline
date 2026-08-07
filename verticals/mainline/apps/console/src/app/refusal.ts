// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * A structural predicate over the refusal wire payload — NOT a re-declaration of it.
 *
 * The normative type lives in `spec/wire/refusal.schema.json` and reaches the console
 * as `src/data/types.generated.ts` (owned by the data-contracts-replay worker) with a
 * CI diff against `spec/`. This module deliberately declares only the four fields the
 * SHELL needs in order to render a refusal correctly when one escapes as an exception:
 * the exhibit name, the SQLSTATE, the database's verbatim message, and whether the
 * constraint name was reported or merely parsed.
 *
 * Keeping it structural means the shell cannot drift out of sync with the wire schema,
 * because it never claims to know the whole of it.
 *
 * D18: refusals are rendered from the payload only — constraint, SQLSTATE, minimal
 * unsatisfiable subset, nearest admissible alternative — never from a message the
 * console composes. A prettified refusal is a different refusal.
 */

/** `spec/errors.md` §1: the closed REFUSE-class set. Anything else is a defect. */
export const REFUSAL_SQLSTATES = ['23514', '23503', '23505', 'P0001'] as const;
export type RefusalSqlstate = (typeof REFUSAL_SQLSTATES)[number];

/** The subset of the wire payload the application shell reads. */
export interface RefusalLike {
  readonly sqlstate: string;
  readonly constraint: string;
  readonly message: string;
  readonly constraint_source?: 'reported' | 'parsed';
  readonly subject_kind?: string;
  readonly subject_id?: string;
  readonly gate_epoch?: number;
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

export function isRefusalLike(value: unknown): value is RefusalLike {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    isNonEmptyString(v.sqlstate) &&
    isNonEmptyString(v.constraint) &&
    isNonEmptyString(v.message)
  );
}

/**
 * An `Error` carrying a refusal payload. Thrown by the transport when the kernel
 * refuses; caught by the shell's error boundary, which renders the payload rather than
 * the exception.
 */
export class RefusalError extends Error {
  readonly refusal: RefusalLike;

  constructor(refusal: RefusalLike) {
    // The Error message IS the database's message. Not a summary of it.
    super(refusal.message);
    this.name = 'RefusalError';
    this.refusal = refusal;
  }
}

/** Finds a refusal on a caught value, whether it was thrown as one or attached to one. */
export function refusalFrom(error: unknown): RefusalLike | null {
  if (error instanceof RefusalError) return error.refusal;
  if (typeof error !== 'object' || error === null) return null;
  const candidate = (error as { refusal?: unknown }).refusal;
  if (isRefusalLike(candidate)) return candidate;
  return isRefusalLike(error) ? error : null;
}

/**
 * True when the SQLSTATE is one the specification models. A code outside the set is
 * not an edge case — `spec/errors.md` §1.1 calls it a defect, because it means the
 * database refused for a reason nobody modelled. The shell says so rather than
 * rendering it as an ordinary refusal.
 */
export function isModelledSqlstate(sqlstate: string): sqlstate is RefusalSqlstate {
  return (REFUSAL_SQLSTATES as readonly string[]).includes(sqlstate);
}
