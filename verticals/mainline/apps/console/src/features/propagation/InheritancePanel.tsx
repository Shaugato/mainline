// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * *"This resolution was later found wrong — and here is every site that inherited it."*
 *
 * ARCHITECTURE.md §5.9 names this as the thing `resolution_memory.origin_conflict` buys
 * that git's `rerere` cannot. It is a RELATIONSHIP, so it is rendered as one: one recorded
 * resolution, and beneath it every conflict that cited it and every site standing on it.
 * A reader who learns that a resolution was wrong reads the blast radius off this panel
 * instead of running a query nobody has written yet.
 *
 * ── THE HALF THIS CONSOLE CANNOT SHOW, SAID OUT LOUD ─────────────────────────────
 *
 * `mainline.resolution_memory.recalled_at` — the column that records that a resolution was
 * later FOUND WRONG — is not in `contracts/propagation.schema.json` v1.0. So the fan-out
 * is renderable and the recall flag is not.
 *
 * The dishonest version of this panel would render the fan-out under a heading like
 * "recalled resolutions" and let the reader supply the flag from context. This one names
 * the missing column, so an absent flag reads as *not carried* rather than as *not
 * recalled*. Recorded as a cross-domain note against the contract, where it can be fixed.
 */

import { type ReactNode } from 'react';

import { Mono } from '../../design/primitives';

import type { ResolutionInheritance } from './model';
import styles from './propagation.module.css';

export interface InheritancePanelProps {
  readonly inheritance: readonly ResolutionInheritance[];
}

export function InheritancePanel({ inheritance }: InheritancePanelProps): ReactNode {
  return (
    <section data-testid="inheritance-panel" aria-label="Resolution memory">
      <h2 className={styles.sectionTitle}>what inherited a recorded resolution</h2>
      <p className={styles.prose}>
        Every conflict below cites a row of <Mono>mainline.resolution_memory</Mono> through
        <Mono> merge_conflict.resolution_source</Mono>. Reading that back-pointer from the far
        end turns one sentence into one relationship: if a recorded resolution is later found
        wrong, this is the list of sites standing on it.
      </p>

      {inheritance.length === 0 ? (
        <p className={styles.panel} data-testid="inheritance-none">
          No conflict in this payload cites a recorded resolution. Nothing here inherited
          anything, which is a statement about these rows and not about the fleet.
        </p>
      ) : (
        <ul className={styles.conflicts} data-testid="inheritance-list">
          {inheritance.map((entry) => (
            <li
              key={entry.source}
              className={styles.inheritance}
              data-testid="inheritance"
              data-source={entry.source}
              data-inheritors={entry.siteIds.length}
            >
              <p>
                <span className={styles.kicker}>recorded resolution</span>
                <Mono data-testid="inheritance-source">{entry.source}</Mono>
              </p>
              <p className={styles.prose}>
                inherited by <Mono data-testid="inheritance-count">{entry.siteIds.length}</Mono>{' '}
                site(s), through <Mono>{entry.conflicts.length}</Mono> conflict row(s).
                {entry.originOnScreen
                  ? ' The originating conflict is itself in this payload.'
                  : ' The originating conflict is not in this payload; only the citation is.'}
              </p>
              <ul className={styles.siteChips}>
                {entry.siteIds.map((siteId) => (
                  <li key={siteId} className={styles.term} data-testid="inheritance-site">
                    <Mono>{siteId}</Mono>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}

      <p className={styles.note} data-testid="inheritance-limit">
        LIMIT, STATED: <Mono>mainline.resolution_memory.recalled_at</Mono> — the column that
        records that a resolution was later found wrong — is not carried by
        <Mono> propagation.schema.json</Mono> v1.0. This panel therefore shows who inherited
        what, and cannot show whether any of it has been recalled. An absent flag here means
        the column was not carried, never that the resolution is sound.
      </p>
    </section>
  );
}
