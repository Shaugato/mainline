// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Reads `tokens.css` as TEXT and turns it into a value map.
 *
 * The contrast, severity and motion gates all need the token VALUES. There are three
 * ways to get them and only one of them is honest:
 *
 *   ✗ Duplicate the values in a TypeScript object. Then the tests check the duplicate,
 *     the duplicate drifts, and the gate quietly stops covering the stylesheet.
 *   ✗ Read `getComputedStyle` in jsdom. jsdom does not implement `oklch()`, so every
 *     value comes back as the literal authored string or as an empty string depending
 *     on the property — a gate that passes because the environment cannot disagree.
 *   ✓ Parse the stylesheet text. The bytes that ship are the bytes under test.
 *
 * The parser is deliberately small and deliberately STRICT: it understands exactly the
 * subset of CSS `tokens.css` is written in, and anything else is a parse failure rather
 * than a silent skip. A token this parser cannot read is a token the gate stops
 * covering, so refusing to read it is how the gate stays total.
 *
 * Pure text in, data out — no filesystem, no DOM, no environment. The caller supplies
 * the text (the tests do it with a Vite `?raw` import), which is also what makes this
 * module safe to import from the EVIDENCE register.
 */

/** One `--custom-property: value` declaration. */
export interface TokenDeclaration {
  readonly token: string;
  readonly value: string;
}

/** The three selectors `tokens.css` uses to declare a register of light. */
export type TokenScope = 'dark' | 'print' | 'explicit-light';

export interface TokenScopeBlock {
  readonly scope: TokenScope;
  /** The selector text, verbatim, for a failure message that points at a real line. */
  readonly selector: string;
  readonly declarations: readonly TokenDeclaration[];
}

/**
 * Strips CSS block comments.
 *
 * Comment stripping must happen before anything else: `tokens.css` documents the ramp's
 * monotonicity inside a comment, in the same `L: 0.845 > 0.775` notation the real
 * declarations use, and a parser that read comments would happily "find" tokens that do
 * not exist.
 */
export function stripCssComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '');
}

const DECLARATION = /(--[a-z0-9-]+)\s*:\s*([^;}]+);/gi;

/** Every `--token: value;` inside one block of declaration text. */
export function parseDeclarations(blockBody: string): readonly TokenDeclaration[] {
  const out: TokenDeclaration[] = [];
  DECLARATION.lastIndex = 0;
  let match = DECLARATION.exec(blockBody);
  while (match !== null) {
    const token = match[1];
    const value = match[2];
    if (token !== undefined && value !== undefined) {
      out.push({ token, value: value.trim().replace(/\s+/g, ' ') });
    }
    match = DECLARATION.exec(blockBody);
  }
  return out;
}

/**
 * Extracts the body of the first `{ … }` block whose selector line matches `selector`,
 * balancing braces so that a nested at-rule does not truncate the block.
 */
function blockAfter(css: string, index: number): { body: string; end: number } | null {
  const open = css.indexOf('{', index);
  if (open < 0) return null;
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    const ch = css[i];
    if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) return { body: css.slice(open + 1, i), end: i };
    }
  }
  return null;
}

/**
 * The three token scopes, in the order `tokens.css` declares them.
 *
 * Throws when a scope is missing. That is the correct behaviour: the light register
 * exists so the printed exhibit is legible, and a print register that silently
 * disappeared would be discovered by a court clerk holding an unreadable page rather
 * than by CI.
 */
export function parseTokenScopes(css: string): readonly TokenScopeBlock[] {
  const clean = stripCssComments(css);

  const findRoot = (): TokenScopeBlock => {
    // The bare `:root {` — the dark register. Anchored so that
    // `:root[data-register-theme='light']` cannot match it.
    const match = /(^|\})\s*(:root)\s*\{/.exec(clean);
    if (match === null) throw new Error('tokens.css: no bare `:root { … }` block — the dark register is missing.');
    const body = blockAfter(clean, match.index + match[0].length - 1);
    if (body === null) throw new Error('tokens.css: the `:root` block is unbalanced.');
    return { scope: 'dark', selector: ':root', declarations: parseDeclarations(body.body) };
  };

  const findPrint = (): TokenScopeBlock => {
    const at = clean.indexOf('@media print');
    if (at < 0) throw new Error('tokens.css: no `@media print` block — the print register is missing.');
    const outer = blockAfter(clean, at);
    if (outer === null) throw new Error('tokens.css: the `@media print` block is unbalanced.');
    const inner = /:root\s*\{/.exec(outer.body);
    if (inner === null) throw new Error('tokens.css: `@media print` declares no `:root` block.');
    const body = blockAfter(outer.body, inner.index);
    if (body === null) throw new Error('tokens.css: the print `:root` block is unbalanced.');
    return {
      scope: 'print',
      selector: '@media print :root',
      declarations: parseDeclarations(body.body),
    };
  };

  const findExplicit = (): TokenScopeBlock => {
    const match = /:root\[data-register-theme=['"]light['"]\]\s*\{/.exec(clean);
    if (match === null) {
      throw new Error(
        'tokens.css: no `:root[data-register-theme="light"]` block — the print register cannot be reviewed on screen before it is printed.',
      );
    }
    const body = blockAfter(clean, match.index);
    if (body === null) throw new Error('tokens.css: the explicit-light block is unbalanced.');
    return {
      scope: 'explicit-light',
      selector: ":root[data-register-theme='light']",
      declarations: parseDeclarations(body.body),
    };
  };

  return [findRoot(), findPrint(), findExplicit()];
}

/** A scope's declarations as a lookup. Later declarations win, as the cascade does. */
export function toMap(block: TokenScopeBlock): ReadonlyMap<string, string> {
  const map = new Map<string, string>();
  for (const declaration of block.declarations) map.set(declaration.token, declaration.value);
  return map;
}

/**
 * The effective token map for one register of light.
 *
 * The dark block is complete; the light blocks OVERRIDE it and legitimately omit the
 * tokens that do not change (type, space, motion, geometry). Resolution therefore
 * layers light over dark, which is exactly what the browser does — and it means a
 * contrast test for the light register is testing what a printer actually receives
 * rather than a partial block.
 */
export function resolveTokens(
  scopes: readonly TokenScopeBlock[],
  scope: TokenScope,
): ReadonlyMap<string, string> {
  const dark = scopes.find((block) => block.scope === 'dark');
  if (dark === undefined) throw new Error('token-source: no dark scope to resolve against.');
  const merged = new Map(toMap(dark));
  if (scope !== 'dark') {
    const overlay = scopes.find((block) => block.scope === scope);
    if (overlay === undefined) throw new Error(`token-source: no ${scope} scope.`);
    for (const [token, value] of toMap(overlay)) merged.set(token, value);
  }
  return merged;
}

/** Every `--tp-*` referenced through `var(--tp-…)` anywhere in a stylesheet. */
export function referencedTokens(css: string): ReadonlySet<string> {
  const out = new Set<string>();
  const pattern = /var\(\s*(--[a-z0-9-]+)/gi;
  let match = pattern.exec(stripCssComments(css));
  while (match !== null) {
    const token = match[1];
    if (token !== undefined) out.add(token);
    match = pattern.exec(stripCssComments(css));
  }
  return out;
}

/** One `selector { … }` rule, for the per-block checks the CSS gates run. */
export interface CssRuleBlock {
  readonly selector: string;
  readonly body: string;
}

/**
 * Splits a stylesheet into flat `selector { body }` rules.
 *
 * At-rules are entered rather than skipped, so a declaration hidden inside
 * `@media print { … }` is still subject to every rule the gates enforce. A policy that
 * stops at a media query is a policy with a documented way around it.
 */
export function parseRuleBlocks(css: string): readonly CssRuleBlock[] {
  const clean = stripCssComments(css);
  const out: CssRuleBlock[] = [];

  const walk = (text: string, prefix: string): void => {
    let index = 0;
    while (index < text.length) {
      const open = text.indexOf('{', index);
      if (open < 0) break;
      const selector = text.slice(index, open).trim();
      const block = blockAfter(text, open - 1 < 0 ? 0 : open);
      if (block === null) break;
      const body = block.body;
      if (selector.startsWith('@')) {
        walk(body, `${prefix}${selector} `);
      } else if (body.includes('{')) {
        // A nested rule (CSS nesting is not used in this package, but a future edit
        // might). Recurse rather than mis-attribute the inner declarations.
        walk(body, `${prefix}${selector} `);
      } else {
        out.push({ selector: `${prefix}${selector}`, body });
      }
      index = block.end + 1;
    }
  };

  walk(clean, '');
  return out;
}
