// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The gate screen's reads, and its one write attempt.
 *
 * ── THE MERGE IS NEVER ATTEMPTED ON MOUNT ────────────────────────────────────────
 *
 * `merge_permit` is a STATE TRANSITION. Firing it because a page loaded would mean the
 * console attempts a merge every time somebody opens a link, and — on the day the gate
 * is legitimately open — issues a permit nobody asked to issue. So the attempt is an
 * explicit act with an author: a control the reader presses, exactly once, with no
 * retry (`spec/wire/refusal.md` C-1, and `src/data/transport.ts`'s no-retry rule).
 *
 * The consequence is a screen that is HONEST before it is dramatic: until an attempt has
 * been made, the refusal bar says the database has refused nothing. A refusal bar
 * pre-populated by prediction would be the console composing a refusal, which is the one
 * thing D18 forbids outright.
 *
 * The behaviour is identical under LIVE and REPLAY — the same request key, the same
 * interface, the same code path — which is what makes the LIVE/REPLAY badge a fact
 * rather than decoration (D7).
 *
 * ── THE READ SET ─────────────────────────────────────────────────────────────────
 *
 *   permit           the seven projected counters, the constraints, the boundary
 *                    certificate, the gate epoch
 *   blocking_checks  the witness rows behind `open_blocking`
 *   clause_version   the edit that armed the check the reason set names
 *   clause_ancestry  what wrote that clause — the introducing commit and the blame edge
 *
 * The last two are addressed by the clause the REFUSAL names, so they are enabled only
 * once a subject has been chosen. `useResource` holds the four-state machine; there is
 * no fifth state and no stale-data-plus-failure state, deliberately.
 */

import { useCallback, useMemo, useState } from 'react';

import type { MainlineTransport } from '../../data/transport';
import { useResource, type ResourceState } from '../../data/useResource';
import type {
  BlockingCheck,
  InvokeResult,
  Permit,
} from '../../data/types.generated';

import {
  buildWeld,
  chooseDiffSubject,
  musObligationIds,
  readRefusal,
  type BlockingChecksData,
  type AncestryData,
  type ClauseData,
  type DiffSubject,
  type WeldDiagramModel,
} from './model';
import type { RefusalBarState } from './RefusalBar';
import type { ProvenanceEntry } from './provenance';

/** A path value that satisfies `resources.ts`'s unreserved-token rule while disabled. */
const PLACEHOLDER = 'disabled';

export interface GateModel {
  readonly permit: ResourceState<Permit>;
  readonly checks: ResourceState<BlockingChecksData>;
  readonly clause: ResourceState<ClauseData>;
  readonly ancestry: ResourceState<AncestryData>;
  readonly attempt: ResourceState<InvokeResult>;

  /** `null` until the permit read succeeds. */
  readonly permitData: Permit | null;
  /** `null` when the blocking-checks read has not landed — NOT an empty list. */
  readonly checkRows: readonly BlockingCheck[] | null;
  readonly clauseData: ClauseData | null;
  readonly ancestryData: AncestryData | null;

  readonly refusalState: RefusalBarState;
  readonly weld: WeldDiagramModel | null;
  readonly diffSubject: DiffSubject;
  readonly namedByReasonSet: ReadonlySet<string>;

  /** Envelope provenance lists, per read, for the chips beside each value. */
  readonly permitProvenance: readonly ProvenanceEntry[] | undefined;
  readonly checksProvenance: readonly ProvenanceEntry[] | undefined;
  readonly clauseProvenance: readonly ProvenanceEntry[] | undefined;
  readonly attemptProvenance: readonly ProvenanceEntry[] | undefined;

  /** True once the reader has pressed the attempt control. Never set by a render. */
  readonly attempted: boolean;
  /** Arms the one merge attempt. Idempotent; there is no automatic retry anywhere. */
  readonly beginAttempt: () => void;
  /** Clock skew reported by whichever read landed most recently, or null. */
  readonly clockSkewMs: number | null;
  readonly staged: boolean;
  readonly stagedNote: string | null;
}

function provenanceOf<T>(state: ResourceState<T>): readonly ProvenanceEntry[] | undefined {
  return state.status === 'ready' ? state.exchange.envelope.provenance : undefined;
}

function dataOf<T>(state: ResourceState<T>): T | null {
  return state.status === 'ready' ? state.data : null;
}

function skewOf<T>(state: ResourceState<T>): number | null {
  return state.status === 'ready' ? state.exchange.clockSkewMs : null;
}

function stagedOf<T>(state: ResourceState<T>): { staged: boolean; note: string | null } | null {
  if (state.status !== 'ready') return null;
  return {
    staged: state.exchange.envelope.staged,
    note: state.exchange.envelope.staged_note ?? null,
  };
}

function refusalStateFrom(
  state: ResourceState<InvokeResult>,
  attempted: boolean,
): RefusalBarState {
  if (!attempted || state.status === 'idle') return { kind: 'none' };
  if (state.status === 'loading') return { kind: 'attempting' };
  if (state.status === 'failed') return { kind: 'failed', failure: state.failure, detail: state.detail };
  if (state.status === 'refused') {
    const read = readRefusal(state.refusal);
    return read.ok ? { kind: 'refused', refusal: read.refusal } : { kind: 'defect', reason: read.reason };
  }
  // `ready` means the transport did NOT raise a refusal, so the outcome is committed or
  // retry. A `refused` outcome cannot reach here: finishExchange throws on it.
  if (state.data.outcome === 'retry') return { kind: 'retry' };
  return { kind: 'committed', mergedCommit: state.data.committed?.merged_commit ?? null };
}

export function useGateData(
  transport: MainlineTransport | null,
  permitId: string,
): GateModel {
  const [attempted, setAttempted] = useState(false);

  const { state: permit } = useResource<Permit>(transport, {
    resource: 'permit',
    path: { permit_id: permitId },
  });
  const permitData = dataOf(permit);

  const { state: checks } = useResource<BlockingChecksData>(transport, {
    resource: 'blocking_checks',
    path: { permit_id: permitId },
  });
  const checksData = dataOf(checks);
  const checkRows = checksData === null ? null : checksData.checks;

  const { state: attempt } = useResource<InvokeResult>(
    transport,
    {
      resource: 'merge_permit',
      path: { permit_id: permitId },
      // Exactly the body the captured round trip carries. The epoch is an optimistic
      // token: it pins WHICH state of the subject this attempt was made against, so a
      // refusal can be replayed against the same epoch.
      body: {
        subject_kind: 'permit',
        subject_id: permitId,
        expected_gate_epoch: permitData?.gate_epoch ?? 0,
      },
    },
    { enabled: attempted && permitData !== null },
  );

  const refusalState = refusalStateFrom(attempt, attempted);
  const refusal = refusalState.kind === 'refused' ? refusalState.refusal : null;

  const diffSubject = useMemo(
    () => chooseDiffSubject(checkRows, refusal),
    [checkRows, refusal],
  );

  const namedByReasonSet = useMemo(
    () => new Set(refusal === null ? [] : musObligationIds(refusal.mus)),
    [refusal],
  );

  const subjectCheck = diffSubject.check;

  const { state: clause } = useResource<ClauseData>(
    transport,
    {
      resource: 'clause_version',
      path: {
        clause_uuid: subjectCheck?.clause_uuid ?? PLACEHOLDER,
        commit_id: subjectCheck?.commit_id ?? PLACEHOLDER,
      },
    },
    { enabled: subjectCheck !== null },
  );

  const { state: ancestry } = useResource<AncestryData>(
    transport,
    {
      resource: 'clause_ancestry',
      path: { clause_uuid: subjectCheck?.clause_uuid ?? PLACEHOLDER },
      query: { as_of: subjectCheck?.commit_id ?? PLACEHOLDER },
    },
    { enabled: subjectCheck !== null },
  );

  const weld = useMemo(
    () =>
      permitData === null
        ? null
        : buildWeld({
            permit: permitData,
            checks: checkRows,
            blamedConstraint: refusal?.constraint ?? null,
          }),
    [permitData, checkRows, refusal],
  );

  const beginAttempt = useCallback(() => {
    setAttempted(true);
  }, []);

  const clockSkewMs =
    skewOf(attempt) ?? skewOf(permit) ?? skewOf(checks) ?? skewOf(clause) ?? skewOf(ancestry);

  const stagedSignals = [
    stagedOf(permit),
    stagedOf(checks),
    stagedOf(clause),
    stagedOf(ancestry),
    stagedOf(attempt),
  ].flatMap((signal) => (signal === null ? [] : [signal]));
  const stagedSignal = stagedSignals.find((signal) => signal.staged) ?? null;
  const staged = stagedSignal !== null;
  const stagedNote = stagedSignal?.note ?? null;

  return {
    permit,
    checks,
    clause,
    ancestry,
    attempt,
    permitData,
    checkRows,
    clauseData: dataOf(clause),
    ancestryData: dataOf(ancestry),
    refusalState,
    weld,
    diffSubject,
    namedByReasonSet,
    permitProvenance: provenanceOf(permit),
    checksProvenance: provenanceOf(checks),
    clauseProvenance: provenanceOf(clause),
    attemptProvenance: provenanceOf(attempt),
    attempted,
    beginAttempt,
    clockSkewMs,
    staged,
    stagedNote,
  };
}
