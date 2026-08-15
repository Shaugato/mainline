// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ON-RAMP, AND THE TWO THINGS IT IS NOT ALLOWED TO BECOME.
 *
 * The founder's finding on 2026-08-15 was that the console opens at a specialist's reading
 * level with no way in. The fix is an on-ramp, and an on-ramp has exactly two failure
 * modes, both of which are worse than the defect:
 *
 *   1. **It softens something.** A plain sentence that replaces a precise one is not an
 *      on-ramp, it is a retreat. So the disclosure's body is asserted to be
 *      `SurfaceEntry.promise` CHARACTER FOR CHARACTER, and the deck is asserted to contain
 *      no sentence that could be mistaken for the precise version of anything.
 *   2. **It ships an identifier.** Every door on the overview is a deep link, and the
 *      cheapest way to make a deep link work is to paste the UUID that works today. That is
 *      exactly how `BLK-07` reached the live URL (`docs/leads/screens-work-plan.md` §2.2),
 *      so the bytes of every file this worker owns are read back and searched for one.
 *
 * The rendering assertions are jsdom, and jsdom is not the proof. The proof for this wave
 * is a build served through `mainline_demo_api.static_site` and read back out of a real
 * browser; this file is the ratchet that keeps it true afterwards.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { DISCLOSURE_STORAGE_KEY, SurfaceHost } from '../../../src/app/SurfaceHost';
import { DECLARED_SURFACES, buildRegistry, type SurfaceEntry } from '../../../src/app/surfaces';
import { FALLBACK_LEDE, SURFACE_LEDES, ledeFor } from '../../../src/copy/onramp';
import { resetDemoSubjects } from '../../../src/data/demo-subjects';
import {
  TransportError,
  type Exchange,
  type MainlineTransport,
  type TransportDescription,
} from '../../../src/data/transport';
import { GateTransportContext } from '../../../src/features/gate/transport-context';
import { OverviewScreen } from '../../../src/features/overview/OverviewScreen';

// ── Fixtures ───────────────────────────────────────────────────────────────

/**
 * Subjects, as opaque strings.
 *
 * They are deliberately NOT uuid-shaped: `demo-subjects.ts` treats every one of these as an
 * opaque identifier the kernel produced, nothing in the console parses one, and the
 * no-identifier assertion at the bottom of this file has to be able to run over this file
 * too.
 */
const SEEDED = Object.freeze({
  permit_id: 'permit-named-by-the-kernel',
  cr_id: 'change-request-named-by-the-kernel',
  check_id: 'check-named-by-the-kernel',
  receipt_id: 'receipt-named-by-the-kernel',
  clause_uuid: 'clause-named-by-the-kernel',
  commit_id: 'commit-named-by-the-kernel',
  run_id: 'run-named-by-the-kernel',
  lesson_id: 'lesson-named-by-the-kernel',
  site_code: 'site-code-named-by-the-kernel',
  site_id: 'site-named-by-the-kernel',
  absent: [],
});

function describeLive(): TransportDescription {
  return { mode: 'live', source: 'scripted', bundleDigestPrefix: null, staged: false, stagedNote: null };
}

function transportAnswering(data: unknown): MainlineTransport {
  return {
    describe: describeLive,
    exchange: <T,>(): Promise<Exchange<T>> =>
      Promise.resolve({
        request: { resource: 'demo_subjects', key: 'GET /v1/demo/subjects', method: 'GET', path: '/v1/demo/subjects' },
        envelope: {
          envelope_version: 1,
          resource: 'demo_subjects',
          schema_id: 'https://spec.trappoint.org/1.0/wire/subjects.schema.json',
          staged: false,
          provenance: [],
          data,
        },
        data,
        httpStatus: 200,
        clockSkewMs: null,
        mode: 'live',
      } as unknown as Exchange<T>),
  };
}

function transportRefusingToAnswer(): MainlineTransport {
  return {
    describe: describeLive,
    exchange: <T,>(): Promise<Exchange<T>> =>
      Promise.reject(new TransportError('status', 'GET /v1/demo/subjects', 'HTTP 503 — no body')),
  };
}

function entryFor(id: string, load: SurfaceEntry['load']): SurfaceEntry {
  const entry = buildRegistry({}).find((candidate) => candidate.id === id);
  if (entry === undefined) throw new Error(`no declared surface ${id}`);
  return { ...entry, status: load === null ? 'declared-missing' : 'loadable', load };
}

beforeEach(() => {
  window.sessionStorage.clear();
  resetDemoSubjects();
});

// ── The deck ───────────────────────────────────────────────────────────────

describe('the copy deck', () => {
  it('carries a lede for every surface the console promises', () => {
    const missing = DECLARED_SURFACES.filter((surface) => SURFACE_LEDES[surface.id] === undefined).map(
      (surface) => surface.id,
    );
    expect(
      missing,
      'these surfaces are promised and have no plain-language note. A screen that reaches a ' +
        'reader with no way in is the defect this deck exists to end; add the entry to ' +
        'src/copy/onramp.ts.',
    ).toEqual([]);
  });

  it('says two or three sentences and no more — an on-ramp nobody finishes is not one', () => {
    for (const surface of DECLARED_SURFACES) {
      const lede = ledeFor(surface.id);
      expect(lede.sentences.length, `${surface.id}: sentence count`).toBeGreaterThanOrEqual(2);
      expect(lede.sentences.length, `${surface.id}: sentence count`).toBeLessThanOrEqual(3);
      expect(lede.kicker.trim(), `${surface.id}: kicker`).not.toBe('');
      for (const sentence of lede.sentences) {
        expect(sentence.trim().endsWith('.'), `${surface.id}: "${sentence}" is not a sentence`).toBe(true);
      }
    }
  });

  it('uses none of the vocabulary the reader has not been given yet', () => {
    // The words below are all CORRECT and all of them stay on the screens that use them.
    // What this asserts is only that none of them is the FIRST thing a reader meets.
    const specialist =
      /\bRFC\b|\bSQLSTATE\b|\bECDSA\b|\bP-256\b|\bSHA-256\b|canonicalis|\bMCP\b|\bUUID\b|\bAPI\b|\bJSON\b|\bSQL\b|\bP0001\b|\b23514\b/i;
    for (const [id, lede] of Object.entries(SURFACE_LEDES)) {
      for (const sentence of lede.sentences) {
        expect(specialist.test(sentence), `${id}: "${sentence}" opens on specialist vocabulary`).toBe(
          false,
        );
      }
    }
  });

  it('gives an undeclared stranger a lede that reports the gap as a gap in this deck', () => {
    expect(ledeFor('fixity')).toBe(FALLBACK_LEDE);
    expect(FALLBACK_LEDE.sentences.join(' ')).toContain('copy deck');
  });
});

// ── The mount ──────────────────────────────────────────────────────────────

describe('SurfaceHost mounts the on-ramp above every outcome', () => {
  it('renders the lede above a surface that loaded, and the surface underneath it', async () => {
    const entry = entryFor('gate', () =>
      Promise.resolve({
        surface: {
          id: 'gate',
          path: '/gate',
          title: 'Gate — the refusal',
          register: 'evidence',
          order: 10,
          milestone: 'K5',
          Component: () => <p>the refusal bar</p>,
        },
      }),
    );
    render(<SurfaceHost entry={entry} />);

    const onramp = await screen.findByTestId('onramp');
    expect(onramp).toHaveAttribute('data-onramp-surface', 'gate');
    expect(await screen.findByText('the refusal bar')).toBeInTheDocument();

    // Above, not merely present: the on-ramp precedes the surface in DOM order, which is
    // reading order and tab order both.
    const position = onramp.compareDocumentPosition(screen.getByText('the refusal bar'));
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders it above a NOT-BUILT-YET card too — the reader still learns what the screen was for', async () => {
    render(<SurfaceHost entry={entryFor('ancestry', null)} />);
    const onramp = await screen.findByTestId('onramp');
    expect(within(onramp).getByTestId('onramp-kicker').textContent).toBe(
      ledeFor('ancestry').kicker,
    );
    expect(screen.getByTestId('not-built-yet')).toBeInTheDocument();
  });
});

describe('the disclosure', () => {
  const gateEntry = (): SurfaceEntry => entryFor('gate', null);

  it('is closed on a first visit', async () => {
    render(<SurfaceHost entry={gateEntry()} />);
    const disclosure = await screen.findByTestId('onramp-disclosure');
    expect((disclosure as HTMLDetailsElement).open).toBe(false);
  });

  it('reveals the promise CHARACTER FOR CHARACTER — never a summary of it', async () => {
    render(<SurfaceHost entry={gateEntry()} />);
    await userEvent.click(await screen.findByTestId('onramp-disclosure-summary'));
    const promised = DECLARED_SURFACES.find((surface) => surface.id === 'gate')?.promise;
    expect(promised).toBeDefined();
    expect(screen.getByTestId('onramp-promise').textContent).toBe(promised);
  });

  it('remembers the reader’s choice for the session, so a technical reader opens it once', async () => {
    const first = render(<SurfaceHost entry={gateEntry()} />);
    await userEvent.click(await screen.findByTestId('onramp-disclosure-summary'));
    await waitFor(() => {
      expect(window.sessionStorage.getItem(DISCLOSURE_STORAGE_KEY)).toBe('open');
    });
    first.unmount();

    // A second screen, in the same session. It opens already open.
    render(<SurfaceHost entry={entryFor('custody', null)} />);
    const disclosure = await screen.findByTestId('onramp-disclosure');
    expect((disclosure as HTMLDetailsElement).open).toBe(true);
  });

  it('survives a browser that refuses storage rather than taking the console down', async () => {
    const original = window.sessionStorage.getItem.bind(window.sessionStorage);
    Object.defineProperty(window.sessionStorage, 'getItem', {
      configurable: true,
      value: () => {
        throw new Error('storage is partitioned');
      },
    });
    try {
      render(<SurfaceHost entry={gateEntry()} />);
      const disclosure = await screen.findByTestId('onramp-disclosure');
      expect((disclosure as HTMLDetailsElement).open).toBe(false);
    } finally {
      Object.defineProperty(window.sessionStorage, 'getItem', { configurable: true, value: original });
    }
  });
});

// ── The overview surface ───────────────────────────────────────────────────

function renderOverview(transport: MainlineTransport | null): void {
  render(
    <GateTransportContext.Provider value={transport}>
      <OverviewScreen />
    </GateTransportContext.Provider>,
  );
}

describe('the overview surface', () => {
  it('opens on what the system refuses, before any case is walked', () => {
    renderOverview(transportAnswering(SEEDED));
    const surface = screen.getByTestId('overview-surface');
    expect(surface).toHaveTextContent('the merge is refused there, by a rule with a name');
    expect(surface).toHaveTextContent('Nothing on this screen is a claim about a record');
  });

  it('walks the two cases the demo actually proves, plus the silence it labels as staged', () => {
    renderOverview(transportAnswering(SEEDED));
    expect(screen.getByTestId('usecase-refusal')).toBeInTheDocument();
    expect(screen.getByTestId('usecase-forged-counter')).toBeInTheDocument();
    expect(screen.getByTestId('usecase-silence')).toHaveTextContent('STAGED');
  });

  it('addresses every door with the subject the kernel named, never with a value of its own', async () => {
    renderOverview(transportAnswering(SEEDED));
    await waitFor(() => {
      expect(screen.getAllByTestId('usecase-door')).toHaveLength(4);
    });
    const hrefs = screen.getAllByTestId('usecase-door').map((door) => door.getAttribute('href'));
    expect(hrefs).toEqual([
      `#/gate?${PERMIT_PARAM}=${SEEDED.permit_id}`,
      `#/custody?${SITE_PARAM}=${SEEDED.site_code}`,
      `#/gate?${PERMIT_PARAM}=${SEEDED.permit_id}`,
      `#/silence?${SILENCE_PERMIT_PARAM}=${SEEDED.permit_id}`,
    ]);
    expect(screen.queryAllByTestId('usecase-door-absent')).toHaveLength(0);
  });

  it('disables every door with a NAMED reason when the deployment does not answer', async () => {
    renderOverview(transportRefusingToAnswer());
    await waitFor(() => {
      expect(screen.getAllByTestId('usecase-door-absent')).toHaveLength(4);
    });
    for (const absent of screen.getAllByTestId('usecase-door-absent')) {
      expect(absent).toHaveTextContent('GET /v1/demo/subjects');
      expect(absent).toHaveTextContent('will not substitute one');
      // The transport's own report, verbatim, rather than a paraphrase of it.
      expect(absent).toHaveTextContent('HTTP 503 — no body');
    }
    expect(screen.queryAllByTestId('usecase-door')).toHaveLength(0);
  });

  it('disables a door, and quotes the emitter, when the kernel answers and holds no such row', async () => {
    renderOverview(
      transportAnswering({
        ...SEEDED,
        site_code: null,
        absent: [
          {
            subject: 'site',
            relation: 'mainline.ledger_checkpoint',
            reason: 'no checkpoint has been written for any site in this database',
          },
        ],
      }),
    );
    const absent = await screen.findByTestId('usecase-door-absent');
    expect(absent).toHaveTextContent('the “site_code” member came back null');
    expect(absent).toHaveTextContent('no checkpoint has been written for any site in this database');
    expect(absent).toHaveTextContent('mainline.ledger_checkpoint');
  });

  it('renders no door at all before the read lands, and says it is asking', async () => {
    renderOverview(transportAnswering(SEEDED));
    const absent = screen.getAllByTestId('usecase-door-absent');
    expect(absent.length).toBeGreaterThan(0);
    expect(absent[0]).toHaveTextContent('Asking GET /v1/demo/subjects');
    // Settle the in-flight read inside the test, so the state update this case exists to
    // observe is not left to land after teardown and be reported as an act() escape.
    await waitFor(() => {
      expect(screen.getAllByTestId('usecase-door').length).toBeGreaterThan(0);
    });
  });

  it('renders the console’s own absence, not a blank, when nobody composed a transport', async () => {
    renderOverview(null);
    const absent = await screen.findAllByTestId('usecase-door-absent');
    expect(absent).toHaveLength(4);
    for (const door of absent) {
      expect(door).toHaveTextContent('No transport has been composed');
      expect(door).toHaveTextContent('does not carry one written into its own source');
    }
  });
});

// ── The two things this must never become ──────────────────────────────────

/**
 * The bytes of every file this worker owns, read as TEXT.
 *
 * `query: '?raw'` so nothing is imported to satisfy the assertion — the point is the
 * characters on disk, not what they evaluate to.
 */
const OWNED: Record<string, unknown> = import.meta.glob(
  ['/src/app/SurfaceHost.tsx', '/src/copy/*.{ts,css}', '/src/features/overview/*.{tsx,css}'],
  { query: '?raw', import: 'default', eager: true },
);

/**
 * The surface roots the overview addresses — also as TEXT, and for a second reason.
 *
 * `GateSurfaceRoot`, `CustodyRoot` and `SilenceSurfaceRoot` each pull a whole screen and,
 * in custody's case, the verifier and its worker. IMPORTING three of them to read three
 * short strings made this file the slowest in the suite and pushed borderline neighbours
 * over their five-second timeout in three runs out of four — a test file that reddens other
 * people's tests by being heavy is a worse defect than the drift it was guarding against.
 * Read as text, the assertion is stronger anyway: it is about the characters both files
 * ship, not about two modules that happen to agree once they have evaluated.
 */
const ROOTS: Record<string, unknown> = import.meta.glob(
  [
    '/src/features/gate/GateSurfaceRoot.tsx',
    '/src/features/custody/CustodyRoot.tsx',
    '/src/features/silence/SilenceSurfaceRoot.tsx',
  ],
  { query: '?raw', import: 'default', eager: true },
);

/** `export const PERMIT_PARAM = 'permit';` → `permit`. */
function declaredParam(path: string, name: string): string {
  const text = ROOTS[path];
  if (typeof text !== 'string') throw new Error(`${path} was not read as text`);
  const match = new RegExp(`export const ${name} = '([^']+)';`).exec(text);
  if (match?.[1] === undefined) throw new Error(`${path} declares no ${name}`);
  return match[1];
}

const PERMIT_PARAM = declaredParam('/src/features/gate/GateSurfaceRoot.tsx', 'PERMIT_PARAM');
const SITE_PARAM = declaredParam('/src/features/custody/CustodyRoot.tsx', 'SITE_PARAM');
const SILENCE_PERMIT_PARAM = declaredParam(
  '/src/features/silence/SilenceSurfaceRoot.tsx',
  'PERMIT_PARAM',
);

describe('what the on-ramp is not allowed to carry', () => {
  it('found the files at all', () => {
    expect(Object.keys(OWNED).length).toBeGreaterThanOrEqual(6);
  });

  it('names no identifier — a UUID in a console file is BLK-07 with a luckier value', () => {
    const uuid = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i;
    const offenders: string[] = [];
    for (const [path, text] of Object.entries(OWNED)) {
      if (typeof text !== 'string') throw new Error(`${path} came back as ${typeof text}, not text`);
      const found = uuid.exec(text);
      if (found !== null) offenders.push(`${path}: ${found[0]}`);
    }
    expect(
      offenders,
      'a console file naming a row is a console asserting a fact about a database it did not ' +
        'write, and it is false the first time a deployment seeds a different history ' +
        '(docs/leads/screens-work-plan.md §2.1). Ask the kernel instead.',
    ).toEqual([]);
  });

  it('agrees with the surfaces it links to about how they are addressed', () => {
    // The overview re-declares these two strings rather than importing them, to keep three
    // feature screens out of its lazy chunk. This is the assertion that pays for that: if a
    // root renames its parameter, the overview's doors stop resolving and this goes red
    // before anybody clicks one.
    const overview = OWNED['/src/features/overview/OverviewScreen.tsx'];
    expect(typeof overview).toBe('string');
    expect(overview).toContain(`const PERMIT_PARAM = '${PERMIT_PARAM}'`);
    expect(overview).toContain(`const SITE_PARAM = '${SITE_PARAM}'`);
    // Gate and Silence both address a permit, and the overview's third door assumes it.
    expect(SILENCE_PERMIT_PARAM).toBe(PERMIT_PARAM);
  });
});
