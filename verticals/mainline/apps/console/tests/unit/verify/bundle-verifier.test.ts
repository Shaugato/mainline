// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The gate: `BundleTransport` cannot serve a frame before this verifier resolves.
 *
 * The three assertions that matter are the tamper ones. `src/data/bundle.ts` was written
 * against the PROMISE that a verifier would be injected; this file is where the promise
 * becomes a mechanism. Flipping one byte of one frame must stop every surface in the
 * console from rendering, and the failure must name the file and both digests.
 *
 * The verifier used here is the real one, driven by the real fixture bundle, over the
 * inline transport (jsdom has no Worker). `InlineVerifier` and `WorkerVerifier` call the
 * same handler, so the arithmetic asserted here is the arithmetic that runs in a browser.
 */

import { describe, expect, it } from 'vitest';

import {
  BundleTransport,
  MemoryBundleSource,
  type BundleManifest,
} from '../../../src/data/bundle';
import { createContractRegistry } from '../../../src/data/contracts';
import { TransportError } from '../../../src/data/transport';
import { toHex, utf8 } from '../../../src/verify/bytes';
import { InBrowserBundleVerifier } from '../../../src/verify/bundle-verifier';
import { InlineVerifier } from '../../../src/verify/client';
import { NO_ANCHOR, operatorConfig } from '../../../src/verify/config';
import { sha256Sync } from '../../../src/verify/sha256';

import { checkpointVectors } from './_vectors';

const RAW = import.meta.glob<string>('/fixtures/bundles/blk-07/**/*', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const BUNDLE_ROOT = '/fixtures/bundles/blk-07/';
/** The seed is the INPUT to sealing, not bundle content; the manifest does not list it. */
const NOT_CONTENT = new Set(['manifest.seed.json']);

function bundleFiles(): Map<string, Uint8Array> {
  const files = new Map<string, Uint8Array>();
  for (const [key, text] of Object.entries(RAW)) {
    if (!key.startsWith(BUNDLE_ROOT)) continue;
    const path = key.slice(BUNDLE_ROOT.length);
    if (NOT_CONTENT.has(path)) continue;
    files.set(path, utf8(text));
  }
  if (files.size === 0) throw new Error('no fixture bundle files were globbed');
  return files;
}

function inline(): InlineVerifier {
  return new InlineVerifier('unit test — inline by construction');
}

function verifierFor(files: Map<string, Uint8Array>): {
  transport: BundleTransport;
  verifier: InBrowserBundleVerifier;
} {
  const verifier = new InBrowserBundleVerifier({ verifier: inline(), config: NO_ANCHOR });
  const transport = new BundleTransport({
    source: new MemoryBundleSource('unit-fixture', files),
    registry: createContractRegistry(),
    verifier,
  });
  return { transport, verifier };
}

function manifestOf(files: Map<string, Uint8Array>): BundleManifest {
  const bytes = files.get('manifest.json');
  if (bytes === undefined) throw new Error('the fixture bundle has no manifest.json');
  return JSON.parse(new TextDecoder().decode(bytes)) as BundleManifest;
}

describe('the untampered fixture bundle', () => {
  it('verifies, and reports the manifest digest it computed', async () => {
    const files = bundleFiles();
    const { transport } = verifierFor(files);
    const opened = await transport.open();

    expect(opened.report.verdict).toBe('verified');
    expect(opened.report.filesChecked).toBe(opened.manifest.files.length);
    expect(opened.report.manifestDigest).toBe(toHex(sha256Sync(files.get('manifest.json') ?? new Uint8Array())));
    expect(transport.describe().bundleDigestPrefix).toBe(opened.report.manifestDigest.slice(0, 12));
  });

  it('records the unchecked checkpoint signature as a SKIP finding, not silence', async () => {
    const { transport } = verifierFor(bundleFiles());
    const opened = await transport.open();
    const skips = opened.report.findings.filter((finding) => finding.check.startsWith('skip:'));
    expect(skips.length).toBeGreaterThan(0);
    expect(skips.map((finding) => finding.check)).toContain('skip:checkpoint-signature');
    expect(opened.report.summary).toContain('NOT RUN');
  });

  it('serves a frame once, and only once, verification has resolved', async () => {
    const { transport } = verifierFor(bundleFiles());
    const exchange = await transport.exchange({ resource: 'ledger', query: { site_code: 'BLK-07' } });
    expect(exchange.mode).toBe('replay');
    expect(exchange.envelope.resource).toBe('ledger');
  });
});

describe('one byte, and no frame is served', () => {
  it('fails the digest check and names both digests', async () => {
    const files = bundleFiles();
    const target = 'frames/GET-65a138de79af333c.json';
    const original = files.get(target);
    expect(original, `${target} is not in the fixture bundle`).toBeDefined();

    // Flip one byte, keeping the length identical so the transport's byte-length guard
    // cannot catch it first. Only the digest can see this.
    const tampered = new Uint8Array(original ?? new Uint8Array());
    const index = Math.floor(tampered.length / 2);
    tampered[index] = (tampered[index] ?? 0) ^ 0x01;
    files.set(target, tampered);

    const { transport } = verifierFor(files);
    await expect(transport.open()).rejects.toThrow(TransportError);
    await expect(transport.open()).rejects.toThrow(/refused this bundle/);

    // And, critically, no surface can get bytes out of it afterwards.
    await expect(
      transport.exchange({ resource: 'ledger', query: { site_code: 'BLK-07' } }),
    ).rejects.toThrow(/file-digest|refused this bundle/);
  });

  it('does not become verified by asking again', async () => {
    const files = bundleFiles();
    const target = 'frames/GET-540549b3695a753c.json';
    const tampered = new Uint8Array(files.get(target) ?? new Uint8Array());
    tampered[0] = (tampered[0] ?? 0) ^ 0xff;
    files.set(target, tampered);

    const { transport } = verifierFor(files);
    await expect(transport.open()).rejects.toThrow();
    await expect(transport.open()).rejects.toThrow();
    expect(transport.report()).toBeNull();
  });

  it('reports the mismatch verbatim, with the path, when called directly', async () => {
    const files = bundleFiles();
    const target = 'frames/GET-540549b3695a753c.json';
    const tampered = new Uint8Array(files.get(target) ?? new Uint8Array());
    tampered[5] = (tampered[5] ?? 0) ^ 0x02;
    files.set(target, tampered);

    const verifier = new InBrowserBundleVerifier({ verifier: inline(), config: NO_ANCHOR });
    const manifest = manifestOf(files);
    const report = await verifier.verify({
      manifestBytes: files.get('manifest.json') ?? new Uint8Array(),
      manifest,
      read: (path) => {
        const bytes = files.get(path);
        return bytes === undefined ? Promise.reject(new Error(`no ${path}`)) : Promise.resolve(bytes);
      },
    });

    expect(report.verdict).toBe('failed');
    const finding = report.findings.find((entry) => entry.subject === target);
    expect(finding?.check).toBe('file-digest');
    expect(finding?.detail).toContain('the bytes served hash to');
    expect(finding?.detail).toContain('These are not the bytes that were sealed.');
  });

  it('fails when a listed file is missing entirely', async () => {
    const files = bundleFiles();
    files.delete('frames/GET-540549b3695a753c.json');
    const { transport } = verifierFor(files);
    await expect(transport.open()).rejects.toThrow(/file-read|refused this bundle/);
  });
});

describe('the manifest is not the signed artefact, and the note is', () => {
  it('fails when the manifest claims a tree size the note does not', async () => {
    const files = bundleFiles();
    const manifest = manifestOf(files);
    const rewritten = {
      ...manifest,
      checkpoint:
        manifest.checkpoint === null ? null : { ...manifest.checkpoint, tree_size: 999 },
    };
    const bytes = utf8(JSON.stringify(rewritten));
    files.set('manifest.json', bytes);

    const verifier = new InBrowserBundleVerifier({ verifier: inline(), config: NO_ANCHOR });
    const report = await verifier.verify({
      manifestBytes: bytes,
      manifest: rewritten,
      read: (path) => {
        const found = files.get(path);
        return found === undefined ? Promise.reject(new Error(`no ${path}`)) : Promise.resolve(found);
      },
    });
    expect(report.verdict).toBe('failed');
    expect(report.findings.some((finding) => finding.check === 'checkpoint-binding')).toBe(true);
  });

  it('verifies the note signature when a key IS configured', async () => {
    const anchor = checkpointVectors().cases.find((c) => c.id === 'spec-7.5-complete-note');
    if (anchor === undefined) throw new Error('vector set is truncated');
    const noteBytes = utf8(anchor.full_note);

    const manifest: BundleManifest = {
      manifest_version: 1,
      bundle_id: 'unit-note-only',
      captured_at: '2026-08-09T00:00:00.000Z',
      generator: 'bundle-verifier.test.ts',
      cluster_fingerprint: {
        source: 'declared',
        product: 'none',
        version: 'none',
        region: 'none',
      },
      schema_version: 'none',
      staged: true,
      staged_note: 'A one-file bundle carrying only the frozen worked-example checkpoint.',
      checkpoint: {
        site_code: 'BLK-07',
        tree_size: anchor.expect_parsed?.tree_size ?? 0,
        root_hex: anchor.expect_parsed?.root_hex ?? '',
        note_path: 'ledger/checkpoint.note',
      },
      files: [
        {
          path: 'ledger/checkpoint.note',
          sha256: toHex(sha256Sync(noteBytes)),
          bytes: noteBytes.byteLength,
          media_type: 'text/plain',
        },
      ],
    };

    const verifier = new InBrowserBundleVerifier({
      verifier: inline(),
      config: operatorConfig(checkpointVectors().keys.trusted.vkey),
    });
    const report = await verifier.verify({
      manifestBytes: utf8(JSON.stringify(manifest)),
      manifest,
      read: (path) =>
        path === 'ledger/checkpoint.note'
          ? Promise.resolve(noteBytes)
          : Promise.reject(new Error(`no ${path}`)),
    });

    expect(report.verdict).toBe('verified');
    const signature = report.findings.find((finding) => finding.check === 'checkpoint-signature');
    expect(signature?.detail).toContain('verifies under ECDSA P-256');
    expect(report.summary).not.toContain('NOT RUN');
  });

  it('fails when the note was signed by a key the reader does not trust', async () => {
    const forged = checkpointVectors().cases.find(
      (c) => c.id === 'resigned-body-different-key-spoofed-id',
    );
    if (forged === undefined) throw new Error('vector set is truncated');
    const noteBytes = utf8(forged.full_note);

    const manifest: BundleManifest = {
      manifest_version: 1,
      bundle_id: 'unit-forged-note',
      captured_at: '2026-08-09T00:00:00.000Z',
      cluster_fingerprint: { source: 'declared', product: 'none', version: 'none', region: 'none' },
      schema_version: 'none',
      staged: true,
      staged_note: 'A bundle whose checkpoint was re-signed by a different key.',
      checkpoint: {
        site_code: 'BLK-07',
        tree_size: 5,
        root_hex: '00c5dddf89d15dfbf9fb2349e0adadbcc4a5131b6612adfc85ad0df2005d359e',
        note_path: 'ledger/checkpoint.note',
      },
      files: [
        {
          path: 'ledger/checkpoint.note',
          sha256: toHex(sha256Sync(noteBytes)),
          bytes: noteBytes.byteLength,
        },
      ],
    };

    const verifier = new InBrowserBundleVerifier({
      verifier: inline(),
      config: operatorConfig(checkpointVectors().keys.trusted.vkey),
    });
    const report = await verifier.verify({
      manifestBytes: utf8(JSON.stringify(manifest)),
      manifest,
      read: () => Promise.resolve(noteBytes),
    });

    expect(report.verdict).toBe('failed');
    expect(
      report.findings.find((finding) => finding.check === 'checkpoint-signature')?.detail,
    ).toContain('does not verify over the note text');
  });
});
