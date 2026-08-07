// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE REGISTER LAW — the single source of truth for `docs/leads/ui.md` §1.1 (D9).
 *
 * Three registers. Every module belongs to exactly one, the register is decided by the
 * module's DIRECTORY, and the boundary is not a style guide — it is a dependency rule
 * enforced twice:
 *
 *   1. `eslint.config.js` spreads `registerBoundaryConfigs()` from this file, so a
 *      forbidden import is a lint error at the moment it is typed; and
 *   2. `tests/unit/design/register-boundary.test.ts` walks the actual module graph, so
 *      a forbidden import is still a failure when the lint rule is suppressed inline,
 *      when it is reached transitively through four intermediate modules, or when
 *      somebody edits the lint config.
 *
 * (2) exists because (1) can be disabled by the person violating it. A design law
 * nobody can violate is worth more than a design law everybody agrees with.
 *
 * ── CONSTRAINTS ON THIS FILE ─────────────────────────────────────────────────────
 *
 * It has ZERO imports and contains only data and pure functions, for two reasons that
 * are both mechanical:
 *
 *   • `eslint.config.js` is plain JavaScript and imports this module directly. Node
 *     ≥ 22.18 strips the types at load; an import of React, a CSS module, or anything
 *     with a bundler-specific resolution would break the lint config.
 *   • `tsconfig.json` sets `erasableSyntaxOnly`, so there is no TypeScript `enum` here
 *     and there never can be. The register "enum" is a frozen tuple plus a union type,
 *     which is the erasable form and is also the form the runtime needs.
 */

// ── The registers ────────────────────────────────────────────────────────────────

/**
 * The three registers, in order of increasing licence to move.
 *
 * This tuple must agree with `src/app/surfaces.ts`'s `REGISTERS`; the ordering is not
 * decorative — `registerAllows()` reads it as a ladder, and a surface that does not
 * declare a register is assigned `evidence` because that is the register that forbids
 * the most (see `surfaces.ts`'s `undeclared` handling).
 */
export const REGISTERS = ['evidence', 'instrument', 'memory'] as const;

export type Register = (typeof REGISTERS)[number];

export function isRegister(value: unknown): value is Register {
  return (REGISTERS as readonly unknown[]).includes(value);
}

// ── Package groups ───────────────────────────────────────────────────────────────

/**
 * Packages that draw with a GPU. Only the MEMORY register may see these.
 *
 * Expressed as GLOB GROUPS rather than exact names. `no-restricted-imports` matches its
 * `paths` entries as exact strings, so an entry named `@react-three/fiber` silently
 * permits `@react-three/fiber/native` and an entry named `motion/*` refuses a module
 * literally called `motion/*` while permitting `motion/react` — the import anybody
 * would actually write. A boundary that reads as enforced and is not is worse than no
 * boundary at all.
 */
export const GPU_PACKAGES: readonly string[] = [
  'three',
  'three/**',
  '@react-three/*',
  '@react-three/*/**',
];

/** Packages that move DOM. Forbidden in EVIDENCE; permitted in INSTRUMENT and MEMORY. */
export const MOTION_PACKAGES: readonly string[] = [
  'motion',
  'motion/**',
  'motion-dom',
  'motion-dom/**',
  'motion-utils',
  'motion-utils/**',
  'framer-motion',
  'framer-motion/**',
];

// ── Directory law ────────────────────────────────────────────────────────────────

/**
 * Which directories carry which register.
 *
 * These are ESLint `files` globs AND the input to the module-graph walker, which is the
 * point: the lint and the graph test cannot disagree about where the boundary is,
 * because there is one list.
 *
 * `src/features/ancestry` is split deliberately. The layout engine, the ribbon and the
 * print exhibit are EVIDENCE — they are the accessible, printable, cuttable form of the
 * blame walk. Only `render3d/` is MEMORY. That split is what makes BUILD_PLAN §10.2's
 * first cut (`rm -r render3d/`) leave a working console rather than a hole.
 */
export const EVIDENCE_DIRECTORIES: readonly string[] = [
  'src/app',
  'src/data',
  'src/verify',
  'src/features/gate',
  'src/features/diff',
  'src/features/disposition',
  'src/features/custody',
  'src/features/audit',
  'src/features/silence',
  'src/features/ancestry/layout',
  'src/features/ancestry/ribbon',
  'src/features/ancestry/exhibit',
];

/**
 * Files sitting directly in `src/features/ancestry/` — `surface.tsx`, `model.ts`,
 * `AncestryScreen.tsx`. EVIDENCE, but matched non-recursively so that the `render3d/`
 * subtree below them keeps its own register.
 */
export const EVIDENCE_FLAT_DIRECTORIES: readonly string[] = ['src/features/ancestry'];

export const INSTRUMENT_DIRECTORIES: readonly string[] = ['src/features/propagation'];

export const MEMORY_DIRECTORIES: readonly string[] = ['src/features/ancestry/render3d'];

/**
 * `src/design/` — this package — is REGISTER-NEUTRAL, and that is a design decision
 * with teeth rather than an exemption.
 *
 * Every register imports these primitives. If one of them imported `motion`, every
 * EVIDENCE surface in the console would transitively import `motion` and the boundary
 * would be dead on arrival while every lint rule stayed green. So the design package
 * imports NEITHER restricted group — the Counter and the Meter, which are INSTRUMENT
 * components, animate with CSS transitions under `motion.ts`'s policy and no library.
 *
 * `register-boundary.test.ts` asserts this directly, because it is the one rule whose
 * violation would be invisible in every feature directory.
 */
export const NEUTRAL_DIRECTORIES: readonly string[] = ['src/design'];

// ── The law, as data the documentation is generated from ─────────────────────────

export interface RegisterLaw {
  readonly register: Register;
  /** The register's name as it appears in prose and in `data-register` attributes. */
  readonly label: string;
  /** One line: what this register is FOR. */
  readonly gloss: string;
  /** The surfaces that live here, named as `docs/leads/ui.md` §1.1 names them. */
  readonly surfaces: readonly string[];
  /**
   * The register's law, as sentences that are individually testable. Each one is a
   * claim some test in `tests/unit/design/` or `tests/browser/` can fail on; a law that
   * cannot fail a test does not belong in this array.
   */
  readonly laws: readonly string[];
  /** Directory globs, recursive. */
  readonly directories: readonly string[];
  /** Directory globs, this level only. */
  readonly flatDirectories: readonly string[];
  /** Import specifiers refused inside those directories, as glob groups. */
  readonly forbidden: readonly string[];
  /** The animation ceiling in milliseconds. `null` means motion is forbidden outright. */
  readonly durationCeilingMs: number | null;
}

export const REGISTER_LAW: readonly RegisterLaw[] = [
  {
    register: 'evidence',
    label: 'EVIDENCE',
    gloss: 'severe — a screen that could be tendered as an exhibit',
    surfaces: [
      'gate refusal',
      'clause diff',
      'disposition',
      'custody',
      'audit',
      'silence',
      'ancestry ribbon + print exhibit',
    ],
    laws: [
      'Anything the database emitted verbatim is rendered in the mono face, as selectable text, never as an image.',
      'No easing over 160 ms, and nothing moves that a screenshot could not reproduce.',
      'No depth, no parallax, no gradient, no bloom, no particle, no shadow that implies a light source.',
      'One severity accent over one neutral ramp; the accent is banded to mainline.virulence_class and to nothing else.',
      'Every number carries a provenance chip naming how the console came to believe it.',
      'Fully operable with a keyboard alone and with a screen reader alone, and printable to a court-legible page.',
      'May not import a GPU package or a DOM-animation package, transitively or directly.',
    ],
    directories: EVIDENCE_DIRECTORIES,
    flatDirectories: EVIDENCE_FLAT_DIRECTORIES,
    forbidden: [...GPU_PACKAGES, ...MOTION_PACKAGES],
    durationCeilingMs: 160,
  },
  {
    register: 'instrument',
    label: 'INSTRUMENT',
    gloss: 'mechanical — motion is permitted only where the transition IS the fact',
    surfaces: [
      'the six gate counters',
      'the weld diagram',
      'the reading-floor meter',
      'propagation states',
    ],
    laws: [
      'A transition is permitted only when the transition itself is the fact being reported — a counter going 1 → 0 is the product working.',
      'Linear or a single cubic easing, never a spring, never a bounce, never an overshoot.',
      'No transition exceeds 220 ms, and every transition is interruptible.',
      'Every transition is skipped entirely under prefers-reduced-motion or a low-power capability signal, and the end state is identical either way.',
      'Colour is the EVIDENCE token set unchanged; an instrument does not get its own palette.',
      'May not import a GPU package.',
    ],
    directories: INSTRUMENT_DIRECTORIES,
    flatDirectories: [],
    forbidden: GPU_PACKAGES,
    durationCeilingMs: 220,
  },
  {
    register: 'memory',
    label: 'MEMORY',
    gloss: 'dimensional — the ancestry walk, and nothing else, ever',
    surfaces: ['the ancestry walk'],
    laws: [
      'THE STILLNESS RULE — the severity-5 node is the only object in the scene that never moves, never scales, never emits and never responds to hover. Everything else moves past it.',
      'The camera runs on rails at constant velocity; no easing into a fatality, no dolly zoom, no orbit.',
      'No emissive vocabulary: no bloom, no lens flare, no god rays, no particles, no depth of field.',
      'The scene uses FEWER colours than the tables — the neutral ramp plus the single severity accent, and nothing else.',
      'No name of any person is ever rendered here (D15 / I15 / the Attribution Rule).',
      'Optional by construction: every node and edge in the scene is also in the ribbon DOM, so deleting this register costs texture and no fact.',
    ],
    directories: MEMORY_DIRECTORIES,
    flatDirectories: [],
    forbidden: [],
    durationCeilingMs: 220,
  },
];

export function lawFor(register: Register): RegisterLaw {
  const found = REGISTER_LAW.find((entry) => entry.register === register);
  if (found === undefined) {
    // Unreachable while REGISTERS and REGISTER_LAW agree, which `registers.test.ts`
    // asserts. Throwing beats returning a default: a missing law would silently make
    // every check in that register vacuous.
    throw new Error(`registers.ts: no law declared for register "${register}".`);
  }
  return found;
}

// ── Token law ────────────────────────────────────────────────────────────────────

export type TokenGroup =
  | 'surface'
  | 'boundary'
  | 'ink'
  | 'severity'
  | 'state'
  | 'geometry'
  | 'type'
  | 'space'
  | 'motion';

export interface TokenRule {
  /** The custom property name, including the leading `--`. */
  readonly token: string;
  readonly group: TokenGroup;
  /** What it is for, in one clause. Rendered into docs/visual-language.md verbatim. */
  readonly purpose: string;
  /** The registers permitted to reference this token. */
  readonly registers: readonly Register[];
}

const ALL: readonly Register[] = REGISTERS;
const EVIDENCE_ONLY: readonly Register[] = ['evidence'];
const MOVING: readonly Register[] = ['instrument', 'memory'];

/**
 * EVERY token in `tokens.css`, mapped to the registers allowed to use it.
 *
 * `tokens.test.ts` asserts this table and the stylesheet are in EXACT bijection: a
 * token added to the CSS without a rule here fails, and a rule here naming a token the
 * CSS does not define fails. A token map that is allowed to be incomplete is a token
 * map that stops being read.
 */
export const TOKEN_LAW: readonly TokenRule[] = [
  { token: '--tp-bg', group: 'surface', purpose: 'the page ground', registers: ALL },
  { token: '--tp-bg-sunken', group: 'surface', purpose: 'chrome and footers — beneath the page', registers: ALL },
  { token: '--tp-bg-raised', group: 'surface', purpose: 'a panel or card standing on the page', registers: ALL },
  { token: '--tp-bg-inset', group: 'surface', purpose: 'a verbatim well: a payload, a plan fragment, a diff hunk', registers: ALL },

  { token: '--tp-rule', group: 'boundary', purpose: 'a decorative row separator; carries no meaning and is exempt from the 3:1 floor', registers: ALL },
  { token: '--tp-rule-strong', group: 'boundary', purpose: 'a meaningful boundary: a panel edge, a table head, a section break', registers: ALL },

  { token: '--tp-ink', group: 'ink', purpose: 'primary text', registers: ALL },
  { token: '--tp-ink-dim', group: 'ink', purpose: 'secondary text and supporting prose', registers: ALL },
  { token: '--tp-ink-faint', group: 'ink', purpose: 'labels, units and captions — never a fact on its own', registers: ALL },

  { token: '--tp-sev-routine', group: 'severity', purpose: "virulence_class 'routine' — near-neutral, because a routine clause is not an alarm", registers: ALL },
  { token: '--tp-sev-serious', group: 'severity', purpose: "virulence_class 'serious'", registers: ALL },
  { token: '--tp-sev-blood-major', group: 'severity', purpose: "virulence_class 'blood_major'", registers: ALL },
  { token: '--tp-sev-blood-fatal', group: 'severity', purpose: "virulence_class 'blood_fatal' — emphasis weight only, never small body text", registers: ALL },

  { token: '--tp-refuse', group: 'state', purpose: 'a refusal: the constraint name, the SQLSTATE, a failed seal — emphasis weight only', registers: ALL },
  { token: '--tp-refuse-ink', group: 'state', purpose: 'prose inside a refusal panel, where the accent would be unreadable at body size', registers: ALL },
  { token: '--tp-warn', group: 'state', purpose: 'unverified, staged, unset — a slot nobody filled must look like one', registers: ALL },
  { token: '--tp-ok', group: 'state', purpose: 'THE ONLY GREEN: the VerificationSeal verified state, and nothing else, ever', registers: EVIDENCE_ONLY },
  { token: '--tp-focus', group: 'state', purpose: 'the keyboard focus ring', registers: ALL },
  { token: '--tp-focus-width', group: 'geometry', purpose: 'focus ring width', registers: ALL },
  { token: '--tp-focus-offset', group: 'geometry', purpose: 'focus ring offset', registers: ALL },

  { token: '--tp-hairline', group: 'geometry', purpose: 'the one border width', registers: ALL },
  { token: '--tp-radius', group: 'geometry', purpose: 'the one corner radius', registers: ALL },

  { token: '--tp-sans', group: 'type', purpose: 'prose — everything the console wrote', registers: ALL },
  { token: '--tp-mono', group: 'type', purpose: 'verbatim — everything the database emitted', registers: ALL },
  { token: '--tp-step--1', group: 'type', purpose: 'caption and label size', registers: ALL },
  { token: '--tp-step-0', group: 'type', purpose: 'body size', registers: ALL },
  { token: '--tp-step-1', group: 'type', purpose: 'emphasis size — the floor for an accent foreground', registers: ALL },
  { token: '--tp-step-2', group: 'type', purpose: 'panel heading', registers: ALL },
  { token: '--tp-step-3', group: 'type', purpose: 'the refusal headline; one per screen at most', registers: ALL },
  { token: '--tp-leading-tight', group: 'type', purpose: 'headings and verbatim blocks', registers: ALL },
  { token: '--tp-leading-body', group: 'type', purpose: 'prose', registers: ALL },
  { token: '--tp-weight-regular', group: 'type', purpose: 'body weight', registers: ALL },
  { token: '--tp-weight-medium', group: 'type', purpose: 'label weight', registers: ALL },
  { token: '--tp-weight-strong', group: 'type', purpose: 'emphasis weight — required wherever an accent is the foreground', registers: ALL },
  { token: '--tp-tracking-caps', group: 'type', purpose: 'tracking for the uppercase label style', registers: ALL },

  { token: '--tp-space-1', group: 'space', purpose: '4px', registers: ALL },
  { token: '--tp-space-2', group: 'space', purpose: '8px', registers: ALL },
  { token: '--tp-space-3', group: 'space', purpose: '12px', registers: ALL },
  { token: '--tp-space-4', group: 'space', purpose: '20px', registers: ALL },
  { token: '--tp-space-5', group: 'space', purpose: '32px', registers: ALL },
  { token: '--tp-space-6', group: 'space', purpose: '52px', registers: ALL },

  { token: '--tp-duration-evidence', group: 'motion', purpose: '120 ms — under the EVIDENCE 160 ms ceiling', registers: ALL },
  { token: '--tp-duration-instrument', group: 'motion', purpose: '200 ms — under the INSTRUMENT 220 ms ceiling', registers: MOVING },
  { token: '--tp-ease-linear', group: 'motion', purpose: 'the default: a measurement does not accelerate', registers: MOVING },
  { token: '--tp-ease-mechanical', group: 'motion', purpose: 'the ONE permitted cubic; no spring, no bounce, no overshoot', registers: MOVING },
];

export function tokenRule(token: string): TokenRule | null {
  return TOKEN_LAW.find((rule) => rule.token === token) ?? null;
}

/** Whether `register` may reference `token`. An unknown token is refused, not allowed. */
export function tokenAllowedIn(token: string, register: Register): boolean {
  const rule = tokenRule(token);
  return rule?.registers.includes(register) ?? false;
}

// ── The ESLint fragment ──────────────────────────────────────────────────────────

/**
 * A `no-restricted-imports` pattern group, in the shape ESLint expects.
 * Declared structurally rather than imported from ESLint so this file keeps zero
 * dependencies and stays loadable by the flat config itself.
 */
export interface RestrictedPatternGroup {
  readonly group: readonly string[];
  readonly message: string;
}

export interface RegisterEslintConfig {
  readonly name: string;
  readonly files: readonly string[];
  readonly rules: {
    readonly 'no-restricted-imports': readonly [
      'error',
      { readonly patterns: readonly RestrictedPatternGroup[] },
    ];
  };
}

const globsFor = (law: RegisterLaw): readonly string[] => [
  ...law.directories.map((dir) => `${dir}/**/*.{ts,tsx}`),
  ...law.flatDirectories.map((dir) => `${dir}/*.{ts,tsx}`),
];

/**
 * The flat-config fragment `eslint.config.js` spreads.
 *
 * Returned as an array so the caller writes `...registerBoundaryConfigs()` and gets
 * every register at once — a caller who copies one entry and forgets another produces
 * a boundary with a hole, and the module-graph test would then be the only thing
 * standing between the console and a `motion` import inside the refusal screen.
 */
export function registerBoundaryConfigs(): readonly RegisterEslintConfig[] {
  return REGISTER_LAW.filter((law) => law.forbidden.length > 0).map((law) => {
    const patterns: RestrictedPatternGroup[] = [];
    if (law.forbidden.some((pattern) => GPU_PACKAGES.includes(pattern))) {
      patterns.push({
        group: GPU_PACKAGES,
        message:
          `${law.label} register: no GPU rendering. Only src/features/ancestry/render3d/** may ` +
          `import a 3D library (docs/leads/ui.md §1.1, D9).`,
      });
    }
    if (law.forbidden.some((pattern) => MOTION_PACKAGES.includes(pattern))) {
      patterns.push({
        group: MOTION_PACKAGES,
        message:
          `${law.label} register: nothing moves that a screenshot could not reproduce ` +
          `(docs/leads/ui.md §1.1). If the transition IS the fact, the component belongs in ` +
          `the INSTRUMENT register.`,
      });
    }
    if (law.register === 'evidence') {
      patterns.push({
        group: ['**/render3d/**'],
        message:
          'The MEMORY register is reachable only through a lazy import in the ancestry ' +
          'surface. Nothing else may depend on it — deleting render3d/ must leave a working ' +
          'ribbon (BUILD_PLAN §10.2, cut 1).',
      });
    }
    return {
      name: `mainline/register-${law.register}`,
      files: globsFor(law),
      rules: { 'no-restricted-imports': ['error', { patterns }] },
    };
  });
}
