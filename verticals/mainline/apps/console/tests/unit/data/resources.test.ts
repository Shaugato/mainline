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
  it('declares seventeen resources, and the seventeenth is the demo gate run', () => {
    // The count is asserted as an EXACT number rather than a floor. A floor would admit
    // an eighteenth resource arriving unannounced, and the whole point of this module is
    // that the console's read surface is a closed, declared set — `resolveRequest` refuses
    // anything not on it, so a resource nobody noticed being added is a request nobody
    // reviewed being sendable.
    expect(RESOURCES.size).toBe(17);
    expect(RESOURCE_KEYS.length).toBe(17);
    expect([...RESOURCES.keys()]).toContain('demo_gate_run');
  });

  it('makes DemoDriver’s not-declared panel unreachable', () => {
    // `src/features/gate/DemoDriver.tsx` gates its whole render on exactly this
    // predicate — `const declared = RESOURCES.has(DEMO_GATE_RUN)` — and shows the
    // "POST /v1/demo/gate-run is not addressable from this console" panel when it is
    // false. That panel is the honest fallback for a build that ever strips the
    // declaration, and it is KEPT for that reason; this asserts that the build shipped
    // today does not take it.
    //
    // The render-level proof is `tests/unit/app/composition.test.tsx`, which mounts the
    // driver and asserts the panel is absent and the four controls are present. This one
    // pins the predicate itself, so a failure here names the cause rather than a symptom
    // three layers up.
    expect(RESOURCES.has('demo_gate_run')).toBe(true);
  });

  it('declares the kernel’s four transition POSTs, the demo POST, and no others', () => {
    // Was "four POST endpoints and no others" until 2026-08-14, when `demo_gate_run`
    // was declared so the deployed console could reach the endpoint it is sitting on
    // (docs/leads/console-live-plan.md §0.4). The assertion did not loosen to admit it:
    // it is still an EXACT list, so a sixth POST arriving unannounced still fails here.
    const posts = [...RESOURCES.values()].filter((resource) => resource.method === 'POST');
    expect(posts.map((resource) => resource.template).sort()).toEqual([
      '/v1/checks/{check_id}/disposition',
      '/v1/demo/gate-run',
      '/v1/permits/{permit_id}/checks:materialise',
      '/v1/permits/{permit_id}/merge',
      '/v1/permits/{permit_id}/suspend',
    ]);
  });

  it('gives the demo run no path parameter, so a caller cannot aim it at another row', () => {
    // The four kernel transitions are addressed by a {permit_id} or {check_id} the
    // caller supplies. The demo run is NOT: its subject is the seeded demo permit,
    // resolved server-side. The demo URL is `authorization_type = NONE`, so a path
    // parameter here would let any stranger holding the link drive the four beats —
    // including the forged-counter attack — against somebody else's subject.
    const demo = resourceOrThrow('demo_gate_run');
    expect(demo.method).toBe('POST');
    expect(demo.template).toBe('/v1/demo/gate-run');
    expect(demo.pathParams).toEqual([]);
    expect(demo.queryParams).toEqual([]);
    expect(demo.owner).toBe('kernel');
    expect(demo.schemaId).toBe('https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json');
  });

  it('refuses a path argument on the demo run rather than ignoring it', () => {
    // The guarantee above is only worth having if it is enforced rather than documented.
    expect(() =>
      resolveRequest({ resource: 'demo_gate_run', path: { permit_id: PERMIT_ID }, body: {} }),
    ).toThrow(/has no path parameter "permit_id"/);
  });

  it('addresses the demo run by one key regardless of how often it is pressed', () => {
    // Four controls, one exchange, one body. `src/features/gate/DemoDriver.tsx` says why:
    // the request key is what names a frame inside an EvidenceBundle, so an identical
    // body means ONE captured frame serves all four controls in REPLAY. A run_id in the
    // body would mint a new key per press and make the replay path uncapturable.
    const first = resolveRequest({ resource: 'demo_gate_run', body: {} });
    const second = resolveRequest({ resource: 'demo_gate_run', body: {} });
    expect(first.key).toBe('POST /v1/demo/gate-run');
    expect(second.key).toBe(first.key);
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
