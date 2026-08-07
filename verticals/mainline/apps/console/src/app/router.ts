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

/** Where a bare `#` or an empty hash lands. The refusal is the first thing shown. */
export const DEFAULT_PATH = '/gate';

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
