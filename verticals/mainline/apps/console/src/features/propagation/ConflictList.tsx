// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Open merge conflicts — the conflictors a failed cherry-pick materialises (M17).
 *
 * Each one is a three-way merge that did not resolve: `base_digest`, `ours_digest`,
 * `theirs_digest`, over one `clause_uuid`, at one site. All three digests are rendered in
 * full (the `Digest` primitive keeps the whole value in the DOM and clips only visually),
 * because the whole point of a three-way record is that a reader can fetch the three
 * texts and see the collision for themselves.
 *
 * ── ESCALATION, RENDERED HONESTLY ────────────────────────────────────────────────
 *
 * ARCHITECTURE.md §3/M17 declares the conflictor undeletable and escalating. This screen
 * can show the escalation — the age of an unresolved conflict, measured against the
 * payload's own reference instant, growing every day nobody closes it — and it CANNOT
 * prove the undeletability, because that is a property of the kernel's constraints and
 * not of any byte in this payload. So the panel says which of the two it is showing and
 * which it is citing. A console that asserted "this row cannot be deleted" from a read
 * payload would be laundering a schema claim through a rendering.
 *
 * ── A RECORDED RESOLUTION IS PROPOSED, NEVER AUTO-APPLIED ────────────────────────
 *
 * `resolution_source` is the rerere-with-recall back-pointer. It is displayed as a
 * citation, and there is no control on this surface that applies one. Auto-applying a
 * safety-text resolution is precisely the rubber-stamp accelerant the design refuses to
 * build, and the reliable way not to build it is to ship no button that does it.
 */

import { type ReactNode } from 'react';

import { Digest, Mono } from '../../design/primitives';

import { Instant } from './Instant';
import { interval, wholeDays } from './model';
import styles from './propagation.module.css';
import type { MergeConflict, Timestamp } from '../../data/types.generated';

export interface ConflictListProps {
  readonly conflicts: readonly MergeConflict[];
  /** The instant every age is measured against — the payload's `observed_at`. */
  readonly reference: Timestamp;
  /** Rendered above the list; distinguishes the orphan list from the main one. */
  readonly caption: string;
  readonly 'data-testid'?: string;
}

function Conflict({
  conflict,
  reference,
}: {
  readonly conflict: MergeConflict;
  readonly reference: Timestamp;
}): ReactNode {
  const age = interval(conflict.opened_at, reference);
  const resolved = conflict.resolved_commit ?? null;

  return (
    <li
      className={styles.conflict}
      data-testid="conflict"
      data-conflict={conflict.conflict_id}
      data-site={conflict.site_id}
      data-resolved={resolved === null ? 'false' : 'true'}
    >
      <div className={styles.siteHead}>
        <span className={styles.siteLabel}>
          <Mono data-testid="conflict-id">{conflict.conflict_id}</Mono>
        </span>
        <span className={styles.siteState} data-testid="conflict-state">
          <Mono>{resolved === null ? 'open' : 'resolved'}</Mono>
        </span>
        <span className={styles.clockValue} data-testid="conflict-age">
          <Mono>{age.measurable ? wholeDays(age.deltaMs) : 0}</Mono>
          <span className={styles.clockReference}> day(s) open</span>
        </span>
      </div>

      <dl className={styles.facts}>
        <dt>clause_uuid</dt>
        <dd>
          <Mono data-testid="conflict-clause">{conflict.clause_uuid}</Mono>
        </dd>
        <dt>site_id</dt>
        <dd>
          <Mono>{conflict.site_id}</Mono>
        </dd>
        <dt>opened_at</dt>
        <dd>
          <Instant
            label="opened_at"
            value={conflict.opened_at}
            interval={age}
            data-testid="conflict-opened"
          />
        </dd>
      </dl>

      <dl className={styles.threeWay} data-testid="conflict-three-way">
        <dt>base</dt>
        <dd>
          <Digest value={conflict.base_digest} label="base_digest" data-testid="conflict-base" />
        </dd>
        <dt>ours</dt>
        <dd>
          <Digest value={conflict.ours_digest} label="ours_digest" data-testid="conflict-ours" />
        </dd>
        <dt>theirs</dt>
        <dd>
          <Digest
            value={conflict.theirs_digest}
            label="theirs_digest"
            data-testid="conflict-theirs"
          />
        </dd>
      </dl>

      <dl className={styles.facts}>
        <dt>resolved_commit</dt>
        <dd>
          {resolved === null ? (
            <span className={styles.absent}>none — this conflict is still open</span>
          ) : (
            <Digest value={resolved} label="resolved_commit" data-testid="conflict-resolved" />
          )}
        </dd>
        <dt>resolved_by</dt>
        <dd>
          {/*
            The only person-shaped value in this payload. It is a verbatim column value and
            it is never a colour, an axis, a facet or a sort key anywhere on this surface
            (D15 / I15); `compareConflicts` orders by age and id alone, and
            tests/unit/propagation/model.test.ts asserts that by permuting this field.
          */}
          {(conflict.resolved_by ?? null) === null ? (
            <span className={styles.absent}>none</span>
          ) : (
            <Mono data-testid="conflict-resolved-by">{conflict.resolved_by}</Mono>
          )}
        </dd>
        <dt>resolution_source</dt>
        <dd>
          {(conflict.resolution_source ?? null) === null ? (
            <span className={styles.absent}>none — nothing was proposed from memory</span>
          ) : (
            <>
              <Mono data-testid="conflict-resolution-source">{conflict.resolution_source}</Mono>
              <p className={styles.note}>
                A rerere-with-recall back-pointer into <Mono>mainline.resolution_memory</Mono>. A
                recorded resolution is PROPOSED, never auto-applied — and this surface ships no
                control that applies one.
              </p>
            </>
          )}
        </dd>
      </dl>
    </li>
  );
}

export function ConflictList({
  conflicts,
  reference,
  caption,
  'data-testid': testId,
}: ConflictListProps): ReactNode {
  return (
    <section data-testid={testId} aria-label={caption}>
      <h2 className={styles.sectionTitle}>{caption}</h2>
      <p className={styles.prose}>
        A conflictor is what a failed three-way cherry-pick leaves behind (ARCHITECTURE.md §3,
        M17): undeletable and escalating. What this screen SHOWS is the escalation — days open,
        measured against the payload&apos;s reference instant, growing every day nobody closes it.
        What it CITES, and cannot prove from these bytes, is the undeletability: that is a
        property of the kernel&apos;s constraints, and a rendering may not stand in for one.
      </p>
      {conflicts.length === 0 ? (
        <p className={styles.panel} data-testid="conflicts-none">
          No conflict rows in this payload. That is the absence of a row, not a guarantee that
          the fleet is clean — this surface reports one lesson.
        </p>
      ) : (
        <ul className={styles.conflicts}>
          {conflicts.map((conflict) => (
            <Conflict key={conflict.conflict_id} conflict={conflict} reference={reference} />
          ))}
        </ul>
      )}
    </section>
  );
}
