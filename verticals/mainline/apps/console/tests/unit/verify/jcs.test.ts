// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * RFC 8785, against the Python reference's output.
 *
 * Not one expected string in this file is written by hand. Every `canonical` value comes
 * out of `tests/vectors/jcs.json`, which was captured from
 * `packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py` — the module that is vendored
 * byte-for-byte into `trappoint-verify` and whose SHA-256 is written into every checkpoint.
 * A test that asserted a literal would be asserting what this implementation happens to
 * do, which is the one thing a cross-verifier contract must not do.
 */

import { describe, expect, it } from 'vitest';

import {
  CanonicalisationError,
  canonicalise,
  canonicaliseJson,
  canonicaliseToString,
  compareMemberNames,
  es6Number,
  parseJsonStrict,
} from '../../../src/verify/jcs';
import { sha256Sync } from '../../../src/verify/sha256';
import { toHex } from '../../../src/verify/bytes';

import { jcsVectors } from './_vectors';

const vectors = jcsVectors();

describe('the vector set is the contract, and it is present', () => {
  it('carries every category the browser implementation has to agree on', () => {
    expect(vectors.cases.length).toBeGreaterThanOrEqual(8);
    expect(vectors.refusals.length).toBeGreaterThanOrEqual(5);
    expect(vectors.number_premise).toContain('IEEE-754 double');
  });
});

describe('canonicalise agrees with the Python reference, byte for byte', () => {
  it.each(vectors.cases.map((testCase) => [testCase.id, testCase] as const))(
    '%s',
    (_id, testCase) => {
      const parsed = parseJsonStrict(testCase.input_text);
      const produced = canonicaliseToString(parsed);
      expect(produced, testCase.note).toBe(testCase.canonical);

      const bytes = canonicalise(parsed);
      expect(bytes.byteLength).toBe(testCase.canonical_bytes);
      expect(toHex(sha256Sync(bytes))).toBe(testCase.sha256);
    },
  );

  it('produces the same bytes through canonicaliseJson', () => {
    for (const testCase of vectors.cases) {
      expect(new TextDecoder().decode(canonicaliseJson(testCase.input_text))).toBe(
        testCase.canonical,
      );
    }
  });
});

describe('the refusals the browser can make, it makes', () => {
  const refusalById = new Map(vectors.refusals.map((refusal) => [refusal.id, refusal]));

  it('refuses NaN', () => {
    const refusal = refusalById.get('nan');
    expect(refusal?.enforced_by).toBe('both');
    expect(() => canonicalise({ a: Number.NaN })).toThrow(CanonicalisationError);
    expect(() => canonicalise({ a: Number.NaN })).toThrow(/no JSON serialisation/);
  });

  it('refuses the infinities', () => {
    expect(refusalById.get('infinity')?.enforced_by).toBe('both');
    expect(() => canonicalise([Number.POSITIVE_INFINITY])).toThrow(/no JSON serialisation/);
    expect(() => canonicalise([Number.NEGATIVE_INFINITY])).toThrow(/no JSON serialisation/);
  });

  it('refuses a lone surrogate, in a value and in a member name', () => {
    expect(refusalById.get('lone-surrogate')?.enforced_by).toBe('both');
    expect(() => canonicalise({ a: '\ud83d' })).toThrow(/unpaired surrogate/);
    expect(() => canonicalise({ '\udc00': 1 })).toThrow(/unpaired surrogate/);
  });

  it('refuses duplicate member names', () => {
    const refusal = refusalById.get('duplicate-member');
    expect(refusal?.enforced_by).toBe('both');
    expect(refusal?.input_text).toBeDefined();
    expect(() => parseJsonStrict(refusal?.input_text ?? '')).toThrow(/appears more than once/);
    // JSON.parse, by contrast, resolves it silently — which is exactly why the parser
    // in src/verify/jcs.ts is written out rather than delegated.
    expect(JSON.parse(refusal?.input_text ?? '{}')).toEqual({ a: 2 });
  });
});

describe('the refusal the browser CANNOT make is recorded as such', () => {
  it('does not claim to refuse an integer above 2**53', () => {
    const refusal = vectors.refusals.find((entry) => entry.id === 'unsafe-integer');
    expect(refusal?.enforced_by).toBe('python-only');
    expect(refusal?.note).toContain('THE BROWSER CANONICALISER DOES NOT AND CANNOT');
    // And it genuinely does not. The literal is fed through the PARSER rather than
    // written in this file, because writing it here would be a source-level rounding —
    // the point is that the rounding happens on the way in, exactly as it would for a
    // payload arriving over the wire.
    expect(canonicaliseToString(parseJsonStrict('{"a":9007199254740993}'))).toBe(
      '{"a":9007199254740992}',
    );
  });
});

describe('the two halves that are free in JavaScript, asserted anyway', () => {
  it('serialises numbers exactly as ECMAScript Number::toString', () => {
    expect(es6Number(-0)).toBe('0');
    expect(es6Number(1e-7)).toBe('1e-7');
    expect(es6Number(0.000001)).toBe('0.000001');
    expect(es6Number(1e20)).toBe('100000000000000000000');
    expect(es6Number(1e21)).toBe('1e+21');
    expect(() => es6Number(Number.NaN)).toThrow();
  });

  it('orders member names by UTF-16 code unit, not by code point', () => {
    // U+1F602 is code point 128514, far above U+FB33 (64307); its UTF-16 encoding starts
    // with the surrogate D83D, which is below FB33.
    expect(compareMemberNames('\ud83d\ude02', '\ufb33')).toBe(-1);
    expect('\ud83d\ude02'.codePointAt(0)).toBeGreaterThan('\ufb33'.codePointAt(0) ?? 0);
  });
});

describe('the strict parser', () => {
  it('preserves -0, which JSON.stringify does not', () => {
    expect(Object.is((parseJsonStrict('{"a":-0}') as { a: number }).a, -0)).toBe(true);
    expect(JSON.stringify({ a: -0 })).toBe('{"a":0}');
  });

  it('refuses trailing content, unescaped controls and unknown escapes', () => {
    expect(() => parseJsonStrict('{} {}')).toThrow(/trailing content/);
    expect(() => parseJsonStrict('"a\u0001b"')).toThrow(/control character/);
    expect(() => parseJsonStrict('"\\x"')).toThrow(/unknown escape/);
  });

  it('does not let a member named __proto__ reach the prototype', () => {
    const parsed = parseJsonStrict('{"__proto__":{"polluted":true}}') as Record<string, unknown>;
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
    expect(Object.keys(parsed)).toContain('__proto__');
  });
});
