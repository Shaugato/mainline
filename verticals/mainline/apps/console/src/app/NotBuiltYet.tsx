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
