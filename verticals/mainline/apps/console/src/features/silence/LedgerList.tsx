// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Every row of the silence ledger, in full.
 *
 * ARCHITECTURE.md §5.7 names the dark side of this table plainly: it is a complete list of
 * every warning the system chose not to give. The console renders it in full rather than as
 * a count, because a count is exactly the artefact that lets an organisation know the
 * number without ever reading the rows.
 *
 * ── A SCORE IS NEVER SHOWN ALONE ─────────────────────────────────────────────────
 *
 * `scoreDisplay` returns `withheld` when a score has no threshold or no policy version
 * beside it, and the row then renders a marker naming the missing companion instead of the
 * number. `0.31` on its own is an invitation to read it as a probability of harm; `0.31
 * against a threshold of 0.45 under BLK-07/recall@2026-07-18` is a fact somebody can
 * argue with. On this surface the second is the only form allowed.
 *
 * ── VOCABULARY IS VERBATIM ───────────────────────────────────────────────────────
 *
 * `source` and `reason` are rendered exactly as the CHECK constraints spell them —
 * `below_tau`, `dedup_sibling`, `bounded_negative`. A reader who greps the migrations for
 * the string on screen finds the constraint that admits it. Softening `below_tau` into
 * "scored too low" would put a translation layer between an exhibit and its schema.
 */

import { type ReactNode } from 'react';

import { Mono } from '../../design/primitives';

import { ArithmeticView } from './ArithmeticView';
import { scoreDisplay } from './model';
import { ProvenanceSlot } from './ProvenanceSlot';
import { pointer, type ProvenanceEntry } from './provenance';
import styles from './silence.module.css';
import type { SilenceEntry } from '../../data/types.generated';

export interface LedgerListProps {
  /** Entries in display order, each paired with its index in the payload. */
  readonly entries: readonly (readonly [SilenceEntry, number])[];
  readonly provenance: readonly ProvenanceEntry[] | undefined;
}

function ScoreLine({ entry }: { readonly entry: SilenceEntry }): ReactNode {
  const display = scoreDisplay(entry);

  if (display.kind === 'absent') {
    return (
      <p className={styles.scoreLine} data-testid="entry-score" data-score-state="absent">
        <span className={styles.slotPointer}>score</span>
        <span>none — this row was not silenced by a threshold</span>
      </p>
    );
  }

  if (display.kind === 'withheld') {
    return (
      <p className={styles.scoreLine} data-testid="entry-score" data-score-state="withheld">
        <span className={styles.slotPointer}>score</span>
        <span className={styles.withheld} data-testid="entry-score-withheld">
          withheld — the row carries a score but no {display.missing.join(' and no ')}
        </span>
      </p>
    );
  }

  return (
    <p className={styles.scoreLine} data-testid="entry-score" data-score-state="shown">
      <span className={styles.slotPointer}>score</span>
      <Mono data-testid="entry-score-value">{display.score}</Mono>
      <span className={styles.slotPointer}>against threshold</span>
      <Mono data-testid="entry-threshold-value">{display.threshold}</Mono>
      <span className={styles.slotPointer}>under policy</span>
      <Mono data-testid="entry-policy-version">{display.policyVersion}</Mono>
    </p>
  );
}

export function LedgerList({ entries, provenance }: LedgerListProps): ReactNode {
  if (entries.length === 0) {
    return (
      <p className={styles.panel} data-testid="entries-none">
        The ledger carries no rows for this subject. That is the absence of a row, not proof
        that nothing was declined — a run that wrote no ledger entry is a different claim from
        a run that never happened, and the recall run above says which this is.
      </p>
    );
  }

  return (
    <ul className={styles.entries} data-testid="entry-list">
      {entries.map(([entry, index]) => (
        <li
          key={entry.silence_id}
          className={styles.entry}
          data-testid="entry"
          data-source={entry.source}
          data-reason={entry.reason}
          data-severity={entry.severity}
        >
          <div className={styles.entryHead}>
            <span className={styles.entryVocab} data-testid="entry-source">
              <Mono>{entry.source}</Mono>
            </span>
            <span className={styles.entryVocab} data-testid="entry-reason">
              <Mono>{entry.reason}</Mono>
            </span>
            <span className={styles.entryVocab} data-testid="entry-severity">
              <span className={styles.slotPointer}>severity </span>
              <Mono>{entry.severity}</Mono>
            </span>
          </div>

          <ScoreLine entry={entry} />
          <p className={styles.slot}>
            <ProvenanceSlot
              provenance={provenance}
              pointer={pointer('entries', index, 'score')}
              data-testid="entry-score-provenance"
            />
            <ProvenanceSlot
              provenance={provenance}
              pointer={pointer('entries', index, 'threshold')}
              data-testid="entry-threshold-provenance"
            />
          </p>

          <dl className={styles.facts}>
            <dt>silence_id</dt>
            <dd>
              <Mono>{entry.silence_id}</Mono>
            </dd>
            <dt>event_id</dt>
            <dd>
              {(entry.event_id ?? null) === null ? (
                <span>none — this silence is not about a single event</span>
              ) : (
                <Mono data-testid="entry-event">{entry.event_id}</Mono>
              )}
            </dd>
            <dt>subject</dt>
            <dd>
              <Mono>
                {entry.subject_kind} {entry.subject_id}
              </Mono>
            </dd>
            <dt>at</dt>
            <dd>
              <Mono data-testid="entry-at">{entry.at}</Mono>
            </dd>
          </dl>

          <ArithmeticView
            arithmetic={entry.arithmetic}
            entry={entry}
            testId={`entry-arithmetic-${entry.silence_id}`}
          />
        </li>
      ))}
    </ul>
  );
}
