// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The router (D2 — no router library).
 *
 * Six static surfaces, no nested layouts, no loaders, no transitions. A router library
 * would add a dependency to a graph that is a licence and liability boundary in order
 * to solve a problem this console does not have.
 *
 * Hash-based, deliberately. The console must deep-link correctly from a bare static
 * host, from an arbitrary sub-path, and from `file://` — the offline reproduction tier
 * (BUILD_PLAN §5) is on the never-cut list, and a history-API router needs a server
 * rewrite rule that a `file://` URL cannot have.
 *
 * `?cinema=1&seed=…&t=…&frame=…` (D12) may be carried in either query position; a
 * route's `params` merges both, with the hash query winning.
 */

import { useMemo, useSyncExternalStore } from 'react';

import { type SurfaceEntry } from './surfaces';

export interface Route {
  /** The surface addressed, or `null` when the path matches no registered surface. */
  readonly surfaceId: string | null;
  /** The normalised path, always rooted, never with a trailing slash. `/gate`. */
  readonly path: string;
  /** Query parameters from both positions, hash winning. */
  readonly params: URLSearchParams;
  /** The raw hash as it appeared, for verbatim display when nothing matched. */
  readonly raw: string;
}

/**
 * Where a bare `#` or an empty hash lands.
 *
 * ── WHY THIS IS NOT `/gate` ANY MORE (2026-08-15) ────────────────────────────────
 *
 * It was `/gate`, and the comment above it read *"the refusal is the first thing shown"*.
 * That was the intent and it was not what happened. `GateSurfaceRoot` renders the gate of
 * ONE subject and — correctly, by its own doctrine — **does not choose one for you**. A
 * bare URL carries no `?permit=`, so the first thing a stranger saw was not a refusal but
 * `NO SUBJECT ADDRESSED — address a permit by its identifier #/gate?permit=<uuid>`: an
 * instruction to type a UUID they do not have, on the headline screen, in the first three
 * seconds. Measured on the live Function URL today.
 *
 * There are two ways to fix that and only one of them is honest. Giving the Gate a default
 * permit would delete the rule that makes it trustworthy — a screen that picks a subject
 * for you is a screen that can pick the flattering one — so the rule stays, verbatim, and
 * the LANDING moves instead. `docs/leads/demo-story-plan.md` R2 rules exactly that.
 *
 * ── WHY `/overview` AND NOT A NEW `/start` ───────────────────────────────────────
 *
 * `demo-story-plan.md` R2 names the destination `/start` and asks for it to be built. It
 * was written against `e88b8b6`; by the time it was executed the every-screen wave had
 * already landed `src/features/overview/` — order 5, above the gate, promised in
 * `DECLARED_SURFACES`, and covering point for point what R2 asks a landing screen to
 * carry: one plain-language headline about what the system refuses, an orientation line,
 * and addressed doors to the gate, custody and silence. Its doors are addressed with
 * identifiers the kernel named at `GET /v1/demo/subjects` rather than with literals, which
 * is the stronger form of the same requirement.
 *
 * Building `/start` beside it would put TWO on-ramps in a navigation whose defect was that
 * a judge could not find one, so the landing points at the on-ramp that exists. The rest of
 * R2 — the Gate keeps its rule, every navigation link becomes an addressed deep link — is
 * unchanged and already holds (`src/app/subjects.ts`).
 *
 * The value is a path, not a surface id, for `parseRoute`'s benefit: an id would have to be
 * resolved against a registry this module deliberately does not import.
 */
export const DEFAULT_PATH = '/overview';

export function normalisePath(path: string): string {
  const rooted = path.startsWith('/') ? path : `/${path}`;
  const trimmed = rooted.length > 1 && rooted.endsWith('/') ? rooted.slice(0, -1) : rooted;
  return trimmed === '' ? '/' : trimmed;
}

export function hrefFor(path: string): string {
  return `#${normalisePath(path)}`;
}

export function parseRoute(
  hash: string,
  search: string,
  entries: readonly SurfaceEntry[],
): Route {
  const raw = hash;
  const withoutHash = hash.startsWith('#') ? hash.slice(1) : hash;
  const queryAt = withoutHash.indexOf('?');
  const rawPath = queryAt >= 0 ? withoutHash.slice(0, queryAt) : withoutHash;
  const hashQuery = queryAt >= 0 ? withoutHash.slice(queryAt + 1) : '';

  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  for (const [key, value] of new URLSearchParams(hashQuery)) params.set(key, value);

  const path = rawPath === '' || rawPath === '/' ? DEFAULT_PATH : normalisePath(rawPath);
  const match = entries.find((entry) => entry.path === path);
  return { surfaceId: match?.id ?? null, path, params, raw };
}

export function navigateTo(path: string): void {
  if (typeof window === 'undefined') return;
  window.location.hash = normalisePath(path);
}

function subscribeToHash(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  window.addEventListener('popstate', onChange);
  return () => {
    window.removeEventListener('hashchange', onChange);
    window.removeEventListener('popstate', onChange);
  };
}

/** A location snapshot as a primitive, so `useSyncExternalStore` can compare it cheaply. */
function locationKey(): string {
  return typeof window === 'undefined' ? '' : `${window.location.search}${window.location.hash}`;
}

export function useRoute(entries: readonly SurfaceEntry[]): Route {
  const key = useSyncExternalStore(subscribeToHash, locationKey, () => '');
  return useMemo(() => {
    const hashAt = key.indexOf('#');
    const search = hashAt >= 0 ? key.slice(0, hashAt) : key;
    const hash = hashAt >= 0 ? key.slice(hashAt) : '';
    return parseRoute(hash, search, entries);
  }, [key, entries]);
}
