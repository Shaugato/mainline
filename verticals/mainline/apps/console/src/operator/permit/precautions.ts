// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * HSG250 FIGURE 1 ELEMENT 7 — PRECAUTIONS NECESSARY, quoted verbatim from the clause version.
 *
 * The clause text is rendered EXACTLY as `GET /v1/clauses/{uuid}/versions/{commit}` returned
 * it, including its `SYNTHETIC —` prefix, which R13 requires stay visible. In particular
 * *"isolated, locked and verified at zero by a competent person"* is not paraphrased:
 * **"competent person" is a term of art**. HSG250 Table 1 gives it as the alternate title
 * for the person working under the terms of the permit, so the seeded clause is already
 * using it in exactly its HSG250 sense. That is a point of fidelity we have for free, and
 * softening it into "a qualified worker" would throw it away.
 *
 * The monospace sub-line is the clause's IDENTITY — `printed_label`, `gen`, `control_delta`,
 * `sev_max`, `canon_sha256` — every one of them a column with its own pointer in the clause
 * envelope, so every one of them carries its own chip. `canon_sha256` is what makes the
 * quotation checkable: the text above it is the text that digest is over.
 *
 * The anchors render as chips, which is what a real control-of-work product does with hazard
 * tags. `LOTO` and `ZERO_ENERGY` are the database's strings, not labels this file chose.
 */

import type { ClauseVersion } from '../../data/types.generated';
import { type ChipLookup, el, formSection, provenanceChip, readField } from './typed-fields';

export interface PrecautionsInput {
  readonly version: ClauseVersion;
  /** Chip lookup bound to the CLAUSE envelope. Pointers here are `/version/...`. */
  readonly lookup: ChipLookup;
}

/** Render element 7. */
export function renderPrecautions(input: PrecautionsInput): HTMLElement {
  const { version, lookup } = input;
  const section = formSection({
    element: 7,
    heading: 'Precautions necessary and actions in the event of an emergency',
    note: 'The controlling clause version this permit relies on, quoted as the database returned it.',
  });

  // ── the clause, verbatim ────────────────────────────────────────────────────────
  const quote = el('blockquote', 'cow-clause');
  quote.appendChild(el('p', 'cow-clause-text', version.canon_text));
  const quoteChip = provenanceChip(lookup, '/version/canon_text');
  if (quoteChip !== null) {
    quote.appendChild(quoteChip);
  }
  section.body.appendChild(quote);

  // ── identity: the monospace sub-line ────────────────────────────────────────────
  const identity = el('div', 'cow-clause-identity');
  identity.appendChild(
    readField({
      label: 'Clause',
      value: version.printed_label ?? null,
      pointer: '/version/printed_label',
      lookup,
      kind: 'mono',
    }),
  );
  identity.appendChild(
    readField({ label: 'Generation', value: version.gen, pointer: '/version/gen', lookup, kind: 'mono' }),
  );
  identity.appendChild(
    readField({
      label: 'Control delta',
      value: version.control_delta,
      pointer: '/version/control_delta',
      lookup,
      kind: 'mono',
    }),
  );
  identity.appendChild(
    readField({
      label: 'Severity max',
      value: version.sev_max,
      pointer: '/version/sev_max',
      lookup,
      kind: 'mono',
      title: 'the worst severity anywhere in this version’s blame lineage; projected, never chosen',
    }),
  );
  identity.appendChild(
    readField({
      label: 'Canonical sha256',
      value: version.canon_sha256,
      pointer: '/version/canon_sha256',
      lookup,
      kind: 'mono',
    }),
  );
  identity.appendChild(
    readField({
      label: 'At commit',
      value: version.commit_id,
      pointer: '/version/commit_id',
      lookup,
      kind: 'mono',
    }),
  );
  section.body.appendChild(identity);

  // ── anchors, as a real system tags hazards ──────────────────────────────────────
  section.body.appendChild(renderAnchors(version, lookup));
  return section.root;
}

/** The anchor set as chips. The strings are the database's; this file adds no anchor. */
export function renderAnchors(version: ClauseVersion, lookup: ChipLookup): HTMLElement {
  const wrap = el('div', 'cow-anchors');
  wrap.appendChild(el('span', 'cow-field-label', 'Anchors'));

  const list = el('ul', 'cow-anchor-list');
  list.setAttribute('data-anchor-count', String(version.anchor_set.length));
  for (const anchor of version.anchor_set) {
    const item = el('li', 'cow-anchor', anchor);
    list.appendChild(item);
  }
  wrap.appendChild(list);

  const chip = provenanceChip(lookup, '/version/anchor_set');
  if (chip !== null) {
    wrap.appendChild(chip);
  }
  return wrap;
}
