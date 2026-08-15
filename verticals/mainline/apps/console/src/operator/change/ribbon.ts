// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ICHEME FIVE-STEP RIBBON — the industry's model, shown BESIDE our state, never AS it.
 *
 * The IChemE Safety Centre's *Management of Change* guidance (v1.0) prints
 * `Initiate → Screen → Review → Approve → Implement`, with `Capture and Close-out`
 * spanning them, across the head of every page. A safety engineer recognises that ribbon
 * on sight, which is why it is here.
 *
 * WHAT THIS MODULE REFUSES TO DO, AND WHY IT IS THE WHOLE POINT
 * -------------------------------------------------------------
 * `operator-systems-plan.md` R11 (following r3-operator §7.1): *"Do not let the ribbon
 * assert a mapping the database does not carry."*
 *
 * `mainline.change_request` has no MOC-step column. Nothing in this deployment says the
 * seeded change request is "at Review". Marking a step current would therefore be an
 * assertion invented by this file — the same class of act as typing a SQLSTATE into a
 * `.ts` file. So **no step is ever marked current**, `renderRibbon` takes no "current
 * step" argument, and there is no code path that could mark one.
 *
 * The real state travels in a chip beside the ribbon, rendered VERBATIM. R10 forbids
 * translating the enum and this worker's brief names `checks_materialised` specifically:
 * it is a real value of `mainline.subject_state` and it is shown as one, with its column
 * named and no gloss attached.
 *
 * ── the three DOM helpers ─────────────────────────────────────────────────────────
 * `el` / `txt` / `dbSpan` live in this module because it is the only leaf under
 * `src/operator/change/` with no dependency of its own, which keeps the module graph in
 * this directory strictly acyclic (ribbon ← {osha-sections, lattice, absence} ←
 * ChangeScreen). They build DOM through `createElement` and `textContent` only. There is
 * no `innerHTML` anywhere in this directory, so no string from the kernel can ever be
 * parsed as markup, and every rendered character is one that was passed in.
 */

/** Create an element, set its classes, and append children. `textContent` only — never HTML. */
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  ...children: readonly (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className !== undefined && className !== '') node.className = className;
  for (const child of children) {
    node.append(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

/**
 * Render a value the DATABASE produced, in the monospace register.
 *
 * `null` is rendered as an ABSENCE, never as an empty string and never as a placeholder:
 * a field this deployment did not return must look different from one it returned empty.
 */
export function dbSpan(value: string | number | null, absentLabel = 'not read'): HTMLElement {
  if (value === null) return el('span', 'moc-absent-inline', absentLabel);
  return el('code', 'moc-db', String(value));
}

/** A short caption in the operator's register. */
export function txt(text: string, className = 'moc-provenance'): HTMLParagraphElement {
  return el('p', className, text);
}

/**
 * The five steps, exactly as the IChemE Safety Centre prints them.
 *
 * These are the industry's words, cited on screen to the ISC guidance. They are a
 * heading vocabulary, not data: nothing in this array is ever presented as a value this
 * deployment returned.
 */
export const ICHEME_STEPS: readonly string[] = [
  'Initiate',
  'Screen',
  'Review',
  'Approve',
  'Implement',
];

/** The band the ISC prints across the five steps rather than after them. */
export const ICHEME_TRAILER = 'Capture and Close-out';

export interface RibbonInput {
  /** `mainline.change_request.state`, verbatim, or `null` when the read has not landed. */
  readonly state: string | null;
  /** The column the state came from, named on screen so the chip is checkable. */
  readonly stateColumn: string;
}

/**
 * The ribbon, plus the state chip beside it, plus the sentence that keeps them apart.
 *
 * No step carries a "current" class, an `aria-current`, or any other mark. The list is
 * `aria-hidden`-free and readable in order; the chip is a separate labelled group so a
 * screen reader announces the state as its own fact rather than as a ribbon position.
 */
export function renderRibbon(input: RibbonInput): HTMLElement {
  const wrap = el('section', 'moc-ribbon-wrap');
  wrap.setAttribute('aria-label', 'Management-of-change process model and record state');

  const row = el('div', 'moc-ribbon-row');

  const list = el('ol', 'moc-ribbon');
  ICHEME_STEPS.forEach((step, index) => {
    if (index > 0) list.append(el('li', 'moc-step-arrow', '→'));
    list.append(el('li', 'moc-step', step));
  });
  list.append(el('li', 'moc-step moc-step-trailer', ICHEME_TRAILER));
  row.append(list);

  const chip = el('div', 'moc-statechip');
  chip.append(el('span', 'moc-statechip-label', input.stateColumn));
  chip.append(dbSpan(input.state));
  row.append(chip);

  wrap.append(row);
  wrap.append(
    txt(
      'The five steps are the IChemE Safety Centre’s Management of Change model (v1.0), ' +
        'shown for orientation. No step is marked current, because no column in this ' +
        'deployment maps a change request onto an IChemE step — the ribbon is not ' +
        'asserting a position the database does not carry.',
    ),
  );
  wrap.append(
    txt(
      `The chip beside it is this deployment’s own value of ${input.stateColumn}, printed ` +
        'exactly as it was returned and not translated into process language.',
    ),
  );

  return wrap;
}
