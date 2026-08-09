// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE MODEL — written RED, before `src/features/diff/engine/build.ts` existed.
 *
 * The assertions that matter here are the REFUSALS:
 *
 *   • a payload whose `parent` is not the commit `version.parent_version` names is NOT
 *     diffed. A diff between the wrong two rows is a picture of an edit that never
 *     happened, and it is indistinguishable from a real one on screen;
 *   • a `weaken` on a `lattice` basis with no witness rows raises a DISCREPANCY naming
 *     `fn_delta_witness_guard`, because the algorithms domain's D8 says such a version
 *     cannot be inserted — so a payload carrying one is telling us something about
 *     itself, and the console must say which of the two it cannot decide between;
 *   • every finding carries an AUTHORITY. A finding whose authority slot is empty is an
 *     opinion, and this console does not render those.
 */

import { describe, expect, it } from 'vitest';

import { buildClauseDiff, comparabilityOf } from '../../../src/features/diff/engine/build';
import type { ClauseDiffInput, ClauseVersion } from '../../../src/features/diff/model';

const CLAUSE = '018f3a30-2200-7d10-9f31-0c9a4e77bb02';
const PARENT_COMMIT = '3d7f406e8091c3543d7f406e8091c3543d7f406e8091c3543d7f406e8091c354';
const VERSION_COMMIT = '5f916282a2a3e5765f916282a2a3e5765f916282a2a3e5765f916282a2a3e576';
const GRANDPARENT = '2c6e3f5d7f90b2432c6e3f5d7f90b2432c6e3f5d7f90b2432c6e3f5d7f90b243';

const PARENT_TEXT =
  'Residual stored energy shall be verified as zero at every accumulator in the isolated circuit, ' +
  'and countersigned by the responsible engineer.';
const VERSION_TEXT =
  'Residual stored energy shall be verified as zero at the hydraulic power unit.';

function parentVersion(overrides: Partial<ClauseVersion> = {}): ClauseVersion {
  return {
    clause_uuid: CLAUSE,
    gen: 4,
    commit_id: PARENT_COMMIT,
    site_id: '018f3a2e-0000-7000-8000-000000000001',
    doc_id: '018f3a30-4400-7a30-8b53-2e1c60997a24',
    activity_root: 'A03-ISOLATING-STORED-ENERGY',
    parent_version: GRANDPARENT,
    ordinal: 732,
    printed_label: '7.3.2(b)',
    raw_text: PARENT_TEXT,
    canon_text: PARENT_TEXT,
    canon_version: 2,
    canon_sha256: '7b1384a4c4c507987b1384a4c4c507987b1384a4c4c507987b1384a4c4c50798',
    anchor_set: ['HPU-0412', 'ISOLATION_AUTHORITY', 'accumulator', 'responsible_engineer'],
    cat_key: 'cat:isolate-stored-energy:verify:zero:accumulator',
    cat_json: {
      control_class: 'isolation.stored_energy.verification',
      actor: 'isolating_officer',
      location: 'every_accumulator_in_circuit',
      countersignature: 'responsible_engineer',
      quantity: { value: 0, unit: 'kPa' },
    },
    cat_confidence: 'ok',
    control_delta: 'strengthen',
    delta_basis: 'lattice',
    delta_model: null,
    delta_prompt_version: null,
    blood_root: '8c2495b5d5d618a98c2495b5d5d618a98c2495b5d5d618a98c2495b5d5d618a9',
    blood_size: 3,
    sev_max: 5,
    ...overrides,
  };
}

function childVersion(overrides: Partial<ClauseVersion> = {}): ClauseVersion {
  return {
    ...parentVersion(),
    gen: 5,
    commit_id: VERSION_COMMIT,
    parent_version: PARENT_COMMIT,
    raw_text: VERSION_TEXT,
    canon_text: VERSION_TEXT,
    canon_sha256: '6a027393b3b4f6876a027393b3b4f6876a027393b3b4f6876a027393b3b4f687',
    anchor_set: ['HPU-0412', 'ISOLATION_AUTHORITY'],
    cat_key: 'cat:isolate-stored-energy:verify:zero:hpu',
    cat_json: {
      control_class: 'isolation.stored_energy.verification',
      actor: 'isolating_officer',
      location: 'hydraulic_power_unit',
      quantity: { value: 0, unit: 'kPa' },
    },
    control_delta: 'weaken',
    blood_size: 4,
    ...overrides,
  };
}

function input(overrides: Partial<ClauseDiffInput> = {}): ClauseDiffInput {
  return {
    clauseUuid: CLAUSE,
    version: childVersion(),
    parent: parentVersion(),
    delta: {
      delta: 'weaken',
      basis: 'lattice',
      witnesses: [
        {
          rule_id: 'R-SCOPE-NARROWED',
          field: 'cat.location',
          from_repr: 'every_accumulator_in_circuit',
          to_repr: 'hydraulic_power_unit',
          note: 'The verification point moved to a single named unit.',
        },
      ],
      minimal: true,
    },
    ...overrides,
  };
}

describe('comparabilityOf — whether these two rows may be diffed at all', () => {
  it('is comparable when the supplied parent is the commit the version names', () => {
    expect(comparabilityOf(childVersion(), parentVersion())).toEqual({
      kind: 'comparable',
      parentCommit: PARENT_COMMIT,
    });
  });

  it('is an origin version when the row names no parent and none was supplied', () => {
    expect(comparabilityOf(childVersion({ parent_version: null }), null)).toEqual({
      kind: 'origin_version',
    });
  });

  it('is unresolved when the row names a parent the payload did not carry', () => {
    expect(comparabilityOf(childVersion(), null)).toEqual({
      kind: 'parent_unresolved',
      named: PARENT_COMMIT,
    });
  });

  it('is a MISMATCH when the supplied parent is a different commit', () => {
    const wrong = parentVersion({ commit_id: GRANDPARENT });
    expect(comparabilityOf(childVersion(), wrong)).toEqual({
      kind: 'parent_mismatch',
      named: PARENT_COMMIT,
      supplied: GRANDPARENT,
    });
  });

  it('is a MISMATCH when the row names no parent but one was supplied anyway', () => {
    expect(comparabilityOf(childVersion({ parent_version: null }), parentVersion())).toEqual({
      kind: 'parent_mismatch',
      named: null,
      supplied: PARENT_COMMIT,
    });
  });
});

describe('buildClauseDiff — the refusal to diff the wrong two rows', () => {
  const model = buildClauseDiff(
    input({ parent: parentVersion({ commit_id: GRANDPARENT }) }),
  );

  it('computes no text, no anchors, no CAT and no scalars', () => {
    expect(model.comparability.kind).toBe('parent_mismatch');
    expect(model.text).toBeNull();
    expect(model.anchors).toBeNull();
    expect(model.cat).toBeNull();
    expect(model.scalars).toEqual([]);
  });

  it('raises a discrepancy naming both commits', () => {
    const finding = model.findings.find((entry) => entry.code === 'parent_mismatch');
    expect(finding?.level).toBe('discrepancy');
    expect(finding?.detail).toContain(PARENT_COMMIT);
    expect(finding?.detail).toContain(GRANDPARENT);
    expect(finding?.authority).not.toBe('');
  });

  it('still renders the verdict, because the verdict is the database’s and not ours', () => {
    expect(model.verdict.delta).toBe('weaken');
    expect(model.verdict.basis).toBe('lattice');
  });
});

describe('buildClauseDiff — the observations', () => {
  const model = buildClauseDiff(input());

  it('diffs the text and reproduces both sides', () => {
    const fromSide = (model.text?.segments ?? [])
      .filter((segment) => segment.kind !== 'added')
      .map((segment) => segment.text)
      .join('');
    expect(fromSide).toBe(PARENT_TEXT);
  });

  it('reports the dropped anchors in parent order and nothing else as dropped', () => {
    expect(model.anchors?.dropped).toEqual(['accumulator', 'responsible_engineer']);
    expect(model.anchors?.added).toEqual([]);
    expect(model.anchors?.kept).toEqual(['HPU-0412', 'ISOLATION_AUTHORITY']);
  });

  it('reports the CAT field changes as pointers with canonical representations', () => {
    const pointers = (model.cat?.changes ?? []).map((change) => change.pointer);
    expect(pointers).toContain('/location');
    expect(pointers).toContain('/countersignature');
    const removed = model.cat?.changes.find((change) => change.pointer === '/countersignature');
    expect(removed?.kind).toBe('removed');
    expect(removed?.fromRepr).toBe('"responsible_engineer"');
    expect(removed?.toRepr).toBeNull();
  });

  it('leaves an unchanged CAT subtree out of the change list', () => {
    const pointers = (model.cat?.changes ?? []).map((change) => change.pointer);
    expect(pointers).not.toContain('/quantity');
    expect(pointers).not.toContain('/quantity/value');
    expect(pointers).not.toContain('/actor');
  });

  it('marks ordinal and printed_label as presentation only', () => {
    const ordinal = model.scalars.find((scalar) => scalar.column === 'ordinal');
    expect(ordinal?.presentationOnly).toBe(true);
    const digest = model.scalars.find((scalar) => scalar.column === 'canon_sha256');
    expect(digest?.presentationOnly).toBe(false);
    expect(digest?.changed).toBe(true);
  });

  it('is deterministic — two builds serialise identically', () => {
    expect(JSON.stringify(buildClauseDiff(input()))).toBe(
      JSON.stringify(buildClauseDiff(input())),
    );
  });
});

describe('buildClauseDiff — the findings, and their authorities', () => {
  it('says nothing at all about a well-formed weaken with a corroborated witness', () => {
    // The quiet case is the important control: a findings panel that always has
    // something in it is a findings panel nobody reads.
    expect(buildClauseDiff(input()).findings).toEqual([]);
  });

  it('gives every finding a non-empty authority, title and detail', () => {
    const models = [
      buildClauseDiff(input({ parent: parentVersion({ commit_id: GRANDPARENT }) })),
      buildClauseDiff(input({ parent: null })),
      buildClauseDiff(input({ version: childVersion({ control_delta: 'restate', gen: 4 }) })),
      buildClauseDiff(
        input({ delta: { delta: 'weaken', basis: 'lattice', witnesses: null, minimal: null } }),
      ),
      buildClauseDiff(
        input({
          delta: {
            delta: 'weaken',
            basis: 'lattice',
            witnesses: [
              { rule_id: 'R-X', field: 'not_a_field', from_repr: '', to_repr: '', note: '' },
            ],
            minimal: null,
          },
        }),
      ),
      buildClauseDiff(input({ version: childVersion({ blood_size: 2, sev_max: 4 }) })),
    ];

    const all = models.flatMap((model) => model.findings);
    expect(all.length).toBeGreaterThan(6);
    for (const finding of all) {
      expect(finding.authority.trim(), finding.code).not.toBe('');
      expect(finding.title.trim(), finding.code).not.toBe('');
      expect(finding.detail.trim(), finding.code).not.toBe('');
    }

    // Every declared code must be reachable by some payload, or it is dead vocabulary.
    const seen = new Set(all.map((finding) => finding.code));
    for (const code of [
      'parent_mismatch',
      'parent_unresolved',
      'generation_not_increasing',
      'verdict_disagrees_with_column',
      'witness_guard_expectation',
      'minimality_unestablished',
      'witness_field_unresolvable',
      'blood_size_decreased',
      'severity_decreased',
    ]) {
      expect(seen, `unreachable finding code: ${code}`).toContain(code);
    }
  });

  it('sorts discrepancies before observations', () => {
    const model = buildClauseDiff(
      input({
        version: childVersion({ control_delta: 'restate' }),
        delta: { delta: 'weaken', basis: 'lattice', witnesses: null, minimal: null },
      }),
    );
    const levels = model.findings.map((finding) => finding.level);
    const firstObservation = levels.indexOf('observation');
    if (firstObservation >= 0) {
      expect(levels.slice(firstObservation).every((level) => level === 'observation')).toBe(true);
    }
  });

  it('raises the witness-guard discrepancy for a lattice weaken with no witnesses', () => {
    const model = buildClauseDiff(
      input({ delta: { delta: 'weaken', basis: 'lattice', witnesses: null, minimal: null } }),
    );
    const finding = model.findings.find((entry) => entry.code === 'witness_guard_expectation');
    expect(finding?.level).toBe('discrepancy');
    expect(finding?.authority).toContain('fn_delta_witness_guard');
  });

  it('raises the same discrepancy when the emitter asserts there are NO witnesses', () => {
    const model = buildClauseDiff(
      input({ delta: { delta: 'weaken', basis: 'lattice', witnesses: [], minimal: true } }),
    );
    expect(model.findings.some((entry) => entry.code === 'witness_guard_expectation')).toBe(true);
  });

  it('does NOT raise it for a strengthen, which the guard does not cover', () => {
    const model = buildClauseDiff(
      input({
        version: childVersion({ control_delta: 'strengthen' }),
        delta: { delta: 'strengthen', basis: 'lattice', witnesses: null, minimal: null },
      }),
    );
    expect(model.findings.some((entry) => entry.code === 'witness_guard_expectation')).toBe(false);
  });

  it('raises a discrepancy when the verdict and the column disagree', () => {
    const model = buildClauseDiff(input({ version: childVersion({ control_delta: 'restate' }) }));
    const finding = model.findings.find(
      (entry) => entry.code === 'verdict_disagrees_with_column',
    );
    expect(finding?.level).toBe('discrepancy');
    expect(finding?.detail).toContain('restate');
    expect(finding?.detail).toContain('weaken');
  });

  it('raises a discrepancy when the generation does not increase', () => {
    const model = buildClauseDiff(input({ version: childVersion({ gen: 4 }) }));
    expect(
      model.findings.some((entry) => entry.code === 'generation_not_increasing'),
    ).toBe(true);
  });

  it('raises a discrepancy when the two rows are not the same clause', () => {
    const model = buildClauseDiff(
      input({ parent: parentVersion({ clause_uuid: '018f3a30-2200-7d10-9f31-000000000000' }) }),
    );
    expect(model.findings.some((entry) => entry.code === 'clause_uuid_disagrees')).toBe(true);
  });

  it('observes an unestablished minimality claim', () => {
    const model = buildClauseDiff(
      input({
        delta: {
          delta: 'weaken',
          basis: 'lattice',
          witnesses: [
            {
              rule_id: 'R-SCOPE-NARROWED',
              field: 'cat.location',
              from_repr: 'a',
              to_repr: 'b',
              note: 'n',
            },
          ],
          minimal: null,
        },
      }),
    );
    const finding = model.findings.find((entry) => entry.code === 'minimality_unestablished');
    expect(finding?.level).toBe('observation');
  });

  it('observes a decreasing blood_size, which the M2 accumulator only appends to', () => {
    const model = buildClauseDiff(input({ version: childVersion({ blood_size: 2 }) }));
    expect(model.findings.some((entry) => entry.code === 'blood_size_decreased')).toBe(true);
  });

  it('is quiet about a clean strengthen with matching columns', () => {
    const model = buildClauseDiff(
      input({
        version: childVersion({ control_delta: 'strengthen' }),
        delta: {
          delta: 'strengthen',
          basis: 'lattice',
          witnesses: [
            {
              rule_id: 'R2_SCOPE',
              field: 'cat.location',
              from_repr: 'every_accumulator_in_circuit',
              to_repr: 'hydraulic_power_unit',
              note: 'scope',
            },
          ],
          minimal: true,
        },
      }),
    );
    expect(model.findings.filter((finding) => finding.level === 'discrepancy')).toEqual([]);
  });
});
