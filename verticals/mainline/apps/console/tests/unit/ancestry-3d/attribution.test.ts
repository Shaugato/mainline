// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * NO NAMED PERSON, EVER — `docs/dimensionality-charter.md` §4.
 *
 * D15 / I15 / `ARCHITECTURE.md` §11.5's Attribution Rule, carried into the artefact that
 * outlives the schema: a screenshot.
 *
 * The gate has two halves, and both are here:
 *
 *   REFUSE  `projectWalk` throws on a layout whose nodes carry a person-shaped field. It
 *           does not filter and continue — a payload carrying a person is a breach one
 *           hop upstream, and a renderer that quietly dropped the field would hide it.
 *   STARVE  The label layer has nowhere for a person to go. It renders exactly two kinds
 *           of string: a year and the still node's own label.
 */

import { describe, expect, it } from 'vitest';

import { buildLabels, MAX_LABELS } from '../../../src/features/ancestry/render3d/label-model';
import {
  assertNoPersonFields,
  projectWalk,
} from '../../../src/features/ancestry/render3d/projection';
import type { AncestryLayout } from '../../../src/features/ancestry/render3d/contract';
import { FIXTURE_LAYOUT, STILL_NODE_ID, layoutWithAbstractTime } from './_fixture';

const SCENE = projectWalk(FIXTURE_LAYOUT);

/** Adds one extra key to the first node, as a payload one hop upstream would. */
function withExtraField(key: string, value: unknown): AncestryLayout {
  const [first, ...rest] = FIXTURE_LAYOUT.nodes;
  if (first === undefined) throw new Error('fixture is empty');
  return {
    ...FIXTURE_LAYOUT,
    nodes: [{ ...first, [key]: value }, ...rest],
  };
}

describe('the refusal', () => {
  it('accepts the clean fixture', () => {
    expect(() => {
      assertNoPersonFields(FIXTURE_LAYOUT);
    }).not.toThrow();
  });

  const PLANTED = [
    'signer_sub',
    'signerSub',
    'sub',
    'person_id',
    'supervisor',
    'operator_name',
    'authorName',
    'user',
    'actor',
    'employee_no',
    'email',
    'who_signed',
    'name',
  ];

  it.each(PLANTED)('refuses a node carrying "%s"', (key) => {
    expect(() => projectWalk(withExtraField(key, 'anything at all'))).toThrow(
      /THE ATTRIBUTION RULE/,
    );
  });

  it('names the offending field and the node in the failure', () => {
    try {
      projectWalk(withExtraField('signer_sub', 'x'));
      expect.unreachable('the renderer drew a layout carrying a person');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      expect(message).toContain('signer_sub');
      expect(message).toContain(STILL_NODE_ID);
      expect(message).toContain('D15');
    }
  });

  it('throws rather than filtering — the breach stays visible', () => {
    // If the renderer filtered, this would succeed and produce a scene. It must not.
    expect(() => projectWalk(withExtraField('person', { id: 'p-1' }))).toThrow();
  });

  it('does not fire on the layout’s own legitimate fields', () => {
    for (const key of ['id', 'kind', 'x', 'y', 't', 'severity', 'virulence', 'lane', 'label']) {
      expect(Object.keys(FIXTURE_LAYOUT.nodes[0] ?? {})).toContain(key);
    }
    expect(() => projectWalk(FIXTURE_LAYOUT)).not.toThrow();
  });
});

describe('the projected node has nowhere to put a person', () => {
  it('exposes exactly the closed set of fields', () => {
    const node = SCENE.nodes[0];
    expect(node).toBeDefined();
    expect(Object.keys(node ?? {}).sort()).toEqual(
      ['id', 'kind', 'label', 'lane', 'severity', 'still', 't', 'virulence', 'x', 'y', 'z'].sort(),
    );
  });

  it('positions, colours and sizes nothing by an identity', () => {
    // The only inputs to geometry are x, y, t, severity, lane and kind. Asserted by
    // construction: there is no other field to read.
    for (const node of SCENE.nodes) {
      const keys = Object.keys(node).join(' ').toLowerCase();
      for (const fragment of ['signer', 'person', 'actor', 'user', 'author', 'operator']) {
        expect(keys).not.toContain(fragment);
      }
    }
  });
});

describe('what is allowed to become a glyph', () => {
  const labels = buildLabels(SCENE, 1);

  it('renders years and the still node’s own label, and nothing else', () => {
    const kinds = new Set(labels.map((label) => label.kind));
    expect([...kinds].sort()).toEqual(['still', 'year']);
  });

  it('renders every year as a bare four-digit year', () => {
    for (const label of labels.filter((entry) => entry.kind === 'year')) {
      expect(label.text).toMatch(/^\d{4}$/);
    }
  });

  it('renders the still label verbatim from the layout and does not compose it', () => {
    const still = labels.find((label) => label.kind === 'still');
    const source = FIXTURE_LAYOUT.nodes.find((node) => node.id === STILL_NODE_ID);
    expect(still?.text).toBe(source?.label);
  });

  it('renders no commit message, no severity number, no virulence band and no edge basis', () => {
    const text = labels.map((label) => label.text).join(' | ');
    expect(text).not.toContain('blood_fatal');
    expect(text).not.toContain('inferred_semantic');
    expect(text).not.toContain('severity');
    expect(text).not.toContain('Strengthen');
    expect(text).not.toContain('renumbered');
  });

  it('draws no year at all on an axis that carries no calendar meaning', () => {
    const abstract = buildLabels(projectWalk(layoutWithAbstractTime()), 1);
    expect(abstract.every((label) => label.kind === 'still')).toBe(true);
  });

  it('thins by stride without ever dropping the still label', () => {
    const thinned = buildLabels(SCENE, 4);
    expect(thinned.length).toBeLessThan(labels.length);
    expect(thinned.some((label) => label.kind === 'still')).toBe(true);
  });

  it('never exceeds the label cap, whatever the corpus does', () => {
    const many: AncestryLayout = {
      ...FIXTURE_LAYOUT,
      nodes: Array.from({ length: 200 }, (_unused, index) => ({
        id: `n-${index}`,
        kind: 'commit' as const,
        x: index,
        y: index,
        // One node per year for two centuries.
        t: Date.UTC(1830 + index, 0, 1),
        severity: 0,
        virulence: 'routine' as const,
        lane: index % 3,
        label: `commit ${index}`,
      })),
      edges: [],
      timeExtent: [Date.UTC(1830, 0, 1), Date.UTC(2029, 0, 1)],
    };
    expect(buildLabels(projectWalk(many), 1).length).toBeLessThanOrEqual(MAX_LABELS);
  });

  it('keeps the deep past when it thins — a reader cannot date 1907 from memory', () => {
    const many: AncestryLayout = {
      ...FIXTURE_LAYOUT,
      nodes: Array.from({ length: 60 }, (_unused, index) => ({
        id: `n-${index}`,
        kind: 'commit' as const,
        x: 0,
        y: index,
        t: Date.UTC(1960 + index, 0, 1),
        severity: 0,
        virulence: 'routine' as const,
        lane: 0,
        label: `commit ${index}`,
      })),
      edges: [],
      timeExtent: [Date.UTC(1960, 0, 1), Date.UTC(2019, 0, 1)],
    };
    const labelled = buildLabels(projectWalk(many), 1).map((label) => label.text);
    expect(labelled).toContain('1960');
    expect(labelled).not.toContain('2019');
  });
});
