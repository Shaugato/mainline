// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SOURCE HALF of D14's gate — pure, so it can be tested against planted fixtures.
 *
 * `audit.ts` audits a rendered tree. Three classes of defect are invisible to it:
 *
 *   1. Markup that never renders in a unit test because nothing mounts that branch.
 *   2. CSS. jsdom has no cascade, so `outline: none` inside a `:focus-visible` rule — the
 *      single edit that blinds a keyboard user — is unreachable from a DOM audit.
 *   3. A pattern that is only wrong because of WHERE it is: a `<canvas>` outside the
 *      MEMORY register, `signer_sub` used as a visual dimension.
 *
 * So these checks read the bytes that ship. They are here, in `src/`, rather than inside
 * `scripts/check-a11y.ts`, for one reason: a checker that only ever runs over a clean
 * repository is a checker nobody has seen fail. `tests/unit/a11y/source-checks.test.ts`
 * runs them against `tests/unit/a11y/fixtures/planted/`, where every check has a file
 * that must trip it and a file that must not.
 *
 * `scripts/check-a11y.ts` is the thin Node wrapper: it reads the filesystem, calls
 * `runSourceChecks`, and exits non-zero.
 *
 * ── VIOLATION versus NOTE ────────────────────────────────────────────────────────
 *
 * `outline: none` inside `:focus-visible` is a VIOLATION. `outline: none` inside a plain
 * `:focus` is a NOTE: the shell's `<main tabindex="-1">` is a programmatic focus target,
 * removing its ring is the correct thing to do there, and CSS alone cannot distinguish
 * that case from a real defect. A gate that fails a legitimate pattern is a gate that
 * gets deleted, so the weaker form is reported and not enforced — and this paragraph is
 * the record of that decision rather than a silence.
 */

export type CheckSeverity = 'violation' | 'note';

export type SourceKind = 'tsx' | 'ts' | 'css';

export interface SourceFile {
  /** Repo-relative, forward-slashed: `src/features/gate/RefusalBar.tsx`. */
  readonly path: string;
  readonly text: string;
  readonly kind: SourceKind;
  /** `true` for `src/features/ancestry/render3d/**` — the only MEMORY-register directory. */
  readonly inMemoryRegister: boolean;
}

export interface SourceViolation {
  readonly checkId: string;
  readonly severity: CheckSeverity;
  readonly file: string;
  /** 1-based. */
  readonly line: number;
  readonly text: string;
  readonly message: string;
  readonly help: string;
}

interface Hit {
  readonly line: number;
  readonly text: string;
  readonly message: string;
}

export interface SourceCheck {
  readonly id: string;
  readonly severity: CheckSeverity;
  readonly help: string;
  readonly run: (file: SourceFile) => readonly Hit[];
}

/**
 * The one file exempt from the scan, and the reason.
 *
 * This module necessarily CONTAINS every pattern it refuses — the regex that finds
 * `<canvas` is a line containing `<canvas`. Exempting it is not a loophole a caller can
 * widen: the list is a literal of length one, and `source-checks.test.ts` asserts that
 * length. Anything else added here would have to be defended in that test.
 */
export const SELF_EXEMPT: readonly string[] = ['src/a11y/source-checks.ts'];

/**
 * `true` when a line is a comment.
 *
 * Crude on purpose. A block-comment tracker over a whole file is a parser, and this
 * module is not allowed to be one. It errs toward SKIPPING, which can only produce a
 * missed finding, never a false one, and every check here is duplicated at some depth by
 * the DOM auditor.
 */
export function commentedOut(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*');
}

function eachLine(file: SourceFile, test: (line: string) => string | null): readonly Hit[] {
  const out: Hit[] = [];
  file.text.split(/\r?\n/).forEach((line, index) => {
    if (commentedOut(line)) return;
    const message = test(line);
    if (message !== null) out.push({ line: index + 1, text: line.trim(), message });
  });
  return out;
}

/** Walks a stylesheet, tracking the selector each declaration sits under. */
function eachDeclaration(
  file: SourceFile,
  test: (selector: string, declaration: string) => string | null,
): readonly Hit[] {
  const out: Hit[] = [];
  let selector = '';
  file.text.split(/\r?\n/).forEach((line, index) => {
    const trimmed = line.trim();
    if (trimmed.includes('{')) selector = trimmed.slice(0, trimmed.indexOf('{')).trim();
    const message = test(selector, trimmed);
    if (message !== null) out.push({ line: index + 1, text: trimmed, message });
  });
  return out;
}

export const SOURCE_CHECKS: readonly SourceCheck[] = [
  {
    id: 'positive-tabindex',
    severity: 'violation',
    help:
      'Use tabIndex={0} and move the element in the DOM. A positive tabindex jumps the whole ' +
      'document queue, so the order a screen reader reads in stops matching the order a keyboard ' +
      'walks in (docs/leads/ui.md D14).',
    run: (file) =>
      file.kind === 'css'
        ? []
        : eachLine(file, (line) => {
            const match = /tabIndex=\{\s*([0-9]+)\s*\}|tabindex=["']([0-9]+)["']/.exec(line);
            if (match === null) return null;
            const value = Number.parseInt(match[1] ?? match[2] ?? '0', 10);
            return value > 0 ? `tabindex ${value} is positive.` : null;
          }),
  },
  {
    id: 'aria-hidden-interactive',
    severity: 'violation',
    help:
      'Remove aria-hidden, or make the element unreachable with tabIndex={-1} / disabled / inert. ' +
      'A keyboard user can land on a control that speech output insists is not there.',
    run: (file) =>
      file.kind === 'css'
        ? []
        : eachLine(file, (line) => {
            if (!/aria-hidden=(?:"true"|\{true\}|'true')/.test(line)) return null;
            const interactive =
              /onClick=|onKeyDown=|href=/.test(line) || /tabIndex=\{\s*0\s*\}/.test(line);
            return interactive ? 'aria-hidden on an element that is also interactive.' : null;
          }),
  },
  {
    id: 'click-handler-on-non-interactive',
    severity: 'violation',
    help:
      'Use a <button>. A div with onClick is not reachable by keyboard and is announced as ' +
      'nothing; adding a role and a key handler is a reimplementation of an element that already ' +
      'exists.',
    run: (file) =>
      file.kind !== 'tsx'
        ? []
        : eachLine(file, (line) => {
            const match = /<(div|span|li|td|p|section|article|figure)\b[^>]*onClick=/.exec(line);
            if (match === null) return null;
            if (line.includes('role=') && /onKeyDown=|onKeyUp=/.test(line)) return null;
            return `<${match[1] ?? 'element'}> has onClick without both a role and a key handler.`;
          }),
  },
  {
    id: 'img-without-alt',
    severity: 'violation',
    help: 'Give the image an alt. `alt=""` is the correct answer for a decorative one and says so.',
    run: (file) =>
      file.kind !== 'tsx'
        ? []
        : eachLine(file, (line) => {
            const match = /<img\b([^>]*)>/.exec(line);
            if (match === null) return null;
            return /\balt[=\s]/.test(match[1] ?? '') ? null : '<img> with no alt attribute.';
          }),
  },
  {
    id: 'inner-html',
    severity: 'violation',
    help:
      'Render the value as text. A verbatim payload injected as HTML is a payload the browser ' +
      'reinterpreted, which is a paraphrase performed by the parser (D18).',
    run: (file) =>
      file.kind === 'css'
        ? []
        : eachLine(file, (line) =>
            line.includes('dangerouslySetInnerHTML') ? 'raw HTML injection is present.' : null,
          ),
  },
  {
    id: 'access-key',
    severity: 'violation',
    help:
      'Remove it. accessKey collides unpredictably with screen-reader and browser shortcuts, and ' +
      'there is no way for a reader to discover which key a control claimed.',
    run: (file) =>
      file.kind === 'css'
        ? []
        : eachLine(file, (line) => (/\baccessKey=/.test(line) ? 'accessKey is present.' : null)),
  },
  {
    id: 'no-canvas-outside-memory',
    severity: 'violation',
    help:
      'The ancestry walk is the only canvas in this product, and it lives in ' +
      'src/features/ancestry/render3d/. A fact drawn on a canvas is a fact with no accessible ' +
      'form, no selectable text and no print (docs/leads/ui.md §1.3).',
    run: (file) =>
      file.kind !== 'tsx' || file.inMemoryRegister
        ? []
        : eachLine(file, (line) =>
            /<canvas\b/i.test(line) ? 'a canvas is rendered outside the MEMORY register.' : null,
          ),
  },
  {
    id: 'signer-sub',
    severity: 'violation',
    help:
      'Choose another dimension. signer_sub may never be a colour, an axis, a facet or a sort key ' +
      'anywhere in this console, and no person is identified in the MEMORY register at all ' +
      '(docs/leads/ui.md D15 / I15 / the Attribution Rule).',
    run: (file) =>
      file.kind === 'css'
        ? []
        : eachLine(file, (line) => {
            if (
              file.inMemoryRegister &&
              /signer[_-]?[Ss]ub|data-person|personName|signerName/.test(line)
            ) {
              return 'a person is identified inside the MEMORY register.';
            }
            const dimension =
              /(data-(?:visual-dimension|colour-by|color-by|sort-key|facet|axis|group-by)|sortKey|colourBy|colorBy|facetBy|groupBy)\s*[=:]\s*["'{]?[^"'\n]*signer[_-]?[Ss]ub/.test(
                line,
              );
            return dimension ? 'signer_sub is used as a visual dimension.' : null;
          }),
  },
  {
    id: 'focus-visible-outline',
    severity: 'violation',
    help:
      'Restore the ring, or replace it with a box-shadow that meets the 3:1 non-text contrast ' +
      'floor. Removing the outline inside :focus-visible removes it from exactly the case ' +
      'keyboard users need it (WCAG 2.4.7, 2.4.11).',
    run: (file) =>
      file.kind !== 'css'
        ? []
        : eachDeclaration(file, (selector, declaration) => {
            if (!/outline\s*:\s*(none|0)\b/.test(declaration)) return null;
            if (!selector.includes(':focus-visible')) return null;
            return `"${selector}" removes the focus ring from :focus-visible.`;
          }),
  },
  {
    id: 'plain-focus-outline-removed',
    severity: 'note',
    help:
      'Legitimate on a programmatic focus target such as `<main tabindex="-1">`; a defect on ' +
      'anything a keyboard can Tab to. CSS alone cannot tell the two apart, so this is reported ' +
      'and not enforced.',
    run: (file) =>
      file.kind !== 'css'
        ? []
        : eachDeclaration(file, (selector, declaration) => {
            if (!/outline\s*:\s*(none|0)\b/.test(declaration)) return null;
            if (selector.includes(':focus-visible') || !selector.includes(':focus')) return null;
            return `"${selector}" removes the focus ring; confirm the element is not tabbable.`;
          }),
  },
  {
    id: 'verbatim-in-pseudo-element',
    severity: 'violation',
    help:
      'Put the value in the DOM as text. A CSS `content:` string is not selectable, not copyable ' +
      'and is dropped by some screen readers — a verbatim value the medium paraphrased.',
    run: (file) =>
      file.kind !== 'css'
        ? []
        : eachLine(file, (line) => {
            const match = /content\s*:\s*"([^"]{4,})"/.exec(line);
            const value = match?.[1] ?? '';
            // Short glyphs and separators are decoration; a word-shaped string is content.
            return /[A-Za-z]{4,}/.test(value)
              ? `content: "${value}" puts words in a pseudo-element.`
              : null;
          }),
  },
];

export const CHECK_IDS: readonly string[] = SOURCE_CHECKS.map((check) => check.id);

export function checkById(id: string): SourceCheck | null {
  return SOURCE_CHECKS.find((check) => check.id === id) ?? null;
}

export interface SourceCheckResult {
  readonly violations: readonly SourceViolation[];
  readonly notes: readonly SourceViolation[];
  readonly filesChecked: number;
  readonly filesExempt: readonly string[];
  readonly checksRun: readonly string[];
}

/** Runs every check over every file, minus the self-exemption. */
export function runSourceChecks(files: readonly SourceFile[]): SourceCheckResult {
  const exempt = files.filter((file) => SELF_EXEMPT.includes(file.path)).map((file) => file.path);
  const subject = files.filter((file) => !SELF_EXEMPT.includes(file.path));

  const violations: SourceViolation[] = [];
  const notes: SourceViolation[] = [];

  for (const file of subject) {
    for (const check of SOURCE_CHECKS) {
      for (const hit of check.run(file)) {
        const record: SourceViolation = {
          checkId: check.id,
          severity: check.severity,
          file: file.path,
          line: hit.line,
          text: hit.text,
          message: hit.message,
          help: check.help,
        };
        if (check.severity === 'violation') violations.push(record);
        else notes.push(record);
      }
    }
  }

  return {
    violations,
    notes,
    filesChecked: subject.length,
    filesExempt: exempt,
    checksRun: CHECK_IDS,
  };
}

/** Classifies a file path the way `runSourceChecks` needs it. Shared with the Node wrapper. */
export function classify(relativePath: string, text: string): SourceFile {
  const path = relativePath.split('\\').join('/');
  const kind: SourceKind = path.endsWith('.css') ? 'css' : path.endsWith('.tsx') ? 'tsx' : 'ts';
  return {
    path,
    text,
    kind,
    inMemoryRegister: path.startsWith('src/features/ancestry/render3d/'),
  };
}
