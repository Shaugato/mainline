// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE AUTHORISATION MATRIX — five real rows, and the sentences that keep them honest.
 *
 * The rows below are VERBATIM `data.lattice` from
 * `GET /v1/checks/<check_id>/disposition`, captured 2026-08-15 from
 * `scripts/deploy/local_furl.py` running the real handler against the local CockroachDB
 * `mainline_demo`. Order, values and nulls are the payload's; nothing was sorted into a
 * more pleasing shape and nothing was rounded.
 *
 * Two failure modes are worth more than the rest, and both get their own test:
 *
 *   • **A matrix with no scope note.** The lattice is keyed by VIRULENCE, not by subject
 *     (`reads.py:819-833`: *"EVERY clearance_legal row for the check's virulence"*).
 *     Printed beside a change request with no note, it reads as that change request's
 *     matrix. `renderLattice` therefore requires a `scopeNote` and prints it.
 *   • **A fallback table.** If the read returns nothing, a module that drew the matrix
 *     from a constant would show a policy this deployment does not enforce. There is no
 *     such constant, and the empty case renders an absence.
 */

import { describe, expect, it } from 'vitest';

import { renderLattice, type LatticeRow } from '../../../../src/operator/change/lattice';

/** VERBATIM `data.lattice`, in payload order (`kind` ascending, as the database returned). */
const REAL_LATTICE: readonly LatticeRow[] = [
  {
    kind: 'applied',
    virulence: 'blood_major',
    min_signer_rank: 3,
    req_second_signer: false,
    req_foreign_org: false,
    req_compensating: false,
    req_predicate: false,
    req_reassert: false,
    max_ttl_hours: null,
    policy_version: 'cl-1.0',
  },
  {
    kind: 'emergency_override',
    virulence: 'blood_major',
    min_signer_rank: 5,
    req_second_signer: true,
    req_foreign_org: true,
    req_compensating: false,
    req_predicate: false,
    req_reassert: false,
    max_ttl_hours: 12,
    policy_version: 'cl-1.0',
  },
  {
    kind: 'escalated',
    virulence: 'blood_major',
    min_signer_rank: 3,
    req_second_signer: true,
    req_foreign_org: false,
    req_compensating: false,
    req_predicate: false,
    req_reassert: false,
    max_ttl_hours: null,
    policy_version: 'cl-1.0',
  },
  {
    kind: 'mechanism_absent',
    virulence: 'blood_major',
    min_signer_rank: 4,
    req_second_signer: true,
    req_foreign_org: true,
    req_compensating: false,
    req_predicate: true,
    req_reassert: true,
    max_ttl_hours: null,
    policy_version: 'cl-1.0',
  },
  {
    kind: 'mitigated',
    virulence: 'blood_major',
    min_signer_rank: 3,
    req_second_signer: true,
    req_foreign_org: false,
    req_compensating: true,
    req_predicate: false,
    req_reassert: false,
    max_ttl_hours: null,
    policy_version: 'cl-1.0',
  },
];

const SCOPE_NOTE =
  'The lattice is keyed by VIRULENCE, not by subject, and the read above was made against ' +
  'the check that is addressable.';

/** One captured row, or a loud failure. `noUncheckedIndexedAccess` is on for a reason. */
function row(index: number): LatticeRow {
  const found = REAL_LATTICE[index];
  if (found === undefined) throw new RangeError(`no captured lattice row at ${String(index)}`);
  return found;
}

function render(rows: readonly LatticeRow[] = REAL_LATTICE): HTMLElement {
  return renderLattice({
    rows,
    virulence: rows[0]?.virulence ?? null,
    readFrom: 'GET /v1/checks/x/disposition → 200 · 3805 bytes on the wire',
    scopeNote: SCOPE_NOTE,
  });
}

describe('renderLattice — the matrix an industry judge recognises on sight', () => {
  it('renders one row per lattice row, in payload order, never re-sorted', () => {
    const bodyRows = [...render().querySelectorAll('tbody tr')];
    expect(bodyRows).toHaveLength(5);
    expect(bodyRows.map((tr) => tr.querySelector('td')?.textContent)).toEqual([
      'applied',
      'emergency_override',
      'escalated',
      'mechanism_absent',
      'mitigated',
    ]);
  });

  it('renders the eight authorisation columns', () => {
    const headings = [...render().querySelectorAll('thead th')].map((th) => th.textContent);
    expect(headings).toEqual([
      'disposition kind',
      'min signer rank',
      'second signer',
      'foreign org',
      'compensating',
      'predicate',
      'reassert',
      'max TTL',
    ]);
  });

  it('renders each row’s cells from the row, with ✓ / — for the required flags', () => {
    const cells = [...(render().querySelectorAll('tbody tr')[3]?.querySelectorAll('td') ?? [])].map(
      (td) => td.textContent,
    );
    // mechanism_absent: rank 4, second signer, foreign org, no compensating, predicate,
    // reassert, no TTL.
    expect(cells).toEqual(['mechanism_absent', '4', '✓', '✓', '—', '✓', '✓', '—']);
  });

  it('renders the 12-hour ceiling on emergency_override and marks it', () => {
    const ttl = render().querySelector('td.moc-ttl');
    expect(ttl?.textContent).toBe('12 h');
    const text = render().textContent ?? '';
    expect(text).toContain('emergency_override expires after 12 hours');
    expect(text).toContain('overuse of temporary changes for extensions beyond intended');
  });

  it('renders a null max_ttl_hours as an em dash, never as 0', () => {
    const applied = render().querySelectorAll('tbody tr')[0];
    const cells = [...(applied?.querySelectorAll('td') ?? [])].map((td) => td.textContent);
    expect(cells[7]).toBe('—');
    expect(cells).not.toContain('0');
  });

  it('names the virulence the rows are scoped by, and the policy version they carry', () => {
    const text = render().textContent ?? '';
    expect(text).toContain('blood_major');
    expect(text).toContain('Policy version cl-1.0');
  });

  it('prints the scope note, so the matrix is never read as this record’s own', () => {
    expect(render().textContent).toContain(SCOPE_NOTE);
  });

  it('says an absent (virulence, kind) pair is non-existent, not merely disallowed', () => {
    expect(render().textContent).toContain('not a disallowed option but one the schema does not');
  });

  it('prints the exchange line, so the table is traceable to a request', () => {
    expect(render().querySelector('.moc-exchange')?.textContent).toContain(
      'GET /v1/checks/x/disposition → 200',
    );
  });
});

describe('renderLattice — there is no fallback matrix anywhere', () => {
  it('renders an absence, and no table at all, when the read returned no rows', () => {
    const rendered = render([]);
    expect(rendered.querySelectorAll('table')).toHaveLength(0);
    expect(rendered.textContent).toContain('does not carry a fallback table');
  });

  it('says “only” about a time-bounded route only when exactly one row carries a TTL', () => {
    // SYNTHETIC pair: a hypothetical policy where two routes expire. A module that hard-
    // coded the sentence would keep claiming "the only route", which would be false.
    const twoBounded: readonly LatticeRow[] = [
      { ...row(1) },
      { ...row(2), max_ttl_hours: 4 },
    ];
    const text = renderLattice({
      rows: twoBounded,
      virulence: 'blood_major',
      readFrom: 'synthetic',
      scopeNote: SCOPE_NOTE,
    }).textContent;
    expect(text).toContain('2 routes on this table are bounded by wall-clock time');
    expect(text).not.toContain('is the only route');
  });

  it('renders an absence for the virulence rather than a guess when it was not read', () => {
    const rendered = renderLattice({
      rows: REAL_LATTICE,
      virulence: null,
      readFrom: 'synthetic',
      scopeNote: SCOPE_NOTE,
    });
    expect(rendered.querySelector('caption')?.textContent).toContain('not read');
  });
});
