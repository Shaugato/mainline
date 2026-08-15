// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE FIELD VOCABULARY OF THE PERMIT SCREEN — and the structural enforcement of R9.
 *
 * `docs/demo/operator-systems-plan.md` R9 is the honesty ledger and it is binding:
 *
 *   > Figure 1 elements 1 (permit title), 3 (job location free text), 5 (description of
 *   > work) are visible `<input>`/`<textarea>` elements with a caret, a placeholder, no
 *   > provenance chip, and they are never echoed back as server data. Element 8 (PPE)
 *   > renders greyed with the words "not carried by this deployment". Element 11
 *   > (extension) is omitted. Hard-coding a plausible job description, plant name, crew or
 *   > PPE list is FORBIDDEN and is the same class of act as reshaping a seed to match a
 *   > constant.
 *
 * A rule written in a document is a rule somebody forgets at 2am. So this module is
 * deliberately the ONLY place in `src/operator/permit/**` that knows how to put a value on
 * the screen, and it offers exactly four ways to do it:
 *
 *   readField()        a value the SERVER returned. Requires an RFC 6901 pointer and a
 *                      `ChipLookup`. Renders a provenance chip if — and only if — the
 *                      envelope claimed that pointer. There is no way to call it without
 *                      naming where the value came from.
 *   typedField()       a value a HUMAN types, on camera. Its signature carries NO value
 *                      parameter and NO pointer, so it is not expressible to prefill one
 *                      from a response, and it never renders a chip.
 *   notCarriedField()  a Figure 1 element this deployment has no column for. Greyed, with
 *                      the words NOT_CARRIED and nothing else.
 *   omittedElement()   a Figure 1 element the kernel has no concept of. Named, not hidden:
 *                      "a capability is named and never populated"
 *                      (docs/decisions/demo-use-cases.md §0).
 *
 * There is no fifth way, and in particular there is no `staticField(label, value)`. That is
 * the whole design: the dishonest option is not a rule you must remember, it is a function
 * that does not exist.
 *
 * R1: this file imports no React, nothing from `src/app`, `src/design`, `src/features`,
 * `src/verify`, and no RUNTIME value from `src/data`. The one import below is type-only and
 * erases to zero bytes, which R1 permits by name.
 */

import type { ProvenanceChip } from '../../data/types.generated';

/**
 * The narrow view of W2's `chipFor()` that this screen needs.
 *
 * `docs/demo/operator-systems-plan.md` §4.2 publishes
 * `chipFor(env: Envelope | null, jsonPointer: string): ProvChip | null`. The composition
 * root binds the envelope once and hands the parts this one-argument closure, so no part
 * can render a value from resource A while chipping it against the envelope of resource B.
 */
export type ChipLookup = (jsonPointer: string) => ProvenanceChip | null;

/** The exact words R9 requires on a Figure 1 element with no column. Not paraphrased. */
export const NOT_CARRIED = 'not carried by this deployment';

/** The words that mark an operator-typed field, so a viewer is never in doubt. */
export const TYPED_HERE = 'typed on this device · not carried by this deployment';

/** Create an element. The only DOM constructor this screen uses. */
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className !== undefined) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

/**
 * Format an instant for a human, in UTC, without losing the instant.
 *
 * The rendered string is a convenience; the machine-readable original is always carried in
 * the `datetime` attribute of the `<time>` element that holds it, so nothing here is the
 * only copy of anything. A string the platform cannot parse is rendered VERBATIM rather
 * than repaired — a date this screen could not read is a fact about the payload, and
 * quietly printing a plausible one instead is exactly the class of act this repository
 * refuses.
 */
export function formatInstantUtc(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    return iso;
  }
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(at);
  return `${parts}Z`;
}

/**
 * The provenance chip for `pointer`, or null when the envelope did not claim it.
 *
 * `envelope.py` is explicit that *"a pointer absent from this list has NO chip and is
 * rendered without one — an unclaimed provenance is better than a comfortable default"*.
 * Returning null here, and every caller appending only a non-null result, is that sentence
 * in code.
 */
export function provenanceChip(lookup: ChipLookup, pointer: string): HTMLElement | null {
  const chip = lookup(pointer);
  if (chip === null) {
    return null;
  }
  const node = el('span', 'cow-chip', chip);
  node.setAttribute('data-chip', chip);
  node.setAttribute('data-pointer', pointer);
  node.title = `provenance: ${chip} at ${pointer}`;
  return node;
}

/** How a server value is drawn. `instant` additionally emits a machine-readable `<time>`. */
export type ReadFieldKind = 'text' | 'mono' | 'instant';

export interface ReadFieldSpec {
  /** The human label. HSG250's own words wherever HSG250 has a word for it. */
  readonly label: string;
  /** The value the server returned. `null` is rendered AS null, never as a placeholder. */
  readonly value: string | number | null;
  /** RFC 6901 pointer into the resource's `data`, e.g. `/external_ref`. */
  readonly pointer: string;
  readonly lookup: ChipLookup;
  readonly kind?: ReadFieldKind;
  /** Extra hover text. Never a substitute for the value. */
  readonly title?: string;
}

/**
 * One labelled value that came back over HTTP in this page load.
 *
 * `pointer` and `lookup` are REQUIRED, which is the point: a server value cannot reach the
 * screen through this module without declaring which field of which envelope it is, and the
 * chip appears only if that declaration is corroborated by the envelope itself.
 */
export function readField(spec: ReadFieldSpec): HTMLElement {
  const kind = spec.kind ?? 'text';
  const row = el('div', 'cow-field cow-field-read');
  row.appendChild(el('span', 'cow-field-label', spec.label));

  const slot = el('span', `cow-field-value${kind === 'text' ? '' : ' cow-mono'}`);
  if (spec.value === null) {
    const absent = el('span', 'cow-null', 'null');
    absent.title = 'the column exists on this row and its value is null';
    slot.appendChild(absent);
  } else if (kind === 'instant' && typeof spec.value === 'string') {
    const time = el('time', undefined, formatInstantUtc(spec.value));
    time.setAttribute('datetime', spec.value);
    time.title = spec.value;
    slot.appendChild(time);
  } else {
    slot.textContent = String(spec.value);
  }
  if (spec.title !== undefined) {
    slot.title = spec.title;
  }
  row.appendChild(slot);

  const chip = provenanceChip(spec.lookup, spec.pointer);
  if (chip !== null) {
    row.appendChild(chip);
  }
  return row;
}

export interface TypedFieldSpec {
  /** The HSG250 Figure 1 element number this field is. */
  readonly element: number;
  /** DOM id, so the `<label>` is a real label. */
  readonly id: string;
  /** HSG250's own words for the element. */
  readonly label: string;
  /** What a supervisor would write here. A PROMPT, never a value: placeholders do not submit. */
  readonly placeholder: string;
  /** Rows for a `<textarea>`; omit for a single-line `<input>`. */
  readonly rows?: number;
}

/**
 * A field a human fills in on camera.
 *
 * There is no `value` parameter and there is no `pointer` parameter, and that is not an
 * oversight — it is R9. A caller cannot prefill this field from a response because the
 * function will not accept one, and it never renders a provenance chip because it has no
 * lookup to render one from.
 *
 * The placeholder is a PROMPT and never a value: `placeholder` is not submitted, is not
 * read back by `.value`, and is styled as absent text so nobody films it as data.
 */
export function typedField(spec: TypedFieldSpec): HTMLElement {
  const row = el('div', 'cow-field cow-field-typed');

  const label = el('label', 'cow-field-label', spec.label);
  label.htmlFor = spec.id;
  row.appendChild(label);

  let control: HTMLInputElement | HTMLTextAreaElement;
  if (spec.rows === undefined) {
    const input = el('input', 'cow-input');
    input.type = 'text';
    input.autocomplete = 'off';
    control = input;
  } else {
    const area = el('textarea', 'cow-input cow-textarea');
    area.rows = spec.rows;
    control = area;
  }
  control.id = spec.id;
  control.placeholder = spec.placeholder;
  control.setAttribute('data-figure1-element', String(spec.element));
  control.setAttribute('data-typed', 'operator');
  row.appendChild(control);

  const hint = el('span', 'cow-hint', TYPED_HERE);
  row.appendChild(hint);
  return row;
}

export interface NotCarriedSpec {
  readonly element: number;
  readonly label: string;
}

/**
 * A Figure 1 element this deployment carries no column for, rendered as an empty box that
 * says so. R9 honest option B: *"maximally honest, visually dead, and it advertises absence
 * at the exact moment we want the judge looking at the refusal."*
 */
export function notCarriedField(spec: NotCarriedSpec): HTMLElement {
  const row = el('div', 'cow-field cow-field-absent');
  row.setAttribute('data-figure1-element', String(spec.element));
  row.appendChild(el('span', 'cow-field-label', spec.label));
  const slot = el('span', 'cow-field-value cow-absent', NOT_CARRIED);
  slot.setAttribute('data-not-carried', 'true');
  row.appendChild(slot);
  return row;
}

export interface OmittedSpec {
  readonly element: number;
  readonly label: string;
  /** Why the kernel has no concept of it. A fact about the kernel, not an apology. */
  readonly reason: string;
}

/**
 * A Figure 1 element that is OMITTED, named rather than silently dropped.
 *
 * `docs/decisions/demo-use-cases.md` §0: a capability is named and never populated. A form
 * that quietly skips element 11 looks complete; a form that says element 11 is not
 * implemented here is one a judge can trust about elements 1–13.
 */
export function omittedElement(spec: OmittedSpec): HTMLElement {
  const row = el('div', 'cow-field cow-field-omitted');
  row.setAttribute('data-figure1-element', String(spec.element));
  row.setAttribute('data-omitted', 'true');
  row.appendChild(el('span', 'cow-field-label', spec.label));
  row.appendChild(el('span', 'cow-field-value cow-absent', `omitted — ${spec.reason}`));
  return row;
}

export interface SectionSpec {
  /** HSG250 Figure 1 element number, printed in the margin the way the form numbers them. */
  readonly element: number | string;
  /** HSG250's own heading for the element. */
  readonly heading: string;
  /** One short line of context. Optional, and never a substitute for a value. */
  readonly note?: string;
}

export interface Section {
  readonly root: HTMLElement;
  readonly body: HTMLElement;
  readonly headingRow: HTMLElement;
}

/** One numbered block of the form, in Figure 1 order. */
export function formSection(spec: SectionSpec): Section {
  const root = el('section', 'cow-section');
  root.setAttribute('data-figure1-element', String(spec.element));

  const headingRow = el('div', 'cow-section-head');
  headingRow.appendChild(el('span', 'cow-element-no', String(spec.element)));
  const heading = el('h2', 'cow-section-title', spec.heading);
  headingRow.appendChild(heading);
  root.appendChild(headingRow);

  if (spec.note !== undefined) {
    root.appendChild(el('p', 'cow-section-note', spec.note));
  }

  const body = el('div', 'cow-section-body');
  root.appendChild(body);
  return { root, body, headingRow };
}

/**
 * The block a read renders when it did not arrive.
 *
 * Absence, never a placeholder — plan §4.2: *"Every screen renders absence rather than a
 * placeholder when a field is null."* The status line is the real one from the exchange.
 */
export function absenceBlock(what: string, detail: string): HTMLElement {
  const box = el('div', 'cow-absence');
  box.setAttribute('role', 'status');
  box.appendChild(el('span', 'cow-absence-what', what));
  box.appendChild(el('span', 'cow-absence-detail cow-mono', detail));
  return box;
}
