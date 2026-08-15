// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE VOCABULARY LAW — the single source of truth for `docs/leads/two-audience-ux-plan.md`
 * ruling R7.
 *
 * Shaped exactly like `registers.ts`: a law expressed as frozen data, with zero imports,
 * pure functions, and a companion `glossary.doc.ts` that renders `docs/console/vocabulary.md`
 * from it. `tests/unit/design/glossary.test.ts` asserts the document is byte-identical to
 * the renderer, the way `doc-generated.test.ts` already holds `visual-language.md` to
 * `registers.doc.ts` and `accessibility.md` to `contract.doc.ts`.
 *
 * ── WHAT THIS FILE IS FOR ────────────────────────────────────────────────────────
 *
 * The lead counted the terms a first-time reader meets on the shipped screens **before
 * anything defines them**: twenty-one (plan §0.4). None of them is wrong and all
 * twenty-one stay. What changes is what a reader meets FIRST.
 *
 * So this is an ON-RAMP, never a dumbing-down. Two collections, and the distinction
 * between them is the whole design:
 *
 *   PRODUCT WORDS  the nine words the console says in its own PROSE. Each carries one
 *                  plain sentence and — this is the part that keeps it honest — the exact
 *                  database thing it names, so a reader who wants to check the sentence
 *                  knows which table or endpoint to open.
 *
 *   GLOSSED TERMS  the eighteen terms that are NEVER replaced and always defined on first
 *                  use. `minimal unsatisfiable subset` stays `minimal unsatisfiable
 *                  subset`; it simply gains a sentence beside it.
 *
 * ── THE SENTENCES ARE NOT MINE TO EDIT ───────────────────────────────────────────
 *
 * Every `sentence` and every `gloss` below is copied VERBATIM from ruling R7, which is
 * normative. A worker who finds one of them clumsy raises it with the lead; a worker who
 * rewrites one here has moved the vocabulary out of the one place it is allowed to live.
 * `glossary.test.ts` pins the count of each collection so an entry cannot be dropped
 * quietly, and pins the two collections' keys so one cannot be renamed into another.
 *
 * ── CONSTRAINTS ON THIS FILE ─────────────────────────────────────────────────────
 *
 * Zero imports, data and pure functions only, for the same two mechanical reasons
 * `registers.ts` gives: `tsconfig.json` sets `erasableSyntaxOnly` (so the key sets are
 * frozen tuples plus union types, never a TypeScript `enum`), and this module is
 * statically reachable from the evidentiary shell, whose gzip closure `budgets.json` caps
 * at 225 280 bytes with `required: true`. Prose is cheap to carry and expensive to carry
 * twice — the Markdown renderer lives in `glossary.doc.ts` and is imported by the test
 * alone, so the shipped console pays for the sentences and not for the tables.
 *
 * ── THE MARKETING GATE ───────────────────────────────────────────────────────────
 *
 * R7 forbids twelve words in any sentence a worker writes, and `forbiddenWordsIn()` below
 * is that rule as a function so the test can run it over every string this file carries
 * rather than over the ones somebody remembered to check.
 */

// ── The words the console says in its own prose ──────────────────────────────────

/**
 * The nine product words, in the order R7's table lists them.
 *
 * The order is not decorative: `vocabulary.md` renders in this order and a reader who has
 * been sent the document reads `permit` before `obligation` before `refusal`, which is the
 * order the gate screen puts them in.
 */
export const PRODUCT_WORD_KEYS = [
  'permit',
  'obligation',
  'refusal',
  'signature',
  'ancestry',
  'custody',
  'silence',
  'propagation',
  'synthetic',
] as const;

export type ProductWordKey = (typeof PRODUCT_WORD_KEYS)[number];

export interface ProductWord {
  /** The key, and the word itself as it appears in prose. */
  readonly key: ProductWordKey;
  /** R7's one plain sentence, verbatim. */
  readonly sentence: string;
  /**
   * The exact database thing the word names — a table, a pair of tables, an endpoint, or
   * the seed's own marker.
   *
   * This is the field that stops the plain sentence becoming a claim nobody can check.
   * `refusal` is a nice word; `a 23514/P0001 error` is where a reader goes to find out
   * whether the nice word was earned.
   */
  readonly names: string;
}

export const PRODUCT_WORDS: readonly ProductWord[] = Object.freeze([
  Object.freeze({
    key: 'permit',
    sentence: 'A written authorisation for one specific piece of work.',
    names: 'mainline.permit',
  }),
  Object.freeze({
    key: 'obligation',
    sentence: 'Something that must be answered before the permit is allowed to take effect.',
    names: 'mainline.blocking_check',
  }),
  Object.freeze({
    key: 'refusal',
    sentence:
      'The database declining to make the change, and printing its own named reason for it.',
    names: 'a 23514/P0001 error',
  }),
  Object.freeze({
    key: 'signature',
    sentence:
      'One named person recording, under their own credential, how an obligation was answered.',
    names: 'mainline.disposition',
  }),
  Object.freeze({
    key: 'ancestry',
    sentence: 'The trail from this rule back through the earlier events and edits it came from.',
    names: 'clause_blame_closure + commit_chain',
  }),
  Object.freeze({
    key: 'custody',
    sentence: 'Proof that a record has not been altered since it was written down.',
    names: 'the ledger + checkpoint',
  }),
  Object.freeze({
    key: 'silence',
    sentence:
      'Everything the search looked at and decided not to show you — and the arithmetic for why.',
    names: '/v1/permits/{id}/silence',
  }),
  Object.freeze({
    key: 'propagation',
    sentence: 'Where else the same lesson was applied, and where it was not.',
    names: '/v1/lessons/{id}/propagation',
  }),
  Object.freeze({
    key: 'synthetic',
    sentence: 'Made up for this demonstration; corresponds to no real person, site or event.',
    names: "the seed's own marker",
  }),
]);

// ── The terms that stay, and gain a definition ───────────────────────────────────

/**
 * The eighteen glossed terms, in R7's order.
 *
 * A key is a slug; a `label` is how the term is SPELLED on screen. The two differ where
 * the term has two names a reader will meet (`projection / projected counter`) or a
 * casing that carries meaning (`STAGED`, `SQLSTATE`). Never derive one from the other:
 * `virulence` slugged from `virulence / severity` would be a third spelling nobody chose.
 */
export const GLOSSED_TERM_KEYS = [
  'projection',
  'projection-drift',
  'sqlstate',
  'constraint',
  'gate-epoch',
  'canonicalisation',
  'inclusion-proof',
  'consistency-proof',
  'corpus-root',
  'clock-skew',
  'minimal-unsatisfiable-subset',
  'nearest-admissible-alternative',
  'defeater',
  'virulence',
  'provenance-chip',
  'staged',
  'transport',
  'seal',
] as const;

export type GlossedTermKey = (typeof GLOSSED_TERM_KEYS)[number];

export interface GlossedTerm {
  readonly key: GlossedTermKey;
  /** How the term is spelled on screen. Rendered verbatim; never re-cased. */
  readonly label: string;
  /** R7's first-use gloss, verbatim. */
  readonly gloss: string;
}

export const GLOSSED_TERMS: readonly GlossedTerm[] = Object.freeze([
  Object.freeze({
    key: 'projection',
    label: 'projection / projected counter',
    gloss:
      'A running total the database keeps in a column so a check can be instant instead of re-counting.',
  }),
  Object.freeze({
    key: 'projection-drift',
    label: 'projection drift',
    gloss:
      'When that running total stops matching what the rows actually say — by accident, or on purpose.',
  }),
  Object.freeze({
    key: 'sqlstate',
    label: 'SQLSTATE',
    gloss:
      'The five-character code the database prints to name what it refused. 23514 means a CHECK constraint was not satisfied.',
  }),
  Object.freeze({
    key: 'constraint',
    label: 'constraint',
    gloss: 'A rule written into the table itself, so no query can get around it.',
  }),
  Object.freeze({
    key: 'gate-epoch',
    label: 'gate epoch',
    gloss:
      'A version number for the set of obligations; it moves when they change, so an old signature cannot be reused across the change.',
  }),
  Object.freeze({
    key: 'canonicalisation',
    label: 'canonicalisation',
    gloss:
      'Writing a record in one exact byte-for-byte form, so two different computers hashing it get the same answer. (RFC 8785)',
  }),
  Object.freeze({
    key: 'inclusion-proof',
    label: 'inclusion proof',
    gloss:
      'A short list of hashes that proves one entry really is in the log, without re-reading the log. (RFC 6962)',
  }),
  Object.freeze({
    key: 'consistency-proof',
    label: 'consistency proof',
    gloss:
      'A short list of hashes that proves the log only ever grew, and no earlier entry was rewritten.',
  }),
  Object.freeze({
    key: 'corpus-root',
    label: 'corpus root',
    gloss:
      "The exact commit of the rule-book that this page's ancestry was worked out against.",
  }),
  Object.freeze({
    key: 'clock-skew',
    label: 'clock skew',
    gloss:
      "The server's clock minus this browser's. A screenshot's timestamp means nothing without it.",
  }),
  Object.freeze({
    key: 'minimal-unsatisfiable-subset',
    label: 'minimal unsatisfiable subset',
    gloss:
      'The smallest set of reasons that is on its own enough to cause the refusal — take any one away and it would not refuse.',
  }),
  Object.freeze({
    key: 'nearest-admissible-alternative',
    label: 'nearest admissible alternative',
    gloss: 'The smallest thing you could actually do that would make this allowed.',
  }),
  Object.freeze({
    key: 'defeater',
    label: 'defeater',
    gloss:
      'The named reason a person is permitted to give for an obligation. The list is fixed per obligation; there is deliberately no general "not applicable".',
  }),
  Object.freeze({
    key: 'virulence',
    label: 'virulence / severity',
    gloss: 'How bad the underlying failure was, on the scale the record itself carries.',
  }),
  Object.freeze({
    key: 'provenance-chip',
    label: 'provenance chip',
    gloss:
      'The little marker saying how the console came to believe the value beside it — read from a column, recomputed here, or never established.',
  }),
  Object.freeze({
    key: 'staged',
    label: 'STAGED',
    gloss:
      'This value came from a fixture, not from the live database, and the badge is there so you never have to wonder.',
  }),
  Object.freeze({
    key: 'transport',
    label: 'transport',
    gloss:
      'Where these bytes came from: LIVE (a database, just now) or REPLAY (a signed bundle, verified in this browser first).',
  }),
  Object.freeze({
    key: 'seal',
    label: 'seal',
    gloss:
      'Whether this browser re-did the arithmetic over the signed bytes and got the same answer.',
  }),
]);

// ── The SQLSTATE map ─────────────────────────────────────────────────────────────

/**
 * What each code the gate path can print MEANS, in one clause.
 *
 * This does not replace `sqlstate.ts`, and the split is deliberate. `sqlstate.ts`
 * CLASSIFIES — it says whether a code is a retry, a refusal, a denial, an admission or
 * outside the taxonomy, which is a fact about `spec/errors.md`. This map GLOSSES — it says
 * what the code names, which is a fact about the SQL standard's condition for that class.
 * Neither one paraphrases a refusal payload: D18 and R8 both say the payload carries its
 * own words, and the gloss goes beside them, never instead of them.
 *
 * The set is the closed gate-path set of `spec/errors.md` §1, plus `42501` (refused before
 * the gate) and `00000` (not an error). A code outside it has no gloss and
 * `sqlstateGloss()` returns `null` rather than inventing one — `Sqlstate.tsx` already
 * announces an unmodelled code as unmodelled, and a made-up sentence beside it would be
 * the console asserting it understood a refusal nobody modelled.
 */
export interface SqlstateGloss {
  /** The code, exactly as the database prints it. Five characters; never normalised. */
  readonly code: string;
  /** What that code names, in one clause, lower case, no full stop. */
  readonly gloss: string;
}

export const SQLSTATE_GLOSSES: readonly SqlstateGloss[] = Object.freeze([
  Object.freeze({
    code: '00000',
    gloss: 'the statement succeeded',
  }),
  Object.freeze({
    code: '23503',
    gloss: 'a foreign key pointed at a row that is not there',
  }),
  Object.freeze({
    code: '23505',
    gloss: 'a unique index already held that value',
  }),
  Object.freeze({
    code: '23514',
    gloss: 'a CHECK constraint written into the table was not satisfied',
  }),
  Object.freeze({
    code: '40001',
    gloss: 'the database could not serialise this transaction against another one, and asks for it to be retried',
  }),
  Object.freeze({
    code: '42501',
    gloss: 'the role was refused by the grant graph before any gate condition was evaluated',
  }),
  Object.freeze({
    code: 'P0001',
    gloss: 'a function raised its own named refusal',
  }),
]);

// ── Lookup ───────────────────────────────────────────────────────────────────────

const PRODUCT_BY_KEY: ReadonlyMap<string, ProductWord> = new Map(
  PRODUCT_WORDS.map((entry) => [entry.key, entry]),
);

const TERM_BY_KEY: ReadonlyMap<string, GlossedTerm> = new Map(
  GLOSSED_TERMS.map((entry) => [entry.key, entry]),
);

const SQLSTATE_BY_CODE: ReadonlyMap<string, SqlstateGloss> = new Map(
  SQLSTATE_GLOSSES.map((entry) => [entry.code, entry]),
);

/** Every key this module answers to, across both collections. */
export type GlossaryKey = ProductWordKey | GlossedTermKey;

/**
 * Overloaded, and the overload is the point.
 *
 * A caller who writes a LITERAL key — `productWord('custody')` — has already been checked
 * by the compiler against `PRODUCT_WORD_KEYS`, so the answer cannot be `null` and the
 * caller must not be made to write `?? ''` for a case that cannot happen. A caller who
 * passes a runtime string gets `null` and has to decide what to do about it.
 *
 * That asymmetry is deliberate: `?? ''` at every call site is exactly the pressure that
 * puts a console-composed fallback where a reader expects a definition, and the whole kit
 * exists to keep that from happening.
 */
export function productWord(key: ProductWordKey): ProductWord;
export function productWord(key: string): ProductWord | null;
export function productWord(key: string): ProductWord | null {
  return PRODUCT_BY_KEY.get(key) ?? null;
}

export function glossedTerm(key: GlossedTermKey): GlossedTerm;
export function glossedTerm(key: string): GlossedTerm | null;
export function glossedTerm(key: string): GlossedTerm | null {
  return TERM_BY_KEY.get(key) ?? null;
}

export function sqlstateGloss(code: string): string | null {
  return SQLSTATE_BY_CODE.get(code)?.gloss ?? null;
}

/**
 * The one sentence for a key, from whichever collection holds it — `null` when nothing
 * does.
 *
 * `null` rather than the key itself, or an empty string, or a cheerful default. A
 * component handed an unknown key must be able to tell that it was handed an unknown key;
 * a fallback that renders the raw slug beside a verbatim value would put console-composed
 * text in the position a reader has been taught to read as a definition.
 */
export function glossFor(key: GlossaryKey): string;
export function glossFor(key: string): string | null;
export function glossFor(key: string): string | null {
  const term = TERM_BY_KEY.get(key);
  if (term !== undefined) return term.gloss;
  return PRODUCT_BY_KEY.get(key)?.sentence ?? null;
}

/** How a key is spelled on screen: a term's label, or a product word's own spelling. */
export function labelFor(key: GlossaryKey): string;
export function labelFor(key: string): string | null;
export function labelFor(key: string): string | null {
  const term = TERM_BY_KEY.get(key);
  if (term !== undefined) return term.label;
  return PRODUCT_BY_KEY.get(key)?.key ?? null;
}

// ── The marketing gate ───────────────────────────────────────────────────────────

/**
 * R7's forbidden list, verbatim, in the order the ruling gives it.
 *
 * Not a style preference. Every one of these is a word that lets a sentence describe an
 * effect on the reader instead of a fact about a field, and the test R7 sets for every
 * added sentence is: *can I point at the field it came from?*
 */
export const FORBIDDEN_WORDS: readonly string[] = Object.freeze([
  'seamless',
  'powerful',
  'robust',
  'enterprise',
  'revolutionary',
  'unlock',
  'empower',
  'leverage',
  'effortless',
  'trust us',
  'simply',
  'just',
]);

/**
 * The one lexical carve-out, written down so it cannot grow silently.
 *
 * R7's own `transport` gloss reads *"LIVE (a database, just now)"*, where `just` is a time
 * reference — the bytes arrived a moment ago — and not the minimiser the ruling bans.
 * The ruling's text is normative and copied verbatim above, so the gate distinguishes the
 * two senses lexically rather than exempting an entry wholesale. `glossary.test.ts`
 * asserts this fires EXACTLY ONCE across the whole vocabulary; a second occurrence is a
 * failure, and the fix is to write the sentence differently rather than to widen this.
 */
const TEMPORAL_JUST = /\bjust now\b/gi;

/**
 * Every forbidden word in `text`, lower-cased, in the order the list declares them.
 *
 * Matched on word boundaries so `justification` is not a hit and `Just` is. `trust us` is
 * two words and is matched as the phrase it is.
 */
export function forbiddenWordsIn(text: string): readonly string[] {
  const scanned = text.replace(TEMPORAL_JUST, ' ');
  const hits: string[] = [];
  for (const word of FORBIDDEN_WORDS) {
    const pattern = new RegExp(`\\b${word.replace(/ /g, '\\s+')}\\b`, 'i');
    if (pattern.test(scanned)) hits.push(word);
  }
  return hits;
}

// ── What a disclosure summary may not be called ──────────────────────────────────

/**
 * Summaries that name the CONTROL rather than the CONTENT, lower-cased.
 *
 * R6: *"Every disclosure summary names what is inside it in the reader's words — 'Show the
 * exact check the database ran' — never 'Details'."* A disclosure labelled "Details" tells
 * a reader nothing about whether opening it is worth their time, and the whole argument of
 * this plan is that the exact material is one **deliberate** click away rather than one
 * hopeful one.
 *
 * It lives in the vocabulary rather than beside `Disclosure.tsx` for two reasons: it is a
 * rule about WORDS, which is what this file is; and `react-refresh/only-export-components`
 * — which this workspace lints at `--max-warnings 0` — refuses a component module that
 * also exports a constant and a predicate. The same split the shell already makes between
 * `app/honesty.ts` and `app/HonestyProvider.tsx`.
 */
export const REFUSED_SUMMARIES: readonly string[] = Object.freeze([
  'details',
  'more',
  'more details',
  'more info',
  'more information',
  'show more',
  'read more',
  'info',
  'information',
  'advanced',
  'technical details',
  'technical',
  'expand',
  'learn more',
]);

/** `false` when the summary names the control instead of the content. */
export function summaryNamesItsContents(summary: string): boolean {
  const normalised = summary.trim().toLowerCase().replace(/[.…:]+$/u, '');
  return normalised !== '' && !REFUSED_SUMMARIES.includes(normalised);
}

/** Every string this module carries, for the gates that must be total over it. */
export function everySentence(): readonly string[] {
  return [
    ...PRODUCT_WORDS.flatMap((entry) => [entry.sentence, entry.names]),
    ...GLOSSED_TERMS.flatMap((entry) => [entry.label, entry.gloss]),
    ...SQLSTATE_GLOSSES.map((entry) => entry.gloss),
  ];
}

// ── The load-time assertion ──────────────────────────────────────────────────────

/**
 * Two invariants, checked when the module loads, in the idiom `src/data/resources.ts`
 * already uses for `RESOURCES` / `RESOURCE_KEYS`.
 *
 * A duplicate key is not a cosmetic problem: `glossFor()` is a Map lookup, so the second
 * entry wins silently and the first sentence disappears from every screen that asked for
 * it while `vocabulary.md` still documents it. An empty sentence is worse — `Gloss`
 * would render a definition-shaped blank beside a verbatim value, which is the console
 * claiming it has explained something it has not.
 *
 * Throwing at load beats returning a default. A vocabulary that is allowed to be
 * inconsistent is a vocabulary that stops being read.
 */
{
  const productKeys: string[] = PRODUCT_WORDS.map((entry) => entry.key);
  const termKeys: string[] = GLOSSED_TERMS.map((entry) => entry.key);

  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const key of [...productKeys, ...termKeys]) {
    if (seen.has(key)) duplicates.add(key);
    seen.add(key);
  }
  if (duplicates.size > 0) {
    throw new Error(
      `src/design/glossary.ts declares the key(s) [${[...duplicates].join(', ')}] more ` +
        'than once. glossFor() is a Map lookup, so the second entry would win silently and the ' +
        'first sentence would vanish from every screen that asked for it.',
    );
  }

  const declaredProduct = [...PRODUCT_WORD_KEYS].sort().join(',');
  const listedProduct = [...productKeys].sort().join(',');
  if (declaredProduct !== listedProduct) {
    throw new Error(
      `src/design/glossary.ts is inconsistent with itself: PRODUCT_WORD_KEYS has ` +
        `[${declaredProduct}] but PRODUCT_WORDS has [${listedProduct}].`,
    );
  }

  const declaredTerm = [...GLOSSED_TERM_KEYS].sort().join(',');
  const listedTerm = [...termKeys].sort().join(',');
  if (declaredTerm !== listedTerm) {
    throw new Error(
      `src/design/glossary.ts is inconsistent with itself: GLOSSED_TERM_KEYS has ` +
        `[${declaredTerm}] but GLOSSED_TERMS has [${listedTerm}].`,
    );
  }

  const codes = SQLSTATE_GLOSSES.map((entry) => entry.code);
  if (new Set(codes).size !== codes.length) {
    throw new Error(
      `src/design/glossary.ts declares a SQLSTATE code twice: [${codes.join(', ')}].`,
    );
  }

  const blank = everySentence().filter((sentence) => sentence.trim() === '');
  if (blank.length > 0) {
    throw new Error(
      `src/design/glossary.ts carries ${blank.length} empty string(s). An empty gloss renders a ` +
        'definition-shaped blank beside a verbatim value, which is the console claiming it has ' +
        'explained something it has not.',
    );
  }
}
