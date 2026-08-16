// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE READS — one thin, typed wrapper per route the operator screens open on.
 *
 * Each function does three things and nothing else: build the path from an identifier that
 * came from {@link resolveAddressing}, name the `resource` the envelope must answer with,
 * and hand back the {@link Exchange}. No caching, no merging, no derived fields, no
 * defaulting of a null. A screen gets the payload the kernel sent and renders absence for
 * anything it did not.
 *
 * The routes are the ones `app.py` declares — the table is closed, and a path assembled
 * anywhere else in `src/operator/**` is a review finding. `encodeURIComponent` on every
 * interpolated identifier: the values come from the kernel, but a client that builds a
 * path by concatenation and happens to be safe is not the same as one that cannot be
 * unsafe.
 *
 * The `data` types are TYPE-ONLY imports from the generated contract model
 * (`src/data/types.generated.ts`), which R1 permits precisely because a type erases to
 * zero bytes and the 1,108-byte headroom on the existing entry chunk is the hardest
 * constraint in the repository right now. They are shapes, not guarantees — see the note
 * on {@link Exchange.data}.
 */

import { get, type Exchange, type RequestOptions } from './client';

import type {
  BlockingChecksResponse,
  ChangeRequestResponse,
  ClauseResponse,
  DispositionResponse,
  ExposureReceipt,
  Permit,
  RecallRun,
} from '../../data/types.generated';

/** `GET /v1/permits/{permit_id}` — the subject the gate refuses. */
export function readPermit(
  permitId: string,
  options?: RequestOptions,
): Promise<Exchange<Permit>> {
  return get<Permit>(`/v1/permits/${encodeURIComponent(permitId)}`, {
    ...options,
    expectResource: 'permit',
  });
}

/** `GET /v1/permits/{permit_id}/blocking-checks` — the obligations still open on it. */
export function readBlockingChecks(
  permitId: string,
  options?: RequestOptions,
): Promise<Exchange<BlockingChecksResponse['data']>> {
  return get<BlockingChecksResponse['data']>(
    `/v1/permits/${encodeURIComponent(permitId)}/blocking-checks`,
    { ...options, expectResource: 'blocking_checks' },
  );
}

/**
 * `GET /v1/change-requests/{cr_id}/blocking-checks` — the SECOND subject's obligations.
 *
 * The mirror of the read above, and deliberately the same contract: the payload's
 * `subject_kind` says which subject answered, and `blocking-check.schema.json` has always
 * required `subject_kind` / `subject_id` rather than `permit_id`. So this is one document
 * governing two routes, not a second document to keep in step with the first.
 *
 * `expectResource` is `cr_blocking_checks` and not `blocking_checks`, because the envelope
 * names the RESOURCE and not the contract. A deployment that answered this path with the
 * permit's resource key would be answering a different question than the one asked, and the
 * client fails it closed rather than rendering it as this change request's.
 *
 * Until 2026-08-16 this route did not exist and the change screen proved it by rendering the
 * deployment's own 404 route table. That absence path is still there and still correct
 * against a deployment that does not carry the route; this is the read for one that does.
 */
export function readCrBlockingChecks(
  crId: string,
  options?: RequestOptions,
): Promise<Exchange<BlockingChecksResponse['data']>> {
  return get<BlockingChecksResponse['data']>(
    `/v1/change-requests/${encodeURIComponent(crId)}/blocking-checks`,
    { ...options, expectResource: 'cr_blocking_checks' },
  );
}

/**
 * `GET /v1/clauses/{clause_uuid}/versions/{commit_id}` — the clause the check hangs off.
 *
 * A clause identifier without a commit addresses no version, so the two travel together or
 * not at all (`subjects.schema.json`, `commit_id`). Both come from addressing.
 */
export function readClauseVersion(
  clauseUuid: string,
  commitId: string,
  options?: RequestOptions,
): Promise<Exchange<ClauseResponse['data']>> {
  return get<ClauseResponse['data']>(
    `/v1/clauses/${encodeURIComponent(clauseUuid)}/versions/${encodeURIComponent(commitId)}`,
    { ...options, expectResource: 'clause_version' },
  );
}

/**
 * `GET /v1/recall-runs/{run_id}` — the recall run that armed the obligation.
 *
 * R17's tense discipline lives on the screen, not here: this is the run that ALREADY
 * happened, and its `started_at` is the past.
 */
export function readRecallRun(
  runId: string,
  options?: RequestOptions,
): Promise<Exchange<RecallRun>> {
  return get<RecallRun>(`/v1/recall-runs/${encodeURIComponent(runId)}`, {
    ...options,
    expectResource: 'recall_run',
  });
}

/**
 * `GET /v1/receipts/{receipt_id}` — what was shown, to whom, and when.
 *
 * A disposition composite-FKs `(receipt_id, check_id)` into `exposure_line`, so "it never
 * showed me" and "I signed without looking" are both foreign-key violations. R14 labels
 * `actor_sub` the ACCEPTOR and gives it no issuing role.
 */
export function readReceipt(
  receiptId: string,
  options?: RequestOptions,
): Promise<Exchange<ExposureReceipt>> {
  return get<ExposureReceipt>(`/v1/receipts/${encodeURIComponent(receiptId)}`, {
    ...options,
    expectResource: 'exposure_receipt',
  });
}

/** `GET /v1/change-requests/{cr_id}` — the second gated subject (screen two). */
export function readChangeRequest(
  crId: string,
  options?: RequestOptions,
): Promise<Exchange<ChangeRequestResponse['data']>> {
  return get<ChangeRequestResponse['data']>(`/v1/change-requests/${encodeURIComponent(crId)}`, {
    ...options,
    expectResource: 'change_request',
  });
}

/**
 * `GET /v1/checks/{check_id}/disposition` — the defeaters offered against one obligation.
 *
 * Each is a QUESTION with a clearance behind it; there is no global "N/A". R11 permits
 * this read for the change request's check **only if a check id was obtained from a live
 * read** — a hardcoded one is forbidden, and there is nowhere in this module one could go.
 */
export function readDisposition(
  checkId: string,
  options?: RequestOptions,
): Promise<Exchange<DispositionResponse['data']>> {
  return get<DispositionResponse['data']>(
    `/v1/checks/${encodeURIComponent(checkId)}/disposition`,
    { ...options, expectResource: 'disposition' },
  );
}

/**
 * The route table a 404 carried, verbatim, or null.
 *
 * `app.py` answers an unrouted path with `{"error":{"kind":"no_route", …,"declared":[…]}}`
 * — the deployment listing every route it does declare. R11 makes that list the EVIDENCE
 * for an absence on screen two: no route yields a change request's blocking-check id, and
 * the honest way to show that is the deployment's own table rather than a sentence we
 * wrote. This reads what already arrived; it sends nothing.
 */
export function declaredRoutes(exchange: Exchange<unknown>): readonly string[] | null {
  const declared = exchange.problem?.extra.declared;
  if (!Array.isArray(declared)) {
    return null;
  }
  return (declared as readonly unknown[]).filter((item): item is string => typeof item === 'string');
}
