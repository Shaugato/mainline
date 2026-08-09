// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE GATE SCREEN — the refusal, its irreducible reason set, and the clause diff that
 * armed it.
 *
 * Top to bottom, and the order is the argument:
 *
 *   0. the subject, and the one control that attempts the transition;
 *   1. the refusal bar — constraint name, SQLSTATE, subject, gate epoch, all verbatim;
 *   2. the minimal unsatisfiable subset and the nearest admissible alternative;
 *   3. the weld — every projected counter under the CHECK that reads it;
 *   4. the precursors — the materialised obligations and what wrote their clauses;
 *   5. the clause diff — the edit, its control delta, and the witnesses behind it.
 *
 * Nothing on this screen is composed by the console except the prose that describes an
 * ABSENCE. Every value is a payload field, rendered in the mono face with a provenance
 * chip. This component computes no gate condition (D5) and imports no animation library
 * — the directory is EVIDENCE and `tests/unit/design/register-boundary.test.ts` walks
 * the real module graph to prove it.
 */

import { type ReactNode } from 'react';

import { Digest, Mono, StagedBadge } from '../../design/primitives';

import { ClauseDiff } from './ClauseDiff';
import styles from './gate.module.css';
import { PrecursorList } from './PrecursorList';
import { ProvenanceSlot } from './ProvenanceSlot';
import { ReasonSet } from './ReasonSet';
import { RefusalBar } from './RefusalBar';
import { WeldDiagram } from './WeldDiagram';
import type { GateModel } from './useGateData';
import type { ResourceState } from '../../data/useResource';

export interface GateScreenProps {
  readonly permitId: string;
  readonly model: GateModel;
  /** True when no transport has been provided. Renders the NO SOURCE panel. */
  readonly noSource?: boolean;
}

function ReadFailure<T>({
  state,
  what,
}: {
  readonly state: ResourceState<T>;
  readonly what: string;
}): ReactNode {
  if (state.status !== 'failed') return null;
  return (
    <div className={styles.absent} role="alert" data-testid={`read-failed-${what}`}>
      <span className={styles.absentTitle}>
        {what} read failed — <Mono>{state.failure}</Mono>
      </span>
      <pre className={styles.refusalMessage}>{state.detail}</pre>
      <p className={styles.prose}>
        A read that did not complete is an absence of evidence on this screen. Nothing about the
        gate follows from it, and no part of this surface fills the hole with a default.
      </p>
    </div>
  );
}

function NoSource(): ReactNode {
  return (
    <div className={styles.surface} data-testid="gate-no-source">
      <section className={styles.refusalBar} data-state="none" aria-label="Refusal">
        <span className={styles.refusalKicker}>no source — nothing has been read</span>
        <p className={styles.prose}>
          This surface has been given neither a live kernel nor a verified evidence bundle, so it
          holds no bytes and shows no claims. It does not construct a transport of its own: a bundle
          player without a verifier is a mock, and{' '}
          <Mono>src/data/bundle.ts</Mono> ships no default verifier on purpose.
        </p>
        <p className={styles.prose}>
          To feed it, provide a <Mono>MainlineTransport</Mono> through{' '}
          <Mono>GateTransportContext</Mono> — an <Mono>HttpTransport</Mono> pointed at the kernel,
          or a <Mono>BundleTransport</Mono> over a verified EvidenceBundle.
        </p>
      </section>
    </div>
  );
}

export function GateScreen({ permitId, model, noSource = false }: GateScreenProps): ReactNode {
  if (noSource) return <NoSource />;

  const {
    permitData,
    checkRows,
    clauseData,
    ancestryData,
    refusalState,
    weld,
    diffSubject,
    namedByReasonSet,
    permitProvenance,
    checksProvenance,
    clauseProvenance,
    attemptProvenance,
    attempted,
    beginAttempt,
    staged,
    stagedNote,
  } = model;

  const busy = model.attempt.status === 'loading';

  return (
    <div className={styles.surface} data-testid="gate-surface">
      {/* ── 0. The subject and the one control ── */}
      <section className={styles.panel} aria-labelledby="gate-subject-title" data-testid="gate-subject">
        <h1 className={styles.panelTitle} id="gate-subject-title">
          Permit <Mono>{permitData?.external_ref ?? permitId}</Mono>
        </h1>
        <div className={styles.facts}>
          <span className={styles.fact}>
            <span className={styles.label}>permit_id</span>
            <Mono>{permitId}</Mono>
          </span>
          {permitData === null ? null : (
            <>
              <span className={styles.fact}>
                <span className={styles.label}>ref_name</span>
                <Mono>{permitData.ref_name}</Mono>
              </span>
              <span className={styles.fact}>
                <span className={styles.label}>state</span>
                <Mono data-testid="permit-state">{permitData.state}</Mono>
                <ProvenanceSlot provenance={permitProvenance} pointer="/state" />
              </span>
              <span className={styles.fact}>
                <span className={styles.label}>gate_epoch</span>
                <Mono data-testid="permit-gate-epoch">{permitData.gate_epoch}</Mono>
                <ProvenanceSlot provenance={permitProvenance} pointer="/gate_epoch" />
              </span>
              <span className={styles.fact}>
                <span className={styles.label}>under_hold</span>
                <Mono>{permitData.under_hold}</Mono>
              </span>
              {permitData.slice_digest === null || permitData.slice_digest === undefined ? null : (
                <Digest value={permitData.slice_digest} label="slice digest" />
              )}
            </>
          )}
          {staged ? <StagedBadge what="every value on this screen came from a staged bundle" /> : null}
        </div>

        {staged && stagedNote !== null ? (
          <p className={styles.panelNote} data-testid="staged-note">
            {stagedNote}
          </p>
        ) : null}

        <div className={styles.attempt}>
          <button
            type="button"
            className={styles.attemptButton}
            onClick={beginAttempt}
            disabled={attempted || permitData === null}
            data-testid="attempt-merge"
          >
            POST /v1/permits/{permitId}/merge
          </button>
          <span className={styles.panelNote}>
            {attempted
              ? 'Attempted once. There is no automatic retry anywhere in this console — spec/wire/refusal.md C-1.'
              : 'Calls trappoint.merge_permit() in one serializable transaction. The database refuses it, by name, or it commits. Nothing on this screen predicts which.'}
          </span>
        </div>

        <ReadFailure state={model.permit} what="permit" />
        <ReadFailure state={model.checks} what="blocking-checks" />
        <ReadFailure state={model.clause} what="clause-version" />
        <ReadFailure state={model.ancestry} what="clause-ancestry" />
      </section>

      {/* ── 1. The refusal bar ── */}
      <RefusalBar state={refusalState} provenance={attemptProvenance} />

      {/* ── 2. The reason set ── */}
      {refusalState.kind === 'refused' ? (
        <ReasonSet refusal={refusalState.refusal} provenance={attemptProvenance} />
      ) : (
        <section className={styles.panel} data-testid="reason-set-absent" aria-label="Reason set">
          <h2 className={styles.panelTitle}>Irreducible reason set</h2>
          <div className={styles.absent}>
            <span className={styles.absentTitle}>no reason set</span>
            <p className={styles.prose}>
              A minimal unsatisfiable subset exists only for a refusal that happened. There is no
              refusal on this screen{busy ? ' yet' : ''}, so there is nothing to decompose.
            </p>
          </div>
        </section>
      )}

      {/* ── 3. The weld ── */}
      {weld === null || permitData === null ? (
        <section className={styles.panel} data-testid="weld-absent" aria-label="The weld">
          <h2 className={styles.panelTitle}>The weld</h2>
          <div className={styles.absent}>
            <span className={styles.absentTitle}>permit not carried</span>
            <p className={styles.prose}>
              The permit read has not landed, so the projected counters and the constraints that
              read them are not available. The console shows no counters rather than zeroes.
            </p>
          </div>
        </section>
      ) : (
        <WeldDiagram
          weld={weld}
          permit={permitData}
          provenance={permitProvenance}
          checks={checkRows}
        />
      )}

      {/* ── 4. The precursors ── */}
      <PrecursorList
        checks={checkRows}
        provenance={checksProvenance}
        ancestry={ancestryData}
        namedByReasonSet={namedByReasonSet}
      />

      {/* ── 5. The clause diff ── */}
      <ClauseDiff
        clause={clauseData}
        selection={diffSubject.selection}
        provenance={clauseProvenance}
      />
    </div>
  );
}
