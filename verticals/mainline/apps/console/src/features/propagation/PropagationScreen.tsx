// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The fleet surface: where a lesson travelled, and where it did not.
 *
 * Five renderings and no sixth — no source, loading, failed, refused, ready. A blank pane
 * is not an outcome this component can produce, and neither is a screen that shows the
 * previous lesson's rows while the current read is failing.
 *
 * ── THE ORDERING IS THE ARGUMENT ─────────────────────────────────────────────────
 *
 * Sites are a LIST, ordered by severity and then by overdue-ness. There is no map, no
 * globe, no cartogram and no cluster bubble. A geographic projection would rank sites by
 * their distance from a viewport, which means nothing about safety, while spending the
 * screen's entire visual budget on decoration — the exact spectacle-over-substance
 * failure the charter forbids. The ordering rule is exported, pure and unit-tested; a
 * projection would be none of those things.
 */

import { Suspense, lazy, type ReactNode } from 'react';

import { Mono, RegisterFrame, StagedBadge } from '../../design/primitives';
import { glossFor } from '../../design/glossary';
import type { ResourceState } from '../../data/useResource';

import { ConflictList } from './ConflictList';
import { InheritancePanel } from './InheritancePanel';
import { LessonPanel } from './LessonPanel';
import { buildFleetView, type PropagationData } from './model';
import styles from './propagation.module.css';
import { SiteRow } from './SiteRow';
import type { ProvenanceEntry } from './provenance';

export interface PropagationScreenProps {
  readonly lessonId: string;
  readonly state: ResourceState<PropagationData>;
  /** True when no transport was provided at all — a different nothing from a failure. */
  readonly noSource: boolean;
}

/**
 * The plain-language walkthrough (R9), in its own chunk.
 *
 * Lazy because prose is the cheapest thing to move off a critical path and the most
 * expensive thing to leave on one — `budgets.json` is a ceiling this wave does not raise,
 * and the evidentiary shell carries none of this. `Suspense fallback={null}` because a
 * spinner where an introduction is about to appear is worse than the introduction arriving
 * a frame late; every precise section of the screen is already painted underneath it.
 */
const UseCaseTwo = lazy(async () => {
  const module = await import('./UseCaseTwo');
  return { default: module.UseCaseTwo };
});

/**
 * The heading, and the walkthrough that has no numbers to show.
 *
 * Used by the four renderings that hold no payload. The walkthrough still appears — it is
 * what tells a reader what this screen is FOR, which is the question somebody who has just
 * met a failure panel most needs answered — and it prints no figures, because there are
 * none and inventing one is the move this repository does not make.
 */
function Opening({
  lessonId,
  absence,
}: {
  readonly lessonId: string;
  readonly absence: string;
}): ReactNode {
  return (
    <>
      <Heading lessonId={lessonId} />
      <Suspense fallback={null}>
        <UseCaseTwo view={null} absence={absence} staged={false} />
      </Suspense>
    </>
  );
}

function Shell({
  children,
  lessonId,
}: {
  readonly children: ReactNode;
  readonly lessonId: string;
}): ReactNode {
  return (
    /*
     * EVIDENCE, declared on the tree.
     *
     * `src/design/registers.ts` classifies this DIRECTORY as INSTRUMENT, which permits
     * motion. This surface elects the stricter register: a declination is a record, not a
     * mechanism, and no transition on this screen is itself the fact. Declaring EVIDENCE
     * here means every `Counter` and `Meter` beneath it refuses to move, and it means a
     * spec can assert the law the subtree was operating under.
     */
    <RegisterFrame register="evidence">
      <div className={styles.surface} data-testid="propagation-surface" data-lesson={lessonId}>
        {children}
      </div>
    </RegisterFrame>
  );
}

function Heading({ lessonId }: { readonly lessonId: string }): ReactNode {
  return (
    <header>
      <h1 className={styles.title}>Propagation — where the lesson travelled</h1>
      <p className={styles.standfirst}>
        One lesson, and every sibling site&apos;s answer to it. A site that declined is rendered
        with the same weight as a site that adopted, because a named, dated, falsifiable NO is
        the most useful row on this screen — and a fleet view that whispers its refusals is a
        fleet view that reports adoption.
      </p>
      <p className={styles.note}>
        lesson <Mono>{lessonId}</Mono>
      </p>
    </header>
  );
}

export function PropagationScreen({
  lessonId,
  state,
  noSource,
}: PropagationScreenProps): ReactNode {
  if (noSource) {
    return (
      <Shell lessonId={lessonId}>
        <Opening
          lessonId={lessonId}
          absence="No transport was provided to this surface, so no read was attempted."
        />
        <section className={styles.panel} data-testid="propagation-no-source">
          <h2 className={styles.sectionTitle}>no source</h2>
          <p className={styles.prose}>
            No transport was provided to this surface, so nothing has been read and nothing is
            claimed. This is not a failure of the fleet — it is the absence of a connection to
            one. The console&apos;s replay transport refuses to run without a verifier, and this
            surface will not manufacture a permissive one to make a screen paint.
          </p>
        </section>
      </Shell>
    );
  }

  if (state.status === 'idle' || state.status === 'loading') {
    return (
      <Shell lessonId={lessonId}>
        <Opening lessonId={lessonId} absence="The read is still in flight." />
        <p className={styles.panel} role="status" data-testid="propagation-loading">
          Reading <Mono>GET /v1/lessons/{lessonId}/propagation</Mono>…
        </p>
      </Shell>
    );
  }

  if (state.status === 'failed') {
    return (
      <Shell lessonId={lessonId}>
        <Opening lessonId={lessonId} absence={`The read did not complete: ${state.failure}.`} />
        <section className={styles.failure} data-testid="propagation-failed">
          <h2 className={styles.failureTitle}>the read did not complete: {state.failure}</h2>
          <pre className={styles.verbatim}>{state.detail}</pre>
          <p className={styles.note}>
            Rendered verbatim. A summarised failure is a failure somebody has to reproduce
            twice.
          </p>
        </section>
      </Shell>
    );
  }

  if (state.status === 'refused') {
    return (
      <Shell lessonId={lessonId}>
        <Opening
          lessonId={lessonId}
          absence={`The database refused this read, under ${state.refusal.constraint}.`}
        />
        <section className={styles.failure} data-testid="propagation-refused">
          <h2 className={styles.failureTitle}>the database refused this read</h2>
          <p className={styles.prose}>
            constraint <Mono>{state.refusal.constraint}</Mono>, SQLSTATE{' '}
            <Mono>{state.refusal.sqlstate}</Mono>
          </p>
          <pre className={styles.verbatim}>{state.refusal.message}</pre>
        </section>
      </Shell>
    );
  }

  const envelope = state.exchange.envelope;
  const provenance = envelope.provenance as readonly ProvenanceEntry[] | undefined;
  /*
   * The reference instant for every interval on this screen, in priority order: the
   * emitter's `observed_at`, then its `server_date`. Never `Date.now()` — an SLA measured
   * against the reader's laptop is a statement about the reader's laptop, and cinema mode
   * (D12) freezes the clock precisely so a capture is reproducible.
   */
  const reference = envelope.observed_at ?? envelope.server_date ?? '';
  const view = buildFleetView(state.data, reference);

  return (
    <Shell lessonId={lessonId}>
      <Heading lessonId={lessonId} />

      {/*
        THE STAGED BADGE IS LOAD-BEARING AND IS NEVER COLLAPSED.
        R6 forbids PLAIN hiding a STAGED badge, and this is the screen where that ruling
        earns its keep: `reads.py::read_propagation` stages this resource IN FULL, because
        `mainline.lesson`, `mainline.propagation` and `mainline.merge_conflict` are produced
        by no migration in this repository. So the badge, the plain sentence under it and
        the emitter's verbatim note are all in the open flow, in both readings of this
        screen, above every number they qualify.
      */}
      {envelope.staged ? (
        <div data-testid="propagation-staged">
          <StagedBadge what="hand-authored demonstration payload — no cluster produced these rows" />
          <p className={styles.prose} data-testid="propagation-staged-plain">
            In plain words: these rows come from a fixture, not from the live database.{' '}
            {glossFor('staged')} Everything below is real console behaviour over a payload the
            demo API composed, and the emitter&apos;s own note saying so is next.
          </p>
          {(envelope.staged_note ?? null) === null ? null : (
            <pre className={styles.verbatim}>{envelope.staged_note}</pre>
          )}
        </div>
      ) : null}

      <Suspense fallback={null}>
        <UseCaseTwo view={view} absence={null} staged={envelope.staged} />
      </Suspense>

      <LessonPanel lesson={view.lesson} provenance={provenance} />

      <section aria-label="Fleet census">
        <h2 className={styles.sectionTitle}>the fleet, by state</h2>
        <ul className={styles.census} data-testid="census">
          {view.census.map(([propState, count]) => (
            <li key={propState} className={styles.censusCell} data-state={propState}>
              <Mono data-testid={`census-${propState}`}>{count}</Mono>
              <span className={styles.slotPointer}>{propState}</span>
            </li>
          ))}
        </ul>
        <p className={styles.note}>
          Every member of <Mono>mainline.prop_state</Mono> appears, including the zeroes. A
          census that omitted the empty states would let a reader mistake &quot;none declined&quot;
          for &quot;declination was not possible&quot;.
        </p>
      </section>

      <section aria-label="Sites">
        <h2 className={styles.sectionTitle}>
          the sites — ordered by severity, then by how long an answer has been owed
        </h2>
        <p className={styles.prose}>
          No map and no globe. A geographic projection ranks sites by distance from a
          viewport, which says nothing about safety; this list ranks them by the lesson&apos;s
          severity and then by overdue-ness, which is the order somebody with a finite morning
          should read them in.
        </p>
        {view.rows.length === 0 ? (
          <p className={styles.panel} data-testid="sites-none">
            The payload carries no propagation rows for this lesson. Nothing was proposed to
            anybody — which is itself a finding, not an empty screen.
          </p>
        ) : (
          <ul className={styles.sites} data-testid="site-list">
            {view.rows.map((row) => (
              <SiteRow
                key={row.propagation.site_id}
                row={row}
                index={row.index}
                provenance={provenance}
              />
            ))}
          </ul>
        )}
      </section>

      <ConflictList
        conflicts={view.attachedConflicts}
        reference={reference}
        caption="open conflicts"
        data-testid="conflict-list"
      />

      {view.orphanConflicts.length === 0 ? null : (
        <ConflictList
          conflicts={view.orphanConflicts}
          reference={reference}
          caption="conflicts whose site has no propagation row"
          data-testid="orphan-conflict-list"
        />
      )}

      <InheritancePanel inheritance={view.inheritance} />
    </Shell>
  );
}
