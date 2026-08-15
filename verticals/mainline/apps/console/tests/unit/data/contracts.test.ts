// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The contracts themselves: they compile, they cross-reference, and the two documents
 * this directory holds as COPIES are still identical to the files that own them.
 *
 * The console workspace may not reach outside itself at build time, so two schemas owned
 * elsewhere are copied into `contracts/`:
 *
 *   * `refusal.schema.json` ← `spec/wire/refusal.schema.json` (the CI check
 *     `docs/leads/ui.md` §4 asks for);
 *   * `gate-run.schema.json` ← `verticals/mainline/apps/demo-api/contracts/gate-run.schema.json`,
 *     the contract the demo API serves `POST /v1/demo/gate-run` against. The console
 *     validates that response before rendering it, so if the two drift the demo's front
 *     door refuses its own kernel's answer in front of a judge.
 *
 * A copy rots. Each is checked TWO ways, and both matter:
 *
 *   1. **Byte for byte**, because "verbatim" is the instruction and a reformat that
 *      preserves structure still makes two readers looking at the two files disagree
 *      about what they are reading.
 *   2. **Pointer by pointer, in BOTH directions**, because that is what names the field
 *      that moved. A byte diff on a 23 KB schema says "these differ"; a pointer diff
 *      says `/$defs/persistence_check/required/3`.
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
const DEMO_API_GATE_RUN = `${REPO_ROOT}verticals/mainline/apps/demo-api/contracts/gate-run.schema.json`;
const DEMO_API_SUBJECTS = `${REPO_ROOT}verticals/mainline/apps/demo-api/contracts/subjects.schema.json`;

type Json = unknown;

/** Every JSON pointer in a document, with its value, for a pointer-precise diff. */
function flatten(value: Json, pointer = '', out = new Map<string, string>()): Map<string, string> {
  if (Array.isArray(value)) {
    out.set(pointer, `array(${value.length})`);
    value.forEach((item, index) => flatten(item, `${pointer}/${index}`, out));
  } else if (typeof value === 'object' && value !== null) {
    const keys = Object.keys(value).sort();
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

/**
 * Asserts that `contracts/<name>` is a verbatim copy of `originalPath`.
 *
 * Written once and used by both copies rather than twice with the pointers renamed: a
 * drift check that exists in two hand-maintained versions has two chances to be the
 * weaker one, and the weaker one is the check nobody notices has stopped checking.
 */
async function expectVerbatimCopy(name: string, originalPath: string, reCopy: string): Promise<void> {
  const fs = await nodeFs();

  // If the original is not reachable the test must FAIL, not skip: a drift check that
  // silently stops checking is worse than no drift check.
  expect(fs.existsSync(originalPath), `${originalPath} must be readable from the console workspace`).toBe(
    true,
  );

  const originalSource = fs.readFileSync(originalPath, 'utf8');
  const registered = CONTRACT_SOURCES.find(([entry]) => entry === name)?.[1];
  expect(registered, `contracts.ts must register "${name}" in CONTRACT_SOURCES`).toBeDefined();

  // (1) The two FILES, byte for byte. Both are read the same way, so a line-ending
  // difference between them is a real difference and not a checkout artefact. Compared
  // on disk rather than against the `?raw` import, because the bundler owns that string
  // and this assertion is about what is committed.
  const copyOnDisk = fs.readFileSync(`contracts/${name}`, 'utf8');
  const bytes =
    copyOnDisk === originalSource
      ? 'identical'
      : `DIFFER (${copyOnDisk.length} chars here, ${originalSource.length} there)`;

  // (2) The two DOCUMENTS, pointer by pointer, both directions — which is what NAMES
  // the field that moved. This one reads the registered `?raw` source, so it also
  // proves the string the runtime validator compiles is the document on disk.
  const original = flatten(JSON.parse(originalSource));
  const copy = flatten(JSON.parse(registered ?? '{}'));

  const missing = [...original.keys()].filter((pointer) => !copy.has(pointer));
  const extra = [...copy.keys()].filter((pointer) => !original.has(pointer));
  const different = [...original.entries()]
    .filter(([pointer, value]) => copy.has(pointer) && copy.get(pointer) !== value)
    .map(([pointer, value]) => `${pointer}: original ${value} / console ${copy.get(pointer) ?? '?'}`);

  // Asserted TOGETHER, in one object, deliberately. Asserting the byte comparison first
  // and returning on failure would make the pointer diff unreachable — it would only
  // ever run when the bytes already matched, which is exactly when it cannot fail. A
  // check that can only pass is not a check. One object means a real drift reports both
  // that the files differ AND which pointers moved.
  expect({ bytes, missing, extra, different }, `contracts/${name} has drifted. ${reCopy}`).toEqual({
    bytes: 'identical',
    missing: [],
    extra: [],
    different: [],
  });
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

  it('contracts/refusal.schema.json is identical to spec/wire/refusal.schema.json', async () => {
    await expectVerbatimCopy(
      'refusal.schema.json',
      SPEC_REFUSAL,
      'Re-copy it from the specification; never edit it here.',
    );
  });

  it('contracts/gate-run.schema.json is identical to the demo API’s, both directions', async () => {
    // The demo API OWNS this contract: it serves POST /v1/demo/gate-run against it and
    // repeats its $id inside the payload. This test is what stops the copy drifting.
    //
    // The direction of repair is not symmetric and is not a matter of taste. If these
    // two ever disagree, the fix is to argue about the ORIGINAL on the record and then
    // re-copy — never to edit one side until they match, which would make the console
    // agree with a document nobody decided on.
    await expectVerbatimCopy(
      'gate-run.schema.json',
      DEMO_API_GATE_RUN,
      'Re-copy it from verticals/mainline/apps/demo-api/contracts/gate-run.schema.json; ' +
        'never edit either side to make them agree.',
    );
  });

  it('contracts/subjects.schema.json is identical to the demo API’s, both directions', async () => {
    // The demo API OWNS this one too: it serves GET /v1/demo/subjects against it from
    // `subjects.py`. The console reads that payload to learn which permit, site, clause
    // and commit a deployment actually seeded, so if the two documents drift the console
    // refuses the answer to the question "which subject?" and five screens open on an
    // absence — which is honest, and is still the demo not working.
    //
    // Same asymmetry as gate-run: argue about the ORIGINAL, then re-copy.
    await expectVerbatimCopy(
      'subjects.schema.json',
      DEMO_API_SUBJECTS,
      'Re-copy it from verticals/mainline/apps/demo-api/contracts/subjects.schema.json; ' +
        'never edit either side to make them agree.',
    );
  });

  it('compiles the gate-run contract rather than admitting it vacuously', () => {
    // createContractRegistry() calls compileAll(), which refuses any keyword this
    // validator does not implement and resolves every $ref. This contract uses
    // allOf / if / then / else / oneOf / const / enum / format and a cross-document
    // $ref to the specification's refusal payload, so "it is registered" and "it is
    // enforceable" are two different claims. This asserts the second.
    const registry = createContractRegistry();
    const id = 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json';
    expect(registry.ids()).toContain(id);

    // The $ref that reaches outside this document resolves to a registered document.
    expect(registry.get(REFUSAL_SCHEMA_ID)).toBeDefined();

    // And it discriminates: a payload missing the member the verdict keys on is refused
    // rather than passed. A contract that accepts everything is a contract asserting
    // nothing, which is the exact failure compileAll() exists to prevent.
    const result = registry.validate(id, { resource: 'demo_gate_run' });
    expect(result.valid).toBe(false);
    expect(result.errors.some((error) => error.keyword === 'required')).toBe(true);
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
