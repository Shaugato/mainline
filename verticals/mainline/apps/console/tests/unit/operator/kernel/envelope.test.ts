// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The read envelope and the provenance chip.
 *
 * The chip rule is the one a screen can violate silently, so it is pinned here from both
 * sides: a claimed pointer gets its chip, and an unclaimed one gets `null` — including the
 * tempting near-misses, an ancestor and a descendant of a pointer that WAS claimed.
 */

import { describe, expect, it } from 'vitest';

import common from '../../../../contracts/common.schema.json';
import {
  CHIPS,
  chipFor,
  claimedPointers,
  parseEnvelope,
} from '../../../../src/operator/kernel/envelope';

function envelopeOf(overrides: Record<string, unknown> = {}): unknown {
  return {
    envelope_version: 1,
    resource: 'permit',
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/permit.schema.json',
    observed_at: '2026-08-15T09:00:00Z',
    server_date: '2026-08-15T09:00:00Z',
    staged: false,
    staged_note: null,
    statement_refs: [{ kind: 'table', object: 'mainline.permit', text: 'SELECT …' }],
    provenance: [
      { pointer: '/state', chip: 'db:column' },
      { pointer: '/counters/open_blocking', chip: 'db:column' },
      { pointer: '/counters/open_blocking_derived', chip: 'recomputed' },
    ],
    data: { state: 'dispositioned' },
    ...overrides,
  };
}

describe('the chip vocabulary is the contract’s, checked rather than restated', () => {
  it('matches common.schema.json#/$defs/provenance_chip exactly', () => {
    // The runtime list is what decides whether a chip renders, so the runtime list is what
    // is compared. A TypeScript alias over the generated model would have compiled happily
    // while `CHIPS` drifted — the filter is the gate, not the type.
    expect([...CHIPS].sort()).toEqual([...common.$defs.provenance_chip.enum].sort());
  });
});

describe('parseEnvelope', () => {
  it('reads the wrapper and hands back data separately', () => {
    const parsed = parseEnvelope(envelopeOf());

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.envelope.resource).toBe('permit');
    expect(parsed.envelope.observed_at).toBe('2026-08-15T09:00:00Z');
    expect(parsed.envelope.staged).toBe(false);
    expect(parsed.envelope.statement_refs).toEqual([
      { kind: 'table', object: 'mainline.permit', text: 'SELECT …', sql_path: null },
    ]);
    expect(parsed.data).toEqual({ state: 'dispositioned' });
  });

  it('carries staged and staged_note verbatim when the emitter staged something', () => {
    const parsed = parseEnvelope(
      envelopeOf({ staged: true, staged_note: 'mainline.lesson has no producer migration.' }),
    );

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.envelope.staged).toBe(true);
    expect(parsed.envelope.staged_note).toBe('mainline.lesson has no producer migration.');
  });

  it('refuses a version it does not recognise and says so rather than guessing', () => {
    const parsed = parseEnvelope(envelopeOf({ envelope_version: 2 }));

    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.reason).toContain('envelope_version is 2');
  });

  it('reports "not an envelope" distinctly from "an envelope I refuse"', () => {
    expect(parseEnvelope({ error: { kind: 'no_route' } })).toEqual({ ok: false, reason: null });
    expect(parseEnvelope(null)).toEqual({ ok: false, reason: null });
    expect(parseEnvelope('<!doctype html>')).toEqual({ ok: false, reason: null });
  });

  it('refuses a version-1 wrapper missing the members the contract requires', () => {
    const parsed = parseEnvelope({ envelope_version: 1, resource: 'permit' });

    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.reason).toContain('resource, schema_id and staged');
  });

  it('defaults nothing: a missing observed_at is null, not now()', () => {
    const parsed = parseEnvelope(envelopeOf({ observed_at: undefined }));

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.envelope.observed_at).toBeNull();
  });
});

describe('provenance', () => {
  it('carries the wire name `chip` and the plan name `kind` with the same value', () => {
    const parsed = parseEnvelope(envelopeOf());
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    expect(parsed.envelope.provenance[0]).toEqual({
      pointer: '/state',
      kind: 'db:column',
      chip: 'db:column',
    });
  });

  it('skips an entry naming a chip outside the contract vocabulary', () => {
    const parsed = parseEnvelope(
      envelopeOf({ provenance: [{ pointer: '/state', chip: 'probably' }] }),
    );
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    expect(parsed.envelope.provenance).toEqual([]);
    expect(chipFor(parsed.envelope, '/state')).toBeNull();
  });
});

describe('chipFor', () => {
  const parsed = parseEnvelope(envelopeOf());
  const envelope = parsed.ok ? parsed.envelope : null;

  it('returns the chip the payload claimed for that exact pointer', () => {
    expect(chipFor(envelope, '/state')).toBe('db:column');
    expect(chipFor(envelope, '/counters/open_blocking_derived')).toBe('recomputed');
  });

  it('returns null for a pointer the payload did not claim', () => {
    expect(chipFor(envelope, '/external_ref')).toBeNull();
  });

  it('does not let an ancestor inherit a descendant’s chip', () => {
    expect(chipFor(envelope, '/counters')).toBeNull();
  });

  it('does not let a descendant inherit an ancestor’s chip', () => {
    expect(chipFor(envelope, '/state/value')).toBeNull();
  });

  it('returns null when there is no envelope at all', () => {
    expect(chipFor(null, '/state')).toBeNull();
  });

  it('lists the claimed pointers in wire order', () => {
    expect(claimedPointers(envelope)).toEqual([
      '/state',
      '/counters/open_blocking',
      '/counters/open_blocking_derived',
    ]);
    expect(claimedPointers(null)).toEqual([]);
  });
});
