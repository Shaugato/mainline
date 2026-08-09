// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The fleet view's model — pure, deterministic, and clock-free.
 *
 * Every function here takes the payload and an explicit reference instant. Nothing reads
 * `Date.now()`, for two reasons that are both load-bearing:
 *
 *   1. cinema mode (D12) freezes the clock so the demo capture is byte-stable, and a
 *      module that reaches for the wall clock defeats that from inside; and
 *   2. an SLA statement measured against *the reader's* laptop clock is a statement
 *      about the reader's laptop. The reference instant is the payload's `observed_at`,
 *      it is rendered beside every interval, and the screen says which one it used.
 *
 * ── WHAT THIS MODULE REFUSES TO DO ───────────────────────────────────────────────
 *
 * It does not decide whether a site is compliant, it does not grade a declination, and
 * it does not compute a gate condition (D5). `mainline.propagation.state` is a column
 * the database wrote; the console orders rows and renders them. The ONE derived value
 * here is an elapsed interval between two timestamps that are both on screen, and it is
 * chipped `recomputed` where it appears.
 *
 * ── THE ATTRIBUTION RULE, MECHANICALLY (D15 / I15) ───────────────────────────────
 *
 * `merge_conflict.resolved_by` is the only person-shaped value in this payload. It is
 * rendered as a verbatim column value and it is NEVER a sort key, a facet, a colour or
 * an axis. `compareFleetRows` and `compareConflicts` below do not read it, and
 * `tests/unit/propagation/model.test.ts` asserts that by permuting it and requiring the
 * order to be unchanged.
 */

import type {
  Lesson,
  MergeConflict,
  Propagation,
  PropState,
  Severity,
  Timestamp,
  Uuid,
} from '../../data/types.generated';

// ── The law, stated rather than applied ──────────────────────────────────────────

/**
 * `only_tightenings_travel` — ARCHITECTURE.md §5.9, MI23.
 *
 * This is rendered as a STATED LAW and never as a filter control, because it is not a
 * filter: `mainline.lesson.control_delta` is constrained by a CHECK, so a weakening
 * lesson is not a representable row. There is nothing being hidden from the list below,
 * and a UI that offered a "show weakenings" toggle would be advertising a state the
 * database cannot hold.
 */
export const ONLY_TIGHTENINGS_TRAVEL = Object.freeze({
  constraint: 'only_tightenings_travel',
  table: 'mainline.lesson',
  column: 'control_delta',
  /** The values the CHECK admits, in the order the DDL writes them. */
  admits: Object.freeze(['introduce', 'strengthen', 'restate'] as const),
  /** Members of `mainline.control_delta` the CHECK excludes. */
  excludes: Object.freeze(['weaken', 'remove'] as const),
  sqlstate: '23514',
  statement:
    'Weakenings are site-local trade-offs and must be re-earned locally. A lesson whose ' +
    'control_delta is weaken or remove is not a representable row, so nothing is being ' +
    'filtered out of the fleet below — there is nothing to filter.',
});

/**
 * The CHECK that makes each declination kind falsifiable, and the column it requires.
 *
 * ARCHITECTURE.md §5.9. The console renders the constraint name and the value of the
 * column it demands; it does not render a verdict. A missing column is shown as missing,
 * which is a fact about the payload, not an accusation about the row.
 */
export const DECLINATION_LAW = Object.freeze({
  mitigated: Object.freeze({
    constraint: 'mitigated_names_local_clause',
    requires: 'already_present_clause',
    gloss: 'the site already carries a local clause that answers the hazard, and names it',
  }),
  waiver: Object.freeze({
    constraint: 'waiver_expires',
    requires: 'declination_expires_at',
    gloss: 'a time-boxed refusal that expires without further action',
  }),
  mechanism_absent: Object.freeze({
    constraint: 'na_is_falsifiable',
    requires: 'declination_predicate_id',
    gloss: 'the hazard mechanism does not exist here, and a machine-checkable predicate says so',
  }),
});

export type DeclinationKind = keyof typeof DECLINATION_LAW;

export function isDeclinationKind(value: unknown): value is DeclinationKind {
  return value === 'mitigated' || value === 'waiver' || value === 'mechanism_absent';
}

// ── Time, measured against a named instant ───────────────────────────────────────

export interface Interval {
  /** `reference − subject`, in milliseconds. Positive when the subject is in the past. */
  readonly deltaMs: number;
  /** The instant the interval was measured against. Always rendered beside it. */
  readonly reference: Timestamp;
  readonly subject: Timestamp;
  /** False when either instant failed to parse; the screen then renders neither number. */
  readonly measurable: boolean;
}

export function interval(subject: Timestamp | null, reference: Timestamp): Interval {
  const subjectMs = subject === null ? Number.NaN : Date.parse(subject);
  const referenceMs = Date.parse(reference);
  const measurable = Number.isFinite(subjectMs) && Number.isFinite(referenceMs);
  return {
    deltaMs: measurable ? referenceMs - subjectMs : Number.NaN,
    reference,
    subject: subject ?? '',
    measurable,
  };
}

const DAY_MS = 86_400_000;

/** Whole days, truncated toward zero. Used for display only; the instants are also shown. */
export function wholeDays(value: number): number {
  return Number.isFinite(value) ? Math.trunc(value / DAY_MS) : 0;
}

// ── SLA standing ─────────────────────────────────────────────────────────────────

/**
 * Three standings and no fourth, and none of them is a judgement.
 *
 *   `answered`  the site recorded a state other than `proposed` — adopted, declined,
 *               already_present, conflicted or revoked. The clock stopped mattering.
 *   `within`    an answer is still owed and the due instant has not passed.
 *   `past_due`  an answer is still owed and the due instant has passed.
 *
 * `past_due` is a comparison between two timestamps on the screen. It is not styled as an
 * alarm and it never blinks: the SLA clock is a fact, never a nag (the brief), and a
 * console that nags is a console people learn to dismiss.
 */
export type SlaStanding = 'answered' | 'within' | 'past_due';

export function slaStanding(state: PropState, due: Interval): SlaStanding {
  if (state !== 'proposed') return 'answered';
  if (!due.measurable) return 'within';
  return due.deltaMs > 0 ? 'past_due' : 'within';
}

// ── A row of the fleet ───────────────────────────────────────────────────────────

export interface Declination {
  readonly kind: DeclinationKind;
  readonly constraint: string;
  /** The column the CHECK requires for this kind. */
  readonly requires: string;
  readonly gloss: string;
  /** The value of that column, or `null` when the payload carries none. */
  readonly requiredValue: string | null;
  readonly predicateId: Uuid | null;
  readonly expiresAt: Timestamp | null;
  readonly alreadyPresentClause: Uuid | null;
  /** Elapsed against the reference instant, when the kind carries an expiry. */
  readonly expiry: Interval | null;
}

export interface FleetRow {
  readonly propagation: Propagation;
  /**
   * The row's index in `data.propagations` as the payload ordered them.
   *
   * Kept because the envelope's provenance pointers address rows POSITIONALLY
   * (`/propagations/1/declination_kind`), and this list is re-ordered for reading. Losing
   * the payload index would silently attach one row's provenance claim to another row's
   * value, which is the quietest possible way for a provenance chip to become a lie.
   */
  readonly index: number;
  /** How the site is named on screen: its code when it has one, else its id. */
  readonly label: string;
  /**
   * The lesson's `max_severity`, carried onto every row.
   *
   * On a single-lesson view this term is constant, so it does not reorder anything
   * today. It is in the key rather than assumed away because the ordering the brief
   * states is "by severity and overdue-ness", and a comparator that silently dropped
   * the first term would be a different rule wearing the same sentence.
   */
  readonly severity: Severity;
  readonly state: PropState;
  readonly standing: SlaStanding;
  readonly due: Interval;
  readonly declination: Declination | null;
  readonly conflicts: readonly MergeConflict[];
  readonly openConflicts: number;
}

function declinationOf(row: Propagation, reference: Timestamp): Declination | null {
  const kind = row.declination_kind ?? null;
  if (kind === null || !isDeclinationKind(kind)) return null;

  const law = DECLINATION_LAW[kind];
  const predicateId = row.declination_predicate_id ?? null;
  const expiresAt = row.declination_expires_at ?? null;
  const alreadyPresentClause = row.already_present_clause ?? null;

  const requiredValue =
    law.requires === 'declination_predicate_id'
      ? predicateId
      : law.requires === 'declination_expires_at'
        ? expiresAt
        : alreadyPresentClause;

  return {
    kind,
    constraint: law.constraint,
    requires: law.requires,
    gloss: law.gloss,
    requiredValue,
    predicateId,
    expiresAt,
    alreadyPresentClause,
    expiry: expiresAt === null ? null : interval(expiresAt, reference),
  };
}

const STANDING_RANK: Readonly<Record<SlaStanding, number>> = Object.freeze({
  past_due: 2,
  within: 1,
  answered: 0,
});

/**
 * Severity, then overdue-ness. Ties broken by open conflicts, then by the site's label.
 *
 * The final term is the site LABEL and not the site id, so the order is stable and
 * readable rather than stable and arbitrary. Nothing in this comparator reads
 * `resolved_by`, `resolution_source`, or any other person-shaped value.
 */
export function compareFleetRows(a: FleetRow, b: FleetRow): number {
  if (a.severity !== b.severity) return b.severity - a.severity;

  const rankA = STANDING_RANK[a.standing];
  const rankB = STANDING_RANK[b.standing];
  if (rankA !== rankB) return rankB - rankA;

  const overdueA = a.standing === 'past_due' && a.due.measurable ? a.due.deltaMs : 0;
  const overdueB = b.standing === 'past_due' && b.due.measurable ? b.due.deltaMs : 0;
  if (overdueA !== overdueB) return overdueB - overdueA;

  if (a.openConflicts !== b.openConflicts) return b.openConflicts - a.openConflicts;

  return a.label.localeCompare(b.label);
}

/** Conflicts, oldest first. Age is the only ordering an undeletable record deserves. */
export function compareConflicts(a: MergeConflict, b: MergeConflict): number {
  const openedA = Date.parse(a.opened_at);
  const openedB = Date.parse(b.opened_at);
  if (Number.isFinite(openedA) && Number.isFinite(openedB) && openedA !== openedB) {
    return openedA - openedB;
  }
  return a.conflict_id.localeCompare(b.conflict_id);
}

// ── Resolution memory, as a visible relationship ─────────────────────────────────

/**
 * `resolution_memory.origin_conflict`, read from the other end.
 *
 * ARCHITECTURE.md §5.9: *"when a resolution is later found wrong, one query returns
 * every site that inherited it"*. `merge_conflict.resolution_source` is that back-pointer,
 * and grouping the conflicts by it turns the sentence into a rendered relationship: one
 * recorded resolution, and every site standing on it.
 *
 * ── THE HONEST GAP ───────────────────────────────────────────────────────────────
 *
 * `resolution_memory.recalled_at` — the column that records that a resolution was later
 * FOUND WRONG — is not in `contracts/propagation.schema.json` v1.0. So this console can
 * show the inheritance fan-out and cannot show the recall flag. The screen says exactly
 * that rather than implying the absence of a flag means the resolution is sound.
 */
export interface ResolutionInheritance {
  /** `merge_conflict.resolution_source` — the recorded resolution being stood on. */
  readonly source: Uuid;
  /** Every conflict citing it, oldest first. */
  readonly conflicts: readonly MergeConflict[];
  /** The distinct sites that inherited it, in first-appearance order. */
  readonly siteIds: readonly Uuid[];
  /** True when the originating conflict is itself in this payload. */
  readonly originOnScreen: boolean;
}

export function inheritanceOf(
  conflicts: readonly MergeConflict[],
): readonly ResolutionInheritance[] {
  const bySource = new Map<Uuid, MergeConflict[]>();
  for (const conflict of conflicts) {
    const source = conflict.resolution_source ?? null;
    if (source === null) continue;
    const bucket = bySource.get(source);
    if (bucket === undefined) bySource.set(source, [conflict]);
    else bucket.push(conflict);
  }

  const known = new Set(conflicts.map((conflict) => conflict.conflict_id));

  return [...bySource.entries()]
    .map(([source, bucket]) => {
      const ordered = [...bucket].sort(compareConflicts);
      const siteIds: Uuid[] = [];
      for (const conflict of ordered) {
        if (!siteIds.includes(conflict.site_id)) siteIds.push(conflict.site_id);
      }
      return {
        source,
        conflicts: ordered,
        siteIds,
        originOnScreen: known.has(source),
      };
    })
    .sort((a, b) => b.conflicts.length - a.conflicts.length || a.source.localeCompare(b.source));
}

// ── The whole view ───────────────────────────────────────────────────────────────

export interface PropagationData {
  readonly lesson: Lesson;
  readonly propagations: readonly Propagation[];
  readonly conflicts: readonly MergeConflict[];
}

export interface FleetView {
  readonly lesson: Lesson;
  readonly rows: readonly FleetRow[];
  /** Conflicts belonging to a site that has a propagation row, oldest first. */
  readonly attachedConflicts: readonly MergeConflict[];
  /** Conflicts whose site has no propagation row — an orphan is shown, never dropped. */
  readonly orphanConflicts: readonly MergeConflict[];
  readonly inheritance: readonly ResolutionInheritance[];
  readonly reference: Timestamp;
  /** Per-state tallies, for the one-line census above the list. */
  readonly census: readonly (readonly [PropState, number])[];
}

/** The order the census is written in. Every state appears, including the zeroes. */
export const PROP_STATES: readonly PropState[] = Object.freeze([
  'proposed',
  'conflicted',
  'declined',
  'already_present',
  'adopted',
  'revoked',
]);

export function buildFleetView(data: PropagationData, reference: Timestamp): FleetView {
  const conflictsBySite = new Map<Uuid, MergeConflict[]>();
  for (const conflict of data.conflicts) {
    const bucket = conflictsBySite.get(conflict.site_id);
    if (bucket === undefined) conflictsBySite.set(conflict.site_id, [conflict]);
    else bucket.push(conflict);
  }

  const rows: FleetRow[] = data.propagations.map((row, index) => {
    const due = interval(row.due_by, reference);
    const conflicts = [...(conflictsBySite.get(row.site_id) ?? [])].sort(compareConflicts);
    return {
      propagation: row,
      index,
      label: row.site_code ?? row.site_id,
      severity: data.lesson.max_severity,
      state: row.state,
      standing: slaStanding(row.state, due),
      due,
      declination: declinationOf(row, reference),
      conflicts,
      openConflicts: row.open_conflicts,
    };
  });
  rows.sort(compareFleetRows);

  const sitesWithRows = new Set(data.propagations.map((row) => row.site_id));
  const attachedConflicts = data.conflicts
    .filter((conflict) => sitesWithRows.has(conflict.site_id))
    .sort(compareConflicts);
  const orphanConflicts = data.conflicts
    .filter((conflict) => !sitesWithRows.has(conflict.site_id))
    .sort(compareConflicts);

  const counts = new Map<PropState, number>(PROP_STATES.map((state) => [state, 0]));
  for (const row of data.propagations) {
    counts.set(row.state, (counts.get(row.state) ?? 0) + 1);
  }

  return {
    lesson: data.lesson,
    rows,
    attachedConflicts,
    orphanConflicts,
    inheritance: inheritanceOf(data.conflicts),
    reference,
    census: PROP_STATES.map((state) => [state, counts.get(state) ?? 0] as const),
  };
}
