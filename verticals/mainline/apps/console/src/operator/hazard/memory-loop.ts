// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * RECALLED · SHOWN TO · STATUS — the store → retrieve → act loop, in operator language.
 *
 * WHY THIS FILE EXISTS
 * ---------------------
 * The hackathon's first judging criterion is agentic memory design, and its rules ask for
 * footage of the memory layer at work rather than a narration of it. These three lines are
 * that footage. Each is a row a database actually holds, fetched over HTTP in the caller's
 * page load, addressed by identifiers `GET /v1/demo/subjects` supplied:
 *
 *   RECALLED   `mainline_meas.recall_run`      the recall run that armed this obligation
 *   SHOWN TO   `mainline.exposure_receipt`     who the obligation was put in front of
 *   STATUS     `mainline.blocking_check`       whether anything has answered it
 *
 * R17 — THE TENSE RULE, AND IT IS ONE CLAUSE AWAY FROM BEING BROKEN
 * ------------------------------------------------------------------
 * The recall run is a SEEDED ROW. It is a record of a pass that ran on 2026-08-02; it is
 * not a retrieval performed by this page. So every sentence about it here is PAST — "the
 * recall run that armed this obligation", "started", "was shown to". The words "watch it
 * remember", "the system just retrieved" and "searched the corpus" are forbidden and none
 * of them appears in this file. The present tense belongs to exactly one thing on this
 * screen, and it is not ours: the re-derivation the merge gate performs when the ISSUE
 * button is pressed, which W5 renders from the gate-run response.
 *
 * AND THERE IS NO VECTOR SEARCH HERE, BECAUSE THERE IS NO VECTOR SEARCH THERE
 * ----------------------------------------------------------------------------
 * `db/seeds/` carries no `recall_candidate`, no `event_cue`, no `clause_embedding` and no
 * `lex_posting` row; those tables exist and are empty, and `reads.py` reads none of them.
 * The channel that produced this obligation is `blame_ancestry` — deterministic graph
 * truth, admitted unconditionally, with `tau_applied = 0` because no threshold was
 * consulted and the recall contract refuses to let anyone claim one. A similarity score,
 * a nearest-neighbour plot or a shimmering embedding cloud would therefore be a FABRICATED
 * EXHIBIT. Nothing in this module draws one, and the honest claim — relational plus graph
 * memory in CockroachDB, re-derived at gate time — is the stronger claim anyway.
 *
 * ABSENCE
 * --------
 * A line whose row was not returned renders NOTHING. No dash, no zero, no "—" standing in
 * for a count, no greyed skeleton. The reason is returned in {@link MemoryLoopResult.absent}
 * so the card can state, in the deployment's own words, which read did not answer. A
 * placeholder in a memory panel is a number a judge might read as data.
 */

import {
  chipRow,
  el,
  humanSpan,
  numberText,
  pair,
  shortDigest,
  sourceLine,
  spanMs,
  utcInstant,
  type ChipLookup,
  type SourceRef,
} from './precursor';

/** The three lines, by id. Used by the card and asserted by the unit tests. */
export type MemoryLoopRowId = 'recalled' | 'shown-to' | 'status';

/** `data.counts` of `GET /v1/recall-runs/{run_id}` — `mainline_meas.recall_run`. */
export interface RecallCounts {
  readonly n_candidates: number | null;
  readonly n_blocking: number | null;
  readonly n_silenced: number | null;
  readonly n_deduped: number | null;
}

/** `data` of `GET /v1/recall-runs/{run_id}`, restricted to what this line renders. */
export interface RecallRunRow {
  readonly run_id: string | null;
  readonly started_at: string | null;
  readonly policy_version: string | null;
  readonly index_generation: string | null;
  readonly counts: RecallCounts | null;
}

/** `data` of `GET /v1/receipts/{receipt_id}` — `mainline.exposure_receipt`. */
export interface ReceiptRow {
  readonly actor_sub: string | null;
  readonly issued_at: string | null;
  readonly receipt_digest: string | null;
}

/** `data.checks[i]`, restricted to the three members the STATUS line reads. */
export interface StatusRow {
  readonly open: boolean | null;
  readonly disposition_id: string | null;
  readonly materialised_at: string | null;
}

/** One source: its row (or `null`), its chip lookup, its request, and why it was absent. */
export interface LoopSource<T> {
  readonly row: T | null;
  readonly chip: ChipLookup;
  readonly source: SourceRef | null;
  /**
   * What the deployment actually answered when the row did not come back — e.g.
   * `GET /v1/recall-runs/… answered 404`. Supplied by the caller from the real exchange,
   * never composed here.
   */
  readonly absence: string | null;
}

export interface MemoryLoopInput {
  readonly recall: LoopSource<RecallRunRow>;
  readonly receipt: LoopSource<ReceiptRow>;
  readonly status: LoopSource<StatusRow>;
  /** The pointer the blocking-checks payload claimed the check object at, e.g. `/checks/0`. */
  readonly statusPointer: string;
}

export interface MemoryLoopAbsence {
  readonly row: MemoryLoopRowId;
  readonly reason: string;
}

export interface MemoryLoopResult {
  /** `null` when not one of the three rows had data. */
  readonly element: HTMLElement | null;
  readonly rendered: readonly MemoryLoopRowId[];
  readonly absent: readonly MemoryLoopAbsence[];
}

const LABELS: Readonly<Record<MemoryLoopRowId, string>> = {
  recalled: 'RECALLED',
  'shown-to': 'SHOWN TO',
  status: 'STATUS',
};

/**
 * Render the three lines.
 *
 * The RECALLED line's `started_at` and the STATUS line's `materialised_at` are ALSO placed
 * side by side, in their own row, whenever the deployment returned both. That pair is one
 * of the three strongest concrete facts on the screen: the recall pass and the obligation
 * it produced are seconds apart, and the elapsed figure between them is computed in this
 * browser from those two emitted instants and is labelled as computed rather than chipped,
 * because no envelope claimed provenance for a value this client made.
 */
export function renderMemoryLoop(input: MemoryLoopInput): MemoryLoopResult {
  const rendered: MemoryLoopRowId[] = [];
  const absent: MemoryLoopAbsence[] = [];
  const loop = el('div', 'hz-loop');

  // ── RECALLED ───────────────────────────────────────────────────────────────────────
  const recall = input.recall.row;
  if (recall === null) {
    absent.push({
      row: 'recalled',
      reason: input.recall.absence ?? 'no mainline_meas.recall_run row was returned for this permit',
    });
  } else {
    const line = row('recalled', 'the recall run that armed this obligation');
    const values = el('div', 'hz-values');

    const runId = shortDigest(recall.run_id);
    if (runId !== null) {
      const idPair = pair('run', runId.short, 'hz-val hz-mono');
      idPair.title = runId.full;
      values.append(idPair);
    }
    if (recall.started_at !== null) {
      const human = utcInstant(recall.started_at);
      values.append(pair('started', human ?? recall.started_at));
      values.append(el('code', 'hz-iso', recall.started_at));
    }
    if (recall.policy_version !== null) {
      values.append(pair('policy', recall.policy_version, 'hz-val hz-mono'));
    }
    if (recall.index_generation !== null) {
      values.append(pair('index generation', recall.index_generation, 'hz-val hz-mono'));
    }
    line.append(values);

    const counts = recall.counts;
    if (counts !== null) {
      const arithmetic = el('div', 'hz-counts');
      appendCount(arithmetic, 'candidates', counts.n_candidates);
      appendCount(arithmetic, 'blocking', counts.n_blocking);
      appendCount(arithmetic, 'silenced', counts.n_silenced);
      appendCount(arithmetic, 'deduped', counts.n_deduped);
      if (arithmetic.childElementCount > 0) {
        line.append(arithmetic);
      }
    }

    appendChips(line, input.recall.chip, [
      '/run_id',
      '/started_at',
      '/policy_version',
      '/index_generation',
      '/counts/n_candidates',
      '/counts/n_blocking',
      '/counts/n_silenced',
      '/counts/n_deduped',
    ]);
    appendSource(line, input.recall.source);
    loop.append(line);
    rendered.push('recalled');
  }

  // ── SHOWN TO ───────────────────────────────────────────────────────────────────────
  const receipt = input.receipt.row;
  if (receipt === null) {
    absent.push({
      row: 'shown-to',
      reason: input.receipt.absence ?? 'no mainline.exposure_receipt row was returned for this permit',
    });
  } else {
    const line = row('shown-to', 'the obligation was put in front of a named human');
    const values = el('div', 'hz-values');
    if (receipt.actor_sub !== null) {
      values.append(pair('actor', receipt.actor_sub, 'hz-val hz-val--loud'));
    }
    if (receipt.issued_at !== null) {
      const human = utcInstant(receipt.issued_at);
      values.append(pair('issued', human ?? receipt.issued_at));
      values.append(el('code', 'hz-iso', receipt.issued_at));
    }
    const digest = shortDigest(receipt.receipt_digest);
    if (digest !== null) {
      const digestPair = pair('receipt digest', digest.short, 'hz-val hz-mono');
      digestPair.title = digest.full;
      values.append(digestPair);
    }
    line.append(values);
    appendChips(line, input.receipt.chip, ['/actor_sub', '/issued_at', '/receipt_digest']);
    appendSource(line, input.receipt.source);
    loop.append(line);
    rendered.push('shown-to');
  }

  // ── STATUS ─────────────────────────────────────────────────────────────────────────
  const status = input.status.row;
  // `open` is read into its own binding first. A check whose `open` member did not arrive
  // is an ABSENT status, never a closed one: defaulting a missing boolean to false is how a
  // screen comes to report a gate as satisfied because a field was missing.
  const openFlag = status?.open ?? null;
  if (openFlag === null || status === null) {
    absent.push({
      row: 'status',
      reason: input.status.absence ?? 'no mainline.blocking_check row was returned for this permit',
    });
  } else {
    const line = row('status', 'whether anything has answered it');
    const values = el('div', 'hz-values');
    const state = el('span', openFlag ? 'hz-state hz-state--open' : 'hz-state hz-state--closed');
    state.append(el('span', 'hz-dot', '●'));
    state.append(el('span', 'hz-state-word', openFlag ? 'OPEN' : 'ANSWERED'));
    values.append(state);
    values.append(
      el(
        'span',
        'hz-val',
        openFlag
          ? 'unanswered on this permit — no disposition of it is live'
          : 'a live disposition answers it',
      ),
    );
    line.append(values);
    line.append(
      el(
        'p',
        'hz-sub',
        'open has no column: the read API derived it from the absence of a mainline.disposition ' +
          'row for this check that is neither retracted nor expired',
      ),
    );
    if (status.disposition_id === null) {
      line.append(pair('disposition_id', 'null', 'hz-val hz-mono'));
    } else {
      const held = shortDigest(status.disposition_id);
      line.append(pair('disposition_id', held?.short ?? status.disposition_id, 'hz-val hz-mono'));
    }
    appendChips(line, input.status.chip, [
      `${input.statusPointer}/open`,
      `${input.statusPointer}/disposition_id`,
    ]);
    appendSource(line, input.status.source);
    loop.append(line);
    rendered.push('status');
  }

  // ── the two instants, side by side ────────────────────────────────────────────────
  const startedAt = recall?.started_at ?? null;
  const materialisedAt = status?.materialised_at ?? null;
  if (startedAt !== null && materialisedAt !== null) {
    loop.append(renderInterval(startedAt, materialisedAt));
  }

  if (rendered.length === 0) {
    return { element: null, rendered, absent };
  }
  return { element: loop, rendered, absent };
}

/**
 * The recall pass and the obligation it produced, on one row, with the elapsed figure.
 *
 * Both instants are emitted columns. The elapsed figure is subtraction performed here, and
 * it says so on screen: it carries no provenance chip, because claiming one for a value
 * this client computed is the console composing an evidentiary assertion.
 */
function renderInterval(startedAt: string, materialisedAt: string): HTMLElement {
  const band = el('div', 'hz-interval');

  const left = el('div', 'hz-interval-cell');
  left.append(el('span', 'hz-label', 'recall run started'));
  left.append(el('span', 'hz-val', utcInstant(startedAt) ?? startedAt));
  left.append(el('code', 'hz-iso', startedAt));
  left.append(el('span', 'hz-sub', 'mainline_meas.recall_run.started_at'));

  const right = el('div', 'hz-interval-cell');
  right.append(el('span', 'hz-label', 'obligation materialised'));
  right.append(el('span', 'hz-val', utcInstant(materialisedAt) ?? materialisedAt));
  right.append(el('code', 'hz-iso', materialisedAt));
  right.append(el('span', 'hz-sub', 'mainline.blocking_check.materialised_at'));

  band.append(left);
  const gap = humanSpan(spanMs(startedAt, materialisedAt));
  const middle = el('div', 'hz-interval-gap');
  if (gap !== null) {
    middle.append(el('span', 'hz-gap-value', gap));
  }
  middle.append(el('span', 'hz-sub', 'subtracted in this browser from the two instants either side — not a column, and not chipped'));
  band.append(middle);
  band.append(right);
  return band;
}

function row(id: MemoryLoopRowId, gloss: string): HTMLElement {
  const line = el('div', `hz-line hz-line--${id}`);
  line.setAttribute('data-row', id);
  const head = el('div', 'hz-line-head');
  head.append(el('span', 'hz-line-label', LABELS[id]));
  head.append(el('span', 'hz-line-gloss', gloss));
  line.append(head);
  return line;
}

function appendCount(host: HTMLElement, label: string, value: number | null): void {
  const text = numberText(value);
  if (text === null) {
    return;
  }
  const cell = el('span', 'hz-count');
  cell.append(el('span', 'hz-count-n', text));
  cell.append(el('span', 'hz-count-label', label));
  host.append(cell);
}

function appendChips(host: HTMLElement, lookup: ChipLookup, pointers: readonly string[]): void {
  const chips = chipRow(lookup, pointers);
  if (chips !== null) {
    host.append(chips);
  }
}

function appendSource(host: HTMLElement, source: SourceRef | null): void {
  const line = sourceLine(source);
  if (line !== null) {
    host.append(line);
  }
}
