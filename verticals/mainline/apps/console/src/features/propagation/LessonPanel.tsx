// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The lesson, and the law that governs which lessons can exist at all.
 *
 * `only_tightenings_travel` is rendered as a STATED LAW and never as a filter control.
 * That distinction is the whole panel:
 *
 *   • as a filter, it would say "we are showing you the tightenings" — which implies a
 *     hidden set of weakenings the reader is not seeing, and invites a "show all" toggle
 *     that would have to lie;
 *   • as a law, it says the CHECK on `mainline.lesson.control_delta` admits three values
 *     and a weakening lesson is NOT A REPRESENTABLE ROW. There is nothing filtered out
 *     of the fleet below, because there is nothing to filter.
 *
 * The excluded members of `mainline.control_delta` are shown struck through, with the
 * constraint name beside them, so the closed set is visible rather than asserted.
 */

import { type ReactNode } from 'react';

import { ConstraintName, Digest, Mono } from '../../design/primitives';

import { ONLY_TIGHTENINGS_TRAVEL } from './model';
import styles from './propagation.module.css';
import { ProvenanceSlot } from './ProvenanceSlot';
import { type ProvenanceEntry } from './provenance';
import type { Lesson } from '../../data/types.generated';

export interface LessonPanelProps {
  readonly lesson: Lesson;
  readonly provenance: readonly ProvenanceEntry[] | undefined;
}

/**
 * `max_severity` is an integer and `virulence_class` is a separate column the database
 * bands ONCE, in `clause_blame_closure` (S1, MI25). The lesson payload carries only the
 * integer, so this panel renders the integer and NO band. Deriving `blood_fatal` from a
 * 5 here would be the console computing a gate-relevant value in TypeScript (D5), one hop
 * downstream of exactly the laundering the schema was shaped to prevent.
 */
export function LessonPanel({ lesson, provenance }: LessonPanelProps): ReactNode {
  return (
    <section className={styles.law} data-testid="lesson-panel" aria-label="The lesson">
      <span className={styles.kicker}>the lesson</span>
      <h2 className={styles.sectionTitle} data-testid="lesson-title">
        {lesson.title ?? 'This lesson carries no title in the payload.'}
      </h2>

      <dl className={styles.facts}>
        <dt>lesson_id</dt>
        <dd>
          <Mono data-testid="lesson-id">{lesson.lesson_id}</Mono>
        </dd>

        <dt>anchor_event</dt>
        <dd>
          <Mono data-testid="lesson-anchor">{lesson.anchor_event}</Mono>
        </dd>

        <dt>max_severity</dt>
        <dd>
          <Mono data-testid="lesson-severity">{lesson.max_severity}</Mono>{' '}
          <span className={styles.slotPointer}>
            an integer 0–5. The virulence band is a separate column this payload does not
            carry, and the console does not derive one.
          </span>
        </dd>

        <dt>control_delta</dt>
        <dd>
          <Mono data-testid="lesson-control-delta">{lesson.control_delta}</Mono>{' '}
          <ProvenanceSlot
            provenance={provenance}
            pointer="/lesson/control_delta"
            data-testid="lesson-control-delta-provenance"
          />
        </dd>

        <dt>patch_digest</dt>
        <dd>
          <Digest
            value={lesson.patch_digest}
            label="patch_digest"
            data-testid="lesson-patch-digest"
          />
          <p className={styles.note}>
            sha256 over the NORMALISED delta set — a git patch-id analogue, so the same
            change arriving by two routes is one lesson rather than two.
          </p>
        </dd>

        <dt>origin_commit</dt>
        <dd>
          <Digest value={lesson.origin_commit} label="origin_commit" data-testid="lesson-origin" />
        </dd>

        <dt>merge_base</dt>
        <dd>
          <Digest value={lesson.merge_base} label="merge_base" data-testid="lesson-merge-base" />
        </dd>
      </dl>

      <h3 className={styles.blockTitle}>the law this lesson exists under</h3>
      <p className={styles.prose} data-testid="tightenings-law">
        <ConstraintName name={ONLY_TIGHTENINGS_TRAVEL.constraint} data-testid="tightenings-constraint" />{' '}
        on <Mono>{`${ONLY_TIGHTENINGS_TRAVEL.table}.${ONLY_TIGHTENINGS_TRAVEL.column}`}</Mono>.{' '}
        {ONLY_TIGHTENINGS_TRAVEL.statement} A write that tried would be refused with SQLSTATE{' '}
        <Mono>{ONLY_TIGHTENINGS_TRAVEL.sqlstate}</Mono>.
      </p>
      <ul className={styles.lawTerms} data-testid="tightenings-terms">
        {ONLY_TIGHTENINGS_TRAVEL.admits.map((value) => (
          <li key={value} className={styles.term} data-admitted="true" data-term={value}>
            {value}
            <span className={styles.srOnly}> — admitted by the constraint</span>
          </li>
        ))}
        {ONLY_TIGHTENINGS_TRAVEL.excludes.map((value) => (
          <li key={value} className={styles.term} data-admitted="false" data-term={value}>
            {value}
            <span className={styles.srOnly}> — excluded by the constraint; not a representable row</span>
          </li>
        ))}
      </ul>
      <p className={styles.note}>
        The two struck-through values are members of <Mono>mainline.control_delta</Mono> that this
        CHECK excludes. They are shown so the closed set is visible rather than asserted, and
        because their absence from the fleet below is a property of the schema rather than a
        choice this screen made.
      </p>
    </section>
  );
}
