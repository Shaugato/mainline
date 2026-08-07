// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Mono — anything the database emitted verbatim.
 *
 * The mono face is the console's only signal for "this string is not ours". Prose is
 * sans; a value that came out of a column, a constraint, a plan fragment or an error is
 * mono. That distinction is the reason a reader can look at a refusal screen and know
 * which words to grep the schema for.
 *
 * It renders a `<code>` element, always with real selectable text. Never an image,
 * never a canvas, never a pseudo-element `content:` string — a verbatim value a reader
 * cannot copy into a bug report is a verbatim value that has been paraphrased by the
 * medium.
 */

import { type ReactNode } from 'react';

import a11y from './a11y.module.css';
import styles from './verbatim.module.css';

export interface MonoProps {
  /** The verbatim string. Rendered exactly as given; never trimmed, never re-cased. */
  readonly children: ReactNode;
  /**
   * Marks this value as one the CONSOLE produced rather than the database. It is
   * accepted so that a caller cannot silently pass one off as the other: a `staged`
   * value gets the same mono face but is announced as staged to assistive technology.
   */
  readonly staged?: boolean;
  readonly className?: string;
  /** Forwarded to the element, e.g. `data-testid` for the browser spec. */
  readonly 'data-testid'?: string;
}

export function Mono({
  children,
  staged = false,
  className,
  'data-testid': testId,
}: MonoProps): ReactNode {
  return (
    <code
      className={className === undefined ? styles.mono : `${styles.mono} ${className}`}
      data-staged={staged ? 'true' : undefined}
      data-testid={testId}
    >
      {staged ? <span className={a11y.visuallyHidden}>staged value: </span> : null}
      {children}
    </code>
  );
}
