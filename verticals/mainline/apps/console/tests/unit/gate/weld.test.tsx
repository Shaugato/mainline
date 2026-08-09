// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE WELD DIAGRAM.
 *
 * The claims under test, in order of how much they matter:
 *
 *   1. every constraint the payload declares appears, by name, with the CHECK
 *      expression the catalog reported and the counters it reads;
 *   2. a zero counter and a zero nobody computed are DISTINGUISHABLE — in the DOM, not
 *      only in the stylesheet, so the distinction survives a screenshot and a
 *      screen reader;
 *   3. `unmodelled_asset_count` with no boundary certificate says UNKNOWN BLOCKS in
 *      those words (ARCHITECTURE.md §5.5, S11);
 *   4. a non-zero counter links to its witness rows, and a counter with no witness
 *      source on this screen says so rather than linking nowhere;
 *   5. the counters are INSTRUMENT-register elements — declared on the tree, where a
 *      Playwright spec and a captured DOM can both read the law that applied.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WeldDiagram } from '../../../src/features/gate/WeldDiagram';
import { buildWeld, type BlockingChecksData } from '../../../src/features/gate/model';
import type { Permit } from '../../../src/data/types.generated';
import { sourcePayload } from './_support';

interface Envelope<T> {
  readonly provenance: readonly { readonly pointer: string; readonly chip: string }[];
  readonly data: T;
}

const permitEnvelope = sourcePayload<Envelope<Permit>>('permit.json');
const checksEnvelope = sourcePayload<Envelope<BlockingChecksData>>('blocking-checks.json');
const permit = permitEnvelope.data;
const checks = checksEnvelope.data.checks;
const provenance = permitEnvelope.provenance as never;

function renderWeld(subject: Permit = permit, rows: typeof checks | null = checks): void {
  const weld = buildWeld({ permit: subject, checks: rows, blamedConstraint: 'gate_closed_when_issued' });
  render(<WeldDiagram weld={weld} permit={subject} provenance={provenance} checks={rows} />);
}

describe('the named refusals', () => {
  it('renders one row per constraint the payload declares, by name', () => {
    renderWeld();
    for (const constraint of permit.constraints) {
      const row = screen.getByTestId(`weld-row-${constraint.constraint}`);
      expect(row.dataset.constraint).toBe(constraint.constraint);
    }
  });

  it('renders the CHECK expression verbatim, and never reconstructs a missing one', () => {
    renderWeld();
    for (const constraint of permit.constraints) {
      const row = screen.getByTestId(`weld-row-${constraint.constraint}`);
      if (constraint.predicate === null || constraint.predicate === undefined) continue;
      expect(row.textContent).toContain(constraint.predicate);
    }

    const stripped: Permit = {
      ...permit,
      constraints: permit.constraints.map((constraint) => ({ ...constraint, predicate: null })),
    };
    renderWeld(stripped);
    const row = screen.getAllByTestId(`weld-row-${permit.constraints[0]?.constraint ?? ''}`)[1];
    expect(row?.textContent).toContain('not captured');
  });

  it('marks the constraint the refusal named', () => {
    renderWeld();
    const blamed = screen.getByTestId('weld-row-gate_closed_when_issued');
    expect(blamed.dataset.blamed).toBe('true');
    expect(blamed.textContent).toContain('named by the refusal');

    const other = screen.getByTestId('weld-row-merge_evidence');
    expect(other.dataset.blamed).toBe('false');
  });

  it('says a constraint over non-counter columns reads no projected counter', () => {
    renderWeld();
    const row = screen.getByTestId('weld-row-merge_evidence');
    expect(row.textContent).toContain('reads no projected counter');
  });

  it('declares the INSTRUMENT register on the tree', () => {
    renderWeld();
    expect(screen.getByTestId('weld').dataset.register).toBe('instrument');
  });
});

describe('the three counter states', () => {
  it('renders the value the database wrote, for every counter', () => {
    renderWeld();
    for (const constraint of permit.constraints) {
      for (const entry of constraint.counters) {
        const node = screen.getByTestId(`counter-${entry.column}`);
        expect(node.textContent).toContain(String(entry.value));
      }
    }
  });

  it('marks a non-zero counter as blocking and links it to its witness rows', () => {
    renderWeld();
    const node = screen.getByTestId('weld-counter-open_blocking');
    expect(node.dataset.counterState).toBe('blocking');
    for (const check of checks.filter((entry) => entry.open)) {
      expect(node.querySelector(`a[href="#gate-check-${check.check_id}"]`)).not.toBeNull();
    }
  });

  it('distinguishes a witnessed zero from an unwitnessed one in the DOM', () => {
    renderWeld();
    // unmodelled_asset_count is zero AND has a certificate behind it.
    expect(screen.getByTestId('weld-counter-unmodelled_asset_count').dataset.counterState).toBe(
      'clear',
    );
    // open_residue is zero and this screen carries nothing that says what was examined.
    expect(screen.getByTestId('weld-counter-open_residue').dataset.counterState).toBe(
      'unwitnessed-zero',
    );
    expect(screen.getByTestId('weld-counter-open_residue').textContent).toContain(
      'witness rows not carried',
    );
  });

  it('never reports a counter as clear when the checks read has not landed', () => {
    renderWeld(permit, null);
    expect(screen.getByTestId('weld-counter-open_blocking').textContent).toContain(
      'witness rows not carried',
    );
  });
});

describe('S11 — an uncounted asset graph is UNKNOWN, and unknown blocks', () => {
  it('says UNKNOWN BLOCKS when the boundary certificate is absent', () => {
    const withoutCertificate: Permit = { ...permit, boundary_certificate: null };
    renderWeld(withoutCertificate);

    const notice = screen.getByTestId('unknown-blocks');
    expect(notice.textContent).toContain('UNKNOWN BLOCKS');
    expect(notice.textContent).toContain('NOT SAFE');
    expect(screen.getByTestId('weld-counter-unmodelled_asset_count').dataset.counterState).toBe(
      'unwitnessed-zero',
    );
    expect(screen.getByTestId('boundary-certificate').textContent).toContain(
      'no boundary certificate',
    );
  });

  it('says nothing of the kind when a certificate is present', () => {
    renderWeld();
    expect(screen.queryByTestId('unknown-blocks')).toBeNull();
    const certificate = permit.boundary_certificate;
    if (certificate === null || certificate === undefined) throw new Error('fixture has none');
    const block = screen.getByTestId('boundary-certificate');
    expect(block.textContent).toContain(certificate.asset_graph_version);
    expect(block.textContent).toContain(String(certificate.tags_declared));
  });
});

describe('holes are named rather than dropped', () => {
  it('reports a projected column no constraint in the payload reads', () => {
    const trimmed: Permit = {
      ...permit,
      constraints: permit.constraints.filter(
        (constraint) => !constraint.counters.some((entry) => entry.column === 'open_warrants'),
      ),
    };
    renderWeld(trimmed);
    expect(screen.getByTestId('weld-unread').textContent).toContain('open_warrants');
  });

  it('reports an empty constraint list as an absence, not as a clean gate', () => {
    renderWeld({ ...permit, constraints: [] });
    const empty = screen.getByTestId('weld-empty');
    expect(empty.textContent).toContain('no constraints in this payload');
  });
});
