// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * HSG250 Figure 1 element 6 — HAZARD IDENTIFICATION. The visual centre of the permit.
 *
 * WHAT A JUDGE IS MEANT TO SEE
 * -----------------------------
 * A site supervisor's own permit-to-work screen, with one hazard on it that nobody typed.
 * It was raised because a 2019 incident investigation named the clause this permit relies
 * on as the control that failed, and the recall run that armed it, the human it was shown
 * to, and the fact that nothing has answered it are all rows in CockroachDB — read here
 * over HTTP, from the same origin that serves this page, in this page load.
 *
 * That is the store → retrieve → act loop the hackathon's first judging criterion is
 * scored on, and this card is the only place in the demo where it is visible.
 *
 * THE FOUR READS, AND WHY EACH ONE IS HERE
 * -----------------------------------------
 *   GET /v1/permits/{permit_id}/blocking-checks   the obligation, its precursor event
 *                                                 joined inline, and its projected
 *                                                 severity — the STORE fact and the
 *                                                 RETRIEVE result in one payload
 *   GET /v1/recall-runs/{run_id}                  the recall run's own arithmetic
 *   GET /v1/receipts/{receipt_id}                 who it was shown to, and when
 *   GET /v1/clauses/{clause_uuid}/ancestry        the investigation's own sentence, and
 *                                                 the blame closure the obligation's
 *                                                 severity was projected from
 *
 * Three of the four go through `kernel/reads.ts`. The fourth does not, because `reads.ts`
 * publishes no wrapper for the ancestry route; this file therefore builds that one path
 * itself, in the same idiom — `encodeURIComponent` on the identifier, `expectResource` on
 * the call — and this comment exists so the omission is a recorded fact rather than a
 * quiet exception. If W2 adds `readClauseAncestry`, this call should move to it.
 *
 * NOTHING ON THIS CARD IS COMPOSED
 * ---------------------------------
 * There is no UUID, no digest, no count, no SQLSTATE and no timestamp literal in these
 * three source files. Every identifier is resolved by `GET /v1/demo/subjects` through
 * {@link Addressing}; every value rendered arrived in a response body; every provenance
 * chip is one `chipFor()` found at the exact pointer the payload claimed it at. There is
 * no `setTimeout`, no artificial delay, and no skeleton that pretends to be work: the
 * pending state is the real promise, and it names the requests that are outstanding.
 *
 * TWO THINGS THAT WOULD MAKE THIS CARD WORTHLESS, NAMED SO NOBODY DRIFTS INTO THEM
 * ---------------------------------------------------------------------------------
 * 1. The present tense for the recall. It is a seeded row recording a pass that ran on a
 *    date the card prints. See `memory-loop.ts`'s R17 note.
 * 2. A similarity score, a vector plot or a nearest-neighbour affordance of any kind.
 *    There are no embeddings, cues or candidate rows in this world; the channel is
 *    `blame_ancestry`, which this card renders by name.
 */

import { chipFor, type Envelope, type ProvChip } from '../kernel/envelope';
import { get, type Exchange } from '../kernel/client';
import { readBlockingChecks, readRecallRun, readReceipt } from '../kernel/reads';

import type { Addressing } from '../kernel/addressing';

import {
  el,
  renderPrecursor,
  type ChipClaim,
  type ChipLookup,
  type PrecursorAncestry,
  type PrecursorCheck,
  type SeedCitation,
  type SourceRef,
} from './precursor';
import {
  renderMemoryLoop,
  type MemoryLoopAbsence,
  type RecallRunRow,
  type ReceiptRow,
  type StatusRow,
} from './memory-loop';

import './hazard.css';

/**
 * The ONE editorial sentence on this card, and it earns its place.
 *
 * Every other character here is a column, a label or a provenance pointer. This one is a
 * claim we make, and it is the difference between MAINLINE and every other permit-to-work
 * product on the market: the hazard on this permit was not chosen from a drop-down by the
 * person who least wanted to see it.
 */
const STRAPLINE = 'raised by recall, not by a checklist';

/**
 * A citation into THIS REPOSITORY. Not a value from any response, and rendered under a
 * label that says exactly that.
 *
 * `r2-memory.md` §4.3 rules that the severity the seed handed the insert must be shown as
 * a code citation with its file and line, and never as a live value, because the live
 * value does not exist — `fn_check_project` overwrote it before the row was stored. The
 * commit is pinned so a reader who checks this later checks the same bytes.
 */
const SEED_CITATION: SeedCitation = {
  file: 'verticals/mainline/db/seeds/demo/demo_permit.sql',
  line: 318,
  commit: '4af05e1',
  quoted: "0, 'routine', 0,   -- projected over by fn_check_project (MI25)",
};

/** Everything the card fetched, kept whole so the raw drawer can show the bytes. */
export interface HazardExchanges {
  readonly checks: Exchange<unknown> | null;
  readonly recall: Exchange<unknown> | null;
  readonly receipt: Exchange<unknown> | null;
  readonly ancestry: Exchange<unknown> | null;
}

/** The rendered card, plus what it could not render and why. */
export interface HazardCardResult {
  readonly element: HTMLElement;
  readonly exchanges: HazardExchanges;
  readonly absent: readonly MemoryLoopAbsence[];
}

// ─────────────────────────────────────────────────────────────────────────────────────
// Reading a payload we did not validate: absence over invention, everywhere.
// ─────────────────────────────────────────────────────────────────────────────────────

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function at(value: unknown, key: string): unknown {
  return isRecord(value) ? value[key] : undefined;
}

function str(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function bool(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function firstOf(value: unknown): { readonly item: unknown; readonly index: number } | null {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }
  return { item: (value as readonly unknown[])[0], index: 0 };
}

/**
 * The exact-match chip lookup, from W2's `chipFor` and from nothing else.
 *
 * `kernel/envelope.ts` states the rule in its own words: there is no fallback chip and no
 * ancestor lookup, because widening a claim the emitter did not make would be the console
 * composing an evidentiary assertion. This wrapper adds the pointer to the answer so the
 * chip on screen can print where it was claimed; it never invents one.
 */
function lookupFor(envelope: Envelope | null): ChipLookup {
  return (pointer: string): ChipClaim | null => {
    const kind: ProvChip | null = chipFor(envelope, pointer);
    return kind === null ? null : { kind, pointer };
  };
}

const NO_CHIPS: ChipLookup = () => null;

/** The request behind a block, as observed. `observedAt` is the SERVER's clock, never ours. */
function sourceOf(exchange: Exchange<unknown> | null): SourceRef | null {
  const envelope = exchange?.envelope ?? null;
  if (envelope === null || exchange === null) {
    return null;
  }
  return {
    resource: envelope.resource,
    method: exchange.method,
    path: exchange.path,
    status: exchange.status,
    wireBytes: exchange.wireBytes,
    observedAt: envelope.observed_at,
  };
}

/**
 * Why a read produced no row, in the deployment's own words wherever it supplied any.
 *
 * A problem body's `detail` is the API's sentence and is rendered verbatim. A transport
 * failure's `detail` is this client's sentence about its own attempt. Neither is a
 * paraphrase, and there is no generic "could not load".
 */
function absenceOf(exchange: Exchange<unknown> | null, path: string | null): string | null {
  if (exchange === null) {
    return path === null
      ? 'no identifier for this subject came back from GET /v1/demo/subjects, so no request was sent'
      : `no request was sent to ${path}: the identifier it needs was not in the subject index`;
  }
  if (exchange.problem !== null) {
    return `${exchange.method} ${exchange.path} answered ${String(exchange.status)} — ${exchange.problem.detail}`;
  }
  if (exchange.failure !== null) {
    return `${exchange.method} ${exchange.path} — ${exchange.failure.kind}: ${exchange.failure.detail}`;
  }
  if (exchange.data === null) {
    return `${exchange.method} ${exchange.path} answered ${String(exchange.status)} with no data member`;
  }
  return `${exchange.method} ${exchange.path} answered ${String(exchange.status)} and carried no row for this subject`;
}

// ─────────────────────────────────────────────────────────────────────────────────────
// The reads
// ─────────────────────────────────────────────────────────────────────────────────────

/**
 * Fetch everything the card renders. Four real, same-origin GETs, in parallel.
 *
 * The ancestry read is skipped when addressing carried no clause identifier: a path built
 * around a missing identifier is a 400 we asked for, and an absence is not a reason to
 * invent an address.
 */
export async function loadHazard(addressing: Addressing): Promise<HazardExchanges> {
  const permitId = addressing.permitId;
  const runId = addressing.runId;
  const receiptId = addressing.receiptId;
  const clauseUuid = addressing.clauseUuid;

  const [checks, recall, receipt, ancestry] = await Promise.all([
    permitId === null ? Promise.resolve(null) : readBlockingChecks(permitId),
    runId === null ? Promise.resolve(null) : readRecallRun(runId),
    receiptId === null ? Promise.resolve(null) : readReceipt(receiptId),
    clauseUuid === null
      ? Promise.resolve(null)
      : get<unknown>(`/v1/clauses/${encodeURIComponent(clauseUuid)}/ancestry`, {
          expectResource: 'clause_ancestry',
        }),
  ]);

  return {
    checks: checks as Exchange<unknown> | null,
    recall: recall as Exchange<unknown> | null,
    receipt: receipt as Exchange<unknown> | null,
    ancestry,
  };
}

// ─────────────────────────────────────────────────────────────────────────────────────
// The render
// ─────────────────────────────────────────────────────────────────────────────────────

/** Render the card from exchanges that have already landed. Pure: no I/O, no clock. */
export function renderHazardCard(exchanges: HazardExchanges): HazardCardResult {
  const section = el('section', 'hz-card');
  section.setAttribute('data-operator-element', '6');

  const headingId = 'hz-hazard-heading';
  const heading = el('h3', 'hz-h3', 'Hazard identification');
  heading.id = headingId;
  section.setAttribute('aria-labelledby', headingId);

  const head = el('header', 'hz-card-head');
  head.append(heading);
  head.append(el('p', 'hz-strapline', STRAPLINE));
  section.append(head);

  // ── the obligation and its precursor ───────────────────────────────────────────────
  const checksData = exchanges.checks?.data ?? null;
  const found = firstOf(at(checksData, 'checks'));
  const checkPointer = found === null ? '/checks/0' : `/checks/${String(found.index)}`;
  const checkRow = found === null ? null : found.item;

  const check: PrecursorCheck | null =
    checkRow === null
      ? null
      : {
          clause_label: str(at(checkRow, 'clause_label')),
          clause_uuid: str(at(checkRow, 'clause_uuid')),
          commit_id: str(at(checkRow, 'commit_id')),
          origin: str(at(checkRow, 'origin')),
          severity: num(at(checkRow, 'severity')),
          virulence: str(at(checkRow, 'virulence')),
          closure_gen: num(at(checkRow, 'closure_gen')),
          evidence_summary: str(at(checkRow, 'evidence_summary')),
          materialised_at: str(at(checkRow, 'materialised_at')),
          precursor: readPrecursorEvent(at(checkRow, 'precursor')),
        };

  const ancestryData = exchanges.ancestry?.data ?? null;
  const ancestry: PrecursorAncestry | null = ancestryData === null ? null : readAncestry(ancestryData);

  const checksChip = lookupFor(exchanges.checks?.envelope ?? null);
  const ancestryChip = lookupFor(exchanges.ancestry?.envelope ?? null);

  const precursor = renderPrecursor({
    check,
    checkPointer,
    checkChip: checksChip,
    checkSource: sourceOf(exchanges.checks),
    ancestry,
    ancestryChip,
    ancestrySource: sourceOf(exchanges.ancestry),
    seedCitation: SEED_CITATION,
  });
  if (precursor.element !== null) {
    section.append(precursor.element);
  }

  // ── the loop ───────────────────────────────────────────────────────────────────────
  const recallData = exchanges.recall?.data ?? null;
  const receiptData = exchanges.receipt?.data ?? null;

  const recallRow: RecallRunRow | null =
    recallData === null
      ? null
      : {
          run_id: str(at(recallData, 'run_id')),
          started_at: str(at(recallData, 'started_at')),
          policy_version: str(at(recallData, 'policy_version')),
          index_generation: str(at(recallData, 'index_generation')),
          counts: readCounts(at(recallData, 'counts')),
        };

  const receiptRow: ReceiptRow | null =
    receiptData === null
      ? null
      : {
          actor_sub: str(at(receiptData, 'actor_sub')),
          issued_at: str(at(receiptData, 'issued_at')),
          receipt_digest: str(at(receiptData, 'receipt_digest')),
        };

  const statusRow: StatusRow | null =
    checkRow === null
      ? null
      : {
          open: bool(at(checkRow, 'open')),
          disposition_id: str(at(checkRow, 'disposition_id')),
          materialised_at: str(at(checkRow, 'materialised_at')),
        };

  const loop = renderMemoryLoop({
    recall: {
      row: recallRow,
      chip: recallRow === null ? NO_CHIPS : lookupFor(exchanges.recall?.envelope ?? null),
      source: sourceOf(exchanges.recall),
      absence: absenceOf(exchanges.recall, '/v1/recall-runs/{run_id}'),
    },
    receipt: {
      row: receiptRow,
      chip: receiptRow === null ? NO_CHIPS : lookupFor(exchanges.receipt?.envelope ?? null),
      source: sourceOf(exchanges.receipt),
      absence: absenceOf(exchanges.receipt, '/v1/receipts/{receipt_id}'),
    },
    status: {
      row: statusRow,
      chip: statusRow === null ? NO_CHIPS : checksChip,
      source: sourceOf(exchanges.checks),
      absence: absenceOf(exchanges.checks, '/v1/permits/{permit_id}/blocking-checks'),
    },
    statusPointer: checkPointer,
  });
  if (loop.element !== null) {
    section.append(loop.element);
  }

  // ── what did not answer, in the deployment's own words ─────────────────────────────
  const absences: MemoryLoopAbsence[] = [...loop.absent];
  if (precursor.element === null) {
    section.append(
      el(
        'p',
        'hz-empty',
        'this deployment returned no blocking check for this permit, so this card has nothing to show',
      ),
    );
  }
  if (absences.length > 0) {
    const strip = el('div', 'hz-absent');
    strip.append(el('h4', 'hz-h4', 'not returned by this deployment'));
    const list = el('ul', 'hz-absent-list');
    for (const item of absences) {
      list.append(el('li', 'hz-absent-item', item.reason));
    }
    strip.append(list);
    section.append(strip);
  }

  return { element: section, exchanges, absent: absences };
}

function readPrecursorEvent(value: unknown): PrecursorCheck['precursor'] {
  if (!isRecord(value)) {
    return null;
  }
  return {
    external_ref: str(value.external_ref),
    kind: str(value.kind),
    title: str(value.title),
    occurred_at: str(value.occurred_at),
    severity_gate: num(value.severity_gate),
    severity_actual: num(value.severity_actual),
    severity_potential: num(value.severity_potential),
    severity_basis: str(value.severity_basis),
    source_object_key: str(value.source_object_key),
    source_sha256: str(value.source_sha256),
  };
}

function readAncestry(value: unknown): PrecursorAncestry {
  const closureRaw = at(value, 'closure');
  const edge = firstOf(at(value, 'blame_edges'));
  return {
    as_of_commit: str(at(value, 'as_of_commit')),
    closure: isRecord(closureRaw)
      ? {
          max_severity: num(closureRaw.max_severity),
          virulence: str(closureRaw.virulence),
          closure_gen: num(closureRaw.closure_gen),
          ancestor_count: num(closureRaw.ancestor_count),
          computed_by: str(closureRaw.computed_by),
          computed_at: str(closureRaw.computed_at),
        }
      : null,
    attribution: edge === null ? null : str(at(edge.item, 'attribution')),
    basis: edge === null ? null : str(at(edge.item, 'basis')),
    state: edge === null ? null : str(at(edge.item, 'state')),
  };
}

function readCounts(value: unknown): RecallRunRow['counts'] {
  if (!isRecord(value)) {
    return null;
  }
  return {
    n_candidates: num(value.n_candidates),
    n_blocking: num(value.n_blocking),
    n_silenced: num(value.n_silenced),
    n_deduped: num(value.n_deduped),
  };
}

// ─────────────────────────────────────────────────────────────────────────────────────
// Mounting, for W3
// ─────────────────────────────────────────────────────────────────────────────────────

/**
 * Mount the card into a container. One call, awaited by the caller.
 *
 * The pending state is a plain line naming the requests that are outstanding. It is
 * replaced when the real promise settles and by nothing else — there is no timer here, and
 * a reveal driven by a timer would be the one thing this demo may not do.
 */
export async function mountHazardCard(
  container: HTMLElement,
  addressing: Addressing,
): Promise<HazardCardResult> {
  container.replaceChildren(pendingNode(addressing));
  const exchanges = await loadHazard(addressing);
  const result = renderHazardCard(exchanges);
  container.replaceChildren(result.element);
  return result;
}

function pendingNode(addressing: Addressing): HTMLElement {
  const node = el('p', 'hz-pending');
  node.setAttribute('aria-live', 'polite');
  const outstanding: string[] = [];
  if (addressing.permitId !== null) {
    outstanding.push('/v1/permits/{permit_id}/blocking-checks');
  }
  if (addressing.runId !== null) {
    outstanding.push('/v1/recall-runs/{run_id}');
  }
  if (addressing.receiptId !== null) {
    outstanding.push('/v1/receipts/{receipt_id}');
  }
  if (addressing.clauseUuid !== null) {
    outstanding.push('/v1/clauses/{clause_uuid}/ancestry');
  }
  node.textContent =
    outstanding.length === 0
      ? 'no subject was addressable, so no request was sent'
      : `reading ${outstanding.join(' · ')}`;
  return node;
}

// Re-exported for W3, so the permit screen can name this card's types without reaching
// past its public surface into the two modules behind it.
export type { ChipClaim, ChipLookup, SourceRef } from './precursor';
export type { MemoryLoopAbsence, MemoryLoopRowId } from './memory-loop';
