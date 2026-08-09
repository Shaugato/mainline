// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The answer to *"what did you decline to surface?"*, with its arithmetic.
 *
 * Order on the page is an argument, and this one goes: the conservation identity, then the
 * degraded-arm statement, then the PER commitment with its bound, then every ledger row in
 * full. A reader who stops after the first screen has still seen how many candidates the
 * run produced and how many of them went nowhere; a reader who scrolls sees each one.
 *
 * The reverse order — rows first, arithmetic at the bottom — reads as a log with a summary
 * appended, and a log is something you close.
 *
 * ── FIVE RENDERINGS AND NO SIXTH ─────────────────────────────────────────────────
 *
 * No source, loading, failed, refused, ready. A blank pane is not an outcome, and neither
 * is a screen that renders the previous permit's ledger while the current read is failing:
 * on this surface stale rows would be a list of warnings that were withheld from a
 * different person about a different job.
 */

import { type ReactNode } from 'react';

import { Mono, RegisterFrame, StagedBadge } from '../../design/primitives';

import { ArmsPanel } from './ArmsPanel';
import { ConservationPanel } from './ConservationPanel';
import { LedgerList } from './LedgerList';
import { compareSilenceEntries, PER_LIMIT_SENTENCE, tally } from './model';
import { PerPanel } from './PerPanel';
import type { ProvenanceEntry } from './provenance';
import styles from './silence.module.css';
import type { SilenceModel } from './useSilenceData';
import type { SilenceEntry } from '../../data/types.generated';

export interface SilenceScreenProps {
  readonly permitId: string;
  readonly model: SilenceModel;
  /** True when no transport was provided at all — a different nothing from a failure. */
  readonly noSource: boolean;
}

function Shell({
  children,
  permitId,
}: {
  readonly children: ReactNode;
  readonly permitId: string;
}): ReactNode {
  return (
    <RegisterFrame register="evidence">
      <div className={styles.surface} data-testid="silence-surface" data-permit={permitId}>
        {children}
      </div>
    </RegisterFrame>
  );
}

function Heading({ permitId }: { readonly permitId: string }): ReactNode {
  return (
    <header>
      <h1 className={styles.title}>Silence — what was not surfaced</h1>
      <p className={styles.standfirst}>
        Every precursor this run declined to surface, with the arithmetic that declined it: the
        score, the threshold it was measured against, the calibration artefact behind that
        threshold, and the policy version in force. This is the answer to{' '}
        <em>your system knew about event X and did not show it</em> — arithmetic instead of an
        adverse inference.
      </p>
      <p className={styles.note}>
        permit <Mono>{permitId}</Mono>
      </p>
    </header>
  );
}

/** The census. Tallies by source and by reason, so a pattern is visible without a chart. */
function Census({ entries }: { readonly entries: readonly SilenceEntry[] }): ReactNode {
  return (
    <section aria-label="Silence census">
      <h2 className={styles.sectionTitle}>the ledger, by vocabulary</h2>
      <ul className={styles.census} data-testid="census-source">
        {tally(entries, 'source').map(([value, count]) => (
          <li key={value} className={styles.censusCell} data-source={value}>
            <Mono data-testid={`census-source-${value}`}>{count}</Mono>
            <span className={styles.slotPointer}>source {value}</span>
          </li>
        ))}
      </ul>
      <ul className={styles.census} data-testid="census-reason">
        {tally(entries, 'reason').map(([value, count]) => (
          <li key={value} className={styles.censusCell} data-reason={value}>
            <Mono data-testid={`census-reason-${value}`}>{count}</Mono>
            <span className={styles.slotPointer}>reason {value}</span>
          </li>
        ))}
      </ul>
      <p className={styles.note}>
        Counts only. The rows themselves are below, in full — a count is precisely the artefact
        that lets an organisation know the number without ever reading them.
      </p>
    </section>
  );
}

export function SilenceScreen({ permitId, model, noSource }: SilenceScreenProps): ReactNode {
  if (noSource) {
    return (
      <Shell permitId={permitId}>
        <Heading permitId={permitId} />
        <section className={styles.panel} data-testid="silence-no-source">
          <h2 className={styles.sectionTitle}>no source</h2>
          <p className={styles.prose}>
            No transport was provided to this surface, so nothing has been read and nothing is
            claimed. An empty silence ledger and an unread silence ledger look identical if
            nobody says which is which — this is the second.
          </p>
        </section>
      </Shell>
    );
  }

  const silence = model.silence;

  if (silence.status === 'idle' || silence.status === 'loading') {
    return (
      <Shell permitId={permitId}>
        <Heading permitId={permitId} />
        <p className={styles.panel} role="status" data-testid="silence-loading">
          Reading <Mono>GET /v1/permits/{permitId}/silence</Mono>…
        </p>
      </Shell>
    );
  }

  if (silence.status === 'failed') {
    return (
      <Shell permitId={permitId}>
        <Heading permitId={permitId} />
        <section className={styles.failure} data-testid="silence-failed">
          <h2 className={styles.failureTitle}>the read did not complete: {silence.failure}</h2>
          <pre className={styles.verbatim}>{silence.detail}</pre>
          <p className={styles.note}>
            Rendered verbatim. On this surface a summarised failure would be indistinguishable
            from an empty ledger, which is the one confusion it exists to prevent.
          </p>
        </section>
      </Shell>
    );
  }

  if (silence.status === 'refused') {
    return (
      <Shell permitId={permitId}>
        <Heading permitId={permitId} />
        <section className={styles.failure} data-testid="silence-refused">
          <h2 className={styles.failureTitle}>the database refused this read</h2>
          <p className={styles.prose}>
            constraint <Mono>{silence.refusal.constraint}</Mono>, SQLSTATE{' '}
            <Mono>{silence.refusal.sqlstate}</Mono>
          </p>
          <pre className={styles.verbatim}>{silence.refusal.message}</pre>
        </section>
      </Shell>
    );
  }

  const envelope = silence.exchange.envelope;
  const provenance = envelope.provenance as readonly ProvenanceEntry[] | undefined;
  const runProvenance =
    model.run.status === 'ready'
      ? (model.run.exchange.envelope.provenance as readonly ProvenanceEntry[] | undefined)
      : undefined;

  const data = silence.data;
  const ordered: readonly (readonly [SilenceEntry, number])[] = data.entries
    .map((entry, index) => [entry, index] as const)
    .sort((a, b) => compareSilenceEntries(a[0], b[0]));

  return (
    <Shell permitId={permitId}>
      <Heading permitId={permitId} />

      {envelope.staged ? (
        <div data-testid="silence-staged">
          <StagedBadge what="hand-authored demonstration payload — no recall run produced these rows" />
          {(envelope.staged_note ?? null) === null ? null : (
            <pre className={styles.verbatim}>{envelope.staged_note}</pre>
          )}
        </div>
      ) : null}

      {model.runData === null ? (
        <section className={styles.panel} data-testid="conservation-unavailable">
          <h2 className={styles.sectionTitle}>the conservation identity is not on screen</h2>
          <p className={styles.prose}>
            {model.runId === null
              ? 'This payload carries no PER receipt, so it names no recall run, so there is no run id to read the conservation counts from. The console does not guess one: a conservation identity belonging to a different retrieval than the rows below would be two internally consistent panels describing two different runs.'
              : model.run.status === 'failed'
                ? `The run read did not complete: ${model.run.detail}`
                : 'Reading the recall run named by the receipt…'}
          </p>
        </section>
      ) : (
        <ConservationPanel run={model.runData} provenance={runProvenance} />
      )}

      {model.runData === null ? null : <ArmsPanel run={model.runData} />}

      {data.receipt === null ? (
        <section className={styles.panel} data-testid="per-absent">
          <h2 className={styles.sectionTitle}>no proof of exhausted recall was issued</h2>
          <p className={styles.prose}>
            The run issued no receipt, so nothing here certifies exhaustion of anything. That is
            a weaker position than a receipt with a bound, and it is displayed as the weaker
            position rather than left blank.
          </p>
          <p className={styles.limit} data-testid="per-limit-sentence">
            {PER_LIMIT_SENTENCE}
          </p>
        </section>
      ) : (
        <PerPanel receipt={data.receipt} provenance={provenance} />
      )}

      <Census entries={data.entries} />

      <section aria-label="Silence ledger">
        <h2 className={styles.sectionTitle}>
          every row — severity first, then the ones that came closest
        </h2>
        <p className={styles.prose}>
          Within a severity band the entry that came CLOSEST to being surfaced is first: it is
          the row where the threshold did the most work, and therefore the row a calibration
          argument would land on hardest.
        </p>
        <LedgerList entries={ordered} provenance={provenance} />
      </section>
    </Shell>
  );
}
