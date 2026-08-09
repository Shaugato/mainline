// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CONTRACT, CHECKED AGAINST THE THINGS IT CLAIMS.
 *
 * `contract.ts` is a document that asserts things about the rest of the repository: that
 * a law is enforced, by a named rule, in a named file. A document like that decays in
 * exactly one direction — the claims stay and the checks leave — and the decay is
 * invisible because the document still reads correctly.
 *
 * So every claim is resolved here:
 *
 *   · a law whose coverage is `enforced` must name a rule that `audit.ts` implements or a
 *     check that `source-checks.ts` implements;
 *   · a law whose coverage is `enforced-elsewhere` must name a file that EXISTS;
 *   · a law whose coverage is `browser-tier` must name a `tests/browser/` path and must
 *     carry the sentence saying it is not yet measured;
 *   · every rule `audit.ts` implements must be cited by some law, so a rule nobody's law
 *     names cannot quietly become dead code;
 *   · every declared surface must have a written statement of what operating it without a
 *     mouse or a screen means.
 */

import { describe, expect, it } from 'vitest';

import {
  A11Y_LAW,
  BLOCKING_IMPACTS,
  COVERAGE_STATES,
  IMPACTS,
  KEYBOARD_TRAVERSAL,
  MEASURED_COVERAGE,
  SURFACE_OPERATIONS,
  enforcementTokens,
  impactRank,
  isBlocking,
  lawById,
  operationsFor,
  verifyTraversal,
} from '../../../src/a11y/contract';
import { RULES, RULE_IDS } from '../../../src/a11y/audit';
import { CHECK_IDS } from '../../../src/a11y/source-checks';
import { DECLARED_SURFACES } from '../../../src/app/surfaces';
import { REGISTERS } from '../../../src/design/registers';

/** Every source path in the workspace, so a claim about a file can be resolved. */
const REPO_FILES: ReadonlySet<string> = new Set([
  ...Object.keys(import.meta.glob('/src/**/*.{ts,tsx}')),
  ...Object.keys(import.meta.glob('/tests/**/*.{ts,tsx}')),
  ...Object.keys(import.meta.glob('/scripts/**/*.ts')),
]);

function fileExists(path: string): boolean {
  return REPO_FILES.has(path.startsWith('/') ? path : `/${path}`);
}

type TokenKind = 'audit-rule' | 'source-check' | 'file' | 'symbol';

function classifyToken(token: string): TokenKind {
  if (RULE_IDS.includes(token)) return 'audit-rule';
  if (token.startsWith('check-a11y:')) return 'source-check';
  if (token.includes('/')) return 'file';
  return 'symbol';
}

describe('the law is well formed', () => {
  it('has unique ids and testable sentences', () => {
    const ids = A11Y_LAW.map((law) => law.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(A11Y_LAW.length).toBeGreaterThan(10);

    for (const law of A11Y_LAW) {
      expect(law.id, `${law.id} is not kebab-case`).toMatch(/^[a-z][a-z0-9-]*$/);
      // A sentence that cannot fail a check is a value statement, not a law.
      expect(law.statement.length, `${law.id} states almost nothing`).toBeGreaterThan(60);
      expect(law.statement.endsWith('.'), `${law.id} is not a sentence`).toBe(true);
      expect(COVERAGE_STATES).toContain(law.coverage);
      expect(law.enforcedBy.length, `${law.id} names nothing that holds it up`).toBeGreaterThan(0);
      for (const register of law.registers) expect(REGISTERS).toContain(register);
      for (const criterion of law.wcag) expect(criterion).toMatch(/^\d+\.\d+\.\d+$/);
    }
  });

  it('resolves by id, and refuses one it does not have', () => {
    expect(lawById('every-control-is-named')?.coverage).toBe('enforced');
    expect(lawById('a-law-nobody-wrote')).toBeNull();
  });

  it('orders impacts, and blocks exactly serious and critical', () => {
    expect([...IMPACTS]).toEqual(['minor', 'moderate', 'serious', 'critical']);
    expect(impactRank('critical')).toBeGreaterThan(impactRank('serious'));
    expect([...BLOCKING_IMPACTS]).toEqual(['serious', 'critical']);
    expect(isBlocking('serious')).toBe(true);
    expect(isBlocking('moderate')).toBe(false);
  });
});

describe('every claim the law makes resolves', () => {
  it.each(A11Y_LAW.filter((law) => law.coverage === 'enforced').map((law) => law.id))(
    '`%s` is enforced by a rule or check that actually exists',
    (id) => {
      const law = lawById(id);
      expect(law).not.toBeNull();
      const holders = (law?.enforcedBy ?? []).filter(
        (token) => classifyToken(token) !== 'symbol',
      );
      expect(holders.length, `${id} claims enforcement but names nothing checkable`).toBeGreaterThan(0);

      for (const token of holders) {
        const kind = classifyToken(token);
        if (kind === 'source-check') {
          const checkId = token.slice('check-a11y:'.length);
          expect(
            CHECK_IDS,
            `${id} cites the static check "${checkId}", which src/a11y/source-checks.ts does not implement`,
          ).toContain(checkId);
        } else if (kind === 'file') {
          expect(fileExists(token), `${id} cites ${token}, which does not exist`).toBe(true);
        }
      }
    },
  );

  it.each(A11Y_LAW.filter((law) => law.coverage === 'enforced-elsewhere').map((law) => law.id))(
    '`%s` names another suite’s file, and that file exists',
    (id) => {
      const law = lawById(id);
      const files = (law?.enforcedBy ?? []).filter((token) => classifyToken(token) === 'file');
      expect(files.length, `${id} claims another suite holds it but names no file`).toBeGreaterThan(0);
      for (const file of files) {
        expect(
          fileExists(file),
          `${id} says ${file} holds this law. That file is not in the workspace — either it was ` +
            'deleted, or the claim was never true.',
        ).toBe(true);
      }
    },
  );

  it.each(A11Y_LAW.filter((law) => law.coverage === 'browser-tier').map((law) => law.id))(
    '`%s` is recorded as NOT YET MEASURED and points at the browser tier',
    (id) => {
      const law = lawById(id);
      expect(law?.enforcedBy.some((token) => token.startsWith('tests/browser/'))).toBe(true);
      // A browser-tier law with no stated limit reads like a law that is held up.
      expect(law?.limit ?? '', `${id} claims the browser tier without saying it is unmeasured`).toContain(
        'NOT YET MEASURED',
      );
    },
  );

  it('has no unenforced law that is silent about it', () => {
    for (const law of A11Y_LAW.filter((entry) => entry.coverage === 'unenforced')) {
      expect(law.limit, `${law.id} is unenforced and says nothing about why`).toBeDefined();
    }
  });

  it('is honest about how much of itself is actually measured', () => {
    const measured = A11Y_LAW.filter((law) => MEASURED_COVERAGE.includes(law.coverage));
    // Not a target — a record. The number is allowed to be low; what is forbidden is a
    // document in which every row reads as covered.
    expect(measured.length).toBeGreaterThan(0);
    expect(measured.length).toBeLessThanOrEqual(A11Y_LAW.length);
    expect(A11Y_LAW.some((law) => law.coverage === 'browser-tier')).toBe(true);
  });
});

describe('every rule is cited by a law', () => {
  it.each([...RULE_IDS])('`%s` appears in some law’s enforcedBy', (ruleId) => {
    expect(
      enforcementTokens(),
      `audit.ts implements "${ruleId}" and no law names it. Either the law is missing or the rule ` +
        'is dead code — and a rule nobody cites is the one that gets deleted in a refactor.',
    ).toContain(ruleId);
  });

  it.each([...CHECK_IDS.filter((id) => id !== 'plain-focus-outline-removed')])(
    'static check `%s` appears in some law’s enforcedBy',
    (checkId) => {
      expect(enforcementTokens()).toContain(`check-a11y:${checkId}`);
    },
  );

  it('every rule declares an impact and real help', () => {
    for (const rule of RULES) {
      expect(IMPACTS).toContain(rule.impact);
      // A message that does not say what to do is a message somebody suppresses.
      expect(rule.help.length, `${rule.id} gives no actionable help`).toBeGreaterThan(60);
    }
  });
});

describe('the surface operations', () => {
  it('are in exact bijection with the declared surfaces', () => {
    const declared = DECLARED_SURFACES.map((surface) => surface.id).sort();
    const written = SURFACE_OPERATIONS.map((entry) => entry.surface).sort();
    expect(
      written,
      'a surface can be promised without anybody writing down what it means to operate it ' +
        'without a mouse or a screen. That is how an accessibility contract becomes decorative.',
    ).toEqual(declared);
  });

  it('state at least three operations each, phrased so a spec could attempt them', () => {
    for (const entry of SURFACE_OPERATIONS) {
      expect(entry.operations.length, `${entry.surface} states too few operations`).toBeGreaterThan(2);
      for (const operation of entry.operations) {
        expect(operation.length).toBeGreaterThan(30);
        expect(operation.endsWith('.')).toBe(true);
      }
    }
    expect(operationsFor('gate')?.operations.length).toBeGreaterThan(2);
    expect(operationsFor('not-a-surface')).toBeNull();
  });
});

describe('the keyboard traversal', () => {
  const declaredIds = KEYBOARD_TRAVERSAL.map((step) => step.id);

  it('starts at the refusal and ends at the signature', () => {
    expect(declaredIds[0]).toBe('refusal');
    expect(declaredIds[declaredIds.length - 1]).toBe('signature');
    expect(new Set(declaredIds).size).toBe(declaredIds.length);
  });

  it('names only declared surfaces, and admits no pointer-only step', () => {
    const surfaces = new Set(DECLARED_SURFACES.map((surface) => surface.id));
    for (const step of KEYBOARD_TRAVERSAL) {
      expect(surfaces, `${step.id} names surface "${step.surface}"`).toContain(step.surface);
      expect(step.pointerOnly).toBe(false);
    }
  });

  it('passes an observed order that contains every step in order, plus extras', () => {
    const observed = ['skip-link', ...declaredIds.slice(0, 3), 'nav', ...declaredIds.slice(3)];
    const result = verifyTraversal(observed);
    expect(result.ok).toBe(true);
    expect(result.unknown).toEqual(['skip-link', 'nav']);
    expect(result.message).toContain('intact');
  });

  it('FAILS when a step is unreachable', () => {
    const result = verifyTraversal(declaredIds.filter((id) => id !== 'signature'));
    expect(result.ok).toBe(false);
    expect(result.missing).toEqual(['signature']);
    expect(result.message).toContain('never reached: signature');
  });

  it('FAILS when the signature comes before the reading floor', () => {
    const scrambled = [...declaredIds];
    const floor = scrambled.indexOf('reading-floor');
    const signature = scrambled.indexOf('signature');
    [scrambled[floor], scrambled[signature]] = [scrambled[signature] ?? '', scrambled[floor] ?? ''];
    const result = verifyTraversal(scrambled);
    expect(
      result.ok,
      'reaching the signature before the reading floor is the ordering defect the whole path ' +
        'exists to prevent',
    ).toBe(false);
    expect(result.outOfOrder.length).toBeGreaterThan(0);
  });
});
