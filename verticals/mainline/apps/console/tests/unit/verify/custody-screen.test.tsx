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
 *
 * ── AND, FROM 2026-08-15, THE THREE THIS SURFACE'S ADDRESSING TURNS ON ───────────
 *
 *   5. **A cold arrival with no query string renders the ledger**, addressed by the site
 *      the `GET /v1/ledger` payload NAMES ABOUT ITSELF, when the subject index does not
 *      answer. That is the case a judge actually walks, because the live deployment does
 *      not carry `GET /v1/demo/subjects` and nobody on this plan may redeploy it.
 *   6. **The console still never guesses.** With neither route answering, the screen is a
 *      named absence that says which of the two reads failed and how.
 *   7. **The signature check reads SKIPPED with its reason**, never green, on a build
 *      carrying no log key.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  BundleTransport,
  MemoryBundleSource,
  type BundleManifest,
} from '../../../src/data/bundle';
import { createContractRegistry } from '../../../src/data/contracts';
import { productWord } from '../../../src/design/glossary';
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

/*
 * EVERY WAIT IN THIS FILE IS FIVE SECONDS, AND SO WAS THE CEILING IT WAITED UNDER.
 *
 * These cases drive the REAL in-browser verifier over a real bundle: fifteen checks, RFC 6962
 * hashing, an ECDSA P-256 verification. In isolation the tier finishes them in seconds; in
 * the fully parallel tier they share a machine with every other crypto suite, and a case
 * whose wait equals its own ceiling loses that race rather than reporting on it. Raising the
 * ceiling changes no expectation in this file — a seal that is not green at twenty seconds
 * is still not green.
 */
vi.setConfig({ testTimeout: 20_000 });

const RAW = import.meta.glob<string>('/fixtures/bundles/blk-07/**/*', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const BUNDLE_ROOT = '/fixtures/bundles/blk-07/';
const LEDGER_FRAME = 'frames/GET-65a138de79af333c.json';
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
 * The site this bundle can answer for, read out of its OWN SEALED MANIFEST.
 *
 * `CustodyRoot` stopped carrying a default site code on 2026-08-15: the one it had was a
 * fixture string that no seed has ever written, and it answered 404 against the live
 * kernel. The root now asks `GET /v1/demo/subjects`, and a replay bundle sealed before
 * that route existed carries no frame for it — so under REPLAY the root has no subject
 * unless the address supplies one. These tests supply one.
 *
 * It is DERIVED, not typed. `manifest.files[].key` is the canonical request line the
 * transport itself looks a frame up by, so taking the site code from there addresses
 * exactly the ledger read this bundle can serve. A literal here would pass against a
 * console that had quietly reintroduced a constant, which is the defect being repaired.
 */
function bundleSiteCode(): string {
  const manifestBytes = bundleFiles().get('manifest.json');
  if (manifestBytes === undefined) throw new Error('the fixture bundle has no manifest.json');
  const manifest = JSON.parse(decode(manifestBytes)) as {
    files: { key?: string | null }[];
  };
  for (const entry of manifest.files) {
    const key = entry.key ?? '';
    if (!key.startsWith('GET /v1/ledger?')) continue;
    const code = new URLSearchParams(key.slice(key.indexOf('?') + 1)).get('site_code');
    if (code !== null && code !== '') return code;
  }
  throw new Error(
    'the sealed blk-07 manifest lists no ledger frame carrying a site_code, so these tests ' +
      'cannot address the site the bundle answers for. Re-run `node scripts/capture-bundle.ts ' +
      'stage --sources fixtures/sources/blk-07 --out fixtures/bundles/blk-07`.',
  );
}

const SITE = bundleSiteCode();

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
  // Addressed explicitly, from the bundle's own manifest — see `bundleSiteCode`.
  window.location.hash = `#/custody?site=${SITE}`;
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

// ── The unaddressed arrival ────────────────────────────────────────────────

/** The request line a `ledger` read with NO `site_code` resolves to. */
const UNQUALIFIED_LEDGER_KEY = 'GET /v1/ledger';

/**
 * A bundle that can also answer `GET /v1/ledger` — the read that asks the kernel to name
 * its own site.
 *
 * The added frame carries the SAME envelope the site-qualified frame carries, because that
 * is what the live route does: `GET /v1/ledger` with no filter answers with the site this
 * deployment holds, and its `data.site_code` is that name. The site this test then expects
 * on screen is read back out of that envelope rather than typed — a literal here would
 * pass against a console that had quietly reintroduced a constant, which is the entire
 * defect under repair.
 */
function withUnqualifiedLedger(files: Map<string, Uint8Array>): Map<string, Uint8Array> {
  const frameBytes = files.get(LEDGER_FRAME);
  if (frameBytes === undefined) throw new Error(`${LEDGER_FRAME} is not in the fixture bundle`);
  const frame = JSON.parse(decode(frameBytes)) as Record<string, unknown>;
  const request = frame.request as Record<string, unknown>;

  const path = 'frames/GET-unqualified-ledger.json';
  const added = utf8(
    JSON.stringify({
      ...frame,
      key: UNQUALIFIED_LEDGER_KEY,
      // The query is dropped, not emptied: this is the read a console performs when it has
      // no site to ask about, and the kernel answers with the one it has.
      request: { ...request, query: [] },
    }),
  );

  const next = new Map(files);
  next.set(path, added);

  const manifestBytes = next.get('manifest.json');
  if (manifestBytes === undefined) throw new Error('the fixture bundle has no manifest.json');
  const manifest = JSON.parse(decode(manifestBytes)) as BundleManifest;
  next.set(
    'manifest.json',
    utf8(
      JSON.stringify({
        ...manifest,
        files: [
          ...manifest.files,
          {
            path,
            sha256: toHex(sha256Sync(added)),
            bytes: added.byteLength,
            media_type: 'application/json',
            key: UNQUALIFIED_LEDGER_KEY,
          },
        ],
      }),
    ),
  );
  return reseal(next);
}

/** Mount with NO `?site=` at all — the arrival a judge makes from the navigation. */
function mountUnaddressed(files: ReadonlyMap<string, Uint8Array>): void {
  window.location.hash = '#/custody';
  render(
    <CustodyTransportContext.Provider value={transportFor(files)}>
      <CustodyVerifierContext.Provider value={new InlineVerifier('unit test — jsdom has no Worker')}>
        <CustodyConfigContext.Provider value={NO_ANCHOR}>
          <CustodyRoot />
        </CustodyConfigContext.Provider>
      </CustodyVerifierContext.Provider>
    </CustodyTransportContext.Provider>,
  );
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
  /*
   * THE WAIT AND THE CASE'S OWN CEILING MOVE TOGETHER, OR NEITHER MOVES.
   *
   * This case waited five seconds inside a case whose default ceiling is also five seconds,
   * so under the fully parallel tier — where fifteen checks of real SHA-256 share a machine
   * with every other crypto test — it died at the ceiling while the arithmetic it was
   * waiting for was still running, and reported as `Test timed out in 5000ms`. In isolation
   * it has never failed. Nothing asserted here changes: the same seals must be `verified`
   * for the same vector; the case is only willing to wait for the worker to finish.
   */
  it('recomputes the ledger and passes the checks the vector names', async () => {
    mount(realBundle(), true);

    await waitFor(
      () => {
        expect(screen.getByTestId('custody-checks')).toBeInTheDocument();
      },
      { timeout: 15_000 },
    );

    for (const name of vector.expect.pass) {
      const seal = await screen.findByTestId(`seal-${name}`, undefined, { timeout: 15_000 });
      expect(seal.getAttribute('data-state'), name).toBe('verified');
    }
  }, 25_000);

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

describe('a cold arrival with no query string', () => {
  it('renders the ledger, addressed by the site the payload names about itself', async () => {
    mountUnaddressed(withUnqualifiedLedger(realBundle()));

    const surface = await screen.findByTestId('custody-surface', undefined, { timeout: 5000 });
    // The site is read back out of the vector, never typed: it is what `GET /v1/ledger`
    // answered with, which is the only thing the console is allowed to have used.
    expect(surface.textContent).toContain(vector.envelope.data.site_code);
    expect(screen.getByTestId('custody-site-origin').getAttribute('data-origin')).toBe('ledger');
    expect(screen.queryByTestId('custody-no-subject')).not.toBeInTheDocument();
  });

  it('names the site as the LEDGER’s, not as a value it carries', async () => {
    mountUnaddressed(withUnqualifiedLedger(realBundle()));
    const origin = await screen.findByTestId('custody-site-origin', undefined, { timeout: 5000 });
    expect(origin.textContent).toContain('named by the ledger itself');
    expect(origin.textContent).toContain('asked with no site_code at all');
  });

  it('still refuses to guess when NEITHER read answers, and says which failed', async () => {
    // The untouched fixture answers `GET /v1/ledger?site_code=…` and nothing else — no
    // subject index, no unqualified ledger. Both reads fail and the screen shows an absence.
    mountUnaddressed(realBundle());

    const panel = await screen.findByTestId('custody-no-subject', undefined, { timeout: 5000 });
    expect(panel.textContent).toContain('GET /v1/demo/subjects');
    // The second read is only attempted once the index has SETTLED, so the note appears
    // after it — waiting for the note is waiting for exactly that ordering to have held.
    const note = await screen.findByTestId('custody-ledger-fallback-note', undefined, {
      timeout: 5000,
    });
    expect(note.textContent).toContain('GET /v1/ledger with no site_code');
    expect(screen.queryByTestId('custody-checks')).not.toBeInTheDocument();
  });
});

describe('the on-ramp, and the one check that cannot run', () => {
  it('opens with the ruled definition of custody, read from the glossary', async () => {
    mount(realBundle(), false);
    const band = await screen.findByTestId('custody-plain-band', undefined, { timeout: 5000 });
    const ruled = productWord('custody');
    expect(ruled).not.toBeNull();
    expect(band.textContent).toContain(ruled?.sentence ?? 'missing');
  });

  it('says SKIPPED — this build carries no log key, and never green', async () => {
    mount(realBundle(), false);
    // Wait for the verifier to have ANSWERED before reading the cell: the point is that the
    // sentence survives the check actually running and reporting SKIP, not that it is
    // printed by a screen that has not looked yet.
    const seal = await screen.findByTestId('seal-log_signature', undefined, { timeout: 5000 });
    expect(seal.getAttribute('data-state')).not.toBe('verified');
    const cell = screen.getByTestId('custody-signature-state');
    expect(cell.getAttribute('data-state')).toBe('skipped');
    expect(cell.textContent).toContain('SKIPPED — this build carries no log key');
  });

  it('does not say it when a key IS configured — the sentence is derived, not written down', async () => {
    mount(realBundle(), true);
    await screen.findByTestId('seal-log_signature', undefined, { timeout: 5000 });
    const cell = screen.getByTestId('custody-signature-state');
    expect(cell.getAttribute('data-state')).not.toBe('not-run');
    expect(cell.textContent).not.toContain('this build carries no log key');
  });
});

describe('PLAIN collapses and never removes', () => {
  it('keeps every recomputation table in the DOM with no ?detail=full', async () => {
    mount(realBundle(), true);
    const table = await screen.findByTestId('recomputation-leaf_hash_recomputation', undefined, {
      timeout: 5000,
    });
    const leaf = vector.envelope.data.leaves[0];
    // Present, findable by a text search, and complete — the collapse clips the paint only.
    expect(table.textContent).toContain(leaf?.leaf_hash_hex ?? 'missing');
    expect(table.closest('details')).not.toBeNull();
  });

  it('never collapses the checkpoint note, which is a string the kernel emitted', async () => {
    mount(realBundle(), true);
    const notes = await screen.findAllByTestId('checkpoint-note', undefined, { timeout: 5000 });
    for (const note of notes) expect(note.closest('details')).toBeNull();
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
