// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `docs/visual-language.md`'s tables, GENERATED from `registers.ts`.
 *
 * The spec and the implementation are the same object. `registers.ts` is the source of
 * truth; this module renders it as Markdown; `doc-generated.test.ts` asserts the
 * committed document contains exactly this output between its generated markers, and
 * prints the expected block when it does not.
 *
 * That is why there is no filesystem access here. A generator that writes a file needs
 * `node:fs`, which this workspace's application tsconfig deliberately cannot see, and a
 * generator that runs only when somebody remembers to run it is a documentation process
 * rather than a gate. A pure renderer plus a refusing test cannot drift: the document is
 * either byte-identical to the code or CI is red.
 */

import { REGISTER_LAW, REGISTERS, TOKEN_LAW, type Register, type TokenGroup } from './registers';

/** The marker pairs `doc-generated.test.ts` looks for in the Markdown. */
export const GENERATED_BLOCKS = ['registers', 'register-laws', 'tokens'] as const;

export type GeneratedBlock = (typeof GENERATED_BLOCKS)[number];

export function openMarker(block: GeneratedBlock): string {
  return `<!-- GENERATED:${block} — rendered from src/design/registers.ts. Do not edit by hand. -->`;
}

export function closeMarker(block: GeneratedBlock): string {
  return `<!-- /GENERATED:${block} -->`;
}

/** Escapes the two characters that would break a Markdown table cell. */
function cell(text: string): string {
  return text.replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

function code(text: string): string {
  return `\`${text}\``;
}

/** The register overview: what each register is, where it lives, what it may not see. */
export function renderRegisterTable(): string {
  const rows = REGISTER_LAW.map((law) => {
    const directories = [
      ...law.directories.map((directory) => `${directory}/**`),
      ...law.flatDirectories.map((directory) => `${directory}/*`),
    ]
      .map(code)
      .join('<br>');
    const forbidden =
      law.forbidden.length === 0
        ? '— (nothing; this is the only register that may draw with a GPU)'
        : law.forbidden.map(code).join('<br>');
    const ceiling = law.durationCeilingMs === null ? 'no motion' : `${law.durationCeilingMs} ms`;
    return `| **${law.label}** | ${cell(law.gloss)} | ${cell(law.surfaces.join(' · '))} | ${directories} | ${forbidden} | ${ceiling} |`;
  });

  return [
    '| Register | Gloss | Surfaces | Directories | May not import | Motion ceiling |',
    '|---|---|---|---|---|---|',
    ...rows,
  ].join('\n');
}

/** Each register's law, as the numbered testable sentences `registers.ts` declares. */
export function renderRegisterLaws(): string {
  const sections = REGISTER_LAW.map((law) => {
    const lines = law.laws.map((sentence, index) => `${index + 1}. ${sentence}`);
    return [`### ${law.label} — ${law.gloss}`, '', ...lines].join('\n');
  });
  return sections.join('\n\n');
}

const GROUP_ORDER: readonly TokenGroup[] = [
  'surface',
  'boundary',
  'ink',
  'severity',
  'state',
  'geometry',
  'type',
  'space',
  'motion',
];

const GROUP_TITLE: Readonly<Record<TokenGroup, string>> = {
  surface: 'Surfaces',
  boundary: 'Boundaries',
  ink: 'Ink',
  severity: 'Severity — banded to `mainline.virulence_class`',
  state: 'States',
  geometry: 'Geometry',
  type: 'Type',
  space: 'Space',
  motion: 'Motion',
};

function registerCells(allowed: readonly Register[]): string {
  return REGISTERS.map((register) => (allowed.includes(register) ? '✓' : '·')).join(' | ');
}

/**
 * The token map: every token, and the registers permitted to reference it.
 *
 * A `·` is a refusal, not an omission. `--tp-ok` is EVIDENCE-only because the only
 * green in this console is a verification seal that a recomputation produced, and a
 * green that can appear in a 3D scene is a green that can appear without arithmetic
 * behind it.
 */
export function renderTokenTable(): string {
  const parts: string[] = [];
  for (const group of GROUP_ORDER) {
    const rules = TOKEN_LAW.filter((rule) => rule.group === group);
    if (rules.length === 0) continue;
    parts.push(`#### ${GROUP_TITLE[group]}`);
    parts.push('');
    parts.push('| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |');
    parts.push('|---|---|---|---|---|');
    for (const rule of rules) {
      parts.push(`| ${code(rule.token)} | ${cell(rule.purpose)} | ${registerCells(rule.registers)} |`);
    }
    parts.push('');
  }
  return parts.join('\n').trimEnd();
}

export function renderBlock(block: GeneratedBlock): string {
  switch (block) {
    case 'registers':
      return renderRegisterTable();
    case 'register-laws':
      return renderRegisterLaws();
    case 'tokens':
      return renderTokenTable();
  }
}

/** `openMarker … content … closeMarker`, exactly as it must appear in the document. */
export function renderMarkedBlock(block: GeneratedBlock): string {
  return `${openMarker(block)}\n\n${renderBlock(block)}\n\n${closeMarker(block)}`;
}

/**
 * Extracts what the document currently has between a block's markers.
 * `null` means the markers are missing or out of order — which is a failure, not an
 * empty block: a generated table nobody can find is a table that stopped being checked.
 */
export function extractMarkedBlock(markdown: string, block: GeneratedBlock): string | null {
  const open = markdown.indexOf(openMarker(block));
  if (open < 0) return null;
  const contentStart = open + openMarker(block).length;
  const close = markdown.indexOf(closeMarker(block), contentStart);
  if (close < 0) return null;
  return markdown.slice(contentStart, close).trim();
}
