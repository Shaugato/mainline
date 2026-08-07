// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The generated read model, checked two ways.
 *
 * **At compile time**, by the exported type assertions below. They are not decoration:
 * `Assert<...>` only accepts `true`, so a drift between the hand-written structural
 * types the transport compiles against and the generated wire types is a TYPE ERROR in
 * `pnpm run typecheck`, not a runtime surprise.
 *
 * **At run time**, by reading the generated file as text and refusing `any` and stray
 * index signatures. A generator is only as trustworthy as the thing that checks it,
 * and "no `any`" is a property of the OUTPUT, so it is asserted against the output.
 */

import { describe, expect, it } from 'vitest';

import type { BundleFrame, BundleManifest } from '../../../src/data/bundle';
import type { ReadEnvelopeShape } from '../../../src/data/transport';
import type {
  EvidenceBundleFrame,
  EvidenceBundleManifest,
  MusAtom,
  Permit,
  PermitResponse,
  ReadEnvelope,
  RefusalPayload,
  VirulenceClass,
} from '../../../src/data/types.generated';

import { nodeFs } from './_support';

// ── Compile-time assertions ────────────────────────────────────────────────

export type Assert<T extends true> = T;

/**
 * The hand-written shapes in `src/data/transport.ts` and `src/data/bundle.ts` exist so
 * those modules compile without the generator having run — a transport that cannot be
 * bisected past a code-generation step is a transport nobody can debug. These
 * assertions are what keep the two descriptions of the same bytes honest.
 */
export type _EnvelopeAgrees = Assert<ReadEnvelopeShape extends ReadEnvelope ? true : false>;
export type _ManifestAgrees = Assert<BundleManifest extends EvidenceBundleManifest ? true : false>;
export type _FrameAgrees = Assert<BundleFrame extends EvidenceBundleFrame ? true : false>;

/** The closed vocabularies really are closed. */
export type _VirulenceIsClosed = Assert<
  VirulenceClass extends 'routine' | 'serious' | 'blood_major' | 'blood_fatal' ? true : false
>;
export type _NoStrayVirulence = Assert<'blood_catastrophic' extends VirulenceClass ? false : true>;

/** A response really is an envelope with its `data` narrowed. */
export type _PermitResponseCarriesPermit = Assert<PermitResponse['data'] extends Permit ? true : false>;
export type _PermitResponseIsAnEnvelope = Assert<
  PermitResponse['resource'] extends string ? true : false
>;

/** The refusal MUS is a discriminated union, not a bag with an index signature. */
export type _MusIsDiscriminated = Assert<
  Extract<MusAtom, { kind: 'authority_gap' }> extends { relation: string } ? true : false
>;
export type _RefusalSqlstateIsClosed = Assert<
  RefusalPayload['sqlstate'] extends '23514' | '23503' | '23505' | 'P0001' ? true : false
>;

// ── Run-time assertions over the generated text ────────────────────────────

const GENERATED = 'src/data/types.generated.ts';

describe('types.generated.ts', () => {
  it('contains no `any`', async () => {
    const fs = await nodeFs();
    const text = fs.readFileSync(GENERATED, 'utf8');
    const code = text
      .split('\n')
      .filter((line) => !line.trimStart().startsWith('*') && !line.trimStart().startsWith('//'))
      .join('\n')
      .replace(/\/\*\*[\s\S]*?\*\//g, '');
    expect(code).not.toMatch(/(?<![A-Za-z0-9_$])any(?![A-Za-z0-9_$])/);
  });

  it('declares its index signatures in exactly three named aliases and nowhere else', async () => {
    const fs = await nodeFs();
    const text = fs.readFileSync(GENERATED, 'utf8');
    const matches = [...text.matchAll(/\[key: string\]/g)];
    // JsonValue, JsonObject, StringMap — the entire open surface of the read model.
    expect(matches.length).toBe(3);
    for (const alias of ['export type JsonValue', 'export type JsonObject', 'export type StringMap<T>']) {
      expect(text).toContain(alias);
    }
  });

  it('marks itself generated, so nobody edits it by hand', async () => {
    const fs = await nodeFs();
    const text = fs.readFileSync(GENERATED, 'utf8');
    expect(text).toContain('GENERATED FILE — DO NOT EDIT');
  });

  it('says what it cannot enforce', async () => {
    const fs = await nodeFs();
    const text = fs.readFileSync(GENERATED, 'utf8');
    // A type here is a shape, not a guarantee. If that sentence ever disappears, a
    // future reader will mistake a successful compile for a validated payload.
    expect(text).toMatch(/enforced at\n \* RUNTIME by `src\/data\/schema\.ts`/);
    expect(text).toMatch(/A type here is a shape, not a guarantee/);
  });
});
