// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ACCESSIBILITY LAW — `docs/leads/ui.md` D14, as data the build consumes.
 *
 * > *A safety product that a supervisor with a cracked screen and gloves cannot operate
 * > has an availability of zero regardless of uptime.*
 *
 * This file is the single source of truth for what "accessible" means in this console.
 * It is deliberately shaped like `src/design/registers.ts`: a law expressed as data,
 * rendered into `docs/accessibility.md` by `contract.doc.ts`, and cross-checked by
 * `tests/unit/a11y/contract.test.ts` against the rules `audit.ts` actually implements.
 *
 * ── THE ONE DISCIPLINE THAT MAKES THIS DIFFERENT FROM A CHECKLIST ────────────────
 *
 * Every law carries a `coverage` field, and `'unenforced'` is a legal value that is
 * REPORTED rather than hidden. An accessibility document whose every line reads "yes"
 * is a document nobody has measured. The gate is not "the list is all green"; the gate
 * is "nothing claims to be enforced that is not, and nothing that is enforced has a
 * blocking finding".
 *
 * That is the same rule the gate screen applies to a counter: a zero that was computed
 * and a zero that was never computed must not look alike.
 *
 * ── WHY THERE IS NO axe-core IMPORT ANYWHERE UNDER src/ ──────────────────────────
 *
 * `@axe-core/playwright` is a devDependency of this workspace, so axe runs in the
 * BROWSER tier. It is not resolvable from the unit tier: pnpm's strict `node_modules`
 * does not hoist `axe-core` itself, `package.json` belongs to the `console-foundation`
 * worker, and adding a dependency to another worker's manifest is not a thing this
 * worker may do. So `audit.ts` implements a documented SUBSET of the same rule set with
 * zero dependencies, and every rule axe would run that it does NOT run is listed by
 * `audit.ts`'s `notChecked` — visibly, in every report.
 */

import { type Register } from '../design/registers';

// ── Impact ───────────────────────────────────────────────────────────────────────

/**
 * The four impacts, in axe-core's vocabulary and in axe-core's order.
 *
 * The vocabulary is borrowed on purpose. D14 states the gate as "axe-core zero
 * serious/critical", and a bespoke severity scale would make that sentence unverifiable
 * against the browser tier, which really does run axe.
 */
export const IMPACTS = ['minor', 'moderate', 'serious', 'critical'] as const;

export type Impact = (typeof IMPACTS)[number];

/** The impacts D14 refuses to ship. A finding at or above `serious` fails the gate. */
export const BLOCKING_IMPACTS: readonly Impact[] = ['serious', 'critical'];

export function isBlocking(impact: Impact): boolean {
  return BLOCKING_IMPACTS.includes(impact);
}

/** Ordering, so a report can be sorted worst-first without a lookup table at the call site. */
export function impactRank(impact: Impact): number {
  return IMPACTS.indexOf(impact);
}

// ── Coverage ─────────────────────────────────────────────────────────────────────

/**
 * How a law is actually held up today. Four honest states, and only the first two are
 * claims that something in this repository will go red.
 *
 *   `enforced`            — a rule in `src/a11y/audit.ts` or a check in
 *                           `scripts/check-a11y.ts` fails when this law is broken, and
 *                           that failure is reachable from `pnpm test`.
 *   `enforced-elsewhere`  — another worker's committed test holds it. The file is named,
 *                           and `contract.test.ts` asserts the file exists, so a law
 *                           cannot point at a test that was deleted or never written.
 *   `browser-tier`        — it needs a real layout, a real accessibility tree or a real
 *                           keyboard, so it belongs to `tests/browser/a11y.spec.ts`.
 *                           That spec is owned by the `cinema-conformance-harness`
 *                           worker and had not landed when this file was written, so
 *                           this state means NOT YET MEASURED — never "fine".
 *   `unenforced`          — nothing checks it. Written down because an unmeasured
 *                           accessibility claim that nobody has recorded is the one that
 *                           gets made out loud.
 */
export const COVERAGE_STATES = [
  'enforced',
  'enforced-elsewhere',
  'browser-tier',
  'unenforced',
] as const;

export type Coverage = (typeof COVERAGE_STATES)[number];

/** The coverage states that mean "a red test exists in this repository today". */
export const MEASURED_COVERAGE: readonly Coverage[] = ['enforced', 'enforced-elsewhere'];

// ── The law ──────────────────────────────────────────────────────────────────────

export interface A11yLaw {
  /** Stable id. Referenced by `docs/accessibility.md` and by failure messages. */
  readonly id: string;
  /**
   * The law, as ONE testable sentence. If a sentence cannot fail a check, it is a value
   * statement and does not belong in this array — `contract.test.ts` refuses a law whose
   * coverage is `enforced` and whose `enforcedBy` names nothing that exists.
   */
  readonly statement: string;
  /** WCAG 2.2 success criteria this law carries, as `1.1.1` style numbers. */
  readonly wcag: readonly string[];
  /** The registers it binds. EVIDENCE surfaces carry the strictest set (ui.md §1.1). */
  readonly registers: readonly Register[];
  readonly coverage: Coverage;
  /**
   * Rule ids from `audit.ts`, check ids from `scripts/check-a11y.ts`, or repo-relative
   * paths of the committed test that holds the law. Never a promise, never a person.
   */
  readonly enforcedBy: readonly string[];
  /** The honest limit, where one exists. Rendered into the document verbatim. */
  readonly limit?: string;
}

const ALL_REGISTERS: readonly Register[] = ['evidence', 'instrument', 'memory'];
const EVIDENCE: readonly Register[] = ['evidence'];

/**
 * THE LAW. Ordered by how badly its violation would hurt the operator standing at the
 * gate, not by WCAG numbering.
 */
export const A11Y_LAW: readonly A11yLaw[] = [
  {
    id: 'every-control-is-named',
    statement:
      'Every control a reader can reach — button, link, field, tab, checkbox — exposes a non-empty accessible name, so that an operator using speech output is told what the control does before activating it.',
    wcag: ['1.1.1', '2.4.4', '4.1.2'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['control-name', 'img-alt', 'check-a11y:img-without-alt'],
  },
  {
    id: 'controls-are-real-controls',
    statement:
      'Interactive behaviour is attached to a native interactive element, never to a div with a click handler — because a div is not reachable by keyboard, is announced as nothing, and reimplementing it with a role and a key handler reimplements an element that already exists.',
    wcag: ['2.1.1', '4.1.2'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['check-a11y:click-handler-on-non-interactive'],
  },
  {
    id: 'keyboard-order-is-dom-order',
    statement:
      'No element carries a positive tabindex and none claims a single-character access key, so the order a screen reader reads a refusal in is the order a keyboard walks it in and no control silently captures a key an operator needs.',
    wcag: ['1.3.2', '2.4.3', '2.1.4'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['tabindex-positive', 'check-a11y:positive-tabindex', 'check-a11y:access-key'],
  },
  {
    id: 'nothing-focusable-is-hidden',
    statement:
      'No element inside an aria-hidden subtree is reachable by keyboard, so a keyboard user never lands on a control a screen reader has been told does not exist.',
    wcag: ['1.3.1', '4.1.2'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['focusable-inside-aria-hidden', 'check-a11y:aria-hidden-interactive'],
  },
  {
    id: 'a-refusal-is-announced',
    statement:
      'Every panel carrying a data-failure marker is inside a live region, so that a refusal reaches an operator who cannot see the screen at the moment it is refused.',
    wcag: ['4.1.3'],
    registers: EVIDENCE,
    coverage: 'enforced',
    enforcedBy: ['refusal-in-live-region'],
    limit:
      'Keyed on data-failure and deliberately NOT on data-sqlstate. A SQLSTATE also appears in records rather than announcements — an audit row, a custody entry, a past exposure receipt — and wrapping every one of them in a live region would announce every historical refusal on the screen assertively, which is how an operator learns to switch live regions off and then does not hear the one that mattered. The check also proves only that the markup is in a live region; whether the announcement was heard needs a real screen reader, and no automated tier here runs one.',
  },
  {
    id: 'a-refusal-is-never-paraphrased',
    statement:
      'What assistive technology is given for a constraint name, a SQLSTATE or a digest is the same string the eye is given — never a friendlier restatement and never a summary.',
    wcag: ['1.1.1', '4.1.2'],
    registers: EVIDENCE,
    coverage: 'enforced',
    enforcedBy: ['verbatim-is-text', 'src/a11y/announce.ts'],
    limit:
      'Enforced structurally: verbatim values render as selectable text in a code element, and the announcer refuses a message that is not the exact string it was given. A caller that builds a different string before calling it is out of reach of any automated check.',
  },
  {
    id: 'verbatim-is-selectable-text',
    statement:
      'Anything the database emitted is real, selectable text — never an image, never a canvas, never a CSS pseudo-element string — so it can be copied into a bug report or a court filing unchanged.',
    wcag: ['1.1.1', '1.4.5'],
    registers: EVIDENCE,
    coverage: 'enforced',
    enforcedBy: [
      'verbatim-is-text',
      'check-a11y:no-canvas-outside-memory',
      'check-a11y:verbatim-in-pseudo-element',
      'check-a11y:inner-html',
    ],
  },
  {
    id: 'severity-is-never-colour-alone',
    statement:
      'Severity, virulence and verification state are carried by text as well as by colour, so the meaning survives a monochrome print, a cracked screen and every form of colour vision.',
    wcag: ['1.4.1'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['severity-not-colour-alone'],
  },
  {
    id: 'contrast-floors-hold',
    statement:
      'Every foreground/background token pair the primitives actually use meets 4.5:1 for body text and 3:1 for large text and meaningful boundaries.',
    wcag: ['1.4.3', '1.4.11'],
    registers: ALL_REGISTERS,
    coverage: 'enforced-elsewhere',
    enforcedBy: ['tests/unit/design/contrast.test.ts'],
    limit:
      'Contrast is computed over the TOKEN SET, not over rendered pixels. jsdom has no cascade and no layout, so `audit.ts` does not attempt it and says so in every report it returns.',
  },
  {
    id: 'motion-is-refusable',
    statement:
      'Every transition is skipped under prefers-reduced-motion or a low-power signal, and the end state is identical either way.',
    wcag: ['2.3.3'],
    registers: ALL_REGISTERS,
    coverage: 'enforced-elsewhere',
    enforcedBy: ['tests/unit/design/motion.test.ts', 'src/design/motion.ts'],
  },
  {
    id: 'structure-is-real',
    statement:
      'Headings descend without skipping a level, lists contain only list items, ids are unique, and every aria reference resolves — so the structure a screen reader announces is the structure the screen has.',
    wcag: ['1.3.1', '2.4.6', '4.1.2'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: [
      'heading-order',
      'heading-empty',
      'list-structure',
      'duplicate-id',
      'aria-ref-resolves',
      'label-for-resolves',
    ],
  },
  {
    id: 'aria-is-valid',
    statement:
      'Every role and every aria-* attribute in the console is one that exists in ARIA 1.2; an invented one is a silent no-op that reads as a feature.',
    wcag: ['4.1.2'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['role-known', 'aria-attr-known', 'aria-attr-value'],
  },
  {
    id: 'nothing-moves-on-its-own',
    statement:
      'No element animates itself outside the motion policy — there is no marquee, no blink, and nothing that moves text a reader cannot stop.',
    wcag: ['2.2.2'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['no-marquee-or-blink'],
  },
  {
    id: 'landmarks-are-navigable',
    statement:
      'Each document has exactly one main landmark, and repeated landmarks of the same kind carry distinct accessible names, so a screen-reader user can jump between regions rather than reading through them.',
    wcag: ['1.3.1', '2.4.1'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['main-landmark', 'landmark-unique-name', 'region-name'],
  },
  {
    id: 'no-name-in-the-memory-register',
    statement:
      'No person is identified anywhere in the MEMORY register, and signer_sub is never a colour, an axis, a facet or a sort key in any register (D15 / I15 / the Attribution Rule).',
    wcag: [],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['no-person-in-memory', 'signer-sub-is-not-a-dimension', 'check-a11y:signer-sub'],
    limit:
      'This is a dignity rule carried into the a11y gate because a screenshot outlives a schema. The DOM rules catch the marked forms; a name pasted into a literal string is caught by the corpus discipline, not by this checker.',
  },
  {
    id: 'the-gate-to-signature-path-is-keyboard-only',
    statement:
      'The complete path from the refusal to the signature — refusal, precursor list, disposition, defeater, reading floor, signature — is operable with a keyboard alone, in that order, with no pointer-only step.',
    wcag: ['2.1.1', '2.1.2', '2.4.3'],
    registers: EVIDENCE,
    coverage: 'browser-tier',
    enforcedBy: ['tests/browser/a11y.spec.ts', 'KEYBOARD_TRAVERSAL'],
    limit:
      'NOT YET MEASURED. The traversal is declared here as data and `verifyTraversal()` checks any observed order against it, but the observation requires a real browser. `tests/browser/a11y.spec.ts` and `playwright.config.ts` belong to the cinema-conformance-harness worker and had not landed when this file was written.',
  },
  {
    id: 'a-focus-ring-is-always-visible',
    statement:
      'Every element that can receive keyboard focus shows a focus indicator that meets the 3:1 non-text contrast floor and is never removed by a stylesheet.',
    wcag: ['2.4.7', '2.4.11', '1.4.11'],
    registers: ALL_REGISTERS,
    coverage: 'enforced',
    enforcedBy: ['check-a11y:focus-visible-outline'],
    limit:
      'The static check refuses `outline: none` inside a `:focus-visible` selector, which is the form that actually blinds a keyboard user. `:focus { outline: none }` on a programmatic focus target (a `tabindex="-1"` main landmark) is legitimate and is reported as a note, not a failure — CSS alone cannot tell the two apart, and a gate that fails a legitimate pattern is a gate that gets deleted.',
  },
  {
    id: 'the-exhibit-prints',
    statement:
      'Every EVIDENCE surface prints to a court-legible page with its caption block, and the ancestry ribbon prints to A3.',
    wcag: [],
    registers: EVIDENCE,
    coverage: 'browser-tier',
    enforcedBy: ['tests/browser/a11y.spec.ts'],
    limit:
      'NOT YET MEASURED here. The ancestry worker asserts the A3 exhibit in its own suite; a console-wide print assertion needs a browser.',
  },
  {
    id: 'no-fact-is-three-dimensional-only',
    statement:
      'Every node and edge drawn in the MEMORY register also exists in the ribbon DOM, so the dimensional walk is optional and the accessible path loses no fact.',
    wcag: ['1.1.1', '1.3.1'],
    registers: ALL_REGISTERS,
    coverage: 'enforced-elsewhere',
    enforcedBy: ['tests/unit/ancestry-3d/projection.test.ts'],
  },
];

export function lawById(id: string): A11yLaw | null {
  return A11Y_LAW.find((law) => law.id === id) ?? null;
}

/** Every enforcement token any law names, deduplicated. */
export function enforcementTokens(): readonly string[] {
  return [...new Set(A11Y_LAW.flatMap((law) => law.enforcedBy))].sort();
}

// ── The keyboard traversal (D14) ─────────────────────────────────────────────────

export interface TraversalStep {
  /** Stable id, and the value the surface puts in `data-traversal` on the landing element. */
  readonly id: string;
  /** The surface that owns this step, matching `src/app/surfaces.ts`'s ids. */
  readonly surface: string;
  /** What the operator is doing here, in the operator's words. */
  readonly action: string;
  /**
   * Whether reaching this step is allowed to require anything other than Tab / Shift+Tab
   * / Enter / Space / arrow keys. Always `false`: a pointer-only step in this path is the
   * failure D14 exists to refuse.
   */
  readonly pointerOnly: false;
}

/**
 * THE PATH THAT MUST WORK WITH A KEYBOARD ALONE.
 *
 * `docs/leads/ui.md` D14: *a complete keyboard-only path gate → disposition → signature*.
 * Declared here as data so that the browser spec, when it lands, asserts against the
 * same list this document is generated from rather than against a copy of it.
 */
export const KEYBOARD_TRAVERSAL: readonly TraversalStep[] = [
  {
    id: 'refusal',
    surface: 'gate',
    action: 'read the constraint name and the SQLSTATE the database reported',
    pointerOnly: false,
  },
  {
    id: 'minimal-unsatisfiable-subset',
    surface: 'gate',
    action: 'walk the minimal unsatisfiable subset, one clause at a time',
    pointerOnly: false,
  },
  {
    id: 'precursors',
    surface: 'gate',
    action: 'open a blocking precursor and read its origin and evidence summary',
    pointerOnly: false,
  },
  {
    id: 'disposition-open',
    surface: 'disposition',
    action: 'open the disposition for that precursor',
    pointerOnly: false,
  },
  {
    id: 'defeater',
    surface: 'disposition',
    action: 'choose a defeater from the per-check vocabulary',
    pointerOnly: false,
  },
  {
    id: 'reading-floor',
    surface: 'disposition',
    action: 'read the reading-floor meter and its consequence',
    pointerOnly: false,
  },
  {
    id: 'signature',
    surface: 'disposition',
    action: 'reach the signature control and submit',
    pointerOnly: false,
  },
];

export interface TraversalResult {
  readonly ok: boolean;
  /** Steps the observed order never reached, in declaration order. */
  readonly missing: readonly string[];
  /** Steps reached out of order, as `expected → observed` pairs. */
  readonly outOfOrder: readonly string[];
  /** Steps observed that the contract has never heard of. */
  readonly unknown: readonly string[];
  /** One sentence, safe to render verbatim in a failure message. */
  readonly message: string;
}

/**
 * Checks an OBSERVED tab order against `KEYBOARD_TRAVERSAL`.
 *
 * The observed sequence is allowed to contain steps this contract does not name — a
 * surface has many controls and only some of them are on the certified path — but it
 * MUST contain every named step, and it must contain them in the declared order.
 * Extra ids are reported rather than ignored, because an id that nobody declared is
 * usually a renamed step, and silently accepting it is how a traversal test rots.
 */
export function verifyTraversal(
  observed: readonly string[],
  contract: readonly TraversalStep[] = KEYBOARD_TRAVERSAL,
): TraversalResult {
  const declared = contract.map((step) => step.id);
  const declaredSet = new Set(declared);

  const missing = declared.filter((id) => !observed.includes(id));
  const unknown = [...new Set(observed.filter((id) => !declaredSet.has(id)))];

  const positions = declared
    .filter((id) => observed.includes(id))
    .map((id) => ({ id, at: observed.indexOf(id) }));

  const outOfOrder: string[] = [];
  for (let index = 1; index < positions.length; index += 1) {
    const previous = positions[index - 1];
    const current = positions[index];
    if (previous === undefined || current === undefined) continue;
    if (current.at < previous.at) {
      outOfOrder.push(`${previous.id} → ${current.id}`);
    }
  }

  const ok = missing.length === 0 && outOfOrder.length === 0;
  const parts: string[] = [];
  if (missing.length > 0) parts.push(`never reached: ${missing.join(', ')}`);
  if (outOfOrder.length > 0) parts.push(`reached out of order: ${outOfOrder.join('; ')}`);
  if (unknown.length > 0) parts.push(`observed but not declared: ${unknown.join(', ')}`);

  return {
    ok,
    missing,
    outOfOrder,
    unknown,
    message: ok
      ? `The keyboard-only path is intact: ${declared.join(' → ')}.`
      : `The keyboard-only path from the refusal to the signature is broken — ${parts.join('; ')} ` +
        `(docs/leads/ui.md D14).`,
  };
}

// ── Per-surface operations ───────────────────────────────────────────────────────

export interface SurfaceOperations {
  /** Matches an id in `src/app/surfaces.ts`'s `DECLARED_SURFACES`. */
  readonly surface: string;
  /**
   * What an operator must be able to do on this surface using a keyboard alone and a
   * screen reader alone. One entry per operation, each phrased so a browser spec could
   * attempt it.
   */
  readonly operations: readonly string[];
}

/**
 * One row per declared surface. `contract.test.ts` asserts this list and
 * `DECLARED_SURFACES` are in exact bijection, so a surface cannot be promised without
 * somebody writing down what it means to operate it without a mouse or a screen.
 */
export const SURFACE_OPERATIONS: readonly SurfaceOperations[] = [
  {
    surface: 'gate',
    operations: [
      'Hear the constraint name and the SQLSTATE, character by character on demand, as the database emitted them.',
      'Walk the minimal unsatisfiable subset item by item and hear each provenance chip.',
      'Reach every non-zero counter and follow it to its witness rows.',
      'Distinguish a counter that is zero from a counter that was never computed, by text.',
      'Open the clause diff and read both sides in the mono face.',
    ],
  },
  {
    surface: 'ancestry',
    operations: [
      'Walk from the current clause to the terminal event using arrow keys alone.',
      'Hear each node as a list item with its date, kind and severity in text.',
      'Hear that a closure is truncated, and by which generation, without seeing the graphic.',
      'Hear that an edge is inferred rather than declared.',
      'Print the ribbon exhibit with its caption block.',
    ],
  },
  {
    surface: 'disposition',
    operations: [
      'Reach every required field in DOM order, with each field announcing the projected column that required it.',
      'Choose a defeater from the per-check vocabulary without a pointer.',
      'Hear the reading-floor meter as a measurement, never as a judgement about the person.',
      'Hear the consequence of an unmet floor as a fact, in text.',
      'Reach and operate the signature control.',
    ],
  },
  {
    surface: 'custody',
    operations: [
      'Hear each verification seal as verified, failed or unverified, in words, never as a colour.',
      'Read the bytes hashed and the digest produced for any recomputed claim.',
      'Hear the split-view honest limit sentence in full.',
    ],
  },
  {
    surface: 'audit',
    operations: [
      'Read every audit view as a real table with header cells.',
      'Hear the truncation flag on any row whose ancestry is incomplete.',
      'Read the row and byte caps each query ran under.',
    ],
  },
  {
    surface: 'propagation',
    operations: [
      'Reach a declined lesson with the same number of keystrokes as an adopted one.',
      'Hear the declination kind and its predicate in text.',
      'Hear an open merge conflict and its base, ours and theirs digests.',
    ],
  },
  {
    surface: 'silence',
    operations: [
      'Read the conservation identity as an arithmetic line that balances.',
      'Hear every score together with its threshold and its policy version.',
      'Hear the PER honest-limit sentence in full.',
    ],
  },
];

export function operationsFor(surface: string): SurfaceOperations | null {
  return SURFACE_OPERATIONS.find((entry) => entry.surface === surface) ?? null;
}
