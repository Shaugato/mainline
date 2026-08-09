// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The diff, against the REAL contract and the REAL fixture payload.
 *
 * The other suites in this directory build their inputs from literals, which is right for
 * unit tests and is also how a feature quietly drifts away from the wire: a model that
 * only ever sees objects the same author wrote will keep passing after the schema moves.
 * This file closes that gap.
 *
 * 1. The fixture is validated against `contracts/clause.schema.json` by the console's own
 *    validator — the same code path the transport runs before any surface sees a payload.
 *    If the fixture stops satisfying the contract, this fails BEFORE the diff is built,
 *    so the failure names the real cause.
 * 2. The model is then built from that validated payload, and the reassembly property is
 *    checked against the fixture's own `canon_text` values.
 * 3. The envelope's `provenance` list is checked to agree with the chips this panel
 *    renders. The panel puts a `db:column` chip beside `control_delta`; the payload says
 *    `/version/control_delta` is `db:column`. Those two facts are maintained in different
 *    files by different workers, and this is the assertion that keeps them the same fact.
 */

import { describe, expect, it } from 'vitest';

import { createContractRegistry } from '../../../src/data/contracts';
import { resourceOrThrow } from '../../../src/data/resources';
import { formatErrors } from '../../../src/data/schema';
import { buildClauseDiff } from '../../../src/features/diff/engine/build';
import type { ClauseResponse } from '../../../src/data/types.generated';

const PAYLOAD_PATH = '/fixtures/sources/blk-07/payloads/clause-version.json';

const RAW = import.meta.glob<string>('/fixtures/sources/blk-07/payloads/clause-version.json', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function envelope(): ClauseResponse {
  const text = RAW[PAYLOAD_PATH];
  if (text === undefined) {
    throw new Error(
      `${PAYLOAD_PATH} was not globbed. The clause-version fixture is owned by the ` +
        'data-contracts-replay worker; if it moved, this test is checking nothing and must ' +
        'fail rather than pass over an empty collection.',
    );
  }
  return JSON.parse(text) as ClauseResponse;
}

const registry = createContractRegistry();

describe('the clause-version fixture', () => {
  it('validates against contracts/clause.schema.json', () => {
    const payload = envelope();
    const resource = resourceOrThrow('clause_version');
    expect(payload.resource).toBe('clause_version');
    expect(payload.schema_id).toBe(resource.schemaId);

    const result = registry.validate(resource.schemaId, payload);
    expect(result.valid, formatErrors(result.errors)).toBe(true);
  });

  it('declares db:column provenance for every value the panel badges as one', () => {
    const pointers = new Map(envelope().provenance.map((entry) => [entry.pointer, entry.chip]));
    // The panel renders each of these beside a `db:column` chip. If the emitter ever
    // marks one `derived` or `staged`, the chip on screen becomes a false statement about
    // where the number came from, and this is where that gets caught.
    for (const pointer of ['/version/control_delta', '/version/delta_basis', '/version/sev_max']) {
      expect(pointers.get(pointer), pointer).toBe('db:column');
    }
    expect(pointers.get('/delta/witnesses')).toBe('db:column');
  });
});

describe('the model over the fixture', () => {
  const payload = envelope();
  const model = buildClauseDiff({
    clauseUuid: payload.data.clause_uuid,
    version: payload.data.version,
    parent: payload.data.parent ?? null,
    delta: payload.data.delta,
  });

  it('finds the two rows comparable', () => {
    expect(model.comparability).toEqual({
      kind: 'comparable',
      parentCommit: payload.data.parent?.commit_id,
    });
  });

  it('reassembles both canon_text values exactly from the segments', () => {
    const segments = model.text?.segments ?? [];
    expect(segments.length).toBeGreaterThan(0);
    const parentSide = segments
      .filter((segment) => segment.kind !== 'added')
      .map((segment) => segment.text)
      .join('');
    const versionSide = segments
      .filter((segment) => segment.kind !== 'removed')
      .map((segment) => segment.text)
      .join('');
    expect(parentSide).toBe(payload.data.parent?.canon_text);
    expect(versionSide).toBe(payload.data.version.canon_text);
  });

  it('reports the anchors the fixture drops', () => {
    expect(model.anchors?.dropped).toEqual(['accumulator', 'responsible_engineer']);
  });

  it('corroborates every witness the fixture carries', () => {
    expect(model.witnesses.availability).toBe('present');
    expect(model.witnesses.witnesses.map((entry) => entry.state)).toEqual([
      'bound',
      'bound',
      'bound',
    ]);
  });

  it('raises no discrepancy — the fixture is internally consistent', () => {
    expect(model.findings.filter((finding) => finding.level === 'discrepancy')).toEqual([]);
  });

  it('still reports the changes the witnesses do not name', () => {
    // The three witnesses in this payload are about the Control Assertion Tuple and the
    // anchor set. Nothing in them names `canon_text` or `cat_key`, and the panel says so
    // rather than letting the reader assume the witness set covers the prose.
    const subjects = model.unwitnessed.map((entry) => entry.subject);
    expect(subjects).toContain('canon_text');
    expect(subjects).toContain('cat_key');
  });
});
