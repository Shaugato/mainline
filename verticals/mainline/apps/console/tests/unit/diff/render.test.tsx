// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PANEL — written RED, before `src/features/diff/ClauseDiff.tsx` existed.
 *
 * Every assertion below is about a REFUSAL or an ABSENCE, because those are the things a
 * screenshot cannot show you are missing:
 *
 *   • WITNESS UNAVAILABLE and "the emitter reports none" are DIFFERENT strings on screen.
 *     Collapsing them would turn a silence into a claim, and the payload contract says
 *     they are different claims;
 *   • a payload whose parent is the wrong commit renders NO `<ins>` and NO `<del>`. The
 *     refusal is the screen;
 *   • no provenance chip inside the witness table says `recomputed`, and the text diff's
 *     chip says exactly that. The console computed WHAT changed; the database said WHY,
 *     and the two are not allowed to wear each other's badge;
 *   • the full `canon_text` of BOTH versions is reconstructible from the DOM, because a
 *     diff a reader cannot reassemble into the clause is a summary, not an exhibit.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { validateSurfaceModule } from '../../../src/app/surfaces';
import { ClauseDiff } from '../../../src/features/diff/ClauseDiff';
import { buildClauseDiff } from '../../../src/features/diff/engine/build';
import type { ClauseDiffInput, ClauseVersion } from '../../../src/features/diff/model';
import * as surfaceModule from '../../../src/features/diff/surface';

const CLAUSE = '018f3a30-2200-7d10-9f31-0c9a4e77bb02';
const PARENT_COMMIT = 'aa'.repeat(32);
const VERSION_COMMIT = 'bb'.repeat(32);
const OTHER_COMMIT = 'cc'.repeat(32);

const PARENT_TEXT =
  'Residual stored energy shall be verified as zero at every accumulator in the isolated ' +
  'circuit, and countersigned by the responsible engineer.';
const VERSION_TEXT =
  'Residual stored energy shall be verified as zero at the hydraulic power unit.';

function parentVersion(overrides: Partial<ClauseVersion> = {}): ClauseVersion {
  return {
    clause_uuid: CLAUSE,
    gen: 4,
    commit_id: PARENT_COMMIT,
    site_id: '018f3a2e-0000-7000-8000-000000000001',
    activity_root: 'A03-ISOLATING-STORED-ENERGY',
    parent_version: null,
    printed_label: '7.3.2(b)',
    ordinal: 732,
    canon_text: PARENT_TEXT,
    canon_version: 2,
    canon_sha256: '11'.repeat(32),
    anchor_set: ['HPU-0412', 'accumulator', 'responsible_engineer'],
    cat_key: 'cat:a',
    cat_json: { location: 'every_accumulator_in_circuit', countersignature: 'responsible_engineer' },
    cat_confidence: 'ok',
    control_delta: 'strengthen',
    delta_basis: 'lattice',
    sev_max: 5,
    blood_size: 3,
    ...overrides,
  };
}

function childVersion(overrides: Partial<ClauseVersion> = {}): ClauseVersion {
  return {
    ...parentVersion(),
    gen: 5,
    commit_id: VERSION_COMMIT,
    parent_version: PARENT_COMMIT,
    canon_text: VERSION_TEXT,
    canon_sha256: '22'.repeat(32),
    anchor_set: ['HPU-0412'],
    cat_key: 'cat:b',
    cat_json: { location: 'hydraulic_power_unit' },
    control_delta: 'weaken',
    blood_size: 4,
    ...overrides,
  };
}

const WITNESS_NOTE =
  'The verification point moved from every accumulator in the isolated circuit to a single ' +
  'named unit. The 2004 mechanism is an accumulator downstream of the unit.';

function input(overrides: Partial<ClauseDiffInput> = {}): ClauseDiffInput {
  return {
    clauseUuid: CLAUSE,
    version: childVersion(),
    parent: parentVersion(),
    delta: {
      delta: 'weaken',
      basis: 'lattice',
      witnesses: [
        {
          rule_id: 'R-SCOPE-NARROWED',
          field: 'cat.location',
          from_repr: 'every_accumulator_in_circuit',
          to_repr: 'hydraulic_power_unit',
          note: WITNESS_NOTE,
        },
      ],
      minimal: true,
    },
    ...overrides,
  };
}

describe('ClauseDiff — the text is complete and reassemblable', () => {
  it('reproduces the ancestor’s canon_text from the equal and removed runs', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    const panel = screen.getByTestId('text-diff');
    const parts: string[] = [];
    for (const node of panel.querySelectorAll('[data-segment]')) {
      const kind = node.getAttribute('data-segment');
      if (kind !== 'added') parts.push(node.getAttribute('data-text') ?? '');
    }
    expect(parts.join('')).toBe(PARENT_TEXT);
  });

  it('reproduces this version’s canon_text from the equal and added runs', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    const panel = screen.getByTestId('text-diff');
    const parts: string[] = [];
    for (const node of panel.querySelectorAll('[data-segment]')) {
      const kind = node.getAttribute('data-segment');
      if (kind !== 'removed') parts.push(node.getAttribute('data-text') ?? '');
    }
    expect(parts.join('')).toBe(VERSION_TEXT);
  });

  it('uses <del> and <ins>, so the change survives a copy into a plain document', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    const panel = screen.getByTestId('text-diff');
    expect(panel.querySelectorAll('del').length).toBeGreaterThan(0);
    expect(panel.querySelectorAll('ins').length).toBeGreaterThan(0);
  });

  it('announces each run to a screen reader rather than relying on colour', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    const removed = screen.getByTestId('text-diff').querySelector('del');
    expect(removed?.textContent ?? '').toContain('removed');
  });
});

describe('ClauseDiff — the refusal to diff the wrong two rows', () => {
  it('renders no diff at all and says why, naming both commits', () => {
    const model = buildClauseDiff(input({ parent: parentVersion({ commit_id: OTHER_COMMIT }) }));
    render(<ClauseDiff model={model} />);

    expect(screen.queryByTestId('text-diff')).toBeNull();
    expect(document.querySelectorAll('ins')).toHaveLength(0);
    expect(document.querySelectorAll('del')).toHaveLength(0);

    const findings = screen.getByTestId('diff-findings');
    expect(findings.textContent).toContain(PARENT_COMMIT);
    expect(findings.textContent).toContain(OTHER_COMMIT);
  });

  it('still renders the verdict the database recorded', () => {
    const model = buildClauseDiff(input({ parent: parentVersion({ commit_id: OTHER_COMMIT }) }));
    render(<ClauseDiff model={model} />);
    expect(screen.getByTestId('delta-verdict').textContent).toContain('weaken');
  });
});

describe('ClauseDiff — silence and a claim of silence are different screens', () => {
  it('renders WITNESS UNAVAILABLE for a null witness member', () => {
    const model = buildClauseDiff(
      input({ delta: { delta: 'weaken', basis: 'lattice', witnesses: null, minimal: null } }),
    );
    render(<ClauseDiff model={model} />);
    const table = screen.getByTestId('delta-witnesses');
    expect(table.textContent).toContain('WITNESS UNAVAILABLE');
    expect(table.textContent).not.toContain('reports that there are none');
  });

  it('renders a DIFFERENT sentence when the emitter asserts there are none', () => {
    const model = buildClauseDiff(
      input({ delta: { delta: 'weaken', basis: 'lattice', witnesses: [], minimal: true } }),
    );
    render(<ClauseDiff model={model} />);
    const table = screen.getByTestId('delta-witnesses');
    expect(table.textContent).toContain('reports that there are none');
    expect(table.textContent).not.toContain('WITNESS UNAVAILABLE');
  });

  it('never invents an explanation when the witnesses are unavailable', () => {
    const model = buildClauseDiff(
      input({ delta: { delta: 'weaken', basis: 'lattice', witnesses: null, minimal: null } }),
    );
    render(<ClauseDiff model={model} />);
    // The observed changes are still shown; what must not appear is a reason for them.
    const unwitnessed = screen.getByTestId('unwitnessed');
    expect(unwitnessed.textContent?.toLowerCase()).not.toContain('because');
    expect(unwitnessed.textContent).toContain('canon_text');
  });
});

describe('ClauseDiff — the badge boundary', () => {
  const model = buildClauseDiff(input());

  it('marks the text diff as RECOMPUTED, because this browser computed it', () => {
    render(<ClauseDiff model={model} />);
    const chips = screen.getByTestId('text-diff').querySelectorAll('[data-kind]');
    expect([...chips].map((chip) => chip.getAttribute('data-kind'))).toContain('recomputed');
  });

  it('never marks a witness as recomputed — the reason is the database’s', () => {
    render(<ClauseDiff model={model} />);
    const table = screen.getByTestId('delta-witnesses');
    expect(table.querySelectorAll('[data-kind="recomputed"]')).toHaveLength(0);
    expect(table.querySelectorAll('[data-kind="db:column"]').length).toBeGreaterThan(0);
  });

  it('renders the witness note verbatim, with no truncation and no rewording', () => {
    render(<ClauseDiff model={model} />);
    expect(screen.getByTestId('delta-witnesses').textContent).toContain(WITNESS_NOTE);
  });

  it('renders the staged badge when the payload said it was staged', () => {
    render(<ClauseDiff model={model} staged="Hand-authored demonstration bundle." />);
    expect(screen.getByTestId('diff-staged').textContent).toContain('staged');
  });

  it('renders no staged badge when the payload did not say so', () => {
    render(<ClauseDiff model={model} />);
    expect(screen.queryByTestId('diff-staged')).toBeNull();
  });
});

describe('ClauseDiff — the residue and the gap', () => {
  const model = buildClauseDiff(input());

  it('lists every dropped anchor by name', () => {
    render(<ClauseDiff model={model} />);
    const anchors = screen.getByTestId('anchor-residue');
    expect(anchors.textContent).toContain('accumulator');
    expect(anchors.textContent).toContain('responsible_engineer');
  });

  it('lists the CAT pointers that changed', () => {
    render(<ClauseDiff model={model} />);
    expect(screen.getByTestId('cat-delta').textContent).toContain('/location');
  });

  it('lists the changes no witness accounts for', () => {
    render(<ClauseDiff model={model} />);
    const gap = screen.getByTestId('unwitnessed');
    expect(gap.textContent).toContain('/countersignature');
    expect(gap.textContent).toContain('canon_text');
  });

  it('says so plainly when every change is witnessed', () => {
    const complete = buildClauseDiff(
      input({
        delta: {
          delta: 'weaken',
          basis: 'lattice',
          witnesses: [
            { rule_id: 'R1', field: 'cat', from_repr: 'a', to_repr: 'b', note: 'n' },
            { rule_id: 'R2', field: 'anchor_set', from_repr: 'a', to_repr: '', note: 'n' },
            { rule_id: 'R3', field: 'canon_text', from_repr: 'a', to_repr: 'b', note: 'n' },
            { rule_id: 'R4', field: 'cat_key', from_repr: 'a', to_repr: 'b', note: 'n' },
          ],
          minimal: true,
        },
      }),
    );
    render(<ClauseDiff model={complete} />);
    expect(screen.getByTestId('unwitnessed').textContent).toContain(
      'Every change this browser observed is named by a witness row',
    );
  });
});

describe('ClauseDiff — accessibility and register', () => {
  it('declares the EVIDENCE register on the tree', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    expect(screen.getByTestId('clause-diff').dataset.register).toBe('evidence');
  });

  it('gives every table a caption', () => {
    const { container } = render(<ClauseDiff model={buildClauseDiff(input())} />);
    const tables = container.querySelectorAll('table');
    expect(tables.length).toBeGreaterThan(0);
    for (const table of tables) {
      expect(table.querySelector('caption')?.textContent?.trim() ?? '').not.toBe('');
    }
  });

  it('exposes the panel as a labelled landmark', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    expect(screen.getByRole('region', { name: /clause diff/i })).toBeInTheDocument();
  });
});

describe('the surface module', () => {
  it('satisfies the surface contract', () => {
    const validation = validateSurfaceModule('diff', surfaceModule);
    expect(validation.ok, validation.ok ? '' : validation.reason).toBe(true);
  });

  it('declares the EVIDENCE register and a milestone', () => {
    expect(surfaceModule.surface.register).toBe('evidence');
    expect(surfaceModule.surface.milestone).toMatch(/^K[0-9]+$/);
  });

  it('renders an honest absence rather than a blank pane when no transport is composed', () => {
    const { Component } = surfaceModule.surface;
    render(<Component />);
    const notice = screen.getByTestId('diff-no-transport');
    expect(notice.textContent).toContain('no transport');
    expect(within(notice).getByText(/clause_version/)).toBeInTheDocument();
  });
});
