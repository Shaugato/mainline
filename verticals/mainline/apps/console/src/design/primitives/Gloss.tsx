// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Gloss — a plain sentence BESIDE a verbatim value, never inside it.
 *
 * Ruling R8 is absolute and this component is its shape: `message`, `constraint`,
 * `sqlstate`, `detail`, `naa.description`, `mus[].detail`, `unreachable[].probe`,
 * `attribution`, `statement`, `predicate` are rendered exactly as the kernel emitted them,
 * in the mono face, through `Mono` / `Sqlstate` / `ConstraintName`. This component does
 * not touch them. It renders them untouched as its children and puts the console's own
 * sentence next to them, in the sans face, where a reader can see which words are whose.
 *
 * ── WHY THE GLOSS IS ALWAYS PAINTED, AND IS NEVER A TOOLTIP ──────────────────────
 *
 * The obvious implementation is a `title=` attribute, or a hover popover, or a small "?"
 * that reveals on focus. All three are refused here:
 *
 *   • `title=` is not reachable by keyboard in any major browser, is not announced
 *     reliably, and is not in a screenshot;
 *   • a hover reveal is not reachable by keyboard at all; and
 *   • **any reveal is a state a screenshot cannot reproduce**, which is the EVIDENCE
 *     register law (`docs/leads/ui.md` §1.1) and the reason this console is hash-routed in
 *     the first place.
 *
 * So the gloss is plain text in the DOM, painted at all times, in document order
 * immediately after the value it explains. A screen reader reads "23514 — a CHECK
 * constraint written into the table was not satisfied" without any ARIA relationship
 * having to be declared, a keyboard user reaches it by reading, and a screenshot carries
 * it. This component sets no `title` attribute anywhere and
 * `plain-primitives.test.tsx` asserts that.
 *
 * ── WHEN THE VOCABULARY DOES NOT KNOW THE TERM ───────────────────────────────────
 *
 * It renders the value alone and marks itself `data-gloss-missing`. It does NOT fall back
 * to the slug, to the empty string, or to a sentence of its own: a definition-shaped blank
 * beside a verbatim value is the console claiming it has explained something it has not,
 * and the raw key rendered as prose would be console-composed text in the exact position a
 * reader has been taught to read as a definition.
 */

import { type ReactNode } from 'react';

import { glossFor, sqlstateGloss } from '../glossary';
import styles from './plain.module.css';

export interface GlossProps {
  /**
   * The verbatim value. Rendered untouched, in whatever element the caller passed —
   * `<Mono>`, `<Sqlstate>`, `<ConstraintName>`, `<Digest>`.
   */
  readonly children: ReactNode;
  /** A key from `src/design/glossary.ts` — a product word or a glossed term. */
  readonly term?: string;
  /**
   * A SQLSTATE, glossed from the map in `glossary.ts`. Takes precedence over `term`,
   * because a screen that passes both is asking about this specific code.
   */
  readonly sqlstate?: string;
  /**
   * `inline` sets the gloss on the same line, wrapping. `stack` sets it underneath — for
   * a long value, a table cell, or a gloss under a heading.
   */
  readonly layout?: 'inline' | 'stack';
  readonly className?: string;
  readonly 'data-testid'?: string;
}

/** The em dash that leads a gloss in, rendered as real text so a copy carries it. */
const LEAD = '—';

export function Gloss({
  children,
  term,
  sqlstate,
  layout = 'inline',
  className,
  'data-testid': testId,
}: GlossProps): ReactNode {
  const resolved =
    sqlstate === undefined ? null : sqlstateGloss(sqlstate);
  const text = resolved ?? (term === undefined ? null : glossFor(term));
  const missing = text === null ? (sqlstate ?? term ?? '(no term given)') : undefined;

  return (
    <span
      className={className === undefined ? styles.glossPair : `${styles.glossPair} ${className}`}
      data-layout={layout}
      data-gloss-term={term}
      data-gloss-sqlstate={sqlstate}
      data-gloss-missing={missing}
      data-testid={testId}
    >
      <span className={styles.glossSubject}>{children}</span>
      {text === null ? null : (
        <span className={styles.glossText}>
          <span className={styles.glossLead}>{LEAD} </span>
          {text}
        </span>
      )}
    </span>
  );
}
