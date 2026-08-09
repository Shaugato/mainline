// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The clause-diff screen: one payload in, one panel out, and no blank state.
 *
 * `docs/leads/ui.md` gives the clause diff to the gate screen, and that is still where it
 * belongs: the gate refuses a merge, and the diff is what the reader opens to find out
 * what "weakened" meant. `ClauseDiff` is exported for exactly that embedding.
 *
 * It ALSO stands on its own route, for three reasons that are each independently
 * sufficient: the browser spec can address it without driving the gate first; the gate
 * surface may land after this one and the panel must be reachable meanwhile; and the diff
 * is a legitimate destination in its own right — an engineer following a blame pointer
 * arrives at a clause version, not at a permit.
 *
 * `diff` is not in `DECLARED_SURFACES`, which is a promise list this worker does not own.
 * The registry admits an undeclared surface deliberately (`buildRegistry`), classifies it
 * into the most restrictive register, and sorts it after every promise. That is the right
 * outcome and no file of another worker's needs editing to get it.
 *
 * ── STATES, AND THERE IS NO BLANK ONE ────────────────────────────────────────────
 *
 * idle    — no transport has been composed. Says so, names what is missing, and names
 *           who owes it. This is the state on `main` today and it is not an error.
 * loading — a status message.
 * refused — the kernel's refusal payload, verbatim (D18).
 * failed  — the transport's own failure text, verbatim. Never "something went wrong".
 * ready   — the panel.
 */

import { type ReactNode } from 'react';

import { useResource } from '../../data/useResource';
import { useRoute } from '../../app/router';
import { SURFACE_REGISTRY } from '../../app/surfaces';
import type { MainlineTransport } from '../../data/transport';
import type { ClauseResponse } from '../../data/types.generated';
import { Mono, ProvenanceChip, RegisterFrame, Sqlstate } from '../../design/primitives';

import { ClauseDiff } from './ClauseDiff';
import styles from './diff.module.css';
import { buildClauseDiff } from './engine/build';
import { useDiffTransport } from './transport-context';

type ClauseData = ClauseResponse['data'];

/**
 * The address the capture bundle carries.
 *
 * An ADDRESS, not data: it selects which row to ask for and asserts nothing about what
 * comes back. `#/diff?clause=…&commit=…` overrides both. It is spelled out here rather
 * than left blank so that a demo URL with no query string still asks a real question.
 */
const DEMO_CLAUSE = '018f3a30-2200-7d10-9f31-0c9a4e77bb02';
const DEMO_COMMIT = '5f916282a2a3e5765f916282a2a3e5765f916282a2a3e5765f916282a2a3e576';

function NoTransport({
  clauseUuid,
  commitId,
}: {
  readonly clauseUuid: string;
  readonly commitId: string;
}): ReactNode {
  return (
    <div className={styles.absence} data-testid="diff-no-transport">
      <p className={styles.absenceHead}>NO BYTES</p>
      <div className={styles.absenceBody}>
        <p>
          This console has no transport composed, so nothing has been requested and nothing is
          being shown. The surface would ask for{' '}
          <code className={styles.mono}>clause_version</code> at{' '}
          <code className={styles.mono}>
            GET /v1/clauses/{clauseUuid}/versions/{commitId}
          </code>
          .
        </p>
        <p>
          A replay transport needs a verified <code className={styles.mono}>EvidenceBundle</code>
          , and a bundle cannot be opened without the in-browser verifier
          (<code className={styles.mono}>ui/verifier-custody-room</code>) — a bundle player
          with no verifier is a mock, and this console does not ship one. Until that line of
          composition exists, this screen reports an absence rather than inventing a clause.
        </p>
      </div>
    </div>
  );
}

export interface ClauseDiffScreenProps {
  /** Explicit transport, for the gate screen and the browser harness. */
  readonly transport?: MainlineTransport | null;
  readonly clauseUuid?: string;
  readonly commitId?: string;
}

export function ClauseDiffScreen({
  transport,
  clauseUuid,
  commitId,
}: ClauseDiffScreenProps): ReactNode {
  const route = useRoute(SURFACE_REGISTRY);
  const contextTransport = useDiffTransport();
  const active = transport === undefined ? contextTransport : transport;

  const clause = clauseUuid ?? route.params.get('clause') ?? DEMO_CLAUSE;
  const commit = commitId ?? route.params.get('commit') ?? DEMO_COMMIT;

  const { state } = useResource<ClauseData>(active, {
    resource: 'clause_version',
    path: { clause_uuid: clause, commit_id: commit },
  });

  if (state.status === 'idle') {
    return <NoTransport clauseUuid={clause} commitId={commit} />;
  }

  if (state.status === 'loading') {
    return (
      <p className={styles.note} role="status" data-testid="diff-loading">
        Requesting clause {clause} at commit {commit}…
      </p>
    );
  }

  if (state.status === 'refused') {
    return (
      <RegisterFrame
        register="evidence"
        as="section"
        label="Refused"
        bordered
        data-testid="diff-refused"
      >
        <div className={styles.chips}>
          <ProvenanceChip kind="db:constraint" detail={state.refusal.constraint} />
        </div>
        <p className={styles.absenceHead}>
          <Sqlstate code={state.refusal.sqlstate} />
        </p>
        <p className={styles.absenceBody}>
          <Mono>{state.refusal.message}</Mono>
        </p>
      </RegisterFrame>
    );
  }

  if (state.status === 'failed') {
    return (
      <div className={styles.absence} data-testid="diff-failed">
        <p className={styles.absenceHead}>{state.failure}</p>
        <pre className={styles.text}>{state.detail}</pre>
      </div>
    );
  }

  const model = buildClauseDiff({
    clauseUuid: state.data.clause_uuid,
    version: state.data.version,
    parent: state.data.parent ?? null,
    delta: state.data.delta,
  });

  const stagedNote = state.exchange.envelope.staged
    ? (state.exchange.envelope.staged_note ??
      'The payload is marked staged and carries no note saying what was staged.')
    : undefined;

  return stagedNote === undefined ? (
    <ClauseDiff model={model} />
  ) : (
    <ClauseDiff model={model} staged={stagedNote} />
  );
}
