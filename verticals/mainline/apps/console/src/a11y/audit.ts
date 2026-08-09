// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE DOM ACCESSIBILITY AUDITOR — D14's gate, running in the unit tier.
 *
 * `docs/leads/ui.md` D14: *axe-core zero serious/critical on all six surfaces*. That is
 * the browser tier's assertion and it needs a browser. This file is the half that runs
 * on every `pnpm test`: a dependency-free auditor over a jsdom tree, implementing a
 * documented subset of the same rules, plus five rules axe does not have because they
 * are about THIS product.
 *
 * ── THE FIVE RULES THAT ARE NOT IN ANY GENERIC CHECKER ───────────────────────────
 *
 *   `verbatim-is-text`             a claim carrying a provenance chip may not be an
 *                                  image, a canvas or an SVG — a value the reader cannot
 *                                  select is a value the medium paraphrased (ui.md §1.1)
 *   `severity-not-colour-alone`    a severity band must carry text, so the meaning
 *                                  survives a monochrome print and a mine-site screen
 *   `refusal-in-live-region`       a refusal an operator cannot hear did not happen for
 *                                  that operator
 *   `no-person-in-memory`          no person is identified in the MEMORY register (D15)
 *   `signer-sub-is-not-a-dimension` signer_sub is never a colour, axis, facet or sort key
 *
 * ── WHAT THIS AUDITOR DOES NOT CHECK, IN WRITING, IN EVERY REPORT ────────────────
 *
 * `A11yReport.notChecked` is not documentation; it is a field of the returned object,
 * and `assertAccessible()` prints it on failure AND on the summary it returns. A report
 * that lists only what it found reads as a clearance. This one cannot: colour contrast,
 * focus visibility, reflow, target size and reading order all require a cascade and a
 * layout, and jsdom has neither. Each is named, with the file that does cover it where
 * one exists.
 *
 * That field is the difference between an audit and a rubber stamp, and it is the same
 * discipline the gate screen applies to `unmodelled_asset_count`: an unknown is reported
 * as an unknown, never folded into a zero.
 */

import { accessibleName, isAriaHidden, visibleTextContent } from './accname';
import { type Impact, impactRank, isBlocking } from './contract';
import { isDisabled, isTabbable, tabindexOf } from './focus';
import {
  ARIA_ATTRIBUTES,
  ARIA_BOOLEAN_ATTRIBUTES,
  ARIA_ENUMERATED_VALUES,
  ARIA_ID_REFERENCES,
  ARIA_ID_REFERENCE_LISTS,
  ARIA_ROLES,
  IMPLICIT_LANDMARKS,
  LABELABLE_ELEMENTS,
  LANDMARK_ROLES,
  LIVE_REGION_ROLES,
  NAME_REQUIRED_ROLES,
} from './roles';

// ── The report ───────────────────────────────────────────────────────────────────

export interface A11yFinding {
  readonly ruleId: string;
  readonly impact: Impact;
  /** What is wrong, in one sentence, naming the element. */
  readonly message: string;
  /** What to do about it. Written for the worker who has to fix it. */
  readonly help: string;
  /** A CSS-ish path to the element, stable enough to grep for. */
  readonly target: string;
  /** The element's opening tag, truncated. Never the whole subtree. */
  readonly snippet: string;
  readonly wcag: readonly string[];
}

export interface A11yReport {
  readonly findings: readonly A11yFinding[];
  /** Findings at `serious` or `critical`. D14's gate is that this array is empty. */
  readonly blocking: readonly A11yFinding[];
  readonly counts: Readonly<Record<Impact, number>>;
  readonly elementsChecked: number;
  /** Every rule ids this run executed, so an empty report can be told from an empty run. */
  readonly rulesRun: readonly string[];
  /** What no rule here can see. Rendered on every failure and every summary. */
  readonly notChecked: readonly string[];
}

/**
 * The honest limits. Every entry names the check that DOES cover it, or says that
 * nothing does.
 */
export const NOT_CHECKED_HERE: readonly string[] = [
  'Colour contrast — needs a cascade and computed colours. Covered over the token set by tests/unit/design/contrast.test.ts.',
  'Focus indicator visibility — needs computed styles. Covered in source form by scripts/check-a11y.ts (focus-visible-outline); the rendered ring is browser-tier.',
  'Reflow, zoom and text spacing (WCAG 1.4.10, 1.4.12) — need layout. NOTHING covers these today.',
  'Target size (WCAG 2.5.8) — needs layout. NOTHING covers this today.',
  'Reading order versus visual order — needs layout. The DOM order is asserted; the painted order is not.',
  'Whether a screen reader actually announces a live region — no automated tier in this repository runs one.',
  'Motion and prefers-reduced-motion — covered by tests/unit/design/motion.test.ts and src/design/motion.ts.',
  'Elements hidden by a CSS class rather than by the DOM — jsdom has no cascade, so such an element is audited as though it were visible.',
];

// ── Rule plumbing ────────────────────────────────────────────────────────────────

interface RuleContext {
  readonly root: ParentNode;
  readonly elements: readonly Element[];
  readonly document: Document;
  readonly expectMain: boolean;
}

interface AuditRule {
  readonly id: string;
  readonly impact: Impact;
  readonly help: string;
  readonly wcag: readonly string[];
  readonly run: (context: RuleContext) => readonly RawFinding[];
}

interface RawFinding {
  readonly element: Element | null;
  readonly message: string;
}

function tagOf(element: Element): string {
  return element.tagName.toLowerCase();
}

function roleTokens(element: Element): readonly string[] {
  const raw = element.getAttribute('role');
  return raw === null ? [] : raw.split(/\s+/).filter((token) => token !== '');
}

/** The element's explicit role, or the implicit one this auditor knows about. */
function effectiveRole(element: Element): string | null {
  const explicit = roleTokens(element)[0];
  if (explicit !== undefined) return explicit;

  const tag = tagOf(element);
  const landmark = IMPLICIT_LANDMARKS[tag];
  if (landmark !== undefined) {
    // <header>/<footer> are only landmarks at the top level. Inside <article>/<section>
    // they are not, and demanding a name from every card footer would bury the report.
    if ((tag === 'header' || tag === 'footer') && element.closest('article, section, aside, nav, main') !== null) {
      return null;
    }
    return landmark;
  }
  if (tag === 'a' && element.hasAttribute('href')) return 'link';
  if (tag === 'button') return 'button';
  if (tag === 'select') return 'combobox';
  if (tag === 'textarea') return 'textbox';
  if (/^h[1-6]$/.test(tag)) return 'heading';
  if (tag === 'input') {
    const type = (element.getAttribute('type') ?? 'text').toLowerCase();
    if (type === 'checkbox') return 'checkbox';
    if (type === 'radio') return 'radio';
    if (type === 'button' || type === 'submit' || type === 'reset' || type === 'image') return 'button';
    if (type === 'range') return 'slider';
    if (type === 'number') return 'spinbutton';
    if (type === 'hidden') return null;
    if (type === 'search') return 'searchbox';
    return 'textbox';
  }
  return null;
}

/** A short, greppable path: `div.shell > main#main > section[role=alert]`. */
export function targetPath(element: Element): string {
  const parts: string[] = [];
  let current: Element | null = element;
  let depth = 0;
  while (current !== null && depth < 4) {
    let part = tagOf(current);
    const id = current.getAttribute('id');
    if (id !== null && id !== '') part += `#${id}`;
    const testId = current.getAttribute('data-testid');
    if (testId !== null && testId !== '') part += `[data-testid=${testId}]`;
    const role = current.getAttribute('role');
    if (role !== null && role !== '') part += `[role=${role}]`;
    parts.unshift(part);
    current = current.parentElement;
    depth += 1;
  }
  return parts.join(' > ');
}

/** The opening tag only, capped. A finding that pastes a whole subtree is unreadable. */
export function snippetOf(element: Element): string {
  const html = element.outerHTML;
  const openingEnd = html.indexOf('>');
  const opening = openingEnd < 0 ? html : html.slice(0, openingEnd + 1);
  return opening.length > 180 ? `${opening.slice(0, 177)}...` : opening;
}

// ── The rules ────────────────────────────────────────────────────────────────────

const RULE_LIST: readonly AuditRule[] = [
  {
    id: 'img-alt',
    impact: 'critical',
    wcag: ['1.1.1'],
    help:
      'Give the image an `alt`. If it carries no information, `alt=""` is the correct answer and ' +
      'says so explicitly; a MISSING alt makes a screen reader read the file name.',
    run: ({ elements }) =>
      elements
        .filter((element) => tagOf(element) === 'img' && !element.hasAttribute('alt'))
        .filter((element) => !isAriaHidden(element))
        .map((element) => ({
          element,
          message: `<img> has no alt attribute (src=${element.getAttribute('src') ?? 'none'}).`,
        })),
  },
  {
    id: 'control-name',
    impact: 'critical',
    wcag: ['4.1.2', '2.4.4'],
    help:
      'Give the control an accessible name: visible text, `aria-label`, `aria-labelledby`, or a ' +
      '`<label for>`. A control with no name is announced as "button" and nothing else.',
    run: ({ elements }) =>
      elements
        .filter((element) => {
          const role = effectiveRole(element);
          if (role === null || !NAME_REQUIRED_ROLES.has(role)) return false;
          if (isAriaHidden(element)) return false;
          if (isDisabled(element)) return false;
          return accessibleName(element) === '';
        })
        .map((element) => ({
          element,
          message: `<${tagOf(element)}> with role "${effectiveRole(element) ?? 'none'}" has no accessible name.`,
        })),
  },
  {
    id: 'heading-empty',
    impact: 'serious',
    wcag: ['1.3.1', '2.4.6'],
    help: 'Remove the heading or give it text. An empty heading is a landmark that leads nowhere.',
    run: ({ elements }) =>
      elements
        .filter((element) => /^h[1-6]$/.test(tagOf(element)) || roleTokens(element).includes('heading'))
        .filter((element) => !isAriaHidden(element) && accessibleName(element) === '')
        .map((element) => ({ element, message: `<${tagOf(element)}> is an empty heading.` })),
  },
  {
    id: 'heading-order',
    impact: 'moderate',
    wcag: ['1.3.1'],
    help:
      'Descend one level at a time. A jump from h2 to h4 tells a screen-reader user a section is ' +
      'missing, and they will go looking for it.',
    run: ({ root }) => {
      const headings = [...root.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]')].filter(
        (element) => !isAriaHidden(element),
      );
      const findings: RawFinding[] = [];
      let previous: number | null = null;
      for (const heading of headings) {
        const explicit = heading.getAttribute('aria-level');
        const level =
          explicit !== null
            ? Number.parseInt(explicit, 10)
            : Number.parseInt(tagOf(heading).slice(1), 10);
        if (Number.isNaN(level)) continue;
        if (previous !== null && level > previous + 1) {
          findings.push({
            element: heading,
            message: `heading level jumps from ${previous} to ${level}.`,
          });
        }
        previous = level;
      }
      return findings;
    },
  },
  {
    id: 'duplicate-id',
    impact: 'serious',
    wcag: ['4.1.1', '1.3.1'],
    help:
      'Make the id unique. `aria-labelledby`, `aria-describedby` and `<label for>` all resolve to ' +
      'the FIRST match, so a duplicate silently gives two controls the same label.',
    run: ({ elements }) => {
      const byId = new Map<string, Element[]>();
      for (const element of elements) {
        const id = element.getAttribute('id');
        if (id === null || id === '') continue;
        const bucket = byId.get(id);
        if (bucket === undefined) byId.set(id, [element]);
        else bucket.push(element);
      }
      return [...byId.entries()]
        .filter(([, group]) => group.length > 1)
        .map(([id, group]) => ({
          element: group[1] ?? null,
          message: `id "${id}" appears ${group.length} times.`,
        }));
    },
  },
  {
    id: 'aria-attr-known',
    impact: 'critical',
    wcag: ['4.1.2'],
    help:
      'Fix the spelling, or delete the attribute. An unknown `aria-*` attribute is not an error in ' +
      'any browser — it is silently ignored, and the control ships with no name at all.',
    run: ({ elements }) => {
      const findings: RawFinding[] = [];
      for (const element of elements) {
        for (const attribute of element.attributes) {
          const name = attribute.name.toLowerCase();
          if (!name.startsWith('aria-')) continue;
          if (!ARIA_ATTRIBUTES.has(name)) {
            findings.push({ element, message: `"${name}" is not an ARIA 1.2 attribute.` });
          }
        }
      }
      return findings;
    },
  },
  {
    id: 'aria-attr-value',
    impact: 'serious',
    wcag: ['4.1.2'],
    help: 'Use one of the values ARIA defines for this attribute; anything else is ignored.',
    run: ({ elements }) => {
      const findings: RawFinding[] = [];
      for (const element of elements) {
        for (const name of ARIA_BOOLEAN_ATTRIBUTES) {
          const value = element.getAttribute(name);
          if (value === null) continue;
          if (value !== 'true' && value !== 'false') {
            findings.push({ element, message: `${name}="${value}" — expected "true" or "false".` });
          }
        }
        for (const [name, permitted] of Object.entries(ARIA_ENUMERATED_VALUES)) {
          const value = element.getAttribute(name);
          if (value === null) continue;
          if (!permitted.includes(value)) {
            findings.push({
              element,
              message: `${name}="${value}" — expected one of ${permitted.join(', ')}.`,
            });
          }
        }
      }
      return findings;
    },
  },
  {
    id: 'aria-ref-resolves',
    impact: 'serious',
    wcag: ['1.3.1', '4.1.2'],
    help:
      'Point the reference at an element that exists. A dangling `aria-labelledby` is the same as ' +
      'no label, and it LOOKS like a label in review.',
    run: ({ elements, document }) => {
      const findings: RawFinding[] = [];
      const exists = (id: string): boolean => document.getElementById(id) !== null;
      for (const element of elements) {
        for (const name of ARIA_ID_REFERENCE_LISTS) {
          const value = element.getAttribute(name);
          if (value === null) continue;
          for (const id of value.split(/\s+/).filter((token) => token !== '')) {
            if (!exists(id)) {
              findings.push({ element, message: `${name} references "${id}", which is not in the document.` });
            }
          }
        }
        for (const name of ARIA_ID_REFERENCES) {
          const value = element.getAttribute(name);
          if (value === null || value === '') continue;
          if (!exists(value)) {
            findings.push({ element, message: `${name} references "${value}", which is not in the document.` });
          }
        }
      }
      return findings;
    },
  },
  {
    id: 'role-known',
    impact: 'serious',
    wcag: ['4.1.2'],
    help: 'Use a role from ARIA 1.2, or remove the attribute and let the native semantics stand.',
    run: ({ elements }) => {
      const findings: RawFinding[] = [];
      for (const element of elements) {
        for (const token of roleTokens(element)) {
          if (!ARIA_ROLES.has(token)) {
            findings.push({ element, message: `role="${token}" is not an ARIA 1.2 role.` });
          }
        }
      }
      return findings;
    },
  },
  {
    id: 'tabindex-positive',
    impact: 'serious',
    wcag: ['2.4.3'],
    help:
      'Use `tabindex="0"` and put the element where it belongs in the DOM. A positive tabindex ' +
      'jumps the whole document queue, so the order a screen reader reads in stops matching the ' +
      'order a keyboard walks in.',
    run: ({ elements }) =>
      elements
        .filter((element) => {
          const value = tabindexOf(element);
          return value !== null && value > 0;
        })
        .map((element) => ({
          element,
          message: `tabindex="${element.getAttribute('tabindex') ?? ''}" is positive.`,
        })),
  },
  {
    id: 'focusable-inside-aria-hidden',
    impact: 'critical',
    wcag: ['1.3.1', '4.1.2'],
    help:
      'Either remove `aria-hidden` or make the element unreachable (`tabindex="-1"`, `disabled`, ' +
      'or `inert`). A keyboard user can land on a control that speech output insists is not there.',
    run: ({ elements }) =>
      elements
        .filter((element) => isTabbable(element) && isAriaHidden(element))
        .map((element) => ({
          element,
          message: `<${tagOf(element)}> is keyboard-reachable inside an aria-hidden subtree.`,
        })),
  },
  {
    id: 'list-structure',
    impact: 'serious',
    wcag: ['1.3.1'],
    help:
      'Put only `<li>` inside `<ul>`/`<ol>`. A stray element breaks the "list of 7 items" ' +
      'announcement that is the only reason the list markup is there.',
    run: ({ elements }) => {
      const findings: RawFinding[] = [];
      const allowed: Readonly<Record<string, readonly string[]>> = {
        ul: ['li', 'script', 'template'],
        ol: ['li', 'script', 'template'],
        dl: ['dt', 'dd', 'div', 'script', 'template'],
      };
      for (const element of elements) {
        const permitted = allowed[tagOf(element)];
        if (permitted === undefined) continue;
        for (const child of element.children) {
          if (!permitted.includes(tagOf(child))) {
            findings.push({
              element: child,
              message: `<${tagOf(child)}> is a direct child of <${tagOf(element)}>; only ${permitted.join(', ')} are permitted.`,
            });
          }
        }
      }
      return findings;
    },
  },
  {
    id: 'label-for-resolves',
    impact: 'serious',
    wcag: ['1.3.1', '3.3.2'],
    help:
      'Point `for=` at the id of a form control that exists. A label bound to nothing is a label ' +
      'that reviews as present and announces as absent.',
    run: ({ elements, document }) =>
      elements
        .filter((element) => tagOf(element) === 'label' && element.hasAttribute('for'))
        .flatMap((element) => {
          const id = element.getAttribute('for') ?? '';
          const target = id === '' ? null : document.getElementById(id);
          if (target === null) {
            return [{ element, message: `<label for="${id}"> targets no element in the document.` }];
          }
          if (!LABELABLE_ELEMENTS.has(tagOf(target))) {
            return [
              {
                element,
                message: `<label for="${id}"> targets a <${tagOf(target)}>, which is not a labelable element.`,
              },
            ];
          }
          return [];
        }),
  },
  {
    id: 'main-landmark',
    impact: 'moderate',
    wcag: ['1.3.1', '2.4.1'],
    help:
      'Give the document exactly one main landmark. Two is ambiguous and zero removes the single ' +
      'most-used screen-reader shortcut on the page.',
    run: ({ root, expectMain }) => {
      if (!expectMain) return [];
      const mains = [...root.querySelectorAll('main, [role=main]')].filter(
        (element) => !isAriaHidden(element),
      );
      if (mains.length === 1) return [];
      return [
        {
          element: mains[0] ?? null,
          message:
            mains.length === 0
              ? 'the document has no main landmark.'
              : `the document has ${mains.length} main landmarks.`,
        },
      ];
    },
  },
  {
    id: 'landmark-unique-name',
    impact: 'moderate',
    wcag: ['1.3.1', '2.4.1'],
    help:
      'Give each repeated landmark an `aria-label` naming what it contains. Two navigations both ' +
      'announced as "navigation" cannot be told apart from the landmark list.',
    run: ({ root }) => {
      const byRole = new Map<string, Element[]>();
      for (const element of root.querySelectorAll('*')) {
        const role = effectiveRole(element);
        if (role === null || !LANDMARK_ROLES.has(role)) continue;
        if (isAriaHidden(element)) continue;
        const bucket = byRole.get(role);
        if (bucket === undefined) byRole.set(role, [element]);
        else bucket.push(element);
      }
      const findings: RawFinding[] = [];
      for (const [role, group] of byRole) {
        if (group.length < 2) continue;
        const names = group.map(accessibleName);
        const duplicated = names.filter((name, index) => names.indexOf(name) !== index);
        for (const [index, element] of group.entries()) {
          const name = names[index] ?? '';
          if (name === '' || duplicated.includes(name)) {
            findings.push({
              element,
              message:
                name === ''
                  ? `one of ${group.length} "${role}" landmarks has no accessible name.`
                  : `two "${role}" landmarks share the name "${name}".`,
            });
          }
        }
      }
      return findings;
    },
  },
  {
    id: 'region-name',
    impact: 'moderate',
    wcag: ['1.3.1'],
    help:
      'Name the region with `aria-label` or `aria-labelledby`, or drop `role="region"`. An unnamed ' +
      'region is announced as "region" and adds a stop to the landmark list for no information.',
    run: ({ elements }) =>
      elements
        .filter((element) => roleTokens(element).includes('region'))
        .filter((element) => !isAriaHidden(element) && accessibleName(element) === '')
        .map((element) => ({ element, message: 'role="region" with no accessible name.' })),
  },
  {
    id: 'no-marquee-or-blink',
    impact: 'serious',
    wcag: ['2.2.2'],
    help: 'Delete it. Moving text that cannot be paused fails 2.2.2 and has no place on an exhibit.',
    run: ({ elements }) =>
      elements
        .filter((element) => tagOf(element) === 'marquee' || tagOf(element) === 'blink')
        .map((element) => ({ element, message: `<${tagOf(element)}> is present.` })),
  },

  // ── The five MAINLINE rules ────────────────────────────────────────────────────

  {
    id: 'verbatim-is-text',
    impact: 'critical',
    wcag: ['1.1.1', '1.4.5'],
    help:
      'Render the value as text in a `<code>` element (src/design/primitives/Mono.tsx). A verbatim ' +
      'value a reader cannot select is a verbatim value the medium paraphrased — and it cannot be ' +
      'pasted into a bug report, a filing or a grep of the schema.',
    run: ({ elements }) =>
      elements
        .filter((element) => element.hasAttribute('data-provenance'))
        .filter((element) => ['img', 'canvas', 'svg', 'picture', 'video'].includes(tagOf(element)))
        .map((element) => ({
          element,
          message: `a claim with provenance "${element.getAttribute('data-provenance') ?? ''}" is rendered as <${tagOf(element)}>, not as text.`,
        })),
  },
  {
    id: 'severity-not-colour-alone',
    impact: 'serious',
    wcag: ['1.4.1'],
    help:
      'Add the severity as text — visible, or in a visually-hidden span if the layout is already ' +
      'carrying it. Colour is not available to every reader, to a monochrome print, or to a court ' +
      'exhibit photocopied twice.',
    run: ({ elements }) =>
      elements
        .filter((element) => element.hasAttribute('data-severity'))
        .filter((element) => !isAriaHidden(element))
        .filter((element) => {
          const text = `${visibleTextContent(element)} ${accessibleName(element)}`;
          return !/[a-z]/i.test(text);
        })
        .map((element) => ({
          element,
          message: `data-severity="${element.getAttribute('data-severity') ?? ''}" is carried by colour alone — the element exposes no text.`,
        })),
  },
  {
    id: 'refusal-in-live-region',
    impact: 'serious',
    wcag: ['4.1.3'],
    help:
      'Put the refusal inside `role="alert"` (or an `aria-live` region). A refusal an operator ' +
      'cannot hear is a refusal that did not happen for that operator, and this product is a ' +
      'refusal.',
    /**
     * Keyed on `data-failure` and NOT on `data-sqlstate`.
     *
     * `data-failure` is the marker a surface puts on the panel that says *the console is
     * reporting a failure right now* — the shell's no-such-surface card, the error
     * boundary, the refusal bar. That is an announcement.
     *
     * `data-sqlstate` is a verbatim VALUE, and it appears in places that are records
     * rather than announcements: a row in the audit surface, a past refusal in the
     * custody chain, a column in a table of exposure receipts. Requiring a live region
     * around every one of them would announce every historical SQLSTATE on the screen
     * assertively, which is precisely how an operator learns to turn live regions off —
     * and then does not hear the one that mattered. The verbatim value is covered by
     * `verbatim-is-text`; the announcement is covered here.
     */
    run: ({ elements }) =>
      elements
        .filter((element) => element.hasAttribute('data-failure'))
        .filter((element) => {
          let current: Element | null = element;
          while (current !== null) {
            if (current.hasAttribute('aria-live')) return false;
            if (roleTokens(current).some((token) => LIVE_REGION_ROLES.has(token))) return false;
            current = current.parentElement;
          }
          return true;
        })
        .map((element) => ({
          element,
          message: `a refusal panel (data-failure="${element.getAttribute('data-failure') ?? ''}") is outside any live region.`,
        })),
  },
  {
    id: 'no-person-in-memory',
    impact: 'critical',
    wcag: [],
    help:
      'Remove the person. `docs/leads/ui.md` D15 and ARCHITECTURE §11.5: events carry titles and ' +
      'severities; people do not appear in the MEMORY register. A screenshot outlives a schema.',
    run: ({ root }) => {
      const findings: RawFinding[] = [];
      const personAttributes = ['data-person', 'data-signer', 'data-signer-sub', 'data-name'];
      for (const memory of root.querySelectorAll('[data-register="memory"]')) {
        const scope = [memory, ...memory.querySelectorAll('*')];
        for (const element of scope) {
          for (const attribute of personAttributes) {
            if (element.hasAttribute(attribute)) {
              findings.push({
                element,
                message: `${attribute} inside a MEMORY-register subtree identifies a person.`,
              });
            }
          }
        }
      }
      return findings;
    },
  },
  {
    id: 'signer-sub-is-not-a-dimension',
    impact: 'critical',
    wcag: [],
    help:
      'Choose another dimension. `signer_sub` may never be a colour, an axis, a facet or a sort ' +
      'key anywhere in this console (D15 / I15 / the Attribution Rule) — a chart of people is the ' +
      'one thing this domain will not build.',
    run: ({ elements }) => {
      const dimensionAttributes = [
        'data-visual-dimension',
        'data-colour-by',
        'data-color-by',
        'data-sort-key',
        'data-facet',
        'data-axis',
        'data-group-by',
      ];
      const findings: RawFinding[] = [];
      for (const element of elements) {
        for (const attribute of dimensionAttributes) {
          const value = element.getAttribute(attribute);
          if (value === null) continue;
          if (/signer[_-]?sub/i.test(value)) {
            findings.push({
              element,
              message: `${attribute}="${value}" makes signer_sub a visual dimension.`,
            });
          }
        }
      }
      return findings;
    },
  },
];

/** Every rule, exported so `contract.test.ts` can prove no law cites a rule that is absent. */
export const RULES: readonly AuditRule[] = RULE_LIST;

export const RULE_IDS: readonly string[] = RULE_LIST.map((rule) => rule.id);

export function ruleById(id: string): AuditRule | null {
  return RULE_LIST.find((rule) => rule.id === id) ?? null;
}

// ── The run ──────────────────────────────────────────────────────────────────────

export interface AuditOptions {
  /**
   * Whether the tree under audit is a whole document that must carry exactly one `main`.
   * Defaults to `true` when `root` is a Document and `false` otherwise — auditing a
   * single component and demanding a main landmark of it would produce a finding the
   * component can never fix.
   */
  readonly expectMain?: boolean;
  /** Rule ids to skip, each with a reason. A skip with no reason is not accepted. */
  readonly skip?: Readonly<Record<string, string>>;
}

function ownerDocumentOf(root: ParentNode & Node): Document {
  if (root.nodeType === 9 /* DOCUMENT_NODE */) return root as unknown as Document;
  if (root instanceof Element) return root.ownerDocument;
  const first = root.firstElementChild;
  if (first !== null) return first.ownerDocument;
  throw new Error(
    'a11y/audit: the root has no owner document and no element children, so no rule could resolve ' +
      'an id reference. Audit a rendered tree, not an empty fragment.',
  );
}

/**
 * Audits a DOM tree.
 *
 * The returned report is worst-first and carries `notChecked` unconditionally. Callers
 * that print only `findings` are printing half the truth, which is why
 * `assertAccessible()` exists and is what the tests use.
 */
export function audit(root: ParentNode & Node, options: AuditOptions = {}): A11yReport {
  const document = ownerDocumentOf(root);
  const elements = [
    ...(root instanceof Element ? [root] : []),
    ...root.querySelectorAll('*'),
  ];
  const expectMain = options.expectMain ?? root.nodeType === 9;
  const skip = options.skip ?? {};

  const context: RuleContext = { root, elements, document, expectMain };

  const findings: A11yFinding[] = [];
  const rulesRun: string[] = [];

  for (const rule of RULE_LIST) {
    if (Object.prototype.hasOwnProperty.call(skip, rule.id)) continue;
    rulesRun.push(rule.id);
    for (const raw of rule.run(context)) {
      findings.push({
        ruleId: rule.id,
        impact: rule.impact,
        message: raw.message,
        help: rule.help,
        wcag: rule.wcag,
        target: raw.element === null ? '(document)' : targetPath(raw.element),
        snippet: raw.element === null ? '' : snippetOf(raw.element),
      });
    }
  }

  findings.sort(
    (a, b) =>
      impactRank(b.impact) - impactRank(a.impact) ||
      a.ruleId.localeCompare(b.ruleId) ||
      a.target.localeCompare(b.target),
  );

  const counts: Record<Impact, number> = { minor: 0, moderate: 0, serious: 0, critical: 0 };
  for (const finding of findings) counts[finding.impact] += 1;

  return {
    findings,
    blocking: findings.filter((finding) => isBlocking(finding.impact)),
    counts,
    elementsChecked: elements.length,
    rulesRun,
    notChecked: NOT_CHECKED_HERE,
  };
}

/** A report rendered for a terminal. Used by failure messages and by the CI summary. */
export function formatReport(report: A11yReport, label = 'tree'): string {
  const lines: string[] = [];
  lines.push(
    `a11y audit of ${label}: ${report.elementsChecked} element(s), ${report.rulesRun.length} rule(s), ` +
      `${report.findings.length} finding(s) — ${report.counts.critical} critical, ` +
      `${report.counts.serious} serious, ${report.counts.moderate} moderate, ${report.counts.minor} minor.`,
  );
  for (const finding of report.findings) {
    lines.push('');
    lines.push(`  [${finding.impact}] ${finding.ruleId} — ${finding.message}`);
    lines.push(`    at   ${finding.target}`);
    if (finding.snippet !== '') lines.push(`    html ${finding.snippet}`);
    lines.push(`    fix  ${finding.help}`);
    if (finding.wcag.length > 0) lines.push(`    wcag ${finding.wcag.join(', ')}`);
  }
  lines.push('');
  lines.push('  NOT CHECKED by this auditor (jsdom has no cascade and no layout):');
  for (const limit of report.notChecked) lines.push(`    · ${limit}`);
  return lines.join('\n');
}

/**
 * D14's gate, as a function that throws.
 *
 * Throws when any finding is `serious` or `critical`. The message carries the full
 * report INCLUDING `notChecked`, because a person reading a failure is the person most
 * likely to conclude that a pass means "accessible" — and it does not; it means "nothing
 * this auditor can see is broken".
 */
export function assertAccessible(
  root: ParentNode & Node,
  options: AuditOptions & { readonly label?: string } = {},
): A11yReport {
  const report = audit(root, options);
  if (report.blocking.length > 0) {
    throw new Error(
      `${report.blocking.length} blocking accessibility finding(s) — docs/leads/ui.md D14 permits ` +
        `zero serious or critical.\n\n${formatReport(report, options.label ?? 'tree')}\n`,
    );
  }
  return report;
}
