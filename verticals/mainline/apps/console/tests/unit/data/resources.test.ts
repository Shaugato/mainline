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
    expect(a.key).toBe('GET /v1/ledger?from_seq=0&site_code=BLK-07&to_seq=5');
  });

  it('builds a URL that matches the key it derived', () => {
    const resolved = resolveRequest({ resource: 'ledger', query: { site_code: 'BLK-07' } });
    expect(urlFor(resolved, 'https://kernel.test/')).toBe('https://kernel.test/v1/ledger?site_code=BLK-07');
    expect(urlFor(resolved, 'https://kernel.test')).toBe('https://kernel.test/v1/ledger?site_code=BLK-07');
  });
});

/**
 * The canonical request key is the ONLY thing a replay bundle is addressed by.
 *
 * `framePathForKey()` used to live in `src/data/resources.ts` and spelled the request
 * line into the frame's file name; these were its injectivity tests. The name is now a
 * content address computed by `scripts/capture-bundle.ts` (the encoding produced
 * 218-character paths that a default Windows install cannot check out — see
 * `scripts/submission/check_path_lengths.py`), so the property that has to hold moved
 * one level up with it: distinct requests must produce distinct KEYS, because a bundle
 * indexes frames by key and two requests sharing one key would share one answer.
 */
describe('the canonical request key is injective', () => {
  it('maps distinct requests to distinct keys', () => {
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
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('gives every declared resource a distinct key for the same parameters', () => {
    const seen = new Map<string, string>();
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
      const rival = seen.get(resolved.key);
      expect(rival, `${resource.key} and ${rival ?? ''} share the key ${resolved.key}`).toBeUndefined();
      seen.set(resolved.key, resource.key);
      expect(resolved.key, resource.key).toMatch(/^(?:GET|POST) \/v1\/[^\s]*$/);
    }
  });
});
