// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE NAVIGATION'S ADDRESSING, AND THE TWO WAYS IT COULD BE WRONG.
 *
 * `src/app/subjects.ts` decides which identifier goes in which query parameter of which
 * nav link. It has exactly two failure modes and both of them look fine on the day they
 * ship:
 *
 *   1. **It carries a value the console invented.** That is how `BLK-07` reached the live
 *      URL. So the module's own bytes are read back and searched for an identifier, and the
 *      four non-resolved states of the subject index are each asserted to produce a link
 *      with no subject at all rather than a plausible one.
 *   2. **It carries a value under a name nothing reads.** A link that says
 *      `#/custody?site_code=…` when `CustodyRoot` reads `?site=` is a link that looks
 *      addressed, opens on nothing, and produces the same screenshot as the defect it was
 *      meant to fix. So the parameter table is asserted against the five feature modules'
 *      OWN declarations, read out of their source.
 *
 * ── WHY THE PIN READS BYTES RATHER THAN IMPORTING THE CONSTANT ───────────────────
 *
 * `import { SITE_PARAM } from '.../CustodyRoot'` would be the better assertion and it is
 * not the one written, for a mechanical reason: every one of those five modules pulls its
 * whole feature's module graph in behind it, and a single half-written sibling anywhere in
 * that graph makes THIS file fail to collect — reporting a defect in the shell's addressing
 * where there is none. The declaration is therefore read out of the file, anchored to
 * `export const <NAME> = '<value>'`, and **a regex that finds nothing is a failure**, so a
 * constant that is renamed or deleted is red rather than silently unasserted.
 */

import { describe, expect, it } from 'vitest';

import {
  SUBJECT_SLOTS,
  detailToggleHref,
  subjectHref,
  subjectParamsFor,
  type SubjectParam,
} from '../../../src/app/subjects';
import type { DemoSubjects, SubjectIndex } from '../../../src/data/demo-subjects';
import { nodeFs } from '../data/_support';

// ── Fixtures ───────────────────────────────────────────────────────────────

/**
 * Subjects, as opaque strings.
 *
 * Deliberately not uuid-shaped, for `tests/unit/data/demo-subjects.test.ts`'s reason:
 * nothing in the console parses one, and the no-identifier assertion below has to be able
 * to run over this file too.
 */
const SEEDED: DemoSubjects = Object.freeze({
  permitId: 'permit-named-by-the-kernel',
  crId: 'change-request-named-by-the-kernel',
  checkId: 'check-named-by-the-kernel',
  receiptId: 'receipt-named-by-the-kernel',
  clauseUuid: 'clause-named-by-the-kernel',
  commitId: 'commit-named-by-the-kernel',
  runId: 'run-named-by-the-kernel',
  lessonId: 'lesson-named-by-the-kernel',
  siteCode: 'site-code-named-by-the-kernel',
  siteId: 'site-named-by-the-kernel',
  absent: Object.freeze([]),
});

const RESOLVED: SubjectIndex = { status: 'resolved', subjects: SEEDED };

/** Every state that is not an answer. None of them may produce a subject. */
const NOT_AN_ANSWER: readonly SubjectIndex[] = [
  { status: 'no_source' },
  { status: 'resolving' },
  { status: 'unavailable', failure: 'status', detail: 'HTTP 404 — no resource is declared at GET /v1/demo/subjects' },
];

function withSubjects(patch: Partial<DemoSubjects>): SubjectIndex {
  return { status: 'resolved', subjects: { ...SEEDED, ...patch } };
}

// ── 1. The parameter names are the surfaces' own ───────────────────────────

describe('the table names the parameters the surfaces actually read', () => {
  /**
   * Where each surface declares the parameter it reads, and under which name. The
   * `member` beside it is what this shell puts in that slot.
   */
  const DECLARED: readonly (readonly [string, string, string, SubjectParam['member']])[] = [
    ['gate', 'src/features/gate/GateSurfaceRoot.tsx', 'PERMIT_PARAM', 'permitId'],
    ['silence', 'src/features/silence/SilenceSurfaceRoot.tsx', 'PERMIT_PARAM', 'permitId'],
    ['custody', 'src/features/custody/CustodyRoot.tsx', 'SITE_PARAM', 'siteCode'],
    ['propagation', 'src/features/propagation/PropagationSurfaceRoot.tsx', 'LESSON_PARAM', 'lessonId'],
    ['diff', 'src/features/diff/ClauseDiffScreen.tsx', 'CLAUSE_PARAM', 'clauseUuid'],
    ['diff', 'src/features/diff/ClauseDiffScreen.tsx', 'COMMIT_PARAM', 'commitId'],
  ];

  function declaredValue(source: string, file: string, name: string): string {
    const found = new RegExp(`export const ${name} = '([^']+)'`).exec(source);
    expect(
      found,
      `${file} no longer declares \`export const ${name}\`. The shell's navigation ` +
        'transcribes that parameter name, and a rename with nothing asserting it is a nav ' +
        'link that looks addressed and opens on nothing.',
    ).not.toBeNull();
    return found?.[1] ?? '';
  }

  it('matches the declaration of every surface it addresses', async () => {
    const fs = await nodeFs();
    for (const [id, file, name, member] of DECLARED) {
      const param = declaredValue(fs.readFileSync(file, 'utf8'), file, name);
      expect(
        SUBJECT_SLOTS.get(id),
        `${id}: src/app/subjects.ts and ${file} disagree about the query parameter. The ` +
          'shell transcribes it rather than importing it — the entry chunk may not pull a ' +
          'feature chunk onto the critical path — and this assertion is what keeps the ' +
          'transcription honest.',
      ).toContainEqual({ param, member });
    }
  });

  it('addresses exactly the five surfaces that render one subject', () => {
    expect([...SUBJECT_SLOTS.keys()].sort()).toEqual([
      'custody',
      'diff',
      'gate',
      'propagation',
      'silence',
    ]);
  });

  it('gives no subject to a surface that takes none, so no link carries a dead parameter', () => {
    for (const id of ['overview', 'evidence', 'audit', 'ancestry', 'disposition']) {
      expect(subjectParamsFor(id, RESOLVED), `${id} was handed a subject it does not read`).toEqual(
        [],
      );
      expect(subjectHref(id, `/${id}`, RESOLVED, 'plain')).toBe(`#/${id}`);
    }
  });
});

// ── 2. It never guesses ────────────────────────────────────────────────────

describe('the degradation path: no answer means no subject, never a plausible one', () => {
  it('carries nothing while the index is unresolved, whichever of the three states it is in', () => {
    for (const index of NOT_AN_ANSWER) {
      for (const id of [...SUBJECT_SLOTS.keys()]) {
        expect(subjectParamsFor(id, index), `${id} under status=${index.status}`).toEqual([]);
        expect(
          subjectHref(id, `/${id}`, index, 'plain'),
          `${id} under status=${index.status} must open the bare path, exactly as it did ` +
            'before this module existed',
        ).toBe(`#/${id}`);
      }
    }
  });

  it('carries nothing when the kernel answered and named null for that slot', () => {
    expect(subjectParamsFor('gate', withSubjects({ permitId: null }))).toEqual([]);
    expect(subjectParamsFor('custody', withSubjects({ siteCode: null }))).toEqual([]);
    expect(subjectParamsFor('propagation', withSubjects({ lessonId: null }))).toEqual([]);
  });

  it('treats an empty string as a name nobody gave — a `?permit=` addresses nothing', () => {
    expect(subjectParamsFor('gate', withSubjects({ permitId: '' }))).toEqual([]);
  });

  it('addresses the diff together or not at all — a clause with no commit is no version', () => {
    expect(subjectParamsFor('diff', RESOLVED)).toEqual([
      ['clause', 'clause-named-by-the-kernel'],
      ['commit', 'commit-named-by-the-kernel'],
    ]);
    expect(subjectParamsFor('diff', withSubjects({ commitId: null }))).toEqual([]);
    expect(subjectParamsFor('diff', withSubjects({ clauseUuid: null }))).toEqual([]);
  });
});

// ── 3. The address it builds ───────────────────────────────────────────────

describe('the href', () => {
  it('carries the subject the kernel named, under the surface`s own parameter', () => {
    expect(subjectHref('gate', '/gate', RESOLVED, 'plain')).toBe(
      '#/gate?permit=permit-named-by-the-kernel',
    );
    expect(subjectHref('custody', '/custody', RESOLVED, 'plain')).toBe(
      '#/custody?site=site-code-named-by-the-kernel',
    );
    expect(subjectHref('diff', '/diff', RESOLVED, 'plain')).toBe(
      '#/diff?clause=clause-named-by-the-kernel&commit=commit-named-by-the-kernel',
    );
  });

  it('carries the detail mode alongside the subject, never instead of it', () => {
    expect(subjectHref('gate', '/gate', RESOLVED, 'full')).toBe(
      '#/gate?permit=permit-named-by-the-kernel&detail=full',
    );
    // PLAIN is the default and has no spelling: a bare `#/gate` and `#/gate?detail=plain`
    // are the same address, so only one of them is ever emitted.
    expect(subjectHref('gate', '/gate', { status: 'resolving' }, 'plain')).toBe('#/gate');
  });
});

describe('the detail toggle keeps everything else in the address', () => {
  it('adds and removes only `detail`', () => {
    const params = new URLSearchParams('permit=typed-by-the-reader');
    expect(detailToggleHref('/gate', params, 'full')).toBe(
      '#/gate?permit=typed-by-the-reader&detail=full',
    );
    expect(detailToggleHref('/gate', new URLSearchParams('permit=typed-by-the-reader&detail=full'), 'plain')).toBe(
      '#/gate?permit=typed-by-the-reader',
    );
  });

  it('produces a bare path when the address carries nothing else', () => {
    expect(detailToggleHref('/audit', new URLSearchParams(), 'plain')).toBe('#/audit');
    expect(detailToggleHref('/audit', new URLSearchParams(), 'full')).toBe('#/audit?detail=full');
  });
});

// ── 4. The rule, turned on this module's own bytes ─────────────────────────

const UUID_ANYWHERE = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/;

describe('the shell names no row', () => {
  it('carries no UUID literal, in code or in a comment', async () => {
    const fs = await nodeFs();
    for (const file of ['src/app/subjects.ts', 'src/app/App.tsx']) {
      const source = fs.readFileSync(file, 'utf8');
      const found = UUID_ANYWHERE.exec(source);
      expect(
        found?.[0] ?? null,
        `${file} contains the identifier ${found?.[0] ?? ''}. An identifier in a console ` +
          'file is a claim about a row this console did not write; the navigation asks for ' +
          'one at GET /v1/demo/subjects instead.',
      ).toBeNull();
    }
  });

  it('carries none of the three identifiers that answered 404 on the live URL', async () => {
    const fs = await nodeFs();
    // Spelled in halves so this assertion is not itself somewhere a reader could copy a
    // working identifier out of.
    const dead = ['BLK' + '-07', '018f3a30' + '-2200', '5f916282'];
    for (const file of ['src/app/subjects.ts', 'src/app/App.tsx']) {
      const source = fs.readFileSync(file, 'utf8');
      for (const id of dead) {
        expect(source.includes(id), `${file} still names ${id}`).toBe(false);
      }
    }
  });

  it('does not import a feature module into the entry chunk to get a parameter name', async () => {
    const fs = await nodeFs();
    const source = fs.readFileSync('src/app/subjects.ts', 'utf8');
    expect(
      /^\s*import[^\n]*from '\.\.\/features\//m.test(source),
      'src/app/subjects.ts statically imports a feature module. The shell is the entry ' +
        'chunk and that import drags a feature chunk onto the critical path; the parameter ' +
        'names are transcribed and pinned by the assertions at the top of this file.',
    ).toBe(false);
  });
});
