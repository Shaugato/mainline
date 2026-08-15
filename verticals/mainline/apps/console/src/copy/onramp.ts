// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ON-RAMP — what a reader meets FIRST, and nothing else.
 *
 * The founder's finding, 2026-08-15: *"the way it's written, it's kind of hard to read…
 * someone might not have technical abilities but still uses this software, they should be
 * able to understand. And someone has technical ability, they should be able to look into
 * more detail."*
 *
 * ── READ THE COPY THIS DECK SITS ABOVE BEFORE JUDGING EITHER ─────────────────────
 *
 * The screens are not badly written. `CustodyScreen.tsx` opens on RFC 8785
 * canonicalisation and RFC 6962 leaf, node, inclusion and consistency hashing; every word
 * of that is correct, every word of it is checkable, and every word of it survives this
 * change untouched. The defect is not the sentence — it is that a first-time reader meets
 * it before anybody has told them what the product refuses or why a refusal is the
 * deliverable. **This deck is an ON-RAMP, never a dumbing-down.** Nothing here replaces,
 * summarises or softens a sentence on any screen. If a lede below ever makes a claim
 * vaguer than the screen it introduces, it is wrong and it is the lede that goes.
 *
 * ── WHY THE WORDS LIVE HERE AND NOT IN THE FEATURES ──────────────────────────────
 *
 * `docs/leads/screens-work-plan.md` §2.10 rules that the on-ramp is **chrome, not feature
 * copy**: mounted by `src/app/SurfaceHost.tsx` from a deck keyed by surface id, precisely
 * so that no feature file is opened and no precise sentence can be edited by accident
 * while adding a plain one. Seven screens, seven ledes, one file, zero diffs under
 * `src/features/` — that property is the whole point of the arrangement, and
 * `tests/unit/app/onramp.test.tsx` asserts the deck covers every declared surface so a new
 * screen cannot ship without one.
 *
 * ── WHAT A LEDE MAY AND MAY NOT SAY ──────────────────────────────────────────────
 *
 * Two or three sentences. No SQLSTATE, no RFC number, no constraint name, no acronym a
 * reader has not been given. Each one answers two questions and no others: *what is this
 * screen for*, and *what would I learn from it*. Every sentence is still a claim this
 * repository is held to, so each is written as what a reader will SEE on the screen below
 * rather than as a characterisation of what the platform IS — a screen that renders an
 * absence must have a lede that admits an absence is possible, which is why several of
 * these say "or" out loud.
 *
 * ── THE BYTES ────────────────────────────────────────────────────────────────────
 *
 * This module is imported LAZILY by `SurfaceHost`, in the same effect that imports the
 * surface. Measured on the demo-mode build of 2026-08-15, the entry chunk gzipped (level 9,
 * the deploy's own settings) to 135,339 B against
 * `static_site.DEFAULT_MAX_RESPONSE_BYTES` of 139,264 — **3,925 B of headroom on the whole
 * console**, and one byte over that ceiling is a 413 rather than a slow page. Carried
 * eagerly, this file cost the entry chunk 4,629 B (1,507 B gzipped); as its own chunk it
 * costs it nothing. Prose is the cheapest thing to move off a critical path and the most
 * expensive thing to leave on one. The ceiling is not negotiable and is not lowered by this
 * change; see the report to the lead.
 */

/** One screen's plain-language opening. Rendered above the surface, never inside it. */
export interface SurfaceLede {
  /** Two or three words, lower case. The CSS decides the rest. */
  readonly kicker: string;
  /** Two or three sentences, in order. No jargon, no hedging, each one checkable. */
  readonly sentences: readonly string[];
}

/*
 * WHAT IS DELIBERATELY *NOT* IN THIS FILE: the disclosure's own label, its note and its
 * storage key. They live in `src/app/SurfaceHost.tsx` beside the chrome that renders them,
 * and the reason is measured rather than aesthetic. A module that is imported STATICALLY
 * for three short constants and LAZILY for the deck is not lazy at all — rollup inlines
 * the whole thing into the entry chunk, and the first two builds of this change proved it
 * twice, at 4,629 B of prose no screen needs before it paints. Only the TYPE above crosses
 * that boundary now, and a type is erased.
 */

/**
 * What a screen with no deck entry says.
 *
 * A surface that self-registered without appearing in the promise list is legal
 * (`src/app/surfaces.ts`), and it will reach `SurfaceHost` with an id this file has never
 * heard of. It still gets a lede, and the lede reports the gap as a gap in this deck
 * rather than implying anything at all about the screen underneath it.
 */
export const FALLBACK_LEDE: SurfaceLede = Object.freeze({
  kicker: 'no plain-language note',
  sentences: Object.freeze([
    'Nobody has written a plain-language note for this screen yet.',
    'That is a gap in the console’s copy deck, not a statement about the screen below — read it as it is written, and the precise version is still one line down.',
  ]),
});

const LEDES = {
  overview: {
    kicker: 'start here',
    sentences: [
      'This is the way in. It says what the system refuses, and then walks two cases from beginning to end.',
      'Each case finishes with a link into the screen that shows it, addressed to a subject this deployment actually seeded — so nothing below is a mock-up of what the product would do.',
    ],
  },

  gate: {
    kicker: 'what this screen is for',
    sentences: [
      'A permit is a request to make a change that safety checks stand in front of. This screen shows one permit and asks the database to merge it.',
      'Press a button at the top and the answer comes back from the database itself: either the merge is admitted, or it is refused and the refusal names the rule that refused it.',
      'What you would learn here: which count was not zero, and which named rule read that count and said no.',
    ],
  },

  diff: {
    kicker: 'what this screen is for',
    sentences: [
      'A refusal points at a written rule. This screen opens that rule at the exact version the record names.',
      'What you would learn here: what an edit to it changed, and whether the change loosened a control — or, when the version has no earlier version to compare against, that there is nothing to compare and why.',
    ],
  },

  custody: {
    kicker: 'what this screen is for',
    sentences: [
      'Everything the system records goes into a log that can only be appended to. This screen re-does that log’s arithmetic in your own browser, from the bytes it was just handed.',
      'What you would learn here: which of the log’s claims survive being recomputed, which do not, and which could not be attempted at all — each one shown beside the numbers it was worked out from.',
      'You do not have to take our word for any of it: the same arithmetic runs on a stranger’s laptop, with no access to our database and no cooperation from us.',
    ],
  },

  evidence: {
    kicker: 'what this screen is for',
    sentences: [
      'This console can run from a signed capture of a past session instead of a live database. This screen audits that capture.',
      'What you would learn here: every file the capture declares, the fingerprint this browser worked out for each one, and whether they agree — or, when no capture was consulted, that fact in words rather than a blank.',
    ],
  },

  audit: {
    kicker: 'what this screen is for',
    sentences: [
      'This screen is the read-only account looking at itself: every question it asked the database, and what came back.',
      'What you would learn here: what it was allowed to ask, the limits it ran under, and where an answer came back with nothing in it — which is a fact about what was reachable, not a claim that nothing exists.',
    ],
  },

  propagation: {
    kicker: 'what this screen is for',
    sentences: [
      'A lesson learned at one site is meant to travel to the sites like it. This screen shows how far it got.',
      'What you would learn here: which sites took the change, which did not, and what the record says about the difference between them.',
    ],
  },

  silence: {
    kicker: 'what this screen is for',
    sentences: [
      'A search that comes back empty can mean two very different things: there was nothing to find, or nothing was looked at.',
      'This screen shows what the system declined to put in front of a person, and the arithmetic behind each of those decisions.',
      'What you would learn here: whether the silence was earned, or whether nobody can tell.',
    ],
  },

  ancestry: {
    kicker: 'what this screen would be for',
    sentences: [
      'This screen would walk backwards from a rule to the edit that wrote it, and to the change that carried that edit.',
      'It has not been built. The card below names the milestone that owes it, and says so rather than letting the screen disappear from the navigation as though it had never been promised.',
    ],
  },

  disposition: {
    kicker: 'what this screen would be for',
    sentences: [
      'Closing out a check is a person taking responsibility for it, so this screen would make that act explicit: the fields the rules demand, and a second signature where the rules demand one.',
      'It has not been built. The card below names the milestone that owes it, and says so rather than letting the screen disappear from the navigation as though it had never been promised.',
    ],
  },
} as const satisfies Readonly<Record<string, SurfaceLede>>;

for (const lede of Object.values(LEDES)) {
  Object.freeze(lede.sentences);
  Object.freeze(lede);
}
Object.freeze(LEDES);

/** The deck. Frozen — copy a feature worker can mutate at runtime is not a deck. */
export const SURFACE_LEDES: Readonly<Record<string, SurfaceLede>> = LEDES;

/**
 * The lede for a surface id. **Never null**, because every surface shows one.
 *
 * An unknown id is the undeclared-stranger case and it gets {@link FALLBACK_LEDE}, which
 * reports the missing entry as a missing entry. Returning null here would make a copy gap
 * indistinguishable from a screen that deliberately has no introduction.
 */
export function ledeFor(id: string): SurfaceLede {
  return SURFACE_LEDES[id] ?? FALLBACK_LEDE;
}
