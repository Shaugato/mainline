// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Digest — a hash, a commit id, a checkpoint root, a bundle manifest digest.
 *
 * Four properties, all of them load-bearing:
 *
 *   1. THE WHOLE VALUE IS ALWAYS IN THE DOM. The truncation is visual — a CSS clip with
 *      an ellipsis — so a select-all copies all sixty-four characters even while twelve
 *      are showing. A digest a reader cannot copy in full is a digest they cannot check,
 *      and a digest nobody can check is decoration.
 *   2. The prefix is what shows, because a prefix is what humans compare.
 *   3. Focus or hover releases the clip, and print releases it unconditionally: an
 *      exhibit that prints `3a91f0c2…` is not an exhibit.
 *   4. Copying reports what actually happened. `navigator.clipboard` is absent on
 *      insecure origins and can reject; both cases say so where a success would have
 *      appeared. Silence after pressing "copy" is the console asserting something it
 *      does not know.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

import a11y from './a11y.module.css';
import styles from './verbatim.module.css';

/** How long the copy result stays on screen. Under the EVIDENCE ceiling × 10; it is a
 *  status message, not a transition, and it must outlast a glance. */
const STATUS_MS = 2400;

export type CopyStatus = 'idle' | 'copied' | 'failed';

export interface DigestProps {
  /** The full value. Never truncated before it reaches this component. */
  readonly value: string;
  /**
   * What this digest IS — `commit`, `checkpoint root`, `manifest sha256`. Shown as a
   * label and used to build the copy button's accessible name, because "Copy" alone is
   * useless when six of them are on screen.
   */
  readonly label: string;
  /** Characters of prefix to show. 12 is the honesty chrome's convention (D16). */
  readonly prefixLength?: number;
  /** Renders the value expanded from the start — for the print exhibit and for tests. */
  readonly expanded?: boolean;
  /** Hide the copy control, e.g. inside a print-only exhibit block. */
  readonly copyable?: boolean;
  readonly 'data-testid'?: string;
}

export function Digest({
  value,
  label,
  prefixLength = 12,
  expanded = false,
  copyable = true,
  'data-testid': testId,
}: DigestProps): ReactNode {
  const [status, setStatus] = useState<CopyStatus>('idle');
  const [detail, setDetail] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );

  const armReset = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setStatus('idle');
      setDetail(null);
    }, STATUS_MS);
  }, []);

  const copy = useCallback(() => {
    const clipboard = typeof navigator === 'undefined' ? undefined : navigator.clipboard;
    if (clipboard === undefined) {
      // Not a failure of the copy; a failure of the environment to offer one. Saying so
      // is more useful than "copy failed", because the fix is different.
      setStatus('failed');
      setDetail('no clipboard API on this origin — select the value and copy it directly');
      armReset();
      return;
    }
    clipboard.writeText(value).then(
      () => {
        setStatus('copied');
        setDetail(null);
        armReset();
      },
      (error: unknown) => {
        setStatus('failed');
        setDetail(error instanceof Error ? error.message : String(error));
        armReset();
      },
    );
  }, [value, armReset, setStatus, setDetail]);

  // `ch` is the correct unit: the face is monospace, so N characters is exactly N ch.
  // One extra covers the ellipsis glyph itself.
  const clipWidth = `${prefixLength + 1}ch`;

  return (
    <span className={styles.digest} data-testid={testId} data-digest-label={label}>
      <span className={styles.digestLabel}>{label}</span>
      <code
        className={`${styles.mono} ${styles.digestValue}`}
        style={{ ['--digest-prefix-width' as string]: clipWidth }}
        data-expanded={expanded ? 'true' : 'false'}
        data-full={value}
        tabIndex={0}
      >
        {value}
      </code>
      {copyable ? (
        <button type="button" className={styles.digestCopy} onClick={copy} aria-label={`Copy ${label}`}>
          copy
        </button>
      ) : null}
      {/*
        A live region, so the outcome is announced rather than only shown. `polite`
        because a copy result must not interrupt a reader in the middle of a refusal.
      */}
      <span className={styles.digestStatus} data-status={status} role="status" aria-live="polite">
        {status === 'idle' ? (
          <span className={a11y.visuallyHidden}>{`${label}: ${value}`}</span>
        ) : status === 'copied' ? (
          'copied'
        ) : (
          `copy failed${detail === null ? '' : ` — ${detail}`}`
        )}
      </span>
    </span>
  );
}
