// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The non-textual half of the diff: anchors, the Control Assertion Tuple, and the scalar
 * columns.
 *
 * Everything here compares TWO COLUMN VALUES and reports the difference. Nothing here
 * interprets one. In particular:
 *
 *   • anchors are compared by exact string equality. `HPU-0412` and `hpu-0412` are two
 *     anchors. Deciding they are one is an identity judgement, identity judgements belong
 *     to the cascade in the algorithms domain, and a renderer that quietly case-folded
 *     would hide exactly the `anchor_drop` residue that `mainline.identity_residue`
 *     exists to raise (ARCHITECTURE.md §5.3);
 *   • the CAT is walked structurally. `contracts/clause.schema.json` says its shape is
 *     owned by the algorithms domain and that the console "renders it as structured data
 *     and asserts nothing about its internals", so the walk knows about JSON and about
 *     nothing else — no field is special-cased, no key is ranked, no value is parsed;
 *   • arrays of different lengths are reported as ONE change at the array's pointer
 *     rather than index-wise. Aligning two arrays of different length means choosing an
 *     alignment, and a chosen alignment is an assertion about which element became which.
 */

import { jsonEqual } from '../../../data/schema';
import type {
  AnchorResidue,
  CatChange,
  CatDiff,
  ClauseVersion,
  JsonValue,
  ScalarChange,
} from '../model';

// ── Canonical JSON ─────────────────────────────────────────────────────────

/**
 * `JSON.stringify` with object keys in code-unit order.
 *
 * Not RFC 8785. This is a DISPLAY representation for two values sitting side by side in
 * a table — the console's canonicalisation for hashing is `src/verify/` (D6), and
 * borrowing this function for that purpose would be a bug. What it does guarantee is that
 * the same value renders the same way every time, which is what makes the from/to columns
 * comparable by eye and the model byte-stable across runs.
 */
export function canonicalJson(value: JsonValue | undefined): string | null {
  if (value === undefined) return null;
  return stringify(value);
}

function stringify(value: JsonValue): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'number') {
    return JSON.stringify(value);
  }
  if (typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => stringify(item)).join(',')}]`;
  const entries = Object.entries(value as Record<string, JsonValue>).sort(([a], [b]) =>
    a < b ? -1 : a > b ? 1 : 0,
  );
  return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stringify(item)}`).join(',')}}`;
}

/** RFC 6901 escaping for one pointer segment. */
export function escapePointerSegment(segment: string): string {
  return segment.replace(/~/g, '~0').replace(/\//g, '~1');
}

// ── Anchors ────────────────────────────────────────────────────────────────

function firstDuplicates(values: readonly string[]): readonly string[] {
  const seen = new Set<string>();
  const duplicated = new Set<string>();
  const order: string[] = [];
  for (const value of values) {
    if (seen.has(value)) {
      if (!duplicated.has(value)) {
        duplicated.add(value);
        order.push(value);
      }
    } else {
      seen.add(value);
    }
  }
  return order;
}

/** Order is preserved from the source arrays; a set would lose the document's order. */
export function diffAnchors(
  parent: readonly string[],
  version: readonly string[],
): AnchorResidue {
  const parentSet = new Set(parent);
  const versionSet = new Set(version);

  const seenDropped = new Set<string>();
  const dropped: string[] = [];
  for (const value of parent) {
    if (!versionSet.has(value) && !seenDropped.has(value)) {
      seenDropped.add(value);
      dropped.push(value);
    }
  }

  const seenAdded = new Set<string>();
  const added: string[] = [];
  const seenKept = new Set<string>();
  const kept: string[] = [];
  for (const value of version) {
    if (parentSet.has(value)) {
      if (!seenKept.has(value)) {
        seenKept.add(value);
        kept.push(value);
      }
    } else if (!seenAdded.has(value)) {
      seenAdded.add(value);
      added.push(value);
    }
  }

  return {
    dropped,
    added,
    kept,
    duplicatedInParent: firstDuplicates(parent),
    duplicatedInVersion: firstDuplicates(version),
  };
}

// ── The Control Assertion Tuple ────────────────────────────────────────────

/**
 * The most CAT changes the walk will report.
 *
 * A cap is needed because `cat_json` is `type: ["object","null"]` in the contract with no
 * depth or size limit, and an unbounded walk over a hostile payload is a frozen tab. The
 * cap is DECLARED in the model (`CatDiff.truncated`) and rendered, because a change list
 * that is quietly a prefix of the real one is worse than no change list.
 */
export const CAT_CHANGE_CAP = 200;

function isPlainObject(value: JsonValue | undefined): value is Readonly<Record<string, JsonValue>> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function walkCat(
  pointer: string,
  from: JsonValue | undefined,
  to: JsonValue | undefined,
  out: CatChange[],
): void {
  if (out.length >= CAT_CHANGE_CAP) return;

  if (from !== undefined && to !== undefined && jsonEqual(from, to)) return;

  if (from === undefined) {
    out.push({ pointer, kind: 'added', fromRepr: null, toRepr: canonicalJson(to) });
    return;
  }
  if (to === undefined) {
    out.push({ pointer, kind: 'removed', fromRepr: canonicalJson(from), toRepr: null });
    return;
  }

  if (isPlainObject(from) && isPlainObject(to)) {
    const keys = [...new Set([...Object.keys(from), ...Object.keys(to)])].sort((a, b) =>
      a < b ? -1 : a > b ? 1 : 0,
    );
    for (const key of keys) {
      walkCat(`${pointer}/${escapePointerSegment(key)}`, from[key], to[key], out);
    }
    return;
  }

  if (Array.isArray(from) && Array.isArray(to) && from.length === to.length) {
    for (let index = 0; index < from.length; index += 1) {
      walkCat(`${pointer}/${index}`, from[index], to[index], out);
    }
    return;
  }

  out.push({
    pointer,
    kind: 'changed',
    fromRepr: canonicalJson(from),
    toRepr: canonicalJson(to),
  });
}

export function diffCat(parent: ClauseVersion, version: ClauseVersion): CatDiff {
  const from = parent.cat_json ?? null;
  const to = version.cat_json ?? null;
  const hasParent = parent.cat_json !== null && parent.cat_json !== undefined;
  const hasVersion = version.cat_json !== null && version.cat_json !== undefined;

  const availability = hasParent
    ? hasVersion
      ? ('both' as const)
      : ('parent_only' as const)
    : hasVersion
      ? ('version_only' as const)
      : ('neither' as const);

  const changes: CatChange[] = [];
  if (availability === 'both') {
    walkCat('', from, to, changes);
  } else if (availability !== 'neither') {
    // One side has no tuple at all. That is one change at the root, not a field list:
    // enumerating the present side's keys as "added" would suggest the console knows
    // the absent side had none, and `cat_json` being NULL says only that it is NULL.
    changes.push({
      pointer: '',
      kind: hasVersion ? 'added' : 'removed',
      fromRepr: hasParent ? canonicalJson(from) : null,
      toRepr: hasVersion ? canonicalJson(to) : null,
    });
  }

  const keyChanged =
    parent.cat_key === undefined ||
    parent.cat_key === null ||
    version.cat_key === undefined ||
    version.cat_key === null
      ? null
      : parent.cat_key !== version.cat_key;

  const confidenceChanged =
    parent.cat_confidence === undefined || version.cat_confidence === undefined
      ? null
      : parent.cat_confidence !== version.cat_confidence;

  return {
    availability,
    changes,
    keyChanged,
    confidenceChanged,
    truncated: changes.length >= CAT_CHANGE_CAP ? { cap: CAT_CHANGE_CAP } : null,
  };
}

// ── Scalar columns ─────────────────────────────────────────────────────────

/**
 * The columns rendered side by side, in the order the panel shows them.
 *
 * `presentationOnly` carries ARCHITECTURE.md §5.3's comment on the DDL — `ordinal` is
 * "presentation only, NEVER identity" — onto the screen, where a reader deciding whether
 * a renumber matters can see it. `printed_label` is the same kind of fact: `7.3.2(b)` is
 * what the paper says, not what the clause IS.
 */
const SCALAR_COLUMNS: readonly {
  readonly column: string;
  readonly presentationOnly: boolean;
  readonly read: (version: ClauseVersion) => string;
}[] = [
  { column: 'canon_sha256', presentationOnly: false, read: (v) => v.canon_sha256 },
  { column: 'canon_version', presentationOnly: false, read: (v) => String(v.canon_version) },
  { column: 'activity_root', presentationOnly: false, read: (v) => v.activity_root },
  { column: 'cat_key', presentationOnly: false, read: (v) => v.cat_key ?? '∅' },
  { column: 'cat_confidence', presentationOnly: false, read: (v) => v.cat_confidence ?? '∅' },
  { column: 'sev_max', presentationOnly: false, read: (v) => String(v.sev_max) },
  { column: 'blood_root', presentationOnly: false, read: (v) => v.blood_root ?? '∅' },
  {
    column: 'blood_size',
    presentationOnly: false,
    read: (v) => (v.blood_size === null || v.blood_size === undefined ? '∅' : String(v.blood_size)),
  },
  { column: 'doc_id', presentationOnly: false, read: (v) => v.doc_id ?? '∅' },
  { column: 'site_id', presentationOnly: false, read: (v) => v.site_id },
  { column: 'printed_label', presentationOnly: true, read: (v) => v.printed_label ?? '∅' },
  {
    column: 'ordinal',
    presentationOnly: true,
    read: (v) => (v.ordinal === undefined ? '∅' : String(v.ordinal)),
  },
];

/**
 * The set of columns a `delta_witness` row could legitimately be ABOUT.
 *
 * A witness explains a control delta. `canon_sha256` and `sev_max` are consequences of
 * one — a digest changes because the text did, a severity is projected from the blame
 * closure by a trigger — so listing them as "unwitnessed" would bury the two entries that
 * matter under a wall of noise, which is how a reader learns to skip the panel.
 */
export const DELTA_BEARING_COLUMNS: readonly string[] = ['cat_key', 'cat_confidence'];

export function diffScalars(
  parent: ClauseVersion,
  version: ClauseVersion,
): readonly ScalarChange[] {
  return SCALAR_COLUMNS.map((spec) => {
    const fromRepr = spec.read(parent);
    const toRepr = spec.read(version);
    return {
      column: spec.column,
      fromRepr,
      toRepr,
      changed: fromRepr !== toRepr,
      presentationOnly: spec.presentationOnly,
    };
  });
}
