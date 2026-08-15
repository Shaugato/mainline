// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE DISPOSITION LATTICE, RENDERED AS THE AUTHORISATION MATRIX — OSHA 1910.119(l)(2)(v).
 *
 * An industry judge recognises an authorisation matrix on sight. IChemE ¶3.4: *"the higher
 * the risk, the higher the level of experience, expertise, authority and number of
 * approvers required."* That sentence describes a table, and this deployment already has
 * one — `mainline.clearance_legal`, served as `data.lattice` by
 * `GET /v1/checks/{check_id}/disposition`. It is not a diagram of a policy. It is the
 * policy, and a `(virulence, kind)` pair missing from it is not a disallowed option but a
 * NON-EXISTENT one (`reads.py:819-833`): attempting it produces `23503` on `fk_clearance`.
 *
 * ── WHAT THIS MODULE IS CAREFUL ABOUT ────────────────────────────────────────────────
 *
 * The lattice is keyed by **virulence**, not by subject: `read_disposition` selects
 * *"EVERY `clearance_legal` row for the check's virulence"*. So this table is a property
 * of a severity class, not of the change request — and the screen says so, names the
 * virulence it is scoped by, names the `policy_version` the rows carry, and names the
 * exact request the rows arrived on.
 *
 * That last part matters here more than anywhere else on this screen. Under R11 the change
 * request's OWN obligation is not addressable from any declared route, so the check this
 * table was read against is the one that IS addressable. Presenting these rows while
 * implying they were read from the change request's obligation would be a fabricated
 * relation. Instead `renderLattice` requires a `scopeNote` and a `readFrom` and prints
 * both: the reader is told which check answered, and that the answer is scoped by
 * virulence rather than by subject. Nothing is claimed about the change request's own
 * obligation, because nothing about it can be read.
 *
 * Every cell is a live value. `max_ttl_hours` is emphasised because it is the only bounded
 * duration this deployment carries and it answers the ISC's own named MOC failure mode —
 * *"overuse of temporary changes for extensions beyond intended durations"*. No number in
 * this file is typed; the only literals are column headings.
 */

import { el, txt } from './ribbon';

/**
 * One `mainline.clearance_legal` row as `GET /v1/checks/{check_id}/disposition` returns it.
 *
 * Every field is optional-free and nullable exactly as the payload is: `max_ttl_hours` is
 * `null` for four of the five kinds, and `null` must render as an absence, not as `0`.
 */
export interface LatticeRow {
  readonly kind: string;
  readonly virulence: string;
  readonly min_signer_rank: number | null;
  readonly req_second_signer: boolean;
  readonly req_foreign_org: boolean;
  readonly req_compensating: boolean;
  readonly req_predicate: boolean;
  readonly req_reassert: boolean;
  readonly max_ttl_hours: number | null;
  readonly policy_version: string | null;
}

interface Column {
  readonly heading: string;
  readonly cell: (row: LatticeRow) => HTMLElement;
}

/** A required flag: `✓` when the policy demands it, an em dash when it does not. */
function flag(on: boolean): HTMLElement {
  const cell = el('td', 'moc-num', on ? '✓' : '—');
  cell.setAttribute('aria-label', on ? 'required' : 'not required');
  return cell;
}

function num(value: number | null): HTMLElement {
  return el('td', 'moc-num', value === null ? '—' : String(value));
}

const COLUMNS: readonly Column[] = [
  { heading: 'disposition kind', cell: (r) => el('td', 'moc-kind', r.kind) },
  { heading: 'min signer rank', cell: (r) => num(r.min_signer_rank) },
  { heading: 'second signer', cell: (r) => flag(r.req_second_signer) },
  { heading: 'foreign org', cell: (r) => flag(r.req_foreign_org) },
  { heading: 'compensating', cell: (r) => flag(r.req_compensating) },
  { heading: 'predicate', cell: (r) => flag(r.req_predicate) },
  { heading: 'reassert', cell: (r) => flag(r.req_reassert) },
  {
    heading: 'max TTL',
    cell: (r) =>
      r.max_ttl_hours === null
        ? el('td', 'moc-num', '—')
        : el('td', 'moc-ttl', `${String(r.max_ttl_hours)} h`),
  },
];

export interface LatticeInput {
  /** The rows exactly as `data.lattice` returned them. Never sorted into a story order. */
  readonly rows: readonly LatticeRow[];
  /** `data.virulence` — the severity class these rows are scoped by. */
  readonly virulence: string | null;
  /** The verbatim request line this read arrived on, e.g. `GET /v1/checks/…/disposition 200`. */
  readonly readFrom: string;
  /**
   * One sentence naming WHOSE check answered and what that does and does not imply.
   * Required, not optional: a lattice with no scope note is a lattice presented as
   * belonging to whatever is nearest on screen.
   */
  readonly scopeNote: string;
}

/** `true` when at least one row bounds a disposition by wall-clock time. */
function boundedRows(rows: readonly LatticeRow[]): readonly LatticeRow[] {
  return rows.filter((row) => row.max_ttl_hours !== null);
}

/**
 * The authorisation matrix, in the order the payload delivered it.
 *
 * Rows are NOT reordered. The payload arrives ordered by `kind` and that ordering is the
 * database's, so a reader comparing this table with a raw payload sees the same sequence.
 */
export function renderLattice(input: LatticeInput): HTMLElement {
  const wrap = el('div');

  if (input.rows.length === 0) {
    wrap.append(
      el(
        'p',
        'moc-absent',
        'No lattice rows were returned by this read, so no authorisation matrix is shown. ' +
          'This screen does not carry a fallback table: a matrix printed from anywhere but ' +
          'the kernel would be a policy this deployment does not enforce.',
      ),
    );
    wrap.append(txt(input.readFrom, 'moc-exchange'));
    return wrap;
  }

  const scroll = el('div', 'moc-scroll');
  const table = el('table', 'moc-table');

  const caption = el('caption');
  caption.append(
    document.createTextNode('Dispositions legal at virulence '),
    input.virulence === null
      ? el('span', 'moc-absent-inline', 'not read')
      : el('code', 'moc-db', input.virulence),
    document.createTextNode(
      `. ${String(input.rows.length)} row${input.rows.length === 1 ? '' : 's'}; a ` +
        '(virulence, kind) pair absent from this table is not a disallowed option but one ' +
        'the schema does not carry.',
    ),
  );
  table.append(caption);

  const thead = el('thead');
  const headRow = el('tr');
  for (const column of COLUMNS) headRow.append(el('th', undefined, column.heading));
  thead.append(headRow);
  table.append(thead);

  const tbody = el('tbody');
  for (const row of input.rows) {
    const tr = el('tr');
    for (const column of COLUMNS) tr.append(column.cell(row));
    tbody.append(tr);
  }
  table.append(tbody);

  scroll.append(table);
  wrap.append(scroll);

  const policies = [...new Set(input.rows.map((row) => row.policy_version).filter((v) => v !== null))];
  if (policies.length > 0) {
    wrap.append(txt(`Policy version ${policies.join(', ')}, as carried on every row above.`));
  }

  // The TTL sentence is composed from the rows that actually carry one, and the word
  // "only" is used ONLY when the payload makes it true. A sentence that says "the only
  // time-bounded route" while two rows carry a TTL is a small lie of exactly the kind
  // this screen exists to make impossible.
  const bounded = boundedRows(input.rows);
  if (bounded.length > 0) {
    const lead =
      bounded.length === 1
        ? `${bounded[0]?.kind ?? ''} is the only route on this table bounded by wall-clock time`
        : `${String(bounded.length)} routes on this table are bounded by wall-clock time`;
    const each = bounded
      .map((row) => `${row.kind} expires after ${String(row.max_ttl_hours)} hours`)
      .join('; ');
    wrap.append(
      txt(
        `${lead}: ${each}, after which it must be taken again. The IChemE Safety Centre names ` +
          '“overuse of temporary changes for extensions beyond intended durations” among its ' +
          'top management-of-change failure modes; that ceiling is the schema’s answer to it, ' +
          'and the database enforces it rather than this page.',
      ),
    );
  }

  wrap.append(txt(input.scopeNote));
  wrap.append(txt(input.readFrom, 'moc-exchange'));
  return wrap;
}
