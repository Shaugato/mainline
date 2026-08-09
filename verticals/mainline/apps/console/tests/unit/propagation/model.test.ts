// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The fleet model — ordering, SLA standing, declination law, resolution inheritance.
 *
 * Each assertion is written so that the COMFORTABLE failure is red: an ordering that
 * quietly sorts declinations to the bottom, an SLA clock that reads the wall clock, a
 * comparator that ranks by the name of whoever resolved a conflict, an inheritance panel
 * that implies a recall flag it does not have.
 */

import { describe, expect, it } from 'vitest';

import {
  buildFleetView,
  compareConflicts,
  compareFleetRows,
  DECLINATION_LAW,
  inheritanceOf,
  interval,
  ONLY_TIGHTENINGS_TRAVEL,
  PROP_STATES,
  slaStanding,
  wholeDays,
  type FleetRow,
} from '../../../src/features/propagation/model';
import type { MergeConflict, PropState } from '../../../src/data/types.generated';

import { sourcePropagation } from './_fixture';

const PAYLOAD = sourcePropagation();
const DATA = PAYLOAD.data;
const REFERENCE = PAYLOAD.observed_at ?? '';

describe('the fixture this suite reads is the one it thinks it reads', () => {
  it('carries an adopted row, a declined row and an open conflict', () => {
    // A guard, not a formality. If the payload lost its declination the equal-prominence
    // assertions below would compare one row with itself and pass.
    const states = DATA.propagations.map((row) => row.state);
    expect(states).toContain('adopted');
    expect(states).toContain('declined');
    expect(DATA.conflicts.length).toBeGreaterThan(0);
    expect(REFERENCE).not.toBe('');
  });

  it('carries a declination with a kind the law knows', () => {
    const declined = DATA.propagations.find((row) => (row.declination_kind ?? null) !== null);
    expect(declined).toBeDefined();
    const kind = declined?.declination_kind;
    expect(kind === undefined ? '' : kind).toMatch(/^(mitigated|waiver|mechanism_absent)$/);
  });
});

describe('the law is stated, not applied', () => {
  it('names the constraint, the three admitted values, and the two excluded ones', () => {
    expect(ONLY_TIGHTENINGS_TRAVEL.constraint).toBe('only_tightenings_travel');
    expect([...ONLY_TIGHTENINGS_TRAVEL.admits]).toEqual(['introduce', 'strengthen', 'restate']);
    expect([...ONLY_TIGHTENINGS_TRAVEL.excludes]).toEqual(['weaken', 'remove']);
  });

  it('admits exactly the control_delta values the payload can carry', () => {
    // The generated type for `lesson.control_delta` is the three-value union. If the
    // contract ever widened it, this pair would disagree and the law panel would be
    // describing a constraint the payload no longer honours.
    expect(ONLY_TIGHTENINGS_TRAVEL.admits).toContain(DATA.lesson.control_delta);
  });

  it('gives every declination kind a constraint and the column it requires', () => {
    expect(Object.keys(DECLINATION_LAW).sort()).toEqual([
      'mechanism_absent',
      'mitigated',
      'waiver',
    ]);
    expect(DECLINATION_LAW.mechanism_absent.constraint).toBe('na_is_falsifiable');
    expect(DECLINATION_LAW.mechanism_absent.requires).toBe('declination_predicate_id');
    expect(DECLINATION_LAW.waiver.constraint).toBe('waiver_expires');
    expect(DECLINATION_LAW.waiver.requires).toBe('declination_expires_at');
    expect(DECLINATION_LAW.mitigated.constraint).toBe('mitigated_names_local_clause');
    expect(DECLINATION_LAW.mitigated.requires).toBe('already_present_clause');
  });
});

describe('the SLA clock is measured against a named instant, never a wall clock', () => {
  it('measures against the instant it is handed', () => {
    const measured = interval('2022-01-16T00:00:00.000Z', '2022-01-17T00:00:00.000Z');
    expect(measured.measurable).toBe(true);
    expect(wholeDays(measured.deltaMs)).toBe(1);
    expect(measured.reference).toBe('2022-01-17T00:00:00.000Z');
  });

  it('reports unmeasurable rather than guessing when an instant will not parse', () => {
    const measured = interval('not-a-date', REFERENCE);
    expect(measured.measurable).toBe(false);
    expect(Number.isNaN(measured.deltaMs)).toBe(true);
  });

  it('is past_due only while an answer is still owed', () => {
    const past = interval('2020-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z');
    expect(slaStanding('proposed', past)).toBe('past_due');
    // A site that ANSWERED is not late, whatever the due date says. Rendering an answered
    // site as overdue would make the clock a permanent accusation.
    expect(slaStanding('declined', past)).toBe('answered');
    expect(slaStanding('adopted', past)).toBe('answered');
    expect(slaStanding('already_present', past)).toBe('answered');
  });

  it('does not read Date.now — the same inputs give the same standing years later', () => {
    const due = interval('2030-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z');
    expect(slaStanding('proposed', due)).toBe('within');
  });
});

// ── Ordering ───────────────────────────────────────────────────────────────

function row(overrides: Partial<FleetRow> & { readonly label: string }): FleetRow {
  const due = interval('2022-01-16T00:00:00.000Z', REFERENCE);
  const base: FleetRow = {
    propagation: {
      lesson_id: DATA.lesson.lesson_id,
      site_id: `site-${overrides.label}`,
      site_code: overrides.label,
      state: 'proposed',
      score: 0.5,
      model_version: 'test',
      proposed_at: '2021-12-02T00:00:00.000Z',
      due_by: '2022-01-16T00:00:00.000Z',
      open_conflicts: 0,
    },
    index: 0,
    label: overrides.label,
    severity: 3,
    state: 'proposed',
    standing: 'within',
    due,
    declination: null,
    conflicts: [],
    openConflicts: 0,
  };
  return { ...base, ...overrides };
}

describe('the ordering rule', () => {
  it('puts higher severity first', () => {
    const rows = [row({ label: 'A', severity: 1 }), row({ label: 'B', severity: 5 })];
    rows.sort(compareFleetRows);
    expect(rows.map((entry) => entry.label)).toEqual(['B', 'A']);
  });

  it('then puts the site that has owed an answer longest first', () => {
    const older = interval('2020-01-01T00:00:00.000Z', REFERENCE);
    const newer = interval('2025-01-01T00:00:00.000Z', REFERENCE);
    const rows = [
      row({ label: 'recent', standing: 'past_due', due: newer }),
      row({ label: 'ancient', standing: 'past_due', due: older }),
    ];
    rows.sort(compareFleetRows);
    expect(rows.map((entry) => entry.label)).toEqual(['ancient', 'recent']);
  });

  it('does NOT rank a declination below an adoption', () => {
    // The one ordering mistake that would quietly restate the product's claim: a fleet view
    // that sorts refusals to the bottom reports adoption. Both rows here have answered, so
    // only the deterministic label tie-break separates them — never the state.
    const rows = [
      row({ label: 'zeta', state: 'declined', standing: 'answered' }),
      row({ label: 'alpha', state: 'adopted', standing: 'answered' }),
    ];
    rows.sort(compareFleetRows);
    expect(rows.map((entry) => entry.label)).toEqual(['alpha', 'zeta']);

    const reversed = [
      row({ label: 'alpha', state: 'declined', standing: 'answered' }),
      row({ label: 'zeta', state: 'adopted', standing: 'answered' }),
    ];
    reversed.sort(compareFleetRows);
    expect(reversed.map((entry) => entry.label)).toEqual(['alpha', 'zeta']);
  });

  it('is a total order that does not depend on input order', () => {
    const forward = [row({ label: 'A' }), row({ label: 'B' }), row({ label: 'C' })];
    const backward = [row({ label: 'C' }), row({ label: 'B' }), row({ label: 'A' })];
    forward.sort(compareFleetRows);
    backward.sort(compareFleetRows);
    expect(forward.map((entry) => entry.label)).toEqual(backward.map((entry) => entry.label));
  });
});

describe('D15 — no person-shaped value is ever a sort key', () => {
  const conflict = (id: string, opened: string, resolvedBy: string | null): MergeConflict => ({
    conflict_id: id,
    lesson_id: DATA.lesson.lesson_id,
    site_id: 'site-1',
    clause_uuid: 'clause-1',
    base_digest: 'a'.repeat(64),
    ours_digest: 'b'.repeat(64),
    theirs_digest: 'c'.repeat(64),
    resolved_by: resolvedBy,
    opened_at: opened,
  });

  it('orders conflicts by age and id, and permuting resolved_by changes nothing', () => {
    const first = [
      conflict('c2', '2021-06-01T00:00:00.000Z', 'zzz'),
      conflict('c1', '2020-06-01T00:00:00.000Z', 'aaa'),
    ].sort(compareConflicts);

    const permuted = [
      conflict('c2', '2021-06-01T00:00:00.000Z', 'aaa'),
      conflict('c1', '2020-06-01T00:00:00.000Z', 'zzz'),
    ].sort(compareConflicts);

    expect(first.map((entry) => entry.conflict_id)).toEqual(['c1', 'c2']);
    expect(permuted.map((entry) => entry.conflict_id)).toEqual(['c1', 'c2']);
  });
});

// ── Resolution memory ──────────────────────────────────────────────────────

describe('resolution memory, read from the far end', () => {
  const conflict = (id: string, site: string, source: string | null): MergeConflict => ({
    conflict_id: id,
    lesson_id: DATA.lesson.lesson_id,
    site_id: site,
    clause_uuid: 'clause-1',
    base_digest: 'a'.repeat(64),
    ours_digest: 'b'.repeat(64),
    theirs_digest: 'c'.repeat(64),
    resolution_source: source,
    opened_at: '2021-06-01T00:00:00.000Z',
  });

  it('groups every conflict citing one recorded resolution, and names the sites', () => {
    const found = inheritanceOf([
      conflict('c1', 'site-a', 'memory-1'),
      conflict('c2', 'site-b', 'memory-1'),
      conflict('c3', 'site-c', null),
    ]);
    expect(found).toHaveLength(1);
    expect(found[0]?.source).toBe('memory-1');
    expect(found[0]?.siteIds).toEqual(['site-a', 'site-b']);
    expect(found[0]?.conflicts).toHaveLength(2);
  });

  it('counts a site once however many conflicts it opened against the same resolution', () => {
    const found = inheritanceOf([
      conflict('c1', 'site-a', 'memory-1'),
      conflict('c2', 'site-a', 'memory-1'),
    ]);
    expect(found[0]?.siteIds).toEqual(['site-a']);
    expect(found[0]?.conflicts).toHaveLength(2);
  });

  it('says whether the originating conflict is itself on screen', () => {
    const withOrigin = inheritanceOf([conflict('memory-1', 'site-a', null), conflict('c2', 'site-b', 'memory-1')]);
    expect(withOrigin[0]?.originOnScreen).toBe(true);

    const withoutOrigin = inheritanceOf([conflict('c2', 'site-b', 'memory-1')]);
    expect(withoutOrigin[0]?.originOnScreen).toBe(false);
  });

  it('returns nothing when nothing cites a resolution', () => {
    expect(inheritanceOf([conflict('c1', 'site-a', null)])).toEqual([]);
  });
});

// ── The whole view ─────────────────────────────────────────────────────────

describe('the fleet view over the real payload', () => {
  const view = buildFleetView(DATA, REFERENCE);

  it('keeps every propagation row — nothing is filtered anywhere', () => {
    expect(view.rows).toHaveLength(DATA.propagations.length);
  });

  it('preserves each row’s payload index, so provenance pointers stay attached', () => {
    for (const fleetRow of view.rows) {
      expect(DATA.propagations[fleetRow.index]).toBe(fleetRow.propagation);
    }
  });

  it('counts every member of prop_state, zeroes included', () => {
    expect(view.census.map(([state]) => state)).toEqual([...PROP_STATES]);
    const total = view.census.reduce((sum, [, count]) => sum + count, 0);
    expect(total).toBe(DATA.propagations.length);
  });

  it('attaches each conflict to the site that owns it, and orphans nothing silently', () => {
    const attached = view.attachedConflicts.length;
    const orphans = view.orphanConflicts.length;
    expect(attached + orphans).toBe(DATA.conflicts.length);
  });

  it('surfaces an orphan conflict rather than dropping it', () => {
    const orphaned = buildFleetView(
      {
        ...DATA,
        conflicts: [
          {
            conflict_id: 'orphan-1',
            lesson_id: DATA.lesson.lesson_id,
            site_id: 'a-site-with-no-propagation-row',
            clause_uuid: 'clause-1',
            base_digest: 'a'.repeat(64),
            ours_digest: 'b'.repeat(64),
            theirs_digest: 'c'.repeat(64),
            opened_at: '2021-06-01T00:00:00.000Z',
          },
        ],
      },
      REFERENCE,
    );
    expect(orphaned.orphanConflicts.map((entry) => entry.conflict_id)).toEqual(['orphan-1']);
  });

  it('builds a declination carrying the constraint that makes it falsifiable', () => {
    const declined = view.rows.find((entry) => entry.declination !== null);
    expect(declined?.declination?.constraint).toBeDefined();
    const kind = declined?.declination?.kind;
    if (kind !== undefined) {
      expect(declined?.declination?.requires).toBe(DECLINATION_LAW[kind].requires);
    }
  });

  it('reports an empty fleet as an empty fleet', () => {
    const empty = buildFleetView({ ...DATA, propagations: [], conflicts: [] }, REFERENCE);
    expect(empty.rows).toEqual([]);
    const states: readonly PropState[] = empty.census.map(([state]) => state);
    expect(states).toEqual([...PROP_STATES]);
    expect(empty.census.every(([, count]) => count === 0)).toBe(true);
  });
});
