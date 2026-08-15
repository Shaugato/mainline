// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The gate screen's view model — pure functions over payloads, and NOTHING ELSE.
 *
 * ── WHAT THIS MODULE MAY NOT DO ──────────────────────────────────────────────────
 *
 * `docs/leads/ui.md` D5: the console never computes a gate condition. Nothing here
 * evaluates a CHECK predicate, decides whether a merge should have been refused, bands a
 * severity into a virulence class, or derives a counter from rows. Every gate-relevant
 * number on the screen is a value the database wrote, carried through this module
 * unchanged. If this file could compute `open_blocking`, the flagship claim would be
 * launderable in TypeScript — P2, one hop downstream.
 *
 * What it DOES do is classify what the payload CARRIES, which is a different question
 * and is the one the screen has to answer honestly:
 *
 *   • is there a refusal at all, or has nothing been attempted?  (`readRefusal`)
 *   • for each named CHECK, which projected counters does it read, and does this
 *     payload carry anything that establishes what a zero MEANS?  (`buildWeld`)
 *   • does a precursor carry a re-verifiable verbatim anchor, or only an
 *     accusation?  (`anchorStrength` — M11: gist may accuse, only verbatim may acquit)
 *   • what changed between two clause versions, textually?  (`anchorDelta`, `catDelta`)
 *
 * The last pair are the only derivations in this file, they are string-set and
 * object-path differences over two payload fields, they are labelled on screen as
 * computed in the browser, and they gate nothing.
 */

import type {
  AncestryResponse,
  BlameEdge,
  BlockingCheck,
  ClauseResponse,
  CommitLink,
  DeltaWitness,
  EvidenceItem,
  GateConstraint,
  JsonObject,
  JsonValue,
  MusAtom,
  Naa,
  Permit,
  PrecursorEvent,
  RefusalPayload,
} from '../../data/types.generated';

// ── Response slices, named ─────────────────────────────────────────────────

export type AncestryData = AncestryResponse['data'];
export type ClauseData = ClauseResponse['data'];

export interface BlockingChecksData {
  readonly subject_kind: string;
  readonly subject_id: string;
  readonly gate_epoch: number;
  readonly checks: readonly BlockingCheck[];
}

// ── The refusal, narrowed ──────────────────────────────────────────────────

/**
 * Reading a refusal out of an `unknown`.
 *
 * The transport has ALREADY validated the whole invoke envelope — including this object
 * — against `contracts/refusal.schema.json`, which is a verbatim copy of
 * `spec/wire/refusal.schema.json`. So this is a NARROWING, not a second validation, and
 * it is written as one: it checks exactly the fields the screen dereferences and it
 * refuses rather than guessing when one is missing.
 *
 * `spec/wire/refusal.md` C-5 — a consumer MUST NOT synthesise a payload for an outcome
 * the database did not produce. `notARefusal` is how that rule shows up in pixels: the
 * screen renders a defect notice naming the missing field, never a plausible refusal.
 */
export type RefusalRead =
  | { readonly ok: true; readonly refusal: RefusalPayload }
  | { readonly ok: false; readonly reason: string };

const REQUIRED_REFUSAL_FIELDS = [
  'spec_version',
  'refusal_id',
  'observed_at',
  'class',
  'sqlstate',
  'constraint',
  'message',
  'subject_kind',
  'subject_id',
  'gate_epoch',
  'diagnosis',
  'probe_calls',
  'mus',
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function readRefusal(value: unknown): RefusalRead {
  if (!isRecord(value)) {
    return {
      ok: false,
      reason: `the refusal slot holds ${value === null ? 'null' : typeof value}, not an object.`,
    };
  }
  const missing = REQUIRED_REFUSAL_FIELDS.filter((field) => value[field] === undefined);
  if (missing.length > 0) {
    return {
      ok: false,
      reason:
        `the payload is missing ${missing.map((field) => `\`${field}\``).join(', ')}, which ` +
        'spec/wire/refusal.md §2 makes required. A refusal this console cannot read verbatim is ' +
        'not a refusal it will render.',
    };
  }
  if (!Array.isArray(value.mus)) {
    return { ok: false, reason: '`mus` is present but is not an array.' };
  }
  if (value.naa === undefined) {
    return {
      ok: false,
      reason:
        '`naa` is absent. spec/wire/refusal.md §2 requires it — `null` is a value here, and an ' +
        'absent key is a different claim from an explicit null.',
    };
  }
  return { ok: true, refusal: value as unknown as RefusalPayload };
}

/**
 * The closed `naa_reason` set and what `spec/wire/refusal.md` §4 says each one MEANS.
 *
 * These glosses are quoted from the specification, and the screen attributes them to it.
 * They are not the console explaining a refusal in its own words (D18) — they are a fact
 * about the RULE, and §4 makes rendering one mandatory for `no_legal_verdict_exists`:
 * "A consumer MUST render it as a statement about the rule, never as a defect."
 */
export const NAA_REASON_GLOSS: Readonly<Record<string, string>> = Object.freeze({
  probe_budget_exhausted: 'the oracle budget ran out before a minimal alternative was found',
  no_legal_verdict_exists:
    'at this ancestral severity the verdict set is empty by design; there is no disposition constructor that clears it',
  requires_human_authority:
    'the alternative exists but requires an authority the requester does not hold; naming it would be advice to impersonate',
  not_computable: 'the refusal is outside the declarative decomposition and probing is unavailable',
});

/** The identifier a MUS atom is addressed by, for the witness cross-reference. */
export function musAtomKey(atom: MusAtom): string {
  switch (atom.kind) {
    case 'obligation':
      return atom.obligation_id;
    case 'clause':
      return atom.clause_id;
    case 'event':
      return atom.event_id;
    case 'authority_gap':
      return atom.relation;
    case 'capability_gap':
      return atom.capability;
  }
}

/** The obligation ids the reason set names, in payload order. */
export function musObligationIds(mus: readonly MusAtom[]): readonly string[] {
  return mus.flatMap((atom) => (atom.kind === 'obligation' ? [atom.obligation_id] : []));
}

/**
 * The minimum-cardinality removal, as a number, when the payload states one.
 *
 * `dispose_obligations` always carries `cardinality`; the other four kinds declare it
 * optional. `null` means the emitter did not state one, and the screen says so instead
 * of counting the array itself — a cardinality the console counted is a claim about
 * minimality that nobody established.
 */
export function naaCardinality(naa: Naa): number | null {
  return naa.cardinality ?? null;
}

// ── Evidentiary typing — M11, the trace floor ──────────────────────────────

/**
 * `verbatim` — the item carries a pointer AND a digest, so a third party can fetch the
 *              bytes and check them without our cooperation.
 * `gist`     — it does not. It may still accuse; it may not acquit.
 *
 * ARCHITECTURE.md §3.3 M11: *gist may accuse, only verbatim may acquit*. This is the one
 * place the console can make that distinction from the payloads it holds, so it makes it
 * loudly, and it never upgrades a gist item by inferring a source for it.
 */
export type AnchorStrength = 'verbatim' | 'gist';

export function precursorAnchor(precursor: PrecursorEvent | null | undefined): AnchorStrength {
  if (precursor === null || precursor === undefined) return 'gist';
  const key = precursor.source_object_key;
  const digest = precursor.source_sha256;
  return typeof key === 'string' && key !== '' && typeof digest === 'string' && digest !== ''
    ? 'verbatim'
    : 'gist';
}

export function evidenceAnchor(item: EvidenceItem): AnchorStrength {
  return typeof item.digest === 'string' && item.digest !== '' ? 'verbatim' : 'gist';
}

// ── The weld diagram ───────────────────────────────────────────────────────

/**
 * Three states, and the third one is the whole point.
 *
 *   `blocking`         — the counter is non-zero. The gate is welded shut by this one.
 *   `clear`            — the counter is zero AND this payload carries the rows or the
 *                        certificate that say what was examined to get there.
 *   `unwitnessed-zero` — the counter is zero and NOTHING on this screen establishes what
 *                        was examined. A zero nobody can account for must not look like a
 *                        zero somebody checked.
 *
 * `unmodelled_asset_count` is the sharp case (ARCHITECTURE.md §5.5, finding S11): an
 * asset with no modelled energy edges is UNKNOWN, not SAFE. With no boundary certificate
 * in the payload, a zero there means nobody has counted the unmodelled tags — and the
 * row says UNKNOWN BLOCKS rather than showing a reassuring nought.
 */
export type CounterState = 'blocking' | 'clear' | 'unwitnessed-zero';

/** Where the rows behind a counter live, when this screen holds them at all. */
export type WitnessSource = 'blocking_check' | 'boundary_certificate' | 'not_carried';

export interface WeldCounter {
  /** The projected column, spelled as the DDL spells it. */
  readonly column: string;
  /** The value the database wrote. Never computed here. */
  readonly value: number;
  readonly state: CounterState;
  readonly witnessSource: WitnessSource;
  /** How many witness rows this payload set carries, or `null` when it carries none. */
  readonly witnessCount: number | null;
  /**
   * S11. True only for `unmodelled_asset_count` with no boundary certificate: the zero
   * is an absence of counting, and an uncounted asset graph blocks.
   */
  readonly unknownBlocks: boolean;
}

export interface WeldRow {
  /** The CONSTRAINT name, verbatim. The name is the exhibit. */
  readonly constraint: string;
  /** The CHECK expression as the catalog reported it, or null. Never reconstructed. */
  readonly predicate: string | null;
  /** True exactly when the refusal payload on this screen names this constraint. */
  readonly blamedByRefusal: boolean;
  readonly counters: readonly WeldCounter[];
}

export interface WeldDiagramModel {
  readonly rows: readonly WeldRow[];
  /**
   * Projected columns present on the permit that NO constraint in this payload reads.
   * An unread counter is not an error — `countersigned_count` is read jointly with
   * `unmet_floor_count` — but a counter nobody reads and nobody mentions is a hole, and
   * the screen names it rather than dropping it.
   */
  readonly unreadColumns: readonly string[];
  /** True when the payload declared no constraints at all. */
  readonly empty: boolean;
}

const UNMODELLED = 'unmodelled_asset_count';
const OPEN_BLOCKING = 'open_blocking';

export interface WeldInput {
  readonly permit: Permit;
  /** The blocking checks this screen holds, or `null` when that read has not landed. */
  readonly checks: readonly BlockingCheck[] | null;
  /** The constraint the refusal named, or `null` when nothing has been refused. */
  readonly blamedConstraint: string | null;
}

function counterFor(input: WeldInput, entry: GateConstraint['counters'][number]): WeldCounter {
  const { permit, checks } = input;
  const value = entry.value;

  if (entry.column === OPEN_BLOCKING) {
    const open = checks === null ? null : checks.filter((check) => check.open).length;
    return {
      column: entry.column,
      value,
      state: value > 0 ? 'blocking' : open === null ? 'unwitnessed-zero' : 'clear',
      witnessSource: open === null ? 'not_carried' : 'blocking_check',
      witnessCount: open,
      unknownBlocks: false,
    };
  }

  if (entry.column === UNMODELLED) {
    const certificate = permit.boundary_certificate ?? null;
    if (value > 0) {
      return {
        column: entry.column,
        value,
        state: 'blocking',
        witnessSource: certificate === null ? 'not_carried' : 'boundary_certificate',
        witnessCount:
          certificate === null ? null : certificate.tags_unmodelled + certificate.under_declared,
        unknownBlocks: false,
      };
    }
    return {
      column: entry.column,
      value,
      state: certificate === null ? 'unwitnessed-zero' : 'clear',
      witnessSource: certificate === null ? 'not_carried' : 'boundary_certificate',
      witnessCount:
        certificate === null ? null : certificate.tags_unmodelled + certificate.under_declared,
      // S11 — an uncounted asset graph is UNKNOWN, and unknown blocks.
      unknownBlocks: certificate === null,
    };
  }

  return {
    column: entry.column,
    value,
    state: value > 0 ? 'blocking' : 'unwitnessed-zero',
    witnessSource: 'not_carried',
    witnessCount: null,
    unknownBlocks: false,
  };
}

export function buildWeld(input: WeldInput): WeldDiagramModel {
  const rows: WeldRow[] = input.permit.constraints.map((constraint) => ({
    constraint: constraint.constraint,
    predicate: constraint.predicate ?? null,
    // The payload's own flag OR a string comparison against the refusal actually on
    // screen. Never an evaluation of the predicate.
    blamedByRefusal:
      constraint.blamed_by_refusal || constraint.constraint === input.blamedConstraint,
    counters: constraint.counters.map((entry) => counterFor(input, entry)),
  }));

  const read = new Set(rows.flatMap((row) => row.counters.map((counter) => counter.column)));
  const unreadColumns = Object.keys(input.permit.counters).filter((column) => !read.has(column));

  return { rows, unreadColumns, empty: rows.length === 0 };
}

// ── Clause diff derivations ────────────────────────────────────────────────

export interface AnchorDelta {
  readonly kept: readonly string[];
  readonly added: readonly string[];
  readonly removed: readonly string[];
}

/**
 * Set difference over `clause_version.anchor_set`.
 *
 * COMPUTED IN THIS BROWSER, and the panel says so beside it. An anchor dropped between
 * versions is one of the residue reasons the identity cascade uses, but the *decision*
 * lives in the database: this is a reading aid over two arrays of strings and it gates
 * nothing.
 */
export function anchorDelta(
  parent: readonly string[] | null,
  child: readonly string[],
): AnchorDelta {
  if (parent === null) return { kept: [], added: [...child], removed: [] };
  const before = new Set(parent);
  const after = new Set(child);
  return {
    kept: [...child].filter((anchor) => before.has(anchor)),
    added: [...child].filter((anchor) => !before.has(anchor)),
    removed: [...parent].filter((anchor) => !after.has(anchor)),
  };
}

export type CatChangeKind = 'added' | 'removed' | 'changed';

export interface CatChange {
  /** Dotted path into the Control Assertion Tuple, e.g. `quantity.value`. */
  readonly path: string;
  readonly from: string | null;
  readonly to: string | null;
  readonly kind: CatChangeKind;
}

function flattenCat(value: JsonValue, prefix: string, out: Map<string, string>): void {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    // `Array.isArray` above has excluded the array arm, but TypeScript does not narrow
    // a readonly-array union through it, so the shape is restated rather than inferred.
    const record = value as Readonly<Record<string, JsonValue>>;
    for (const key of Object.keys(record).sort()) {
      const child = record[key];
      if (child === undefined) continue;
      flattenCat(child, prefix === '' ? key : `${prefix}.${key}`, out);
    }
    return;
  }
  out.set(prefix, JSON.stringify(value) ?? 'null');
}

/**
 * Flat-path comparison of two CAT tuples.
 *
 * The tuple's SHAPE is owned by the algorithms domain and this console asserts nothing
 * about its internals — which is exactly why the comparison is generic: every leaf path
 * present in either side is reported, and no key is special-cased. A console that knew
 * which CAT fields mattered would be a console with an opinion about the lattice.
 */
export function catDelta(
  parent: JsonObject | null | undefined,
  child: JsonObject | null | undefined,
): readonly CatChange[] {
  const before = new Map<string, string>();
  const after = new Map<string, string>();
  if (parent !== null && parent !== undefined) flattenCat(parent, '', before);
  if (child !== null && child !== undefined) flattenCat(child, '', after);

  const paths = [...new Set([...before.keys(), ...after.keys()])].sort();
  const changes: CatChange[] = [];
  for (const path of paths) {
    const from = before.get(path) ?? null;
    const to = after.get(path) ?? null;
    if (from === to) continue;
    changes.push({
      path,
      from,
      to,
      kind: from === null ? 'added' : to === null ? 'removed' : 'changed',
    });
  }
  return changes;
}

/**
 * `null` witnesses and an EMPTY witness array are DIFFERENT CLAIMS.
 *
 * `null`  — the payload carries no witness rows. The panel renders WITNESS UNAVAILABLE
 *           and infers nothing. (ui.md §4: never an inferred explanation.)
 * `[]`    — the emitter states there are none. That is an assertion, and it is rendered
 *           as one.
 *
 * The algorithms domain's `fn_delta_witness_guard` refuses a weaken/remove verdict with
 * `delta_basis='lattice'` whose witnesses were not written in the same transaction
 * (P0001), so a `null` here on a weaken is itself a finding — but that is the database's
 * judgement to make, not this module's, so the panel reports the absence and stops.
 */
export type WitnessState = 'rows' | 'asserted-none' | 'unavailable';

export function witnessState(witnesses: readonly DeltaWitness[] | null): WitnessState {
  if (witnesses === null) return 'unavailable';
  return witnesses.length === 0 ? 'asserted-none' : 'rows';
}

// ── Clause origin, from the ancestry payload ───────────────────────────────

export interface ClauseOrigin {
  /** The commit that INTRODUCED the clause, when the commit chain carries one. */
  readonly introducing: CommitLink | null;
  /** The blame edge tying the named precursor event to this clause, when present. */
  readonly blame: BlameEdge | null;
}

/**
 * What wrote the clause, taken from the ancestry payload and from nowhere else.
 *
 * The read model carries NO commit message column — `commit_obj` is not exposed through
 * `contracts/ancestry.schema.json` — so the console does not render one. What it has,
 * and renders, is the introducing commit (the `control_delta='introduce'` link in the
 * chain, with its date and printed label) and the blame edge's `attribution`, which is
 * the prose the database holds for a human to read. When the ancestry payload is absent
 * the screen says the origin is not carried, rather than reaching for a plausible
 * sentence.
 */
export function clauseOrigin(
  ancestry: AncestryData | null,
  precursorEventId: string | null,
): ClauseOrigin {
  if (ancestry === null) return { introducing: null, blame: null };
  const introducing =
    ancestry.commit_chain.find((link) => link.control_delta === 'introduce') ?? null;
  const blame =
    precursorEventId === null
      ? null
      : (ancestry.blame_edges.find((edge) => edge.event_id === precursorEventId) ?? null);
  return { introducing, blame };
}

// ── Choosing the clause the diff panel shows ───────────────────────────────

export type DiffSelection = 'named-by-reason-set' | 'first-open-check' | 'none';

export interface DiffSubject {
  readonly selection: DiffSelection;
  readonly check: BlockingCheck | null;
}

/**
 * Which clause the diff panel is about.
 *
 * Preference order, and the order is the argument:
 *
 *   1. the check the REFUSAL's minimal unsatisfiable subset names — the clause diff that
 *      armed the check that welded the gate. This is the one the screen exists for.
 *   2. failing that, the first still-open blocking check. Before an attempt has been made
 *      there is no reason set, and showing the open obligation's clause is honest as long
 *      as the panel says which rule picked it.
 *   3. failing that, nothing — and the panel says nothing rather than picking a clause.
 */
export function chooseDiffSubject(
  checks: readonly BlockingCheck[] | null,
  refusal: RefusalPayload | null,
): DiffSubject {
  if (checks === null || checks.length === 0) return { selection: 'none', check: null };

  if (refusal !== null) {
    const named = new Set(musObligationIds(refusal.mus));
    const match = checks.find((check) => named.has(check.check_id));
    if (match !== undefined) return { selection: 'named-by-reason-set', check: match };
  }

  const open = checks.find((check) => check.open);
  if (open !== undefined) return { selection: 'first-open-check', check: open };

  return { selection: 'none', check: null };
}

/** The witness rows behind `open_blocking`, in payload order. */
export function openChecks(checks: readonly BlockingCheck[] | null): readonly BlockingCheck[] {
  return checks === null ? [] : checks.filter((check) => check.open);
}

// ── The plain-language band ────────────────────────────────────────────────

/**
 * THE HEADINGS, AFTER R7.
 *
 * `docs/leads/two-audience-ux-plan.md` R7 overrules two console-composed headings because
 * they are console jargon rather than kernel vocabulary, and nothing verbatim is lost by
 * changing them: *"The weld"* becomes *"What the database checks before it will merge"*,
 * and *"Irreducible reason set"* becomes *"Why it refused — the smallest set of
 * reasons"*. The word **weld** survives as the section's FULL-DETAIL subtitle and in the
 * source comments — the diagram is still the weld, and the file still calls it that — and
 * `mus` in the payload is untouched.
 *
 * They are constants rather than literals in three components so that a rename cannot
 * half-land, and so `tests/unit/gate/plain.test.tsx` can assert the rendered heading is
 * the ruled one.
 */
export const WELD_TITLE = 'What the database checks before it will merge';
export const WELD_SUBTITLE = 'the weld — every projected counter under the CHECK that reads it';
export const REASON_SET_TITLE = 'Why it refused — the smallest set of reasons';

/** A verbatim quotation of the database's own prose, with the member it was read from. */
export interface PlainQuote {
  /** What the reader is about to read, in the reader's words. Console prose. */
  readonly label: string;
  /** The database's text, VERBATIM. Never re-worded, never truncated (D18). */
  readonly text: string;
  /** The payload member it came from, so the quotation can be checked. */
  readonly field: string;
}

export interface PlainBandModel {
  readonly heading: string;
  /** At most three. Every clause points at a field named in {@link PlainBandModel.basis}. */
  readonly sentences: readonly string[];
  /**
   * The demonstration seed's own SYNTHETIC marker, verbatim, or `null` when no payload on
   * this screen carries one.
   */
  readonly marker: string | null;
  readonly markerField: string | null;
  readonly quotes: readonly PlainQuote[];
  /** The members the sentences were built from, in order, for the FULL-DETAIL source line. */
  readonly basis: readonly string[];
}

export interface PlainBandInput {
  readonly permitId: string;
  readonly permit: Permit | null;
  readonly checks: readonly BlockingCheck[] | null;
  readonly ancestry: AncestryData | null;
}

/**
 * The seed's own disclosure prefix.
 *
 * `db/seeds/demo/demo_world.sql` §preamble states the rule this reads:
 * *"free text opens with `SYNTHETIC —` (title, narrative, message, attribution)"*. So the
 * marker is a property of the TEXT the database returned, and finding it is a check over
 * that text — not a code branch, not a deployment assumption, and not something the
 * console may supply when the text does not carry it. R5: where the seed's own text
 * already starts `SYNTHETIC —`, render it verbatim and do not re-word it.
 */
const SYNTHETIC_PREFIX = 'SYNTHETIC';

function carriesSyntheticMarker(text: string | null | undefined): text is string {
  return typeof text === 'string' && text.trimStart().startsWith(SYNTHETIC_PREFIX);
}

/** Every text on this screen that could carry the seed's marker, with its member path. */
function markerCandidates(input: PlainBandInput): readonly PlainQuote[] {
  const found: PlainQuote[] = [];

  (input.checks ?? []).forEach((check, index) => {
    const title = check.precursor?.title ?? null;
    if (carriesSyntheticMarker(title)) {
      found.push({
        label: 'What the record says happened',
        text: title,
        field: `blocking_checks.checks[${index}].precursor.title`,
      });
    }
  });

  (input.ancestry?.blame_edges ?? []).forEach((edge, index) => {
    const attribution = edge.attribution ?? null;
    if (carriesSyntheticMarker(attribution)) {
      found.push({
        label: 'Why this rule is the one this permit relies on',
        text: attribution,
        field: `clause_ancestry.blame_edges[${index}].attribution`,
      });
    }
  });

  return found;
}

/**
 * The three sentences a first-time reader meets, and the marker above them.
 *
 * **Every clause points at a field.** R7's test for an added sentence is *can I point at
 * the field it came from?* — so the count comes off `permit.counters.open_blocking` and
 * nowhere else, the subject line comes off `permit.external_ref`, and the quotations are
 * the database's own prose rendered verbatim. Nothing here evaluates a predicate, decides
 * whether a merge should have been refused, or predicts what the control will do (D5).
 *
 * The permit-absent branch is not a fallback. It states which nothing this is — the read
 * has not landed — and it deliberately shows no count rather than a zero, because a zero
 * nobody read is the reassuring default this console refuses everywhere else.
 */
export function plainGateBand(input: PlainBandInput): PlainBandModel {
  const { permit, permitId } = input;
  const subject = permit === null ? permitId : permit.external_ref;
  const basis: string[] = [permit === null ? 'no permit payload' : 'permit.external_ref'];

  const sentences: string[] = [
    `A permit is a written authorisation for one specific piece of work, and this screen is ` +
      `about one of them: ${subject}.`,
  ];

  if (permit === null) {
    sentences.push(
      'An obligation is something that must be answered before that authorisation is allowed to ' +
        'take effect; the permit read has not landed on this screen, so no count is shown here ' +
        'rather than a zero.',
    );
    basis.push('no permit payload');
  } else {
    const open = permit.counters.open_blocking;
    sentences.push(
      'An obligation is something that must be answered before that authorisation is allowed to ' +
        `take effect, and the database keeps a running total of them in a column: it reads ` +
        `${open} still open against this permit.`,
    );
    basis.push('permit.counters.open_blocking');
  }

  sentences.push(
    'Nothing under this band is the console’s wording: press the one control on this screen and ' +
      'the database either refuses the merge and prints the name of the rule it broke, or it ' +
      'commits — and whichever it does is what you will read below.',
  );
  basis.push('POST /v1/permits/{permit_id}/merge');

  const quotes = markerCandidates(input);
  const first = quotes[0] ?? null;

  return {
    heading: 'What this screen is about',
    sentences,
    marker: first === null ? null : first.text,
    markerField: first === null ? null : first.field,
    quotes,
    basis,
  };
}

/** Formats an RFC 3339 instant as a UTC date, with the instant kept verbatim beside it. */
export function utcDate(instant: string): string {
  const parsed = Date.parse(instant);
  if (Number.isNaN(parsed)) return instant;
  return new Intl.DateTimeFormat('en-AU', {
    timeZone: 'UTC',
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  }).format(parsed);
}
