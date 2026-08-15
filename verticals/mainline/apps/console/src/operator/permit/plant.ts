// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * HSG250 FIGURE 1 ELEMENT 4 — PLANT IDENTIFICATION, from the boundary certificate.
 *
 * On paper, element 4 is a blank line where somebody writes a tag number, and its weakness
 * has always been that a form cannot tell you whether the line is COMPLETE. Ours can:
 * `boundary_certificate` carries `tags_declared`, `tags_resolved`, `tags_unmodelled` and
 * `under_declared` under a named `asset_graph_version`, so the screen states not only which
 * plant is identified but whether anything in the work's boundary is unaccounted for.
 * That is the one place on this screen where the system is straightforwardly better than
 * the paper it replaces, and it is worth saying plainly.
 *
 * TWO HONESTY CONSTRAINTS SHAPE THIS FILE.
 *
 * 1. `reads.py:500-501` claims exactly ONE provenance pointer for the whole certificate —
 *    `/boundary_certificate` — and none for its individual fields. So the chip sits on the
 *    block, and the individual numbers render WITHOUT chips, because they have no backing
 *    pointer and plan §4.2 says a chip with no backing pointer must not render. Chipping
 *    each number `db:column` because the block is `db:column` would be inventing corroboration.
 *
 * 2. THE "BOUNDARY CERTIFIED" MARK IS NOT THIS FILE'S ARITHMETIC. The schema records that
 *    `unmodelled_asset_count = tags_unmodelled + under_declared`, and it is the PERMIT's
 *    projected counter — written by a trigger, read by the CHECK constraint
 *    `boundary_certified_when_issued` — that decides the question. So the mark is keyed on
 *    `counters.unmodelled_asset_count`, which is a real column with a real pointer, and the
 *    constraint's own verbatim predicate is printed beside it. The console never composes an
 *    evidentiary claim (D5); it shows which column was read and what the database's own
 *    CHECK says about it.
 */

import type { Permit } from '../../data/types.generated';
import { type ChipLookup, absenceBlock, el, formSection, provenanceChip, readField } from './typed-fields';

/** The constraint whose predicate decides whether the boundary is certified. */
export const BOUNDARY_CONSTRAINT = 'boundary_certified_when_issued';

/** The projected counter that constraint reads. */
export const BOUNDARY_COUNTER = 'unmodelled_asset_count';

export interface PlantInput {
  readonly permit: Permit;
  readonly lookup: ChipLookup;
}

/** Render element 4. */
export function renderPlantIdentification(input: PlantInput): HTMLElement {
  const { permit, lookup } = input;
  const section = formSection({
    element: 4,
    heading: 'Plant identification',
    note: 'The boundary this permit was gated against, as the asset graph resolved it.',
  });

  const certificate = permit.boundary_certificate ?? null;
  if (certificate === null) {
    section.body.appendChild(
      absenceBlock(
        'no boundary certificate on this permit',
        'mainline.boundary_certificate has no row for this subject; the read returned null',
      ),
    );
    return section.root;
  }

  // The block-level chip. One pointer, one chip, on the block it actually covers.
  const blockChip = provenanceChip(lookup, '/boundary_certificate');
  if (blockChip !== null) {
    section.headingRow.appendChild(blockChip);
  }

  const version = el('div', 'cow-plant-version');
  version.appendChild(el('span', 'cow-field-label', 'Asset graph version'));
  version.appendChild(el('span', 'cow-mono cow-field-value', certificate.asset_graph_version));
  section.body.appendChild(version);

  const grid = el('div', 'cow-plant-grid');
  grid.appendChild(countCell('Tags declared', certificate.tags_declared));
  grid.appendChild(countCell('Tags resolved', certificate.tags_resolved));
  grid.appendChild(countCell('Tags unmodelled', certificate.tags_unmodelled));
  grid.appendChild(countCell('Under declared', certificate.under_declared));
  section.body.appendChild(grid);

  const computed = el('div', 'cow-plant-computed');
  computed.appendChild(el('span', 'cow-field-label', 'Certificate computed at'));
  const time = el('time', 'cow-mono cow-field-value', certificate.computed_at);
  time.setAttribute('datetime', certificate.computed_at);
  computed.appendChild(time);
  section.body.appendChild(computed);

  section.body.appendChild(renderCertifiedMark(permit, lookup));
  return section.root;
}

/**
 * The "boundary certified" mark, and the column and predicate it is keyed on.
 *
 * S11, quoted in the permit contract: *"an asset with no modelled energy edges is UNKNOWN,
 * not SAFE — and unknown blocks."* The mark therefore states which counter it read and what
 * the database's own CHECK requires of it, so a reader can disagree with the mark by reading
 * two printed facts rather than by trusting this screen.
 */
export function renderCertifiedMark(permit: Permit, lookup: ChipLookup): HTMLElement {
  const count = permit.counters.unmodelled_asset_count;
  const certified = count === 0;

  const box = el('div', `cow-certified ${certified ? 'cow-certified-yes' : 'cow-certified-no'}`);
  box.setAttribute('data-certified', String(certified));

  const mark = el('div', 'cow-certified-mark');
  mark.appendChild(el('span', 'cow-certified-glyph', certified ? '✓' : '●'));
  mark.appendChild(
    el(
      'span',
      'cow-certified-word',
      certified ? 'boundary certified' : 'boundary NOT certified',
    ),
  );
  box.appendChild(mark);

  box.appendChild(
    readField({
      label: `mainline.permit.${BOUNDARY_COUNTER}`,
      value: count,
      pointer: `/counters/${BOUNDARY_COUNTER}`,
      lookup,
      kind: 'mono',
    }),
  );

  const constraint = permit.constraints.find((item) => item.constraint === BOUNDARY_CONSTRAINT);
  if (constraint !== undefined) {
    const index = permit.constraints.indexOf(constraint);
    const line = el('div', 'cow-constraint');
    line.appendChild(el('span', 'cow-field-label', 'Constraint'));
    line.appendChild(el('span', 'cow-mono cow-constraint-name', constraint.constraint));
    const chip = provenanceChip(lookup, `/constraints/${index}`);
    if (chip !== null) {
      line.appendChild(chip);
    }
    box.appendChild(line);

    const predicate = constraint.predicate ?? null;
    if (predicate !== null) {
      // Verbatim CHECK text as the catalog reports it. Never paraphrased.
      const pre = el('pre', 'cow-predicate', predicate);
      box.appendChild(pre);
    }
  }

  return box;
}

/** One counted cell. No chip: `reads.py` claims no pointer for these fields. */
function countCell(label: string, value: number): HTMLElement {
  const cell = el('div', 'cow-plant-cell');
  cell.appendChild(el('span', 'cow-plant-count', String(value)));
  cell.appendChild(el('span', 'cow-plant-label', label));
  return cell;
}
