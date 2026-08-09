// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The MEMORY register's gates read FILE TEXT, and this is the one place that happens.
 *
 * Several rules in `docs/dimensionality-charter.md` are ABSENCES — no bloom, no orbit
 * control, no fifth colour, no `Math.random`, no WebGPU. An absence cannot be asserted
 * by calling a function; it is asserted by reading the bytes that ship and failing on a
 * name. Vite's `?raw` glob is how those bytes arrive.
 *
 * A glob that silently matches nothing is the classic way a gate becomes decorative:
 * every assertion downstream iterates an empty collection and passes. So every reader
 * here declares a MINIMUM and throws below it.
 *
 * Not a `.test.ts`, so Vitest does not collect it.
 */

type RawGlob = Record<string, unknown>;

function asSources(glob: RawGlob, what: string, minimum: number): Record<string, string> {
  const entries = Object.entries(glob);
  if (entries.length < minimum) {
    throw new Error(
      `ancestry-3d/_sources: the ${what} glob matched ${entries.length} file(s), fewer than the ` +
        `${minimum} required for the checks over it to mean anything.`,
    );
  }
  const out: Record<string, string> = {};
  for (const [path, value] of entries) {
    if (typeof value !== 'string') {
      throw new Error(
        `ancestry-3d/_sources: ${path} came back as ${typeof value} rather than text; the glob is ` +
          "missing `query: '?raw', import: 'default'`.",
      );
    }
    out[path] = value;
  }
  return out;
}

/** Every TypeScript source in the MEMORY register. */
export function memorySources(): Record<string, string> {
  return asSources(
    import.meta.glob('/src/features/ancestry/render3d/**/*.{ts,tsx}', {
      query: '?raw',
      import: 'default',
      eager: true,
    }),
    'src/features/ancestry/render3d/**/*.{ts,tsx}',
    12,
  );
}

/** The MEMORY register's stylesheet. */
export function memoryStylesheets(): Record<string, string> {
  return asSources(
    import.meta.glob('/src/features/ancestry/render3d/**/*.css', {
      query: '?raw',
      import: 'default',
      eager: true,
    }),
    'src/features/ancestry/render3d/**/*.css',
    1,
  );
}

/** Every TypeScript source in the application, for the deletability walk. */
export function applicationSources(): Record<string, string> {
  return asSources(
    import.meta.glob('/src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }),
    'src/**/*.{ts,tsx}',
    20,
  );
}

/** `src/design/tokens.css`, so the palette mirror is checked against the real thing. */
export function tokensCss(): string {
  const files = asSources(
    import.meta.glob('/src/design/tokens.css', {
      query: '?raw',
      import: 'default',
      eager: true,
    }),
    'src/design/tokens.css',
    1,
  );
  const text = Object.values(files)[0];
  if (text === undefined) throw new Error('ancestry-3d/_sources: tokens.css did not load.');
  return text;
}

/**
 * Strips line and block comments so a source scan does not fire on the prose that
 * EXPLAINS why a thing is forbidden. Every file in this directory names the banned
 * identifiers in its own documentation; a scanner that could not tell the difference
 * would make the documentation unwritable.
 */
export function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[^:])\/\/[^\n]*/g, '$1 ');
}

/** Every MEMORY source with its comments removed. The input to every absence check. */
export function memoryCode(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(memorySources()).map(([path, text]) => [path, stripComments(text)]),
  );
}
