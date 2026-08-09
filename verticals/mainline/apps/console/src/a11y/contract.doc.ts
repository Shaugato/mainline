// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `docs/accessibility.md`'s tables, GENERATED from `contract.ts` and `audit.ts`.
 *
 * Same idiom as `src/design/registers.doc.ts`, for the same reason: an accessibility
 * document and an accessibility implementation agree on the day they are written and
 * diverge on every day after. Here the divergence is worse than in a design system,
 * because the document is the thing somebody quotes in a procurement answer.
 *
 * There is no writer script. A pure renderer plus `tests/unit/a11y/doc-generated.test.ts`
 * means the committed document is byte-identical to the code or CI is red, and the
 * failure message is the exact text to paste.
 */

import { RULES } from './audit';
import {
  A11Y_LAW,
  IMPACTS,
  KEYBOARD_TRAVERSAL,
  SURFACE_OPERATIONS,
  type Coverage,
} from './contract';

export const GENERATED_BLOCKS = ['laws', 'rules', 'traversal', 'operations'] as const;

export type GeneratedBlock = (typeof GENERATED_BLOCKS)[number];

export function openMarker(block: GeneratedBlock): string {
  return `<!-- GENERATED:${block} — rendered from src/a11y/contract.ts + src/a11y/audit.ts. Do not edit by hand. -->`;
}

export function closeMarker(block: GeneratedBlock): string {
  return `<!-- /GENERATED:${block} -->`;
}

function cell(text: string): string {
  return text.replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

function code(text: string): string {
  return `\`${text}\``;
}

/**
 * How each coverage state prints.
 *
 * `browser-tier` prints as **NOT YET MEASURED** on purpose. A table where every row says
 * something reassuring is a table nobody has audited, and this document is the one a
 * reader is most likely to quote back at us.
 */
const COVERAGE_LABEL: Readonly<Record<Coverage, string>> = {
  enforced: 'enforced here',
  'enforced-elsewhere': 'enforced (other suite)',
  'browser-tier': '**NOT YET MEASURED** (browser tier)',
  unenforced: '**UNENFORCED**',
};

/** The law: one row per rule, with its coverage and the check that holds it. */
export function renderLawTable(): string {
  const rows = A11Y_LAW.map((law) => {
    const wcag = law.wcag.length === 0 ? '—' : law.wcag.map(code).join(', ');
    const registers = law.registers.map((register) => register.toUpperCase()).join(' · ');
    const by = law.enforcedBy.map(code).join('<br>');
    return `| ${code(law.id)} | ${cell(law.statement)} | ${wcag} | ${registers} | ${COVERAGE_LABEL[law.coverage]} | ${by} |`;
  });
  return [
    '| Law | Statement | WCAG 2.2 | Registers | Coverage | Held up by |',
    '|---|---|---|---|---|---|',
    ...rows,
  ].join('\n');
}

/** Every rule `src/a11y/audit.ts` runs, with its impact. */
export function renderRuleTable(): string {
  const byImpact = [...RULES].sort(
    (a, b) => IMPACTS.indexOf(b.impact) - IMPACTS.indexOf(a.impact) || a.id.localeCompare(b.id),
  );
  const rows = byImpact.map(
    (rule) =>
      `| ${code(rule.id)} | ${rule.impact} | ${rule.wcag.length === 0 ? '—' : rule.wcag.map(code).join(', ')} | ${cell(rule.help)} |`,
  );
  return ['| Rule | Impact | WCAG 2.2 | What to do about it |', '|---|---|---|---|', ...rows].join(
    '\n',
  );
}

/** The keyboard-only path D14 requires, in order. */
export function renderTraversal(): string {
  const rows = KEYBOARD_TRAVERSAL.map(
    (step, index) =>
      `| ${index + 1} | ${code(step.id)} | ${code(step.surface)} | ${cell(step.action)} |`,
  );
  return ['| # | Step | Surface | The operator... |', '|---|---|---|---|', ...rows].join('\n');
}

/** What operating each surface without a mouse or a screen actually means. */
export function renderOperations(): string {
  const parts: string[] = [];
  for (const entry of SURFACE_OPERATIONS) {
    parts.push(`#### \`${entry.surface}\``);
    parts.push('');
    for (const operation of entry.operations) parts.push(`- ${operation}`);
    parts.push('');
  }
  return parts.join('\n').trimEnd();
}

export function renderBlock(block: GeneratedBlock): string {
  switch (block) {
    case 'laws':
      return renderLawTable();
    case 'rules':
      return renderRuleTable();
    case 'traversal':
      return renderTraversal();
    case 'operations':
      return renderOperations();
  }
}

export function renderMarkedBlock(block: GeneratedBlock): string {
  return `${openMarker(block)}\n\n${renderBlock(block)}\n\n${closeMarker(block)}`;
}

/** What the committed document currently has between a block's markers, or `null`. */
export function extractMarkedBlock(markdown: string, block: GeneratedBlock): string | null {
  const open = markdown.indexOf(openMarker(block));
  if (open < 0) return null;
  const contentStart = open + openMarker(block).length;
  const close = markdown.indexOf(closeMarker(block), contentStart);
  if (close < 0) return null;
  return markdown.slice(contentStart, close).trim();
}
