// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * RFC 8785 — JSON Canonicalization Scheme, in TypeScript, with no dependencies.
 *
 * This is the browser half of a two-implementation contract. The other half is
 * `packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py`, which is vendored byte-for-byte
 * into `trappoint-verify` and whose SHA-256 is written into every checkpoint as
 * `canon_src_sha256`. `tests/vectors/jcs.json` carries the Python implementation's output
 * for every case below; if the two ever disagree, CI fails on whichever side moved. A
 * vector is never edited to make an implementation pass.
 *
 * ── WHY A HASH OF BYTES NOBODY CAN REPRODUCE IS NOT EVIDENCE ──────────────────────
 *
 * CockroachDB cannot produce the hashed bytes: `sha256()` returns hex *text*, and `JSONB`
 * normalises and reorders keys, so `sha256(payload::STRING)` is a number only we can
 * compute. Canonicalisation is therefore client-side, versioned and frozen — and the
 * console recomputes it in the reader's own browser rather than trusting the value the
 * database sent.
 *
 * ── THE THREE PLACES EVERY NAIVE PORT IS WRONG ────────────────────────────────────
 *
 * 1. **Number layout.** ECMAScript switches to exponential notation below 1e-6 and at or
 *    above 1e21. Python's `repr` switches at 1e-4 and 1e16. `1e-5` is `0.00001` here and
 *    `'1e-05'` in Python; `1e17` is `100000000000000000` here and `'1e+17'` in Python.
 *    In JavaScript this half is free — `String(n)` IS `Number::toString` — which is why
 *    the risk lives entirely on the Python side and why the vectors were captured there.
 *
 * 2. **Member ordering.** RFC 8785 §3.2.3 sorts by the **UTF-16 code unit** sequence, not
 *    by code point. U+1F602 encodes as the surrogate pair D83D DE02 and therefore sorts
 *    BELOW U+FB33, whose code point is far lower. In JavaScript this half is also free —
 *    the `<` operator on strings compares UTF-16 code units — so `Array.prototype.sort()`
 *    with the default comparator is exactly the specified order. The comparator below is
 *    written out anyway, because "the default happens to be right" is a fact a reader
 *    should be able to check rather than a coincidence they have to trust.
 *
 * 3. **String escaping.** Seven short escapes and nothing else; every other C0 control as
 *    lowercase `\u00xx`; the solidus emitted literally; U+007F literal; astral characters
 *    literal.
 *
 * ── THE ONE THING THIS IMPLEMENTATION CANNOT DO, STATED PLAINLY ───────────────────
 *
 * The Python canonicaliser refuses an integer outside ±(2**53 − 1), because an
 * exact-integer implementation and an ECMAScript one would emit different digits for it.
 * **This implementation cannot make that refusal and does not pretend to.** By the time a
 * JSON number reaches JavaScript it is already an IEEE-754 double and the offending digits
 * are already gone. The same limit means the CU-5 evidentiary profile — *no evidentiary
 * quantity is a binary float* — is unenforceable here: JavaScript cannot distinguish `1`
 * from `1.0`. Both rules are WRITING-side rules, enforced in Python where the distinction
 * exists. `tests/vectors/jcs.json` records the asymmetry as data (`enforced_by`), so it is
 * a documented fact rather than a silent divergence.
 */

// ── Errors ─────────────────────────────────────────────────────────────────

/** Base class. Every refusal in this module is one of these. */
export class CanonicalisationError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'CanonicalisationError';
    this.code = code;
  }
}

export function nonFiniteNumber(value: number): CanonicalisationError {
  return new CanonicalisationError(
    'NonFiniteNumber',
    `${String(value)} has no JSON serialisation; JSON has no NaN and no infinity literal`,
  );
}

export function invalidString(where: string): CanonicalisationError {
  return new CanonicalisationError(
    'InvalidString',
    `${where} contains an unpaired surrogate and has no UTF-8 encoding`,
  );
}

export function unsupportedType(value: unknown): CanonicalisationError {
  return new CanonicalisationError(
    'UnsupportedType',
    `${typeof value} is not a JSON value; convert it before canonicalising`,
  );
}

export function duplicateKey(name: string): CanonicalisationError {
  return new CanonicalisationError(
    'DuplicateKey',
    `object member ${JSON.stringify(name)} appears more than once. RFC 8785 §3.1 requires ` +
      'input free of duplicates; resolving last-wins would choose, on the writer\'s behalf, ' +
      'which of two records was signed.',
  );
}

export function depthExceeded(limit: number): CanonicalisationError {
  return new CanonicalisationError(
    'DepthExceeded',
    `structure nests deeper than MAX_DEPTH=${limit}`,
  );
}

// ── Constants ──────────────────────────────────────────────────────────────

/**
 * Structural depth limit, matching `canon_v1.MAX_DEPTH`. Evidentiary payloads are shallow;
 * unbounded recursion inside a verifier running on a hostile bundle is a denial-of-service
 * surface, not a feature.
 */
export const MAX_DEPTH = 64;

/** The value written to `ledger_intake.payload_ver`. The verifier dispatches on it. */
export const CANON_VERSION = 1;

/** RFC 8785 §3.2.2.2 — the seven short escapes. `\/` is deliberately absent. */
const SHORT_ESCAPES = new Map<number, string>([
  [0x08, '\\b'],
  [0x09, '\\t'],
  [0x0a, '\\n'],
  [0x0c, '\\f'],
  [0x0d, '\\r'],
  [0x22, '\\"'],
  [0x5c, '\\\\'],
]);

// ── The serialiser ─────────────────────────────────────────────────────────

/**
 * RFC 8785 §3.2.3: sort by the UTF-16 code unit sequence of the member name.
 *
 * ECMAScript's relational operators on strings compare UTF-16 code units, so this IS the
 * specified order. It is written out rather than left implicit so that a reader can see
 * which ordering was intended and a future refactor cannot swap in a locale-aware
 * comparison without deleting this function first.
 */
export function compareMemberNames(a: string, b: string): number {
  if (a === b) return 0;
  return a < b ? -1 : 1;
}

function assertEncodable(value: string, where: string): void {
  for (let i = 0; i < value.length; i += 1) {
    const unit = value.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = i + 1 < value.length ? value.charCodeAt(i + 1) : 0;
      if (next < 0xdc00 || next > 0xdfff) throw invalidString(where);
      i += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw invalidString(where);
    }
  }
}

function serialiseString(value: string, where: string, out: string[]): void {
  assertEncodable(value, where);
  out.push('"');
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? 0;
    const escape = SHORT_ESCAPES.get(codePoint);
    if (escape !== undefined) {
      out.push(escape);
    } else if (codePoint < 0x20) {
      out.push(`\\u${codePoint.toString(16).padStart(4, '0')}`);
    } else {
      out.push(character);
    }
  }
  out.push('"');
}

/**
 * RFC 8785 §3.2.2.3 — ECMAScript number serialisation.
 *
 * `String(n)` is the ECMAScript `Number::toString` algorithm, which is exactly what the
 * specification cites. `-0` collapses to `"0"` because `String(-0)` is `"0"`.
 */
export function es6Number(value: number): string {
  if (!Number.isFinite(value)) throw nonFiniteNumber(value);
  return String(value);
}

function serialise(value: unknown, out: string[], depth: number, path: string): void {
  if (depth > MAX_DEPTH) throw depthExceeded(MAX_DEPTH);

  if (value === null) {
    out.push('null');
    return;
  }
  switch (typeof value) {
    case 'boolean':
      out.push(value ? 'true' : 'false');
      return;
    case 'string':
      serialiseString(value, path, out);
      return;
    case 'number':
      out.push(es6Number(value));
      return;
    case 'object':
      break;
    default:
      throw unsupportedType(value);
  }

  if (Array.isArray(value)) {
    out.push('[');
    value.forEach((item, index) => {
      if (index > 0) out.push(',');
      serialise(item, out, depth + 1, `${path}[${index}]`);
    });
    out.push(']');
    return;
  }

  const record = value as Record<string, unknown>;
  const names = Object.keys(record);
  for (const name of names) assertEncodable(name, `${path} member name`);
  names.sort(compareMemberNames);

  out.push('{');
  names.forEach((name, index) => {
    if (index > 0) out.push(',');
    serialiseString(name, `${path} member name`, out);
    out.push(':');
    serialise(record[name], out, depth + 1, `${path}.${name}`);
  });
  out.push('}');
}

/** The canonical UTF-8 bytes of an already-parsed JSON value. */
export function canonicalise(value: unknown): Uint8Array {
  return new TextEncoder().encode(canonicaliseToString(value));
}

/** The canonical text. Exported because a test that compares strings reads better. */
export function canonicaliseToString(value: unknown): string {
  const out: string[] = [];
  serialise(value, out, 0, '$');
  return out.join('');
}

// ── Strict JSON parsing ────────────────────────────────────────────────────

/**
 * A JSON parser that REFUSES duplicate member names.
 *
 * `JSON.parse` resolves a duplicate last-wins and silently, which is the one behaviour a
 * canonicaliser must not have: it would decide, on the writer's behalf, which of two
 * records was signed. There is no reviver trick that recovers the information — the
 * reviver runs once per surviving key — so the parser is written out. It is a strict
 * RFC 8259 recursive descent over the text, and it is deliberately small enough to read.
 *
 * Numbers are converted with `Number(...)`, which is the same conversion `JSON.parse`
 * performs, so a value parsed here and a value parsed there are the same double.
 */
export function parseJsonStrict(text: string): unknown {
  const parser = new StrictParser(text);
  const value = parser.parseValue(0);
  parser.skipWhitespace();
  if (!parser.atEnd()) throw parser.fail('unexpected trailing content');
  return value;
}

/** Parse strictly, then canonicalise. The pair `canonicalise_json` names in Python. */
export function canonicaliseJson(text: string): Uint8Array {
  return canonicalise(parseJsonStrict(text));
}

const WHITESPACE = new Set([0x20, 0x09, 0x0a, 0x0d]);

class StrictParser {
  private readonly text: string;
  private index = 0;

  constructor(text: string) {
    this.text = text;
  }

  atEnd(): boolean {
    return this.index >= this.text.length;
  }

  fail(message: string): CanonicalisationError {
    return new CanonicalisationError(
      'InvalidJson',
      `${message} at offset ${this.index}`,
    );
  }

  skipWhitespace(): void {
    while (this.index < this.text.length && WHITESPACE.has(this.text.charCodeAt(this.index))) {
      this.index += 1;
    }
  }

  private peek(): string {
    return this.text.charAt(this.index);
  }

  private expect(character: string): void {
    if (this.peek() !== character) throw this.fail(`expected ${JSON.stringify(character)}`);
    this.index += 1;
  }

  parseValue(depth: number): unknown {
    if (depth > MAX_DEPTH) throw depthExceeded(MAX_DEPTH);
    this.skipWhitespace();
    const character = this.peek();
    switch (character) {
      case '{':
        return this.parseObject(depth);
      case '[':
        return this.parseArray(depth);
      case '"':
        return this.parseString();
      case 't':
        return this.parseLiteral('true', true);
      case 'f':
        return this.parseLiteral('false', false);
      case 'n':
        return this.parseLiteral('null', null);
      default:
        return this.parseNumber();
    }
  }

  private parseLiteral<T>(word: string, value: T): T {
    if (this.text.slice(this.index, this.index + word.length) !== word) {
      throw this.fail(`expected ${word}`);
    }
    this.index += word.length;
    return value;
  }

  private parseObject(depth: number): Record<string, unknown> {
    this.expect('{');
    const result: Record<string, unknown> = Object.create(null) as Record<string, unknown>;
    const seen = new Set<string>();
    this.skipWhitespace();
    if (this.peek() === '}') {
      this.index += 1;
      return { ...result };
    }
    for (;;) {
      this.skipWhitespace();
      const name = this.parseString();
      if (seen.has(name)) throw duplicateKey(name);
      seen.add(name);
      this.skipWhitespace();
      this.expect(':');
      result[name] = this.parseValue(depth + 1);
      this.skipWhitespace();
      const next = this.peek();
      if (next === ',') {
        this.index += 1;
        continue;
      }
      if (next === '}') {
        this.index += 1;
        // Spread onto a normal object so downstream code sees an ordinary record.
        // `Object.create(null)` was used during parsing so that a member literally
        // named `__proto__` cannot rewrite the prototype of the value being built.
        return { ...result };
      }
      throw this.fail('expected "," or "}"');
    }
  }

  private parseArray(depth: number): unknown[] {
    this.expect('[');
    const items: unknown[] = [];
    this.skipWhitespace();
    if (this.peek() === ']') {
      this.index += 1;
      return items;
    }
    for (;;) {
      items.push(this.parseValue(depth + 1));
      this.skipWhitespace();
      const next = this.peek();
      if (next === ',') {
        this.index += 1;
        continue;
      }
      if (next === ']') {
        this.index += 1;
        return items;
      }
      throw this.fail('expected "," or "]"');
    }
  }

  private parseString(): string {
    this.expect('"');
    let out = '';
    for (;;) {
      if (this.atEnd()) throw this.fail('unterminated string');
      const character = this.text.charAt(this.index);
      const code = this.text.charCodeAt(this.index);
      this.index += 1;
      if (character === '"') return out;
      if (character === '\\') {
        out += this.parseEscape();
        continue;
      }
      if (code < 0x20) throw this.fail('unescaped control character in string');
      out += character;
    }
  }

  private parseEscape(): string {
    const character = this.text.charAt(this.index);
    this.index += 1;
    switch (character) {
      case '"':
        return '"';
      case '\\':
        return '\\';
      case '/':
        return '/';
      case 'b':
        return '\b';
      case 'f':
        return '\f';
      case 'n':
        return '\n';
      case 'r':
        return '\r';
      case 't':
        return '\t';
      case 'u': {
        const digits = this.text.slice(this.index, this.index + 4);
        if (!/^[0-9a-fA-F]{4}$/.test(digits)) throw this.fail('malformed \\u escape');
        this.index += 4;
        return String.fromCharCode(Number.parseInt(digits, 16));
      }
      default:
        throw this.fail(`unknown escape \\${character}`);
    }
  }

  private parseNumber(): number {
    const start = this.index;
    if (this.peek() === '-') this.index += 1;
    if (this.peek() === '0') {
      this.index += 1;
    } else {
      if (!/[1-9]/.test(this.peek())) throw this.fail('expected a JSON value');
      while (/[0-9]/.test(this.peek())) this.index += 1;
    }
    if (this.peek() === '.') {
      this.index += 1;
      if (!/[0-9]/.test(this.peek())) throw this.fail('expected a digit after "."');
      while (/[0-9]/.test(this.peek())) this.index += 1;
    }
    if (this.peek() === 'e' || this.peek() === 'E') {
      this.index += 1;
      if (this.peek() === '+' || this.peek() === '-') this.index += 1;
      if (!/[0-9]/.test(this.peek())) throw this.fail('expected a digit in the exponent');
      while (/[0-9]/.test(this.peek())) this.index += 1;
    }
    const literal = this.text.slice(start, this.index);
    if (literal === '' || literal === '-') throw this.fail('expected a JSON value');
    return Number(literal);
  }
}
