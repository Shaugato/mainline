// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SIGNATURE BLOCK — elements 9 to 13, and the rows a fake screen hides.
 *
 * Two rulings are under test.
 *
 * **R14.** `exposure_receipt.actor_sub` means *who the obligation was shown to*, which is
 * Figure 1 element 10 — acceptance. So the signer is labelled the ACCEPTOR and is given no
 * issuing role. r3-operator §10 flagged its own earlier "Issuing authority" mapping as
 * genuinely ambiguous; between two readings of one column we take the one the column's name
 * supports, and this test is what keeps that decision from drifting back.
 *
 * **Plan §5 item 5 / r3-operator §6.5.** Hand-back and cancellation render EMPTY AND
 * UNSIGNED. *"An unsigned hand-back box is what a live permit looks like."* The temptation is
 * to hide the rows that have no data, which makes the permit look issued when it is not.
 */

import { describe, expect, it } from 'vitest';

import type { ExposureReceipt, Permit } from '../../../../src/data/types.generated';
import {
  ROLE_ACCEPTOR,
  ROLE_ISSUING_AUTHORITY,
  ROLE_PERFORMING_AUTHORITY,
  renderSignatureBlock,
} from '../../../../src/operator/permit/signatures';
import type { ChipLookup } from '../../../../src/operator/permit/typed-fields';

const PERMIT: Permit = {
  permit_id: 'permit-uuid-under-test',
  site_id: 'site-uuid-under-test',
  site_code: 'site-code-under-test',
  external_ref: 'REF-UNDER-TEST',
  ref_name: 'refs/permits/under-test',
  state: 'dispositioned',
  head_seq: 2,
  gate_epoch: 1,
  merged_commit: null,
  under_hold: false,
  opened_at: 'opened-instant-under-test',
  horizon_at: 'horizon-instant-under-test',
  counters: {
    open_blocking: 1,
    open_residue: 0,
    open_conflicts: 0,
    open_warrants: 0,
    unmodelled_asset_count: 0,
    unmet_floor_count: 0,
    countersigned_count: 0,
  },
  constraints: [],
  boundary_certificate: null,
  merge_record: null,
};

const RECEIPT: ExposureReceipt = {
  receipt_id: 'receipt-uuid-under-test',
  permit_id: 'permit-uuid-under-test',
  actor_sub: 'signer-under-test',
  issued_at: 'issued-instant-under-test',
  expires_at: 'expiry-instant-under-test',
  corpus_root: 'corpus-root-under-test',
  silence_receipt_id: 'silence-uuid-under-test',
  policy_version: 'policy-under-test',
  total_tokens: 200,
  receipt_digest: 'receipt-digest-under-test',
  swept_at: null,
  lines: [
    {
      receipt_id: 'receipt-uuid-under-test',
      check_id: 'check-uuid-under-test',
      payload_digest: 'payload-digest-under-test',
      tokens: 200,
    },
  ],
};

const permitLookup: ChipLookup = () => 'db:column';
const receiptLookup: ChipLookup = () => 'db:column';
const noChips: ChipLookup = () => null;

const block = (over: { readonly receipt?: ExposureReceipt | null } = {}): HTMLElement =>
  renderSignatureBlock({
    permit: PERMIT,
    permitLookup,
    receipt: over.receipt === undefined ? RECEIPT : over.receipt,
    receiptLookup,
  });

const row = (host: HTMLElement, element: number): HTMLElement | null =>
  host.querySelector<HTMLElement>(`.cow-sig-row[data-figure1-element="${element}"]`);

describe('every row is dated and timed — HSG250 ¶49', () => {
  it('gives every signature row a signatory cell and a date-and-time cell', () => {
    const host = block();
    for (const element of [9, 10, 12, 13]) {
      const node = row(host, element);
      expect(node, `element ${element}`).not.toBeNull();
      expect(node?.querySelectorAll('.cow-sig-cell').length).toBeGreaterThanOrEqual(2);
    }
  });

  it('heads the block with Signatory and Date and time columns', () => {
    const headings = [...block().querySelectorAll('.cow-sig-h')].map((n) => n.textContent);
    expect(headings).toContain('Signatory');
    expect(headings).toContain('Date and time');
  });
});

describe('element 10 — the signer is the ACCEPTOR, and holds no issuing role (R14)', () => {
  it('labels the acceptance row with HSG250 Table 1’s acceptor', () => {
    const acceptance = row(block(), 10);
    expect(acceptance?.querySelector('.cow-sig-role')?.textContent).toBe(ROLE_ACCEPTOR);
  });

  it('shows actor_sub on the acceptance row and nowhere else', () => {
    const host = block();
    const occurrences = [...host.querySelectorAll('.cow-sig-name')].map((n) => n.textContent);
    expect(occurrences).toEqual([RECEIPT.actor_sub]);
    expect(row(host, 10)?.textContent).toContain(RECEIPT.actor_sub);
  });

  it('never puts the signer on the issue row', () => {
    const issue = row(block(), 9);
    expect(issue?.textContent).not.toContain(RECEIPT.actor_sub);
    expect(issue?.querySelector('.cow-sig-role')?.textContent).toBe(ROLE_ISSUING_AUTHORITY);
    expect(issue?.getAttribute('data-signed')).toBe('false');
  });

  it('carries the receipt as the acceptance evidence, chipped', () => {
    const acceptance = row(block(), 10);
    expect(acceptance?.getAttribute('data-signed')).toBe('true');
    expect(acceptance?.textContent).toContain(RECEIPT.receipt_digest);
    const pointers = [...(acceptance?.querySelectorAll('.cow-chip') ?? [])].map((n) =>
      n.getAttribute('data-pointer'),
    );
    expect(pointers).toContain('/actor_sub');
    expect(pointers).toContain('/issued_at');
    expect(pointers).toContain('/receipt_digest');
  });

  it('states the absence rather than inventing an acceptance when no receipt read', () => {
    const host = renderSignatureBlock({
      permit: PERMIT,
      permitLookup,
      receipt: null,
      receiptLookup: noChips,
      receiptAbsence: 'GET /v1/receipts/… → 404',
    });
    const acceptance = row(host, 10);
    expect(acceptance?.getAttribute('data-signed')).toBe('false');
    expect(acceptance?.textContent).toContain('GET /v1/receipts/… → 404');
    expect(acceptance?.querySelector('.cow-sig-name')).toBeNull();
  });
});

describe('elements 12 and 13 render UNSIGNED, which is what a live permit looks like', () => {
  it('renders hand-back with empty cells and says they are unsigned', () => {
    const handback = row(block(), 12);
    expect(handback).not.toBeNull();
    expect(handback?.getAttribute('data-signed')).toBe('false');
    expect(handback?.textContent).toContain('Hand-back');
    expect(handback?.querySelectorAll('[data-unsigned="true"]').length).toBe(2);
    expect(handback?.querySelector('.cow-sig-name')).toBeNull();
    expect(handback?.querySelector('time')).toBeNull();
  });

  it('renders cancellation the same way, and does not hide it', () => {
    const cancellation = row(block(), 13);
    expect(cancellation).not.toBeNull();
    expect(cancellation?.getAttribute('data-signed')).toBe('false');
    expect(cancellation?.textContent).toContain('Cancellation');
    expect(cancellation?.querySelector('.cow-sig-name')).toBeNull();
  });

  it('names HSG250 Table 1 roles, never "approver"', () => {
    const host = block();
    const roles = [...host.querySelectorAll('.cow-sig-role')].map((n) => n.textContent ?? '');
    expect(roles.join(' ')).toContain(ROLE_PERFORMING_AUTHORITY);
    expect(roles.join(' ').toLowerCase()).not.toContain('approver');
    expect((host.textContent ?? '').toLowerCase()).not.toContain('approver');
  });

  it('fabricates no signatory anywhere in the block', () => {
    const names = [...block().querySelectorAll('.cow-sig-name')].map((n) => n.textContent);
    expect(names).toEqual([RECEIPT.actor_sub]);
  });
});

describe('element 11 is omitted and says so', () => {
  it('names the omission rather than skipping the number', () => {
    const omitted = block().querySelector('[data-omitted="true"]');
    expect(omitted).not.toBeNull();
    expect(omitted?.getAttribute('data-figure1-element')).toBe('11');
    expect(omitted?.textContent).toContain('omitted');
  });

  it('is not a signature row — an omitted element cannot be signed', () => {
    expect(row(block(), 11)).toBeNull();
  });
});

describe('element 9 proves it is unsigned from a column, not from an inference', () => {
  it('shows merged_commit null, chipped, beside the real duration', () => {
    const issue = row(block(), 9);
    const pointers = [...(issue?.querySelectorAll('.cow-chip') ?? [])].map((n) =>
      n.getAttribute('data-pointer'),
    );
    expect(pointers).toContain('/merged_commit');
    expect(pointers).toContain('/opened_at');
    expect(pointers).toContain('/horizon_at');
    expect(issue?.querySelector('.cow-null')?.textContent).toBe('null');
  });
});
