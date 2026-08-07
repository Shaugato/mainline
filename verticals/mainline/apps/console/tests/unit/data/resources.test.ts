// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The canonical request key is the joint between the two transports. If it were not
 * injective, two different requests could name one frame and a bundle could answer a
 * question it was never asked — which is a fabricated screen with a plausible
 * explanation, and the whole design exists to make that impossible.
 */

import { describe, expect, it } from 'vitest';

import {
  RESOURCES,
  RESOURCE_KEYS,
  framePathForKey,
  resolveRequest,
  resourceOrThrow,
  urlFor,
} from '../../../src/data/resources';

const PERMIT_ID = '018f3a2f-1104-7c88-b3aa-77c1de40e2b1';

describe('the resource catalogue', () => {
  it('declares the kernel’s four POST endpoints and no others', () => {
    const posts = [...RESOURCES.values()].filter((resource) => resource.method === 'POST');
    expect(posts.map((resource) => resource.template).sort()).toEqual([
      '/v1/checks/{check_id}/disposition',
      '/v1/permits/{permit_id}/checks:materialise',
      '/v1/permits/{permit_id}/merge',
      '/v1/permits/{permit_id}/suspend',
    ]);
  });

  it('records that the ancestry read endpoint has no owner', () => {
    // docs/leads/ui.md §4. If somebody later assigns it, this test is the one line to
    // change — and changing it should be a visible decision, not a silent one.
    expect(resourceOrThrow('clause_ancestry').owner).toBeNull();
    const unowned = [...RESOURCES.values()].filter((resource) => resource.owner === null);
    expect(unowned.map((resource) => resource.key)).toEqual(['clause_ancestry']);
  });

  it('keeps RESOURCE_KEYS and RESOURCES in agreement', () => {
    expect([...RESOURCE_KEYS].sort()).toEqual([...RESOURCES.keys()].sort());
  });
});

describe('request resolution', () => {
  it('refuses a path parameter that could address a different resource', () => {
    expect(() =>
      resolveRequest({ resource: 'permit', path: { permit_id: `${PERMIT_ID}/../audit` } }),
    ).toThrow(/not an unreserved token/);
  });

  it('refuses a missing path parameter rather than interpolating a blank', () => {
    expect(() => resolveRequest({ resource: 'permit' })).toThrow(/requires path parameter "permit_id"/);
  });

  it('refuses an undeclared query parameter', () => {
    expect(() =>
      resolveRequest({
        resource: 'clause_ancestry',
        path: { clause_uuid: PERMIT_ID },
        query: { as_of: 'aa', depth: '3' },
      }),
    ).toThrow(/does not declare query parameter "depth"/);
  });

  it('refuses a body on a GET', () => {
    expect(() => resolveRequest({ resource: 'permit', path: { permit_id: PERMIT_ID }, body: {} })).toThrow(
      /cannot carry a body/,
    );
  });

  it('sorts the query so a key is stable regardless of the caller’s object order', () => {
    const a = resolveRequest({
      resource: 'ledger',
      query: { site_code: 'BLK-07', from_seq: '0', to_seq: '5' },
    });
    const b = resolveRequest({
      resource: 'ledger',
      query: { to_seq: '5', site_code: 'BLK-07', from_seq: '0' },
    });
    expect(a.key).toBe(b.key);
    expect(a.framePath).toBe(b.framePath);
    expect(a.key).toBe('GET /v1/ledger?from_seq=0&site_code=BLK-07&to_seq=5');
  });

  it('builds a URL that matches the key it derived', () => {
    const resolved = resolveRequest({ resource: 'ledger', query: { site_code: 'BLK-07' } });
    expect(urlFor(resolved, 'https://kernel.test/')).toBe('https://kernel.test/v1/ledger?site_code=BLK-07');
    expect(urlFor(resolved, 'https://kernel.test')).toBe('https://kernel.test/v1/ledger?site_code=BLK-07');
  });
});

describe('framePathForKey is injective', () => {
  it('maps distinct keys to distinct paths across the whole catalogue', () => {
    const keys = [
      'GET /v1/permits/a',
      'GET /v1/permits/a?x=1',
      'GET /v1/permits/a~x=1',
      'GET /v1/permits/a/blocking-checks',
      'POST /v1/permits/a/merge',
      'GET /v1/audit',
      'GET /v1/ledger?site_code=BLK-07',
      'GET /v1/ledger?site_code=BLK~2D07',
    ];
    const paths = keys.map(framePathForKey);
    expect(new Set(paths).size).toBe(keys.length);
  });

  it('escapes the escape character, so ~ in a key cannot collide with an encoded byte', () => {
    // '~' itself must not pass through, or "a~2Fb" and "a/b" would share a file.
    expect(framePathForKey('a~b')).not.toBe(framePathForKey('a/b'));
    expect(framePathForKey('a/b')).toBe('frames/a~2Fb.json');
    expect(framePathForKey('a~b')).toBe('frames/a~7Eb.json');
  });

  it('produces only characters the bundle contract admits in a path', () => {
    const pattern = /^frames\/[A-Za-z0-9._~-]+\.json$/;
    for (const resource of RESOURCES.values()) {
      const path: Record<string, string> = {};
      for (const name of resource.pathParams) path[name] = PERMIT_ID;
      const query: Record<string, string> = {};
      for (const name of resource.queryParams) query[name] = 'BLK-07';
      const resolved = resolveRequest({
        resource: resource.key,
        path,
        query,
        ...(resource.method === 'POST' ? { body: { probe: true } } : {}),
      });
      expect(resolved.framePath, resource.key).toMatch(pattern);
    }
  });
});
