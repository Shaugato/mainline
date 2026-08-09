// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CLAUSE DIFF.
 *
 * The assertion that earns this file its place is the negative one: with
 * `witnesses: null`, the panel must render WITNESS UNAVAILABLE and must not contain a
 * single word of any witness note — not paraphrased, not summarised, not inferred. A
 * diff panel that explains a `weaken` verdict it cannot see the witnesses for is exactly
 * the fabrication `docs/leads/ui.md` §4 forbids.
 *
 * `null` and `[]` are asserted separately, because they are different claims.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ClauseDiff } from '../../../src/features/gate/ClauseDiff';
import type { ClauseData } from '../../../src/features/gate/model';
import { sourcePayload } from './_support';

interface Envelope<T> {
  readonly provenance: readonly { readonly pointer: string; readonly chip: string }[];
  readonly data: T;
}

const envelope = sourcePayload<Envelope<ClauseData>>('clause-version.json');
const clause = envelope.data;
const provenance = envelope.provenance as never;

function renderDiff(subject: ClauseData | null = clause): void {
  render(
    <ClauseDiff clause={subject} selection="named-by-reason-set" provenance={provenance} />,
  );
}

describe('the two canonical texts', () => {
  it('renders the ancestor and the descendant verbatim, side by side', () => {
    renderDiff();
    expect(screen.getByTestId('canon-current').textContent).toBe(clause.version.canon_text);
    expect(screen.getByTestId('canon-parent').textContent).toBe(clause.parent?.canon_text);
  });

  it('says the ancestor is not carried rather than reconstructing one', () => {
    renderDiff({ ...clause, parent: null });
    expect(screen.queryByTestId('canon-parent')).toBeNull();
    expect(screen.getByTestId('parent-absent').textContent).toContain('does not reconstruct');
  });

  it('renders nothing at all when no clause version arrived', () => {
    renderDiff(null);
    expect(screen.getByTestId('clause-diff-absent').textContent).toContain(
      'no clause version carried',
    );
  });
});

describe('the control delta and its basis', () => {
  it('renders the verdict and the basis the payload recorded', () => {
    renderDiff();
    expect(screen.getByTestId('control-delta').textContent).toBe(clause.delta.delta);
    expect(screen.getByTestId('delta-basis').textContent).toBe(clause.delta.basis);
  });

  it('marks a lattice basis as structurally re-derivable', () => {
    expect(clause.delta.basis).toBe('lattice');
    renderDiff();
    expect(screen.getByTestId('basis-strength').dataset.anchor).toBe('verbatim');
  });

  it('marks a model-assisted basis as not structurally re-derivable', () => {
    renderDiff({ ...clause, delta: { ...clause.delta, basis: 'lattice+model' } });
    expect(screen.getByTestId('basis-strength').dataset.anchor).toBe('gist');
  });

  it('says an abstention that defaulted to weaken is a default, not a finding', () => {
    renderDiff({ ...clause, delta: { ...clause.delta, basis: 'abstain_to_weaken' } });
    expect(screen.getByTestId('basis-note').textContent).toContain('not a finding');
  });

  it('reports unestablished minimality rather than implying it', () => {
    renderDiff({ ...clause, delta: { ...clause.delta, minimal: null } });
    expect(screen.getByTestId('minimality-unestablished').textContent).toContain(
      'not established',
    );
    expect(screen.queryByTestId('minimality')).toBeNull();
  });
});

describe('the witnesses', () => {
  it('renders every witness row verbatim', () => {
    renderDiff();
    const rows = screen.getAllByTestId('witness-row');
    const witnesses = clause.delta.witnesses ?? [];
    expect(rows).toHaveLength(witnesses.length);
    rows.forEach((row, index) => {
      const witness = witnesses[index];
      if (witness === undefined) throw new Error('fixture drift');
      expect(row.textContent).toContain(witness.rule_id);
      expect(row.textContent).toContain(witness.field);
      expect(row.textContent).toContain(witness.note);
    });
  });

  it('renders WITNESS UNAVAILABLE for null and infers absolutely nothing', () => {
    const view = render(
      <ClauseDiff
        clause={{ ...clause, delta: { ...clause.delta, witnesses: null } }}
        selection="named-by-reason-set"
        provenance={provenance}
      />,
    );

    expect(screen.getByTestId('witness-unavailable').textContent).toContain('witness unavailable');
    expect(screen.queryByTestId('witness-table')).toBeNull();

    // No rule id and no witness note may survive anywhere on the panel: those strings
    // exist ONLY in the witness rows, so their presence would mean the panel had kept a
    // copy of an explanation the payload no longer carries.
    for (const witness of clause.delta.witnesses ?? []) {
      expect(view.container.textContent).not.toContain(witness.rule_id);
      expect(view.container.textContent).not.toContain(witness.note);
    }

    // `from_repr` is asserted against the witness subtree only, because the same values
    // legitimately appear in the CAT comparison — which is derived from `cat_json`, not
    // from the witnesses, and is labelled as computed in this browser.
    const panel = screen.getByTestId('witnesses');
    for (const witness of clause.delta.witnesses ?? []) {
      if (witness.from_repr !== '') expect(panel.textContent).not.toContain(witness.from_repr);
    }
    // The verdict itself is still shown; it is the database's word, not an inference.
    expect(screen.getByTestId('control-delta').textContent).toBe(clause.delta.delta);
  });

  it('renders an empty array as the emitter asserting there are none', () => {
    renderDiff({ ...clause, delta: { ...clause.delta, witnesses: [] } });
    expect(screen.getByTestId('witness-asserted-none').textContent).toContain(
      'positive claim by the emitter',
    );
    expect(screen.queryByTestId('witness-unavailable')).toBeNull();
  });
});

/**
 * Anchor marks are read from the anchor panel's own subtree rather than by text search.
 * An anchor string such as `responsible_engineer` also occurs as a CAT value elsewhere on
 * the panel, and a document-wide text query would happily assert against the wrong node.
 */
function anchorMarks(): Map<string, string> {
  const marks = new Map<string, string>();
  for (const node of screen.getByTestId('anchor-delta').querySelectorAll('[data-change]')) {
    marks.set(node.textContent ?? '', (node as HTMLElement).dataset.change ?? '');
  }
  return marks;
}

describe('anchors and the Control Assertion Tuple', () => {
  it('marks every dropped anchor as removed', () => {
    renderDiff();
    const dropped = (clause.parent?.anchor_set ?? []).filter(
      (anchor) => !clause.version.anchor_set.includes(anchor),
    );
    expect(dropped.length).toBeGreaterThan(0);
    const marks = anchorMarks();
    for (const anchor of dropped) expect(marks.get(anchor)).toBe('removed');
    expect(screen.getByTestId('anchors-dropped').textContent).toContain(String(dropped.length));
  });

  it('keeps every surviving anchor visible, marked as kept', () => {
    renderDiff();
    const kept = clause.version.anchor_set.filter((anchor) =>
      (clause.parent?.anchor_set ?? []).includes(anchor),
    );
    expect(kept.length).toBeGreaterThan(0);
    const marks = anchorMarks();
    for (const anchor of kept) expect(marks.get(anchor)).toBe('kept');
  });

  it('reports the CAT paths that differ, and says the comparison is ours', () => {
    renderDiff();
    const rows = screen.getAllByTestId('cat-row');
    expect(rows.length).toBeGreaterThan(0);
    expect(screen.getByTestId('cat-delta').textContent).toContain('computed in this browser');
  });

  it('says so plainly when no CAT path differs', () => {
    renderDiff({
      ...clause,
      parent:
        clause.parent === null || clause.parent === undefined
          ? null
          : {
              ...clause.parent,
              ...(clause.version.cat_json === undefined
                ? {}
                : { cat_json: clause.version.cat_json }),
            },
    });
    expect(screen.getByTestId('cat-unchanged').textContent).toContain('No leaf path differs');
  });
});

describe('the selection rule is stated, never assumed', () => {
  it('says the clause was chosen because the reason set names it', () => {
    renderDiff();
    expect(screen.getByTestId('clause-diff').textContent).toContain(
      'minimal unsatisfiable subset names',
    );
  });

  it('says the fallback is a fallback', () => {
    render(<ClauseDiff clause={clause} selection="first-open-check" provenance={provenance} />);
    expect(screen.getByTestId('clause-diff').textContent).toContain(
      'not a claim that this clause is the reason',
    );
  });
});
