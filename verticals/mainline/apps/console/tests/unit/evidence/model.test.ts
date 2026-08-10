// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The evidence view's model — pure arithmetic, asserted against the committed bundle.
 *
 * The load-bearing test in this file is the ROUND TRIP, and it has moved rather than
 * gone. Frames used to be named by their request line under a `~XX` escape, and this
 * file decoded every committed name and re-encoded it. Names are now content addresses,
 * `<METHOD>-<sha256(key)[:16]>.json`, because the old scheme produced 218-character
 * repository paths that a default Windows install cannot check out (see
 * `scripts/submission/check_path_lengths.py`).
 *
 * `src/**` computes no digests, so the model can no longer re-derive a name — and this
 * file is the tree that is allowed to hash. It re-hashes every committed frame's
 * declared key with WebCrypto and asserts the committed file name matches, which is the
 * same round trip against the same real file names, checked from the one side that can
 * still check it.
 */

import { describe, expect, it } from 'vitest';

import type { BundleManifest } from '../../../src/data/bundle';
import { RESOURCES } from '../../../src/data/resources';
import {
  LIMITS,
  buildInventory,
  classifyBundlePath,
  isFrameAddress,
  keyFromManifestEntry,
  parseRequestKey,
  resourceForRequestKey,
  resourcesWithoutFrame,
  summarise,
  type DigestState,
  type InventoryRow,
} from '../../../src/features/evidence/model';

import { bundleFiles } from './_fixture';

function manifest(): BundleManifest {
  const bytes = bundleFiles().get('manifest.json');
  if (bytes === undefined) throw new Error('the fixture bundle has no manifest.json');
  return JSON.parse(new TextDecoder().decode(bytes)) as BundleManifest;
}

describe('classifyBundlePath', () => {
  it('names the four kinds by directory, and nothing else', () => {
    expect(classifyBundlePath('frames/GET-540549b3695a753c.json')).toBe('frame');
    expect(classifyBundlePath('ledger/bundle.json')).toBe('ledger');
    expect(classifyBundlePath('sql/merge-refused-23514.txt')).toBe('sql');
    expect(classifyBundlePath('manifest.json')).toBe('other');
    expect(classifyBundlePath('README.md')).toBe('other');
  });
});

/** The content address `scripts/capture-bundle.ts` writes, recomputed independently. */
async function contentAddressOf(key: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key));
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
  const method = key.slice(0, key.indexOf(' '));
  return `frames/${method}-${hex.slice(0, 16)}.json`;
}

describe('every committed frame is filed under the content address of its own key', () => {
  it('re-hashes EVERY frame in the committed bundle', async () => {
    const frames = manifest().files.filter((entry) => entry.path.startsWith('frames/'));
    expect(frames.length, 'the fixture carries no frames, so this assertion is vacuous').toBe(15);

    for (const entry of frames) {
      const key = keyFromManifestEntry(entry);
      expect(key, `${entry.path} declares no request key in the manifest`).not.toBeNull();
      expect(
        await contentAddressOf(key ?? ''),
        `${entry.path} is not the content address of ${key}`,
      ).toBe(entry.path);
    }
  });

  it('every committed frame name has the address SHAPE, and foreign names do not', () => {
    for (const entry of manifest().files.filter((e) => e.path.startsWith('frames/'))) {
      expect(isFrameAddress(entry.path), entry.path).toBe(true);
    }
    // The retired scheme, a wrong digest width, a wrong case and a non-frame.
    expect(isFrameAddress('frames/GET~20~2Fv1~2Faudit.json')).toBe(false);
    expect(isFrameAddress('frames/GET-540549b3695a75.json')).toBe(false);
    expect(isFrameAddress('frames/GET-540549B3695A753C.json')).toBe(false);
    expect(isFrameAddress('frames/PATCH-540549b3695a753c.json')).toBe(false);
    expect(isFrameAddress('ledger/bundle.json')).toBe(false);
  });

  it('reports a missing or empty key as null rather than guessing one from the name', () => {
    const base = { path: 'frames/GET-540549b3695a753c.json', sha256: 'a'.repeat(64), bytes: 1 };
    expect(keyFromManifestEntry(base)).toBeNull();
    expect(keyFromManifestEntry({ ...base, key: null })).toBeNull();
    expect(keyFromManifestEntry({ ...base, key: '' })).toBeNull();
    expect(keyFromManifestEntry({ ...base, key: 'GET /v1/audit' })).toBe('GET /v1/audit');
  });
});

describe('parseRequestKey', () => {
  it('splits method, path and sorted query', () => {
    expect(parseRequestKey('GET /v1/ledger?site_code=BLK-07')).toEqual({
      method: 'GET',
      path: '/v1/ledger',
      query: [['site_code', 'BLK-07']],
    });
    expect(parseRequestKey('POST /v1/permits/abc/merge')?.query).toEqual([]);
  });

  it('refuses anything that is not `METHOD /path`', () => {
    expect(parseRequestKey('')).toBeNull();
    expect(parseRequestKey('GET')).toBeNull();
    expect(parseRequestKey('PATCH /v1/permits/abc')).toBeNull();
    expect(parseRequestKey('GET v1/permits/abc')).toBeNull();
  });
});

describe('resourceForRequestKey', () => {
  it('matches templated paths, including the two-parameter one', () => {
    expect(resourceForRequestKey('GET /v1/permits/018f3a2f-1104-7c88-b3aa-77c1de40e2b1')?.key).toBe(
      'permit',
    );
    expect(
      resourceForRequestKey('GET /v1/permits/018f3a2f-1104-7c88-b3aa-77c1de40e2b1/blocking-checks')
        ?.key,
    ).toBe('blocking_checks');
    expect(resourceForRequestKey('GET /v1/clauses/abc/versions/def')?.key).toBe('clause_version');
    expect(resourceForRequestKey('POST /v1/permits/abc/checks:materialise')?.key).toBe(
      'materialise_checks',
    );
  });

  it('distinguishes the GET and the POST on the same path', () => {
    expect(resourceForRequestKey('GET /v1/checks/abc/disposition')?.key).toBe('disposition');
    expect(resourceForRequestKey('POST /v1/checks/abc/disposition')?.key).toBe('sign_disposition');
  });

  it('honours the declared query parameters', () => {
    expect(resourceForRequestKey('GET /v1/ledger?site_code=BLK-07')?.key).toBe('ledger');
    expect(resourceForRequestKey('GET /v1/ledger?nonsense=1')).toBeNull();
  });

  it('returns null for a request no declared resource can produce', () => {
    expect(resourceForRequestKey('GET /v1/not-a-resource')).toBeNull();
    expect(resourceForRequestKey('GET /v1/permits')).toBeNull();
  });

  it('reports the unowned endpoint as unowned rather than hiding it', () => {
    // ui.md §4: the ancestry read endpoint has no backend worker. The console renders
    // `owner: null` as a fact; a default of "kernel" here would invent an owner.
    const ancestry = resourceForRequestKey('GET /v1/clauses/abc/ancestry?as_of=deadbeef');
    expect(ancestry?.key).toBe('clause_ancestry');
    expect(ancestry?.owner).toBeNull();
  });
});

describe('buildInventory', () => {
  const rows = buildInventory(manifest());

  it('produces one row per listed file, in manifest order, all unchecked', () => {
    expect(rows).toHaveLength(21);
    expect(rows.map((row) => row.path)).toEqual(manifest().files.map((entry) => entry.path));
    for (const row of rows) {
      expect(row.state).toBe('unchecked');
      expect(row.actualDigest).toBeNull();
      expect(row.actualBytes).toBeNull();
    }
  });

  it('attaches frame facts to frames and to nothing else', () => {
    const ledger = rows.find((row) => row.path === 'ledger/bundle.json');
    expect(ledger?.frame).toBeNull();

    const permit = rows.find((row) =>
      row.frame?.requestKey === 'GET /v1/permits/018f3a2f-1104-7c88-b3aa-77c1de40e2b1',
    );
    expect(permit?.frame?.resourceKey).toBe('permit');
    expect(permit?.frame?.canonical).toBe(true);
    expect(permit?.frame?.owner).toBe('kernel');
  });

  it('carries the declared digest and byte count verbatim', () => {
    const note = rows.find((row) => row.path === 'ledger/checkpoint-000005.note');
    expect(note?.declaredDigest).toBe(
      '9e0b318f063bd109738f7dc3a6e117ce47b05073815ab1adda23b3fda4925d4b',
    );
    expect(note?.declaredBytes).toBe(177);
    expect(note?.mediaType).toBe('text/plain; charset=utf-8');
  });
});

describe('summarise — the conservation law', () => {
  const rows = buildInventory(manifest());

  it('counts an unaudited inventory as entirely unchecked, and balances', () => {
    const coverage = summarise(rows, null);
    expect(coverage.filesDeclared).toBe(21);
    expect(coverage.filesUnchecked).toBe(21);
    expect(coverage.digestsMatched).toBe(0);
    expect(coverage.bytesRead).toBe(0);
    expect(coverage.bytesDeclared).toBeGreaterThan(100_000);
    expect(coverage.framesDeclared).toBe(15);
    expect(coverage.framesNonCanonical).toBe(0);
    expect(coverage.framesUnaddressable).toBe(0);
    expect(coverage.resourcesDeclared).toBe(RESOURCES.size);
    expect(coverage.resourcesWithFrame).toBe(14);
    expect(coverage.conserved).toBe(true);
  });

  it('reports `unlisted` as null when the source could not enumerate itself', () => {
    // The difference between "none found" and "we cannot look" is the entire honesty
    // claim of the coverage panel; a default of [] would silently assert the stronger one.
    expect(summarise(rows, null).unlisted).toBeNull();
    expect(summarise(rows, []).unlisted).toEqual([]);
  });

  it('tallies all four states and still balances', () => {
    const states: DigestState[] = ['match', 'mismatch', 'unreadable', 'unchecked'];
    const mixed: InventoryRow[] = rows.map((row, index) => ({
      ...row,
      state: states[index % 4] ?? 'unchecked',
      actualBytes: index % 4 === 3 ? null : row.declaredBytes,
    }));
    const coverage = summarise(mixed, null);
    expect(
      coverage.digestsMatched +
        coverage.digestsMismatched +
        coverage.filesUnreadable +
        coverage.filesUnchecked,
    ).toBe(21);
    expect(coverage.conserved).toBe(true);
  });

  it('goes UNCONSERVED when a row carries a state the summary has never heard of', () => {
    // PL-2 for an invariant that cannot fail while the code is correct. The fifth-state
    // defect — somebody adds a DigestState and forgets a branch in summarise() — is
    // simulated here by injecting one, and the conservation law must catch it. If this
    // assertion ever passes with `true`, the equation on the coverage panel is
    // decoration and every count beside it is unaudited.
    const [first, ...rest] = rows;
    if (first === undefined) throw new Error('the fixture inventory is empty');
    const withUnknownState: InventoryRow[] = [
      { ...first, state: 'quarantined' as unknown as DigestState },
      ...rest,
    ];
    const coverage = summarise(withUnknownState, null);
    expect(coverage.conserved).toBe(false);
    expect(
      coverage.digestsMatched +
        coverage.digestsMismatched +
        coverage.filesUnreadable +
        coverage.filesUnchecked,
    ).toBe(20);
  });
});

describe('resourcesWithoutFrame', () => {
  it('names exactly the declared resources the committed bundle never captured', () => {
    const gaps = resourcesWithoutFrame(buildInventory(manifest()));
    expect(gaps.map((gap) => gap.key)).toEqual(['change_request', 'suspend_permit']);
    for (const gap of gaps) {
      expect(gap.purpose.length).toBeGreaterThan(20);
      expect(['GET', 'POST']).toContain(gap.method);
    }
  });

  it('is empty only when every declared resource has a frame', () => {
    const everyFrame = [...RESOURCES.values()].map((resource) => ({
      path: `frames/${resource.key}.json`,
      kind: 'frame' as const,
      declaredDigest: '0'.repeat(64),
      declaredBytes: 1,
      mediaType: null,
      frame: {
        requestKey: `${resource.method} ${resource.template}`,
        canonical: true,
        resourceKey: resource.key,
        owner: resource.owner,
        purpose: resource.purpose,
      },
      state: 'unchecked' as const,
      actualDigest: null,
      actualBytes: null,
      detail: null,
    }));
    expect(resourcesWithoutFrame(everyFrame)).toEqual([]);
  });
});

describe('LIMITS — the honesty panel is data so a test can hold it', () => {
  it('states at least four limits, each with a reason', () => {
    expect(LIMITS.length).toBeGreaterThanOrEqual(4);
    for (const limit of LIMITS) {
      expect(limit.claim.trim().length).toBeGreaterThan(20);
      expect(limit.why.trim().length).toBeGreaterThan(60);
    }
  });

  it('says out loud that the carried ledger is not verified here', () => {
    const joined = LIMITS.map((limit) => `${limit.claim} ${limit.why}`).join('\n').toLowerCase();
    expect(joined).toContain('custody');
    expect(joined).toContain('provenance, not truth');
  });
});
