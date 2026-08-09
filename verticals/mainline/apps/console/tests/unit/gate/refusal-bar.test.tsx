// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE REFUSAL BAR.
 *
 * Every expected string here is read out of the EvidenceBundle frame, decoded from the
 * captured response body — the same bytes the transport serves. Nothing is retyped, and
 * the mutation cases below change the fixture and require the rendering to change with
 * it. That is the only way this file can distinguish a component that renders the
 * payload from a component that renders a constant.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RefusalBar } from '../../../src/features/gate/RefusalBar';
import { readRefusal } from '../../../src/features/gate/model';
import type { InvokeResult } from '../../../src/data/types.generated';
import { bundleFiles, frameEnvelope, mergeFramePath } from './_support';

interface Envelope {
  readonly provenance: readonly { readonly pointer: string; readonly chip: string }[];
  readonly data: InvokeResult;
}

const files = bundleFiles();
const envelope = frameEnvelope<Envelope>(files, mergeFramePath());

function refusalFromBundle(): NonNullable<InvokeResult['refusal']> {
  const read = readRefusal(envelope.data.refusal);
  if (!read.ok) throw new Error(`the bundle's refusal is unreadable: ${read.reason}`);
  return read.refusal;
}

const refusal = refusalFromBundle();
const provenance = envelope.provenance as never;

describe('a refusal the database issued', () => {
  it('renders the constraint name the BUNDLE carries, verbatim', () => {
    render(<RefusalBar state={{ kind: 'refused', refusal }} provenance={provenance} />);

    const node = screen.getByTestId('refusal-constraint');
    expect(node.dataset.constraint).toBe(refusal.constraint);
    expect(node.textContent).toContain(refusal.constraint);
    // Mono, selectable text — never an image and never a pseudo-element.
    expect(node.tagName).toBe('CODE');
  });

  it('renders the SQLSTATE the BUNDLE carries, and does not translate it', () => {
    render(<RefusalBar state={{ kind: 'refused', refusal }} provenance={provenance} />);

    expect(screen.getByTestId('refusal-sqlstate').textContent).toContain(refusal.sqlstate);
    expect(screen.getByTestId('refusal-bar').dataset.sqlstate).toBe(refusal.sqlstate);
  });

  it('follows the payload when the constraint name changes — nothing is hardcoded', () => {
    const renamed = { ...refusal, constraint: 'boundary_certified_when_issued' };
    expect(renamed.constraint).not.toBe(refusal.constraint);

    const view = render(
      <RefusalBar state={{ kind: 'refused', refusal: renamed }} provenance={provenance} />,
    );
    expect(screen.getByTestId('refusal-constraint').dataset.constraint).toBe(
      renamed.constraint,
    );
    expect(view.container.textContent).not.toContain(refusal.constraint);
  });

  it('follows the payload when the SQLSTATE changes', () => {
    const other = { ...refusal, sqlstate: '23503' as const };
    render(<RefusalBar state={{ kind: 'refused', refusal: other }} provenance={provenance} />);
    expect(screen.getByTestId('refusal-bar').dataset.sqlstate).toBe('23503');
  });

  it('announces a SQLSTATE outside spec/errors.md’s closed set as outside it', () => {
    // Not a value the schema admits; the point is that the taxonomy is closed and the
    // component says so rather than rendering an unknown code as an ordinary refusal.
    const strange = { ...refusal, sqlstate: '42P01' as unknown as typeof refusal.sqlstate };
    render(<RefusalBar state={{ kind: 'refused', refusal: strange }} provenance={provenance} />);
    expect(screen.getByTestId('refusal-bar').textContent).toContain('OUTSIDE THE TAXONOMY');
  });

  it('renders the database message verbatim and composes none of its own', () => {
    render(<RefusalBar state={{ kind: 'refused', refusal }} provenance={provenance} />);
    expect(screen.getByTestId('refusal-message').textContent).toBe(refusal.message);
  });

  it('renders the subject and the gate epoch the payload states', () => {
    render(<RefusalBar state={{ kind: 'refused', refusal }} provenance={provenance} />);
    const subject = screen.getByTestId('refusal-subject').textContent ?? '';
    expect(subject).toContain(refusal.subject_id);
    expect(subject).toContain(refusal.subject_kind);
    expect(screen.getByTestId('refusal-gate-epoch').textContent).toBe(String(refusal.gate_epoch));
  });

  it('reports the diagnosis method and the probe budget it consumed', () => {
    render(<RefusalBar state={{ kind: 'refused', refusal }} provenance={provenance} />);
    expect(screen.getByTestId('refusal-diagnosis').textContent).toBe(refusal.diagnosis);
  });
});

describe('constraint_source — a parsed diagnosis is a weakened one (C-4)', () => {
  it('says nothing extra when the driver reported the name', () => {
    expect(refusal.constraint_source).toBe('reported');
    render(<RefusalBar state={{ kind: 'refused', refusal }} provenance={provenance} />);
    expect(screen.queryByTestId('refusal-parsed')).toBeNull();
  });

  it('announces a parsed constraint name as a weakened diagnosis', () => {
    const parsed = { ...refusal, constraint_source: 'parsed' as const };
    render(<RefusalBar state={{ kind: 'refused', refusal: parsed }} provenance={provenance} />);
    const notice = screen.getByTestId('refusal-parsed');
    expect(notice.textContent).toContain('WEAKENED DIAGNOSIS');
    expect(notice.textContent).toContain('constraint_source');
  });
});

describe('the states that are not refusals', () => {
  it('says nothing has been refused before an attempt', () => {
    render(<RefusalBar state={{ kind: 'none' }} provenance={provenance} />);
    const bar = screen.getByTestId('refusal-bar');
    expect(bar.dataset.state).toBe('none');
    expect(bar.textContent).toContain('nothing has been refused');
    // The absence of a refusal must not look like a refusal.
    expect(bar.dataset.constraint).toBeUndefined();
  });

  it('reports a committed transition as committed, not as a silent success', () => {
    render(
      <RefusalBar state={{ kind: 'committed', mergedCommit: 'ab'.repeat(32) }} provenance={provenance} />,
    );
    expect(screen.getByTestId('refusal-bar').textContent).toContain('committed');
  });

  it('reports SQLSTATE 40001 as undecided, with no reason set', () => {
    render(<RefusalBar state={{ kind: 'retry' }} provenance={provenance} />);
    const bar = screen.getByTestId('refusal-bar');
    expect(bar.dataset.state).toBe('retry');
    expect(bar.textContent).toContain('40001');
    expect(bar.textContent).toContain('UNDECIDED');
  });

  it('refuses to render an unreadable payload as a refusal, and names the missing field', () => {
    const broken = { ...(refusal as unknown as Record<string, unknown>) };
    delete broken.constraint;
    const read = readRefusal(broken);
    expect(read.ok).toBe(false);
    if (read.ok) return;

    render(<RefusalBar state={{ kind: 'defect', reason: read.reason }} provenance={provenance} />);
    const bar = screen.getByTestId('refusal-bar');
    expect(bar.dataset.state).toBe('defect');
    expect(bar.textContent).toContain('constraint');
    expect(bar.dataset.constraint).toBeUndefined();
  });

  it('reports a transport failure as a transport failure, not as a gate outcome', () => {
    render(
      <RefusalBar
        state={{ kind: 'failed', failure: 'missing_frame', detail: 'no such frame in bundle' }}
        provenance={provenance}
      />,
    );
    const bar = screen.getByTestId('refusal-bar');
    expect(bar.dataset.state).toBe('failed');
    expect(bar.textContent).toContain('no such frame in bundle');
    expect(bar.textContent).toContain('not a refusal');
  });
});
