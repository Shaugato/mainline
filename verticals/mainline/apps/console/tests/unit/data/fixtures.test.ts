// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Every fixture validates against its contract, and the fixture set covers the six
 * situations the demo has to be able to show.
 *
 * The coverage test is not decoration. A fixture directory that quietly lost the
 * `23503` case would leave `disposition.spec.ts` asserting against a screen that can no
 * longer be reached, and the suite would stay green. So the six are named here, matched
 * by SQLSTATE and constraint TAKEN FROM THE PAYLOAD, and a missing one fails.
 */

import { describe, expect, it } from 'vitest';

import { decodeBase64ToText } from '../../../src/data/bundle';
import { createContractRegistry } from '../../../src/data/contracts';
import { formatErrors } from '../../../src/data/schema';
import { resolveRequest, resourceOrThrow } from '../../../src/data/resources';

import { bundleFiles, sourcePayloads, stagePlan } from './_support';

const registry = createContractRegistry();

interface EnvelopeShape {
  readonly resource: string;
  readonly schema_id: string;
  readonly staged: boolean;
  readonly staged_note: string | null;
  readonly data: unknown;
}

function payloadFor(file: string): { text: string; envelope: EnvelopeShape } {
  const text = sourcePayloads().get(file);
  if (text === undefined) throw new Error(`fixture payload "${file}" was not found.`);
  return { text, envelope: JSON.parse(text) as EnvelopeShape };
}

const plan = stagePlan();

describe('fixture payloads satisfy their contracts', () => {
  it.each(plan.steps.map((step) => [step.payload, step.resource] as const))(
    '%s validates against the contract for %s',
    (payloadFile, resourceKey) => {
      const { envelope } = payloadFor(payloadFile.split('/').slice(-1)[0] ?? payloadFile);
      const resource = resourceOrThrow(resourceKey);

      expect(envelope.resource).toBe(resourceKey);
      expect(envelope.schema_id).toBe(resource.schemaId);

      const result = registry.validate(resource.schemaId, envelope);
      expect(result.valid, `${payloadFile}\n${formatErrors(result.errors)}`).toBe(true);
    },
  );

  it('every fixture payload declares itself staged, with a note', () => {
    for (const step of plan.steps) {
      const { envelope } = payloadFor(step.payload.split('/').slice(-1)[0] ?? step.payload);
      expect(envelope.staged, step.payload).toBe(true);
      expect(typeof envelope.staged_note, step.payload).toBe('string');
      expect((envelope.staged_note ?? '').length, step.payload).toBeGreaterThan(40);
    }
  });

  it('the staging plan itself declares the bundle staged', () => {
    expect(plan.manifest.staged).toBe(true);
  });
});

describe('the fixture set covers the six situations the demo must be able to show', () => {
  interface InvokeShape {
    readonly outcome: string;
    readonly refusal: { readonly sqlstate: string; readonly constraint: string } | null;
  }

  function refusal(file: string): { sqlstate: string; constraint: string } {
    const { envelope } = payloadFor(file);
    const data = envelope.data as InvokeShape;
    expect(data.outcome, file).toBe('refused');
    expect(data.refusal, file).not.toBeNull();
    return {
      sqlstate: data.refusal?.sqlstate ?? '',
      constraint: data.refusal?.constraint ?? '',
    };
  }

  it('1 — a refused merge: 23514 on gate_closed_when_issued', () => {
    expect(refusal('merge-refused-23514.json')).toEqual({
      sqlstate: '23514',
      constraint: 'gate_closed_when_issued',
    });
  });

  it('2 — a 23503 on the clearance lattice', () => {
    const found = refusal('disposition-refused-23503.json');
    expect(found.sqlstate).toBe('23503');
    expect(found.constraint).toBe('fk_clearance');

    // The MUS must name the missing lattice row, because "not permitted" and
    // "not representable" are different sentences and only one of them is true.
    const { envelope } = payloadFor('disposition-refused-23503.json');
    const mus = (
      envelope.data as { refusal: { mus: { kind: string; key?: Record<string, unknown> }[] } }
    ).refusal.mus;
    expect(mus[0]?.kind).toBe('authority_gap');
    expect(mus[0]?.key).toEqual({ virulence: 'blood_fatal', kind: 'mechanism_absent' });
  });

  it('3 — a P0001 raised by attaching a precursor to an issued permit', () => {
    const found = refusal('materialise-refused-p0001.json');
    expect(found.sqlstate).toBe('P0001');
    expect(found.constraint).toMatch(/^trappoint\./);

    const { envelope } = payloadFor('materialise-refused-p0001.json');
    const naa = (envelope.data as { refusal: { naa: { kind: string } } }).refusal.naa;
    // The declared path is suspend-and-fork. Anything else would be rewriting history.
    expect(naa.kind).toBe('fork_subject');
  });

  it('4 — an ancestry spanning 22 years and ending at a severity-5 event', () => {
    const { envelope } = payloadFor('ancestry.json');
    const data = envelope.data as {
      closure: { max_severity: number; depth: number };
      truncation: { ancestry_complete: boolean };
      events: { occurred_at: string; severity_gate: number }[];
      commit_chain: { committed_at: string }[];
    };

    expect(data.closure.max_severity).toBe(5);
    expect(data.events.some((event) => event.severity_gate === 5)).toBe(true);
    expect(data.truncation.ancestry_complete).toBe(true);

    const years = (a: string, b: string): number =>
      (Date.parse(b) - Date.parse(a)) / (365.2425 * 24 * 60 * 60 * 1000);
    const oldest = data.events
      .map((event) => event.occurred_at)
      .sort((a, b) => Date.parse(a) - Date.parse(b))[0];
    const newestCommit = data.commit_chain
      .map((link) => link.committed_at)
      .sort((a, b) => Date.parse(b) - Date.parse(a))[0];
    expect(oldest).toBeDefined();
    expect(newestCommit).toBeDefined();
    expect(years(oldest ?? '', newestCommit ?? '')).toBeGreaterThanOrEqual(22);
  });

  it('5 — a silence ledger entry whose arithmetic adds up to the score it reports', () => {
    const { envelope } = payloadFor('silence.json');
    const data = envelope.data as {
      entries: {
        reason: string;
        score: number | null;
        threshold: number | null;
        arithmetic: Record<string, unknown>;
      }[];
      receipt: { theta: number; s: number; n: number; bound: { statement: string } };
    };

    const belowTau = data.entries.find((entry) => entry.reason === 'below_tau');
    expect(belowTau).toBeDefined();
    expect(belowTau?.score).toBeLessThan(belowTau?.threshold ?? 0);

    const channels = belowTau?.arithmetic.channels as Record<string, { contribution: number }>;
    const summed = Object.values(channels).reduce((total, channel) => total + channel.contribution, 0);
    const fused = belowTau?.arithmetic.fused_raw as number;
    // The published components must add up to the published fused score. A silence
    // ledger whose arithmetic does not reconcile is a worse exhibit than none.
    expect(summed).toBeCloseTo(fused, 4);

    // s <= n, and the honest bound is carried rather than implied.
    expect(data.receipt.s).toBeLessThanOrEqual(data.receipt.n);
    expect(data.receipt.bound.statement).toMatch(/retrieval that ran, not of the corpus/);
  });

  it('6 — a checkpoint with an inclusion proof against a tree size it declares', () => {
    const { envelope } = payloadFor('ledger.json');
    const data = envelope.data as {
      checkpoints: { tree_size: number; root_hex: string; note: string }[];
      leaves: { seq: number; prev_link_hash_hex: string }[];
      inclusion_proofs: { seq: number; tree_size: number; path_hex: string[] }[];
    };

    const proof = data.inclusion_proofs[0];
    expect(proof).toBeDefined();
    expect(proof?.path_hex.length).toBeGreaterThan(0);
    expect(data.checkpoints.some((checkpoint) => checkpoint.tree_size === proof?.tree_size)).toBe(true);

    // seq is dense from zero, and genesis is 64 zeroes rather than a special case.
    const seqs = data.leaves.map((leaf) => leaf.seq).sort((a, b) => a - b);
    expect(seqs).toEqual(seqs.map((_, index) => index));
    expect(data.leaves.find((leaf) => leaf.seq === 0)?.prev_link_hash_hex).toBe('0'.repeat(64));
  });
});

/**
 * `docs/evidence-bundle.md` §8 makes a claim about the producer: *what a reviewer reads
 * in `fixtures/sources/**` is exactly what the console receives, to the byte.*
 *
 * That is the whole reason the fixtures are hand-authored as readable payload files and
 * then staged, rather than written directly into frames as base64 nobody can review. It
 * only holds if `stage` copies payload BYTES into the frame instead of parsing and
 * re-emitting them — a re-serialised capture would be testing our JSON writer, and one
 * whitespace change would move every digest computed over it.
 *
 * So it is asserted rather than described. Every step in the staging plan is walked, the
 * frame is located by the same key derivation the transport uses, and the decoded body is
 * compared to the source file character for character.
 */
describe('the sealed bundle carries the source payloads byte for byte', () => {
  const files = bundleFiles();
  const decoder = new TextDecoder('utf-8', { fatal: true });

  for (const step of plan.steps) {
    it(`${step.resource} ← ${step.payload}`, () => {
      const resolved = resolveRequest({
        resource: step.resource,
        ...(step.path === undefined ? {} : { path: step.path }),
        ...(step.query === undefined ? {} : { query: step.query }),
      });

      const frameBytes = files.get(resolved.framePath);
      expect(frameBytes, `${resolved.framePath} is missing from the sealed bundle`).toBeDefined();

      const frame = JSON.parse(decoder.decode(frameBytes)) as { response: { body_b64: string } };
      const served = decodeBase64ToText(resolved.framePath, frame.response.body_b64);

      const source = sourcePayloads().get(step.payload.split('/').slice(-1)[0] ?? step.payload);
      expect(source, `${step.payload} is missing from fixtures/sources`).toBeDefined();

      // Character for character, not JSON-equal. JSON equality would pass through a
      // re-serialisation, which is exactly the defect this test exists to catch.
      expect(served).toBe(source);
    });
  }
});

describe('the fixtures do not overclaim', () => {
  it('the checkpoint note names a log origin that cannot be mistaken for a real one', () => {
    const { envelope } = payloadFor('ledger.json');
    const data = envelope.data as { checkpoints: { note: string; admissible: boolean }[] };
    const checkpoint = data.checkpoints[0];
    expect(checkpoint?.note.split('\n')[0]).toMatch(/\.invalid\//);
    // Quorum and diversity are not satisfied by one operator cosignature, and the
    // projected column says so.
    expect(checkpoint?.admissible).toBe(false);
  });

  it('no fixture claims end-to-end Australian data residency', () => {
    for (const [, text] of sourcePayloads()) {
      expect(text.toLowerCase()).not.toMatch(/data residency in australia|australian data residency/);
    }
  });

  it('no fixture uses the forbidden custody vocabulary', () => {
    // spec/wire/evidence-bundle.md §14: these strings must not appear, because a ledger
    // built to be evidence is not a business record.
    for (const [name, text] of sourcePayloads()) {
      expect(text.toLowerCase(), name).not.toMatch(/defence exhibit|for litigation|court-ready/);
    }
  });
});
