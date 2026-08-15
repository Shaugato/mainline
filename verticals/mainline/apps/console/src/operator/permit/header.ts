// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PERMIT HEADER — HSG250 Figure 1 element 2, plus the validity window (element 9).
 *
 * Four things an industry judge checks in the first ten seconds live here, and each is a
 * thing a fake screen normally gets wrong (r3-operator §9, plan §5):
 *
 *   1. a reference number and a status chip           → `external_ref`, `state`
 *   2. an expiry / validity window                    → `opened_at` → `horizon_at`
 *   8. the permit type, colour-coded                  → the blue COLD WORK edge
 *   —  the branch the permit is a ref of              → `ref_name`, ours alone
 *
 * THE COLOUR IS LOAD-BEARING. HSG250 Table 2 assigns **blue-edged or blue** to cold work
 * and **red-edged or red** to hot work. Our story is isolation of stored energy before
 * intrusive work with no ignition source named: cold work, blue. Rendering it red is the
 * kind of tell that makes an industry judge stop believing the screen.
 *
 * THE PERMIT TYPE IS NOT DATA, AND THIS FILE DOES NOT PRETEND IT IS. Plan §7 records it as
 * unsettled and rules it operator-typed: *"No column carries a permit type. If the type is
 * put on screen it is operator-typed or omitted, like every other uncarried field."* So the
 * type is a `<select>` the supervisor works in — visibly a control, carrying no provenance
 * chip — and the edge colour follows the selection, exactly as a real control-of-work
 * product colours the document it is about to print. The selection is a fact about the
 * person at the keyboard. It is never a fact about the database, and it is never chipped.
 *
 * THE STATUS CHIP RENDERS `state` VERBATIM (R10). `dispositioned` is a real value of
 * `mainline.subject_state` (`0011_type_subject_state.sql:27-35`). Translating it into
 * "Pending approval" would invent a status vocabulary this system does not have. The hover
 * gloss names the enum and its alphabet — which is checkable — and never replaces the word.
 */

import type { Permit, SubjectState } from '../../data/types.generated';
import { type ChipLookup, el, provenanceChip, readField } from './typed-fields';

/**
 * HSG250 Table 2, the colour-coded document types, in the guide's own order.
 *
 * `id` is this screen's own token, `label` is Table 2's wording for the type, and `edge` is
 * the CSS custom property the left edge takes. Nothing here is a database value: the whole
 * table is HSG250's, and the selection within it is the operator's.
 */
export interface PermitTypeOption {
  readonly id: string;
  readonly label: string;
  readonly edge: string;
}

export const PERMIT_TYPES: readonly PermitTypeOption[] = [
  { id: 'cold-work', label: 'Cold work', edge: 'var(--cow-edge-cold)' },
  { id: 'hot-work', label: 'Hot work', edge: 'var(--cow-edge-hot)' },
  { id: 'confined-space', label: 'Confined space entry', edge: 'var(--cow-edge-confined)' },
  { id: 'disjointing', label: 'Equipment disjointing', edge: 'var(--cow-edge-disjointing)' },
  { id: 'isolation-certificate', label: 'Isolation certificate', edge: 'var(--cow-edge-white)' },
  { id: 'hv-electrical', label: 'High voltage electrical isolation', edge: 'var(--cow-edge-hv)' },
  { id: 'sanction-to-test', label: 'Sanction to test', edge: 'var(--cow-edge-white)' },
  { id: 'excavation', label: 'Excavation', edge: 'var(--cow-edge-white)' },
];

/** Cold work. The clause is about isolating stored energy; no ignition source is named. */
export const DEFAULT_PERMIT_TYPE_ID = 'cold-work';

/**
 * The alphabet of `mainline.subject_state`, in the order `0011_type_subject_state.sql:27-35`
 * declares it.
 *
 * It is written as a `Record` keyed by the generated `SubjectState` union so that DRIFT IS A
 * RED BUILD: drop a value and the record is missing a key, add one the enum does not have and
 * it is an excess property. Neither compiles. The alternative — a bare string array — would
 * let this screen quietly disagree with the type the kernel answers to.
 *
 * It earns its place on screen twice. It is the status chip's gloss, and a gloss that shows
 * the reader the alphabet a word is drawn from is a checkable fact, where a gloss telling
 * them what `dispositioned` "really means" would be an editorial claim about a state machine
 * (R10). And it is fidelity checklist item 6 — *is suspension present as a state distinct
 * from closed?* — which HSG250 ¶19 makes load-bearing: *"a suspended permit remains live
 * until it is cancelled",* so a system that collapses the two is a system that can lose track
 * of a live isolation.
 */
const SUBJECT_STATE_DECLARATION: Readonly<Record<SubjectState, true>> = {
  draft: true,
  checks_materialised: true,
  dispositioned: true,
  merged: true,
  suspended: true,
  closed: true,
  abandoned: true,
};

export const SUBJECT_STATE_ALPHABET = Object.keys(
  SUBJECT_STATE_DECLARATION,
) as readonly SubjectState[];

export interface PermitHeaderInput {
  readonly permit: Permit;
  readonly lookup: ChipLookup;
}

export interface PermitHeader {
  readonly root: HTMLElement;
  /** Where the composition root mounts the display-copy control. */
  readonly actions: HTMLElement;
}

/**
 * Render the permit header.
 *
 * Every value below except the permit-type selection comes from one `GET /v1/permits/{id}`
 * in this page load and is chipped against that response's own envelope.
 */
export function renderPermitHeader(input: PermitHeaderInput): PermitHeader {
  const { permit, lookup } = input;

  const root = el('header', 'cow-permit-header');
  root.setAttribute('data-figure1-element', '2');

  // ── the coloured edge (HSG250 Table 2) ──────────────────────────────────────────
  const edge = el('div', 'cow-edge');
  edge.setAttribute('aria-hidden', 'true');
  root.appendChild(edge);

  const inner = el('div', 'cow-permit-header-inner');
  root.appendChild(inner);

  // ── top line: permit type (typed), reference number, status chip ────────────────
  const topLine = el('div', 'cow-hdr-top');

  const typeWrap = el('div', 'cow-hdr-type');
  const typeLabel = el('label', 'cow-field-label', 'Permit type');
  typeLabel.htmlFor = 'cow-permit-type';
  const select = el('select', 'cow-input cow-select');
  select.id = 'cow-permit-type';
  select.setAttribute('data-typed', 'operator');
  for (const option of PERMIT_TYPES) {
    const node = el('option', undefined, option.label);
    node.value = option.id;
    select.appendChild(node);
  }
  select.value = DEFAULT_PERMIT_TYPE_ID;
  const applyEdge = (): void => {
    const chosen = PERMIT_TYPES.find((option) => option.id === select.value);
    edge.style.background = chosen === undefined ? 'var(--cow-edge-white)' : chosen.edge;
    root.setAttribute('data-permit-type', select.value);
  };
  applyEdge();
  select.addEventListener('change', applyEdge);
  typeWrap.appendChild(typeLabel);
  typeWrap.appendChild(select);
  typeWrap.appendChild(el('span', 'cow-hint', 'HSG250 Table 2 · selected on this device'));
  topLine.appendChild(typeWrap);

  const refWrap = el('div', 'cow-hdr-ref');
  refWrap.appendChild(el('span', 'cow-field-label', 'Permit reference number'));
  const refLine = el('div', 'cow-hdr-ref-line');
  refLine.appendChild(el('span', 'cow-ref', permit.external_ref));
  const refChip = chipInto(refLine, lookup, '/external_ref');
  refWrap.appendChild(refLine);

  // The branch. A permit that is a git ref is our most distinctive idea; it belongs in the
  // header, not hidden in a detail pane (r3-operator §6.2).
  const branchLine = el('div', 'cow-hdr-branch');
  branchLine.appendChild(el('span', 'cow-mono cow-branch', permit.ref_name));
  chipInto(branchLine, lookup, '/ref_name');
  refWrap.appendChild(branchLine);
  topLine.appendChild(refWrap);

  topLine.appendChild(renderStateChip(permit, lookup));
  inner.appendChild(topLine);

  // ── the facts line ──────────────────────────────────────────────────────────────
  const facts = el('div', 'cow-hdr-facts');
  facts.appendChild(
    readField({
      label: 'Site',
      value: permit.site_code ?? null,
      pointer: '/site_code',
      lookup,
      kind: 'mono',
      title: 'mainline.site.site_code, joined on mainline.permit.site_id',
    }),
  );
  facts.appendChild(
    readField({
      label: 'Valid from',
      value: permit.opened_at,
      pointer: '/opened_at',
      lookup,
      kind: 'instant',
    }),
  );
  facts.appendChild(
    readField({
      label: 'Expires',
      value: permit.horizon_at,
      pointer: '/horizon_at',
      lookup,
      kind: 'instant',
      title: 'HSG250 audit item 23 — permits must clearly specify a time limit for expiry',
    }),
  );
  facts.appendChild(
    readField({ label: 'Gate epoch', value: permit.gate_epoch, pointer: '/gate_epoch', lookup }),
  );
  facts.appendChild(
    readField({ label: 'Chain head', value: permit.head_seq, pointer: '/head_seq', lookup }),
  );
  facts.appendChild(
    readField({
      label: 'Under hold',
      value: String(permit.under_hold),
      pointer: '/under_hold',
      lookup,
      kind: 'mono',
    }),
  );
  inner.appendChild(facts);

  const actions = el('div', 'cow-hdr-actions');
  inner.appendChild(actions);

  // A header whose reference number carried no chip would be a header nobody should
  // believe. Say so on the screen rather than failing silently.
  if (refChip === null) {
    refWrap.appendChild(
      el('span', 'cow-hint cow-unchipped', 'no provenance pointer for /external_ref'),
    );
  }

  return { root, actions };
}

/**
 * The status chip — `state` VERBATIM, per R10.
 *
 * The word on the chip is the database's word. The `title` gloss names the type it is drawn
 * from and lists that type's values; it does not translate the word, and it is available on
 * hover rather than in the word's place.
 */
export function renderStateChip(permit: Permit, lookup: ChipLookup): HTMLElement {
  const wrap = el('div', 'cow-hdr-state');
  wrap.appendChild(el('span', 'cow-field-label', 'Status'));

  const line = el('div', 'cow-hdr-state-line');
  const chip = el('span', 'cow-state-chip', permit.state);
  chip.setAttribute('data-state', permit.state);
  chip.title = `mainline.subject_state — one of: ${SUBJECT_STATE_ALPHABET.join(', ')}`;
  line.appendChild(chip);
  chipInto(line, lookup, '/state');
  wrap.appendChild(line);

  // The lifecycle vocabulary, visible rather than only on hover. Fidelity item 6 turns on
  // `suspended` being on this list and not being the same word as `closed`.
  const alphabet = el('ul', 'cow-state-alphabet');
  alphabet.title = 'mainline.subject_state — the seven values the enum declares';
  for (const value of SUBJECT_STATE_ALPHABET) {
    const item = el('li', 'cow-state-value', value);
    if (value === permit.state) {
      item.setAttribute('data-current', 'true');
      item.setAttribute('aria-current', 'true');
    }
    alphabet.appendChild(item);
  }
  wrap.appendChild(alphabet);
  wrap.appendChild(el('span', 'cow-hint', 'mainline.subject_state'));
  return wrap;
}

/** Append the provenance chip for `pointer` to `host`, if the envelope claimed it. */
function chipInto(host: HTMLElement, lookup: ChipLookup, pointer: string): HTMLElement | null {
  const node = provenanceChip(lookup, pointer);
  if (node !== null) {
    host.appendChild(node);
  }
  return node;
}
