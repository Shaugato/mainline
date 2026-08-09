// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The canonical text: the column, and then the derivation.
 *
 * Both are on screen, in that order, and the badges say which is which:
 *
 *   `db:column`  — `clause_version.canon_text`, verbatim, complete, selectable. This is
 *                  the thing a reader copies into a bug report or an exhibit.
 *   `recomputed` — the unified token diff, worked out in THIS BROWSER from the two
 *                  strings above. Nothing in the database says these two runs correspond;
 *                  the correspondence is ours, and the badge says so.
 *
 * Keeping both makes the distinction checkable rather than decorative — a reader can
 * reassemble either column from the diff and compare it, character for character, with
 * the well above it. That is also why every run carries `data-text`: the browser spec
 * reassembles both sides from the DOM and fails if a single character went missing.
 *
 * Colour never carries the change. Removed runs are struck through and announced as
 * "removed"; added runs are underlined and announced as "added". The panel photocopies,
 * and it reads correctly to somebody using a screen reader alone (D14).
 */

import { type ReactNode } from 'react';

import { ProvenanceChip } from '../../../design/primitives';
import styles from '../diff.module.css';
import type { TextDiff } from '../model';

function Run({ kind, text }: { readonly kind: string; readonly text: string }): ReactNode {
  if (kind === 'removed') {
    return (
      <del className={styles.removed} data-segment="removed" data-text={text}>
        <span className={styles.visuallyHidden}>removed: </span>
        {text}
        <span className={styles.visuallyHidden}> end removed. </span>
      </del>
    );
  }
  if (kind === 'added') {
    return (
      <ins className={styles.added} data-segment="added" data-text={text}>
        <span className={styles.visuallyHidden}>added: </span>
        {text}
        <span className={styles.visuallyHidden}> end added. </span>
      </ins>
    );
  }
  return (
    <span className={styles.equal} data-segment="equal" data-text={text}>
      {text}
    </span>
  );
}

export function TextDiffView({
  diff,
  parentText,
  versionText,
  parentCommit,
  versionCommit,
}: {
  readonly diff: TextDiff;
  readonly parentText: string;
  readonly versionText: string;
  readonly parentCommit: string;
  readonly versionCommit: string;
}): ReactNode {
  return (
    <section className={styles.section} data-testid="text-diff" aria-labelledby="diff-text-head">
      <div className={styles.sectionHead}>
        <h3 className={styles.sectionTitle} id="diff-text-head">
          Canonical text
        </h3>
        <span className={styles.verdictLabel}>
          {diff.removedChars} removed · {diff.addedChars} added · {diff.equalChars} unchanged
        </span>
      </div>

      <p className={styles.note}>
        Offsets are into <code className={styles.mono}>canon_text</code> and nothing else. The
        two wells below are the columns as the database holds them; the unified rendering
        beneath them is this browser&rsquo;s arithmetic over those two strings.
      </p>

      {diff.degraded === null ? null : (
        <div className={styles.absence} data-testid="diff-degraded">
          <p className={styles.absenceHead}>Coarse diff</p>
          <p className={styles.absenceBody}>
            The differing middle of these two texts demands{' '}
            <code className={styles.mono}>{diff.degraded.demanded}</code> comparison cells and
            the budget is <code className={styles.mono}>{diff.degraded.budget}</code>. The two
            texts are shown as one removed block and one added block. Both columns are still
            complete and still reassemblable from this screen; what is missing is the
            word-level correspondence, not any text.
          </p>
        </div>
      )}

      <div className={styles.chips}>
        <ProvenanceChip kind="db:column" detail="clause_version.canon_text" />
      </div>

      <h4 className={styles.subtitle}>
        Ancestor <code className={styles.mono}>{parentCommit.slice(0, 12)}…</code>
      </h4>
      <div className={styles.text} data-testid="text-parent">
        {parentText}
      </div>

      <h4 className={styles.subtitle}>
        This version <code className={styles.mono}>{versionCommit.slice(0, 12)}…</code>
      </h4>
      <div className={styles.text} data-testid="text-version">
        {versionText}
      </div>

      <div className={styles.chips}>
        <ProvenanceChip kind="recomputed" detail="token diff over canon_text, in this browser" />
      </div>

      <div className={styles.text} data-testid="text-unified">
        {diff.segments.map((segment, index) => (
          <Run
            key={`${segment.kind}-${String(segment.fromStart)}-${String(segment.toStart)}-${index}`}
            kind={segment.kind}
            text={segment.text}
          />
        ))}
      </div>

      {diff.identical ? (
        <p className={styles.settled}>
          The two versions carry byte-identical <code className={styles.mono}>canon_text</code>.
        </p>
      ) : null}
    </section>
  );
}
