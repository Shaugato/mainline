// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SUBJECT INDEX — the read that replaced three identifiers nobody had seeded.
 *
 * On 2026-08-15 five of the console's nine navigation rows showed a judge nothing. Two of
 * them refused to choose a subject, and three chose one that does not exist: measured
 * against the live Function URL, `site_code 'BLK-07'`, clause `018f3a30-…` and commit
 * `5f916282…` each answered **404**. They were not stale — no seed in this repository has
 * ever written any of them.
 *
 * Two repairs were available and only one of them is honest. Pasting the identifier the
 * seed DOES carry into the same constants would produce the identical defect against the
 * next deployment, because a console file that names a row is a console asserting a fact
 * about a database it did not write. So the console asks: `GET /v1/demo/subjects`, whose
 * body the kernel SELECTs back out of the demo tables.
 *
 * ── NOT ONE UUID IS TYPED IN THIS FILE ───────────────────────────────────────────
 *
 * Every identifier below is minted by `crypto.randomUUID()` at run time. That is not
 * fastidiousness: a test carrying the demo's real permit would pass against a build that
 * had quietly reintroduced a constant, because the constant and the expectation would
 * agree. Random subjects can only be satisfied by a console that reads what it was given.
 *
 * The last describe block turns the same rule on the SOURCE TREE, over the actual bytes of
 * the files this repair touched.
 */

import { afterEach, describe, expect, it } from 'vitest';

import { contractRegistry } from '../../../src/data/contracts';
import {
  DEMO_SUBJECTS_ROUTE,
  addressSubject,
  resetDemoSubjects,
  resolveDemoSubjects,
  subjectAbsence,
  type SubjectAddressShape,
  type SubjectIndex,
} from '../../../src/data/demo-subjects';
import { HttpTransport } from '../../../src/data/transport';

import { nodeFs } from './_support';

const SCHEMA_ID = 'https://console.mainline.trappoint.org/contracts/1.0/subjects.schema.json';
const BASE = 'https://kernel.test';

/** A fresh, unguessable identifier. See the header: nothing here is the demo's. */
function anId(): string {
  return crypto.randomUUID();
}

/** 64 lowercase hex characters, minted the same way. */
function aCommit(): string {
  return `${crypto.randomUUID()}${crypto.randomUUID()}`.replace(/-/g, '');
}

interface SubjectsData {
  readonly site_id: string | null;
  readonly site_code: string | null;
  readonly permit_id: string | null;
  readonly cr_id: string | null;
  readonly check_id: string | null;
  readonly receipt_id: string | null;
  readonly clause_uuid: string | null;
  readonly commit_id: string | null;
  readonly run_id: string | null;
  readonly lesson_id: string | null;
  readonly subjects: Record<string, unknown>;
  readonly absent: readonly { subject: string; relation: string; reason: string }[];
}

/**
 * A payload that satisfies `contracts/subjects.schema.json` — the demo API's document,
 * copied into this workspace and pinned against it by `contracts.test.ts`.
 *
 * `subjects.site` is the one member the contract always requires, because the emitter
 * answers 404 rather than returning an index of nothing.
 */
function fullIndex(): SubjectsData {
  const siteId = anId();
  const siteCode = anId();
  return {
    site_id: siteId,
    site_code: siteCode,
    permit_id: anId(),
    cr_id: anId(),
    check_id: anId(),
    receipt_id: anId(),
    clause_uuid: anId(),
    commit_id: aCommit(),
    run_id: anId(),
    lesson_id: anId(),
    subjects: { site: { count: 1, site_id: siteId, site_code: siteCode } },
    absent: [],
  };
}

function envelopeFor(data: unknown): string {
  return JSON.stringify({
    envelope_version: 1,
    resource: 'demo_subjects',
    schema_id: SCHEMA_ID,
    staged: false,
    staged_note: null,
    provenance: [],
    data,
  });
}

interface Wire {
  readonly urls: string[];
  readonly transport: HttpTransport;
}

/** A real `HttpTransport` over a scripted `fetch`, so the CONTRACT is exercised too. */
function wire(respond: (url: string) => { status: number; body: string }): Wire {
  const urls: string[] = [];
  const fetchImpl: typeof fetch = (input) => {
    // Narrowed rather than stringified: `RequestInfo` includes `Request`, whose default
    // stringification is `[object Object]`, and a probe that recorded that would assert
    // nothing about which URL was asked for.
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    urls.push(url);
    const { status, body } = respond(url);
    return Promise.resolve(new Response(body, { status }));
  };
  return {
    urls,
    transport: new HttpTransport({ baseUrl: BASE, registry: contractRegistry(), fetchImpl }),
  };
}

function serving(data: unknown): Wire {
  return wire(() => ({ status: 200, body: envelopeFor(data) }));
}

const ADDRESS: SubjectAddressShape = {
  noun: 'permit',
  member: 'permit_id',
  subjectKey: 'permit',
  example: '#/gate?permit=<uuid>',
};

/** A resolved index naming one permit and nothing else. */
function resolved(
  permitId: string | null,
  absent: readonly { subject: string; relation: string; reason: string }[] = [],
): SubjectIndex {
  return {
    status: 'resolved',
    subjects: {
      permitId,
      crId: null,
      checkId: null,
      receiptId: null,
      clauseUuid: null,
      commitId: null,
      runId: null,
      lessonId: null,
      siteCode: null,
      siteId: null,
      absent,
    },
  };
}

afterEach(() => {
  resetDemoSubjects();
});

// ── The read ───────────────────────────────────────────────────────────────

describe('resolveDemoSubjects', () => {
  it('asks GET /v1/demo/subjects and returns what the kernel named', async () => {
    const data = fullIndex();
    const { urls, transport } = serving(data);

    const outcome = await resolveDemoSubjects(transport);

    expect(urls).toEqual([`${BASE}/v1/demo/subjects`]);
    expect(outcome.status).toBe('resolved');
    if (outcome.status !== 'resolved') return;
    expect(outcome.subjects.permitId).toBe(data.permit_id);
    expect(outcome.subjects.siteCode).toBe(data.site_code);
    expect(outcome.subjects.clauseUuid).toBe(data.clause_uuid);
    expect(outcome.subjects.commitId).toBe(data.commit_id);
    expect(outcome.subjects.lessonId).toBe(data.lesson_id);
  });

  it('performs ONE exchange however many surfaces ask', async () => {
    // Five surfaces mount on one navigation. A read per surface would be five requests
    // for one answer, and — when the route is absent — five 404s behind a screen that
    // merely looks blank.
    const { urls, transport } = serving(fullIndex());

    const [a, b, c] = await Promise.all([
      resolveDemoSubjects(transport),
      resolveDemoSubjects(transport),
      resolveDemoSubjects(transport),
    ]);
    await resolveDemoSubjects(transport);

    expect(urls).toHaveLength(1);
    expect(a).toBe(b);
    expect(b).toBe(c);
  });

  it('remembers a failure rather than re-asking, and never rejects', async () => {
    // The memo holds a promise every future caller awaits. A rejected one would become an
    // unhandled rejection the first time a surface mounted without a `.catch`, and a
    // retried one would turn an absent route into a request storm.
    const { urls, transport } = wire(() => ({ status: 404, body: 'Not Found' }));

    const first = await resolveDemoSubjects(transport);
    const second = await resolveDemoSubjects(transport);

    expect(urls).toHaveLength(1);
    expect(first).toBe(second);
    expect(first.status).toBe('unavailable');
    if (first.status !== 'unavailable') return;
    expect(first.failure).toBe('status');
    expect(first.detail).toContain('404');
  });

  it('keeps one deployment’s answer out of another transport’s cache', async () => {
    const live = serving(fullIndex());
    const other = serving(fullIndex());

    const a = await resolveDemoSubjects(live.transport);
    const b = await resolveDemoSubjects(other.transport);

    expect(a.status).toBe('resolved');
    expect(b.status).toBe('resolved');
    if (a.status !== 'resolved' || b.status !== 'resolved') return;
    expect(a.subjects.permitId).not.toBe(b.subjects.permitId);
    expect(live.urls).toHaveLength(1);
    expect(other.urls).toHaveLength(1);
  });

  it('refuses a payload the contract does not admit, instead of rendering it', () => {
    // The whole mechanism turns on the kernel naming subjects. A body that satisfies no
    // contract is exactly what a wrong deployment, a proxy error page, or a tampered
    // frame produces, and the console must report it rather than address whatever it can
    // pick out of the JSON.
    const { transport } = serving({ permit_id: 'not a uuid', site_code: null });

    return resolveDemoSubjects(transport).then((outcome) => {
      expect(outcome.status).toBe('unavailable');
      if (outcome.status !== 'unavailable') return;
      expect(outcome.failure).toBe('contract');
      expect(outcome.detail).toContain(SCHEMA_ID);
    });
  });

  it('carries a null member through as an absence, not as a value', async () => {
    const data = { ...fullIndex(), lesson_id: null };
    const { transport } = serving(data);

    const outcome = await resolveDemoSubjects(transport);

    expect(outcome.status).toBe('resolved');
    if (outcome.status !== 'resolved') return;
    expect(outcome.subjects.lessonId).toBeNull();
    expect(outcome.subjects.permitId).toBe(data.permit_id);
  });

  it('carries the emitter’s own reason for an absence through to the surfaces', async () => {
    // The contract calls `reason` the one member the database did not produce — prose,
    // because there is no row to speak for itself. The console quotes it; it does not
    // paraphrase it and it does not replace it with a friendlier sentence of its own.
    const reason = 'mainline.event holds no row anchored on the chosen permit’s precursor.';
    const { transport } = serving({
      ...fullIndex(),
      lesson_id: null,
      absent: [{ subject: 'event', relation: 'mainline.event', reason }],
    });

    const outcome = await resolveDemoSubjects(transport);

    expect(outcome.status).toBe('resolved');
    if (outcome.status !== 'resolved') return;
    expect(outcome.subjects.absent).toEqual([
      { subject: 'event', relation: 'mainline.event', reason },
    ]);
  });
});

// ── Precedence ─────────────────────────────────────────────────────────────

describe('addressSubject', () => {
  it('lets an explicit address win over the index', () => {
    const typed = anId();
    const seeded = anId();
    const addressed = addressSubject(typed, resolved(seeded), (s) => s.permitId);
    expect(addressed).toEqual({ value: typed, source: 'address' });
  });

  it('lets an explicit address win while the index is still in flight', () => {
    // A reader who typed an identifier is not made to wait for a read they did not ask
    // for, and is not shown a "no subject" panel in the meantime.
    const typed = anId();
    const addressed = addressSubject(typed, { status: 'resolving' }, (s) => s.permitId);
    expect(addressed).toEqual({ value: typed, source: 'address' });
  });

  it('lets an explicit address win even when the index failed', () => {
    const typed = anId();
    const addressed = addressSubject(
      typed,
      { status: 'unavailable', failure: 'status', detail: 'HTTP 404' },
      (s) => s.permitId,
    );
    expect(addressed).toEqual({ value: typed, source: 'address' });
  });

  it('falls back to the index, and says that is where the value came from', () => {
    const seeded = anId();
    const addressed = addressSubject(null, resolved(seeded), (s) => s.permitId);
    expect(addressed).toEqual({ value: seeded, source: 'index' });
  });

  it('treats an empty query parameter as no address at all', () => {
    const seeded = anId();
    expect(addressSubject('', resolved(seeded), (s) => s.permitId)).toEqual({
      value: seeded,
      source: 'index',
    });
  });

  it('yields nothing — never a fallback — when the index named nothing', () => {
    for (const index of [
      { status: 'no_source' } as const,
      { status: 'resolving' } as const,
      { status: 'unavailable', failure: 'status', detail: 'HTTP 404' } as const,
      resolved(null),
    ]) {
      expect(addressSubject(null, index, (s) => s.permitId)).toEqual({
        value: null,
        source: null,
      });
    }
  });
});

// ── What the surfaces say when they have no subject ────────────────────────

describe('subjectAbsence', () => {
  it('names the route, the classification and the verbatim report when the read failed', () => {
    const absence = subjectAbsence(
      { status: 'unavailable', failure: 'status', detail: 'HTTP 404; body carries no envelope' },
      ADDRESS,
    );
    const prose = absence.paragraphs.join(' ');

    expect(prose).toContain(DEMO_SUBJECTS_ROUTE);
    expect(prose).toContain('"status"');
    expect(absence.detail).toBe('HTTP 404; body carries no envelope');
    expect(absence.example).toBe(ADDRESS.example);
  });

  it('distinguishes "nobody gave this console a source" from "the read failed"', () => {
    const noSource = subjectAbsence({ status: 'no_source' }, ADDRESS);
    const failed = subjectAbsence(
      { status: 'unavailable', failure: 'network', detail: 'TypeError: fetch failed' },
      ADDRESS,
    );
    expect(noSource.paragraphs.join(' ')).toContain('No transport has been composed');
    expect(noSource.detail).toBeNull();
    expect(failed.paragraphs.join(' ')).toContain('did not answer');
  });

  it('says the index answered and named nothing, when that is what happened', () => {
    const absence = subjectAbsence(resolved(null), ADDRESS);
    const prose = absence.paragraphs.join(' ');
    expect(prose).toContain('"permit_id" member came back null');
    expect(prose).toContain('will not substitute');
  });

  it('quotes the emitter’s reason verbatim, and attributes it to the emitter', () => {
    // Not paraphrased and not replaced. The contract calls this member prose written
    // because there is no row to speak for itself; the console’s job is to carry it,
    // and to make clear whose sentence it is.
    const reason = 'mainline.permit holds no row for the chosen site.';
    const absence = subjectAbsence(
      resolved(null, [{ subject: 'permit', relation: 'mainline.permit', reason }]),
      ADDRESS,
    );
    const prose = absence.paragraphs.join(' ');
    expect(prose).toContain(reason);
    expect(prose).toContain('rather than ours');
    expect(prose).toContain('mainline.permit');
  });

  it('says nothing extra when the emitter offered no reason', () => {
    const absence = subjectAbsence(resolved(null), ADDRESS);
    expect(absence.paragraphs.join(' ')).not.toContain('rather than ours');
  });

  it('keeps the console-does-not-guess principle in every branch, and offers the override', () => {
    const branches: SubjectIndex[] = [
      { status: 'no_source' },
      { status: 'resolving' },
      { status: 'unavailable', failure: 'status', detail: 'HTTP 404' },
      resolved(null),
    ];
    for (const index of branches) {
      const absence = subjectAbsence(index, ADDRESS);
      expect(absence.paragraphs[0], index.status).toContain('does not guess which permit');
      expect(absence.override, index.status).toContain('still wins');
      expect(absence.example, index.status).toBe('#/gate?permit=<uuid>');
    }
  });
});

// ── The rule, turned on the source tree ────────────────────────────────────

/**
 * Every file this repair touched, plus the two it removed identifiers from.
 *
 * Written out rather than globbed. A glob would silently stop covering a file that was
 * renamed, and the failure mode this asserts against — a constant creeping back in — is
 * exactly the one nobody notices.
 */
const REPAIRED = [
  'src/data/demo-subjects.ts',
  'src/data/resources.ts',
  'src/features/gate/GateSurfaceRoot.tsx',
  'src/features/custody/CustodyRoot.tsx',
  'src/features/diff/ClauseDiffScreen.tsx',
  'src/features/propagation/PropagationSurfaceRoot.tsx',
  'src/features/silence/SilenceSurfaceRoot.tsx',
];

const UUID_ANYWHERE = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/;

describe('no console source file names a row', () => {
  it('carries no UUID literal, in code or in a comment', async () => {
    const fs = await nodeFs();
    for (const file of REPAIRED) {
      const source = fs.readFileSync(file, 'utf8');
      const found = UUID_ANYWHERE.exec(source);
      expect(
        found?.[0] ?? null,
        `${file} contains the identifier ${found?.[0] ?? ''}. An identifier in a console ` +
          'file is a claim about a row this console did not write; ask the kernel for it ' +
          'instead (src/data/demo-subjects.ts).',
      ).toBeNull();
    }
  });

  it('carries none of the three identifiers that answered 404 on the live URL', async () => {
    const fs = await nodeFs();
    // Spelled in halves so that this assertion is not itself a place a reader could copy a
    // working identifier out of, and so that grepping the tree for the dead ids finds only
    // the prose that explains them.
    const dead = ['BLK' + '-07', '018f3a30' + '-2200', '5f916282'];
    for (const file of REPAIRED) {
      const source = fs.readFileSync(file, 'utf8');
      for (const id of dead) {
        expect(source.includes(id), `${file} still names ${id}`).toBe(false);
      }
    }
  });

  it('leaves no DEFAULT_SITE_CODE, DEMO_CLAUSE or DEMO_COMMIT to import', async () => {
    const fs = await nodeFs();
    for (const file of REPAIRED) {
      const source = fs.readFileSync(file, 'utf8');
      for (const name of ['DEMO_CLAUSE', 'DEMO_COMMIT']) {
        expect(source.includes(name), `${file} still declares or imports ${name}`).toBe(false);
      }
    }
    // `DEFAULT_SITE_CODE` is deleted from `CustodyScreen.tsx` by the custody worker; what
    // is asserted here is the seam this worker owns — the root no longer reaches for it.
    const root = fs.readFileSync('src/features/custody/CustodyRoot.tsx', 'utf8');
    expect(root.includes('DEFAULT_SITE_CODE')).toBe(false);
  });
});
