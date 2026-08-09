// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The two SHA-256 implementations must agree, or one of them is a liability.
 *
 * The software fallback exists so that a console served over plain HTTP — the class of
 * host a free demo URL lands on — can still recompute what it displays. Two
 * implementations exercised separately are two chances to be wrong; two asserted equal on
 * every committed vector are one.
 */

import { describe, expect, it } from 'vitest';

import { toHex, utf8 } from '../../../src/verify/bytes';
import {
  SOFTWARE_ORACLE,
  resolveSha256,
  sha256Sync,
  webCryptoOracle,
} from '../../../src/verify/sha256';

import { rfc6962Vectors } from './_vectors';

/** FIPS 180-4 and the two RFC 6962 boundary values. Published, not invented here. */
const KNOWN = [
  ['', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'],
  ['abc', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'],
  [
    'abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq',
    '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1',
  ],
  [
    'abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu',
    'cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1',
  ],
] as const;

describe('the software implementation is SHA-256', () => {
  it.each(KNOWN.map(([input, digest]) => [input.slice(0, 24), input, digest] as const))(
    'hashes %s… correctly',
    (_label, input, digest) => {
      expect(toHex(sha256Sync(utf8(input)))).toBe(digest);
    },
  );

  it('pads a 55-byte message into ONE block and a 56-byte message into two', () => {
    // Length ≡ 55 (mod 64) is where an "add a whole extra block" padding bug hides: every
    // shorter and every longer message is unaffected.
    expect(toHex(sha256Sync(utf8('a'.repeat(55))))).toBe(
      '9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318',
    );
    expect(toHex(sha256Sync(utf8('a'.repeat(56))))).toBe(
      'b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a',
    );
    expect(toHex(sha256Sync(utf8('a'.repeat(64))))).toBe(
      'ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb',
    );
  });

  it('hashes exactly the view it was given, not the buffer behind it', () => {
    const backing = new Uint8Array([9, 9, 9, 97, 98, 99, 9, 9]);
    const view = backing.subarray(3, 6);
    expect(toHex(sha256Sync(view))).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
  });
});

describe('the software implementation agrees with WebCrypto', () => {
  const subtle = globalThis.crypto?.subtle;

  it.runIf(subtle !== undefined)('on every committed leaf', async () => {
    if (subtle === undefined) return;
    const web = webCryptoOracle(subtle);
    for (const leaf of rfc6962Vectors().leaves) {
      const bytes = utf8(leaf.canon_bytes_utf8);
      expect(toHex(await web.digest(bytes))).toBe(toHex(await SOFTWARE_ORACLE.digest(bytes)));
    }
  });

  it.runIf(subtle !== undefined)('on a megabyte of pseudo-random bytes', async () => {
    if (subtle === undefined) return;
    // A seeded xorshift, so a failure is reproducible from the source rather than from a
    // log line nobody kept.
    let state = 0x2f6e2b1;
    const bytes = new Uint8Array(1 << 20);
    for (let i = 0; i < bytes.length; i += 1) {
      state ^= state << 13;
      state ^= state >>> 17;
      state ^= state << 5;
      bytes[i] = state & 0xff;
    }
    const web = webCryptoOracle(subtle);
    expect(toHex(await web.digest(bytes))).toBe(toHex(await SOFTWARE_ORACLE.digest(bytes)));
  });

  it.runIf(subtle !== undefined)('at every length across two block boundaries', async () => {
    if (subtle === undefined) return;
    const web = webCryptoOracle(subtle);
    const source = utf8('mainline'.repeat(40));
    for (let length = 0; length <= 200; length += 1) {
      const slice = source.subarray(0, length);
      expect(toHex(await web.digest(slice)), `length ${length}`).toBe(
        toHex(await SOFTWARE_ORACLE.digest(slice)),
      );
    }
  });
});

describe('resolveSha256 never fails, and says which primitive it chose', () => {
  it('returns WebCrypto with no note when subtle is present', () => {
    const resolved = resolveSha256();
    if (globalThis.crypto?.subtle === undefined) {
      expect(resolved.oracle.backend).toBe('software');
      return;
    }
    expect(resolved.oracle.backend).toBe('webcrypto');
    expect(resolved.note).toBe('');
  });

  it('falls back with a stated reason on an insecure origin', () => {
    const resolved = resolveSha256({ crypto: {} as Crypto });
    expect(resolved.oracle.backend).toBe('software');
    expect(resolved.note).toContain('not running in a secure context');
    expect(resolved.oracle.name).toBe('software SHA-256 (FIPS 180-4)');
  });

  it('falls back when there is no crypto object at all', () => {
    const resolved = resolveSha256({});
    expect(resolved.oracle.backend).toBe('software');
    expect(resolved.note).toContain('secure context');
  });
});
