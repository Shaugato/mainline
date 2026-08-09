// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE WITNESSES — written RED, before `src/features/diff/engine/witness.ts` existed.
 *
 * One rule governs this whole module, and every test below is an instance of it:
 *
 *     THE CONSOLE MAY COMPUTE WHAT CHANGED. ONLY THE DATABASE MAY SAY WHY.
 *
 * So there is no code path from an observed change to a reason for it. What there IS:
 *
 *   • binding — a witness row names a field; the console checks whether that field
 *     actually changed between these two rows, and reports `bound`, `no_observed_change`
 *     or `unresolvable_field`. It never edits the witness and never re-words the note;
 *   • the tri-state — `witnesses: null` is WITNESS UNAVAILABLE (the emitter said
 *     nothing); `witnesses: []` is the emitter CLAIMING there are none. Collapsing those
 *     two into "no witnesses" would turn a silence into an assertion, and the contract
 *     (`contracts/clause.schema.json`, `$defs.delta_verdict`) says so in as many words;
 *   • the gap — a change with no witness is LISTED, as a change with no witness. Not
 *     explained, not ranked, not called suspicious.
 */

import { describe, expect, it } from 'vitest';

import { buildClauseDiff } from '../../../src/features/diff/engine/build';
import { resolveWitnessField } from '../../../src/features/diff/engine/witness';
import type {
  ClauseDiffInput,
  ClauseVersion,
  DeltaWitness,
} from '../../../src/features/diff/model';

const CLAUSE = '018f3a30-2200-7d10-9f31-0c9a4e77bb02';
const PARENT_COMMIT = 'aa'.repeat(32);
const VERSION_COMMIT = 'bb'.repeat(32);

function base(): ClauseVersion {
  return {
    clause_uuid: CLAUSE,
    gen: 4,
    commit_id: PARENT_COMMIT,
    site_id: '018f3a2e-0000-7000-8000-000000000001',
    activity_root: 'A03-ISOLATING-STORED-ENERGY',
    parent_version: null,
    canon_text: 'Verified as zero at every accumulator, countersigned by the responsible engineer.',
    canon_version: 2,
    canon_sha256: '11'.repeat(32),
    anchor_set: ['HPU-0412', 'accumulator', 'responsible_engineer'],
    cat_key: 'cat:a',
    cat_json: { location: 'every_accumulator_in_circuit', countersignature: 'responsible_engineer' },
    cat_confidence: 'ok',
    control_delta: 'strengthen',
    delta_basis: 'lattice',
    sev_max: 5,
    blood_size: 3,
  };
}

function child(): ClauseVersion {
  return {
    ...base(),
    gen: 5,
    commit_id: VERSION_COMMIT,
    parent_version: PARENT_COMMIT,
    canon_text: 'Verified as zero at the hydraulic power unit.',
    canon_sha256: '22'.repeat(32),
    anchor_set: ['HPU-0412'],
    cat_key: 'cat:b',
    cat_json: { location: 'hydraulic_power_unit' },
    control_delta: 'weaken',
    blood_size: 4,
  };
}

const SCOPE: DeltaWitness = {
  rule_id: 'R-SCOPE-NARROWED',
  field: 'cat.location',
  from_repr: 'every_accumulator_in_circuit',
  to_repr: 'hydraulic_power_unit',
  note: 'The verification point moved from every accumulator to a single named unit.',
};

const ANCHORS: DeltaWitness = {
  rule_id: 'R-ANCHOR-DROPPED',
  field: 'anchor_set',
  from_repr: 'accumulator, responsible_engineer',
  to_repr: '',
  note: 'Two anchors present in the ancestor are absent from the descendant.',
};

function input(witnesses: readonly DeltaWitness[] | null, minimal: boolean | null = true): ClauseDiffInput {
  return {
    clauseUuid: CLAUSE,
    version: child(),
    parent: base(),
    delta: { delta: 'weaken', basis: 'lattice', witnesses, minimal },
  };
}

describe('resolveWitnessField — what a witness row is pointing at', () => {
  it('resolves the anchor set', () => {
    expect(resolveWitnessField('anchor_set')).toEqual({
      kind: 'anchor_set',
      pointer: null,
      column: null,
    });
    expect(resolveWitnessField('clause_version.anchor_set').kind).toBe('anchor_set');
  });

  it('resolves the canonical text', () => {
    expect(resolveWitnessField('canon_text').kind).toBe('text');
  });

  it('resolves a dotted CAT path to an RFC 6901 pointer', () => {
    expect(resolveWitnessField('cat.location')).toEqual({
      kind: 'cat',
      pointer: '/location',
      column: null,
    });
    expect(resolveWitnessField('cat_json.quantity.value').pointer).toBe('/quantity/value');
    expect(resolveWitnessField('/cat_json/quantity/unit').pointer).toBe('/quantity/unit');
  });

  it('escapes a pointer segment containing a slash or a tilde', () => {
    expect(resolveWitnessField('cat./odd~name').pointer).toBe('/~1odd~0name');
  });

  it('resolves the CAT root', () => {
    expect(resolveWitnessField('cat')).toEqual({ kind: 'cat', pointer: '', column: null });
  });

  it('resolves a scalar column', () => {
    expect(resolveWitnessField('cat_confidence')).toEqual({
      kind: 'column',
      pointer: null,
      column: 'cat_confidence',
    });
  });

  it('refuses to guess at a field it does not recognise', () => {
    expect(resolveWitnessField('deontic_strength').kind).toBe('unresolved');
    expect(resolveWitnessField('').kind).toBe('unresolved');
  });
});

describe('the tri-state — silence is not a claim', () => {
  it('reports `unavailable` for a null witness list', () => {
    expect(buildClauseDiff(input(null)).witnesses.availability).toBe('unavailable');
  });

  it('reports `asserted_none` for an empty witness list — a DIFFERENT claim', () => {
    expect(buildClauseDiff(input([])).witnesses.availability).toBe('asserted_none');
  });

  it('reports `present` when rows arrived', () => {
    expect(buildClauseDiff(input([SCOPE])).witnesses.availability).toBe('present');
  });

  it('carries the minimality claim through unchanged, including its null', () => {
    expect(buildClauseDiff(input([SCOPE], null)).witnesses.minimal).toBeNull();
    expect(buildClauseDiff(input([SCOPE], false)).witnesses.minimal).toBe(false);
  });
});

describe('binding — the console corroborates, it does not explain', () => {
  it('binds a witness whose field actually changed', () => {
    const bound = buildClauseDiff(input([SCOPE, ANCHORS])).witnesses.witnesses;
    expect(bound.map((entry) => entry.state)).toEqual(['bound', 'bound']);
    expect(bound[0]?.target).toEqual({ kind: 'cat', pointer: '/location', column: null });
    expect(bound[1]?.target.kind).toBe('anchor_set');
  });

  it('renders the row verbatim — no field of the witness is rewritten', () => {
    const bound = buildClauseDiff(input([SCOPE])).witnesses.witnesses[0];
    expect(bound?.witness).toEqual(SCOPE);
  });

  it('reports a witness whose field did not change, without discarding it', () => {
    const stale: DeltaWitness = { ...SCOPE, field: 'cat.actor' };
    const model = buildClauseDiff(input([stale]));
    const bound = model.witnesses.witnesses[0];
    expect(bound?.state).toBe('no_observed_change');
    expect(bound?.witness).toEqual(stale);
    expect(model.findings.some((f) => f.code === 'witness_names_unchanged_field')).toBe(true);
  });

  it('reports an unresolvable field rather than guessing at one', () => {
    const odd: DeltaWitness = { ...SCOPE, field: 'deontic_strength' };
    const model = buildClauseDiff(input([odd]));
    expect(model.witnesses.witnesses[0]?.state).toBe('unresolvable_field');
    expect(model.witnesses.witnesses[0]?.target.kind).toBe('unresolved');
    expect(model.findings.some((f) => f.code === 'witness_field_unresolvable')).toBe(true);
  });

  it('cannot corroborate anything when there is no comparable ancestor', () => {
    const model = buildClauseDiff({
      clauseUuid: CLAUSE,
      version: child(),
      parent: null,
      delta: { delta: 'weaken', basis: 'lattice', witnesses: [SCOPE], minimal: true },
    });
    expect(model.comparability.kind).toBe('parent_unresolved');
    expect(model.witnesses.witnesses[0]?.state).toBe('uncorroborable');
    // And it must NOT be reported as a witness naming an unchanged field: the console
    // did not observe the field being unchanged, it observed nothing at all.
    expect(model.findings.some((f) => f.code === 'witness_names_unchanged_field')).toBe(false);
  });

  it('binds a witness naming the CAT root to any CAT change', () => {
    const root: DeltaWitness = { ...SCOPE, field: 'cat_json' };
    expect(buildClauseDiff(input([root])).witnesses.witnesses[0]?.state).toBe('bound');
  });
});

describe('the gap — a change with no witness is listed, never explained', () => {
  const model = buildClauseDiff(input([SCOPE]));

  it('lists each dropped anchor when no witness names the anchor set', () => {
    const dropped = model.unwitnessed.filter((entry) => entry.kind === 'anchor_dropped');
    expect(dropped.map((entry) => entry.subject)).toEqual([
      'accumulator',
      'responsible_engineer',
    ]);
  });

  it('stops listing anchors once a witness names the anchor set', () => {
    const withAnchors = buildClauseDiff(input([SCOPE, ANCHORS]));
    expect(withAnchors.unwitnessed.some((entry) => entry.kind === 'anchor_dropped')).toBe(false);
  });

  it('lists a CAT pointer that changed with no witness naming it', () => {
    const cat = model.unwitnessed.filter((entry) => entry.kind === 'cat');
    expect(cat.map((entry) => entry.subject)).toEqual(['/countersignature']);
  });

  it('lists the canonical text when no witness names it', () => {
    const text = model.unwitnessed.filter((entry) => entry.kind === 'text');
    expect(text).toHaveLength(1);
    expect(text[0]?.subject).toBe('canon_text');
  });

  it('never puts a reason in the detail — only the observation', () => {
    for (const entry of model.unwitnessed) {
      expect(entry.detail.toLowerCase()).not.toContain('because');
    }
  });

  it('reports no gap at all when every observation is witnessed', () => {
    const complete = buildClauseDiff(
      input([
        SCOPE,
        ANCHORS,
        { ...SCOPE, rule_id: 'R-TEXT', field: 'canon_text' },
        { ...SCOPE, rule_id: 'R-COUNTERSIGN', field: 'cat.countersignature' },
        { ...SCOPE, rule_id: 'R-KEY', field: 'cat_key' },
      ]),
    );
    expect(complete.unwitnessed).toEqual([]);
  });
});
