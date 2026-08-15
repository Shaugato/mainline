// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE HEADER — the four things an industry judge checks in the first ten seconds.
 *
 * The assertion that matters most here is the one a careless implementation passes by
 * accident and a helpful one breaks on purpose: **`dispositioned` renders verbatim**.
 * `docs/demo/operator-systems-plan.md` R10 forbids translating it, because it is a real
 * value of `mainline.subject_state` (`0011_type_subject_state.sql:27-35`) and rendering
 * "Pending approval" in its place would invent a status vocabulary this system does not
 * have. The temptation is real — "Pending approval" reads better to a lay judge — so the
 * test names the specific strings that must NOT appear.
 *
 * The permit fixture below is shaped like the seeded row but is not it: no identifier,
 * digest or timestamp from the real world is written into this tree (plan §6). The values
 * here are obviously-synthetic stand-ins whose only job is to be echoed.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import type { Permit, ProvenanceChip } from '../../../../src/data/types.generated';
import {
  DEFAULT_PERMIT_TYPE_ID,
  PERMIT_TYPES,
  renderPermitHeader,
  SUBJECT_STATE_ALPHABET,
} from '../../../../src/operator/permit/header';
import type { ChipLookup } from '../../../../src/operator/permit/typed-fields';

const PERMIT: Permit = {
  permit_id: 'permit-uuid-under-test',
  site_id: 'site-uuid-under-test',
  site_code: 'site-code-under-test',
  external_ref: 'REF-UNDER-TEST',
  ref_name: 'refs/permits/under-test',
  parent_permit_id: null,
  state: 'dispositioned',
  head_seq: 2,
  gate_epoch: 1,
  merged_commit: null,
  under_hold: false,
  slice_digest: null,
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
  constraints: [],
  boundary_certificate: null,
  merge_record: null,
};

/** Claims exactly the pointers the live permit read claims, and nothing else. */
const CLAIMED = new Set([
  '/permit_id',
  '/site_id',
  '/external_ref',
  '/ref_name',
  '/state',
  '/head_seq',
  '/gate_epoch',
  '/merged_commit',
  '/under_hold',
  '/opened_at',
  '/horizon_at',
  '/site_code',
]);

const lookup: ChipLookup = (pointer) => (CLAIMED.has(pointer) ? 'db:column' : null);
const noChips: ChipLookup = () => null;

let root: HTMLElement;

beforeEach(() => {
  root = renderPermitHeader({ permit: PERMIT, lookup }).root;
});

describe('the status chip renders mainline.subject_state VERBATIM (R10)', () => {
  it('shows the enum value the database returned, character for character', () => {
    const chip = root.querySelector('.cow-state-chip');
    expect(chip?.textContent).toBe('dispositioned');
    expect(chip?.getAttribute('data-state')).toBe('dispositioned');
  });

  it('does not translate the state into a status vocabulary this system does not have', () => {
    const text = root.textContent ?? '';
    for (const invented of [
      'Pending approval',
      'Pending Approval',
      'Awaiting approval',
      'Approved',
      'Ready for issue',
      'In progress',
    ]) {
      expect(text).not.toContain(invented);
    }
  });

  it('shows the enum alphabet on screen, with suspension distinct from closed', () => {
    // Fidelity checklist item 6. HSG250 ¶19: "a suspended permit remains live until it is
    // cancelled" — a screen that collapses the two can lose track of a live isolation.
    const values = [...root.querySelectorAll('.cow-state-value')].map((n) => n.textContent);
    expect(values).toEqual([...SUBJECT_STATE_ALPHABET]);
    expect(values).toContain('suspended');
    expect(values).toContain('closed');
    expect(values.indexOf('suspended')).not.toBe(values.indexOf('closed'));
  });

  it('marks which value of the alphabet this permit currently holds', () => {
    const current = root.querySelectorAll('.cow-state-value[data-current="true"]');
    expect(current).toHaveLength(1);
    expect(current[0]?.textContent).toBe(PERMIT.state);
  });

  it('offers the gloss on hover, as the enum alphabet rather than as a translation', () => {
    const chip = root.querySelector('.cow-state-chip');
    const title = chip?.getAttribute('title') ?? '';
    expect(title).toContain('mainline.subject_state');
    for (const value of SUBJECT_STATE_ALPHABET) {
      expect(title).toContain(value);
    }
    // The gloss is available on demand; it never appears in the word's place.
    expect(chip?.textContent).toBe(PERMIT.state);
  });
});

describe('the reference number, the branch and the validity window', () => {
  it('renders external_ref as the permit reference number, chipped', () => {
    const ref = root.querySelector('.cow-ref');
    expect(ref?.textContent).toBe(PERMIT.external_ref);
    const chip = root.querySelector('.cow-hdr-ref-line .cow-chip');
    expect(chip?.getAttribute('data-pointer')).toBe('/external_ref');
  });

  it('keeps ref_name in the header as a secondary line — a permit that is a git ref', () => {
    const branch = root.querySelector('.cow-branch');
    expect(branch?.textContent).toBe(PERMIT.ref_name);
    expect(root.querySelector('.cow-hdr-branch .cow-chip')).not.toBeNull();
  });

  it('carries a validity window — the classic tell is a permit with no expiry', () => {
    const pointers = [...root.querySelectorAll('.cow-chip')].map((node) =>
      node.getAttribute('data-pointer'),
    );
    expect(pointers).toContain('/opened_at');
    expect(pointers).toContain('/horizon_at');

    const times = [...root.querySelectorAll('time')].map((node) => node.getAttribute('datetime'));
    expect(times).toContain(PERMIT.opened_at);
    expect(times).toContain(PERMIT.horizon_at);
  });

  it('renders gate_epoch and head_seq from the row', () => {
    const pointers = [...root.querySelectorAll('.cow-chip')].map((node) =>
      node.getAttribute('data-pointer'),
    );
    expect(pointers).toContain('/gate_epoch');
    expect(pointers).toContain('/head_seq');
  });
});

describe('the permit type is the operator’s selection, never the database’s claim', () => {
  it('is a control, not a value, and carries no provenance chip', () => {
    const select = root.querySelector<HTMLSelectElement>('#cow-permit-type');
    expect(select).not.toBeNull();
    expect(select?.tagName).toBe('SELECT');
    expect(select?.getAttribute('data-typed')).toBe('operator');
    expect(select?.closest('.cow-hdr-type')?.querySelector('.cow-chip')).toBeNull();
  });

  it('defaults to cold work and paints the edge blue — HSG250 Table 2, not red', () => {
    const select = root.querySelector<HTMLSelectElement>('#cow-permit-type');
    expect(select?.value).toBe(DEFAULT_PERMIT_TYPE_ID);
    expect(root.getAttribute('data-permit-type')).toBe('cold-work');

    const edge = root.querySelector<HTMLElement>('.cow-edge');
    expect(edge?.style.background).toContain('--cow-edge-cold');
    expect(edge?.style.background).not.toContain('--cow-edge-hot');
  });

  it('repaints the edge when the supervisor changes the type', () => {
    const select = root.querySelector<HTMLSelectElement>('#cow-permit-type');
    if (select === null) {
      throw new Error('no permit type control');
    }
    select.value = 'hot-work';
    select.dispatchEvent(new Event('change'));

    const edge = root.querySelector<HTMLElement>('.cow-edge');
    expect(edge?.style.background).toContain('--cow-edge-hot');
    expect(root.getAttribute('data-permit-type')).toBe('hot-work');
  });

  it('offers HSG250 Table 2’s document types', () => {
    const labels = [...root.querySelectorAll('#cow-permit-type option')].map(
      (node) => node.textContent,
    );
    expect(labels).toEqual(PERMIT_TYPES.map((type) => type.label));
  });
});

describe('a chip with no backing pointer does not render', () => {
  it('renders every value and no chip at all when the envelope claimed nothing', () => {
    const bare = renderPermitHeader({ permit: PERMIT, lookup: noChips }).root;
    expect(bare.querySelectorAll('.cow-chip')).toHaveLength(0);
    // The values are still there. Absence of corroboration is not absence of the value.
    expect(bare.querySelector('.cow-ref')?.textContent).toBe(PERMIT.external_ref);
    expect(bare.querySelector('.cow-state-chip')?.textContent).toBe(PERMIT.state);
    // And the screen says the reference number went unchipped rather than hiding it.
    expect(bare.querySelector('.cow-unchipped')).not.toBeNull();
  });

  it('never invents a chip kind the lookup did not return', () => {
    const kinds = new Set<ProvenanceChip | null>();
    for (const node of root.querySelectorAll('.cow-chip')) {
      kinds.add(node.getAttribute('data-chip') as ProvenanceChip | null);
    }
    expect([...kinds]).toEqual(['db:column']);
  });
});

describe('the header exposes a mount point rather than owning the print control', () => {
  it('offers an actions slot', () => {
    const { actions } = renderPermitHeader({ permit: PERMIT, lookup });
    expect(actions.className).toContain('cow-hdr-actions');
    expect(actions.childElementCount).toBe(0);
  });
});
