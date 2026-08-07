// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PRIMITIVES.
 *
 * Every assertion here is about a REFUSAL the component makes, not about how it looks:
 *
 *   • a verbatim value is real, selectable, complete text — never truncated in the DOM,
 *     never an image;
 *   • a constraint name is rendered exactly as the database spelled it;
 *   • a SQLSTATE outside `spec/errors.md`'s closed set is announced as outside it;
 *   • the copy control reports what actually happened, including failure;
 *   • a Counter does not move in the EVIDENCE register and its end state is identical
 *     either way;
 *   • the Meter has no colour that means "you failed"; and
 *   • the severity band's NAME is always present, with no prop that removes it.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  ConstraintName,
  Counter,
  Digest,
  Meter,
  Mono,
  ProvenanceChip,
  RegisterFrame,
  Rule,
  SeverityBand,
  Sqlstate,
  StagedBadge,
  VerificationSeal,
} from '../../../src/design/primitives';
import { PROVENANCE_KINDS } from '../../../src/design/provenance';
import { VIRULENCE_CLASSES } from '../../../src/design/severity';
import { sqlstateClass } from '../../../src/design/sqlstate';

describe('Mono', () => {
  it('renders a <code> with the value verbatim and selectable', () => {
    render(<Mono data-testid="m">gate_closed_when_issued</Mono>);
    const node = screen.getByTestId('m');
    expect(node.tagName).toBe('CODE');
    expect(node.textContent).toBe('gate_closed_when_issued');
  });

  it('announces a staged value as staged', () => {
    render(
      <Mono staged data-testid="m">
        7
      </Mono>,
    );
    expect(screen.getByTestId('m').textContent).toContain('staged value');
    expect(screen.getByTestId('m').dataset.staged).toBe('true');
  });
});

describe('ConstraintName', () => {
  it('renders the identifier exactly as given — no case change, no prettifying', () => {
    render(<ConstraintName name="gate_closed_when_issued" data-testid="c" />);
    const node = screen.getByTestId('c');
    expect(node.dataset.constraint).toBe('gate_closed_when_issued');
    expect(node.textContent).toContain('gate_closed_when_issued');
    expect(node.textContent).not.toContain('Gate Closed');
  });

  it('carries the refusal tone when it is the subject of the refusal', () => {
    render(<ConstraintName name="fk_clearance" tone="refuse" data-testid="c" />);
    expect(screen.getByTestId('c').dataset.tone).toBe('refuse');
  });
});

describe('Sqlstate', () => {
  it('classifies every code in the closed set spec/errors.md §1 defines', () => {
    expect(sqlstateClass('40001')).toBe('retry');
    expect(sqlstateClass('23514')).toBe('refuse');
    expect(sqlstateClass('23503')).toBe('refuse');
    expect(sqlstateClass('23505')).toBe('refuse');
    expect(sqlstateClass('P0001')).toBe('refuse');
    // 42501 is excluded from the gate taxonomy BY DEFINITION: the writer was refused by
    // the grant graph or an RLS policy before any gate condition was evaluated, so it is
    // an authorisation error and must never be shown as a gate refusal.
    expect(sqlstateClass('42501')).toBe('deny');
    expect(sqlstateClass('00000')).toBe('admit');
  });

  it('says so, loudly, when a code is outside the taxonomy', () => {
    render(<Sqlstate code="23502" data-testid="s" />);
    // 23502 means a NOT NULL projected column was left unset by a trigger — a defect,
    // not an edge case. Rendering it as an ordinary refusal would hide a broken projection.
    expect(document.body.textContent).toContain('OUTSIDE THE TAXONOMY');
  });

  it('renders the code verbatim in mono', () => {
    render(<Sqlstate code="23514" data-testid="s" />);
    expect(screen.getByTestId('s').textContent).toContain('23514');
    expect(screen.getByTestId('s').tagName).toBe('CODE');
  });
});

describe('Digest', () => {
  const VALUE = '3a91f0c2b47e5d18aa6c0f39e2b7145c8d0e6a2f4b9c1d3e5f7a9b0c2d4e6f81';

  it('keeps the WHOLE value in the DOM — the truncation is a paint, not a cut', () => {
    render(<Digest value={VALUE} label="checkpoint root" data-testid="d" />);
    const code = screen.getByTestId('d').querySelector('code');
    expect(code?.textContent).toBe(VALUE);
    expect(code?.dataset.full).toBe(VALUE);
  });

  it('is focusable, so a keyboard reader can expand it', () => {
    render(<Digest value={VALUE} label="commit" data-testid="d" />);
    expect(screen.getByTestId('d').querySelector('code')?.tabIndex).toBe(0);
  });

  it('names what it is copying, because "Copy" is useless when six are on screen', () => {
    render(<Digest value={VALUE} label="manifest sha256" data-testid="d" />);
    expect(screen.getByRole('button', { name: 'Copy manifest sha256' })).toBeInTheDocument();
  });

  it('reports a successful copy', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    render(<Digest value={VALUE} label="commit" data-testid="d" />);
    await userEvent.click(screen.getByRole('button', { name: 'Copy commit' }));

    expect(writeText).toHaveBeenCalledWith(VALUE);
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('copied');
    });
  });

  it('reports a FAILED copy rather than going quiet', async () => {
    // Silence after pressing "copy" is the console asserting something it does not know.
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error('denied by permissions policy')),
      },
    });

    render(<Digest value={VALUE} label="commit" data-testid="d" />);
    await userEvent.click(screen.getByRole('button', { name: 'Copy commit' }));

    await waitFor(() => {
      const status = screen.getByRole('status');
      expect(status.textContent).toContain('copy failed');
      expect(status.textContent).toContain('denied by permissions policy');
      expect(status.dataset.status).toBe('failed');
    });
  });

  it('says the environment offers no clipboard, which is a different fix', async () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });

    render(<Digest value={VALUE} label="commit" data-testid="d" />);
    await userEvent.click(screen.getByRole('button', { name: 'Copy commit' }));

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('no clipboard API');
    });
  });
});

describe('ProvenanceChip', () => {
  it('offers exactly the four kinds and no fifth', () => {
    expect([...PROVENANCE_KINDS]).toEqual(['db:column', 'db:constraint', 'recomputed', 'staged']);
  });

  it('shows `unspecified` rather than an empty slot when the detail is missing', () => {
    // An empty slot looks like a chip that had nothing to say; `unspecified` looks like a
    // caller who did not fill it in. Different bugs; only one is visible.
    render(<ProvenanceChip kind="db:column" data-testid="p" />);
    expect(screen.getByTestId('p').textContent).toContain('unspecified');
  });

  it('renders the source when it is given', () => {
    render(<ProvenanceChip kind="db:column" detail="permit.open_blocking" data-testid="p" />);
    expect(screen.getByTestId('p').textContent).toContain('permit.open_blocking');
  });
});

describe('VerificationSeal', () => {
  it('renders the recomputation beside a verified seal', () => {
    render(
      <VerificationSeal
        state="verified"
        subject="checkpoint signature"
        recomputation={{
          algorithm: 'ECDSA P-256 over the C2SP checkpoint note',
          at: '2026-08-04T02:11:44Z',
          digestPrefix: '3a91f0c2b47e',
        }}
        data-testid="seal"
      />,
    );
    const node = screen.getByTestId('seal');
    expect(node.dataset.state).toBe('verified');
    expect(node.textContent).toContain('ECDSA P-256');
    expect(node.textContent).toContain('3a91f0c2b47e');
  });

  it('distinguishes unverified from failed', () => {
    const { unmount } = render(
      <VerificationSeal state="unverified" subject="bundle" reason="no bundle loaded" data-testid="s" />,
    );
    expect(screen.getByTestId('s').dataset.state).toBe('unverified');
    expect(screen.getByTestId('s').textContent).toContain('no recomputation has been run');
    unmount();

    render(
      <VerificationSeal
        state="failed"
        subject="bundle"
        reason="leaf hash at index 41 does not match the inclusion proof"
        data-testid="f"
      />,
    );
    expect(screen.getByTestId('f').dataset.state).toBe('failed');
    expect(screen.getByTestId('f').textContent).toContain('index 41');
  });

  it('cannot be verified without a recomputation — enforced by the prop type', () => {
    // The following is a COMPILE error, which is the enforcement. `tsc --noEmit` runs in
    // CI before this suite does, so the line below is checked by the type-checker rather
    // than by a runtime assertion:
    //
    //     <VerificationSeal state="verified" subject="x" />
    //     //               ^ Property 'recomputation' is missing
    //
    // @ts-expect-error state="verified" requires `recomputation`
    const illegal = <VerificationSeal state="verified" subject="x" />;
    expect(illegal).toBeTruthy();
  });
});

describe('SeverityBand', () => {
  it.each([...VIRULENCE_CLASSES])('renders the band NAME for %s, always', (virulence) => {
    render(<SeverityBand virulence={virulence} data-testid="b" />);
    const node = screen.getByTestId('b');
    expect(node.dataset.virulence).toBe(virulence);
    // Colour never carries the band alone: a photocopied exhibit, a dichromat, and a
    // screenshot that outlives the stylesheet all need the word.
    expect(node.textContent).toContain(virulence);
  });

  it('spells the value the way the column spells it', () => {
    render(<SeverityBand virulence="blood_fatal" data-testid="b" />);
    expect(screen.getByTestId('b').textContent).toContain('blood_fatal');
    expect(screen.getByTestId('b').textContent).not.toContain('Critical');
  });

  it('shows severity as a separate fact when it is given, and omits it otherwise', () => {
    const { unmount } = render(<SeverityBand virulence="blood_fatal" severity={5} data-testid="b" />);
    expect(screen.getByTestId('b').textContent).toContain('5');
    unmount();
    render(<SeverityBand virulence="blood_fatal" data-testid="n" />);
    expect(screen.getByTestId('n').textContent).not.toMatch(/sev/);
  });
});

describe('StagedBadge', () => {
  it('says what is staged and what would change it', () => {
    render(<StagedBadge what="not yet POSTed to sign_disposition" data-testid="s" />);
    expect(screen.getByTestId('s').textContent).toContain('not written, not refused, not signed');
    expect(screen.getByTestId('s').textContent).toContain('sign_disposition');
  });
});

describe('Counter and the register it is rendered into', () => {
  it('does not mark a change in the EVIDENCE register', () => {
    const { rerender } = render(
      <RegisterFrame register="evidence">
        <Counter value={1} label="open blocking checks" data-testid="c" />
      </RegisterFrame>,
    );
    rerender(
      <RegisterFrame register="evidence">
        <Counter value={0} label="open blocking checks" data-testid="c" />
      </RegisterFrame>,
    );
    const value = screen.getByTestId('c').firstElementChild as HTMLElement;
    expect(value.dataset.transition).toBeUndefined();
    // The end state is what matters and it is identical either way.
    expect(value.textContent).toBe('0');
  });

  it('marks a downward change in the INSTRUMENT register — the transition IS the fact', async () => {
    const { rerender } = render(
      <RegisterFrame register="instrument">
        <Counter value={1} label="open blocking checks" data-testid="c" />
      </RegisterFrame>,
    );
    rerender(
      <RegisterFrame register="instrument">
        <Counter value={0} label="open blocking checks" data-testid="c" />
      </RegisterFrame>,
    );
    const value = screen.getByTestId('c').firstElementChild as HTMLElement;
    await waitFor(() => {
      expect(value.dataset.transition).toBe('down');
    });
    expect(value.textContent).toBe('0');
  });

  it('never tweens the value — a rolling counter displays numbers nobody reported', () => {
    const { rerender } = render(
      <RegisterFrame register="instrument">
        <Counter value={7} label="checks" data-testid="c" />
      </RegisterFrame>,
    );
    rerender(
      <RegisterFrame register="instrument">
        <Counter value={0} label="checks" data-testid="c" />
      </RegisterFrame>,
    );
    expect((screen.getByTestId('c').firstElementChild as HTMLElement).textContent).toBe('0');
  });

  it('defaults to EVIDENCE outside any frame', () => {
    render(<Counter value={3} label="checks" data-testid="c" />);
    expect(screen.getByTestId('c').dataset.register).toBe('evidence');
  });
});

describe('Meter', () => {
  it('is a real ARIA meter with units in its value text', () => {
    render(<Meter value={4} max={10} floor={6} label="tokens dispositioned" units="tokens" />);
    const meter = screen.getByRole('meter', { name: 'tokens dispositioned' });
    expect(meter.getAttribute('aria-valuenow')).toBe('4');
    expect(meter.getAttribute('aria-valuemax')).toBe('10');
    expect(meter.getAttribute('aria-valuetext')).toBe('4 tokens of 10, floor 6');
  });

  it('marks the floor as a position, never as a verdict about the reader', () => {
    render(<Meter value={2} max={10} floor={6} label="reading floor" data-testid="m" />);
    const floor = screen.getByTestId('m').querySelector('[data-floor="true"]');
    expect(floor).not.toBeNull();
    // There is no `data-failing`, no `data-below-floor` and no colour that means "you
    // failed". The consequence is stated in words by the surface that owns the meter.
    expect(screen.getByTestId('m').querySelector('[data-failing]')).toBeNull();
    expect(screen.getByTestId('m').querySelector('[data-below-floor]')).toBeNull();
  });

  it('clamps rather than overflowing when the value exceeds the max', () => {
    render(<Meter value={99} max={10} label="elapsed" data-testid="m" />);
    const fill = screen.getByTestId('m').querySelector<HTMLElement>('[class*="meterFill"]');
    expect(fill).not.toBeNull();
    expect(fill?.style.getPropertyValue('--meter-fraction')).toBe('100.000%');
  });
});

describe('RegisterFrame', () => {
  it('writes the register onto the DOM, so a screenshot carries the law it applied', () => {
    render(
      <RegisterFrame register="memory" data-testid="f">
        <span>walk</span>
      </RegisterFrame>,
    );
    expect(screen.getByTestId('f').dataset.register).toBe('memory');
  });

  it('renders a labelled landmark when asked', () => {
    render(
      <RegisterFrame register="evidence" as="section" label="Refusal" data-testid="f">
        <span>x</span>
      </RegisterFrame>,
    );
    expect(screen.getByRole('region', { name: 'Refusal' })).toBeInTheDocument();
  });
});

describe('Rule', () => {
  it('hides a decorative separator from assistive technology and announces a section break', () => {
    const { unmount } = render(<Rule data-testid="r" />);
    expect(screen.getByTestId('r').getAttribute('aria-hidden')).toBe('true');
    unmount();
    render(<Rule variant="section" data-testid="s" />);
    expect(screen.getByTestId('s').getAttribute('aria-hidden')).toBeNull();
  });
});
