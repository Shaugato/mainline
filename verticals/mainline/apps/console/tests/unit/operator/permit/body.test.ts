// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE FIGURE 1 BODY — plant identification (element 4) and precautions (element 7).
 *
 * Element 4 is the one place this screen is straightforwardly better than the paper form it
 * imitates: `boundary_certificate` states not only which plant is identified but whether
 * anything in the boundary is unaccounted for. The risk that comes with that is over-claiming
 * — chipping every number `db:column` because the block is chipped, or computing the
 * "certified" verdict in the browser and presenting it as the database's. `reads.py:500-501`
 * claims exactly ONE pointer for the whole certificate, so the tests below pin the chip to the
 * block and assert its absence on the individual counts.
 *
 * Element 7 quotes the clause. The assertion that matters is that it is quoted VERBATIM —
 * including the seed's own `SYNTHETIC —` prefix, which R13 requires stay visible, and
 * including "competent person", which is HSG250 Table 1's term of art and correct already.
 */

import { describe, expect, it } from 'vitest';

import type { ClauseVersion, Permit } from '../../../../src/data/types.generated';
import {
  BOUNDARY_CONSTRAINT,
  BOUNDARY_COUNTER,
  renderPlantIdentification,
} from '../../../../src/operator/permit/plant';
import { renderPrecautions } from '../../../../src/operator/permit/precautions';
import type { ChipLookup } from '../../../../src/operator/permit/typed-fields';

const PREDICATE_UNDER_TEST =
  "CHECK (((state != 'merged'::mainline.subject_state) OR (unmodelled_asset_count = 0)))";

const permitWith = (over: Partial<Permit> = {}): Permit => ({
  permit_id: 'permit-uuid-under-test',
  site_id: 'site-uuid-under-test',
  site_code: 'site-code-under-test',
  external_ref: 'REF-UNDER-TEST',
  ref_name: 'refs/permits/under-test',
  state: 'dispositioned',
  head_seq: 2,
  gate_epoch: 1,
  merged_commit: null,
  under_hold: false,
  opened_at: 'opened-instant-under-test',
  horizon_at: 'horizon-instant-under-test',
  counters: {
    open_blocking: 1,
    open_residue: 0,
    open_conflicts: 0,
    open_warrants: 0,
    unmodelled_asset_count: 0,
    unmet_floor_count: 0,
    countersigned_count: 0,
  },
  constraints: [
    {
      constraint: BOUNDARY_CONSTRAINT,
      predicate: PREDICATE_UNDER_TEST,
      counters: [{ column: BOUNDARY_COUNTER, value: 0 }],
      blamed_by_refusal: false,
    },
  ],
  boundary_certificate: {
    asset_graph_version: 'asset-graph-under-test',
    tags_declared: 1,
    tags_resolved: 1,
    tags_unmodelled: 0,
    under_declared: 0,
    computed_at: 'computed-instant-under-test',
  },
  merge_record: null,
  ...over,
});

/** Claims exactly what the live permit read claims: the block, not its fields. */
const permitClaims: ChipLookup = (pointer) =>
  pointer === '/boundary_certificate' ||
  pointer === `/counters/${BOUNDARY_COUNTER}` ||
  pointer === '/constraints/0'
    ? pointer === '/constraints/0'
      ? 'db:constraint'
      : 'db:column'
    : null;

describe('element 4 — plant identification from the boundary certificate', () => {
  const root = renderPlantIdentification({ permit: permitWith(), lookup: permitClaims });

  it('is the fourth Figure 1 element and uses HSG250’s heading', () => {
    expect(root.getAttribute('data-figure1-element')).toBe('4');
    expect(root.querySelector('.cow-section-title')?.textContent).toBe('Plant identification');
  });

  it('renders the four counts under the asset graph version', () => {
    const counts = [...root.querySelectorAll('.cow-plant-count')].map((n) => n.textContent);
    expect(counts).toEqual(['1', '1', '0', '0']);
    expect(root.querySelector('.cow-plant-version')?.textContent).toContain(
      'asset-graph-under-test',
    );
  });

  it('chips the BLOCK, because the envelope claims one pointer for the whole certificate', () => {
    const blockChip = root.querySelector('.cow-section-head .cow-chip');
    expect(blockChip?.getAttribute('data-pointer')).toBe('/boundary_certificate');
  });

  it('does NOT chip the individual counts — they have no backing pointer', () => {
    for (const cell of root.querySelectorAll('.cow-plant-cell')) {
      expect(cell.querySelector('.cow-chip')).toBeNull();
    }
  });

  it('marks the boundary certified from the projected counter, not from its own arithmetic', () => {
    const box = root.querySelector('.cow-certified');
    expect(box?.getAttribute('data-certified')).toBe('true');
    expect(box?.textContent).toContain('boundary certified');
    // The counter it read is named on screen, chipped, so the mark can be disagreed with.
    const pointers = [...(box?.querySelectorAll('.cow-chip') ?? [])].map((n) =>
      n.getAttribute('data-pointer'),
    );
    expect(pointers).toContain(`/counters/${BOUNDARY_COUNTER}`);
  });

  it('prints the database’s own CHECK predicate verbatim beside the mark', () => {
    expect(root.querySelector('.cow-predicate')?.textContent).toBe(PREDICATE_UNDER_TEST);
    expect(root.querySelector('.cow-constraint-name')?.textContent).toBe(BOUNDARY_CONSTRAINT);
  });

  it('says NOT certified when the counter says so — unknown blocks (S11)', () => {
    const permit = permitWith({
      counters: { ...permitWith().counters, unmodelled_asset_count: 1 },
    });
    const box = renderPlantIdentification({ permit, lookup: permitClaims }).querySelector(
      '.cow-certified',
    );
    expect(box?.getAttribute('data-certified')).toBe('false');
    expect(box?.textContent).toContain('boundary NOT certified');
  });

  it('renders absence, not a blank form, when there is no certificate', () => {
    const permit = permitWith({ boundary_certificate: null });
    const root2 = renderPlantIdentification({ permit, lookup: permitClaims });
    expect(root2.querySelector('.cow-absence')).not.toBeNull();
    expect(root2.querySelector('.cow-plant-grid')).toBeNull();
  });

  it('names no plant, tag or vessel of its own', () => {
    const text = (root.textContent ?? '').toLowerCase();
    for (const invented of ['pump', 'vessel', 'compressor', 'tank ', 'unit 3', 'p-101']) {
      expect(text).not.toContain(invented);
    }
  });
});

describe('element 7 — the clause, quoted verbatim', () => {
  const CANON = 'SYNTHETIC — clause text under test, verified at zero by a competent person.';
  const VERSION: ClauseVersion = {
    clause_uuid: 'clause-uuid-under-test',
    gen: 1,
    commit_id: 'commit-under-test',
    site_id: 'site-uuid-under-test',
    activity_root: 'activity-root-under-test',
    printed_label: 'label-under-test',
    raw_text: CANON,
    canon_text: CANON,
    canon_version: 1,
    canon_sha256: 'canon-digest-under-test',
    anchor_set: ['LOTO', 'ZERO_ENERGY'],
    control_delta: 'introduce',
    delta_basis: 'lattice',
    sev_max: 4,
  };

  const clauseClaims: ChipLookup = (pointer) =>
    pointer.startsWith('/version/') ? 'db:column' : null;

  const root = renderPrecautions({ version: VERSION, lookup: clauseClaims });

  it('is the seventh Figure 1 element and uses HSG250’s full heading', () => {
    expect(root.getAttribute('data-figure1-element')).toBe('7');
    expect(root.querySelector('.cow-section-title')?.textContent).toBe(
      'Precautions necessary and actions in the event of an emergency',
    );
  });

  it('quotes canon_text character for character, prefix and all', () => {
    expect(root.querySelector('.cow-clause-text')?.textContent).toBe(CANON);
  });

  it('keeps the SYNTHETIC marker visible (R13) and does not paraphrase "competent person"', () => {
    const quoted = root.querySelector('.cow-clause-text')?.textContent ?? '';
    expect(quoted).toContain('SYNTHETIC');
    expect(quoted).toContain('competent person');
    expect(quoted).not.toContain('qualified worker');
    expect(quoted).not.toContain('trained operative');
  });

  it('carries the identity sub-line, every part of it chipped to its own column', () => {
    const pointers = [...root.querySelectorAll('.cow-clause-identity .cow-chip')].map((n) =>
      n.getAttribute('data-pointer'),
    );
    expect(pointers).toEqual([
      '/version/printed_label',
      '/version/gen',
      '/version/control_delta',
      '/version/sev_max',
      '/version/canon_sha256',
      '/version/commit_id',
    ]);
  });

  it('renders the anchors as chips, using the database’s own strings', () => {
    const anchors = [...root.querySelectorAll('.cow-anchor')].map((n) => n.textContent);
    expect(anchors).toEqual(['LOTO', 'ZERO_ENERGY']);
    expect(root.querySelector('.cow-anchor-list')?.getAttribute('data-anchor-count')).toBe('2');
  });

  it('drops the quotation’s chip rather than inventing one when it is unclaimed', () => {
    const bare = renderPrecautions({ version: VERSION, lookup: () => null });
    expect(bare.querySelectorAll('.cow-chip')).toHaveLength(0);
    expect(bare.querySelector('.cow-clause-text')?.textContent).toBe(CANON);
  });
});
