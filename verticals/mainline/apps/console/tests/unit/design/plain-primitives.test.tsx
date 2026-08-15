// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PLAIN-LANGUAGE PRIMITIVES — PlainBand, Disclosure, Gloss.
 *
 * Every assertion here is about a REFUSAL these components make, in the idiom
 * `primitives.test.tsx` already uses:
 *
 *   • a gloss goes BESIDE a verbatim value and never inside it, and it is real painted
 *     text rather than a `title=`, a tooltip or a hover reveal (R8);
 *   • a disclosure's children are in the DOM in BOTH modes, so a screenshot and a Ctrl-F
 *     both find them, and it is open when the address says `?detail=full` (R6);
 *   • a disclosure summary that names the control rather than the content is refused
 *     outright, not merely discouraged (R6);
 *   • a plain band takes at most three sentences and refuses a fourth (R6); and
 *   • the whole kit passes `src/a11y/audit.ts` with zero serious and zero critical
 *     findings (D14).
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { assertAccessible, audit } from '../../../src/a11y/audit';
import { isTabbable } from '../../../src/a11y/focus';
import { DetailModeContext, type DetailMode } from '../../../src/app/detail-mode';
import {
  Disclosure,
  Gloss,
  Mono,
  PlainBand,
  REFUSED_SUMMARIES,
  Sqlstate,
  summaryNamesItsContents,
} from '../../../src/design/primitives';

/** Renders `node` inside a detail mode, the way the shell publishes one. */
function renderIn(mode: DetailMode, node: ReactNode) {
  return render(<DetailModeContext value={mode}>{node}</DetailModeContext>);
}

/** The `<summary>` of a disclosure addressed by its test id, or a failure that says so. */
function summaryOf(testId: string): HTMLElement {
  const found = screen.getByTestId(testId).querySelector('summary');
  if (found === null) throw new Error(`disclosure "${testId}" rendered no <summary>.`);
  return found;
}

// ── Gloss ────────────────────────────────────────────────────────────────────────

describe('Gloss', () => {
  it('renders the verbatim value untouched, in its own element', () => {
    render(
      <Gloss term="constraint" data-testid="g">
        <Mono data-testid="v">gate_closed_when_issued</Mono>
      </Gloss>,
    );
    const value = screen.getByTestId('v');
    expect(value.tagName).toBe('CODE');
    expect(value.textContent).toBe('gate_closed_when_issued');
    // R8: the gloss is not inside the element carrying the kernel's string.
    expect(value.textContent).not.toContain('A rule written into the table');
  });

  it('puts the gloss beside the value, as text that is already painted', () => {
    render(
      <Gloss term="constraint" data-testid="g">
        <Mono>gate_closed_when_issued</Mono>
      </Gloss>,
    );
    expect(screen.getByTestId('g').textContent).toContain(
      'A rule written into the table itself, so no query can get around it.',
    );
  });

  it('never sets a title attribute — a tooltip is not keyboard-reachable and not in a screenshot', () => {
    const { container } = render(
      <Gloss sqlstate="23514" data-testid="g">
        <Sqlstate code="23514" />
      </Gloss>,
    );
    expect(container.querySelectorAll('[title]')).toHaveLength(0);
    expect(container.querySelectorAll('[aria-describedby]')).toHaveLength(0);
  });

  it('needs no interaction at all: the gloss is in the tree on first paint', async () => {
    const user = userEvent.setup();
    render(
      <Gloss sqlstate="P0001" data-testid="g">
        <Sqlstate code="P0001" />
      </Gloss>,
    );
    const before = screen.getByTestId('g').textContent ?? '';
    await user.tab();
    await user.hover(screen.getByTestId('g'));
    expect(screen.getByTestId('g').textContent).toBe(before);
    expect(before).toContain('a function raised its own named refusal');
  });

  it('glosses a SQLSTATE from the map, and lets it win over a term', () => {
    render(
      <Gloss sqlstate="23514" term="constraint" data-testid="g">
        <Sqlstate code="23514" />
      </Gloss>,
    );
    const node = screen.getByTestId('g');
    expect(node.textContent).toContain('a CHECK constraint written into the table was not satisfied');
    expect(node.textContent).not.toContain('so no query can get around it');
  });

  it('renders the value alone and says so when the vocabulary does not know the term', () => {
    render(
      <Gloss term="weld" data-testid="g">
        <Mono>the weld</Mono>
      </Gloss>,
    );
    const node = screen.getByTestId('g');
    expect(node.dataset.glossMissing).toBe('weld');
    expect(node.textContent).toBe('the weld');
  });

  it('invents no sentence for a SQLSTATE outside the taxonomy', () => {
    render(
      <Gloss sqlstate="99999" data-testid="g">
        <Sqlstate code="99999" />
      </Gloss>,
    );
    expect(screen.getByTestId('g').dataset.glossMissing).toBe('99999');
  });

  it('stacks under the value when asked, without changing a character of it', () => {
    render(
      <Gloss term="seal" layout="stack" data-testid="g">
        <Mono data-testid="v">NOT VERIFIED</Mono>
      </Gloss>,
    );
    expect(screen.getByTestId('g').dataset.layout).toBe('stack');
    expect(screen.getByTestId('v').textContent).toBe('NOT VERIFIED');
  });
});

// ── PlainBand ────────────────────────────────────────────────────────────────────

describe('PlainBand', () => {
  const THREE = [
    'This permit has one obligation still open against it.',
    'The database refused the merge and printed its own reason.',
    'Every exact value behind that sentence is one click away below.',
  ];

  it('renders every sentence it was given, in order', () => {
    render(<PlainBand kicker="the gate" sentences={THREE} data-testid="b" />);
    const band = screen.getByTestId('b');
    for (const sentence of THREE) expect(band.textContent).toContain(sentence);
    expect(within(band).getAllByText(/./, { selector: 'p' })).toHaveLength(3);
  });

  it('renders the SYNTHETIC marker slot above the sentences (R5)', () => {
    render(
      <PlainBand
        sentences={['This is a synthetic demonstration record.']}
        marker={<span data-testid="marker">SYNTHETIC</span>}
        data-testid="b"
      />,
    );
    const band = screen.getByTestId('b');
    const marker = screen.getByTestId('marker');
    const firstSentence = within(band).getByText('This is a synthetic demonstration record.');
    // A marker a reader meets after the narrative arrives too late to change how the
    // narrative was read, so it must precede it in document order.
    expect(marker.compareDocumentPosition(firstSentence) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it('refuses a fourth sentence rather than growing', () => {
    expect(() =>
      render(<PlainBand sentences={[...THREE, 'And one more thing.']} />),
    ).toThrow(/ceiling at 3/);
  });

  it('refuses an empty band and an empty sentence', () => {
    expect(() => render(<PlainBand sentences={[]} />)).toThrow(/no sentences/);
    expect(() => render(<PlainBand sentences={['a real one', '   ']} />)).toThrow(
      /empty sentence/,
    );
  });

  it('needs no kicker and no marker', () => {
    render(<PlainBand sentences={['One sentence is a legal band.']} data-testid="b" />);
    expect(screen.getByTestId('b').textContent).toBe('One sentence is a legal band.');
  });
});

// ── Disclosure ───────────────────────────────────────────────────────────────────

describe('Disclosure', () => {
  const SUMMARY = 'Show the exact check the database ran';

  it('puts its children in the DOM in PLAIN — collapsed clips the paint, not the text', () => {
    renderIn(
      'plain',
      <Disclosure summary={SUMMARY} data-testid="d">
        <Mono data-testid="predicate">open_blocking_projected = 0</Mono>
      </Disclosure>,
    );
    const details = screen.getByTestId('d');
    expect(details.tagName).toBe('DETAILS');
    expect(details.hasAttribute('open')).toBe(false);
    // In the DOM, findable, selectable, and present in a Ctrl-F — even while collapsed.
    expect(screen.getByTestId('predicate').textContent).toBe('open_blocking_projected = 0');
  });

  it('is OPEN when the detail mode is full, with the same children', () => {
    renderIn(
      'full',
      <Disclosure summary={SUMMARY} data-testid="d">
        <Mono data-testid="predicate">open_blocking_projected = 0</Mono>
      </Disclosure>,
    );
    expect(screen.getByTestId('d').hasAttribute('open')).toBe(true);
    expect(screen.getByTestId('predicate').textContent).toBe('open_blocking_projected = 0');
  });

  it('re-seeds when the mode changes, so FULL DETAIL opens what PLAIN collapsed', () => {
    const tree = (mode: DetailMode) => (
      <DetailModeContext value={mode}>
        <Disclosure summary={SUMMARY} data-testid="d">
          <Mono>open_blocking_projected = 0</Mono>
        </Disclosure>
      </DetailModeContext>
    );
    const { rerender } = render(tree('plain'));
    expect(screen.getByTestId('d').hasAttribute('open')).toBe(false);
    rerender(tree('full'));
    expect(screen.getByTestId('d').hasAttribute('open')).toBe(true);
    rerender(tree('plain'));
    expect(screen.getByTestId('d').hasAttribute('open')).toBe(false);
  });

  it('opens and closes from the keyboard, through the summary the UA already made focusable', async () => {
    const user = userEvent.setup();
    renderIn(
      'plain',
      <Disclosure summary={SUMMARY} data-testid="d">
        <Mono>open_blocking_projected = 0</Mono>
      </Disclosure>,
    );
    const details = screen.getByTestId('d');
    const summary = summaryOf('d');
    expect(isTabbable(summary)).toBe(true);

    await user.click(summary);
    expect(details.hasAttribute('open')).toBe(true);
    await user.click(summary);
    expect(details.hasAttribute('open')).toBe(false);
  });

  it('names what is inside it, and says show/hide in words rather than by a rotating glyph', async () => {
    const user = userEvent.setup();
    renderIn(
      'plain',
      <Disclosure summary={SUMMARY} note="the predicate and its counters" data-testid="d">
        <Mono>open_blocking_projected = 0</Mono>
      </Disclosure>,
    );
    const summary = summaryOf('d');
    expect(summary.textContent).toContain('show');
    expect(summary.textContent).toContain(SUMMARY);
    expect(summary.textContent).toContain('the predicate and its counters');
    await user.click(summary);
    expect(summary.textContent).toContain('hide');
  });

  it('opens in PLAIN when the caller says the material is short enough to leave open', () => {
    renderIn(
      'plain',
      <Disclosure summary={SUMMARY} defaultOpen data-testid="d">
        <Mono>open_blocking_projected = 0</Mono>
      </Disclosure>,
    );
    expect(screen.getByTestId('d').hasAttribute('open')).toBe(true);
  });

  it('refuses a summary that names the control instead of the content', () => {
    for (const refused of REFUSED_SUMMARIES) {
      expect(summaryNamesItsContents(refused), refused).toBe(false);
      expect(summaryNamesItsContents(`${refused.toUpperCase()}…`), refused).toBe(false);
    }
    expect(summaryNamesItsContents('   ')).toBe(false);
    expect(summaryNamesItsContents(SUMMARY)).toBe(true);
  });

  it('throws on "Details" rather than rendering it', () => {
    expect(() =>
      renderIn(
        'plain',
        <Disclosure summary="Details">
          <Mono>x</Mono>
        </Disclosure>,
      ),
    ).toThrow(/names the control rather than what is inside it/);
  });

  it('defaults to PLAIN outside any provider, which is the mode that hides nothing R6 forbids hiding', () => {
    render(
      <Disclosure summary={SUMMARY} data-testid="d">
        <Mono data-testid="predicate">open_blocking_projected = 0</Mono>
      </Disclosure>,
    );
    expect(screen.getByTestId('d').dataset.detailMode).toBe('plain');
    expect(screen.getByTestId('predicate')).toBeTruthy();
  });
});

// ── The whole kit, audited ───────────────────────────────────────────────────────

describe('D14 — zero serious, zero critical', () => {
  const kit = (
    <main>
      <PlainBand
        kicker="the gate"
        sentences={[
          'This permit has one obligation still open against it.',
          'The database refused the merge and printed its own reason.',
        ]}
        marker={<span>SYNTHETIC — this record corresponds to nobody.</span>}
      />
      <p>
        <Gloss sqlstate="23514">
          <Sqlstate code="23514" tone="refuse" />
        </Gloss>
      </p>
      <p>
        <Gloss term="minimal-unsatisfiable-subset" layout="stack">
          <Mono>mus</Mono>
        </Gloss>
      </p>
      <Disclosure summary="Show the exact check the database ran" note="the predicate">
        <Mono>open_blocking_projected = 0</Mono>
      </Disclosure>
    </main>
  );

  it.each(['plain', 'full'] as const)('passes the audit in %s mode', (mode) => {
    const { container } = renderIn(mode, kit);
    const report = assertAccessible(container, { label: `plain kit (${mode})` });
    expect(report.counts.serious).toBe(0);
    expect(report.counts.critical).toBe(0);
  });

  it('reports no moderate finding either, so nothing is being carried by shape alone', () => {
    const { container } = renderIn('plain', kit);
    const report = audit(container);
    expect(
      report.findings.map((finding) => `${finding.impact} ${finding.ruleId} ${finding.message}`),
    ).toEqual([]);
  });
});
