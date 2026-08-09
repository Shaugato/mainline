// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CUSTODY SCREEN, THROUGH THE REAL TRANSPORT AND THE REAL VERIFIER.
 *
 * This file lives under `tests/unit/verify/` rather than `tests/unit/custody/` because
 * file ownership in this repository is absolute and `tests/unit/custody/` belongs to
 * nobody: creating it would be a path outside this worker's allocation. The subject is the
 * custody surface; the location is an ownership fact, not a taxonomy claim.
 *
 * Four claims are only provable here, end to end:
 *
 *   1. **A green seal is green because arithmetic ran.** The bundle's ledger frame is
 *      replaced with `tests/vectors/ledger-payload.json` — cryptographically real, down to
 *      an ECDSA P-256 signature made with the key published in `spec/wire/checkpoint.md`
 *      §7.1 — and the screen shows PASS with the recomputed digest beside it.
 *   2. **One byte, and it goes red.** The same bundle with one canon byte flipped and the
 *      manifest re-sealed renders a FAILED seal and the leaf that disagreed.
 *   3. **The staged demo fixture fails, and the screen says so.** Its own
 *      `ledger/bundle.json` says running a verifier against it MUST fail. No allowlist.
 *   4. **The split-view limit renders as literal text**, from the exported constant, on a
 *      screen that has just shown a passing quorum check.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import {
  BundleTransport,
  MemoryBundleSource,
  type BundleManifest,
} from '../../../src/data/bundle';
import { createContractRegistry } from '../../../src/data/contracts';
import { toBase64, toHex, utf8 } from '../../../src/verify/bytes';
import { InBrowserBundleVerifier } from '../../../src/verify/bundle-verifier';
import { InlineVerifier } from '../../../src/verify/client';
import { NO_ANCHOR, operatorConfig } from '../../../src/verify/config';
import { SPLIT_VIEW_LIMIT } from '../../../src/verify/ledger';
import { sha256Sync } from '../../../src/verify/sha256';
import { CustodyRoot } from '../../../src/features/custody/CustodyRoot';
import { surface } from '../../../src/features/custody/surface';
import {
  CustodyConfigContext,
  CustodyTransportContext,
  CustodyVerifierContext,
} from '../../../src/features/custody/transport-context';

import { ledgerPayloadVector } from './_vectors';

const RAW = import.meta.glob<string>('/fixtures/bundles/blk-07/**/*', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const BUNDLE_ROOT = '/fixtures/bundles/blk-07/';
const LEDGER_FRAME = 'frames/GET~20~2Fv1~2Fledger~3Fsite_code~3DBLK-07.json';
const vector = ledgerPayloadVector();

function bundleFiles(): Map<string, Uint8Array> {
  const files = new Map<string, Uint8Array>();
  for (const [key, text] of Object.entries(RAW)) {
    if (!key.startsWith(BUNDLE_ROOT)) continue;
    const path = key.slice(BUNDLE_ROOT.length);
    if (path === 'manifest.seed.json') continue;
    files.set(path, utf8(text));
  }
  if (files.size === 0) throw new Error('no fixture bundle files were globbed');
  return files;
}

function decode(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes);
}

/**
 * Replace a frame's response body and RE-SEAL the manifest.
 *
 * Re-sealing is what makes the substitution honest: the bundle that results is internally
 * consistent, so it exercises the verifier's cryptography rather than its error handling.
 * The tamper tests then break exactly one byte AFTER sealing, which is the only way to
 * make the digest check the thing under test.
 */
function withFrameBody(
  files: Map<string, Uint8Array>,
  framePath: string,
  bodyText: string,
): Map<string, Uint8Array> {
  const frameBytes = files.get(framePath);
  if (frameBytes === undefined) throw new Error(`${framePath} is not in the fixture bundle`);
  const frame = JSON.parse(decode(frameBytes)) as Record<string, unknown>;
  const response = frame.response as Record<string, unknown>;
  frame.response = { ...response, body_b64: toBase64(utf8(bodyText)) };

  const next = new Map(files);
  next.set(framePath, utf8(JSON.stringify(frame)));
  return reseal(next);
}

/** Recompute every manifest digest and length over the current bytes. */
function reseal(files: Map<string, Uint8Array>): Map<string, Uint8Array> {
  const manifestBytes = files.get('manifest.json');
  if (manifestBytes === undefined) throw new Error('the fixture bundle has no manifest.json');
  const manifest = JSON.parse(decode(manifestBytes)) as BundleManifest;

  const sealed = {
    ...manifest,
    files: manifest.files.map((entry) => {
      const bytes = files.get(entry.path);
      if (bytes === undefined) throw new Error(`manifest lists ${entry.path}, which is absent`);
      return { ...entry, sha256: toHex(sha256Sync(bytes)), bytes: bytes.byteLength };
    }),
  };

  const next = new Map(files);
  next.set('manifest.json', utf8(JSON.stringify(sealed, null, 2)));
  return next;
}

/** Flip one byte of a file WITHOUT re-sealing. This is what tampering looks like. */
function tamper(files: Map<string, Uint8Array>, path: string): Map<string, Uint8Array> {
  const bytes = files.get(path);
  if (bytes === undefined) throw new Error(`${path} is not in the bundle`);
  const copy = new Uint8Array(bytes);
  const index = Math.floor(copy.length / 2);
  copy[index] = (copy[index] ?? 0) ^ 0x01;
  const next = new Map(files);
  next.set(path, copy);
  return next;
}

function transportFor(files: ReadonlyMap<string, Uint8Array>): BundleTransport {
  return new BundleTransport({
    source: new MemoryBundleSource('custody-screen-test', files),
    registry: createContractRegistry(),
    verifier: new InBrowserBundleVerifier({
      verifier: new InlineVerifier('unit test — jsdom has no Worker'),
      config: NO_ANCHOR,
    }),
  });
}

function mount(files: ReadonlyMap<string, Uint8Array>, anchored: boolean): void {
  render(
    <CustodyTransportContext.Provider value={transportFor(files)}>
      <CustodyVerifierContext.Provider value={new InlineVerifier('unit test — jsdom has no Worker')}>
        <CustodyConfigContext.Provider
          value={anchored ? operatorConfig(vector.vkey, vector.canon_src_sha256) : NO_ANCHOR}
        >
          <CustodyRoot />
        </CustodyConfigContext.Provider>
      </CustodyVerifierContext.Provider>
    </CustodyTransportContext.Provider>,
  );
}

/** The bundle with the cryptographically real ledger payload in place of the staged one. */
function realBundle(): Map<string, Uint8Array> {
  return withFrameBody(bundleFiles(), LEDGER_FRAME, JSON.stringify(vector.envelope));
}

afterEach(() => {
  window.location.hash = '';
});

describe('the surface registers itself honestly', () => {
  it('declares the id its directory requires, in the EVIDENCE register', () => {
    expect(surface.id).toBe('custody');
    expect(surface.path).toBe('/custody');
    expect(surface.register).toBe('evidence');
    expect(surface.milestone).toBe('K2');
  });
});

describe('with no transport, it says so and shows nothing else', () => {
  it('renders the NO SOURCE panel rather than an empty screen', () => {
    render(<CustodyRoot />);
    expect(screen.getByTestId('custody-no-source')).toBeInTheDocument();
    expect(screen.queryByTestId('custody-checks')).not.toBeInTheDocument();
  });
});

describe('a green seal is green because arithmetic ran', () => {
  it('recomputes the ledger and passes the checks the vector names', async () => {
    mount(realBundle(), true);

    await waitFor(
      () => {
        expect(screen.getByTestId('custody-checks')).toBeInTheDocument();
      },
      { timeout: 5000 },
    );

    for (const name of vector.expect.pass) {
      const seal = await screen.findByTestId(`seal-${name}`);
      expect(seal.getAttribute('data-state'), name).toBe('verified');
    }
  });

  it('shows the bytes hashed, the digest and the comparison', async () => {
    mount(realBundle(), true);
    const table = await screen.findByTestId('recomputation-leaf_hash_recomputation', undefined, {
      timeout: 5000,
    });
    // The published leaf hash of seq 0, from spec/wire/checkpoint.md §7.2 via the vectors.
    const leaf = vector.envelope.data.leaves[0];
    expect(leaf).toBeDefined();
    expect(table.textContent).toContain(leaf?.leaf_hash_hex ?? 'missing');
    expect(table.textContent).toContain('SHA-256(0x00');
    expect(table.textContent).toContain('agrees');
  });

  it('is BOUNDED overall, never clean, and says which checks were not run', async () => {
    mount(realBundle(), true);
    const summary = await screen.findByTestId('custody-summary', undefined, { timeout: 5000 });
    expect(summary.textContent).toContain('NOT RUN');
    expect(screen.getByTestId('custody-overall-seal').getAttribute('data-state')).toBe('unverified');
  });

  it('names every deferred check instead of omitting it', async () => {
    mount(realBundle(), true);
    await screen.findByTestId('custody-checks', undefined, { timeout: 5000 });
    for (const name of vector.expect.skip) {
      expect(screen.getByTestId(`seal-${name}`).getAttribute('data-state'), name).toBe('unverified');
    }
  });
});

describe('one byte, and the seal goes red — and the frame is blocked', () => {
  it('fails the leaf hash check when a canon byte is changed and the bundle re-sealed', async () => {
    const files = bundleFiles();
    const mutated = JSON.parse(JSON.stringify(vector.envelope)) as {
      data: { leaves: Record<string, unknown>[] };
    };
    const leaf = mutated.data.leaves[3];
    if (leaf === undefined) throw new Error('the vector is truncated');
    const canon = decode(utf8(atob(String(leaf.canon_bytes_b64))));
    leaf.canon_bytes_b64 = toBase64(utf8(canon.replace('"controlled"', '"uncontrolled"')));

    mount(withFrameBody(files, LEDGER_FRAME, JSON.stringify(mutated)), true);

    const seal = await screen.findByTestId('seal-leaf_hash_recomputation', undefined, {
      timeout: 5000,
    });
    expect(seal.getAttribute('data-state')).toBe('failed');
    expect(screen.getByTestId('custody-overall-seal').getAttribute('data-state')).toBe('failed');
  });

  it('blocks the frame entirely when a byte is flipped WITHOUT re-sealing', async () => {
    mount(tamper(realBundle(), LEDGER_FRAME), true);

    const failure = await screen.findByTestId('custody-transport-failure', undefined, {
      timeout: 5000,
    });
    expect(failure.textContent).toContain('file-digest');
    expect(failure.textContent).toContain('These are not the bytes that were sealed.');
    // Nothing was rendered from bundle bytes: there is no check list at all.
    expect(screen.queryByTestId('custody-checks')).not.toBeInTheDocument();
  });
});

describe('the staged demo fixture fails, and the screen says why', () => {
  it('renders a failed leaf-hash seal over the hand-authored payload', async () => {
    mount(bundleFiles(), false);
    const seal = await screen.findByTestId('seal-leaf_hash_recomputation', undefined, {
      timeout: 5000,
    });
    expect(seal.getAttribute('data-state')).toBe('failed');
    expect(screen.getByTestId('custody-checks').textContent).toContain(
      'do not hash to the value recorded against them',
    );
  });
});

describe('the honest limits are literal text on the screen', () => {
  it('renders the split-view sentence verbatim, from the exported constant', async () => {
    mount(realBundle(), true);
    const limit = await screen.findByTestId('split-view-limit', undefined, { timeout: 5000 });
    expect(limit.textContent).toContain(SPLIT_VIEW_LIMIT);
  });

  it('renders it beside a quorum check that PASSED, which is the point', async () => {
    mount(realBundle(), true);
    const seal = await screen.findByTestId('seal-witness_quorum', undefined, { timeout: 5000 });
    expect(seal.getAttribute('data-state')).toBe('verified');
    expect(screen.getByTestId('bounded-witness_quorum').textContent).toContain(SPLIT_VIEW_LIMIT);
  });

  it('shows the checkpoint note verbatim, em dash and all', async () => {
    mount(realBundle(), true);
    const notes = await screen.findAllByTestId('checkpoint-note', undefined, { timeout: 5000 });
    const head = vector.envelope.data.checkpoints.at(-1);
    expect(head).toBeDefined();
    expect(notes.map((node) => node.textContent)).toContain(head?.note ?? 'missing');
    expect(notes.some((node) => (node.textContent ?? '').includes('—'))).toBe(true);
  });

  it('names the four layers of the chain in order', async () => {
    mount(realBundle(), true);
    const chain = await screen.findByTestId('custody-chain', undefined, { timeout: 5000 });
    const levels = [...chain.querySelectorAll('[data-level]')].map((node) =>
      node.getAttribute('data-level'),
    );
    expect(levels).toEqual(['L0', 'L1', 'L2', 'L3']);
    // L0 intake is present-but-unseen, not omitted.
    expect(screen.getByTestId('chain-count-L0').textContent).toContain('not visible from here');
  });
});

describe('the verifier names itself', () => {
  it('says which transport and which primitive did the arithmetic', async () => {
    mount(realBundle(), true);
    // The slot exists from the first paint and says `starting`, which is the honest value
    // before the worker has answered. Waiting for it to CHANGE is the assertion: a slot
    // that was pre-filled with a plausible name would pass without the verifier running.
    await waitFor(
      () => {
        expect(screen.getByTestId('verifier-transport').textContent).toMatch(/inline|worker/);
      },
      { timeout: 5000 },
    );
    expect(screen.getByTestId('verifier-transport').textContent).toMatch(/SHA-256/);
  });
});
