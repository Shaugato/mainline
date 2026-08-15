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
 * ── HOW THIS SCREEN LEARNS WHICH CLAUSE, AND WHY IT NO LONGER CARRIES ONE ─────────
 *
 * Until 2026-08-15 this module held two constants naming a clause and a commit, under a
 * docstring calling them *"the address the capture bundle carries"*. They were not that.
 * Measured against the live URL, each answered **404**: no seed in this repository has
 * ever written either, and the capture bundle does not carry them either. A judge clicking
 * `diff` got the kernel's not-found. The two values are recorded, once, in
 * `docs/leads/screens-work-plan.md` §2.3 — not here, where the next reader could copy one.
 *
 * They are DELETED rather than corrected. A better constant fails the same way against the
 * next deployment, because a clause identifier in a console file is a claim about a row
 * this console did not write. The address now comes from one of two places and nowhere
 * else: `#/diff?clause=…&commit=…`, which always wins, or the kernel's own subject index
 * (`src/data/demo-subjects.ts`, `GET /v1/demo/subjects`). When neither names a clause, the
 * screen says so and asks for nothing.
 *
 * The two travel TOGETHER. A clause with no commit addresses no version, so one without
 * the other is treated as no address at all rather than as half a request.
 *
 * ── STATES, AND THERE IS NO BLANK ONE ────────────────────────────────────────────
 *
 * no source   — no transport has been composed. Says so, names what is missing, and names
 *               who owes it. This is the state on `main` today and it is not an error.
 * no subject  — nothing named a clause version to read: no `?clause=`/`?commit=`, and the
 *               subject index did not supply one. Names the route it asked and what came
 *               back, verbatim.
 * loading     — a status message.
 * refused     — the kernel's refusal payload, verbatim (D18).
 * failed      — the transport's own failure text, verbatim. Never "something went wrong".
 * ready       — the panel.
 */

import { type ReactNode } from 'react';

import {
  addressSubject,
  subjectAbsence,
  useDemoSubjects,
  type SubjectAddressShape,
} from '../../data/demo-subjects';
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

/** `#/diff?clause=<uuid>&commit=<hex>`. */
export const CLAUSE_PARAM = 'clause';
export const COMMIT_PARAM = 'commit';

/**
 * What this surface asks the subject index for.
 *
 * It reads TWO members and reports the absence against `clause_uuid`, because a clause
 * with no head commit is the case the index expresses by nulling both — and naming one
 * member is more useful to a reader than naming a pair.
 */
const ADDRESS: SubjectAddressShape = {
  noun: 'clause version',
  member: 'clause_uuid',
  subjectKey: 'clause',
  example: `#/diff?${CLAUSE_PARAM}=<uuid>&${COMMIT_PARAM}=<hex>`,
};

/**
 * A path value that satisfies `resources.ts`'s unreserved-token rule while the read is
 * disabled. It is never sent: `useResource` performs no exchange when `enabled` is false.
 * The same device, for the same reason, as `useGateData`'s `PLACEHOLDER`.
 */
const UNADDRESSED = 'unaddressed';

function NoTransport({
  clauseUuid,
  commitId,
}: {
  readonly clauseUuid: string | null;
  readonly commitId: string | null;
}): ReactNode {
  const addressed = clauseUuid !== null && commitId !== null;
  const requestLine = addressed
    ? `GET /v1/clauses/${clauseUuid}/versions/${commitId}`
    : 'GET /v1/clauses/{clause_uuid}/versions/{commit_id}';
  const which = addressed
    ? ''
    : ' It does not know which clause version that is: the address is not in the URL, and with ' +
      'no transport there is nothing to ask the kernel’s subject index either.';
  return (
    <div className={styles.absence} data-testid="diff-no-transport">
      <p className={styles.absenceHead}>NO BYTES</p>
      <div className={styles.absenceBody}>
        <p>
          This console has no transport composed, so nothing has been requested and nothing is
          being shown. The surface would ask for{' '}
          <code className={styles.mono}>clause_version</code> at{' '}
          <code className={styles.mono}>{requestLine}</code>.{which}
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

  const index = useDemoSubjects(active);
  const clauseAddress = addressSubject(
    clauseUuid ?? route.params.get(CLAUSE_PARAM),
    index,
    (subjects) => subjects.clauseUuid,
  );
  const commitAddress = addressSubject(
    commitId ?? route.params.get(COMMIT_PARAM),
    index,
    (subjects) => subjects.commitId,
  );

  // Together or not at all — a clause with no commit addresses no version.
  const addressed = clauseAddress.value !== null && commitAddress.value !== null;
  const clause = addressed ? clauseAddress.value : null;
  const commit = addressed ? commitAddress.value : null;

  const { state } = useResource<ClauseData>(
    active,
    {
      resource: 'clause_version',
      path: { clause_uuid: clause ?? UNADDRESSED, commit_id: commit ?? UNADDRESSED },
    },
    { enabled: addressed },
  );

  // The transport question is answered before the subject question, because "nobody gave
  // this console a source" is the more fundamental absence: with no transport there is
  // nothing to ask the subject index either, and two panels saying so would be one too
  // many.
  if (active === null) {
    return <NoTransport clauseUuid={clause} commitId={commit} />;
  }

  if (clause === null || commit === null) {
    const absence = subjectAbsence(index, ADDRESS);
    return (
      <div className={styles.absence} data-testid="diff-no-subject" data-index={index.status}>
        <p className={styles.absenceHead}>{absence.kicker}</p>
        <div className={styles.absenceBody}>
          {absence.paragraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
          <p>
            {absence.override} <Mono>{absence.example}</Mono>
          </p>
          {absence.detail !== null && (
            <pre className={styles.text} data-testid="diff-subject-index-detail">
              {absence.detail}
            </pre>
          )}
        </div>
      </div>
    );
  }

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
