// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Where the bundle comes from — and the one refusal that is a security property.
 *
 * `?bundle=` is a link, and a link is something a stranger can send. A console that
 * fetched, hashed and rendered an arbitrary cross-origin directory because a query
 * string said so would be a machine for producing authentic-looking screenshots of
 * somebody else's bytes under our chrome. The absolute-URL, protocol-relative and `..`
 * cases below are that refusal, and each asserts the REASON reaches the caller — a
 * refusal a reader cannot read is a blank screen.
 *
 * ── WHAT 2026-08-15 ADDED, AND WHY IT IS HERE RATHER THAN SOMEWHERE MILDER ───────
 *
 * `FetchBundleSource` now resolves its base against `document.baseURI`, because the
 * deployed build compiles the relative `./bundle/` and `new URL(path, base)` requires an
 * absolute base — the Evidence screen was rendering `Invalid base URL` where an inventory
 * belonged. That fix removes an accident: several candidates reach ANOTHER ORIGIN without
 * starting with a scheme or with `//` (a backslash pair, a leading space, a tab, a NUL),
 * and every one of them was stopped only because the constructor threw first. The vectors
 * are asserted twice below — once that they really do escape, once that they are refused
 * by name — so the refusal is a policy rather than a side effect, and the order (refuse
 * the RAW candidate, resolve afterwards) is asserted on its own.
 */

import { describe, expect, it } from 'vitest';

import { FetchBundleSource, documentBaseUrl, resolveBundleBase } from '../../../src/data/bundle';
import {
  BUNDLE_PARAM,
  bundleSourceFor,
  isListable,
  paramsFromLocation,
  refuseRelativePath,
  resolveBundleLocation,
} from '../../../src/features/evidence/source';

import { ListableMemorySource, OpaqueMemorySource, bundleFiles } from './_fixture';

const params = (query: string): URLSearchParams => new URLSearchParams(query);

describe('resolveBundleLocation', () => {
  it('takes a same-origin relative path from the address', () => {
    const location = resolveBundleLocation(params(`${BUNDLE_PARAM}=fixtures/bundles/blk-07`), {});
    expect(location.kind).toBe('url');
    expect(location.kind === 'url' ? location.url : '').toBe('fixtures/bundles/blk-07');
    expect(location.why).toContain(BUNDLE_PARAM);
  });

  it('REFUSES an absolute URL and says why', () => {
    const location = resolveBundleLocation(
      params(`${BUNDLE_PARAM}=https://elsewhere.example/bundle`),
      {},
    );
    expect(location.kind).toBe('none');
    expect(location.why).toContain('absolute URL');
    expect(location.why).toContain('will not fetch');
  });

  it('REFUSES a protocol-relative host', () => {
    const location = resolveBundleLocation(params(`${BUNDLE_PARAM}=//elsewhere.example/b`), {});
    expect(location.kind).toBe('none');
    expect(location.why).toContain('protocol-relative');
  });

  it('REFUSES a path with a `..` segment', () => {
    const location = resolveBundleLocation(params(`${BUNDLE_PARAM}=a/../../etc`), {});
    expect(location.kind).toBe('none');
    expect(location.why).toContain('".." segment');
  });

  it('REFUSES an empty parameter rather than silently falling back to the build default', () => {
    // Falling back would mean a reader who typed `?bundle=` saw the shipped bundle and
    // believed they were looking at the one they named.
    const location = resolveBundleLocation(params(`${BUNDLE_PARAM}=`), {
      VITE_MAINLINE_BUNDLE_URL: './bundles/demo',
    });
    expect(location.kind).toBe('none');
    expect(location.why).toContain('was empty');
  });

  it('falls back to the build-time default, which MAY be absolute', () => {
    const location = resolveBundleLocation(params(''), {
      VITE_MAINLINE_BUNDLE_URL: 'https://demo.example/bundles/blk-07',
    });
    expect(location.kind).toBe('url');
    expect(location.kind === 'url' ? location.url : '').toBe('https://demo.example/bundles/blk-07');
    expect(location.why).toContain('build-time default');
  });

  it('says which of the several possible nothings it is', () => {
    const location = resolveBundleLocation(params(''), {});
    expect(location.kind).toBe('none');
    expect(location.why).toContain('VITE_MAINLINE_BUNDLE_URL');
    expect(location.why).toContain('a fact about this deployment');
  });

  it('lets the address win over the build default', () => {
    const location = resolveBundleLocation(params(`${BUNDLE_PARAM}=other/bundle`), {
      VITE_MAINLINE_BUNDLE_URL: './bundles/demo',
    });
    expect(location.kind === 'url' ? location.url : '').toBe('other/bundle');
  });
});

describe('refuseRelativePath', () => {
  it('accepts the shapes a bundle directory actually takes', () => {
    expect(refuseRelativePath('bundles/blk-07')).toBeNull();
    expect(refuseRelativePath('./bundles/blk-07/')).toBeNull();
    expect(refuseRelativePath('/bundles/blk-07')).toBeNull();
    expect(refuseRelativePath('a.b/c-d_e')).toBeNull();
  });

  it('refuses every scheme, not only http', () => {
    for (const candidate of [
      'javascript:alert(1)',
      'data:application/json,{}',
      'file:///etc/passwd',
      'HTTPS://elsewhere.example/b',
    ]) {
      expect(refuseRelativePath(candidate), candidate).not.toBeNull();
    }
  });

  /**
   * The forms that reach another origin WITHOUT starting with a scheme or with `//`.
   *
   * Each one was measured resolving to `https://elsewhere.example/` against a same-origin
   * base, and each one walks straight past a refusal that reads the string as written.
   * They could not reach a fetch while `new URL(path, './bundle/')` still threw, so the
   * refusal that stopped them was an accident of a defect rather than a policy — and the
   * moment that defect was fixed, this became the check that keeps the stated policy
   * ("a same-origin, relative location") true in fact as well as in prose.
   *
   * The assertion below is the whole point: the resolution these vectors were aiming at
   * is IMPOSSIBLE, because `resolveBundleLocation` refuses them and therefore
   * `bundleSourceFor` never constructs anything to resolve.
   */
  it('REFUSES the forms that reach another origin without a scheme or a leading //', () => {
    const base = 'https://console.example/app/';
    const vectors = [
      '\\\\elsewhere.example',
      '\\/elsewhere.example',
      '/\\elsewhere.example',
      ' https://elsewhere.example',
      '\thttps://elsewhere.example',
      '\t//elsewhere.example',
      '\n//elsewhere.example',
      '\u0000//elsewhere.example',
    ];
    for (const candidate of vectors) {
      // First: the vector really does escape, so this test cannot pass by being wrong
      // about the danger. `resolveBundleBase` is what a source would do with it.
      const resolved = resolveBundleBase(candidate, base);
      expect(resolved.url, `${JSON.stringify(candidate)} was expected to escape`).toContain(
        'elsewhere.example',
      );

      // Then: it is refused by name, before any of that can happen.
      expect(refuseRelativePath(candidate), JSON.stringify(candidate)).not.toBeNull();

      // And the refusal is what the address resolver returns, so no source exists.
      const location = resolveBundleLocation(
        new URLSearchParams([[BUNDLE_PARAM, candidate]]),
        { VITE_MAINLINE_BUNDLE_URL: './bundle/' },
      );
      expect(location.kind, JSON.stringify(candidate)).toBe('none');
      expect(bundleSourceFor(location)).toBeNull();
    }
  });

  it('names the backslash and the control character separately, so a reader can act', () => {
    expect(refuseRelativePath('\\\\elsewhere.example')).toContain('backslash');
    expect(refuseRelativePath(' https://elsewhere.example')).toContain('control character');
  });
});

/**
 * REFUSE FIRST, RESOLVE SECOND.
 *
 * `FetchBundleSource` resolves its base against `document.baseURI` in its constructor —
 * that is what makes the deployed build's `./bundle/` a legal value. The ordering is a
 * security property: the refusal runs on the RAW candidate, so a candidate that would
 * resolve to somebody else's origin is never resolved at all rather than resolved and then
 * inspected.
 */
describe('the order of the refusal and the resolution', () => {
  it('refuses `..` on the raw candidate — before any base is consulted', () => {
    // `a/../../etc` against `https://console.example/app/` resolves to
    // `https://console.example/etc`, which is same-origin and would therefore survive any
    // check made AFTER resolution. It does not survive this one.
    const escaped = resolveBundleBase('a/../../etc', 'https://console.example/app/');
    expect(escaped.url).toBe('https://console.example/etc/');

    const location = resolveBundleLocation(params(`${BUNDLE_PARAM}=a/../../etc`), {});
    expect(location.kind).toBe('none');
    expect(location.why).toContain('".." segment');
    expect(bundleSourceFor(location)).toBeNull();
  });

  it('constructs no source at all for a refused candidate', () => {
    for (const candidate of ['https://elsewhere.example/b', '//elsewhere.example/b', 'a/../b']) {
      const location = resolveBundleLocation(
        new URLSearchParams([[BUNDLE_PARAM, candidate]]),
        { VITE_MAINLINE_BUNDLE_URL: 'https://demo.example/bundles/blk-07' },
      );
      expect(location.kind, candidate).toBe('none');
      // Not even the build-time default: a reader who named a bundle must not be shown a
      // different one and believe it was theirs.
      expect(bundleSourceFor(location), candidate).toBeNull();
    }
  });
});

/**
 * The one-line defect that put a raw JavaScript exception on the deployed Evidence screen.
 *
 * `new URL(path, base)` REQUIRES an absolute `base`. The demo artefact compiles
 * `VITE_MAINLINE_BUNDLE_URL:'./bundle/'` — relative on purpose, so the build names no
 * hostname — and the constructor therefore threw `Failed to construct 'URL': Invalid base
 * URL` before a single request was attempted, while `GET /bundle/manifest.json` was
 * answering 200 with 8 435 B from the same origin.
 */
describe('resolveBundleBase', () => {
  it('resolves the RELATIVE location the demo build actually compiles', () => {
    const resolved = resolveBundleBase('./bundle/', 'https://demo.example/');
    expect(resolved.url).toBe('https://demo.example/bundle/');
    expect(resolved.why).toBeNull();
  });

  it('resolves against a hash-routed address, which is where the console lives', () => {
    // The deployed console is hash-routed, so `document.baseURI` carries a fragment. The
    // fragment is not part of the base path and must not become part of the bundle URL.
    expect(resolveBundleBase('./bundle/', 'https://demo.example/#/evidence').url).toBe(
      'https://demo.example/bundle/',
    );
    expect(resolveBundleBase('./bundle/', 'https://demo.example/sub/index.html#/evidence').url).toBe(
      'https://demo.example/sub/bundle/',
    );
  });

  it('adds the trailing slash, so a file resolves INSIDE the directory and not beside it', () => {
    const resolved = resolveBundleBase('bundles/blk-07', 'https://demo.example/');
    expect(resolved.url).toBe('https://demo.example/bundles/blk-07/');
    expect(new URL('manifest.json', resolved.url ?? '').toString()).toBe(
      'https://demo.example/bundles/blk-07/manifest.json',
    );
  });

  it('leaves an absolute location alone and consults no base for it', () => {
    // The build-time default MAY be absolute — the operator who set it built the artefact.
    expect(resolveBundleBase('https://cdn.example/b/', 'https://demo.example/').url).toBe(
      'https://cdn.example/b/',
    );
    expect(resolveBundleBase('https://cdn.example/b/', null).url).toBe('https://cdn.example/b/');
  });

  it('reports a relative location with no base as unresolved, with the reason, not a throw', () => {
    const resolved = resolveBundleBase('./bundle/', null);
    expect(resolved.url).toBeNull();
    expect(resolved.configured).toBe('./bundle/');
    expect(resolved.why).toContain('relative location');
    expect(resolved.why).toContain('document.baseURI');
  });

  /**
   * THE THREE SHAPES `.env.demo` SAYS THE RELATIVE VALUE EXISTS FOR.
   *
   * `VITE_MAINLINE_BUNDLE_URL=./bundle/` is relative ON PURPOSE, so the built artefact
   * names no hostname and the same bytes run from a bucket root, from a sub-path and from a
   * local file. Two of the three were already asserted above; `file://` was not, and it is
   * the one a reviewer opening `dist/index.html` from their downloads folder actually
   * meets. All three are asserted together so that a future change to the resolution cannot
   * fix one deployment by breaking another.
   */
  it('resolves the same relative value from a bucket root, a sub-path and file://', () => {
    expect(resolveBundleBase('./bundle/', 'https://demo.example/').url).toBe(
      'https://demo.example/bundle/',
    );
    expect(resolveBundleBase('./bundle/', 'https://demo.example/console/v3/').url).toBe(
      'https://demo.example/console/v3/bundle/',
    );
    const local = resolveBundleBase('./bundle/', 'file:///C:/Users/reviewer/dist/index.html');
    expect(local.url).toBe('file:///C:/Users/reviewer/dist/bundle/');
    expect(local.why).toBeNull();
  });
});

/**
 * THE WHOLE PATH THE DEPLOYED BUILD TAKES, IN ONE CASE.
 *
 * The screenshot the founder sent read *"Could not read manifest.json — Failed to construct
 * 'URL': Invalid base URL"*, and the path that produced it is exactly this one: no
 * `?bundle=` in the address, `VITE_MAINLINE_BUNDLE_URL` compiled as the relative `./bundle/`,
 * `resolveBundleLocation` accepting it, `bundleSourceFor` constructing the source, and the
 * first `read('manifest.json')` throwing before a request was ever made. Each link in that
 * chain is asserted elsewhere in this file; this case walks all of them in order, because
 * the defect lived in the JOIN and not in any one of them.
 *
 * `GET /bundle/manifest.json` answered 200 with 8 435 B from the live origin on 2026-08-15,
 * which is why the console reading it is the correct fix and suppressing the error is not.
 */
describe('the deployed build’s own path: a relative default, end to end', () => {
  it('resolves ./bundle/ to an absolute request and reads the manifest through it', async () => {
    const location = resolveBundleLocation(new URLSearchParams(), {
      VITE_MAINLINE_BUNDLE_URL: './bundle/',
    });
    expect(location.kind).toBe('url');
    expect(location.why).toContain('VITE_MAINLINE_BUNDLE_URL');

    const requested: string[] = [];
    const source = bundleSourceFor(location, (input: RequestInfo | URL) => {
      // `FetchBundleSource` passes the absolute string it built; a `Request` or a `URL` would
      // stringify to something a reader could not compare, so the shape is asserted here
      // rather than flattened.
      expect(typeof input).toBe('string');
      requested.push(
        input instanceof URL ? input.href : typeof input === 'string' ? input : input.url,
      );
      return Promise.resolve(new Response('{"files":[]}', { status: 200 }));
    });
    expect(source).not.toBeNull();

    const base = documentBaseUrl();
    expect(base).not.toBeNull();
    expect(source?.id).toBe(new URL('./bundle/', base ?? '').toString());

    const bytes = await source?.read('manifest.json');
    expect(new TextDecoder().decode(bytes)).toBe('{"files":[]}');
    expect(requested).toEqual([`${source?.id ?? ''}manifest.json`]);
    expect(requested[0]?.startsWith('http')).toBe(true);
  });
});

describe('FetchBundleSource, once resolution is its own job', () => {
  it('reports the ABSOLUTE url it will request as its id — the thing the screen prints', () => {
    const source = new FetchBundleSource('./bundle/');
    const base = documentBaseUrl();
    expect(base).not.toBeNull();
    expect(source.id).toBe(new URL('./bundle/', base ?? '').toString());
    expect(source.id.startsWith('http')).toBe(true);
  });

  it('names the request and the verbatim status when the manifest is not there', async () => {
    const source = new FetchBundleSource('./bundle/', () =>
      Promise.resolve(new Response('', { status: 404, statusText: 'Not Found' })),
    );
    await expect(source.read('manifest.json')).rejects.toThrow(
      `GET ${source.id}manifest.json → HTTP 404 Not Found`,
    );
  });

  it('names the request when the fetch itself does not complete', async () => {
    const source = new FetchBundleSource('./bundle/', () =>
      Promise.reject(new TypeError('Failed to fetch')),
    );
    await expect(source.read('manifest.json')).rejects.toThrow(
      /GET http.*manifest\.json → the request did not complete: TypeError: Failed to fetch/,
    );
  });
});

describe('paramsFromLocation', () => {
  it('merges both query positions, with the hash winning', () => {
    const merged = paramsFromLocation('?bundle=from-search&seed=1', '#/evidence?bundle=from-hash');
    expect(merged.get('bundle')).toBe('from-hash');
    expect(merged.get('seed')).toBe('1');
  });

  it('handles a hash with no query and a missing search', () => {
    expect(paramsFromLocation('', '#/evidence').get('bundle')).toBeNull();
    expect(paramsFromLocation('?bundle=x', '').get('bundle')).toBe('x');
  });
});

describe('bundleSourceFor', () => {
  it('returns null when there is nowhere to read from', () => {
    expect(bundleSourceFor({ kind: 'none', why: 'nothing configured' })).toBeNull();
  });

  it('builds a fetch source for a located bundle', () => {
    const source = bundleSourceFor({ kind: 'url', url: 'bundles/blk-07', why: 'test' });
    expect(source).toBeInstanceOf(FetchBundleSource);
    // The id is what the screen renders as "read from", and since 2026-08-15 it is the
    // ABSOLUTE url that will actually be requested rather than the relative string that
    // was configured — a reader comparing the screen against a `curl` needs one value, not
    // two. The trailing slash is still added so a file resolves inside the directory
    // rather than beside it.
    expect(source?.id).toBe(new URL('bundles/blk-07/', documentBaseUrl() ?? '').toString());
    expect(source?.id.endsWith('/bundles/blk-07/')).toBe(true);
  });
});

describe('isListable', () => {
  it('separates a source that can enumerate itself from one that cannot', () => {
    expect(isListable(new ListableMemorySource('l', bundleFiles()))).toBe(true);
    expect(isListable(new OpaqueMemorySource('o', bundleFiles()))).toBe(false);
    expect(isListable(new FetchBundleSource('bundles/blk-07'))).toBe(false);
  });
});
