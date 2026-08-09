// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * D14 — the SOURCE half of the accessibility gate, as a CI command.
 *
 * All the judgement lives in `src/a11y/source-checks.ts`, which is pure and is exercised
 * against planted fixtures by `tests/unit/a11y/source-checks.test.ts`. This file is the
 * Node wrapper: it reads the bytes that ship, hands them over, and exits.
 *
 * That split is deliberate. A checker whose rules live inside its own CLI can only ever
 * be run over the real repository, which is clean — so nobody ever sees it fail, and a
 * regex that stopped matching two months ago reports success forever.
 *
 *   `node scripts/check-a11y.ts`
 *
 * Node 24 strips the types; there is no bundler in this path, which is why both files use
 * only erasable syntax.
 *
 * Exit codes: 0 clean (notes print and do not fail), 1 violations, 2 the script could not
 * run — because a gate that cannot measure has not passed, it has not run.
 */

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative, resolve, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { classify, runSourceChecks, SOURCE_CHECKS } from '../src/a11y/source-checks.ts';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(ROOT, 'src');

/** The fewest files a scan of this workspace can match and still mean anything. */
const MINIMUM_FILES = 20;

function die(message: string): never {
  process.stderr.write(`\ncheck-a11y: ${message}\n\n`);
  process.exit(2);
}

function walk(directory: string, out: string[]): void {
  for (const entry of readdirSync(directory)) {
    const full = join(directory, entry);
    if (statSync(full).isDirectory()) {
      walk(full, out);
      continue;
    }
    if (/\.(tsx|ts|css)$/.test(entry) && !entry.endsWith('.d.ts')) out.push(full);
  }
}

function main(): void {
  if (!existsSync(SRC)) {
    die(`${SRC} does not exist. "Nothing to check" is not the same as "clean".`);
  }

  const paths: string[] = [];
  walk(SRC, paths);
  if (paths.length < MINIMUM_FILES) {
    die(
      `only ${paths.length} source file(s) found under src/, fewer than the ${MINIMUM_FILES} this ` +
        'scan needs to mean anything. A glob that matches almost nothing reports the console ' +
        'clean by iterating an empty list.',
    );
  }

  const files = paths.map((path) =>
    classify(relative(ROOT, path).split(sep).join('/'), readFileSync(path, 'utf8')),
  );

  const result = runSourceChecks(files);

  console.log(
    `check-a11y: ${result.filesChecked} source file(s) against ${SOURCE_CHECKS.length} static ` +
      `check(s); ${result.filesExempt.length} exempt (${result.filesExempt.join(', ') || 'none'}).`,
  );

  if (result.notes.length > 0) {
    console.log(`\n${result.notes.length} note(s) — reported, not enforced:`);
    for (const note of result.notes) {
      console.log(`  ${note.file}:${note.line}  [${note.checkId}] ${note.message}`);
      console.log(`      ${note.text}`);
      console.log(`      why this is a note, not a failure: ${note.help}`);
    }
  }

  if (result.violations.length > 0) {
    console.error(`\n${result.violations.length} accessibility violation(s):\n`);
    for (const violation of result.violations) {
      console.error(`  ${violation.file}:${violation.line}  [${violation.checkId}]`);
      console.error(`      ${violation.message}`);
      console.error(`      ${violation.text}`);
      console.error(`      fix: ${violation.help}\n`);
    }
    console.error(
      'These are the defects a rendered-DOM audit cannot see. The DOM half runs in ' +
        'tests/unit/a11y/ on every `pnpm test`; docs/accessibility.md states what neither half ' +
        'checks.\n',
    );
    process.exit(1);
  }

  console.log('\ncheck-a11y: no violations.');
  console.log(
    'This checks SOURCE PATTERNS only. Colour contrast is covered by ' +
      'tests/unit/design/contrast.test.ts over the token set; focus-ring visibility, reflow and ' +
      'target size are not covered by any tier in this repository today — see ' +
      'docs/accessibility.md, which states that rather than implying otherwise.',
  );
}

main();
