// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * RECALLED · SHOWN TO · STATUS — the loop the first judging criterion is scored on.
 *
 * THE FIXTURES ARE TRANSCRIPTS. Every value below was captured from
 * `GET /v1/recall-runs/{run_id}`, `GET /v1/receipts/{receipt_id}` and
 * `GET /v1/permits/{permit_id}/blocking-checks` against `scripts/deploy/local_furl.py`
 * over the local CockroachDB node on 2026-08-15. They are renderer inputs. The tests below
 * assert what the renderer does with them, and above all what it does when they are NOT
 * there — because the failure mode that would sink this demo is a card that shows a run id,
 * a count or a signer for a row the deployment did not return.
 */

import { describe, expect, it } from 'vitest';

import {
  renderMemoryLoop,
  type MemoryLoopInput,
  type RecallRunRow,
  type ReceiptRow,
  type StatusRow,
} from '../../../../src/operator/hazard/memory-loop';
import type { ChipLookup, SourceRef } from '../../../../src/operator/hazard/precursor';

const RECALL: RecallRunRow = {
  run_id: 'dec0de00-0009-4000-8000-000000000001',
  started_at: '2026-08-02T03:00:00Z',
  policy_version: 'demo-recall-1.0',
  index_generation: 'g1',
  counts: { n_candidates: 1, n_blocking: 1, n_silenced: 0, n_deduped: 0 },
};

const RECEIPT: ReceiptRow = {
  actor_sub: 'demo.signer',
  issued_at: '2026-08-02T03:05:00Z',
  receipt_digest: '993c00c3f3c34a2bbf2bfd7646af7b5a51c594aa06f75fb6ce08cf4b5dd7af46',
};

const STATUS: StatusRow = {
  open: true,
  disposition_id: null,
  materialised_at: '2026-08-02T03:00:10Z',
};

const recallChip: ChipLookup = (pointer) =>
  [
    '/run_id',
    '/started_at',
    '/policy_version',
    '/index_generation',
    '/counts/n_candidates',
    '/counts/n_blocking',
    '/counts/n_silenced',
    '/counts/n_deduped',
  ].includes(pointer)
    ? { kind: 'db:column', pointer }
    : null;

const receiptChip: ChipLookup = (pointer) =>
  ['/actor_sub', '/issued_at', '/receipt_digest'].includes(pointer)
    ? { kind: 'db:column', pointer }
    : null;

const statusChip: ChipLookup = (pointer) =>
  pointer === '/checks/0/open' || pointer === '/checks/0/disposition_id'
    ? { kind: 'derived', pointer }
    : null;

const NO_CHIPS: ChipLookup = () => null;

function source(resource: string, path: string, bytes: number): SourceRef {
  return {
    resource,
    method: 'GET',
    path,
    status: 200,
    wireBytes: bytes,
    observedAt: '2026-08-15T11:06:45.481309Z',
  };
}

function input(over: {
  recall?: RecallRunRow | null;
  receipt?: ReceiptRow | null;
  status?: StatusRow | null;
  recallAbsence?: string | null;
  receiptAbsence?: string | null;
}): MemoryLoopInput {
  const recall = over.recall === undefined ? RECALL : over.recall;
  const receipt = over.receipt === undefined ? RECEIPT : over.receipt;
  const status = over.status === undefined ? STATUS : over.status;
  return {
    recall: {
      row: recall,
      chip: recall === null ? NO_CHIPS : recallChip,
      source: recall === null ? null : source('recall_run', '/v1/recall-runs/x', 2223),
      absence: over.recallAbsence ?? null,
    },
    receipt: {
      row: receipt,
      chip: receipt === null ? NO_CHIPS : receiptChip,
      source: receipt === null ? null : source('exposure_receipt', '/v1/receipts/x', 1817),
      absence: over.receiptAbsence ?? null,
    },
    status: {
      row: status,
      chip: status === null ? NO_CHIPS : statusChip,
      source: status === null ? null : source('blocking_checks', '/v1/permits/x/blocking-checks', 2408),
      absence: null,
    },
    statusPointer: '/checks/0',
  };
}

function text(result: ReturnType<typeof renderMemoryLoop>): string {
  return result.element?.textContent ?? '';
}

describe('renderMemoryLoop — the three lines, when the rows are there', () => {
  it('renders all three, in store → retrieve → act order', () => {
    const result = renderMemoryLoop(input({}));
    expect(result.rendered).toEqual(['recalled', 'shown-to', 'status']);
    expect(result.absent).toEqual([]);
    const rows = Array.from(result.element?.querySelectorAll('[data-row]') ?? []).map((node) =>
      node.getAttribute('data-row'),
    );
    expect(rows).toEqual(['recalled', 'shown-to', 'status']);
  });

  it('renders the recall run in the PAST tense, as the run that armed the obligation', () => {
    const out = text(renderMemoryLoop(input({})));
    expect(out).toContain('the recall run that armed this obligation');
    expect(out).toContain('demo-recall-1.0');
    expect(out).toContain('g1');
  });

  it('renders every count the payload carried, and no total it did not', () => {
    const out = text(renderMemoryLoop(input({})));
    expect(out).toContain('candidates');
    expect(out).toContain('blocking');
    expect(out).toContain('silenced');
    expect(out).toContain('deduped');
  });

  it('renders who the obligation was shown to, and when', () => {
    const out = text(renderMemoryLoop(input({})));
    expect(out).toContain('demo.signer');
    expect(out).toContain('2 August 2026 03:05 UTC');
  });

  it('renders the obligation as open and unanswered, and says how open was derived', () => {
    const out = text(renderMemoryLoop(input({})));
    expect(out).toContain('OPEN');
    expect(out).toContain('unanswered on this permit');
    expect(out).toContain('open has no column');
  });
});

describe('renderMemoryLoop — the two instants, side by side', () => {
  it('places the recall start and the materialisation together and subtracts them', () => {
    const result = renderMemoryLoop(input({}));
    const band = result.element?.querySelector('.hz-interval');
    expect(band).not.toBeNull();
    const out = band?.textContent ?? '';
    expect(out).toContain('2026-08-02T03:00:00Z');
    expect(out).toContain('2026-08-02T03:00:10Z');
    expect(out).toContain('10 s');
    expect(out).toContain('subtracted in this browser');
  });

  it('computes the gap rather than printing a constant', () => {
    const later: StatusRow = { ...STATUS, materialised_at: '2026-08-02T03:01:00Z' };
    const out = text(renderMemoryLoop(input({ status: later })));
    expect(out).toContain('60 s');
    expect(out).not.toContain('10 s');
  });

  it('draws no interval at all when either instant is missing', () => {
    const undated: StatusRow = { ...STATUS, materialised_at: null };
    const result = renderMemoryLoop(input({ status: undated }));
    expect(result.element?.querySelector('.hz-interval')).toBeNull();
  });
});

describe('renderMemoryLoop — an absent row renders NOTHING, not a placeholder', () => {
  it('omits RECALLED entirely when no recall run came back', () => {
    const result = renderMemoryLoop(
      input({ recall: null, recallAbsence: 'GET /v1/recall-runs/x answered 404 — no row' }),
    );
    const out = text(result);
    expect(result.rendered).toEqual(['shown-to', 'status']);
    expect(out).not.toContain('RECALLED');
    expect(out).not.toContain('demo-recall-1.0');
    expect(out).not.toContain('candidates');
    expect(out).not.toContain('index generation');
    // No stand-in either: the line is gone, not blanked. A dash where a count belongs is
    // a character a judge can read as data.
    expect(result.element?.querySelector('[data-row="recalled"]')).toBeNull();
    expect(result.absent).toEqual([
      { row: 'recalled', reason: 'GET /v1/recall-runs/x answered 404 — no row' },
    ]);
  });

  it('omits SHOWN TO entirely when no receipt came back', () => {
    const result = renderMemoryLoop(
      input({ receipt: null, receiptAbsence: 'GET /v1/receipts/x answered 404 — no row' }),
    );
    const out = text(result);
    expect(result.rendered).toEqual(['recalled', 'status']);
    expect(out).not.toContain('SHOWN TO');
    expect(out).not.toContain('demo.signer');
    expect(out).not.toContain('993c00c3');
    expect(result.element?.querySelector('[data-row="shown-to"]')).toBeNull();
    expect(result.absent).toEqual([
      { row: 'shown-to', reason: 'GET /v1/receipts/x answered 404 — no row' },
    ]);
  });

  it('names the absence in the deployment’s own words, and invents one only if it must', () => {
    const result = renderMemoryLoop(input({ recall: null }));
    expect(result.absent[0]?.reason).toBe(
      'no mainline_meas.recall_run row was returned for this permit',
    );
  });

  it('renders no element at all when not one of the three rows came back', () => {
    const result = renderMemoryLoop(input({ recall: null, receipt: null, status: null }));
    expect(result.element).toBeNull();
    expect(result.rendered).toEqual([]);
    expect(result.absent.map((item) => item.row)).toEqual(['recalled', 'shown-to', 'status']);
  });

  it('treats a check whose open flag is missing as a missing STATUS, not as closed', () => {
    const unknown: StatusRow = { ...STATUS, open: null };
    const result = renderMemoryLoop(input({ status: unknown }));
    expect(result.rendered).not.toContain('status');
    expect(text(result)).not.toContain('ANSWERED');
  });
});

describe('renderMemoryLoop — provenance is claimed, never widened', () => {
  it('prints each chip beside the pointer the payload claimed it at', () => {
    const result = renderMemoryLoop(input({}));
    const out = text(result);
    expect(out).toContain('/counts/n_blocking');
    expect(out).toContain('/checks/0/open');
    const kinds = Array.from(result.element?.querySelectorAll('[data-chip]') ?? []).map(
      (node) => node.textContent,
    );
    expect(kinds).toContain('db:column');
    expect(kinds).toContain('derived');
  });

  it('renders no chip when the payload claimed none for that pointer', () => {
    const bare: MemoryLoopInput = {
      ...input({}),
      recall: { ...input({}).recall, chip: NO_CHIPS },
      receipt: { ...input({}).receipt, chip: NO_CHIPS },
      status: { ...input({}).status, chip: NO_CHIPS },
    };
    const result = renderMemoryLoop(bare);
    expect(result.element?.querySelector('[data-chip]')).toBeNull();
    // and the values themselves are still there, bare — an unclaimed provenance is not a
    // reason to hide a column, only a reason not to decorate it.
    expect(text(result)).toContain('demo.signer');
  });
});

describe('renderMemoryLoop — copy discipline (R17)', () => {
  const BANNED = [
    'similarity',
    'similar',
    'vector',
    'embedding',
    'nearest neighbour',
    'nearest neighbor',
    'cosine',
    'semantic',
    'watch it remember',
    'just retrieved',
    'is retrieving',
    'searching',
    'searches the corpus',
    'searched the corpus',
    'is recalling',
    'remembers',
  ];

  it('uses no similarity, vector or live-retrieval language anywhere in the loop', () => {
    const out = text(renderMemoryLoop(input({}))).toLowerCase();
    for (const word of BANNED) {
      expect(out).not.toContain(word);
    }
  });

  it('offers no affordance a similarity view could hang off', () => {
    const result = renderMemoryLoop(input({}));
    expect(result.element?.querySelector('canvas')).toBeNull();
    expect(result.element?.querySelector('svg')).toBeNull();
    expect(result.element?.querySelector('input[type="range"]')).toBeNull();
  });
});
