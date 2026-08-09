// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CLAUSE DIFF, as a type.
 *
 * One sentence governs every declaration in this file:
 *
 *     THE CONSOLE MAY COMPUTE WHAT CHANGED. ONLY THE DATABASE MAY SAY WHY.
 *
 * `TextDiff`, `AnchorResidue`, `CatDiff` and `ScalarChange` are the WHAT. They are
 * re-derived in this browser from two `canon_text` / `anchor_set` / `cat_json` column
 * values, they are deterministic, and they carry the `recomputed` provenance chip.
 *
 * `DeltaWitness` — the WHY — is never computed here. It arrives as rows from
 * `mainline.delta_witness`, it is rendered verbatim, and when it is absent the surface
 * says WITNESS UNAVAILABLE and stops. There is no code path in this feature that turns
 * an observed textual change into a reason for it; `UnwitnessedChange` exists precisely
 * so that the gap between the two is a rendered fact rather than a plausible sentence.
 *
 * Everything here is data. No function in this file, and no `Date`, no `Math.random`,
 * no locale-sensitive comparison anywhere in the engine that produces it — the model is
 * a pure function of the payload, which is what makes it screenshot-testable (D12) and
 * what lets `engine.test.ts` assert byte-identity across two runs.
 */

import type {
  ClauseVersion,
  ControlDelta,
  DeltaBasis,
  DeltaWitness,
  JsonValue,
} from '../../data/types.generated';

// ── The text ───────────────────────────────────────────────────────────────

export type TokenKind = 'word' | 'space' | 'punct';

export interface Token {
  readonly text: string;
  /** Offset of the first character, into the string that was tokenised. */
  readonly start: number;
  /** Offset one past the last character. */
  readonly end: number;
  readonly kind: TokenKind;
}

export type TextSegmentKind = 'equal' | 'removed' | 'added';

/**
 * One run of the diff.
 *
 * Offsets are ALWAYS into `canon_text` — `contracts/clause.schema.json` says so about
 * the column and this console holds to it: a highlight drawn against `raw_text` would
 * be off by however much the canonicaliser moved, and nobody would notice until an
 * exhibit was already printed. `fromStart`/`fromEnd` index the PARENT's `canon_text`;
 * `toStart`/`toEnd` index the VERSION's. A segment absent from one side carries `null`
 * on that side rather than a plausible-looking zero.
 */
export interface TextSegment {
  readonly kind: TextSegmentKind;
  readonly text: string;
  readonly fromStart: number | null;
  readonly fromEnd: number | null;
  readonly toStart: number | null;
  readonly toEnd: number | null;
}

/**
 * Why a diff is coarser than it could be. `null` means it is exact.
 *
 * The only value is `diff_budget_exhausted`, and it is a DECLARED state rather than a
 * quiet fallback: the segments still reproduce both texts exactly, but the granularity
 * is whole-block rather than token, and the surface says so in words.
 */
export interface DiffDegradation {
  readonly reason: 'diff_budget_exhausted';
  readonly budget: number;
  readonly demanded: number;
}

export interface TextDiff {
  readonly segments: readonly TextSegment[];
  readonly equalChars: number;
  readonly removedChars: number;
  readonly addedChars: number;
  readonly parentLength: number;
  readonly versionLength: number;
  readonly identical: boolean;
  readonly degraded: DiffDegradation | null;
}

// ── The anchors ────────────────────────────────────────────────────────────

/**
 * `clause_version.anchor_set` — tags, setpoints, citations, CAS numbers, roles.
 *
 * An anchor dropped between versions is one of `mainline.identity_residue`'s declared
 * reasons (`anchor_drop`, ARCHITECTURE.md §5.3), which is why this is its own panel and
 * not a footnote under the text. Comparison is EXACT STRING EQUALITY: no case folding,
 * no trimming, no fuzzy match. `HPU-0412` and `hpu-0412` are two anchors here, because
 * deciding they are one is an identity judgement and identity judgements belong to the
 * cascade in the algorithms domain, not to a renderer.
 */
export interface AnchorResidue {
  /** Present in the parent, absent from the version. Parent order preserved. */
  readonly dropped: readonly string[];
  /** Present in the version, absent from the parent. Version order preserved. */
  readonly added: readonly string[];
  /** Present in both. Version order preserved. */
  readonly kept: readonly string[];
  /** Values appearing more than once in the parent's array, in first-seen order. */
  readonly duplicatedInParent: readonly string[];
  /** Values appearing more than once in the version's array, in first-seen order. */
  readonly duplicatedInVersion: readonly string[];
}

// ── The Control Assertion Tuple ────────────────────────────────────────────

export type CatChangeKind = 'added' | 'removed' | 'changed';

export interface CatChange {
  /** RFC 6901 JSON Pointer into `cat_json`. The empty string is the document root. */
  readonly pointer: string;
  readonly kind: CatChangeKind;
  /** Canonical JSON text — object keys sorted — or `null` when the side has no value. */
  readonly fromRepr: string | null;
  readonly toRepr: string | null;
}

export type CatAvailability = 'both' | 'version_only' | 'parent_only' | 'neither';

export interface CatDiff {
  readonly availability: CatAvailability;
  readonly changes: readonly CatChange[];
  /** `cat_key` differs between the two versions. Null when either side has none. */
  readonly keyChanged: boolean | null;
  /** `cat_confidence` differs. Null when either side omitted it. */
  readonly confidenceChanged: boolean | null;
  /** Set when the walk hit its node cap; the change list is a prefix, and says so. */
  readonly truncated: { readonly cap: number } | null;
}

// ── The scalar columns ─────────────────────────────────────────────────────

/**
 * One column, both sides, rendered verbatim.
 *
 * `repr` is a STRING on purpose. These values reach the screen in the mono face beside
 * a `db:column` chip, and formatting a number for display is a decision that must be
 * made once, here, rather than in each component — a column that reads `1 200` in one
 * panel and `1200` in another is a column a reader cannot grep for.
 */
export interface ScalarChange {
  readonly column: string;
  readonly fromRepr: string;
  readonly toRepr: string;
  readonly changed: boolean;
  /**
   * True for columns that are presentation only and NEVER identity — `ordinal`, and
   * `printed_label`. ARCHITECTURE.md §5.3 says so of `ordinal` in a comment on the DDL;
   * carrying the fact into the model keeps it on the screen.
   */
  readonly presentationOnly: boolean;
}

// ── Comparability ──────────────────────────────────────────────────────────

/**
 * Whether these two rows may be diffed at all.
 *
 * `parent_mismatch` is the interesting one, and it REFUSES: `version.parent_version`
 * names a commit, the payload supplied a different one, and a diff between them would
 * be a picture of an edit that never happened. The surface renders the refusal instead
 * of the diff. That is the same shape as the product's central move — a precondition
 * that is checked before the thing is shown, not a warning underneath it.
 */
export type Comparability =
  | { readonly kind: 'comparable'; readonly parentCommit: string }
  | { readonly kind: 'origin_version' }
  | { readonly kind: 'parent_unresolved'; readonly named: string }
  | {
      readonly kind: 'parent_mismatch';
      readonly named: string | null;
      readonly supplied: string;
    };

// ── Findings ───────────────────────────────────────────────────────────────

export type FindingCode =
  | 'parent_mismatch'
  | 'parent_unresolved'
  | 'clause_uuid_disagrees'
  | 'generation_not_increasing'
  | 'verdict_disagrees_with_column'
  | 'basis_disagrees_with_column'
  | 'witness_guard_expectation'
  | 'minimality_unestablished'
  | 'witness_names_unchanged_field'
  | 'witness_field_unresolvable'
  | 'blood_size_decreased'
  | 'severity_decreased'
  | 'text_identical_under_non_restate';

/**
 * `discrepancy` — two things in this payload contradict each other, or contradict a
 *                 rule some named artefact in this repository states. It is rendered in
 *                 the refusal accent and it is never hidden behind a disclosure.
 * `observation` — something a reader should see and decide about. Not a contradiction.
 *
 * There is no `info` and no `warning`. Two levels means every finding has been
 * classified by somebody; three means the middle one is where the awkward ones go.
 */
export type FindingLevel = 'discrepancy' | 'observation';

export interface Finding {
  readonly code: FindingCode;
  readonly level: FindingLevel;
  /** One line, sentence case. Console prose — rendered in the sans face. */
  readonly title: string;
  /** The specifics, including the two values that disagree. Console prose. */
  readonly detail: string;
  /**
   * WHAT MAKES THIS A FINDING — a file, a section, or a database object by name.
   * A finding with no authority is an opinion, and this console does not have those.
   */
  readonly authority: string;
}

// ── Witnesses ──────────────────────────────────────────────────────────────

/**
 * Three states, and the difference between the last two is the whole point.
 *
 * `present`       — the payload carries witness rows.
 * `asserted_none` — `witnesses: []`. The emitter says there are none. A CLAIM.
 * `unavailable`   — `witnesses: null`. The payload carries no witness rows and the
 *                   emitter said nothing about whether any exist. NOT a claim.
 *
 * `contracts/clause.schema.json` spells this out on `$defs.delta_verdict`, and
 * `docs/leads/ui.md` §4 requires the console to render the third as an explicit
 * WITNESS UNAVAILABLE state and never as an inferred explanation.
 */
export type WitnessAvailability = 'present' | 'asserted_none' | 'unavailable';

export type WitnessTargetKind = 'text' | 'anchor_set' | 'cat' | 'column' | 'unresolved';

export interface WitnessTarget {
  readonly kind: WitnessTargetKind;
  /** RFC 6901 pointer into `cat_json`, for `kind === 'cat'`. Null otherwise. */
  readonly pointer: string | null;
  /** The `clause_version` column, for `kind === 'column'`. Null otherwise. */
  readonly column: string | null;
}

/**
 * `bound`               — the witness names something this diff observed changing.
 * `no_observed_change`  — the witness names a field that did NOT change between these
 *                         two rows. The witness is still rendered verbatim; what is
 *                         reported is that the console could not corroborate it.
 * `unresolvable_field`  — the console does not know what `field` refers to. It renders
 *                         the string as given and attaches nothing. Guessing here would
 *                         be the console inventing a reason, which is the one thing it
 *                         may never do.
 * `uncorroborable`      — there is no comparable ancestor in this payload, so the
 *                         console observed NOTHING and has no basis for either of the
 *                         two verdicts above. Distinct from `no_observed_change` on
 *                         purpose: "I looked and the field was unchanged" and "I could
 *                         not look" are different statements about a witness, and only
 *                         one of them is evidence against it.
 */
export type WitnessBindState =
  | 'bound'
  | 'no_observed_change'
  | 'unresolvable_field'
  | 'uncorroborable';

export interface BoundWitness {
  /** The row, verbatim. Never edited, never re-ordered internally, never summarised. */
  readonly witness: DeltaWitness;
  readonly target: WitnessTarget;
  readonly state: WitnessBindState;
  /**
   * CONSOLE PROSE about the binding — never about the delta. Rendered in the sans face
   * so that it cannot be mistaken for `witness.note`, which is the database's words.
   */
  readonly bindingNote: string;
}

export interface WitnessBinding {
  readonly availability: WitnessAvailability;
  readonly witnesses: readonly BoundWitness[];
  /** `delta.minimal`: true, false, or null when the emitter did not establish it. */
  readonly minimal: boolean | null;
}

/**
 * A change this browser observed for which no witness row accounts.
 *
 * The console states the change and stops. It does not say what the change means, it
 * does not rank it, and it does not call it suspicious — an unwitnessed change may be
 * entirely innocent. What it may not be is invisible.
 */
export interface UnwitnessedChange {
  readonly kind: 'text' | 'anchor_dropped' | 'anchor_added' | 'cat' | 'column';
  /** The thing that changed, named the way the schema names it. Rendered mono. */
  readonly subject: string;
  /** The observation, in console prose. Never a reason. */
  readonly detail: string;
}

// ── The whole model ────────────────────────────────────────────────────────

export interface ClauseDiffInput {
  readonly clauseUuid: string;
  readonly version: ClauseVersion;
  readonly parent: ClauseVersion | null;
  readonly delta: {
    readonly delta: ControlDelta;
    readonly basis: DeltaBasis;
    readonly witnesses: readonly DeltaWitness[] | null;
    readonly minimal: boolean | null;
  };
}

export interface ClauseDiffModel {
  readonly clauseUuid: string;
  readonly versionCommit: string;
  readonly parentCommit: string | null;
  readonly comparability: Comparability;
  /** The verdict as the DELTA CONTRACT states it — never as the console interprets it. */
  readonly verdict: {
    readonly delta: ControlDelta;
    readonly basis: DeltaBasis;
    /** `delta_model`, when the basis involved one. Null otherwise. */
    readonly model: string | null;
    readonly promptVersion: string | null;
    /** `clause_version.control_delta`, the column, for comparison with the verdict. */
    readonly column: ControlDelta;
    readonly columnBasis: DeltaBasis;
  };
  /**
   * The two column values, verbatim.
   *
   * Carried on the model so the panel can render the COLUMN beside the DERIVATION: the
   * verbatim wells wear a `db:column` chip and are the thing a reader copies; the unified
   * diff wears `recomputed` and is the thing this browser worked out. Keeping both on
   * screen is what makes the badge distinction checkable rather than decorative.
   */
  readonly canonText: {
    readonly parent: string | null;
    readonly version: string;
  };
  /** Null exactly when `comparability.kind !== 'comparable'`. */
  readonly text: TextDiff | null;
  /** Null exactly when `comparability.kind !== 'comparable'`. */
  readonly anchors: AnchorResidue | null;
  /** Null exactly when `comparability.kind !== 'comparable'`. */
  readonly cat: CatDiff | null;
  /** Empty exactly when `comparability.kind !== 'comparable'`. */
  readonly scalars: readonly ScalarChange[];
  readonly witnesses: WitnessBinding;
  readonly unwitnessed: readonly UnwitnessedChange[];
  readonly findings: readonly Finding[];
  /** Severity as the columns report it. Rendered; never derived from anything here. */
  readonly severity: {
    readonly versionSevMax: number;
    readonly parentSevMax: number | null;
    readonly versionBloodSize: number | null;
    readonly parentBloodSize: number | null;
  };
}

/** Re-exported so a consumer needs one import for the whole vocabulary. */
export type { ClauseVersion, ControlDelta, DeltaBasis, DeltaWitness, JsonValue };
