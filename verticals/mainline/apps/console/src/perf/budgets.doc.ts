// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `docs/performance-budgets.md`'s tables, GENERATED from `budgets.ts` and `marks.ts`.
 *
 * Same idiom as `src/design/registers.doc.ts` and `src/a11y/contract.doc.ts`: a pure
 * renderer plus a refusing test, so the committed document is byte-identical to the code
 * or CI is red. A performance document that has drifted from the numbers the gate
 * enforces is worse than none, because it is the version somebody quotes.
 */

import { BUDGETS, formatLimit, type Budget } from './budgets';
import { SPANS } from './marks';

export const GENERATED_BLOCKS = ['budgets', 'spans'] as const;

export type GeneratedBlock = (typeof GENERATED_BLOCKS)[number];

export function openMarker(block: GeneratedBlock): string {
  return `<!-- GENERATED:${block} — rendered from src/perf/budgets.ts + src/perf/marks.ts. Do not edit by hand. -->`;
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
 * `not-yet-measurable` prints as **NOT YET MEASURABLE**, in bold, in the table.
 *
 * It is the column a reader skims, and the whole point of `verdict.ts` is that this
 * state is not a pass. A document that rendered it as a quiet lowercase word would
 * undo in one glance what the type system spends a file enforcing.
 */
function statusOf(budget: Budget): string {
  return budget.status === 'measurable'
    ? `measured by ${code(budget.measuredBy)}`
    : `**NOT YET MEASURABLE** — ${code(budget.measuredBy)} has not landed`;
}

export function renderBudgetTable(): string {
  const rows = BUDGETS.map((budget) => {
    const required = budget.required ? 'required' : 'optional';
    return (
      `| ${code(budget.id)} | ${cell(budget.title)} | ${formatLimit(budget)} | ` +
      `${cell(budget.conditions)} | ${required} | ${statusOf(budget)} |`
    );
  });
  return [
    '| Budget | What it bounds | Limit | Only true under | Required | Status |',
    '|---|---|---|---|---|---|',
    ...rows,
  ].join('\n');
}

export function renderSpanTable(): string {
  const rows = SPANS.map(
    (span) =>
      `| ${code(span.id)} | ${code(span.from)} → ${code(span.to)} | ` +
      `${span.budget === null ? 'diagnostic only' : code(span.budget)} | ${cell(span.why)} |`,
  );
  return ['| Span | Between | Budget | Why measured there |', '|---|---|---|---|', ...rows].join('\n');
}

export function renderBlock(block: GeneratedBlock): string {
  switch (block) {
    case 'budgets':
      return renderBudgetTable();
    case 'spans':
      return renderSpanTable();
  }
}

export function renderMarkedBlock(block: GeneratedBlock): string {
  return `${openMarker(block)}\n\n${renderBlock(block)}\n\n${closeMarker(block)}`;
}

export function extractMarkedBlock(markdown: string, block: GeneratedBlock): string | null {
  const open = markdown.indexOf(openMarker(block));
  if (open < 0) return null;
  const contentStart = open + openMarker(block).length;
  const close = markdown.indexOf(closeMarker(block), contentStart);
  if (close < 0) return null;
  return markdown.slice(contentStart, close).trim();
}
