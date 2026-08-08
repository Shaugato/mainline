// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Tests for the validator itself.
 *
 * A contract-conformance suite is only worth what its validator is worth. If the
 * validator ignored a keyword it had not implemented, every fixture test in this
 * directory would pass while asserting strictly less than it claims — the exact
 * failure PL-2 exists to prevent. So the first three tests here are about the
 * validator's REFUSALS, not its acceptances.
 */

import { describe, expect, it } from 'vitest';

import { SchemaCompileError, SchemaRefError, SchemaRegistry } from '../../../src/data/schema';

const ID = 'https://example.test/s.schema.json';

function registryFor(schema: Record<string, unknown>): SchemaRegistry {
  const registry = new SchemaRegistry();
  registry.add({ $id: ID, ...schema });
  registry.compileAll();
  return registry;
}

describe('the validator refuses what it cannot check', () => {
  it('throws on a keyword it does not implement, rather than ignoring it', () => {
    const registry = new SchemaRegistry();
    registry.add({
      $id: ID,
      type: 'object',
      properties: { a: { type: 'string' } },
      unevaluatedProperties: false,
    });

    expect(() => {
      registry.compileAll();
    }).toThrow(SchemaCompileError);
    expect(() => {
      registry.compileAll();
    }).toThrow(/unevaluatedProperties/);
  });

  it('throws on a format name it does not implement', () => {
    const registry = new SchemaRegistry();
    registry.add({ $id: ID, type: 'string', format: 'idn-hostname' });
    expect(() => {
      registry.compileAll();
    }).toThrow(/format "idn-hostname" is not implemented/);
  });

  it('throws on a $ref that names a document nobody registered', () => {
    const registry = new SchemaRegistry();
    registry.add({
      $id: ID,
      properties: { a: { $ref: 'https://example.test/missing.schema.json' } },
    });
    expect(() => {
      registry.compileAll();
    }).toThrow(SchemaRefError);
  });

  it('throws on a $ref pointing at a member that does not exist', () => {
    const registry = new SchemaRegistry();
    registry.add({
      $id: ID,
      properties: { a: { $ref: '#/$defs/nope' } },
      $defs: { yes: { type: 'string' } },
    });
    expect(() => {
      registry.compileAll();
    }).toThrow(/does not exist/);
  });
});

describe('assertions', () => {
  it('asserts format date-time, including impossible calendar dates', () => {
    const registry = registryFor({ type: 'string', format: 'date-time' });
    expect(registry.validate(ID, '2026-08-07T02:15:00.000Z').valid).toBe(true);
    expect(registry.validate(ID, '2026-08-07T02:15:00+10:00').valid).toBe(true);
    expect(registry.validate(ID, '2026-02-30T00:00:00Z').valid).toBe(false);
    expect(registry.validate(ID, '2026-13-01T00:00:00Z').valid).toBe(false);
    expect(registry.validate(ID, '2026-08-07 02:15:00').valid).toBe(false);
  });

  it('refuses an undeclared property when additionalProperties is false', () => {
    const registry = registryFor({
      type: 'object',
      additionalProperties: false,
      properties: { a: { type: 'string' } },
    });
    const result = registry.validate(ID, { a: 'x', b: 'y' });
    expect(result.valid).toBe(false);
    expect(result.errors[0]?.keyword).toBe('additionalProperties');
    expect(result.errors[0]?.instancePath).toBe('/b');
  });

  it('enforces oneOf as exactly-one', () => {
    const registry = registryFor({
      oneOf: [{ type: 'integer' }, { type: 'number' }],
    });
    // 3 satisfies both branches, so oneOf must fail.
    const both = registry.validate(ID, 3);
    expect(both.valid).toBe(false);
    expect(both.errors[0]?.message).toMatch(/2 alternatives matched/);
    expect(registry.validate(ID, 3.5).valid).toBe(true);
  });

  it('applies if/then/else, which is how the envelope binds staged to staged_note', () => {
    const registry = registryFor({
      type: 'object',
      properties: { staged: { type: 'boolean' }, staged_note: { type: ['string', 'null'] } },
      required: ['staged', 'staged_note'],
      if: { properties: { staged: { const: true } }, required: ['staged'] },
      then: { properties: { staged_note: { type: 'string' } } },
      else: { properties: { staged_note: { type: 'null' } } },
    });
    expect(registry.validate(ID, { staged: true, staged_note: 'because' }).valid).toBe(true);
    expect(registry.validate(ID, { staged: true, staged_note: null }).valid).toBe(false);
    expect(registry.validate(ID, { staged: false, staged_note: 'because' }).valid).toBe(false);
    expect(registry.validate(ID, { staged: false, staged_note: null }).valid).toBe(true);
  });

  it('measures string length in code points, not UTF-16 units', () => {
    const registry = registryFor({ type: 'string', maxLength: 2 });
    // Two code points that occupy four UTF-16 units.
    expect(registry.validate(ID, '\u{1F6A7}\u{1F6A7}').valid).toBe(true);
    expect(registry.validate(ID, '\u{1F6A7}\u{1F6A7}\u{1F6A7}').valid).toBe(false);
  });

  it('distinguishes integer from number', () => {
    const registry = registryFor({ type: 'integer' });
    expect(registry.validate(ID, 5).valid).toBe(true);
    expect(registry.validate(ID, 5.5).valid).toBe(false);
  });

  it('resolves a cross-document $ref through the registry', () => {
    const registry = new SchemaRegistry();
    registry.add({
      $id: 'https://example.test/common.schema.json',
      $defs: { code: { type: 'string', pattern: '^[A-Z]{3}$' } },
    });
    registry.add({
      $id: 'https://example.test/leaf.schema.json',
      type: 'object',
      required: ['code'],
      properties: { code: { $ref: 'common.schema.json#/$defs/code' } },
    });
    registry.compileAll();

    const target = 'https://example.test/leaf.schema.json';
    expect(registry.validate(target, { code: 'BLK' }).valid).toBe(true);
    const bad = registry.validate(target, { code: 'blk' });
    expect(bad.valid).toBe(false);
    expect(bad.errors[0]?.keyword).toBe('pattern');
  });

  it('reports the instance pointer of the failing value, not just that something failed', () => {
    const registry = registryFor({
      type: 'object',
      properties: {
        checks: {
          type: 'array',
          items: {
            type: 'object',
            required: ['severity'],
            properties: { severity: { type: 'integer', minimum: 0, maximum: 5 } },
          },
        },
      },
    });
    const result = registry.validate(ID, { checks: [{ severity: 3 }, { severity: 9 }] });
    expect(result.valid).toBe(false);
    expect(result.errors[0]?.instancePath).toBe('/checks/1/severity');
    expect(result.errors[0]?.keyword).toBe('maximum');
  });
});
