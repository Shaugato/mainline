// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * NOT BUILT YET (D8).
 *
 * The cut ladder (BUILD_PLAN §10.2) is executed by deleting directories. A deleted
 * surface must therefore produce a screen that says, in the product's own voice, what
 * was promised, which milestone owed it, and what the reader has instead — not a blank
 * pane, not a 404, and above all not silence.
 *
 * BUILD_PLAN §10.2 cut 2 says the sibling-site propagation beat becomes "spec only,
 * named in NOT-BUILT-YET". This component is the named thing.
 *
 * ── THE FIRST SENTENCE (2026-08-15) ──────────────────────────────────────────────
 *
 * The card used to open on a badge, a title and then a `<dl>` of surface id, milestone,
 * owner and expected path — four facts that are exact and none of which answers the
 * question a first-time reader actually has, which is *has something gone wrong?*. It
 * had not: the two links that reach this card are `declared-missing` on purpose, and the
 * console keeps them in the navigation rather than quietly dropping them, because a
 * promise you can still see is a promise somebody can hold us to.
 *
 * So the card now opens with one plain sentence saying that, and naming the milestone
 * that owes the screen. It adds no claim: what the screen will show is `entry.promise`,
 * quoted verbatim from the console's own promise list a few lines further down, and the
 * milestone is `entry.milestone` from the same list. Nothing was removed to make room —
 * the badge, the metadata, the promise and the verbatim reason are all still here, in
 * that order.
 */

import { type ReactNode } from 'react';

import styles from './shell.module.css';
import { type SurfaceEntry } from './surfaces';

export function NotBuiltYet({
  entry,
  reason,
}: {
  readonly entry: SurfaceEntry;
  /** Verbatim. If a module failed to import, this is the import error's own message. */
  readonly reason: string;
}): ReactNode {
  return (
    <section className={styles.notBuilt} data-testid="not-built-yet" data-surface={entry.id}>
      <p className={styles.notBuiltBadge}>NOT BUILT YET</p>
      <h2 className={styles.notBuiltTitle}>{entry.title}</h2>

      <p className={styles.notBuiltPromise} data-testid="not-built-plain">
        Nothing has gone wrong. This screen has not been built yet; what it will show is written
        below, under <em>What this screen owes you</em>, and the work that owes it is{' '}
        <code>{entry.milestone}</code>. The link stays in the navigation so the promise stays
        visible.
      </p>

      <dl className={styles.notBuiltMeta}>
        <dt>surface</dt>
        <dd>
          <code>{entry.id}</code> at <code>{entry.path}</code>
        </dd>
        <dt>milestone</dt>
        <dd>
          <code>{entry.milestone}</code>
        </dd>
        <dt>owner</dt>
        <dd>
          <code>{entry.owner}</code>
        </dd>
        <dt>expected at</dt>
        <dd>
          <code>src/features/{entry.id}/surface.tsx</code>
        </dd>
      </dl>

      <h3 className={styles.notBuiltSubhead}>What this screen owes you</h3>
      <p className={styles.notBuiltPromise}>{entry.promise}</p>

      <h3 className={styles.notBuiltSubhead}>Why you are seeing this instead</h3>
      <pre className={styles.verbatim}>{reason}</pre>

      <p className={styles.notBuiltNote}>
        This card is the product working. A surface that has been cut, or that has not landed,
        renders its own absence — because a console that quietly drops a promised screen is a
        console whose silences you cannot audit.
      </p>
    </section>
  );
}
