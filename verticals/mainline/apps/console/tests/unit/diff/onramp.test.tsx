// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ON-RAMP, HELD TO THE RULING THAT PUT IT THERE.
 *
 * `docs/leads/two-audience-ux-plan.md` R6 gives a two-audience screen exactly two
 * obligations, and both of them fail SILENTLY if nobody asserts them:
 *
 *   1. **COLLAPSED IS NOT REMOVED.** A worker who "collapses" a witness table by rendering
 *      it conditionally produces a screen that looks identical on arrival and has quietly
 *      lost an exhibit. Every assertion below therefore reaches INSIDE a closed `<details>`
 *      and demands the bytes: the two canonical texts, every unified run, every witness row
 *      and every stored column are in the DOM whether the disclosure is open or shut.
 *   2. **SOME THINGS MAY NOT COLLAPSE AT ALL.** R6 names them — a refusal, a stated
 *      absence, a provenance chip, a STAGED badge, a verdict. The comfortable mistake is to
 *      tidy one of those behind a click because the screen is long, and it is the one
 *      mistake this file exists to catch, so each is asserted to have no `<details>`
 *      ancestor at all.
 *
 * A third property is asserted because the founder's complaint was about reading level and
 * a reading level regresses without anybody noticing: the plain band may not contain a term
 * from the lead's own list of twenty-one (§0.4) that nothing has defined yet.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ClauseDiff } from '../../../src/features/diff/ClauseDiff';
import { buildClauseDiff } from '../../../src/features/diff/engine/build';
import type { ClauseDiffInput, ClauseVersion } from '../../../src/features/diff/model';

const CLAUSE = 'dead0000-0000-4000-8000-00000000beef';
const PARENT_COMMIT = '1a'.repeat(32);
const VERSION_COMMIT = '2b'.repeat(32);

const PARENT_TEXT =
  'Stored energy shall be isolated, locked and verified at zero at every accumulator in the ' +
  'isolated circuit before intrusive work begins.';
const VERSION_TEXT =
  'Stored energy shall be isolated, locked and verified at zero at the hydraulic power unit.';

function parentVersion(): ClauseVersion {
  return {
    clause_uuid: CLAUSE,
    gen: 4,
    commit_id: PARENT_COMMIT,
    site_id: 'dead0000-0000-4000-8000-000000000001',
    activity_root: 'A03-ISOLATING-STORED-ENERGY',
    parent_version: null,
    printed_label: '7.3.2(b)',
    ordinal: 732,
    canon_text: PARENT_TEXT,
    canon_version: 2,
    canon_sha256: '33'.repeat(32),
    anchor_set: ['HPU-0412', 'accumulator', 'responsible_engineer'],
    cat_key: 'cat:a',
    cat_json: { location: 'every_accumulator_in_circuit' },
    cat_confidence: 'ok',
    control_delta: 'strengthen',
    delta_basis: 'lattice',
    sev_max: 5,
    blood_size: 3,
  };
}

function childVersion(): ClauseVersion {
  return {
    ...parentVersion(),
    gen: 5,
    commit_id: VERSION_COMMIT,
    parent_version: PARENT_COMMIT,
    canon_text: VERSION_TEXT,
    canon_sha256: '44'.repeat(32),
    anchor_set: ['HPU-0412'],
    cat_key: 'cat:b',
    cat_json: { location: 'hydraulic_power_unit' },
    control_delta: 'weaken',
    blood_size: 4,
  };
}

function input(): ClauseDiffInput {
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
          note: 'The verification point moved from every accumulator to a single named unit.',
        },
      ],
      minimal: true,
    },
  };
}

/** The nearest enclosing `<details>`, or null when the node is in the open flow. */
function enclosingDetails(node: Element): HTMLDetailsElement | null {
  return node.closest('details');
}

describe('the panel opens in plain language', () => {
  it('renders a plain band before anything it computed', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    const band = screen.getByTestId('diff-plain-band');
    expect(band.textContent ?? '').toContain('A clause is the written rule');
    // It introduces the screen; it is not itself part of the evidence, and it is not
    // hidden behind the very click it exists to make unnecessary.
    expect(enclosingDetails(band)).toBeNull();
  });

  it('uses no term from the lead’s undefined-on-arrival list', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    const text = (screen.getByTestId('diff-plain-band').textContent ?? '').toLowerCase();
    // docs/leads/two-audience-ux-plan.md §0.4 — the twenty-one a first-time reader met
    // before anything defined them. Every one of them still ships; none of them opens.
    const UNDEFINED_ON_ARRIVAL = [
      'projection',
      'projected counter',
      'canonicalisation',
      'inclusion proof',
      'consistency proof',
      'gate epoch',
      'blame ancestry',
      'defeater',
      'closure generation',
      'virulence',
      'minimal unsatisfiable subset',
      'nearest admissible alternative',
      'the weld',
      'provenance chip',
      'sqlstate',
      'corpus root',
      'clock skew',
      'rfc ',
    ];
    for (const term of UNDEFINED_ON_ARRIVAL) {
      expect(text.includes(term), `the plain band opens with "${term}"`).toBe(false);
    }
  });

  it('glosses control_delta beside the value and never inside it', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    const value = screen.getByTestId('delta-verdict').querySelector('[data-delta]');
    expect(value).not.toBeNull();
    const glosses = screen.getAllByTestId('diff-gloss');
    for (const gloss of glosses) {
      expect(gloss.contains(value), 'a gloss swallowed the value it explains (R8)').toBe(false);
    }
    expect(glosses.some((gloss) => (gloss.textContent ?? '').includes('control_delta'))).toBe(true);
  });
});

describe('collapsed is not removed', () => {
  it('keeps both canonical texts and every unified run in the DOM while shut', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);

    const disclosure: HTMLDetailsElement = screen.getByTestId('diff-text-disclosure');
    expect(disclosure.open, 'the disclosure starts open, so nothing was collapsed').toBe(false);

    expect(screen.getByTestId('text-parent').textContent).toBe(PARENT_TEXT);
    expect(screen.getByTestId('text-version').textContent).toBe(VERSION_TEXT);

    // The exhibit property, asserted through the shut disclosure: the ancestor is
    // reassemblable from the runs, character for character.
    const parts: string[] = [];
    for (const node of screen.getByTestId('text-unified').querySelectorAll('[data-segment]')) {
      if (node.getAttribute('data-segment') !== 'added') {
        parts.push(node.getAttribute('data-text') ?? '');
      }
    }
    expect(parts.join('')).toBe(PARENT_TEXT);
  });

  it('keeps every witness row, anchor, structured field and stored column in the DOM', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);

    for (const id of [
      'diff-witness-disclosure',
      'diff-anchor-disclosure',
      'diff-cat-disclosure',
      'diff-scalar-disclosure',
      'diff-commits-disclosure',
    ]) {
      const disclosure: HTMLDetailsElement = screen.getByTestId(id);
      expect(disclosure.open, `${id} is not collapsed`).toBe(false);
    }

    // The database's own reason, verbatim, through a shut disclosure.
    expect(screen.getByTestId('delta-witnesses').textContent ?? '').toContain('R-SCOPE-NARROWED');
    // A dropped anchor — the thing `identity_residue` exists to record.
    expect(screen.getByTestId('anchor-residue').textContent ?? '').toContain('accumulator');
    // A stored column, both sides.
    expect(screen.getByTestId('scalar-columns').textContent ?? '').toContain('canon_sha256');
  });

  it('gives every disclosure a summary that says what is behind it', () => {
    const { container } = render(<ClauseDiff model={buildClauseDiff(input())} />);
    const summaries = [...container.querySelectorAll('summary')];
    expect(summaries.length).toBeGreaterThanOrEqual(5);
    for (const summary of summaries) {
      const label = (summary.textContent ?? '').trim();
      expect(label.length, 'an unlabelled disclosure').toBeGreaterThan(12);
      expect(/^(details|more|show more|advanced)$/i.test(label), `bare label "${label}"`).toBe(
        false,
      );
    }
  });
});

describe('what may never be collapsed', () => {
  it('leaves the verdict, its chips and the findings in the open flow', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} />);
    const verdict = screen.getByTestId('delta-verdict');
    expect(enclosingDetails(verdict), 'the verdict is behind a click').toBeNull();
    for (const chip of verdict.querySelectorAll('[data-provenance]')) {
      expect(enclosingDetails(chip), 'a provenance chip is behind a click').toBeNull();
    }
    expect(enclosingDetails(screen.getByTestId('unwitnessed'))).toBeNull();
  });

  it('leaves a stated absence in the open flow — WITNESS UNAVAILABLE stays visible', () => {
    const model = buildClauseDiff({
      ...input(),
      // `null`, not omitted: the payload carries the member and it says nothing. That is
      // the state the panel must render as WITNESS UNAVAILABLE rather than as "none".
      // `minimal` is a REQUIRED member of the delta the contract describes, and `null` is
      // its "the payload carried the member and it said nothing" value — the same reading
      // `witnesses: null` gets one line up. Omitting it did not compile.
      delta: { delta: 'weaken', basis: 'lattice', witnesses: null, minimal: null },
    });
    render(<ClauseDiff model={model} />);
    const witnesses = screen.getByTestId('delta-witnesses');
    expect(witnesses.textContent ?? '').toContain('WITNESS UNAVAILABLE');
    const absence = [...witnesses.querySelectorAll('p')].find((node) =>
      (node.textContent ?? '').includes('WITNESS UNAVAILABLE'),
    );
    expect(absence).toBeDefined();
    expect(absence === undefined ? null : enclosingDetails(absence)).toBeNull();
    // And the absent-member state is still a different string from the asserted-none one.
    expect(witnesses.textContent ?? '').not.toContain('NO WITNESSES');
  });

  it('leaves the STAGED badge in the open flow', () => {
    render(<ClauseDiff model={buildClauseDiff(input())} staged="fixture, not the database" />);
    expect(enclosingDetails(screen.getByTestId('diff-staged'))).toBeNull();
  });
});
