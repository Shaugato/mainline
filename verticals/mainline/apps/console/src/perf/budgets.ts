// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PERFORMANCE BUDGETS — `docs/leads/ui.md` D13, as data.
 *
 * > *"Sub-second on a mine-site laptop" is a number or it is marketing.*
 *
 * Six budgets. Three are byte counts and are enforced after the build by
 * `scripts/check-budgets.ts` over the real Vite manifest; three are durations measured in
 * a running browser. This file is the register of all six, so that the console can state
 * its own performance contract in one place and so that no number appears twice with two
 * values.
 *
 * ── THE THREE BYTE BUDGETS ARE MIRRORED, NOT DUPLICATED ──────────────────────────
 *
 * `budgets.json` is authoritative for them — it is what the build gate reads, and it
 * belongs to the `console-foundation` worker. The entries here carry the same numbers and
 * `tests/unit/perf/budgets.test.ts` asserts the two files agree byte for byte, INCLUDING the
 * set of ids. If they ever disagree, that test fails rather than one of them silently winning;
 * a performance contract with two answers is a performance contract with none. That is why
 * `operator-surface` had to be added here the moment it was added there.
 *
 * ── WHY `status` EXISTS ──────────────────────────────────────────────────────────
 *
 * Three of these budgets need a real browser with CPU throttling, and the harness that
 * provides one (`playwright.config.ts`, `tests/browser/budgets.spec.ts`) belongs to the
 * `cinema-conformance-harness` worker and had not landed when this file was written. A
 * budget in that position is marked `not-yet-measurable`, and `verdict.ts` treats an
 * unmeasured required budget as a FAILURE rather than as a pass.
 *
 * That asymmetry is the whole design. It is the same rule the gate screen applies to
 * `unmodelled_asset_count`: an unknown is not a zero, and a gate that could not measure
 * has not passed — it has not run.
 */

/** What kind of quantity a budget bounds. */
export const BUDGET_KINDS = ['transfer-bytes', 'duration-ms', 'percentile-ms'] as const;

export type BudgetKind = (typeof BUDGET_KINDS)[number];

/** Whether anything in this repository can produce a number for this budget today. */
export const BUDGET_STATUSES = ['measurable', 'not-yet-measurable'] as const;

export type BudgetStatus = (typeof BUDGET_STATUSES)[number];

export interface Budget {
  readonly id: string;
  readonly title: string;
  /** Why the number is this number, in the operator's terms. Never "for performance". */
  readonly why: string;
  readonly kind: BudgetKind;
  /** The ceiling. Exceeding it is a failure; equalling it is a pass. */
  readonly limit: number;
  readonly unit: 'bytes (gzip)' | 'ms';
  /**
   * The conditions the number is only meaningful under. A latency budget without its
   * throttle factor is a number somebody will quote from a workstation.
   */
  readonly conditions: string;
  /** A budget that is not required may be absent (the 3D chunk after a scope cut). */
  readonly required: boolean;
  /** The file that produces the measurement. Named so an absence is attributable. */
  readonly measuredBy: string;
  readonly status: BudgetStatus;
  /** For percentile budgets: which percentile, as a fraction. */
  readonly percentile?: number;
  /** The fewest samples a percentile is honest at. Below it, the result is not measured. */
  readonly minimumSamples?: number;
}

export const BUDGETS: readonly Budget[] = [
  {
    id: 'evidentiary-shell',
    title: 'Evidentiary shell — entry chunk plus its static import closure and CSS',
    why:
      'The refusal must paint before a supervisor decides the screen is broken. This is the only ' +
      'weight on the critical path; every feature surface is a lazy chunk.',
    kind: 'transfer-bytes',
    limit: 225280,
    unit: 'bytes (gzip)',
    conditions: 'gzip of the transferred JavaScript and CSS closure, not raw bytes',
    required: true,
    measuredBy: 'scripts/check-budgets.ts',
    status: 'measurable',
  },
  {
    id: 'operator-surface',
    title: 'Operator surface — operator.html’s entry chunk plus its static closure and CSS',
    why:
      'CONTROL OF WORK is a separate wire object served by the same static handler under the same ' +
      'response ceiling: a body over DEFAULT_MAX_RESPONSE_BYTES comes back as a 413, and a 413 on ' +
      'an entry chunk is a screen that never boots in front of a supervisor.',
    kind: 'transfer-bytes',
    limit: 139264,
    unit: 'bytes (gzip)',
    conditions: 'gzip of the operator entry’s static closure; the ceiling itself is per-object',
    required: true,
    measuredBy: 'scripts/check-budgets.ts',
    status: 'measurable',
  },
  {
    id: 'memory-register-walk',
    title: 'Lazy 3D chunk — the MEMORY-register ancestry walk',
    why:
      'Loaded only after a refusal has been shown, only on a machine that passed the capability ' +
      'probe, and it is cut-ladder item 1 — so its ABSENCE is legal and is not a budget failure.',
    kind: 'transfer-bytes',
    limit: 614400,
    unit: 'bytes (gzip)',
    conditions: 'gzip of the lazy chunk closure, minus anything already in the entry',
    required: false,
    measuredBy: 'scripts/check-budgets.ts',
    status: 'measurable',
  },
  {
    id: 'gate-interactive',
    title: 'Gate surface interactive',
    why:
      'A supervisor at a gate is standing up, holding a radio, and has one hand. A screen that is ' +
      'not operable within a second is a screen they will walk away from with the permit unresolved.',
    kind: 'duration-ms',
    limit: 1000,
    unit: 'ms',
    conditions: '4× CPU throttle, cold cache, replay transport, 1920×1080',
    required: true,
    measuredBy: 'tests/browser/budgets.spec.ts',
    status: 'not-yet-measurable',
  },
  {
    id: 'first-refusal-paint',
    title: 'First refusal paint, from a verified bundle',
    why:
      'The refusal is the product. Everything else on the screen may stream in; the constraint ' +
      'name and the SQLSTATE may not.',
    kind: 'duration-ms',
    limit: 400,
    unit: 'ms',
    conditions: 'from bundle verification resolving to the refusal bar being in the DOM',
    required: true,
    measuredBy: 'tests/browser/budgets.spec.ts',
    status: 'not-yet-measurable',
  },
  {
    id: 'interaction-p95',
    title: 'Interaction latency, 95th percentile',
    why:
      'Above 100 ms an interaction stops feeling like a response and starts feeling like a ' +
      'question about whether the click registered — which, on a screen where the next click is a ' +
      'signature, is the wrong question to provoke.',
    kind: 'percentile-ms',
    limit: 100,
    unit: 'ms',
    conditions: '4× CPU throttle; event-timing durations over a session of at least 20 interactions',
    required: true,
    measuredBy: 'tests/browser/budgets.spec.ts (samples from src/perf/interaction.ts)',
    status: 'not-yet-measurable',
    percentile: 0.95,
    minimumSamples: 20,
  },
];

export function budgetById(id: string): Budget | null {
  return BUDGETS.find((budget) => budget.id === id) ?? null;
}

/** The byte budgets, which `budgets.json` is authoritative for. */
export const BYTE_BUDGET_IDS: readonly string[] = BUDGETS.filter(
  (budget) => budget.kind === 'transfer-bytes',
).map((budget) => budget.id);

/** The runtime budgets this package measures. */
export const RUNTIME_BUDGET_IDS: readonly string[] = BUDGETS.filter(
  (budget) => budget.kind !== 'transfer-bytes',
).map((budget) => budget.id);

/** Human form, e.g. `220 KB` or `1000 ms`. Used in reports and in the generated doc. */
export function formatLimit(budget: Budget): string {
  if (budget.unit === 'ms') return `${budget.limit} ms`;
  const kb = budget.limit / 1024;
  return Number.isInteger(kb) ? `${kb} KB` : `${kb.toFixed(1)} KB`;
}
