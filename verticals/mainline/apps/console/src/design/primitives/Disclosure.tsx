// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Disclosure — the collapse half of ruling R6.
 *
 * PLAIN collapses; it never removes. Predicates, digests, JSON pointers, SQL statements,
 * byte and row caps, hash tables, witness tables, canonicalisation detail and the RFC
 * citations go inside one of these. The refusal bar, the SQLSTATE, the constraint name, a
 * provenance chip, a STAGED badge, a SYNTHETIC marker and the honesty strip **never do** —
 * those are visible in both modes, always, and a worker who puts one of them in here has
 * hidden a fact PLAIN is required to show.
 *
 * ── THE FOUR PROPERTIES, AND WHY EACH IS BUILT THIS WAY ──────────────────────────
 *
 * 1. **Its children are in the DOM in both modes.** A native `<details>` clips the paint,
 *    not the text: the value is still selectable, still `Ctrl-F`-able (find-in-page opens a
 *    closed `<details>`), still in the accessibility tree's document order, and still
 *    printable — `plain.module.css` forces it open on paper. The alternative,
 *    conditionally rendering `{open && children}`, would make FULL DETAIL and PLAIN two
 *    different documents and would make a screenshot of one silently incomplete.
 *
 * 2. **It is open when detail mode is full.** It reads `useDetailMode()` itself rather
 *    than taking an `open` prop, so a feature worker writes `<Disclosure summary="…">` and
 *    the R6 rule holds without them having to remember it. A change of mode re-seeds the
 *    local state during render — the documented React pattern for deriving state from a
 *    changing input — so a reader who switches to FULL DETAIL sees every disclosure on the
 *    screen open, and switching back restores the collapsed reading.
 *
 * 3. **It is keyboard-operable, and the UA gives that for free.** `<summary>` is focusable
 *    and activates on Enter and Space with no `tabindex`, no `role`, no `aria-expanded` and
 *    no key handler of ours. Every one of those, hand-written, is a thing that can drift
 *    out of sync with the visual state; the UA's cannot.
 *
 * 4. **Its summary names what is inside it, in the reader's words.** R6: *"Show the exact
 *    check the database ran"*, never *"Details"*. That is enforced rather than requested —
 *    `REFUSED_SUMMARIES` and `summaryNamesItsContents()` live in `src/design/glossary.ts`,
 *    because a rule about words belongs with the words.
 *
 * ── WHY IT THROWS ON A GENERIC SUMMARY ───────────────────────────────────────────
 *
 * A disclosure labelled "Details" is a control that tells a reader nothing about whether
 * opening it is worth their time, and the entire argument of this plan is that the exact
 * material must be one deliberate click away rather than one hopeful click away. A lint
 * rule cannot see a string prop, and a code review catches it only if somebody looks. A
 * throw is caught by `app/ErrorBoundary.tsx`, is impossible to miss in the test that
 * renders the screen, and is the idiom `resources.ts` and `registers.ts` already use for a
 * law that must not be negotiable.
 */

import { useState, type ReactNode } from 'react';

import { useDetailMode } from '../../app/detail-mode';
import { REFUSED_SUMMARIES, summaryNamesItsContents } from '../glossary';
import styles from './plain.module.css';

export interface DisclosureProps {
  /**
   * What is inside, in the reader's words. A sentence or an imperative phrase, not a
   * category. Refused if it is empty or one of `REFUSED_SUMMARIES`.
   */
  readonly summary: string;
  /**
   * One short line about what a reader would learn by opening it. Optional, and set in
   * the faint ink beside the summary — it is a signpost, never a fact of its own.
   */
  readonly note?: string;
  /** The exact material. Always rendered into the DOM; the collapse clips the paint. */
  readonly children: ReactNode;
  /**
   * Open even in PLAIN. For material that is exact but short enough that collapsing it
   * costs a reader more than it saves. FULL DETAIL opens everything regardless.
   */
  readonly defaultOpen?: boolean;
  readonly className?: string;
  readonly 'data-testid'?: string;
}

export function Disclosure({
  summary,
  note,
  children,
  defaultOpen = false,
  className,
  'data-testid': testId,
}: DisclosureProps): ReactNode {
  // Every hook runs before the refusal below, unconditionally. A `throw` placed above
  // them would make the hook calls conditional on a code path — which is what
  // `react-hooks/rules-of-hooks` refuses, and it is right to: a component that sometimes
  // calls three hooks and sometimes none corrupts React's hook list for its siblings.
  const mode = useDetailMode();
  const openInMode = mode === 'full' || defaultOpen;

  const [open, setOpen] = useState(openInMode);
  const [seenMode, setSeenMode] = useState(mode);

  if (!summaryNamesItsContents(summary)) {
    throw new Error(
      `Disclosure: the summary ${JSON.stringify(summary)} names the control rather than what is ` +
        'inside it. Ruling R6 of docs/leads/two-audience-ux-plan.md: every disclosure summary ' +
        'names what is inside it in the reader\'s words — "Show the exact check the database ran" ' +
        '— never "Details". Refused summaries: ' +
        REFUSED_SUMMARIES.join(', ') +
        '.',
    );
  }

  if (seenMode !== mode) {
    // Re-seed from the mode the moment the mode changes. Deriving state during render is
    // the documented React pattern for this and is cheaper and more predictable than an
    // effect, which would paint the stale state for one frame — and a frame of "collapsed"
    // after a reader pressed FULL DETAIL is a frame in which the screenshot is wrong.
    setSeenMode(mode);
    setOpen(openInMode);
  }

  return (
    <details
      className={className === undefined ? styles.disclosure : `${styles.disclosure} ${className}`}
      open={open}
      data-detail-mode={mode}
      data-testid={testId}
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
      }}
    >
      <summary
        className={styles.summary}
        onClick={(event) => {
          // The UA would toggle this itself. It is intercepted so the `open` prop stays
          // the single source of truth in every engine and in jsdom alike — a control
          // whose state lives in two places is a control that can be screenshotted in a
          // state React does not believe it is in.
          event.preventDefault();
          setOpen((current) => !current);
        }}
      >
        <span className={styles.affordance}>{open ? 'hide' : 'show'}</span>
        <span className={styles.summaryLabel}>{summary}</span>
        {note === undefined ? null : <span className={styles.summaryNote}>{note}</span>}
      </summary>
      <div className={styles.panel}>{children}</div>
    </details>
  );
}
