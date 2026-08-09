// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The C2SP signed note — parse, then verify, and never the other way round.
 *
 * A profile of `c2sp.org/tlog-checkpoint` over `c2sp.org/signed-note@v1.0.0`, normatively
 * specified in `spec/wire/checkpoint.md` v1.0 (frozen 2026-08-07). This module implements
 * §6's algorithm in §6's order, including step 7:
 *
 *   > Only then read the tree size, root and extensions. **Unverified note text is not
 *   > data.**
 *
 * That ordering is why `verifyNote()` returns the parsed note only alongside a verdict,
 * and why a caller cannot reach `ParsedNote.treeSize` without having seen whether any
 * trusted key signed it. A verifier that parses first and checks later has already let
 * attacker-chosen bytes into its state machine.
 *
 * ── THE FOUR ERRORS THIS FORMAT PUNISHES ──────────────────────────────────────────
 *
 * 1. **The em dash.** A signature line starts with U+2014, not U+002D and not U+2013.
 *    Getting it wrong produces a note that parses as one long text with no signatures,
 *    which then fails for the wrong reason. Both wrong dashes are committed vectors.
 * 2. **DER, not `r‖s`.** C2SP signature type `0x02` is "ECDSA as implemented by
 *    transparency-dev/witness", whose verifier calls Go's `ecdsa.VerifyASN1` — that is
 *    DER — and AWS KMS returns DER for `ECDSA_SHA_256`. WebCrypto, meanwhile, accepts
 *    ONLY the fixed-width 64-byte `r‖s` form. The conversion in `derToRaw` below is the
 *    entire bridge, and an implementer who assumed one encoding or the other fails
 *    verification against a genuine signature.
 * 3. **The key ID derivation.** For type `0x02` it is `SHA-256(DER SPKI)[:4]` — the SPKI
 *    ALONE, no name and no algorithm byte. That is different from the Ed25519 (`0x01`)
 *    rule, and deriving it the Ed25519 way produces a note that "verifies" against
 *    nothing.
 * 4. **The vkey's third field contains `+`.** Base64's alphabet includes it, so a parser
 *    that splits on every plus gets four fields for most keys and three for the rest — a
 *    bug that passes in testing and fails on the next key you generate. Split on the
 *    first two separators only, and RECOMPUTE the key ID rather than trusting the field.
 *
 * ── WHERE THE KEY COMES FROM, AND WHY IT IS NEVER BUNDLED ─────────────────────────
 *
 * The public key is supplied by CONFIGURATION — a build-time constant, a URL parameter in
 * the harness, or an operator paste. It is a public key, so it is not a secret; the reason
 * it is never taken from the bundle is different and more important. `ledger.schema.json`
 * says it plainly: *a bundle that carries its own trust anchor proves nothing*. A
 * checkpoint verified against a key that arrived in the same payload is reported with
 * `trust: 'self-asserted'` and is a DISTINCT verdict on screen, never a green seal.
 */

import { ByteFormatError, concat, digestFromHex, fromBase64, fromHex, toHex, utf8 } from './bytes';
import type { Sha256Oracle } from './sha256';

export const EM_DASH = '—';

/** C2SP signature type for ECDSA P-256 / SHA-256 / DER (spec §5.1, ruling CU-3). */
export const SIGNATURE_TYPE_ECDSA_P256 = 0x02;

// ── Shapes ─────────────────────────────────────────────────────────────────

export interface NoteSignature {
  /** The key name on the line. For the log signature this is the origin. */
  readonly name: string;
  readonly keyIdHex: string;
  /** The signature bytes after the 4-byte key ID. DER for type 0x02. */
  readonly signature: Uint8Array;
  /** The line, verbatim, including its newline. Preserved byte for byte on re-encode. */
  readonly line: string;
}

export interface ParsedNote {
  /** The signed bytes: the note text INCLUDING its own final newline. */
  readonly signedText: string;
  readonly origin: string;
  readonly treeSize: number;
  readonly rootHex: string;
  readonly rootBytes: Uint8Array;
  /** Extension lines, `name` → `value`, in the order they appeared. */
  readonly extensions: ReadonlyMap<string, string>;
  readonly signatures: readonly NoteSignature[];
}

export type KeyTrust = 'configured' | 'self-asserted';

export interface VerificationKey {
  readonly name: string;
  readonly keyIdHex: string;
  readonly algorithm: number;
  /** DER SubjectPublicKeyInfo. */
  readonly spki: Uint8Array;
  /**
   * `configured` — supplied out of band and therefore load-bearing.
   * `self-asserted` — read from the same payload as the checkpoint. Proves nothing on its
   * own, and the surface says so rather than showing a green seal.
   */
  readonly trust: KeyTrust;
}

export type CheckpointVerdict = 'verified' | 'failed' | 'malformed' | 'skipped';

export interface CheckpointResult {
  readonly verdict: CheckpointVerdict;
  /** Verbatim, rendered without paraphrase. Empty exactly when `verified`. */
  readonly reason: string;
  /** Null when the note could not be parsed. Never populated from unverified bytes. */
  readonly note: ParsedNote | null;
  /** Names of keys whose signature verified. */
  readonly verifiedBy: readonly string[];
  /** Names on lines that were IGNORED because the key is unknown. Not a failure. */
  readonly ignored: readonly string[];
  /** The trust status of the key that carried the verdict, when there was one. */
  readonly trust: KeyTrust | null;
  /** SHA-256 of the signed bytes, lowercase hex. Displayed beside the seal. */
  readonly signedTextSha256: string;
}

export class NoteFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NoteFormatError';
  }
}

// ── Parsing ────────────────────────────────────────────────────────────────

const ORIGIN_LINE = /^[^\s+]+$/;
const TREE_SIZE_LINE = /^(0|[1-9][0-9]*)$/;
const EXTENSION_LINE = /^([a-z][a-z0-9.]*): (.+)$/;
const SIGNATURE_LINE = new RegExp(`^${EM_DASH} ([^\\s]+) ([A-Za-z0-9+/]+={0,2})$`);

/**
 * Split a note into signed text and signature lines, then parse both.
 *
 * Throws `NoteFormatError` for anything malformed. The caller turns that into a
 * `malformed` verdict, which is deliberately NOT the same as `failed`: a note that will
 * not parse has not been accused of carrying a bad signature.
 */
export function parseNote(note: string): ParsedNote {
  if (note.includes('\r')) {
    throw new NoteFormatError(
      'the note contains a carriage return. The signed bytes are LF-terminated; a CRLF ' +
        'checkout would change every signature, so CR is refused rather than normalised.',
    );
  }

  const separator = note.lastIndexOf('\n\n');
  if (separator < 0) {
    throw new NoteFormatError(
      'the note has no empty line, so it has no signature section. The note text is ' +
        'separated from the signatures by the LAST empty line (spec §2). Unverified note ' +
        'text is not data, so a note with no signatures is refused rather than displayed.',
    );
  }

  const signedText = note.slice(0, separator + 1);
  const signatureBlock = note.slice(separator + 2);

  for (const character of signedText) {
    const code = character.codePointAt(0) ?? 0;
    if (code < 0x20 && character !== '\n') {
      throw new NoteFormatError(
        `the note text contains the control character U+${code.toString(16).padStart(4, '0').toUpperCase()}. ` +
          'Spec §6.2: no ASCII control character other than U+000A anywhere outside the ' +
          'signature lines.',
      );
    }
  }

  const lines = signedText.split('\n');
  // `signedText` ends in a newline, so `split` leaves an empty final element.
  const last = lines.pop();
  if (last !== '') {
    throw new NoteFormatError('the note text does not end in a newline');
  }
  if (lines.length < 3) {
    throw new NoteFormatError(
      `the note text has ${lines.length} line(s); at least three are required ` +
        '(origin, tree size, root hash).',
    );
  }

  const origin = lines[0] ?? '';
  if (!ORIGIN_LINE.test(origin)) {
    throw new NoteFormatError(
      `origin line ${JSON.stringify(origin)} is empty, or contains whitespace or "+", which ` +
        'C2SP forbids so that a vkey\'s first two separators are unambiguous.',
    );
  }

  const sizeLine = lines[1] ?? '';
  if (!TREE_SIZE_LINE.test(sizeLine)) {
    throw new NoteFormatError(
      `tree size line ${JSON.stringify(sizeLine)} is not ASCII decimal without a leading zero. ` +
        '"05" and "5" would be two different signed texts for one tree.',
    );
  }
  const treeSize = Number.parseInt(sizeLine, 10);

  const rootLine = lines[2] ?? '';
  let rootBytes: Uint8Array;
  try {
    rootBytes = fromBase64(rootLine, 'root hash');
  } catch (error) {
    throw new NoteFormatError(
      error instanceof ByteFormatError ? error.message : String(error),
    );
  }
  if (rootBytes.byteLength !== 32) {
    throw new NoteFormatError(
      `the root line decodes to ${rootBytes.byteLength} bytes; spec §3 requires exactly 32 bytes.`,
    );
  }

  const extensions = new Map<string, string>();
  for (let i = 3; i < lines.length; i += 1) {
    const line = lines[i] ?? '';
    if (line === '') {
      throw new NoteFormatError(
        `note text line ${i + 1} is empty. Extension lines are non-empty and the blank line ` +
          'belongs to the framing, not to the text.',
      );
    }
    const match = EXTENSION_LINE.exec(line);
    if (match === null) {
      throw new NoteFormatError(
        `note text line ${i + 1} is not an extension line. The form is "<name>: <value>" with ` +
          'name matching [a-z][a-z0-9.]* and exactly one space after the colon.',
      );
    }
    const name = match[1] ?? '';
    if (extensions.has(name)) {
      throw new NoteFormatError(
        `extension "${name}" appears twice. Each name appears at most once, so that the note ` +
          'text is a function of its content (spec §4).',
      );
    }
    extensions.set(name, match[2] ?? '');
  }

  const signatures: NoteSignature[] = [];
  const rawSignatureLines = signatureBlock.split('\n');
  const trailing = rawSignatureLines.pop();
  if (trailing !== '') {
    throw new NoteFormatError('the last signature line does not end in a newline');
  }
  if (rawSignatureLines.length === 0) {
    throw new NoteFormatError('the note carries no signature lines');
  }
  for (const line of rawSignatureLines) {
    const match = SIGNATURE_LINE.exec(line);
    if (match === null) {
      const firstChar = line.slice(0, 1);
      const hint =
        firstChar === '-' || firstChar === '–'
          ? ` It starts with U+${(firstChar.codePointAt(0) ?? 0).toString(16).padStart(4, '0').toUpperCase()}; ` +
            'a signature line starts with the em dash U+2014. This is the single most common ' +
            'implementation error in the format.'
          : '';
      throw new NoteFormatError(
        `signature line ${JSON.stringify(line)} does not match "U+2014 SPACE name SPACE base64".${hint}`,
      );
    }
    const decoded = fromBase64(match[2] ?? '', 'signature line');
    if (decoded.byteLength < 5) {
      throw new NoteFormatError(
        'a signature line decodes to fewer than 5 bytes; it must carry a 4-byte key ID ' +
          'followed by the signature.',
      );
    }
    signatures.push({
      name: match[1] ?? '',
      keyIdHex: toHex(decoded.slice(0, 4)),
      signature: decoded.slice(4),
      line: `${line}\n`,
    });
  }

  return { signedText, origin, treeSize, rootHex: toHex(rootBytes), rootBytes, extensions, signatures };
}

// ── The verifier key ───────────────────────────────────────────────────────

/**
 * Parse a C2SP vkey: `<name>+<8 hex key id>+<base64(algorithm ‖ DER SPKI)>`.
 *
 * The key ID is RECOMPUTED as `SHA-256(DER SPKI)[:4]` and compared with the stated field.
 * The field is a convenience; the derivation is the fact. A vkey whose stated ID does not
 * match is refused rather than trusted, because trusting it would let a caller bind a
 * signature to whichever key ID they wanted.
 */
export async function parseVerificationKey(
  oracle: Sha256Oracle,
  vkey: string,
  trust: KeyTrust = 'configured',
): Promise<VerificationKey> {
  // Split on the FIRST TWO separators only. The third field is standard base64, whose
  // alphabet contains "+".
  const firstPlus = vkey.indexOf('+');
  if (firstPlus < 0) throw new NoteFormatError('vkey has no "+" separator');
  const secondPlus = vkey.indexOf('+', firstPlus + 1);
  if (secondPlus < 0) throw new NoteFormatError('vkey has only one "+" separator; three fields are required');

  const name = vkey.slice(0, firstPlus);
  const statedKeyId = vkey.slice(firstPlus + 1, secondPlus);
  const material = vkey.slice(secondPlus + 1);

  if (name === '') throw new NoteFormatError('vkey key name is empty');
  if (!/^[0-9a-f]{8}$/.test(statedKeyId)) {
    throw new NoteFormatError(`vkey key id ${JSON.stringify(statedKeyId)} is not 8 lowercase hex characters`);
  }

  const decoded = fromBase64(material, 'vkey key material');
  const algorithm = decoded[0];
  if (algorithm === undefined) throw new NoteFormatError('vkey key material is empty');
  if (algorithm !== SIGNATURE_TYPE_ECDSA_P256) {
    throw new NoteFormatError(
      `vkey declares signature algorithm 0x${algorithm.toString(16).padStart(2, '0')}; this ` +
        'verifier implements only 0x02 (ECDSA P-256, SHA-256, DER). Type 0x01 is Ed25519, ' +
        'whose key-ID derivation is different — refusing beats guessing.',
    );
  }
  const spki = decoded.slice(1);
  const derived = toHex((await oracle.digest(spki)).slice(0, 4));
  if (derived !== statedKeyId) {
    throw new NoteFormatError(
      `vkey states key id ${statedKeyId} but SHA-256(DER SPKI)[:4] is ${derived}. The stated ` +
        'field is never trusted; the derivation is.',
    );
  }

  return { name, keyIdHex: derived, algorithm, spki, trust };
}

/** Build a key from an SPKI supplied as hex or base64, deriving its ID. */
export async function verificationKeyFromSpki(
  oracle: Sha256Oracle,
  options: {
    readonly name: string;
    readonly spkiHex?: string;
    readonly spkiBase64?: string;
    readonly trust?: KeyTrust;
  },
): Promise<VerificationKey> {
  const { name, spkiHex, spkiBase64 } = options;
  const spki =
    spkiHex !== undefined
      ? fromHex(spkiHex, 'SPKI')
      : spkiBase64 !== undefined
        ? fromBase64(spkiBase64, 'SPKI')
        : null;
  if (spki === null) throw new NoteFormatError('no SPKI supplied (expected spkiHex or spkiBase64)');
  return {
    name,
    keyIdHex: toHex((await oracle.digest(spki)).slice(0, 4)),
    algorithm: SIGNATURE_TYPE_ECDSA_P256,
    spki,
    trust: options.trust ?? 'configured',
  };
}

// ── DER → raw, the bridge between C2SP and WebCrypto ───────────────────────

/**
 * `SEQUENCE { r INTEGER, s INTEGER }` → the fixed-width 64-byte `r‖s` WebCrypto wants.
 *
 * DER INTEGERs are signed and minimally encoded: a leading `0x00` appears exactly when the
 * high bit of the first content byte is set, and short values are shorter than 32 bytes.
 * Both are handled here by left-padding into a fixed 32-byte field. A verifier that
 * memcpy'd the DER content would fail on roughly half of all signatures — the half whose
 * `r` happens to have its high bit set — which is the kind of defect that passes every
 * test written on a Tuesday.
 */
export function derToRaw(der: Uint8Array): Uint8Array {
  let index = 0;
  const byte = (): number => {
    const value = der[index];
    if (value === undefined) throw new NoteFormatError('DER signature ended unexpectedly');
    index += 1;
    return value;
  };

  if (byte() !== 0x30) throw new NoteFormatError('DER signature does not start with SEQUENCE (0x30)');
  let sequenceLength = byte();
  if (sequenceLength === 0x81) sequenceLength = byte();
  else if (sequenceLength > 0x80) throw new NoteFormatError('DER signature length is not short-form or 0x81');
  if (index + sequenceLength !== der.byteLength) {
    throw new NoteFormatError(
      `DER SEQUENCE declares ${sequenceLength} content bytes but ${der.byteLength - index} follow.`,
    );
  }

  const readInteger = (): Uint8Array => {
    if (byte() !== 0x02) throw new NoteFormatError('DER signature member is not an INTEGER (0x02)');
    const length = byte();
    if (length === 0 || length > 33) throw new NoteFormatError(`DER INTEGER length ${length} is out of range`);
    const value = der.slice(index, index + length);
    if (value.byteLength !== length) throw new NoteFormatError('DER INTEGER ran past the end of the signature');
    index += length;
    // Strip the sign byte, then left-pad into 32 bytes.
    let start = 0;
    while (start < value.byteLength - 1 && value[start] === 0x00) start += 1;
    const trimmed = value.slice(start);
    if (trimmed.byteLength > 32) throw new NoteFormatError('DER INTEGER is wider than 32 bytes; this is not P-256');
    const padded = new Uint8Array(32);
    padded.set(trimmed, 32 - trimmed.byteLength);
    return padded;
  };

  const r = readInteger();
  const s = readInteger();
  if (index !== der.byteLength) throw new NoteFormatError('DER signature carries trailing bytes');
  return concat(r, s);
}

// ── Verification ───────────────────────────────────────────────────────────

export interface VerifyNoteOptions {
  readonly note: string;
  /** The keys this verifier trusts. An empty set produces `skipped`, never `verified`. */
  readonly keys: readonly VerificationKey[];
  readonly oracle: Sha256Oracle;
  /** Injected so tests need no global patching. Defaults to the platform's. */
  readonly subtle?: SubtleCrypto | undefined;
}

/**
 * spec/wire/checkpoint.md §6, in order.
 *
 * The three non-obvious rules, all of which have committed vectors:
 *
 *   • a line whose `(name, key ID)` is unknown is IGNORED, not failed — that is what lets
 *     witnesses cosign without any format change;
 *   • if ANY signature from a KNOWN key fails, the whole note is rejected;
 *   • if NO signature from a known key verified, the note is rejected. "Ignored" is not
 *     "passed", and a note nobody could check is not a note that checked out.
 */
export async function verifyNote(options: VerifyNoteOptions): Promise<CheckpointResult> {
  const { keys, oracle } = options;
  // `Object.hasOwn`, not `??`. A caller that explicitly passes `subtle: undefined` is
  // saying "this environment has no WebCrypto" — the insecure-origin case — and `??`
  // would quietly hand it the platform's, which is the one substitution that would make
  // this function report a green verdict for an environment that cannot produce one.
  const subtle: SubtleCrypto | undefined = Object.hasOwn(options, 'subtle')
    ? options.subtle
    : globalThis.crypto?.subtle;

  let parsed: ParsedNote;
  try {
    parsed = parseNote(options.note);
  } catch (error) {
    return {
      verdict: 'malformed',
      reason: error instanceof Error ? error.message : String(error),
      note: null,
      verifiedBy: [],
      ignored: [],
      trust: null,
      signedTextSha256: '',
    };
  }

  const signedBytes = utf8(parsed.signedText);
  const signedTextSha256 = toHex(await oracle.digest(signedBytes));

  if (keys.length === 0) {
    return {
      verdict: 'skipped',
      reason:
        'no verification key is configured, so nothing on this checkpoint has been checked. ' +
        'A public key that arrives in the same bundle as the checkpoint is not a trust anchor; ' +
        'supply one out of band.',
      note: parsed,
      verifiedBy: [],
      ignored: parsed.signatures.map((signature) => signature.name),
      trust: null,
      signedTextSha256,
    };
  }

  if (subtle === undefined) {
    return {
      verdict: 'skipped',
      reason:
        'crypto.subtle is unavailable, so the ECDSA P-256 signature could not be checked here. ' +
        'WebCrypto is exposed only in a secure context (HTTPS, localhost, or a local file). ' +
        'The Merkle arithmetic on this page still ran — the software SHA-256 in src/verify/ ' +
        'does not need a secure context — but the SIGNATURE has not been verified, and no seal ' +
        'on this checkpoint is green. Serve the console over HTTPS and reload.',
      note: parsed,
      verifiedBy: [],
      ignored: [],
      trust: null,
      signedTextSha256,
    };
  }

  const known = new Map<string, VerificationKey>();
  for (const key of keys) known.set(`${key.name} ${key.keyIdHex}`, key);

  const verifiedBy: string[] = [];
  const ignored: string[] = [];
  let trust: KeyTrust | null = null;

  for (const signature of parsed.signatures) {
    const key = known.get(`${signature.name} ${signature.keyIdHex}`);
    if (key === undefined) {
      ignored.push(signature.name);
      continue;
    }

    let raw: Uint8Array;
    try {
      raw = derToRaw(signature.signature);
    } catch (error) {
      return {
        verdict: 'failed',
        reason:
          `the signature line for key "${signature.name}" (${signature.keyIdHex}) is not a valid ` +
          `DER ECDSA signature: ${error instanceof Error ? error.message : String(error)}`,
        note: parsed,
        verifiedBy,
        ignored,
        trust: key.trust,
        signedTextSha256,
      };
    }

    let ok: boolean;
    try {
      const imported = await subtle.importKey(
        'spki',
        copyOf(key.spki),
        { name: 'ECDSA', namedCurve: 'P-256' },
        false,
        ['verify'],
      );
      ok = await subtle.verify(
        { name: 'ECDSA', hash: 'SHA-256' },
        imported,
        copyOf(raw),
        copyOf(signedBytes),
      );
    } catch (error) {
      return {
        verdict: 'failed',
        reason:
          `WebCrypto refused the key or the signature for "${signature.name}" ` +
          `(${signature.keyIdHex}): ${error instanceof Error ? error.message : String(error)}`,
        note: parsed,
        verifiedBy,
        ignored,
        trust: key.trust,
        signedTextSha256,
      };
    }

    if (!ok) {
      return {
        verdict: 'failed',
        reason:
          `the signature from the KNOWN key "${signature.name}" (${signature.keyIdHex}) does not ` +
          'verify over the note text. Either the note text was altered after signing, or the ' +
          'line was produced by a different key presented under this one\'s id. Spec §6.6: if ' +
          'any signature from a known key fails, the whole note is rejected.',
        note: parsed,
        verifiedBy,
        ignored,
        trust: key.trust,
        signedTextSha256,
      };
    }

    verifiedBy.push(signature.name);
    trust = trust === 'self-asserted' ? trust : key.trust;
  }

  if (verifiedBy.length === 0) {
    return {
      verdict: 'failed',
      reason:
        'no signature from a known key verified this note. Every line carried a key this ' +
        `verifier does not hold (${ignored.join(', ') || 'none'}), and an ignored line is not a ` +
        'passed line.',
      note: parsed,
      verifiedBy,
      ignored,
      trust: null,
      signedTextSha256,
    };
  }

  return { verdict: 'verified', reason: '', note: parsed, verifiedBy, ignored, trust, signedTextSha256 };
}

/**
 * A fresh `ArrayBuffer` holding exactly these bytes.
 *
 * A `Uint8Array` may be a view with a non-zero `byteOffset` over a larger or shared
 * buffer. Handing WebCrypto the underlying buffer would verify over the neighbours.
 */
function copyOf(bytes: Uint8Array): ArrayBuffer {
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  return buffer;
}

// ── Extension lines ────────────────────────────────────────────────────────

export interface CanonExtension {
  readonly payloadVer: number;
  readonly canonSrcSha256: string;
}

/** Parse the `canon:` line: `<payload_ver decimal> <64 lowercase hex>` (spec §4.1). */
export function parseCanonExtension(value: string): CanonExtension {
  const match = /^([0-9]+) ([0-9a-f]{64})$/.exec(value);
  if (match === null) {
    throw new NoteFormatError(
      `canon extension ${JSON.stringify(value)} is not "<payload_ver> <64 lowercase hex>".`,
    );
  }
  return {
    payloadVer: Number.parseInt(match[1] ?? '0', 10),
    canonSrcSha256: match[2] ?? '',
  };
}

/** drand quicknet genesis and period, from spec §4.2. Round → UNIX seconds. */
export const DRAND_QUICKNET_GENESIS = 1_692_803_367;
export const DRAND_QUICKNET_PERIOD = 3;

export function drandRoundTime(round: number): number {
  return DRAND_QUICKNET_GENESIS + (round - 1) * DRAND_QUICKNET_PERIOD;
}

export interface DrandExtension {
  readonly chainHash: string;
  readonly round: number;
  readonly randomness: string;
  /** ISO-8601 UTC instant the round could not have existed before. */
  readonly roundTimeIso: string;
}

/**
 * Parse the `drand:` line.
 *
 * The round-to-time arithmetic is verifiable offline with no dependency and IS checked.
 * The BLS12-381 G1 signature over the round is NOT — no browser primitive verifies it and
 * `cryptography` has no BLS either, so `trappoint-verify` reports the same SKIP. The
 * `drand:` line alone is therefore not a lower bound a stranger can check, and no surface
 * in this console may present it as one.
 */
export function parseDrandExtension(value: string): DrandExtension {
  const match = /^([0-9a-f]{64}) ([0-9]+) ([0-9a-f]{64})$/.exec(value);
  if (match === null) {
    throw new NoteFormatError(
      `drand extension ${JSON.stringify(value)} is not "<64 hex chain> <round> <64 hex randomness>".`,
    );
  }
  const round = Number.parseInt(match[2] ?? '0', 10);
  return {
    chainHash: match[1] ?? '',
    round,
    randomness: match[3] ?? '',
    roundTimeIso: new Date(drandRoundTime(round) * 1000).toISOString(),
  };
}

/** Check 10: does the checkpoint name the canonicaliser the reader pinned? */
export function compareCanonSource(
  noteValue: string,
  pinnedSha256: string | null,
): { readonly status: 'match' | 'mismatch' | 'unpinned'; readonly detail: string } {
  const parsedCanon = parseCanonExtension(noteValue);
  if (pinnedSha256 === null) {
    return {
      status: 'unpinned',
      detail:
        `the checkpoint names canonicaliser ${parsedCanon.canonSrcSha256} (payload_ver ` +
        `${parsedCanon.payloadVer}), but this console has no pin to compare it against. ` +
        'Check 10 is SKIPPED, not passed: comparing a value against itself proves nothing.',
    };
  }
  if (parsedCanon.canonSrcSha256 === pinnedSha256) {
    return {
      status: 'match',
      detail:
        `the checkpoint names canonicaliser ${parsedCanon.canonSrcSha256}, which is the value ` +
        `pinned in spec/custody/canon-registry.yaml for payload_ver ${parsedCanon.payloadVer}.`,
    };
  }
  return {
    status: 'mismatch',
    detail:
      `the checkpoint names canonicaliser ${parsedCanon.canonSrcSha256}; the pinned value is ` +
      `${pinnedSha256}. Re-canonicalising an old leaf under a newer version changes this line, ` +
      'and this line is signed.',
  };
}

/** Convenience for a caller that holds a hex root and wants the bytes. */
export function rootBytesFromHex(hexValue: string): Uint8Array {
  return digestFromHex(hexValue, 'root');
}
