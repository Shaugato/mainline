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
 */

import { describe, expect, it } from 'vitest';

import { FetchBundleSource } from '../../../src/data/bundle';
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
    // The id is what the screen renders as "read from"; a trailing slash is added so a
    // relative frame path resolves inside the directory rather than beside it.
    expect(source?.id).toBe('bundles/blk-07/');
  });
});

describe('isListable', () => {
  it('separates a source that can enumerate itself from one that cannot', () => {
    expect(isListable(new ListableMemorySource('l', bundleFiles()))).toBe(true);
    expect(isListable(new OpaqueMemorySource('o', bundleFiles()))).toBe(false);
    expect(isListable(new FetchBundleSource('bundles/blk-07'))).toBe(false);
  });
});
