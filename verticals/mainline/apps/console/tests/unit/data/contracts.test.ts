// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The contracts themselves: they compile, they cross-reference, and the copy of the
 * refusal payload contract is still the specification's.
 *
 * The last of those is the CI check `docs/leads/ui.md` §4 asks for. The console
 * workspace may not reach outside itself at build time, so `spec/wire/refusal.schema.json`
 * is COPIED into `contracts/`. A copy rots. This test compares the two structurally —
 * every JSON pointer, both directions — so a field added, removed or retyped in the
 * specification fails the console's own suite, by name, on the next run.
 *
 * D18: never invent a refusal field.
 */

import { describe, expect, it } from 'vitest';

import {
  CONTRACT_ID_PREFIX,
  CONTRACT_SOURCES,
  REFUSAL_SCHEMA_ID,
  createContractRegistry,
} from '../../../src/data/contracts';
import { RESOURCES } from '../../../src/data/resources';

import { REPO_ROOT, nodeFs } from './_support';

const SPEC_REFUSAL = `${REPO_ROOT}spec/wire/refusal.schema.json`;

type Json = unknown;

/** Every JSON pointer in a document, with its value, for a pointer-precise diff. */
function flatten(value: Json, pointer = '', out = new Map<string, string>()): Map<string, string> {
  if (Array.isArray(value)) {
    out.set(pointer, `array(${value.length})`);
    value.forEach((item, index) => flatten(item, `${pointer}/${index}`, out));
  } else if (typeof value === 'object' && value !== null) {
    const keys = Object.keys(value as Record<string, Json>).sort();
    out.set(pointer, `object(${keys.join(',')})`);
    for (const key of keys) {
      const escaped = key.replace(/~/g, '~0').replace(/\//g, '~1');
      flatten((value as Record<string, Json>)[key], `${pointer}/${escaped}`, out);
    }
  } else {
    out.set(pointer, JSON.stringify(value) ?? 'undefined');
  }
  return out;
}

describe('contracts', () => {
  it('all compile: no unimplemented keyword, no dangling $ref', () => {
    // createContractRegistry() calls compileAll(), which throws on either.
    const registry = createContractRegistry();
    expect(registry.ids().length).toBe(CONTRACT_SOURCES.length);
  });

  it('every declared resource names a contract the registry holds', () => {
    const registry = createContractRegistry();
    const known = new Set(registry.ids());
    for (const resource of RESOURCES.values()) {
      expect(known, `resource "${resource.key}"`).toContain(resource.schemaId);
    }
  });

  it('every console-owned contract uses the console $id prefix, and only refusal does not', () => {
    const registry = createContractRegistry();
    for (const id of registry.ids()) {
      if (id === REFUSAL_SCHEMA_ID) continue;
      expect(id.startsWith(CONTRACT_ID_PREFIX), id).toBe(true);
    }
    expect(registry.get(REFUSAL_SCHEMA_ID)).toBeDefined();
  });

  it('contracts/refusal.schema.json is structurally identical to spec/wire/refusal.schema.json', async () => {
    const fs = await nodeFs();

    // If the specification file is not reachable the test must FAIL, not skip: a drift
    // check that silently stops checking is worse than no drift check.
    expect(fs.existsSync(SPEC_REFUSAL), `${SPEC_REFUSAL} must be readable from the console workspace`).toBe(
      true,
    );

    const specSource = fs.readFileSync(SPEC_REFUSAL, 'utf8');
    const consoleSource = CONTRACT_SOURCES.find(([name]) => name === 'refusal.schema.json')?.[1];
    expect(consoleSource).toBeDefined();

    const spec = flatten(JSON.parse(specSource));
    const copy = flatten(JSON.parse(consoleSource ?? '{}'));

    const missing = [...spec.keys()].filter((pointer) => !copy.has(pointer));
    const extra = [...copy.keys()].filter((pointer) => !spec.has(pointer));
    const different = [...spec.entries()]
      .filter(([pointer, value]) => copy.has(pointer) && copy.get(pointer) !== value)
      .map(([pointer, value]) => `${pointer}: spec ${value} / console ${copy.get(pointer) ?? '?'}`);

    expect(
      { missing, extra, different },
      'contracts/refusal.schema.json has drifted from the specification. Re-copy it; never edit it here.',
    ).toEqual({ missing: [], extra: [], different: [] });
  });

  it('the refusal contract still declares the five payload members the console renders', () => {
    const registry = createContractRegistry();
    const refusal = registry.get(REFUSAL_SCHEMA_ID);
    const properties = (refusal as unknown as { properties: Record<string, unknown> }).properties;
    // D18 names exactly these. If the specification drops one, the console's gate
    // surface has been rendering something that is no longer in the contract.
    for (const member of ['constraint', 'sqlstate', 'mus', 'naa', 'subject_id', 'gate_epoch']) {
      expect(Object.keys(properties)).toContain(member);
    }
  });

  it('refuses a refusal payload whose SQLSTATE is outside the modelled set', () => {
    const registry = createContractRegistry();
    const payload = {
      spec_version: '1.0.0',
      refusal_id: '018f3a37-1100-7a10-8b55-2b7e9f10a3d5',
      observed_at: '2026-08-06T21:52:44.000Z',
      class: 'gate',
      sqlstate: '40001',
      constraint: 'gate_closed_when_issued',
      message: 'MAINLINE: restart',
      subject_kind: 'permit',
      subject_id: '018f3a2f-1104-7c88-b3aa-77c1de40e2b1',
      gate_epoch: 7,
      diagnosis: 'declarative',
      probe_calls: 0,
      mus: [{ kind: 'event', event_id: '018f3a31-5500-7a20-8c44-2b7e9f10a3d5' }],
      naa: null,
      naa_reason: 'not_computable',
    };
    const result = registry.validate(REFUSAL_SCHEMA_ID, payload);
    expect(result.valid).toBe(false);
    // 40001 is excluded on purpose: an undecided transaction has no reason set.
    expect(result.errors.some((error) => error.instancePath === '/sqlstate')).toBe(true);
  });
});
