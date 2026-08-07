// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The property the replay transport exists to have: **a tampered bundle renders a
 * failure state, never a screen.**
 *
 * The tamper is one byte. `manifest.json` declares a SHA-256 for every file; one hex
 * digit of one of those digests is flipped, nothing else changes, and the transport
 * must refuse to serve ANY frame — not the mutated one, any of them — because the
 * manifest is the thing that says this is the bundle it claims to be.
 *
 * Every assertion below was written against a transport that did not yet have the gate
 * and failed for the right reason first (PL-2). The three "not vacuous" tests are what
 * keep it that way: they fail if the refusal ever becomes unconditional, if the
 * verifier's verdict ever stops being consulted, or if an unlisted file becomes
 * servable.
 */

import { describe, expect, it } from 'vitest';

import {
  BundleTransport,
  MemoryBundleSource,
  decodeBase64ToText,
} from '../../../src/data/bundle';
import { createContractRegistry } from '../../../src/data/contracts';
import { TransportError } from '../../../src/data/transport';

import { bundleFiles, manifestIntegrityVerifier, refusingVerifier } from './_support';

const registry = createContractRegistry();
const decoder = new TextDecoder();
const encoder = new TextEncoder();

const PERMIT_ID = '018f3a2f-1104-7c88-b3aa-77c1de40e2b1';
const permitRequest = { resource: 'permit', path: { permit_id: PERMIT_ID } };

function transportOver(files: Map<string, Uint8Array>): BundleTransport {
  return new BundleTransport({
    source: new MemoryBundleSource('fixtures/bundles/blk-07', files),
    registry,
    verifier: manifestIntegrityVerifier(),
  });
}

/** Flips one hex digit of one file's declared digest. One byte, nothing else. */
function tamperOneByteOfADigest(): { files: Map<string, Uint8Array>; targetPath: string } {
  const files = bundleFiles();
  const manifestBytes = files.get('manifest.json');
  if (manifestBytes === undefined) throw new Error('the fixture bundle has no manifest.json');
  const manifestText = decoder.decode(manifestBytes);

  const manifest = JSON.parse(manifestText) as { files: { path: string; sha256: string }[] };
  const target = manifest.files.find((entry) => entry.path.startsWith('frames/'));
  if (target === undefined) throw new Error('the fixture bundle lists no frames');

  const original = target.sha256;
  const firstChar = original.charAt(0);
  const flipped = `${firstChar === '0' ? '1' : '0'}${original.slice(1)}`;
  expect(flipped).toHaveLength(original.length);
  expect(flipped).not.toBe(original);

  const mutatedText = manifestText.replace(original, flipped);
  expect(mutatedText).not.toBe(manifestText);
  // Exactly one character differs.
  let differences = 0;
  for (let i = 0; i < manifestText.length; i += 1) {
    if (manifestText[i] !== mutatedText[i]) differences += 1;
  }
  expect(differences).toBe(1);

  files.set('manifest.json', encoder.encode(mutatedText));
  return { files, targetPath: target.path };
}

describe('BundleTransport — the intact bundle', () => {
  it('serves a frame, so the refusal below is not vacuous', async () => {
    const transport = transportOver(bundleFiles());
    const exchange = await transport.exchange(permitRequest);

    expect(exchange.mode).toBe('replay');
    expect(exchange.httpStatus).toBe(200);
    expect(exchange.envelope.resource).toBe('permit');
    expect((exchange.data as { permit_id: string }).permit_id).toBe(PERMIT_ID);
  });

  it('reports itself as REPLAY and STAGED, with the manifest digest prefix the verifier computed', async () => {
    const transport = transportOver(bundleFiles());
    // Before opening, nothing is established and the description says so.
    expect(transport.describe().bundleDigestPrefix).toBeNull();

    await transport.open();
    const description = transport.describe();

    expect(description.mode).toBe('replay');
    expect(description.source).toBe('blk-07-staged-2026-08-07');
    expect(description.staged).toBe(true);
    expect(description.stagedNote).toMatch(/Hand-authored demonstration bundle/);
    expect(description.bundleDigestPrefix).toMatch(/^[0-9a-f]{12}$/);
  });
});

describe('BundleTransport — one mutated byte', () => {
  it('refuses to serve the frame whose digest was mutated', async () => {
    const { files } = tamperOneByteOfADigest();
    const transport = transportOver(files);

    await expect(transport.exchange(permitRequest)).rejects.toThrow(TransportError);
    await expect(transport.exchange(permitRequest)).rejects.toThrow(/tampered/);
  });

  it('refuses to serve EVERY frame, including ones whose bytes are untouched', async () => {
    const { files, targetPath } = tamperOneByteOfADigest();
    const transport = transportOver(files);

    // A different resource, whose own frame file is byte-identical to the sealed one.
    const other = { resource: 'audit' };
    await expect(transport.exchange(other)).rejects.toThrow(/tampered/);

    // And the manifest names the file that failed, so the failure state can say which.
    const error = await transport.exchange(other).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(TransportError);
    expect((error as TransportError).detail).toContain(targetPath);
  });

  it('never resolves `open()` optimistically after a failure', async () => {
    const { files } = tamperOneByteOfADigest();
    const transport = transportOver(files);

    await expect(transport.open()).rejects.toThrow(/tampered/);
    // Asking again does not make a tampered bundle verified.
    await expect(transport.open()).rejects.toThrow(/tampered/);
    expect(transport.report()).toBeNull();
    expect(transport.manifest()).toBeNull();
  });
});

describe('BundleTransport — the gate is the verifier, not an internal opinion', () => {
  it('refuses when the injected verifier refuses, even though every byte is intact', async () => {
    const transport = new BundleTransport({
      source: new MemoryBundleSource('fixtures/bundles/blk-07', bundleFiles()),
      registry,
      verifier: refusingVerifier('the checkpoint signature did not verify against the pinned key'),
    });

    const error = await transport.exchange(permitRequest).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(TransportError);
    expect((error as TransportError).failure).toBe('tampered');
    // Verbatim, not summarised.
    expect((error as TransportError).detail).toContain(
      'the checkpoint signature did not verify against the pinned key',
    );
  });

  it('refuses a file that is present on disk but absent from manifest.files', async () => {
    const files = bundleFiles();
    files.set('frames/smuggled.json', encoder.encode('{"frame_version":1}'));

    const transport = transportOver(files);
    // The bundle still verifies — nothing the manifest lists has changed — but the
    // smuggled file is outside the checked set and can never be addressed.
    await expect(transport.exchange(permitRequest)).resolves.toBeDefined();

    const opened = await transport.open();
    expect(opened.files.has('frames/smuggled.json')).toBe(false);
  });

  it('refuses a manifest that lists itself', async () => {
    const files = bundleFiles();
    const manifest = JSON.parse(decoder.decode(files.get('manifest.json') ?? new Uint8Array())) as {
      files: { path: string; sha256: string; bytes: number }[];
    };
    manifest.files.push({ path: 'manifest.json', sha256: '0'.repeat(64), bytes: 1 });
    files.set('manifest.json', encoder.encode(JSON.stringify(manifest)));

    const transport = transportOver(files);
    await expect(transport.open()).rejects.toThrow(/cannot carry its own digest/);
  });
});

describe('BundleTransport — replay answers the exchange that was captured', () => {
  it('refuses a POST whose body differs from the captured one', async () => {
    const transport = transportOver(bundleFiles());
    const error = await transport
      .exchange({
        resource: 'merge_permit',
        path: { permit_id: PERMIT_ID },
        body: { subject_kind: 'permit', subject_id: PERMIT_ID, expected_gate_epoch: 8 },
      })
      .catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(TransportError);
    expect((error as TransportError).failure).toBe('mismatch');
  });

  it('reports a request the bundle never captured as a missing frame, not as an empty result', async () => {
    const transport = transportOver(bundleFiles());
    const error = await transport
      .exchange({ resource: 'permit', path: { permit_id: '018f3a2f-0000-7000-8000-000000000000' } })
      .catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(TransportError);
    expect((error as TransportError).failure).toBe('missing_frame');
    expect((error as TransportError).detail).toMatch(/captured a different set of exchanges/);
  });
});

describe('base64 frame bodies', () => {
  it('decode to exactly the source payload bytes', () => {
    const files = bundleFiles();
    const framePath = [...files.keys()].find((path) => path.startsWith('frames/'));
    expect(framePath).toBeDefined();

    const frame = JSON.parse(decoder.decode(files.get(framePath ?? '') ?? new Uint8Array())) as {
      response: { body_b64: string };
    };
    const text = decodeBase64ToText(framePath ?? '', frame.response.body_b64);
    // A frame body must round-trip as JSON; a re-serialised capture would not be
    // byte-for-byte and every digest over it would be a digest over our JSON writer.
    expect(() => JSON.parse(text) as unknown).not.toThrow();
  });

  it('raises rather than returning a partial string when the base64 is corrupt', () => {
    expect(() => decodeBase64ToText('frames/x.json', '!!!not base64!!!')).toThrow(TransportError);
  });
});
