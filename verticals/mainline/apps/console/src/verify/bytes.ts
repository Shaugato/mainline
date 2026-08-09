// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Byte plumbing for the verifier: hex, base64 and UTF-8, with no dependencies and no
 * silent coercions.
 *
 * Every function here refuses malformed input rather than producing a plausible wrong
 * answer. That is not defensive style — a verifier that reads `"0xabc"` as three bytes,
 * or that lets `atob` drop a stray character, produces a digest that does not match and a
 * finding nobody can interpret. The failure has to name the malformation.
 *
 * `atob`/`btoa` are used deliberately rather than a hand-rolled base64: they are the same
 * primitives the transport already relies on for frame bodies, and their behaviour on the
 * standard RFC 4648 §4 alphabet with padding — which is what `spec/wire/checkpoint.md` §2
 * mandates throughout — is exactly what is needed. What they do NOT do is validate, so the
 * alphabet and padding are checked here first.
 */

const HEX = /^[0-9a-f]*$/;
const BASE64 = /^[A-Za-z0-9+/]*={0,2}$/;

export class ByteFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ByteFormatError';
  }
}

/** Lowercase hex → bytes. Uppercase is refused: the wire format is lowercase. */
export function fromHex(text: string, what = 'value'): Uint8Array {
  if (text.length % 2 !== 0) {
    throw new ByteFormatError(`${what}: hex string has odd length ${text.length}`);
  }
  if (!HEX.test(text)) {
    throw new ByteFormatError(
      `${what}: not lowercase hex. Every hex value on this wire is lowercase, and accepting ` +
        'mixed case would make two spellings of one digest compare unequal as strings.',
    );
  }
  const bytes = new Uint8Array(text.length / 2);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(text.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

/** Bytes → lowercase hex. */
export function toHex(bytes: Uint8Array): string {
  let out = '';
  for (const byte of bytes) out += byte.toString(16).padStart(2, '0');
  return out;
}

/** A 32-byte digest from hex, or a refusal naming the length that arrived. */
export function digestFromHex(text: string, what = 'digest'): Uint8Array {
  const bytes = fromHex(text, what);
  if (bytes.length !== 32) {
    throw new ByteFormatError(`${what}: expected 32 bytes, got ${bytes.length}`);
  }
  return bytes;
}

/** Standard base64 with padding (RFC 4648 §4) → bytes. */
export function fromBase64(text: string, what = 'value'): Uint8Array {
  if (!BASE64.test(text)) {
    throw new ByteFormatError(
      `${what}: not standard base64 (RFC 4648 §4). The URL-safe alphabet is not accepted; ` +
        'spec/wire/checkpoint.md §2 fixes the alphabet so two encodings of one signature ' +
        'cannot both be "the" signature.',
    );
  }
  if (text.length % 4 !== 0) {
    throw new ByteFormatError(`${what}: base64 length ${text.length} is not a multiple of 4`);
  }
  let binary: string;
  try {
    binary = atob(text);
  } catch (error) {
    throw new ByteFormatError(`${what}: base64 did not decode (${String(error)})`);
  }
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** Bytes → standard base64 with padding. */
export function toBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });

export function utf8(text: string): Uint8Array {
  return encoder.encode(text);
}

export function fromUtf8(bytes: Uint8Array, what = 'value'): string {
  try {
    return decoder.decode(bytes);
  } catch (error) {
    throw new ByteFormatError(`${what}: not valid UTF-8 (${String(error)})`);
  }
}

/** Concatenation, because every hash in RFC 6962 is over a concatenation. */
export function concat(...parts: readonly Uint8Array[]): Uint8Array {
  let total = 0;
  for (const part of parts) total += part.byteLength;
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.byteLength;
  }
  return out;
}

/**
 * Constant-time-ish equality.
 *
 * Nothing here is a secret, so this is not a timing-attack defence; it is a defence
 * against the ordinary bug where an early return on the first differing byte gets
 * refactored into an early return on the first EQUAL byte. The loop has one exit.
 */
export function equalBytes(a: Uint8Array, b: Uint8Array): boolean {
  if (a.byteLength !== b.byteLength) return false;
  let difference = 0;
  for (let i = 0; i < a.byteLength; i += 1) difference |= (a[i] ?? 0) ^ (b[i] ?? 0);
  return difference === 0;
}
