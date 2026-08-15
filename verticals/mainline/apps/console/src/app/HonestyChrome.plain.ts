// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE HONESTY STRIP'S PLAIN SENTENCES — one per cell, and why they are a LAZY chunk.
 *
 * R4 requires every cell of the strip to carry a plain one-sentence explanation that a
 * keyboard can reach, because a `title=` attribute is invisible on a phone, unreachable by
 * keyboard, unreliable to a screen reader and absent from print. `HonestyChrome` renders
 * them as real text nodes, referenced by `aria-describedby`.
 *
 * ── WHY THEY ARE NOT IN THE STRIP'S OWN MODULE ───────────────────────────────────
 *
 * Measured on the demo-mode build of 2026-08-15, gzip level 9, the deploy's own setting:
 * the entry chunk is **139,199 B before this wave's strip work**, against
 * `mainline_demo_api.static_site.DEFAULT_MAX_RESPONSE_BYTES` of **139,264** — sixty-five
 * bytes of headroom on the whole console, and one byte past that ceiling is a **413**
 * rather than a slow page. Carried eagerly, these nine sentences cost the entry 829 B and
 * put it 764 B over. As their own chunk they cost it the import glue and nothing else.
 *
 * This is exactly the arrangement `src/app/SurfaceHost.tsx` already uses for the on-ramp
 * deck, and it is adopted here for the same measured reason and with the same failure
 * mode: **no deck, no sentences, and the strip is unchanged.** Every FACT on the strip —
 * every value, every tone, every provenance marker, the SKIP and its reason — is eager and
 * is rendered before this module is asked for. What arrives late is only the explanation of
 * what each cell is about, and a cell with no explanation yet declares none: the strip does
 * not point `aria-describedby` at an element that is not there.
 *
 * ── WHAT A SENTENCE MAY SAY ──────────────────────────────────────────────────────
 *
 * One sentence, for somebody who has never read a line of this repository. It answers only
 * *what is this cell about* — never *is the value good*, which is the cell's own job and is
 * already exact. None of them softens a value, and none of them can: they are keyed by
 * cell and are the same string whatever the cell happens to read.
 */

/** Keyed by the cell's slug — the same slug its `data-testid` uses. */
export type PlainDeck = Readonly<Record<string, string>>;

export const PLAIN: PlainDeck = Object.freeze({
  transport:
    'Where the numbers on this page came from: LIVE means a database answered just now, and ' +
    'REPLAY means a signed recording was opened and re-checked in this browser first. The word ' +
    'is asked of the thing that fetched the bytes, so it cannot disagree with them.',
  bundle:
    'The fingerprint this browser worked out for a signed recording’s file list — it is only ' +
    'filled in when a recording was actually opened here.',
  seal:
    'Whether this browser re-did the arithmetic over a signed recording and got the same ' +
    'answer as the recording claims.',
  'checkpoint-signature':
    'Whether this build carries the public key that would let it check who signed the log’s ' +
    'checkpoints — without that key the question cannot be asked at all, and amber is what ' +
    'a question nobody could ask looks like.',
  'corpus-root':
    'Which exact version of the rule-book the trail shown on this page was worked out ' +
    'against, so two screenshots can be compared.',
  'clock-skew':
    'The server’s clock minus this browser’s clock. A timestamp in a screenshot means nothing ' +
    'until you know how far apart the two clocks were.',
  'signature-path':
    'How a person’s signature would be captured in this build. It is decided when the build ' +
    'is made, not while you are using it.',
  render:
    'Which way this build draws the history view on this machine — a flat ribbon, or a walk ' +
    'through it in three dimensions.',
  build:
    'The identifier of the exact artefact you are looking at, so a screenshot names the build ' +
    'it came from and can be rebuilt.',
});
