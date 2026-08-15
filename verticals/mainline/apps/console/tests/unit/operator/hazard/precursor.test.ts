// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The precursor half of HSG250 Figure 1 element 6.
 *
 * THE FIXTURES ARE TRANSCRIPTS, NOT INVENTIONS. Every field value below was captured from
 * `GET /v1/permits/{permit_id}/blocking-checks` and `GET /v1/clauses/{clause_uuid}/ancestry`
 * against `scripts/deploy/local_furl.py` over the local CockroachDB node on 2026-08-15.
 * They are inputs to a renderer, which is what a fixture is; nothing here is asserted to be
 * true of the deployment, and the renderer is never given a value the API cannot produce.
 *
 * The one thing these tests exist to stop is the class of defect that would make the film
 * worthless: a card that shows a date, a severity or a sentence the response did not carry.
 */

import { describe, expect, it } from 'vitest';

import {
  renderPrecursor,
  utcInstant,
  type ChipLookup,
  type PrecursorAncestry,
  type PrecursorCheck,
} from '../../../../src/operator/hazard/precursor';

/** The commit the seeded obligation names. Fixture input, captured, not asserted. */
const COMMIT = '9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39';

function event(overrides: Partial<NonNullable<PrecursorCheck['precursor']>> = {}): NonNullable<
  PrecursorCheck['precursor']
> {
  return {
    external_ref: 'DEMO-INC-0001',
    kind: 'incident',
    title: 'SYNTHETIC — Stored energy release during intrusive work',
    occurred_at: '2019-03-14T06:20:00Z',
    severity_gate: 4,
    severity_actual: 4,
    severity_potential: 4,
    severity_basis: 'human_rated',
    source_object_key: 'demo/incident-0001.pdf',
    source_sha256: '1f84f023f5f891fadab55ef7e9f16f08285b3803f65c509f514476ea6770ba46',
    ...overrides,
  };
}

function closure(
  overrides: Partial<NonNullable<PrecursorAncestry['closure']>> = {},
): NonNullable<PrecursorAncestry['closure']> {
  return {
    max_severity: 4,
    virulence: 'blood_major',
    closure_gen: 0,
    ancestor_count: 1,
    computed_by: 'verticals/mainline/db/seeds/demo/demo_world.sql',
    computed_at: '2026-08-14T23:02:42.173203Z',
    ...overrides,
  };
}

function check(overrides: Partial<PrecursorCheck> = {}): PrecursorCheck {
  return {
    clause_label: '7.3.2(b)',
    clause_uuid: 'dec0de00-0004-4000-8000-000000000001',
    commit_id: COMMIT,
    origin: 'blame_ancestry',
    severity: 4,
    virulence: 'blood_major',
    closure_gen: 0,
    evidence_summary:
      'SYNTHETIC — recalled precursor DEMO-INC-0001 reaches the clause version this permit relies on.',
    materialised_at: '2026-08-02T03:00:10Z',
    precursor: event(),
    ...overrides,
  };
}

function ancestry(overrides: Partial<PrecursorAncestry> = {}): PrecursorAncestry {
  return {
    as_of_commit: COMMIT,
    closure: closure(),
    attribution: 'SYNTHETIC — the investigation names this clause as the control that failed.',
    basis: 'asserted_document',
    state: 'active',
    ...overrides,
  };
}

/** A lookup that claims exactly the pointers the real blocking-checks envelope claims. */
const checksChip: ChipLookup = (pointer) => {
  if (pointer === '/checks/0') {
    return { kind: 'db:column', pointer };
  }
  if (pointer === '/checks/0/open' || pointer === '/checks/0/disposition_id') {
    return { kind: 'derived', pointer };
  }
  return null;
};

const ancestryChip: ChipLookup = (pointer) =>
  pointer === '/blame_edges/0' ? { kind: 'db:column', pointer } : null;

const NO_CHIPS: ChipLookup = () => null;

function render(
  over: {
    check?: PrecursorCheck | null;
    ancestry?: PrecursorAncestry | null;
    checkChip?: ChipLookup;
    ancestryChip?: ChipLookup;
  } = {},
): ReturnType<typeof renderPrecursor> {
  return renderPrecursor({
    check: over.check === undefined ? check() : over.check,
    checkPointer: '/checks/0',
    checkChip: over.checkChip ?? checksChip,
    checkSource: {
      resource: 'blocking_checks',
      method: 'GET',
      path: '/v1/permits/dec0de00-0006-4000-8000-000000000001/blocking-checks',
      status: 200,
      wireBytes: 2408,
      observedAt: '2026-08-15T11:06:45.450447Z',
    },
    ancestry: over.ancestry === undefined ? ancestry() : over.ancestry,
    ancestryChip: over.ancestryChip ?? ancestryChip,
    ancestrySource: null,
    seedCitation: null,
  });
}

function text(result: ReturnType<typeof renderPrecursor>): string {
  return result.element?.textContent ?? '';
}

describe('utcInstant', () => {
  it('renders the seeded occurred_at in UTC, whatever zone the reader is in', () => {
    expect(utcInstant('2019-03-14T06:20:00Z')).toBe('14 March 2019 06:20 UTC');
  });

  it('renders the same characters for the same instant written with an offset', () => {
    // 06:20Z and 07:20+01:00 are one instant. A card that showed two different days for
    // them would be disagreeing with itself about when a fatality nearly happened.
    expect(utcInstant('2019-03-14T07:20:00+01:00')).toBe(utcInstant('2019-03-14T06:20:00Z'));
  });

  it('answers null for absent or unparseable input rather than Invalid Date', () => {
    expect(utcInstant(null)).toBeNull();
    expect(utcInstant('')).toBeNull();
    expect(utcInstant('not an instant')).toBeNull();
  });
});

describe('renderPrecursor — the date is 2019 and it is a column', () => {
  it('renders the seeded 2019 occurred_at, both as the emitted ISO and in words', () => {
    const out = text(render());
    expect(out).toContain('2019-03-14T06:20:00Z');
    expect(out).toContain('14 March 2019 06:20 UTC');
  });

  it('renders no year the payload did not carry — 2024 in particular', () => {
    // The only 2024 anywhere near this story lives inside a STAGED propagation payload
    // this card never reads. If one ever appears here, it was composed.
    const out = text(render());
    expect(out).not.toContain('2024');
  });

  it('renders no date at all when the payload carried no occurred_at', () => {
    const withoutDate = check({ precursor: event({ occurred_at: null }) });
    const result = render({ check: withoutDate });
    expect(text(result)).not.toContain('2019');
    expect(result.absent).toContain('precursor_event.occurred_at');
  });
});

describe('renderPrecursor — the seeded strings are not paraphrased', () => {
  it('keeps the SYNTHETIC prefix on the event title', () => {
    expect(text(render())).toContain('SYNTHETIC — Stored energy release during intrusive work');
  });

  it('keeps the SYNTHETIC prefix on the blame edge attribution', () => {
    expect(text(render())).toContain(
      'SYNTHETIC — the investigation names this clause as the control that failed.',
    );
  });

  it('keeps the SYNTHETIC prefix on the evidence summary', () => {
    expect(text(render())).toContain(
      'SYNTHETIC — recalled precursor DEMO-INC-0001 reaches the clause version this permit relies on.',
    );
  });

  it('renders the origin channel by name', () => {
    expect(text(render())).toContain('blame_ancestry');
  });
});

describe('renderPrecursor — absence renders as absence', () => {
  it('renders nothing at all when no blocking check came back', () => {
    const result = render({ check: null });
    expect(result.element).toBeNull();
    expect(result.absent).toEqual(['blocking_check']);
  });

  it('omits the attribution sentence, and names it absent, when ancestry did not answer', () => {
    const result = render({ ancestry: null });
    expect(text(result)).not.toContain('the investigation names this clause');
    expect(result.absent).toContain('blame_edge.attribution');
  });

  it('renders no severity figure when the payload carried none', () => {
    const blank = check({
      severity: null,
      virulence: null,
      closure_gen: null,
      precursor: event({ severity_gate: null, severity_actual: null, severity_potential: null }),
    });
    const out = text(render({ check: blank, ancestry: null }));
    expect(out).not.toContain('severity gate');
    expect(out).not.toContain('blood_major');
  });
});

describe('renderPrecursor — the projection exhibit', () => {
  it('puts the obligation and the blame closure side by side and reports them equal', () => {
    const out = text(render());
    expect(out).toContain('on the obligation');
    expect(out).toContain('in the blame closure');
    expect(out).toContain('the two rows carry the same three values');
  });

  it('reports them unequal rather than hiding a disagreement', () => {
    const drifted = ancestry({ closure: closure({ max_severity: 3 }) });
    const out = text(render({ ancestry: drifted }));
    expect(out).toContain('the two rows disagree');
  });

  it('suppresses the comparison when the closure is for a different clause version', () => {
    // Comparing a closure computed at another commit is an exhibit that looks like proof
    // and is not one, so the row is not drawn at all.
    const otherCommit = ancestry({ as_of_commit: `${COMMIT.slice(0, 63)}0` });
    const out = text(render({ ancestry: otherCommit }));
    expect(out).not.toContain('in the blame closure');
    expect(out).not.toContain('the two rows carry the same three values');
  });
});

describe('renderPrecursor — provenance is claimed, never widened', () => {
  it('renders the chip at the pointer the payload claimed it at', () => {
    const result = render();
    const chip = result.element?.querySelector('[data-chip]');
    expect(chip?.textContent).toBe('db:column');
    expect(text(result)).toContain('/checks/0');
  });

  it('renders no chip at all when the payload claimed none', () => {
    const result = render({ checkChip: NO_CHIPS, ancestryChip: NO_CHIPS });
    expect(result.element?.querySelector('[data-chip]')).toBeNull();
  });
});

/* ══ what the SOURCE of src/operator/hazard/** may not contain ═════════════════════ */

const SOURCES = import.meta.glob<string>('../../../../src/operator/hazard/*.{ts,css}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

/**
 * Comments are stripped before the literal bans are applied, and only before those.
 *
 * The three modules DOCUMENT the values they must never contain — the 2019 instant, the
 * commit, the channel — because a reader has to know what the card is about. A grep that
 * could not tell an explanation from a hard-coded value would either fail on prose or
 * force the prose out, and the prose is the reason the next person gets this right. This
 * is a test heuristic and nothing else depends on it.
 */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[^:])\/\/.*$/gm, '$1 ');
}

describe('the source of src/operator/hazard/**', () => {
  it('finds all four owned modules', () => {
    const names = Object.keys(SOURCES)
      .map((path) => path.split('/').pop())
      .sort();
    expect(names).toEqual(['HazardCard.ts', 'hazard.css', 'memory-loop.ts', 'precursor.ts']);
  });

  it('carries an SPDX header on every file', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(source, path).toContain('SPDX-License-Identifier: FSL-1.1-ALv2');
    }
  });

  it('contains no UUID literal — every identifier comes from GET /v1/demo/subjects', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(code(source), path).not.toMatch(
        /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
      );
    }
  });

  it('contains no digest, no SQLSTATE and no timestamp literal', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      const body = code(source);
      expect(body, path).not.toMatch(/\b[0-9a-f]{64}\b/i);
      expect(body, path).not.toMatch(/\b(?:23514|P0001)\b/);
      expect(body, path).not.toMatch(/\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);
    }
  });

  it('has no setTimeout, setInterval or animation-driven reveal of any kind', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      const body = code(source);
      expect(body, path).not.toMatch(/setTimeout|setInterval|requestAnimationFrame/);
      // and no CSS that would make a value appear over time
      expect(body, path).not.toMatch(/@keyframes|animation\s*:|transition\s*:/);
    }
  });

  it('builds DOM without innerHTML, outerHTML or insertAdjacentHTML', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(code(source), path).not.toMatch(/innerHTML|outerHTML|insertAdjacentHTML|document\.write/);
    }
  });

  it('names no absolute origin — every request is same-origin, through the kernel client', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      expect(code(source), path).not.toMatch(/https?:\/\//);
    }
  });

  it('imports nothing from React or from the console’s own surfaces (R1)', () => {
    for (const [path, source] of Object.entries(SOURCES)) {
      const body = code(source);
      expect(body, path).not.toMatch(/from\s+['"]react/);
      expect(body, path).not.toMatch(/from\s+['"][^'"]*\/(?:app|design|features|verify)\//);
    }
  });

  it('carries exactly one editorial sentence, and it is the permitted one', () => {
    const straplines = Object.values(SOURCES).filter((source) =>
      source.includes('raised by recall, not by a checklist'),
    );
    expect(straplines).toHaveLength(1);
  });
});

describe('renderPrecursor — copy discipline (R17)', () => {
  const BANNED = [
    'similarity',
    'similar',
    'vector',
    'embedding',
    'nearest neighbour',
    'nearest neighbor',
    'cosine',
    'semantic',
    'watch it remember',
    'just retrieved',
    'is retrieving',
    'searching',
    'searches the corpus',
    'searched the corpus',
  ];

  it('uses no similarity, vector or live-retrieval language anywhere in the block', () => {
    const out = text(render()).toLowerCase();
    for (const word of BANNED) {
      expect(out).not.toContain(word);
    }
  });
});
