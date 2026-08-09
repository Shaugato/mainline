// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Where the bundle under audit comes from, decided by a pure function.
 *
 * Two rules, both of which are security properties rather than conveniences.
 *
 * **A URL parameter may name only a same-origin, relative location.** `?bundle=…` is a
 * link, and a link is something a stranger can send. A console that fetched, hashed and
 * then rendered an arbitrary cross-origin directory because a query string said so
 * would be a machine for producing authentic-looking screenshots of somebody else's
 * bytes under our chrome. Absolute URLs, protocol-relative `//host` forms and `..`
 * segments are refused BY NAME, so a reader who tries one is told why rather than shown
 * an empty screen.
 *
 * **The build-time default may be absolute**, because whoever set `VITE_MAINLINE_BUNDLE_URL`
 * is the operator who built the artefact, not a person who sent a link.
 *
 * The decision returns a REASON in every branch. The reason is rendered: a surface that
 * shows nothing must say which of the several possible nothings it is.
 */

import { FetchBundleSource, type BundleSource } from '../../data/bundle';

export type BundleLocation =
  | { readonly kind: 'url'; readonly url: string; readonly why: string }
  | { readonly kind: 'none'; readonly why: string };

/** The query parameter a reader can put in a link. */
export const BUNDLE_PARAM = 'bundle';

const ABSOLUTE = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;

/** Why a candidate was refused, or `null` when it is acceptable as a relative path. */
export function refuseRelativePath(candidate: string): string | null {
  if (candidate.trim() === '') {
    return `?${BUNDLE_PARAM}= was empty.`;
  }
  if (ABSOLUTE.test(candidate)) {
    return (
      `?${BUNDLE_PARAM}=${candidate} names an absolute URL. A link can be sent by anyone, and ` +
      'this console will not fetch, hash and render bytes from an origin a query string chose. ' +
      'Serve the bundle from this origin, or set VITE_MAINLINE_BUNDLE_URL at build time.'
    );
  }
  if (candidate.startsWith('//')) {
    return (
      `?${BUNDLE_PARAM}=${candidate} is protocol-relative, which resolves to another host. Same ` +
      'refusal as an absolute URL, and for the same reason.'
    );
  }
  if (candidate.split('/').includes('..')) {
    return (
      `?${BUNDLE_PARAM}=${candidate} contains a ".." segment. A bundle location is a directory ` +
      'under this origin, not a path expression.'
    );
  }
  return null;
}

export interface BundleEnvironment {
  readonly VITE_MAINLINE_BUNDLE_URL?: string;
}

/**
 * Query parameters from both positions, hash winning — the same merge `src/app/router.ts`
 * performs.
 *
 * Duplicated as four lines rather than imported, because the router's `parseRoute` also
 * needs the surface registry and this module must stay a pure function of two strings so
 * that `source.test.ts` can call it with no DOM and no registry at all. The two are held
 * together by `source.test.ts`, which asserts the hash-wins rule the router documents.
 */
export function paramsFromLocation(search: string, hash: string): URLSearchParams {
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
 * `?bundle=` wins over the build-time default, and both are named on screen.
 *
 * A reader must be able to tell, from the page, whether they are looking at the bundle
 * the build shipped with or one their own link selected.
 */
export function resolveBundleLocation(
  params: URLSearchParams,
  env: BundleEnvironment,
): BundleLocation {
  const requested = params.get(BUNDLE_PARAM);
  if (requested !== null) {
    const refusal = refuseRelativePath(requested);
    if (refusal !== null) return { kind: 'none', why: refusal };
    return {
      kind: 'url',
      url: requested,
      why: `selected by ?${BUNDLE_PARAM}= in this page's address, relative to this origin.`,
    };
  }

  const configured = env.VITE_MAINLINE_BUNDLE_URL;
  if (configured !== undefined && configured.trim() !== '') {
    return {
      kind: 'url',
      url: configured,
      why: 'the build-time default, VITE_MAINLINE_BUNDLE_URL, compiled into this artefact.',
    };
  }

  return {
    kind: 'none',
    why:
      'no bundle is configured. This build carries no VITE_MAINLINE_BUNDLE_URL and this page\'s ' +
      `address names no ?${BUNDLE_PARAM}=. Nothing has been fetched, so there is nothing to audit ` +
      '— which is a fact about this deployment, not about any bundle.',
  };
}

/** A reader for a located bundle. Trailing slash added here so callers need not care. */
export function bundleSourceFor(location: BundleLocation, fetchImpl?: typeof fetch): BundleSource | null {
  if (location.kind === 'none') return null;
  return fetchImpl === undefined
    ? new FetchBundleSource(location.url)
    : new FetchBundleSource(location.url, fetchImpl);
}

// ── Enumeration, when the source can do it ─────────────────────────────────

/**
 * A source that can say what is actually in the directory.
 *
 * `FetchBundleSource` cannot: a static host answers requests and does not list. So the
 * "no smuggled files" claim is one this console usually CANNOT make, and `Coverage.unlisted`
 * is `null` rather than `[]` in that case — the difference between "none found" and
 * "not established" is the whole difference between honesty and reassurance here.
 */
export interface ListableBundleSource extends BundleSource {
  list(): Promise<readonly string[]>;
}

export function isListable(source: BundleSource): source is ListableBundleSource {
  return typeof (source as Partial<ListableBundleSource>).list === 'function';
}
