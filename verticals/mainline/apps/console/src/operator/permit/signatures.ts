// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * HSG250 FIGURE 1 ELEMENTS 9–13 — THE SIGNATURE BLOCK.
 *
 * HSG250 ¶49: *"Signatures on permit-to-work forms should be dated and timed."* So every row
 * below has a signatory cell and a date-and-time cell, and a row that is not signed shows
 * BOTH cells empty rather than being hidden. Plan §5 item 5 and r3-operator §6.5 both single
 * out the unsigned hand-back as a fidelity signal: *"an unsigned hand-back box is what a live
 * permit looks like."* A screen that renders only the rows it has data for looks finished;
 * a permit that looks finished before it is issued is the tell.
 *
 * THE ROLE NAMES ARE HSG250 TABLE 1's, NOT "APPROVER". r3-operator §1.2: *"The single most
 * common fidelity failure in a fake PTW screen is calling everybody approver."*
 *
 * R14 GOVERNS ROW 10, AND IT IS THE ONE JUDGEMENT CALL IN THIS FILE.
 * `exposure_receipt.actor_sub` is `demo.signer`. The column means *who the obligation was
 * shown to*, which is Figure 1 element 10 — acceptance — so `demo.signer` is labelled the
 * ACCEPTOR and is given NO issuing role. r3-operator §10 flagged its own §6.1 mapping
 * ("Issuing authority") as genuinely ambiguous; between two readings of one column we take
 * the one the column's name supports.
 *
 * ROW 9 IS THEREFORE UNSIGNED, AND THE EVIDENCE FOR THAT IS A REAL COLUMN. `merged_commit`
 * is null on this permit and the read claims a pointer for it, so the row can show, chipped,
 * that no issue has been recorded. It does not say "awaiting your signature" — it says which
 * column is null.
 *
 * ELEMENT 11 IS OMITTED, NOT FAKED. R9: the kernel has no extension mechanism. The row is
 * present as a NAMED omission, because a form that silently skips element 11 is a form whose
 * other twelve elements you cannot check.
 */

import type { ExposureReceipt, Permit } from '../../data/types.generated';
import {
  type ChipLookup,
  absenceBlock,
  el,
  formatInstantUtc,
  formSection,
  omittedElement,
  provenanceChip,
  readField,
} from './typed-fields';

/** HSG250 Table 1 titles, used verbatim. */
export const ROLE_ISSUING_AUTHORITY = 'Issuing authority';
export const ROLE_PERFORMING_AUTHORITY = 'Performing authority';
export const ROLE_ACCEPTOR = 'Acceptor';

export interface SignaturesInput {
  readonly permit: Permit;
  /** Chip lookup bound to the PERMIT envelope. */
  readonly permitLookup: ChipLookup;
  /** The exposure receipt, or null when the read did not resolve one. */
  readonly receipt: ExposureReceipt | null;
  /** Chip lookup bound to the RECEIPT envelope. */
  readonly receiptLookup: ChipLookup;
  /** Verbatim status line when `receipt` is null — the exchange's own words. */
  readonly receiptAbsence?: string;
}

/** Render the whole signature block, elements 9 to 13, in Figure 1 order. */
export function renderSignatureBlock(input: SignaturesInput): HTMLElement {
  const section = formSection({
    element: '9–13',
    heading: 'Signature block',
    note: 'HSG250 ¶49 — signatures on permit-to-work forms should be dated and timed.',
  });

  const table = el('div', 'cow-signatures');
  table.setAttribute('role', 'table');
  table.appendChild(headerRow());

  table.appendChild(renderIssueRow(input));
  table.appendChild(renderAcceptanceRow(input));
  table.appendChild(
    omittedElement({
      element: 11,
      label: '11 · Extension / shift handover',
      reason: 'this deployment has no extension mechanism; no column and no route carry one',
    }),
  );
  table.appendChild(
    renderUnsignedRow({
      element: 12,
      title: 'Hand-back',
      roles: `${ROLE_PERFORMING_AUTHORITY} · ${ROLE_ISSUING_AUTHORITY}`,
      certifies: 'work completed, plant ready for testing and recommissioning',
    }),
  );
  table.appendChild(
    renderUnsignedRow({
      element: 13,
      title: 'Cancellation',
      roles: ROLE_ISSUING_AUTHORITY,
      certifies: 'work tested and plant satisfactorily recommissioned',
    }),
  );

  section.body.appendChild(table);
  return section.root;
}

/**
 * Element 9 — ISSUE.
 *
 * The duration is real (`opened_at` → `horizon_at`). The signature is not: this permit has
 * not been issued, and the row proves it with `merged_commit`, chipped, rather than asserting
 * it. The ISSUE action itself is the action bar, which is W5's; this row does not simulate it.
 */
export function renderIssueRow(input: SignaturesInput): HTMLElement {
  const { permit, permitLookup } = input;
  const row = signatureRow(9, 'Issue', ROLE_ISSUING_AUTHORITY);
  row.setAttribute('data-signed', 'false');

  row.appendChild(unsignedCell('signatory'));
  row.appendChild(unsignedCell('date and time'));

  const detail = el('div', 'cow-sig-detail');
  detail.appendChild(
    readField({
      label: 'Duration from',
      value: permit.opened_at,
      pointer: '/opened_at',
      lookup: permitLookup,
      kind: 'instant',
    }),
  );
  detail.appendChild(
    readField({
      label: 'Duration to',
      value: permit.horizon_at,
      pointer: '/horizon_at',
      lookup: permitLookup,
      kind: 'instant',
    }),
  );
  detail.appendChild(
    readField({
      label: 'Merged commit',
      value: permit.merged_commit ?? null,
      pointer: '/merged_commit',
      lookup: permitLookup,
      kind: 'mono',
      title: 'null while the permit has not been issued — the column, not an inference',
    }),
  );
  row.appendChild(detail);
  return row;
}

/**
 * Element 10 — ACCEPTANCE, from the exposure receipt.
 *
 * HSG250 element 10 is *"signature confirming understanding of work to be done… Also
 * confirming permit information has been explained to all permit users."* A paper form has a
 * tick-box for that. This one has a Merkle digest over the exact payloads that were rendered
 * to that person, which is the same claim made checkable.
 */
export function renderAcceptanceRow(input: SignaturesInput): HTMLElement {
  const { receipt, receiptLookup } = input;
  const row = signatureRow(10, 'Acceptance', ROLE_ACCEPTOR);

  if (receipt === null) {
    row.setAttribute('data-signed', 'false');
    row.appendChild(unsignedCell('signatory'));
    row.appendChild(unsignedCell('date and time'));
    const detail = el('div', 'cow-sig-detail');
    detail.appendChild(
      absenceBlock(
        'no exposure receipt on this screen',
        input.receiptAbsence ?? 'the receipt read did not resolve',
      ),
    );
    row.appendChild(detail);
    return row;
  }

  row.setAttribute('data-signed', 'true');

  const who = el('div', 'cow-sig-cell cow-sig-signed');
  who.appendChild(el('span', 'cow-sig-name cow-mono', receipt.actor_sub));
  const whoChip = provenanceChip(receiptLookup, '/actor_sub');
  if (whoChip !== null) {
    who.appendChild(whoChip);
  }
  row.appendChild(who);

  const when = el('div', 'cow-sig-cell cow-sig-signed');
  const time = el('time', 'cow-mono', formatInstantUtc(receipt.issued_at));
  time.setAttribute('datetime', receipt.issued_at);
  time.title = receipt.issued_at;
  when.appendChild(time);
  const whenChip = provenanceChip(receiptLookup, '/issued_at');
  if (whenChip !== null) {
    when.appendChild(whenChip);
  }
  row.appendChild(when);

  const detail = el('div', 'cow-sig-detail');
  detail.appendChild(
    readField({
      label: 'Receipt digest',
      value: receipt.receipt_digest,
      pointer: '/receipt_digest',
      lookup: receiptLookup,
      kind: 'mono',
      title: 'the Merkle digest of the exact payloads rendered to that person',
    }),
  );
  detail.appendChild(
    readField({
      label: 'Obligations shown',
      value: receipt.lines.length,
      pointer: '/lines/0',
      lookup: receiptLookup,
      title: 'one exposure_line per obligation the receipt covers',
    }),
  );
  detail.appendChild(
    readField({
      label: 'Tokens',
      value: receipt.total_tokens,
      pointer: '/total_tokens',
      lookup: receiptLookup,
      kind: 'mono',
    }),
  );
  detail.appendChild(
    readField({
      label: 'Receipt expires',
      value: receipt.expires_at,
      pointer: '/expires_at',
      lookup: receiptLookup,
      kind: 'instant',
    }),
  );
  detail.appendChild(
    readField({
      label: 'Policy version',
      value: receipt.policy_version,
      pointer: '/policy_version',
      lookup: receiptLookup,
      kind: 'mono',
    }),
  );
  detail.appendChild(
    readField({
      label: 'Corpus root',
      value: receipt.corpus_root,
      pointer: '/corpus_root',
      lookup: receiptLookup,
      kind: 'mono',
      title: 'the ledger checkpoint root at the read timestamp — what the system knew at signing time',
    }),
  );
  row.appendChild(detail);
  return row;
}

export interface UnsignedRowSpec {
  readonly element: number;
  readonly title: string;
  readonly roles: string;
  /** HSG250's own account of what the signature certifies. */
  readonly certifies: string;
}

/**
 * An element 12 or 13 row: present, correct and UNSIGNED.
 *
 * This is not a placeholder and it is not a disabled control awaiting a click. It is the
 * shape of the form, empty, because the work it certifies has not happened.
 */
export function renderUnsignedRow(spec: UnsignedRowSpec): HTMLElement {
  const row = signatureRow(spec.element, spec.title, spec.roles);
  row.setAttribute('data-signed', 'false');
  row.appendChild(unsignedCell('signatory'));
  row.appendChild(unsignedCell('date and time'));
  const detail = el('div', 'cow-sig-detail');
  detail.appendChild(el('span', 'cow-hint', `certifies: ${spec.certifies}`));
  row.appendChild(detail);
  return row;
}

/** The column headings, once. */
function headerRow(): HTMLElement {
  const row = el('div', 'cow-sig-head');
  row.setAttribute('role', 'row');
  row.appendChild(el('span', 'cow-sig-h', 'Element'));
  row.appendChild(el('span', 'cow-sig-h', 'Signatory'));
  row.appendChild(el('span', 'cow-sig-h', 'Date and time'));
  row.appendChild(el('span', 'cow-sig-h', 'Record'));
  return row;
}

/** The left-hand cell every row shares: number, HSG250 title, HSG250 Table 1 role. */
function signatureRow(element: number, title: string, roles: string): HTMLElement {
  const row = el('div', 'cow-sig-row');
  row.setAttribute('role', 'row');
  row.setAttribute('data-figure1-element', String(element));

  const what = el('div', 'cow-sig-what');
  what.appendChild(el('span', 'cow-element-no', String(element)));
  what.appendChild(el('span', 'cow-sig-title', title));
  what.appendChild(el('span', 'cow-sig-role', roles));
  row.appendChild(what);
  return row;
}

/** An empty, ruled cell. It carries no chip because it carries no value. */
function unsignedCell(what: string): HTMLElement {
  const cell = el('div', 'cow-sig-cell cow-sig-unsigned');
  cell.setAttribute('data-unsigned', 'true');
  cell.appendChild(el('span', 'cow-sig-rule'));
  cell.appendChild(el('span', 'cow-hint', `unsigned — ${what}`));
  return cell;
}
