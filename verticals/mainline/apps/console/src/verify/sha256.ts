// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * SHA-256, twice: WebCrypto when the platform has it, and a documented synchronous
 * fallback when it does not.
 *
 * ── WHY THERE IS A FALLBACK AT ALL ────────────────────────────────────────────────
 *
 * `crypto.subtle` is exposed only in a **secure context** — HTTPS, `localhost`, or a
 * local file in some engines. That is not a hypothetical for this product: `G6` requires
 * a free public demo URL, and the class of host that ends up on plain `http://` is
 * exactly the class of host a free demo lands on. On such an origin a verifier with no
 * fallback has three options, two of which are lies:
 *
 *   • render a green seal — a lie;
 *   • render a red seal — an accusation against a bundle nobody checked;
 *   • render "not checked, and here is why" — honest, and useless to the reader.
 *
 * The fallback makes a fourth option available: check it anyway, in software, and SAY SO.
 * `RESOLVED_BY` travels with every digest so the screen can name what did the arithmetic
 * (`WebCrypto SHA-256` or `software SHA-256 (FIPS 180-4)`), and the custody surface prints
 * that name beside the seal. A reader is entitled to know whether the browser's own
 * primitive or our 90 lines produced the number.
 *
 * ── WHY THE FALLBACK IS NOT A SECOND SOURCE OF TRUTH ──────────────────────────────
 *
 * `tests/unit/verify/sha256.test.ts` asserts the two implementations agree on the FIPS
 * 180-4 vectors, on every leaf in `tests/vectors/rfc6962.json`, and on a megabyte of
 * pseudo-random input. Two implementations that are only ever exercised separately are
 * two chances to be wrong; two that are asserted equal on every committed vector are one.
 *
 * The software implementation below is a plain transcription of FIPS 180-4 §6.2 with no
 * cleverness: 32-bit arithmetic through `>>> 0`, big-endian length in the padding, and a
 * copy of the message rather than a view, so a `Uint8Array` with a non-zero `byteOffset`
 * over a larger buffer cannot silently hash its neighbours.
 */

import { concat, toHex, utf8 } from './bytes';

// ── The port ───────────────────────────────────────────────────────────────

export type DigestBackend = 'webcrypto' | 'software';

export interface Sha256Oracle {
  /** Named on screen beside every seal it produced. */
  readonly name: string;
  readonly backend: DigestBackend;
  digest(bytes: Uint8Array): Promise<Uint8Array>;
}

// ── The software implementation (FIPS 180-4) ───────────────────────────────

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rotr(value: number, bits: number): number {
  return ((value >>> bits) | (value << (32 - bits))) >>> 0;
}

/** SHA-256 over `message`. Synchronous, allocation-light, no platform dependency. */
export function sha256Sync(message: Uint8Array): Uint8Array {
  // A COPY, not a view: `message` may be a window over a larger (or shared) buffer, and
  // "the digest is over exactly these bytes" must be true by construction.
  const length = message.byteLength;
  const bitLengthHigh = Math.floor(length / 0x20000000);
  const bitLengthLow = (length << 3) >>> 0;
  // ceil((length + 1 + 8) / 64) * 64 — the SMALLEST valid padding. A padded length one
  // block too large is not merely wasteful: it is different padding, and therefore a
  // different (wrong) digest for every message of length ≡ 55 mod 64.
  const paddedLength = ((length + 9 + 63) >> 6) << 6;
  const block = new Uint8Array(paddedLength);
  block.set(message);
  block[length] = 0x80;
  const view = new DataView(block.buffer);
  view.setUint32(paddedLength - 8, bitLengthHigh, false);
  view.setUint32(paddedLength - 4, bitLengthLow, false);

  const h = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const w = new Uint32Array(64);

  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let i = 0; i < 16; i += 1) w[i] = view.getUint32(offset + i * 4, false);
    for (let i = 16; i < 64; i += 1) {
      const w15 = w[i - 15] ?? 0;
      const w2 = w[i - 2] ?? 0;
      const s0 = (rotr(w15, 7) ^ rotr(w15, 18) ^ (w15 >>> 3)) >>> 0;
      const s1 = (rotr(w2, 17) ^ rotr(w2, 19) ^ (w2 >>> 10)) >>> 0;
      w[i] = (((w[i - 16] ?? 0) + s0 + (w[i - 7] ?? 0) + s1) >>> 0);
    }

    let a = h[0] ?? 0;
    let b = h[1] ?? 0;
    let c = h[2] ?? 0;
    let d = h[3] ?? 0;
    let e = h[4] ?? 0;
    let f = h[5] ?? 0;
    let g = h[6] ?? 0;
    let hh = h[7] ?? 0;

    for (let i = 0; i < 64; i += 1) {
      const S1 = (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) >>> 0;
      const ch = ((e & f) ^ (~e & g)) >>> 0;
      const temp1 = (hh + S1 + ch + (K[i] ?? 0) + (w[i] ?? 0)) >>> 0;
      const S0 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) >>> 0;
      const maj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const temp2 = (S0 + maj) >>> 0;

      hh = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    h[0] = ((h[0] ?? 0) + a) >>> 0;
    h[1] = ((h[1] ?? 0) + b) >>> 0;
    h[2] = ((h[2] ?? 0) + c) >>> 0;
    h[3] = ((h[3] ?? 0) + d) >>> 0;
    h[4] = ((h[4] ?? 0) + e) >>> 0;
    h[5] = ((h[5] ?? 0) + f) >>> 0;
    h[6] = ((h[6] ?? 0) + g) >>> 0;
    h[7] = ((h[7] ?? 0) + hh) >>> 0;
  }

  const out = new Uint8Array(32);
  const outView = new DataView(out.buffer);
  for (let i = 0; i < 8; i += 1) outView.setUint32(i * 4, h[i] ?? 0, false);
  return out;
}

// ── Oracles ────────────────────────────────────────────────────────────────

export const SOFTWARE_ORACLE: Sha256Oracle = Object.freeze({
  name: 'software SHA-256 (FIPS 180-4)',
  backend: 'software',
  digest(bytes: Uint8Array): Promise<Uint8Array> {
    return Promise.resolve(sha256Sync(bytes));
  },
});

export function webCryptoOracle(subtle: SubtleCrypto): Sha256Oracle {
  return Object.freeze({
    name: 'WebCrypto SHA-256',
    backend: 'webcrypto' as const,
    async digest(bytes: Uint8Array): Promise<Uint8Array> {
      const buffer = new ArrayBuffer(bytes.byteLength);
      new Uint8Array(buffer).set(bytes);
      return new Uint8Array(await subtle.digest('SHA-256', buffer));
    },
  });
}

export interface ResolvedOracle {
  readonly oracle: Sha256Oracle;
  /**
   * Verbatim, rendered beside the seal. Empty string when WebCrypto was available and
   * nothing needs explaining.
   */
  readonly note: string;
}

/**
 * The platform's oracle, or the software one plus the reason the platform's was absent.
 *
 * There is no failure branch. A verifier that cannot hash is a verifier that cannot
 * report anything, and this one always can.
 */
export function resolveSha256(host: { readonly crypto?: Crypto } = globalThis): ResolvedOracle {
  const platform = host.crypto;
  // `subtle` is typed as always-present and is genuinely absent on an insecure origin.
  const subtle: SubtleCrypto | undefined = platform?.subtle;
  if (subtle === undefined) {
    return {
      oracle: SOFTWARE_ORACLE,
      note:
        'crypto.subtle is unavailable here, which means this page is not running in a secure ' +
        'context (WebCrypto is exposed only over HTTPS, on localhost, or from a local file). ' +
        'Every digest on this screen was computed by the software SHA-256 in src/verify/, not ' +
        'by the browser. It is asserted byte-equal to WebCrypto on every committed vector; it ' +
        'has not been audited, and it is slower.',
    };
  }
  return { oracle: webCryptoOracle(subtle), note: '' };
}

// ── Convenience ────────────────────────────────────────────────────────────

/** SHA-256 over a concatenation, returned as lowercase hex. Used by the surfaces. */
export async function sha256HexOf(
  oracle: Sha256Oracle,
  ...parts: readonly Uint8Array[]
): Promise<string> {
  return toHex(await oracle.digest(concat(...parts)));
}

/** SHA-256 of UTF-8 text. Used for the note digest the checkpoint panel displays. */
export async function sha256HexOfText(oracle: Sha256Oracle, text: string): Promise<string> {
  return toHex(await oracle.digest(utf8(text)));
}
