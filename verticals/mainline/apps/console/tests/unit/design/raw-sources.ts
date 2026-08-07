// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The design gates read FILE TEXT, and this is the one place that reading happens.
 *
 * Every check in `tests/unit/design/` is written against the bytes that ship rather than
 * against a TypeScript copy of them: `tokens.css` for the palette, the CSS modules for the
 * usage rules, the `.ts`/`.tsx` sources for the module graph, and `visual-language.md` for
 * the generated tables. Vite's `?raw` glob is how that text arrives.
 *
 * ── WHY THIS IS A FUNCTION AND NOT AN INLINE CAST ────────────────────────────────
 *
 * `import.meta.glob(..., { query: '?raw', import: 'default', eager: true })` is typed
 * `Record<string, unknown>`. The obvious `as Record<string, string>` is a promise, and a
 * promise is exactly what the rest of this directory refuses to accept from anybody else.
 *
 * `asSources()` CHECKS instead. It refuses a non-string value, and — more usefully — it
 * refuses an EMPTY result. A glob that silently matches nothing is the classic way a gate
 * becomes decorative: every assertion downstream iterates an empty collection, every one
 * of them passes, and the suite reports green while checking nothing at all.
 *
 * Not a `.test.ts`, so Vitest does not collect it (`include` is `**/*.{test,spec}.*`).
 */

/** A glob result before it has been checked. */
export type RawGlob = Record<string, unknown>;

/**
 * Narrows a `?raw` glob to `path → text`, refusing anything that is not that.
 *
 * @param glob     the raw `import.meta.glob` result
 * @param what     what was being globbed, for the failure message
 * @param minimum  the fewest files this glob must match to be meaningful
 */
export function asSources(glob: RawGlob, what: string, minimum = 1): Record<string, string> {
  const entries = Object.entries(glob);

  if (entries.length < minimum) {
    throw new Error(
      `raw-sources: the ${what} glob matched ${entries.length} file(s), fewer than the ${minimum} ` +
        'required for the checks over it to mean anything. A glob that matches nothing makes ' +
        'every assertion downstream pass by iterating an empty collection.',
    );
  }

  const out: Record<string, string> = {};
  for (const [path, value] of entries) {
    if (typeof value !== 'string') {
      throw new Error(
        `raw-sources: ${path} came back as ${typeof value} rather than text. The glob is missing ` +
          "`query: '?raw', import: 'default'`, and the checks over it would be comparing objects.",
      );
    }
    out[path] = value;
  }
  return out;
}

/** The same, as the `Map` the module-graph walker takes. */
export function asSourceMap(glob: RawGlob, what: string, minimum = 1): Map<string, string> {
  return new Map(Object.entries(asSources(glob, what, minimum)));
}

/** Every stylesheet in the design package, `tokens.css` included. */
export function designStylesheets(): Record<string, string> {
  return asSources(
    import.meta.glob('/src/design/**/*.css', { query: '?raw', import: 'default', eager: true }),
    'src/design/**/*.css',
    4,
  );
}

/** The design package's COMPONENT stylesheets — `tokens.css` declares the palette rather
 *  than using it, so the usage rules must not be applied to it. */
export function componentStylesheets(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(designStylesheets()).filter(([path]) => !path.endsWith('/tokens.css')),
  );
}

/** Every TypeScript source in the application, for the module-graph walk. */
export function applicationSources(): Map<string, string> {
  return asSourceMap(
    import.meta.glob('/src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }),
    'src/**/*.{ts,tsx}',
    10,
  );
}

/** The deliberately-violating fixtures. Five files: four plants and one control. */
export function plantedSources(): Map<string, string> {
  return asSourceMap(
    import.meta.glob('/tests/unit/design/fixtures/planted/**/*.ts', {
      query: '?raw',
      import: 'default',
      eager: true,
    }),
    'tests/unit/design/fixtures/planted/**/*.ts',
    5,
  );
}
