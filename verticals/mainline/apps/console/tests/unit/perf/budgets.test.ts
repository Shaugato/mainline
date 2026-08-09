// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The budget register, and the one thing it must never do: disagree with `budgets.json`.
 *
 * `budgets.json` is what `scripts/check-budgets.ts` reads after a build, and it belongs
 * to the `console-foundation` worker. `src/perf/budgets.ts` mirrors its two byte budgets
 * so the console can state its whole performance contract in one place. Mirrored numbers
 * drift; that is what mirrored numbers do. So the drift is a test failure rather than one
 * of them silently winning — a performance contract with two answers is a performance
 * contract with none.
 */

import { describe, expect, it } from 'vitest';

import {
  BUDGETS,
  BUDGET_KINDS,
  BUDGET_STATUSES,
  BYTE_BUDGET_IDS,
  RUNTIME_BUDGET_IDS,
  budgetById,
  formatLimit,
} from '../../../src/perf/budgets';

interface BudgetsJsonEntry {
  readonly id: string;
  readonly max_gzip_bytes: number;
  readonly required: boolean;
}

interface BudgetsJson {
  readonly budgets: readonly BudgetsJsonEntry[];
}

const RAW: Record<string, unknown> = import.meta.glob('/budgets.json', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function budgetsJson(): BudgetsJson {
  const text = RAW['/budgets.json'];
  if (typeof text !== 'string') {
    throw new Error(
      'budgets.json did not load as text. Without it this suite would assert agreement with ' +
        'nothing and pass.',
    );
  }
  return JSON.parse(text) as BudgetsJson;
}

describe('the register is well formed', () => {
  it('has unique ids, real reasons, and stated conditions', () => {
    const ids = BUDGETS.map((budget) => budget.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(BUDGETS.length).toBe(5);

    for (const budget of BUDGETS) {
      expect(BUDGET_KINDS).toContain(budget.kind);
      expect(BUDGET_STATUSES).toContain(budget.status);
      expect(budget.limit).toBeGreaterThan(0);
      // "for performance" is not a reason. Every budget says what it costs an operator.
      expect(budget.why.length, `${budget.id} does not say why`).toBeGreaterThan(80);
      // A latency budget without its throttle factor is a number quoted from a workstation.
      expect(budget.conditions.length, `${budget.id} states no conditions`).toBeGreaterThan(20);
    }
  });

  it('separates the byte budgets from the runtime ones, with nothing in both or neither', () => {
    expect([...BYTE_BUDGET_IDS, ...RUNTIME_BUDGET_IDS].sort()).toEqual(
      BUDGETS.map((budget) => budget.id).sort(),
    );
    expect(BYTE_BUDGET_IDS.filter((id) => RUNTIME_BUDGET_IDS.includes(id))).toEqual([]);
  });

  it('resolves by id and refuses one it does not have', () => {
    expect(budgetById('interaction-p95')?.percentile).toBe(0.95);
    expect(budgetById('a-budget-nobody-declared')).toBeNull();
  });

  it('formats a limit in the unit a person would quote', () => {
    const shell = budgetById('evidentiary-shell');
    const interactive = budgetById('gate-interactive');
    expect(shell).not.toBeNull();
    expect(interactive).not.toBeNull();
    if (shell === null || interactive === null) return;
    expect(formatLimit(shell)).toBe('220 KB');
    expect(formatLimit(interactive)).toBe('1000 ms');
    expect(formatLimit({ ...shell, limit: 614400 })).toBe('600 KB');
    expect(formatLimit({ ...shell, limit: 1536 })).toBe('1.5 KB');
  });
});

describe('agreement with budgets.json', () => {
  const json = budgetsJson();

  it('covers every byte budget the build gate enforces', () => {
    expect(json.budgets.length).toBeGreaterThan(0);
    expect(json.budgets.map((entry) => entry.id).sort()).toEqual([...BYTE_BUDGET_IDS].sort());
  });

  it.each(BYTE_BUDGET_IDS.map((id) => id))('`%s` carries the same number in both files', (id) => {
    const mirrored = budgetById(id);
    const authoritative = json.budgets.find((entry) => entry.id === id);
    expect(authoritative, `budgets.json has no "${id}"`).toBeDefined();
    expect(
      mirrored?.limit,
      `src/perf/budgets.ts says ${mirrored?.limit ?? 'nothing'} and budgets.json says ` +
        `${authoritative?.max_gzip_bytes ?? 'nothing'}. budgets.json is authoritative — it is what ` +
        'scripts/check-budgets.ts reads after the build. Correct the mirror, not the original.',
    ).toBe(authoritative?.max_gzip_bytes);
    expect(mirrored?.required).toBe(authoritative?.required);
  });
});

describe('the honest status', () => {
  it('marks the runtime budgets as not yet measurable, because no browser tier has landed', () => {
    // playwright.config.ts and tests/browser/budgets.spec.ts belong to the
    // cinema-conformance-harness worker. Marking these `measurable` before that lands
    // would be a claim about a gate that does not exist.
    for (const id of RUNTIME_BUDGET_IDS) {
      expect(budgetById(id)?.status, id).toBe('not-yet-measurable');
    }
  });

  it('marks the byte budgets as measurable, because check-budgets.ts really does run', () => {
    for (const id of BYTE_BUDGET_IDS) {
      expect(budgetById(id)?.status).toBe('measurable');
      expect(budgetById(id)?.measuredBy).toBe('scripts/check-budgets.ts');
    }
  });

  it('makes exactly one budget optional, and says which', () => {
    const optional = BUDGETS.filter((budget) => !budget.required).map((budget) => budget.id);
    // BUILD_PLAN §10.2 cut 1: `rm -r render3d/`. The absence is legal because somebody
    // wrote it down, not because nothing noticed.
    expect(optional).toEqual(['memory-register-walk']);
  });
});
