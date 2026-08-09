// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Witness binding — the console corroborating, never explaining.
 *
 *     THE CONSOLE MAY COMPUTE WHAT CHANGED. ONLY THE DATABASE MAY SAY WHY.
 *
 * A `mainline.delta_witness` row names a `field` and asserts a `from_repr → to_repr` with
 * a `note`. This module does exactly one thing with it: works out WHICH OBSERVATION the
 * field refers to, and reports whether this browser saw that thing change. It never edits
 * the row, never reorders its members, never re-words the note, and never turns an
 * observation into a reason.
 *
 * The two states people would be tempted to collapse are kept apart deliberately:
 *
 *   `no_observed_change` — the console looked at the named field and it was the same in
 *                          both rows. That is evidence about the witness.
 *   `uncorroborable`     — there is no comparable ancestor in this payload, so the
 *                          console looked at nothing. That is evidence about the payload.
 *
 * And the field vocabulary is a CLOSED, DECLARED map. `resolveWitnessField` refuses
 * anything it does not recognise rather than pattern-matching its way to a plausible
 * target: `docs/leads/algorithms.md` says `rule_id ∈ R1_DEONTIC … R9_COVERAGE` and says
 * nothing at all about the spelling of `field`, so a console that guessed would be
 * inventing a correspondence between a database row and a screen element.
 */

import type {
  AnchorResidue,
  BoundWitness,
  CatDiff,
  DeltaWitness,
  ScalarChange,
  TextDiff,
  UnwitnessedChange,
  WitnessAvailability,
  WitnessBinding,
  WitnessTarget,
} from '../model';
import { DELTA_BEARING_COLUMNS, escapePointerSegment } from './structure';

// ── The field vocabulary ───────────────────────────────────────────────────

/** Spellings that mean `clause_version.canon_text`. */
const TEXT_FIELDS = new Set(['canon_text', 'clause_version.canon_text', 'text']);

/** Spellings that mean `clause_version.anchor_set`. */
const ANCHOR_FIELDS = new Set(['anchor_set', 'clause_version.anchor_set', 'anchors']);

/** Spellings that mean the whole Control Assertion Tuple. */
const CAT_ROOT_FIELDS = new Set(['cat', 'cat_json', 'clause_version.cat_json']);

/**
 * Scalar columns a witness may name.
 *
 * Closed on purpose, and short: these are the columns of `mainline.clause_version` that a
 * lattice rule could plausibly be about. A column absent from this set resolves to
 * `unresolved`, which is rendered as "this console does not know what that field is" —
 * an honest gap that somebody can close by adding one line here.
 */
const COLUMN_FIELDS = new Set([
  'cat_key',
  'cat_confidence',
  'canon_version',
  'canon_sha256',
  'activity_root',
  'printed_label',
  'ordinal',
  'sev_max',
  'blood_root',
  'blood_size',
  'control_delta',
  'delta_basis',
]);

const CAT_PREFIXES = ['cat.', 'cat/', 'cat_json.', 'cat_json/', '/cat_json/', '/cat/'];

const UNRESOLVED: WitnessTarget = { kind: 'unresolved', pointer: null, column: null };

/**
 * Maps a witness's `field` string onto the observation it refers to.
 *
 * Accepts the dotted form (`cat.location`), the slashed form (`cat_json/location`) and a
 * rooted pointer (`/cat_json/location`), because all three appear in the design documents
 * and none of them is wrong. Everything else is `unresolved`.
 */
export function resolveWitnessField(field: string): WitnessTarget {
  const trimmed = field.trim();
  if (trimmed === '') return UNRESOLVED;

  if (TEXT_FIELDS.has(trimmed)) return { kind: 'text', pointer: null, column: null };
  if (ANCHOR_FIELDS.has(trimmed)) return { kind: 'anchor_set', pointer: null, column: null };
  if (CAT_ROOT_FIELDS.has(trimmed)) return { kind: 'cat', pointer: '', column: null };

  for (const prefix of CAT_PREFIXES) {
    if (!trimmed.startsWith(prefix)) continue;
    const rest = trimmed.slice(prefix.length);
    if (rest === '') return { kind: 'cat', pointer: '', column: null };
    // Split on the separator the caller used. A dotted path never contains a slash
    // segment separator and vice versa, so trying both would invent segments.
    const separator = prefix.endsWith('.') ? '.' : '/';
    const segments = rest.split(separator).filter((segment) => segment !== '');
    const pointer = segments.map((segment) => `/${escapePointerSegment(segment)}`).join('');
    return { kind: 'cat', pointer, column: null };
  }

  const bare = trimmed.startsWith('clause_version.') ? trimmed.slice('clause_version.'.length) : trimmed;
  if (COLUMN_FIELDS.has(bare)) return { kind: 'column', pointer: null, column: bare };

  return UNRESOLVED;
}

// ── Observations, as a thing a witness can be checked against ──────────────

export interface Observations {
  readonly text: TextDiff | null;
  readonly anchors: AnchorResidue | null;
  readonly cat: CatDiff | null;
  readonly scalars: readonly ScalarChange[];
  /** False when there is no comparable ancestor: nothing was observed, at all. */
  readonly comparable: boolean;
}

/** Whether one CAT pointer is the same node as, an ancestor of, or a descendant of another. */
function pointersRelated(a: string, b: string): boolean {
  if (a === b) return true;
  if (a === '') return b.startsWith('/');
  if (b === '') return a.startsWith('/');
  return a.startsWith(`${b}/`) || b.startsWith(`${a}/`);
}

function targetChanged(target: WitnessTarget, observations: Observations): boolean {
  switch (target.kind) {
    case 'text':
      return observations.text !== null && !observations.text.identical;
    case 'anchor_set':
      return (
        observations.anchors !== null &&
        observations.anchors.dropped.length + observations.anchors.added.length > 0
      );
    case 'cat': {
      const pointer = target.pointer;
      if (observations.cat === null || pointer === null) return false;
      return observations.cat.changes.some((change) => pointersRelated(change.pointer, pointer));
    }
    case 'column':
      return observations.scalars.some(
        (scalar) => scalar.column === target.column && scalar.changed,
      );
    case 'unresolved':
      return false;
  }
}

function bindingNoteFor(
  state: BoundWitness['state'],
  target: WitnessTarget,
  field: string,
): string {
  switch (state) {
    case 'bound':
      return `This browser compared the two rows and observed a change at ${describeTarget(target)}, which is what this row names.`;
    case 'no_observed_change':
      return `This browser compared the two rows and observed NO change at ${describeTarget(target)}. The row is shown as the database wrote it; the console reports only that it could not corroborate it here.`;
    case 'unresolvable_field':
      return `This console does not know what "${field}" refers to, so it attached nothing. The row is shown verbatim; guessing at a target would be the console inventing a correspondence.`;
    case 'uncorroborable':
      return 'This payload carries no comparable ancestor version, so the console observed nothing and has no basis to corroborate or question this row.';
  }
}

function describeTarget(target: WitnessTarget): string {
  switch (target.kind) {
    case 'text':
      return 'canon_text';
    case 'anchor_set':
      return 'anchor_set';
    case 'cat':
      return target.pointer === '' ? 'cat_json' : `cat_json${target.pointer ?? ''}`;
    case 'column':
      return target.column ?? 'an unnamed column';
    case 'unresolved':
      return 'an unresolved field';
  }
}

export function bindWitnesses(
  witnesses: readonly DeltaWitness[] | null,
  minimal: boolean | null,
  observations: Observations,
): WitnessBinding {
  const availability: WitnessAvailability =
    witnesses === null ? 'unavailable' : witnesses.length === 0 ? 'asserted_none' : 'present';

  const bound: BoundWitness[] = (witnesses ?? []).map((witness) => {
    const target = resolveWitnessField(witness.field);
    const state: BoundWitness['state'] =
      target.kind === 'unresolved'
        ? 'unresolvable_field'
        : !observations.comparable
          ? 'uncorroborable'
          : targetChanged(target, observations)
            ? 'bound'
            : 'no_observed_change';
    return { witness, target, state, bindingNote: bindingNoteFor(state, target, witness.field) };
  });

  return { availability, witnesses: bound, minimal };
}

// ── The gap ────────────────────────────────────────────────────────────────

/**
 * Observed changes that no witness row accounts for.
 *
 * Scope is deliberate. Only things a `delta_witness` could BE about are considered: the
 * canonical text, the anchor set, the CAT, and the two CAT columns. A digest that changed
 * because the text did is not an unexplained change, and listing it would bury the two
 * entries that matter.
 *
 * The wording of every entry is an OBSERVATION. There is no "because", no ranking, and no
 * adjective. An unwitnessed change may be entirely innocent; what it may not be is
 * invisible.
 */
export function findUnwitnessed(
  binding: WitnessBinding,
  observations: Observations,
): readonly UnwitnessedChange[] {
  if (!observations.comparable) return [];

  const covered = binding.witnesses.filter((entry) => entry.state === 'bound');
  const coversText = covered.some((entry) => entry.target.kind === 'text');
  const coversAnchors = covered.some((entry) => entry.target.kind === 'anchor_set');
  const catPointers = covered
    .filter((entry) => entry.target.kind === 'cat')
    .map((entry) => entry.target.pointer ?? '');
  const columns = new Set(
    covered.filter((entry) => entry.target.kind === 'column').map((entry) => entry.target.column),
  );

  const out: UnwitnessedChange[] = [];

  const text = observations.text;
  if (text !== null && !text.identical && !coversText) {
    out.push({
      kind: 'text',
      subject: 'canon_text',
      detail:
        `The canonical text differs between the two versions — ${text.removedChars} character(s) ` +
        `removed, ${text.addedChars} added. No witness row in this payload names canon_text.`,
    });
  }

  const anchors = observations.anchors;
  if (anchors !== null && !coversAnchors) {
    for (const value of anchors.dropped) {
      out.push({
        kind: 'anchor_dropped',
        subject: value,
        detail:
          'Present in the ancestor version, absent from this one. No witness row in this ' +
          'payload names anchor_set.',
      });
    }
    for (const value of anchors.added) {
      out.push({
        kind: 'anchor_added',
        subject: value,
        detail:
          'Absent from the ancestor version, present in this one. No witness row in this ' +
          'payload names anchor_set.',
      });
    }
  }

  const cat = observations.cat;
  if (cat !== null) {
    for (const change of cat.changes) {
      if (catPointers.some((pointer) => pointersRelated(pointer, change.pointer))) continue;
      out.push({
        kind: 'cat',
        subject: change.pointer === '' ? 'cat_json' : change.pointer,
        detail:
          `The Control Assertion Tuple was ${change.kind} at this pointer. No witness row in ` +
          'this payload names it.',
      });
    }
  }

  for (const scalar of observations.scalars) {
    if (!scalar.changed) continue;
    if (!DELTA_BEARING_COLUMNS.includes(scalar.column)) continue;
    if (columns.has(scalar.column)) continue;
    out.push({
      kind: 'column',
      subject: scalar.column,
      detail: 'This column differs between the two versions. No witness row in this payload names it.',
    });
  }

  return out;
}
