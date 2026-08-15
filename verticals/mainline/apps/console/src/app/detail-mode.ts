// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * PLAIN and FULL DETAIL — ruling R6, as a module.
 *
 * One control in the shell. **PLAIN** on arrival; **FULL DETAIL** is exactly today's
 * screen with the plain band still above it. The mode is not a preference and not a
 * theme — it decides which of two readings of the same screen a link reproduces, so it
 * lives in the ADDRESS and nowhere else.
 *
 * ── WHY THERE IS NO localStorage AND NO sessionStorage HERE ──────────────────────
 *
 * Two independent reasons, and either one alone would be enough:
 *
 *   • **The console must run from `file://`.** `src/app/router.ts` is hash-based for the
 *     same reason — the offline reproduction tier is on the never-cut list, and a
 *     `file://` origin is opaque, so `localStorage` is either unavailable or shared with
 *     every other `file://` document the reader has ever opened.
 *   • **A screenshot must reproduce from its URL.** That is the whole argument this
 *     console makes about itself. A mode held in browser storage produces two readers
 *     looking at the same link and seeing different screens, with nothing on either page
 *     saying which one they got — which is exactly the class of defect the honesty strip
 *     exists to refuse.
 *
 * So `?detail=full` is the entire state, and `hrefWithDetail()` is how it survives a nav
 * click. Nothing here reads or writes `Storage`, and `detail-mode.test.ts` asserts that by
 * stubbing both globals to throw.
 *
 * ── WHY THE QUERY MERGE IS WRITTEN OUT AGAIN ─────────────────────────────────────
 *
 * `paramsFromAddress()` below is the same four-line merge — search plus hash query, hash
 * winning — that `src/app/router.ts` performs and that `src/app/source-select.ts` and
 * `src/features/evidence/source.ts` each restate. I am FOLLOWING THAT PRECEDENT
 * deliberately and for the reason those two modules give in their own comments: the
 * router's `parseRoute` also needs the surface registry, and this module must stay a pure
 * function of two strings so a test can call it with no DOM and no registry at all. Four
 * lines of duplication buys a decision function a test can drive directly, and the four
 * copies are held together by the tests that each assert the hash-wins rule.
 *
 * ── WHY THE CONTEXT AND THE HOOK LIVE IN A `.ts` FILE ────────────────────────────
 *
 * `react-refresh/only-export-components` runs at `--max-warnings 0` in this workspace and
 * refuses a component module that also exports a context or a hook. The same split the
 * shell already makes between `app/honesty.ts` and `app/HonestyProvider.tsx`, and that
 * `app/source-select.ts` makes for the transport control.
 */

import { createContext, useContext, useMemo, useSyncExternalStore } from 'react';

// ── The mode ─────────────────────────────────────────────────────────────────────

/**
 * The two readings, in the order a reader meets them.
 *
 * A frozen tuple plus a union type rather than a TypeScript `enum`, because
 * `tsconfig.json` sets `erasableSyntaxOnly` — the same form `registers.ts` uses and for
 * the same mechanical reason.
 */
export const DETAIL_MODES = ['plain', 'full'] as const;

export type DetailMode = (typeof DETAIL_MODES)[number];

/** What a reader gets on arrival, before any link has said otherwise. */
export const DEFAULT_DETAIL_MODE: DetailMode = 'plain';

/** The query parameter. One name, used by the parser and by the link builder alike. */
export const DETAIL_PARAM = 'detail';

/** The value that selects FULL DETAIL. Anything else — including absent — is PLAIN. */
export const FULL_VALUE = 'full';

export function isDetailMode(value: unknown): value is DetailMode {
  return (DETAIL_MODES as readonly unknown[]).includes(value);
}

// ── Parsing ──────────────────────────────────────────────────────────────────────

/**
 * Query parameters from both positions, hash winning — the merge `src/app/router.ts`
 * performs and `src/app/source-select.ts` and `src/features/evidence/source.ts` restate.
 * See the header for why it is written out here rather than imported.
 */
export function paramsFromAddress(search: string, hash: string): URLSearchParams {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const withoutHash = hash.startsWith('#') ? hash.slice(1) : hash;
  const mark = withoutHash.indexOf('?');
  if (mark >= 0) {
    for (const [key, value] of new URLSearchParams(withoutHash.slice(mark + 1))) {
      params.set(key, value);
    }
  }
  return params;
}

/**
 * The mode a merged query selects.
 *
 * `?detail=full` is FULL DETAIL. Absent is PLAIN. **An unrecognised value is PLAIN**, and
 * that direction is chosen rather than defaulted into: PLAIN never hides the refusal bar,
 * the SQLSTATE, the constraint name, a provenance chip, a STAGED badge, a SYNTHETIC
 * marker or the honesty strip (R6), so falling back to it can only ever collapse a
 * disclosure a reader can open. Falling back the other way would silently promote a typo
 * into "show everything", which is the reading a screenshot is least likely to be
 * reproducible from.
 *
 * Matched case-insensitively and trimmed, because `?detail=FULL` from a pasted link is a
 * reader asking for the same thing.
 */
export function detailModeFrom(params: URLSearchParams): DetailMode {
  const raw = params.get(DETAIL_PARAM);
  if (raw === null) return DEFAULT_DETAIL_MODE;
  return raw.trim().toLowerCase() === FULL_VALUE ? 'full' : DEFAULT_DETAIL_MODE;
}

/** The mode an address selects, as a pure function of two strings. */
export function detailModeFromAddress(search: string, hash: string): DetailMode {
  return detailModeFrom(paramsFromAddress(search, hash));
}

// ── Link building ────────────────────────────────────────────────────────────────

/** Rooted, no trailing slash — the same normalisation `router.ts` applies to a path. */
function normalisePath(path: string): string {
  const rooted = path.startsWith('/') ? path : `/${path}`;
  const trimmed = rooted.length > 1 && rooted.endsWith('/') ? rooted.slice(0, -1) : rooted;
  return trimmed === '' ? '/' : trimmed;
}

/**
 * A hash href for `path` that CARRIES the current mode.
 *
 * This is how `?detail=full` survives a nav click, and every link in the shell must be
 * built with it — a single nav item built with `hrefFor()` would drop a reader out of FULL
 * DETAIL without saying so, which is the same defect as holding the mode in storage.
 *
 * `path` may already carry its own query (`/gate?permit=…`); those parameters are
 * preserved and only `detail` is set or removed. In PLAIN the parameter is REMOVED rather
 * than written as `detail=plain`, so the default reading has the shortest possible link
 * and a bare `#/gate` and a `#/gate?detail=plain` are the same address.
 */
export function hrefWithDetail(path: string, mode: DetailMode = DEFAULT_DETAIL_MODE): string {
  const withoutHash = path.startsWith('#') ? path.slice(1) : path;
  const mark = withoutHash.indexOf('?');
  const rawPath = mark >= 0 ? withoutHash.slice(0, mark) : withoutHash;
  const params = new URLSearchParams(mark >= 0 ? withoutHash.slice(mark + 1) : '');

  if (mode === 'full') params.set(DETAIL_PARAM, FULL_VALUE);
  else params.delete(DETAIL_PARAM);

  const query = params.toString();
  return `#${normalisePath(rawPath)}${query === '' ? '' : `?${query}`}`;
}

// ── The context ──────────────────────────────────────────────────────────────────

/**
 * The mode, shared down the tree.
 *
 * The default is `plain` rather than `null`, deliberately. A `Disclosure` rendered outside
 * any provider — in a unit test, in an error boundary's fallback, in a surface the shell
 * has not wrapped yet — must still render, and the mode it renders in must be the one that
 * hides nothing that R6 forbids hiding. A `null` default would force every consumer to
 * handle an absence that has no honest handling.
 *
 * React 19 renders a context object directly as its own provider, so the shell writes
 * `<DetailModeContext value={mode}>` and no `DetailModeProvider` component is needed —
 * which is what keeps this module free of JSX and therefore free of
 * `react-refresh/only-export-components`.
 */
export const DetailModeContext = createContext<DetailMode>(DEFAULT_DETAIL_MODE);

/** The mode this subtree is being read in. */
export function useDetailMode(): DetailMode {
  return useContext(DetailModeContext);
}

/** `true` when the reader has asked for FULL DETAIL. A convenience, not a second source. */
export function useIsFullDetail(): boolean {
  return useDetailMode() === 'full';
}

/**
 * A link builder bound to the current mode: `href('/custody')` keeps the reader where
 * they are.
 */
export function useHrefWithDetail(): (path: string) => string {
  const mode = useDetailMode();
  return useMemo(() => (path: string) => hrefWithDetail(path, mode), [mode]);
}

// ── Reading the live address ─────────────────────────────────────────────────────

function subscribeToAddress(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  window.addEventListener('popstate', onChange);
  return () => {
    window.removeEventListener('hashchange', onChange);
    window.removeEventListener('popstate', onChange);
  };
}

/** A location snapshot as a primitive, so `useSyncExternalStore` can compare it cheaply. */
function addressKey(): string {
  return typeof window === 'undefined' ? '' : `${window.location.search}${window.location.hash}`;
}

/**
 * The mode the CURRENT address selects, re-read whenever the address changes.
 *
 * The shell calls this once and publishes the result through `DetailModeContext`; nothing
 * else should call it, because two subscribers reading the address independently is two
 * places for the answer to differ. The same `useSyncExternalStore` shape `router.ts` uses,
 * and for the same reason — the address is an external store and React must be told so.
 */
export function useDetailModeFromAddress(): DetailMode {
  const key = useSyncExternalStore(subscribeToAddress, addressKey, () => '');
  return useMemo(() => {
    const hashAt = key.indexOf('#');
    const search = hashAt >= 0 ? key.slice(0, hashAt) : key;
    const hash = hashAt >= 0 ? key.slice(hashAt) : '';
    return detailModeFromAddress(search, hash);
  }, [key]);
}
