// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE MINIMAL UNSATISFIABLE SUBSET AND THE NEAREST ADMISSIBLE ALTERNATIVE.
 *
 * The assertions that matter are about ABSENCE, not presence:
 *
 *   • a `null` alternative renders an explicit not-computable state carrying the
 *     emitter's `naa_reason` verbatim — never a blank panel and never a guess;
 *   • `no_legal_verdict_exists` is rendered as a statement about the RULE, which
 *     `spec/wire/refusal.md` §4 makes mandatory ("A consumer MUST render it as a
 *     statement about the rule, never as a defect");
 *   • an `naa_reason` the specification does not declare is rendered verbatim and
 *     interpreted no further;
 *   • an empty `mus` is reported as a non-conformant payload rather than as "no reasons".
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ReasonSet } from '../../../src/features/gate/ReasonSet';
import { readRefusal } from '../../../src/features/gate/model';
import type { InvokeResult, RefusalPayload } from '../../../src/data/types.generated';
import { bundleFiles, frameEnvelope, mergeFramePath } from './_support';

interface Envelope {
  readonly provenance: readonly { readonly pointer: string; readonly chip: string }[];
  readonly data: InvokeResult;
}

const envelope = frameEnvelope<Envelope>(bundleFiles(), mergeFramePath());
const read = readRefusal(envelope.data.refusal);
if (!read.ok) throw new Error(`the bundle's refusal is unreadable: ${read.reason}`);
const refusal: RefusalPayload = read.refusal;
const provenance = envelope.provenance as never;

function withNaa(
  naa: RefusalPayload['naa'],
  reason: NonNullable<RefusalPayload['naa_reason']> | null,
): RefusalPayload {
  return { ...refusal, naa, naa_reason: reason };
}

describe('the reason set', () => {
  it('renders every atom the payload carries, in payload order', () => {
    render(<ReasonSet refusal={refusal} provenance={provenance} />);
    const atoms = screen.getAllByTestId('mus-atom');
    expect(atoms).toHaveLength(refusal.mus.length);
    atoms.forEach((node, index) => {
      expect(node.dataset.atomKind).toBe(refusal.mus[index]?.kind);
    });
  });

  it('renders each atom’s detail verbatim', () => {
    render(<ReasonSet refusal={refusal} provenance={provenance} />);
    const details = screen.getAllByTestId('mus-atom-detail').map((node) => node.textContent);
    for (const atom of refusal.mus) {
      if (atom.detail === undefined) continue;
      expect(details).toContain(atom.detail);
    }
  });

  it('states how the subset was obtained and what it cost', () => {
    const view = render(<ReasonSet refusal={refusal} provenance={provenance} />);
    expect(view.container.textContent).toContain(refusal.diagnosis);
    expect(view.container.textContent).toContain(String(refusal.probe_calls));
  });

  it('reports an empty mus as a non-conformant payload, not as "no reasons"', () => {
    render(<ReasonSet refusal={{ ...refusal, mus: [] }} provenance={provenance} />);
    const empty = screen.getByTestId('mus-empty');
    expect(empty.textContent).toContain('M-1');
    expect(screen.queryByTestId('mus-list')).toBeNull();
  });

  it('renders an authority gap with its relation and its key', () => {
    const gap: RefusalPayload = {
      ...refusal,
      mus: [
        {
          kind: 'authority_gap',
          relation: 'mainline.clearance_legal',
          key: { virulence: 'blood_fatal', kind: 'mechanism_absent' },
          detail: 'no row exists for this pair',
        },
      ],
    };
    const view = render(<ReasonSet refusal={gap} provenance={provenance} />);
    expect(screen.getByTestId('mus-atom').dataset.atomKind).toBe('authority_gap');
    expect(view.container.textContent).toContain('mainline.clearance_legal');
    expect(view.container.textContent).toContain('blood_fatal');
  });

  it('renders a capability gap with the required and observed values', () => {
    const gap: RefusalPayload = {
      ...refusal,
      mus: [
        {
          kind: 'capability_gap',
          capability: 'signer.rank',
          required_value: 4,
          observed_value: 2,
        },
      ],
    };
    const view = render(<ReasonSet refusal={gap} provenance={provenance} />);
    expect(view.container.textContent).toContain('signer.rank');
    expect(view.container.textContent).toContain('4');
    expect(view.container.textContent).toContain('2');
  });
});

describe('the nearest admissible alternative', () => {
  it('renders the alternative the payload carries, with its stated cardinality', () => {
    expect(refusal.naa).not.toBeNull();
    render(<ReasonSet refusal={refusal} provenance={provenance} />);

    const naa = refusal.naa;
    if (naa === null) return;
    expect(screen.getByTestId('naa-kind').textContent).toBe(naa.kind);
    expect(screen.getByTestId('naa-description').textContent).toBe(naa.description);
    if (naa.cardinality !== undefined) {
      expect(screen.getByTestId('naa-cardinality').textContent).toBe(String(naa.cardinality));
    }
  });

  it('says the cardinality is unstated rather than counting the array itself', () => {
    const naa = refusal.naa;
    if (naa === null) throw new Error('fixture carries no alternative');
    const withoutCardinality = { ...naa } as Record<string, unknown>;
    delete withoutCardinality.cardinality;

    render(
      <ReasonSet
        refusal={withNaa(withoutCardinality as unknown as typeof naa, null)}
        provenance={provenance}
      />,
    );
    expect(screen.getByTestId('naa-cardinality-absent').textContent).toContain('not stated');
    expect(screen.queryByTestId('naa-cardinality')).toBeNull();
  });

  it('renders an honest not-computable state when naa is null', () => {
    render(
      <ReasonSet refusal={withNaa(null, 'probe_budget_exhausted')} provenance={provenance} />,
    );
    const absent = screen.getByTestId('naa-absent');
    expect(absent.dataset.naaReason).toBe('probe_budget_exhausted');
    expect(absent.textContent).toContain('not computable');
    expect(screen.getByTestId('naa-gloss').textContent).toContain('oracle budget');
    expect(screen.queryByTestId('naa')).toBeNull();
  });

  it('renders no_legal_verdict_exists as a statement about the rule (§4)', () => {
    render(
      <ReasonSet refusal={withNaa(null, 'no_legal_verdict_exists')} provenance={provenance} />,
    );
    const absent = screen.getByTestId('naa-absent');
    expect(absent.textContent).toContain('no way to sign this away');
    expect(absent.textContent).toContain('the product working');
    // It must NOT be presented as an error or a failure of the diagnoser.
    expect(absent.textContent).not.toContain('not computable');
  });

  it('renders requires_human_authority without naming the authority to impersonate', () => {
    render(
      <ReasonSet refusal={withNaa(null, 'requires_human_authority')} provenance={provenance} />,
    );
    expect(screen.getByTestId('naa-gloss').textContent).toContain('impersonate');
  });

  it('reports a missing naa_reason as an emitter defect, and guesses nothing', () => {
    render(<ReasonSet refusal={withNaa(null, null)} provenance={provenance} />);
    const absent = screen.getByTestId('naa-absent');
    expect(absent.dataset.naaReason).toBe('unstated');
    expect(absent.textContent).toContain('defect in the emitter');
    expect(screen.queryByTestId('naa-gloss')).toBeNull();
  });

  it('renders an unknown naa_reason verbatim and interprets it no further', () => {
    const strange = 'because_we_felt_like_it' as unknown as NonNullable<
      RefusalPayload['naa_reason']
    >;
    const view = render(<ReasonSet refusal={withNaa(null, strange)} provenance={provenance} />);
    expect(view.container.textContent).toContain('because_we_felt_like_it');
    expect(view.container.textContent).toContain('outside the closed set');
    expect(screen.queryByTestId('naa-gloss')).toBeNull();
  });

  it('says the alternative is advice rather than authority', () => {
    const view = render(<ReasonSet refusal={refusal} provenance={provenance} />);
    expect(view.container.textContent).toContain('Advice, not authority');
  });
});
