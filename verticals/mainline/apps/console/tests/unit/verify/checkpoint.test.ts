// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The C2SP signed note, against `spec/wire/checkpoint.md` §10's conformance list.
 *
 * The anchor case is §7.5's complete note, signed by §7.1's published key — an example key
 * released deliberately so anyone can reproduce every value. The generator verified that
 * signature with Node's own crypto before writing the vector, so a failure here is this
 * implementation's, not the specification's.
 *
 * `resigned-body-different-key-spoofed-id` is the case that matters most: the note text is
 * byte-identical and the signature line carries the TRUSTED key's id, but the bytes were
 * produced by a different key. A verifier that dispatches on the key id and forgets to
 * verify passes it.
 */

import { describe, expect, it } from 'vitest';

import { fromHex, toHex } from '../../../src/verify/bytes';
import {
  NoteFormatError,
  derToRaw,
  drandRoundTime,
  parseCanonExtension,
  parseDrandExtension,
  parseNote,
  parseVerificationKey,
  verificationKeyFromSpki,
  verifyNote,
  type VerificationKey,
} from '../../../src/verify/checkpoint';
import { SOFTWARE_ORACLE } from '../../../src/verify/sha256';

import { checkpointVectors } from './_vectors';

const oracle = SOFTWARE_ORACLE;
const vectors = checkpointVectors();
const subtle = globalThis.crypto?.subtle;

async function keysFor(ids: readonly string[]): Promise<VerificationKey[]> {
  const keys: VerificationKey[] = [];
  for (const id of ids) {
    const source = id === 'A' ? vectors.keys.trusted : vectors.keys.adversary;
    keys.push(await parseVerificationKey(oracle, source.vkey));
  }
  return keys;
}

describe('vkey parsing', () => {
  it.each(vectors.vkey_parsing.map((v) => [v.id, v] as const))('%s', async (_id, v) => {
    if (v.expect !== undefined) {
      const key = await parseVerificationKey(oracle, v.vkey);
      expect(key.name).toBe(v.expect.name);
      expect(key.keyIdHex).toBe(v.expect.key_id_hex);
      expect(key.algorithm).toBe(v.expect.algorithm);
      expect(toHex(key.spki)).toBe(v.expect.spki_der_hex);
      return;
    }
    await expect(parseVerificationKey(oracle, v.vkey)).rejects.toThrow(
      new RegExp(v.expect_error ?? '.'),
    );
  });

  it('splits on the first two plus signs only', async () => {
    const vkey = vectors.keys.trusted.vkey;
    // The key material genuinely contains a "+" — otherwise the assertion is vacuous.
    expect(vkey.split('+').length).toBeGreaterThan(3);
    const key = await parseVerificationKey(oracle, vkey);
    expect(key.name).toBe(vectors.keys.trusted.origin);
  });

  it('derives the same key id from a bare SPKI', async () => {
    const key = await verificationKeyFromSpki(oracle, {
      name: vectors.keys.trusted.origin,
      spkiHex: vectors.keys.trusted.spki_der_hex,
    });
    expect(key.keyIdHex).toBe(vectors.keys.trusted.key_id_hex);
  });
});

describe('DER to raw, the bridge C2SP and WebCrypto meet on', () => {
  it('produces 64 bytes and strips the sign byte', () => {
    const der = fromHex(
      '3045022100e04abf2882fec769c7156a2ec6366e6f96b6ec46827e947db747ee1d2ece299a' +
        '022040677922ce51a00cb2f2d2bd9d79e9a3694c29fd8b211da305c5ed99850fdebb',
    );
    const raw = derToRaw(der);
    expect(raw.byteLength).toBe(64);
    expect(toHex(raw.slice(0, 32))).toBe(
      'e04abf2882fec769c7156a2ec6366e6f96b6ec46827e947db747ee1d2ece299a',
    );
    expect(toHex(raw.slice(32))).toBe(
      '40677922ce51a00cb2f2d2bd9d79e9a3694c29fd8b211da305c5ed99850fdebb',
    );
  });

  it('left-pads a short INTEGER instead of shifting it', () => {
    // r = 0x01, s = 0x02 — the pathological short case a memcpy implementation gets wrong.
    const raw = derToRaw(fromHex('3006020101020102'));
    expect(toHex(raw)).toBe(`${'00'.repeat(31)}01${'00'.repeat(31)}02`);
  });

  it('refuses anything that is not a two-INTEGER SEQUENCE', () => {
    expect(() => derToRaw(fromHex('3145022100aa'))).toThrow(NoteFormatError);
    expect(() => derToRaw(fromHex('3003020101'))).toThrow(NoteFormatError);
  });
});

describe('note parsing', () => {
  it('splits at the last empty line and keeps the text terminator', () => {
    const anchor = vectors.cases.find((c) => c.id === 'spec-7.5-complete-note');
    if (anchor?.note_text === undefined) throw new Error('vector set is truncated');
    const parsed = parseNote(anchor.full_note);
    expect(parsed.signedText).toBe(anchor.note_text);
    expect(parsed.signedText.endsWith('\n')).toBe(true);
    expect(parsed.origin).toBe(anchor.expect_parsed?.origin);
    expect(parsed.treeSize).toBe(anchor.expect_parsed?.tree_size);
    expect(parsed.rootHex).toBe(anchor.expect_parsed?.root_hex);
    expect(Object.fromEntries(parsed.extensions)).toEqual(anchor.expect_parsed?.extensions);
    expect(parsed.signatures).toHaveLength(1);
    expect(parsed.signatures[0]?.keyIdHex).toBe(vectors.keys.trusted.key_id_hex);
  });

  it('preserves an unknown signature line byte for byte', () => {
    const extra = vectors.cases.find((c) => c.id === 'unknown-extra-signature-line-is-ignored');
    if (extra === undefined) throw new Error('vector set is truncated');
    const parsed = parseNote(extra.full_note);
    expect(parsed.signatures).toHaveLength(2);
    const reencoded = parsed.signedText + '\n' + parsed.signatures.map((s) => s.line).join('');
    expect(reencoded).toBe(extra.full_note);
  });

  it('reads the canon and drand extension lines', () => {
    const anchor = vectors.cases.find((c) => c.id === 'spec-7.5-complete-note');
    const parsed = parseNote(anchor?.full_note ?? '');
    const canon = parseCanonExtension(parsed.extensions.get('canon') ?? '');
    expect(canon.payloadVer).toBe(1);
    expect(canon.canonSrcSha256).toHaveLength(64);

    const drand = parseDrandExtension(parsed.extensions.get('drand') ?? '');
    expect(drand.round).toBe(31088494);
    // spec §7.3: 1692803367 + (31088494 − 1) × 3 = 1786068846 = 2026-08-07T02:14:06Z.
    expect(drandRoundTime(drand.round)).toBe(1786068846);
    expect(drand.roundTimeIso).toBe('2026-08-07T02:14:06.000Z');
  });
});

describe('verifyNote — the whole conformance list', () => {
  it.runIf(subtle !== undefined).each(vectors.cases.map((c) => [c.id, c] as const))(
    '%s',
    async (_id, testCase) => {
      const result = await verifyNote({
        note: testCase.full_note,
        keys: await keysFor(testCase.trust),
        oracle,
        subtle,
      });
      expect(result.verdict, `${testCase.note}\n${result.reason}`).toBe(testCase.expect);
      if (testCase.expect_reason_contains !== undefined) {
        expect(result.reason.toLowerCase()).toContain(testCase.expect_reason_contains.toLowerCase());
      }
      if (testCase.expect === 'verified') {
        expect(result.reason).toBe('');
        expect(result.verifiedBy.length).toBeGreaterThan(0);
      }
      if (testCase.signed_text_sha256 !== undefined) {
        expect(result.signedTextSha256).toBe(testCase.signed_text_sha256);
      }
      if (testCase.expect_ignored_signature_names !== undefined) {
        expect(result.ignored).toEqual([...testCase.expect_ignored_signature_names]);
      }
    },
  );

  it.runIf(subtle !== undefined)('rejects the anchor note after ANY single-byte mutation', async () => {
    const anchor = vectors.cases.find((c) => c.id === 'spec-7.5-complete-note');
    if (anchor?.note_text === undefined) throw new Error('vector set is truncated');
    const keys = await keysFor(['A']);
    const text = anchor.note_text;

    // Every 17th offset, so the suite stays fast while still crossing every line.
    for (let offset = 0; offset < text.length; offset += 17) {
      const original = text.charAt(offset);
      if (original === '\n') continue;
      const replacement = original === 'a' ? 'b' : 'a';
      const mutatedText = text.slice(0, offset) + replacement + text.slice(offset + 1);
      const mutatedNote = anchor.full_note.replace(text, mutatedText);
      const result = await verifyNote({ note: mutatedNote, keys, oracle, subtle });
      expect(result.verdict, `offset ${offset}`).not.toBe('verified');
    }
  });

  it('SKIPS rather than passing when no key is configured', async () => {
    const anchor = vectors.cases.find((c) => c.id === 'spec-7.5-complete-note');
    const result = await verifyNote({ note: anchor?.full_note ?? '', keys: [], oracle, subtle });
    expect(result.verdict).toBe('skipped');
    expect(result.reason).toContain('no verification key is configured');
    // The note still parsed — a SKIP is not a refusal to look at the bytes.
    expect(result.note?.treeSize).toBe(5);
  });

  it('SKIPS with a named reason when WebCrypto is absent', async () => {
    const anchor = vectors.cases.find((c) => c.id === 'spec-7.5-complete-note');
    const result = await verifyNote({
      note: anchor?.full_note ?? '',
      keys: await keysFor(['A']),
      oracle,
      subtle: undefined,
    });
    expect(result.verdict).toBe('skipped');
    expect(result.reason).toContain('crypto.subtle is unavailable');
    expect(result.reason).toContain('no seal on this checkpoint is green');
  });
});
