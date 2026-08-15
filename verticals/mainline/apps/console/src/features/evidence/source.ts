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
 * bytes under our chrome. Absolute URLs, protocol-relative `//host` forms, backslashes,
 * C0 controls or spaces, and `..` segments are refused BY NAME, so a reader who tries one
 * is told why rather than shown an empty screen. The last three of those five are the
 * forms that reach another origin WITHOUT looking like it, and each is documented beside
 * the check with the resolution it was measured producing.
 *
 * **The build-time default may be absolute**, because whoever set `VITE_MAINLINE_BUNDLE_URL`
 * is the operator who built the artefact, not a person who sent a link.
 *
 * The decision returns a REASON in every branch. The reason is rendered: a surface that
 * shows nothing must say which of the several possible nothings it is.
 *
 * ── THE ORDER IS THE SECURITY PROPERTY ───────────────────────────────────────────
 *
 * `refuseRelativePath` runs on the RAW candidate, in `resolveBundleLocation`, before any
 * resolution happens anywhere. `FetchBundleSource` resolves its base against
 * `document.baseURI` in its constructor — which is what makes `./bundle/` a legal value
 * for the deployed build — and that constructor is reached only through
 * `bundleSourceFor`, which is reached only for a candidate this module already accepted.
 * Refuse first, resolve second. Checking an origin AFTER resolution would be a different
 * and weaker property: it would mean the console had already decided what a query string
 * meant before deciding whether it was allowed to mean it.
 *
 * `tests/unit/evidence/source.test.ts` asserts the ordering directly — a refused candidate
 * yields `kind: 'none'`, so no source object is ever constructed for it.
 */

import { FetchBundleSource, type BundleSource } from '../../data/bundle';

export type BundleLocation =
  | { readonly kind: 'url'; readonly url: string; readonly why: string }
  | { readonly kind: 'none'; readonly why: string };

/** The query parameter a reader can put in a link. */
export const BUNDLE_PARAM = 'bundle';

const ABSOLUTE = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;

/**
 * A backslash anywhere.
 *
 * The WHATWG URL parser treats `\` as a path separator for every SPECIAL scheme, so
 * `?bundle=\\elsewhere.example` resolves to `https://elsewhere.example/` — a foreign
 * origin, reached through a string that starts with neither a scheme nor `//` and that
 * both refusals below therefore wave through. Measured against Node 24 and Chromium on
 * 2026-08-15.
 *
 * `mainline_demo_api.static_site` refuses a backslash in a request path for the adjacent
 * reason (it is a separator on the platform this is developed on), so the two halves of
 * one origin now refuse the same character.
 */
const BACKSLASH = '\\';

/** The highest code point the URL parser strips or deletes: ASCII space. */
const LAST_STRIPPED_CODE_POINT = 0x20;

/**
 * Whether a candidate carries any C0 control or space, anywhere.
 *
 * Before the WHATWG parser decides anything it REMOVES every ASCII tab, LF and CR from its
 * input and STRIPS leading and trailing C0 controls and spaces. A candidate carrying one
 * therefore does not mean what it reads, and the two refusals below — which read the
 * string as written — can both be walked straight past:
 *
 *     " https://elsewhere.example"   parses absolute, though it starts with no scheme
 *     "\t//elsewhere.example"        parses protocol-relative, though it starts with no //
 *     "\u0000//elsewhere.example"  the same again, with a NUL in front
 *
 * All three were measured resolving to `https://elsewhere.example/` on 2026-08-15. None of
 * them could reach a fetch while `new URL(path, './bundle/')` still threw, so this closes
 * a hole that resolution would otherwise have opened — which is the whole reason it is
 * here. **A resolution change must not become an origin-policy change**, and a refusal
 * that only held by accident is not a policy anyone was enforcing.
 *
 * The cost is stated rather than hidden: a bundle directory whose name contains a literal
 * space cannot be named by `?bundle=`. It is refused BY NAME, and the build-time default —
 * which no stranger can send — is not subject to this rule at all.
 *
 * Written as a code-point scan rather than a character class: a regular expression over
 * this range puts a literal control byte in the source file, which `no-control-regex`
 * refuses and which no reviewer can see on the page.
 */
function carriesStrippedCharacter(candidate: string): boolean {
  for (const character of candidate) {
    if ((character.codePointAt(0) ?? 0) <= LAST_STRIPPED_CODE_POINT) return true;
  }
  return false;
}

/** Why a candidate was refused, or `null` when it is acceptable as a relative path. */
export function refuseRelativePath(candidate: string): string | null {
  if (candidate.trim() === '') {
    return `?${BUNDLE_PARAM}= was empty.`;
  }
  // Before the shape checks, never after: both of them read the candidate as written, and
  // these are the characters that make what is written differ from what is parsed.
  if (carriesStrippedCharacter(candidate)) {
    return (
      `?${BUNDLE_PARAM}=${JSON.stringify(candidate)} contains a space or a control character. ` +
      'URL parsing deletes tabs and newlines and trims leading control characters before it ' +
      'reads anything, so such a string does not resolve to what it appears to say — a leading ' +
      'space is enough to turn a name that looks relative into another origin. Refused by name ' +
      'rather than resolved and then inspected.'
    );
  }
  if (candidate.includes(BACKSLASH)) {
    return (
      `?${BUNDLE_PARAM}=${candidate} contains a backslash. URL parsing treats it as a path ` +
      'separator, so a leading pair resolves to another host exactly as a protocol-relative ' +
      'form does. Same refusal, same reason.'
    );
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

/**
 * A reader for a located bundle.
 *
 * The trailing slash and the resolution against `document.baseURI` both happen inside
 * `FetchBundleSource`, so callers need not care and — more to the point — cannot get them
 * differently. The source's `id` comes back as the ABSOLUTE URL that will be requested,
 * which is what the screen prints as `Source:`.
 *
 * Reached only for a `location` this module already accepted: a refused candidate is
 * `kind: 'none'` and returns `null` here, so nothing is ever constructed for it.
 */
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
