// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE VIEW MODEL — every assertion is over the real fixture payloads, and every expected
 * value is READ from them.
 *
 * The rule this file holds to: no expectation may be a string literal that also appears
 * in the source under test. `expect(rendered).toBe('gate_closed_when_issued')` passes
 * against a component that hardcodes `gate_closed_when_issued`; the pair asserts nothing.
 * So the fixture supplies both sides, and the mutation tests prove the coupling.
 */

import { describe, expect, it } from 'vitest';

import {
  anchorDelta,
  buildWeld,
  catDelta,
  chooseDiffSubject,
  clauseOrigin,
  evidenceAnchor,
  musObligationIds,
  naaCardinality,
  precursorAnchor,
  readRefusal,
  witnessState,
  type AncestryData,
  type BlockingChecksData,
  type ClauseData,
} from '../../../src/features/gate/model';
import { lookupProvenance, pointer } from '../../../src/features/gate/provenance';
import type { InvokeResult, Permit } from '../../../src/data/types.generated';
import { sourcePayload } from './_support';

interface Envelope<T> {
  readonly provenance: readonly { readonly pointer: string; readonly chip: string }[];
  readonly data: T;
}

const permitEnvelope = sourcePayload<Envelope<Permit>>('permit.json');
const checksEnvelope = sourcePayload<Envelope<BlockingChecksData>>('blocking-checks.json');
const clauseEnvelope = sourcePayload<Envelope<ClauseData>>('clause-version.json');
const ancestryEnvelope = sourcePayload<Envelope<AncestryData>>('ancestry.json');
const mergeEnvelope = sourcePayload<Envelope<InvokeResult>>('merge-refused-23514.json');

const permit = permitEnvelope.data;
const checks = checksEnvelope.data.checks;
const clause = clauseEnvelope.data;
const ancestry = ancestryEnvelope.data;

/**
 * A copy of `source` with one key absent. Written as a filter rather than a `delete` so
 * the "field is missing" fixtures are built the same way whether the key is a literal or
 * a loop variable — and so no test mutates a payload another test also reads.
 */
function without(source: object, key: string): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(source as Record<string, unknown>).filter(([name]) => name !== key),
  );
}

function refusalOrThrow(): NonNullable<InvokeResult['refusal']> {
  const read = readRefusal(mergeEnvelope.data.refusal);
  if (!read.ok) throw new Error(`fixture refusal is unreadable: ${read.reason}`);
  return read.refusal;
}

describe('readRefusal — a refusal the console cannot read verbatim is not rendered', () => {
  it('accepts the fixture payload and carries it through unchanged', () => {
    const read = readRefusal(mergeEnvelope.data.refusal);
    expect(read.ok).toBe(true);
    if (!read.ok) return;
    // Identity, not equality: the payload is passed through, never rebuilt.
    expect(read.refusal).toBe(mergeEnvelope.data.refusal);
  });

  it.each(['constraint', 'sqlstate', 'message', 'gate_epoch', 'mus'])(
    'refuses a payload missing `%s`, and names the field',
    (field) => {
      const read = readRefusal(without(mergeEnvelope.data.refusal as object, field));
      expect(read.ok).toBe(false);
      if (read.ok) return;
      expect(read.reason).toContain(field);
    },
  );

  it('treats an ABSENT naa key differently from an explicit null', () => {
    const withNull = { ...(mergeEnvelope.data.refusal as unknown as Record<string, unknown>), naa: null };
    expect(readRefusal(withNull).ok).toBe(true);

    const read = readRefusal(without(mergeEnvelope.data.refusal as object, 'naa'));
    expect(read.ok).toBe(false);
    if (read.ok) return;
    expect(read.reason).toContain('naa');
  });

  it('refuses a non-object', () => {
    expect(readRefusal(null).ok).toBe(false);
    expect(readRefusal('gate_closed_when_issued').ok).toBe(false);
    expect(readRefusal([]).ok).toBe(false);
  });
});

describe('the reason set', () => {
  it('names obligation ids that exist as blocking checks in the same bundle', () => {
    const ids = musObligationIds(refusalOrThrow().mus);
    expect(ids.length).toBeGreaterThan(0);
    const known = new Set(checks.map((check) => check.check_id));
    for (const id of ids) expect(known.has(id)).toBe(true);
  });

  it('reports the emitter’s cardinality and never counts the array itself', () => {
    const naa = refusalOrThrow().naa;
    expect(naa).not.toBeNull();
    if (naa === null) return;
    expect(naaCardinality(naa)).toBe(naa.cardinality ?? null);

    expect(naaCardinality(without(naa, 'cardinality') as unknown as NonNullable<typeof naa>)).toBeNull();
  });
});

describe('evidentiary typing — M11, gist may accuse, only verbatim may acquit', () => {
  it('splits the fixture’s precursors by whether a third party could re-fetch them', () => {
    const strengths = checks.map((check) => precursorAnchor(check.precursor ?? null));
    // The fixture deliberately carries one of each; if it stopped doing so this
    // assertion would be vacuous, so it asserts the mix rather than the values.
    expect(new Set(strengths)).toEqual(new Set(['verbatim', 'gist']));

    for (const check of checks) {
      const precursor = check.precursor ?? null;
      const anchored =
        precursor !== null &&
        typeof precursor.source_object_key === 'string' &&
        typeof precursor.source_sha256 === 'string';
      expect(precursorAnchor(precursor)).toBe(anchored ? 'verbatim' : 'gist');
    }
  });

  it('treats a missing precursor as gist, never as verbatim', () => {
    expect(precursorAnchor(null)).toBe('gist');
    expect(precursorAnchor(undefined)).toBe('gist');
  });

  it('classifies refusal evidence items by whether they carry a digest', () => {
    const items = refusalOrThrow().evidence ?? [];
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) {
      expect(evidenceAnchor(item)).toBe(item.digest === undefined ? 'gist' : 'verbatim');
    }
  });
});

describe('the weld — the projected counters under the CHECK that reads each', () => {
  const blamed = refusalOrThrow().constraint;

  it('renders one row per constraint the payload declares, in declaration order', () => {
    const weld = buildWeld({ permit, checks, blamedConstraint: blamed });
    expect(weld.rows.map((row) => row.constraint)).toEqual(
      permit.constraints.map((constraint) => constraint.constraint),
    );
    expect(weld.empty).toBe(false);
  });

  it('marks the constraint the refusal names, by string comparison and nothing else', () => {
    const weld = buildWeld({ permit, checks, blamedConstraint: blamed });
    const row = weld.rows.find((entry) => entry.constraint === blamed);
    expect(row?.blamedByRefusal).toBe(true);

    // With no refusal on screen the payload's own flag still governs; the console never
    // evaluates a predicate to decide.
    const noRefusal = buildWeld({ permit, checks, blamedConstraint: null });
    for (const entry of noRefusal.rows) {
      const declared = permit.constraints.find((c) => c.constraint === entry.constraint);
      expect(entry.blamedByRefusal).toBe(declared?.blamed_by_refusal ?? false);
    }
  });

  it('reads every counter value from the permit row and never derives one', () => {
    const weld = buildWeld({ permit, checks, blamedConstraint: blamed });
    for (const row of weld.rows) {
      const declared = permit.constraints.find((c) => c.constraint === row.constraint);
      expect(row.counters.map((counter) => [counter.column, counter.value])).toEqual(
        (declared?.counters ?? []).map((entry) => [entry.column, entry.value]),
      );
    }
  });

  it('counts the open blocking checks as the witnesses behind open_blocking', () => {
    const weld = buildWeld({ permit, checks, blamedConstraint: blamed });
    const counter = weld.rows
      .flatMap((row) => row.counters)
      .find((entry) => entry.column === 'open_blocking');
    expect(counter?.witnessSource).toBe('blocking_check');
    expect(counter?.witnessCount).toBe(checks.filter((check) => check.open).length);
    expect(counter?.state).toBe(permit.counters.open_blocking > 0 ? 'blocking' : 'clear');
  });

  it('has no witnesses for open_blocking when the checks read has not landed', () => {
    const weld = buildWeld({ permit, checks: null, blamedConstraint: blamed });
    const counter = weld.rows
      .flatMap((row) => row.counters)
      .find((entry) => entry.column === 'open_blocking');
    expect(counter?.witnessSource).toBe('not_carried');
    expect(counter?.witnessCount).toBeNull();
  });

  it('distinguishes a witnessed zero from a zero nobody computed', () => {
    const weld = buildWeld({ permit, checks, blamedConstraint: blamed });
    const counters = weld.rows.flatMap((row) => row.counters);

    const unmodelled = counters.find((entry) => entry.column === 'unmodelled_asset_count');
    expect(permit.boundary_certificate).not.toBeNull();
    expect(unmodelled?.state).toBe('clear');
    expect(unmodelled?.unknownBlocks).toBe(false);

    // A counter with no witness source on this screen is NEVER `clear`.
    const residue = counters.find((entry) => entry.column === 'open_residue');
    expect(residue?.value).toBe(0);
    expect(residue?.state).toBe('unwitnessed-zero');
  });

  it('S11 — an uncounted asset graph is UNKNOWN, not SAFE, and says so', () => {
    const withoutCertificate: Permit = { ...permit, boundary_certificate: null };
    const weld = buildWeld({ permit: withoutCertificate, checks, blamedConstraint: blamed });
    const unmodelled = weld.rows
      .flatMap((row) => row.counters)
      .find((entry) => entry.column === 'unmodelled_asset_count');

    expect(unmodelled?.value).toBe(0);
    expect(unmodelled?.state).toBe('unwitnessed-zero');
    expect(unmodelled?.unknownBlocks).toBe(true);
    expect(unmodelled?.witnessCount).toBeNull();
  });

  it('names every projected column no constraint in the payload reads', () => {
    const weld = buildWeld({ permit, checks, blamedConstraint: blamed });
    expect(weld.unreadColumns).toEqual([]);

    const trimmed: Permit = {
      ...permit,
      constraints: permit.constraints.filter(
        (constraint) => !constraint.counters.some((entry) => entry.column === 'open_warrants'),
      ),
    };
    expect(buildWeld({ permit: trimmed, checks, blamedConstraint: null }).unreadColumns).toContain(
      'open_warrants',
    );
  });

  it('reports an empty constraint list as empty rather than as a clean gate', () => {
    const bare: Permit = { ...permit, constraints: [] };
    const weld = buildWeld({ permit: bare, checks, blamedConstraint: null });
    expect(weld.empty).toBe(true);
    expect(weld.unreadColumns.length).toBe(Object.keys(permit.counters).length);
  });
});

describe('clause diff derivations', () => {
  it('reports anchors dropped between the ancestor and the descendant', () => {
    const parent = clause.parent ?? null;
    expect(parent).not.toBeNull();
    if (parent === null) return;

    const delta = anchorDelta(parent.anchor_set, clause.version.anchor_set);
    const expectedRemoved = parent.anchor_set.filter(
      (anchor) => !clause.version.anchor_set.includes(anchor),
    );
    expect([...delta.removed]).toEqual(expectedRemoved);
    expect(delta.removed.length).toBeGreaterThan(0);
    expect([...delta.kept, ...delta.added].sort()).toEqual([...clause.version.anchor_set].sort());
  });

  it('treats an absent ancestor as "everything is new", never as "nothing changed"', () => {
    const delta = anchorDelta(null, clause.version.anchor_set);
    expect(delta.removed).toEqual([]);
    expect(delta.added).toEqual([...clause.version.anchor_set]);
  });

  it('compares CAT tuples by flat path with no key special-cased', () => {
    const parent = clause.parent ?? null;
    if (parent === null) throw new Error('fixture has no ancestor version');
    const changes = catDelta(parent.cat_json, clause.version.cat_json);
    expect(changes.length).toBeGreaterThan(0);
    // Paths are sorted and unique, and every reported path really differs.
    expect([...changes].map((change) => change.path)).toEqual(
      [...new Set(changes.map((change) => change.path))].sort(),
    );
    for (const change of changes) expect(change.from).not.toBe(change.to);
  });

  it('reports no change for a tuple compared with itself', () => {
    expect(catDelta(clause.version.cat_json, clause.version.cat_json)).toEqual([]);
  });

  it('separates "no witnesses reached us" from "the emitter says there are none"', () => {
    expect(witnessState(clause.delta.witnesses)).toBe('rows');
    expect(witnessState(null)).toBe('unavailable');
    expect(witnessState([])).toBe('asserted-none');
  });
});

describe('choosing the clause the diff panel is about', () => {
  it('prefers the check the reason set names', () => {
    const refusal = refusalOrThrow();
    const subject = chooseDiffSubject(checks, refusal);
    expect(subject.selection).toBe('named-by-reason-set');
    expect(musObligationIds(refusal.mus)).toContain(subject.check?.check_id);
  });

  it('falls back to the first open check, and labels the fallback', () => {
    const subject = chooseDiffSubject(checks, null);
    expect(subject.selection).toBe('first-open-check');
    expect(subject.check?.open).toBe(true);
  });

  it('picks nothing rather than guessing when there is nothing to pick', () => {
    expect(chooseDiffSubject(null, null).selection).toBe('none');
    expect(chooseDiffSubject([], null).check).toBeNull();
    const closed = checks.map((check) => ({ ...check, open: false }));
    expect(chooseDiffSubject(closed, null).selection).toBe('none');
  });
});

describe('what wrote the clause', () => {
  it('finds the introducing commit and the blame edge from the ancestry payload', () => {
    const check = checks[0];
    if (check === undefined) throw new Error('fixture has no blocking checks');
    const origin = clauseOrigin(ancestry, check.precursor_event_id ?? null);

    expect(origin.introducing?.control_delta).toBe('introduce');
    expect(origin.introducing?.commit_id).toBe(
      ancestry.commit_chain.find((link) => link.control_delta === 'introduce')?.commit_id,
    );
    expect(origin.blame?.event_id).toBe(check.precursor_event_id);
    expect(origin.blame?.attribution).toBe(
      ancestry.blame_edges.find((edge) => edge.event_id === check.precursor_event_id)?.attribution,
    );
  });

  it('reports nothing when no ancestry payload reached the screen', () => {
    const origin = clauseOrigin(null, 'whatever');
    expect(origin.introducing).toBeNull();
    expect(origin.blame).toBeNull();
  });
});

describe('provenance lookup — an unclaimed provenance is better than a default', () => {
  it('finds an exactly declared pointer', () => {
    const declared = permitEnvelope.provenance[0];
    if (declared === undefined) throw new Error('fixture declares no provenance');
    const found = lookupProvenance(
      permitEnvelope.provenance as never,
      declared.pointer,
    );
    expect(found.kind).toBe('exact');
    expect(found.kind === 'exact' ? found.chip : null).toBe(declared.chip);
  });

  it('inherits from the nearest declared ancestor, and says it inherited', () => {
    const found = lookupProvenance(
      permitEnvelope.provenance as never,
      pointer('constraints', 0, 'constraint'),
    );
    expect(found.kind).toBe('inherited');
    expect(found.kind === 'inherited' ? found.pointer : null).toBe('/constraints');
  });

  it('does not confuse a prefix with an ancestor', () => {
    const found = lookupProvenance(
      [{ pointer: '/counter', chip: 'db:column' }],
      '/counters/open_blocking',
    );
    expect(found.kind).toBe('undeclared');
  });

  it('returns undeclared rather than a comfortable default', () => {
    expect(lookupProvenance(permitEnvelope.provenance as never, '/nowhere').kind).toBe(
      'undeclared',
    );
    expect(lookupProvenance(undefined, '/anything').kind).toBe('undeclared');
  });
});
