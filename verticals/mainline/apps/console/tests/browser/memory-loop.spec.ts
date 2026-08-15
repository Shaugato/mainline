// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * W6 — `/memory.html` IN A REAL BROWSER, AGAINST A REAL KERNEL.
 *
 * `docs/demo/memory-visible-plan.md` §5 defines the panel as done when it "makes four GETs
 * and, on press, one POST, and every value on screen is Ctrl-F-able in one of those five
 * response bodies". This file is that definition, executed.
 *
 * ── THE CENTRAL ASSERTION, AND WHY IT IS EXHAUSTIVE RATHER THAN SAMPLED ──────────────
 *
 * `every visible value is present in one of the five response bodies` walks EVERY element
 * carrying `data-cell`, takes the text a viewer can read, and requires it to be a value one
 * of the five recorded responses actually carried. Not a sample of cells; not a list of
 * interesting ones. The claim this page makes is universal — *nothing on it was composed by
 * the client* — and a sampled check would leave the one composed cell unchecked.
 *
 * Four kinds of cell cannot be a plain payload scalar, and each is handled by a DECLARED
 * decomposition rather than an exemption (see `DECOMPOSITIONS`):
 *
 *   • `annot.gap.*`        R-M4 arithmetic over two columns already on screen. It is not a
 *                          stored value, it says so in its own text, and the spec asserts it
 *                          says so and carries no chip.
 *   • `meta.received_at`   R-M7.1 the client's own receipt clock; asserted to name itself.
 *   • `retrieve.match.*`   R-M5.2 a comparison between two responses; its OPERANDS are
 *                          checked against the bodies, the words `match` / `DIFFERS` are not.
 *   • `verify.leaf.*`      D6 re-derivation in this browser; every 64-hex token in it must be
 *                          a hash the ledger response carried.
 *
 * Everything else — every SQLSTATE, constraint, count, timestamp, digest, statement and
 * verdict — must appear verbatim. The comparison is against a corpus built by parsing each
 * body and rendering every scalar the way `memory-loop.js`'s own `textOf` renders it, with a
 * raw-substring fallback. That is what "Ctrl-F-able" means for a judge reading a body in the
 * Network panel with its escapes decoded: `statement_refs[].text` carries real newlines once
 * parsed, and a raw-bytes-only comparison would fail on the one cell the plan cares most
 * about.
 *
 * ── FOUR GETs, OR FIVE? THE COUNT IS 4 + 1 AND THE SPEC SAYS SO OUT LOUD ─────────────
 *
 * Plan §5 says four GETs. The page makes FIVE: `/v1/demo/subjects` first, then the four reads
 * the columns are filled from. That is not a discrepancy to paper over — it is R-M8, which
 * forbids any identifier literal in the page and requires exactly this addressing call. So
 * this spec asserts the shape R-M8 mandates: exactly one addressing GET, exactly four data
 * GETs, no other request to `/v1/*`, and no POST until the button is pressed. The five bodies
 * the central assertion draws its corpus from are the four data reads plus the POST —
 * `subjects` is deliberately EXCLUDED from the corpus, so a value that could only have come
 * from the addressing payload fails the test rather than passing it.
 *
 * ── WHAT THIS FILE PUTS INTO THE PAGE, PRECISELY ─────────────────────────────────────
 *
 * One observer, and one fault injection, and nothing else.
 *
 * The observer wraps `window.setTimeout` / `window.setInterval` in functions that record
 * `{kind, delay, generatedAt}` — where `generatedAt` is read out of the page's own
 * `meta.generated_at` cell AT THE MOMENT THE TIMER IS SCHEDULED — and then call the original
 * with the original arguments and return its return value. It changes no data, no timing and
 * no rendering path. It exists to prove R-M7.3 at runtime and not only in the source: every
 * timer the page schedules is scheduled AFTER the response had been parsed and painted,
 * because the value it snapshots is the payload's own `generated_at`.
 *
 * The fault injection is confined to one test. `a failed read renders its status and its path`
 * stubs ONE GET with a 503 through `page.route`, because R-M10 cannot be observed without a
 * failure and breaking the real kernel to make one would be a worse idea. Every other test in
 * this file asserts on bytes that came off a real socket, and each asserts that the response
 * carried `x-mainline-emulator`, which makes a run pointed at the deployed Function URL fail
 * loudly instead of load-testing the URL a judge is about to open.
 *
 * ── RUNNING IT ───────────────────────────────────────────────────────────────────────
 *
 *   pnpm run build            # dist/memory.html and its three siblings must exist
 *   pnpm run test:browser     # playwright.config.ts starts scripts/deploy/local_furl.py
 *
 * NOTE FOR WHOEVER OWNS `playwright.config.ts`: its `testMatch` is `/operator-.*\.spec\.ts$/`,
 * which collects W7's operator specs and NOT this file. That config landed after
 * `memory-visible-plan.md` was written, and this file is not mine to edit. One character class
 * collects both suites:
 *
 *     testMatch: /(operator|memory)-.*\.spec\.ts$/
 *
 * Until that lands, this file runs with an explicit config or with
 * `MAINLINE_MEMORY_BASE_URL` pointed at a running emulator. It is reported rather than worked
 * around, because a spec nobody collects is a spec nobody runs.
 */

import { expect, test } from '@playwright/test';
import type { Page, Request, Response } from '@playwright/test';

// ── Where the panel lives ──────────────────────────────────────────────────────────────

/** The page, served out of `dist/` by whatever host the config points `baseURL` at. */
const MEMORY_PAGE = '/memory.html';

/** R-M7.4's disarm: all four beats filled the instant the one response resolves. */
const MEMORY_PAGE_INSTANT = '/memory.html?reveal=off';

/**
 * An emulator this spec was pointed at by hand. `playwright.config.ts` supplies `baseURL`
 * when it collects this file; this covers the interim in which it does not.
 */
const EXPLICIT_BASE = process.env['MAINLINE_MEMORY_BASE_URL'] ?? '';

function pageUrl(path: string): string {
  return EXPLICIT_BASE === '' ? path : `${EXPLICIT_BASE.replace(/\/+$/, '')}${path}`;
}

// ── The five bodies, and the one that is addressing rather than content ────────────────

const SUBJECTS_PATH = '/v1/demo/subjects';
const GATE_RUN_PATH = '/v1/demo/gate-run';

/** The four reads the three columns are filled from. Order-independent; matched by shape. */
const DATA_READS = {
  checks: /^\/v1\/permits\/[^/]+\/blocking-checks$/,
  ancestry: /^\/v1\/clauses\/[^/]+\/ancestry$/,
  recall: /^\/v1\/recall-runs\/[^/]+$/,
  ledger: /^\/v1\/ledger$/,
} as const;

type ReadName = keyof typeof DATA_READS;

/**
 * The route that answers `423 demo_subject_write_protected` on the seeded subject. The page
 * must never call it: rendering a 423 in a refusal banner is a fabricated exhibit, and
 * `r3-operator` flagged it independently of `r4-story` measuring the status.
 */
const MERGE_ROUTE = /\/v1\/permits\/[^/]+\/merge$/;

/** The header `scripts/deploy/local_furl.py` stamps on every response it serves. */
const EMULATOR_HEADER = 'x-mainline-emulator';

/** R-M3: the envelope's five, and no sixth. The page never invents one. */
const CHIP_VOCABULARY = new Set(['db:column', 'db:constraint', 'recomputed', 'staged', 'derived']);

// ── What came off the wire ─────────────────────────────────────────────────────────────

interface Recorded {
  readonly method: string;
  readonly path: string;
  readonly search: string;
  readonly status: number;
  readonly emulator: string | null;
  readonly text: string;
}

interface Wire {
  /** Every request to `/v1/*` the page made, in order, as `METHOD path`. */
  readonly requests: string[];
  /** Every `/v1/*` response body, parsed or not. */
  readonly responses: Recorded[];
  /** Resolves when every body this recorder started reading has been read. */
  settle: () => Promise<void>;
}

function recordWire(page: Page): Wire {
  const requests: string[] = [];
  const responses: Recorded[] = [];
  const reading: Promise<void>[] = [];

  page.on('request', (request: Request) => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/v1/')) return;
    requests.push(`${request.method()} ${url.pathname}`);
  });

  page.on('response', (response: Response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith('/v1/')) return;
    reading.push(
      (async () => {
        let text = '';
        try {
          text = await response.text();
        } catch {
          text = '';
        }
        responses.push({
          method: response.request().method(),
          path: url.pathname,
          search: url.search,
          status: response.status(),
          emulator: response.headers()[EMULATOR_HEADER] ?? null,
          text,
        });
      })(),
    );
  });

  return {
    requests,
    responses,
    settle: async () => {
      await Promise.all(reading);
    },
  };
}

function readsIn(wire: Wire): Map<ReadName, Recorded> {
  const found = new Map<ReadName, Recorded>();
  for (const recorded of wire.responses) {
    if (recorded.method !== 'GET') continue;
    for (const [name, shape] of Object.entries(DATA_READS) as [ReadName, RegExp][]) {
      if (shape.test(recorded.path)) found.set(name, recorded);
    }
  }
  return found;
}

function gateRunIn(wire: Wire): Recorded {
  const found = wire.responses.find((r) => r.method === 'POST' && r.path === GATE_RUN_PATH);
  if (found === undefined) {
    throw new Error('the press produced no POST /v1/demo/gate-run to assert against');
  }
  return found;
}

/** One of the four reads, or a failure that names which one did not answer. */
function mustRead(reads: Map<ReadName, Recorded>, name: ReadName): Recorded {
  const found = reads.get(name);
  if (found === undefined) {
    throw new Error(`the ${name} read did not answer; there is nothing to assert against`);
  }
  return found;
}

// ── The corpus: every scalar the five bodies carried, rendered as the page renders it ──

/**
 * `memory-loop.js`'s `textOf`, reimplemented here deliberately rather than imported.
 *
 * Importing the page's own renderer would make this test agree with the page by construction:
 * if `textOf` started lying, the corpus would learn the same lie. Eleven lines of duplication
 * buy an independent witness, and the duplication is stated here so nobody "fixes" it.
 */
function asRendered(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  return JSON.stringify(value);
}

function collectScalars(node: unknown, into: Set<string>): void {
  if (node === null || typeof node !== 'object') {
    into.add(asRendered(node));
    return;
  }
  if (Array.isArray(node)) {
    for (const item of node) collectScalars(item, into);
    return;
  }
  for (const item of Object.values(node)) collectScalars(item, into);
}

interface Corpus {
  /** Every scalar in the five bodies, as text. */
  readonly scalars: Set<string>;
  /** The raw bodies, for the substring fallback. */
  readonly raw: string[];
  /** Names the bodies that fed it, so a failure message says what was searched. */
  readonly sources: string[];
}

function buildCorpus(bodies: Recorded[]): Corpus {
  const scalars = new Set<string>();
  const raw: string[] = [];
  const sources: string[] = [];
  for (const body of bodies) {
    raw.push(body.text);
    sources.push(`${body.method} ${body.path}${body.search} (${body.text.length} B)`);
    try {
      collectScalars(JSON.parse(body.text), scalars);
    } catch {
      // A body that did not parse still contributes its bytes to the substring fallback.
    }
  }
  return { scalars, raw, sources };
}

function corpusHas(corpus: Corpus, token: string): boolean {
  const trimmed = token.trim();
  if (trimmed === '') return true;
  if (corpus.scalars.has(trimmed)) return true;
  return corpus.raw.some((body) => body.includes(trimmed));
}

// ── What a viewer can read ─────────────────────────────────────────────────────────────

interface Cell {
  readonly id: string;
  /** The cell's text with any chip removed — the value itself. */
  readonly text: string;
  readonly chip: string | null;
  readonly filled: boolean;
  readonly error: boolean;
  readonly state: string | null;
}

async function readCells(page: Page): Promise<Cell[]> {
  return page.$$eval('[data-cell]', (elements) =>
    elements.map((element) => {
      const clone = element.cloneNode(true) as HTMLElement;
      for (const chip of clone.querySelectorAll('.chip, .mem-chip')) chip.remove();
      // Both clients declare the chip's KIND in an attribute — `memory-loop.js` as
      // `data-chip`, `memory-verify.js` as `data-kind` — and both wrap it in spans carrying
      // the spoken form and the pointer. The attribute is the vocabulary word; the text is
      // the rendering of it.
      const chip = element.querySelector('.chip, .mem-chip');
      const chipKind =
        chip === null
          ? null
          : (chip.getAttribute('data-chip') ?? chip.getAttribute('data-kind') ?? '').trim();
      return {
        id: element.getAttribute('data-cell') ?? '',
        text: clone.textContent.trim(),
        chip: chipKind,
        filled: element.getAttribute('data-filled') === 'true',
        error: element.getAttribute('data-error') === 'true',
        state: element.getAttribute('data-state'),
      };
    }),
  );
}

function cellById(cells: Cell[], id: string): Cell {
  const found = cells.find((cell) => cell.id === id);
  if (found === undefined) {
    throw new Error(`the page rendered no cell with data-cell="${id}"`);
  }
  return found;
}

// ── The declared decompositions ────────────────────────────────────────────────────────

/**
 * A cell whose text is not a bare payload scalar, and the exact account of what it is.
 *
 * `tokens` returns the strings that MUST be in one of the five bodies. `must` is what the
 * cell has to say about itself, so a composed cell cannot masquerade as a column value.
 * `chipAllowed: false` enforces R-M3/R-M4: a value this browser composed wears no chip,
 * because there is no identifier in the vocabulary that would make it a column.
 */
interface Decomposition {
  readonly name: string;
  readonly matches: RegExp;
  readonly tokens: (text: string) => string[];
  readonly must: RegExp | null;
  readonly chipAllowed: boolean;
}

/** R-M4's exact words, as `memory-loop.js` writes them. */
const GAP_NOTE = /arithmetic over the two columns above; not a stored value$/;

const DECOMPOSITIONS: readonly Decomposition[] = [
  {
    name: 'R-M4 gap annotation',
    matches: /^(?:annot|store|retrieve)\.gap\./,
    tokens: () => [],
    must: GAP_NOTE,
    chipAllowed: false,
  },
  {
    name: 'R-M7.1 client receipt clock',
    matches: /^meta\.received_at$/,
    tokens: () => [],
    must: /client clock$/,
    chipAllowed: false,
  },
  {
    name: 'R-M5.2 equality across two responses',
    matches: /^retrieve\.match\./,
    tokens: (text) =>
      text
        .replace(/^(?:match|DIFFERS)\s*·\s*/u, '')
        .split(/[=≠]/u)
        .map((part) => part.trim())
        .filter((part) => part !== ''),
    must: /^(?:match|DIFFERS)\s*·/u,
    chipAllowed: false,
  },
  {
    name: 'D6 leaf hash re-derived in this browser',
    matches: /^verify\./,
    tokens: (text) => text.match(/[0-9a-f]{64}/g) ?? [],
    must: /recomputed in this browser/,
    chipAllowed: true,
  },
  {
    name: "the payload's own unit, named beside its number",
    matches: /\.elapsed_ms$/,
    tokens: (text) => [text.replace(/\s*ms$/, '')],
    must: /\sms$/,
    chipAllowed: true,
  },
  {
    name: 'R-M10 every string in failures[], or the fact that there are none',
    matches: /^act\.failures$/,
    tokens: (text) =>
      /^failures\[\] is empty \(0\)$/.test(text)
        ? []
        : text
            .split(/\n/)
            .map((line) => line.replace(/^\s*\d+\.\s*/, '').trim())
            .filter((line) => line !== ''),
    must: null,
    chipAllowed: false,
  },
];

/** The cells whose text is checked verbatim get this. */
const VERBATIM: Decomposition = {
  name: 'a value the response carried, verbatim',
  matches: /.*/,
  tokens: (text) => [text],
  must: null,
  chipAllowed: true,
};

function decompositionFor(id: string): Decomposition {
  return DECOMPOSITIONS.find((rule) => rule.matches.test(id)) ?? VERBATIM;
}

/**
 * The cells that are allowed to contribute NO token to the corpus check, enumerated by id.
 *
 * This list is the whole of the exemption surface and the test asserts it exactly: a new
 * composed cell cannot quietly join it, because a cell outside this list that yields no
 * token fails, and a cell inside it that stops existing fails too.
 */
const COMPOSED_CELL_IDS = [
  'annot.gap.event_to_check',
  'annot.gap.recall_to_check',
  'meta.received_at',
  'act.failures',
] as const;

// ── The timer observer ─────────────────────────────────────────────────────────────────

interface TimerCall {
  readonly kind: string;
  readonly delay: number;
  /** `meta.generated_at`'s text at the instant the timer was scheduled. */
  readonly generatedAt: string;
}

declare global {
  // A global needs `var`: `let` here declares a module binding the page never sees.
  var __memoryTimers: TimerCall[] | undefined;
}

async function observeTimers(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const calls: { kind: string; delay: number; generatedAt: string }[] = [];
    globalThis.__memoryTimers = calls;
    const note = (kind: string, delay: number): void => {
      const cell = document.querySelector('[data-cell="meta.generated_at"]');
      calls.push({ kind, delay, generatedAt: (cell?.textContent ?? '').trim() });
    };
    const realTimeout = window.setTimeout.bind(window);
    const realInterval = window.setInterval.bind(window);
    window.setTimeout = ((handler: TimerHandler, delay?: number, ...args: unknown[]) => {
      note('setTimeout', delay ?? 0);
      return realTimeout(handler, delay, ...args);
    }) as typeof window.setTimeout;
    window.setInterval = ((handler: TimerHandler, delay?: number, ...args: unknown[]) => {
      note('setInterval', delay ?? 0);
      return realInterval(handler, delay, ...args);
    }) as typeof window.setInterval;
  });
}

async function timersSoFar(page: Page): Promise<TimerCall[]> {
  return page.evaluate(() => (globalThis.__memoryTimers ?? []).slice());
}

// ── Waiting for the page, without waiting on a clock ───────────────────────────────────

/** The last cell the four reads fill, and the last one the recomputation fills. */
async function waitForReads(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    const recall = document.querySelector('[data-cell="retrieve.recall.n_deduped"]');
    const verify = document.querySelector('[data-cell="verify.leaf.closure"]');
    return (
      recall?.getAttribute('data-filled') === 'true' &&
      verify?.getAttribute('data-filled') === 'true'
    );
  });
}

/** The cells the client paints LAST, after every beat has landed. */
async function waitForActColumn(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    const verdict = document.querySelector('[data-cell="act.verdict"]');
    const elapsed = document.querySelector('[data-cell="meta.elapsed_ms"]');
    return (
      verdict?.getAttribute('data-filled') === 'true' &&
      (elapsed?.textContent ?? '').trim() !== ''
    );
  });
}

async function pressTheGate(page: Page): Promise<void> {
  await page.click('[data-action="gate-run"]');
  await waitForActColumn(page);
}

function expectEmulator(wire: Wire): void {
  for (const recorded of wire.responses) {
    expect(
      recorded.emulator,
      `${recorded.method} ${recorded.path} carried no ${EMULATOR_HEADER} header. This suite ` +
        'runs against scripts/deploy/local_furl.py and never against the deployed Function ' +
        'URL, which is one shared public row a judge is about to open.',
    ).not.toBeNull();
  }
}

// ── The tests ──────────────────────────────────────────────────────────────────────────

test.describe('/memory.html — the store, retrieve, act loop', () => {
  test('one addressing GET, four data GETs, and exactly one POST on press', async ({ page }) => {
    const wire = recordWire(page);
    await page.goto(pageUrl(MEMORY_PAGE));
    await waitForReads(page);
    await wire.settle();

    // Before the press: the addressing call R-M8 requires, the four reads the columns are
    // filled from, and nothing else. No POST of any kind has been sent.
    const before = [...wire.requests];
    const subjectsBefore = before.filter((line) => line === `GET ${SUBJECTS_PATH}`);
    const dataBefore = before.filter((line) =>
      Object.values(DATA_READS).some((shape) => shape.test(line.replace(/^GET /, ''))),
    );
    expect(subjectsBefore, 'R-M8: the page addresses every subject from one GET').toHaveLength(1);
    expect(dataBefore, 'plan §5: four reads fill the STORE and RETRIEVE columns').toHaveLength(4);
    expect(
      before.filter((line) => !line.startsWith('GET ')),
      'nothing but GETs may leave this page before the button is pressed',
    ).toHaveLength(0);
    expect(
      before.length,
      `the page made ${before.length} requests to /v1/* before the press: ${before.join(', ')}`,
    ).toBe(5);
    expect(readsIn(wire).size, 'all four reads answered').toBe(4);
    expectEmulator(wire);

    await pressTheGate(page);
    await wire.settle();

    const after = wire.requests.slice(before.length);
    expect(after, 'one press, one request').toEqual([`POST ${GATE_RUN_PATH}`]);
    expect(
      wire.requests.filter((line) => MERGE_ROUTE.test(line)),
      'the merge route answers 423 on the seeded subject; rendering that as a refusal would ' +
        'be a fabricated exhibit',
    ).toHaveLength(0);
    expectEmulator(wire);

    // A second press is one more request, never two: the client refuses to run while a run
    // is in flight, and this endpoint is a real transaction against a real database.
    await pressTheGate(page);
    await wire.settle();
    expect(wire.requests.filter((line) => line === `POST ${GATE_RUN_PATH}`)).toHaveLength(2);
  });

  test('every visible value is present in one of the five response bodies', async ({ page }) => {
    const wire = recordWire(page);
    await page.goto(pageUrl(MEMORY_PAGE));
    await waitForReads(page);
    await pressTheGate(page);
    await wire.settle();
    expectEmulator(wire);

    const reads = readsIn(wire);
    expect(reads.size, 'the corpus needs all four reads to have answered').toBe(4);
    const bodies = [...reads.values(), gateRunIn(wire)];
    expect(bodies, 'four reads and one write make the five bodies').toHaveLength(5);
    // `subjects` is addressing, not content. Leaving it out of the corpus makes this test
    // strictly harder: a value that could only have come from it now fails.
    expect(
      bodies.some((body) => body.path === SUBJECTS_PATH),
      'the addressing payload is not part of the corpus',
    ).toBe(false);
    const corpus = buildCorpus(bodies);

    const cells = await readCells(page);
    const filled = cells.filter((cell) => cell.filled);
    expect(
      filled.length,
      'a page that rendered nothing must not pass this test by rendering nothing',
    ).toBeGreaterThanOrEqual(60);
    expect(
      cells.filter((cell) => !cell.filled).map((cell) => cell.id),
      'every declared cell is filled after one press',
    ).toEqual([]);
    expect(
      filled.filter((cell) => cell.error).map((cell) => cell.id),
      'no cell rendered an error on a healthy run',
    ).toEqual([]);

    const composed: string[] = [];
    for (const cell of filled) {
      const rule = decompositionFor(cell.id);
      if (rule.must !== null) {
        expect(
          cell.text,
          `${cell.id} is a ${rule.name} and must say so in its own text`,
        ).toMatch(rule.must);
      }
      if (!rule.chipAllowed) {
        expect(cell.chip, `${cell.id} composed its text here and may wear no chip`).toBeNull();
      }
      if (cell.chip !== null) {
        expect(
          CHIP_VOCABULARY.has(cell.chip),
          `${cell.id} wears the chip "${cell.chip}", which is not one of the envelope's five`,
        ).toBe(true);
      }

      const tokens = rule.tokens(cell.text);
      if (tokens.length === 0) {
        composed.push(cell.id);
        continue;
      }
      for (const token of tokens) {
        expect(
          corpusHas(corpus, token),
          `${cell.id} shows "${token}", which is in none of the five bodies:\n` +
            `  ${corpus.sources.join('\n  ')}\n` +
            'Either the client composed it, or a decomposition is missing from this spec.',
        ).toBe(true);
      }
    }

    // The exemption surface, asserted exactly. A new composed cell fails here rather than
    // joining the list quietly.
    expect(composed.sort()).toEqual([...COMPOSED_CELL_IDS].sort());

    // And the two claims the panel makes about the run itself, read off the payload rather
    // than off a literal in this file.
    const payload = JSON.parse(gateRunIn(wire).text) as {
      data: {
        verdict: string;
        beats: { sqlstate: string | null; constraint: string | null; outcome: string }[];
        transaction: { single_transaction: boolean; isolation: string };
        persistence_check: { self_persisted: boolean };
      };
    };
    expect(cellById(cells, 'act.verdict').text).toContain(payload.data.verdict);
    expect(cellById(cells, 'act.single_transaction').text).toBe(
      String(payload.data.transaction.single_transaction),
    );
    expect(cellById(cells, 'act.self_persisted').text).toBe(
      String(payload.data.persistence_check.self_persisted),
    );
    payload.data.beats.forEach((beat, index) => {
      const ordinal = index + 1;
      expect(cellById(cells, `act.beat${ordinal}.sqlstate`).text).toBe(asRendered(beat.sqlstate));
      expect(cellById(cells, `act.beat${ordinal}.constraint`).text).toBe(
        asRendered(beat.constraint),
      );
      expect(cellById(cells, `act.beat${ordinal}.outcome`).text).toBe(beat.outcome);
    });
  });

  test('?reveal=off fills the ACT column with no timer at all', async ({ page }) => {
    const wire = recordWire(page);
    await observeTimers(page);
    await page.goto(pageUrl(MEMORY_PAGE_INSTANT));
    await waitForReads(page);

    expect(
      await timersSoFar(page),
      'R-M7.3: no timer runs before a response has resolved',
    ).toEqual([]);

    await pressTheGate(page);
    await wire.settle();

    expect(
      await timersSoFar(page),
      'R-M7.4: with ?reveal=off every beat is painted from the response already in hand, so ' +
        'the page schedules no timer at all. A judge proves the values were in the response ' +
        'with one keystroke.',
    ).toEqual([]);

    const cells = await readCells(page);
    const payload = JSON.parse(gateRunIn(wire).text) as {
      data: { beats: { ordinal: number; outcome: string }[] };
    };
    for (const beat of payload.data.beats) {
      const outcome = cellById(cells, `act.beat${beat.ordinal}.outcome`);
      expect(outcome.filled, `beat ${beat.ordinal} was not filled without a timer`).toBe(true);
      expect(outcome.text).toBe(beat.outcome);
    }
    expect(cellById(cells, 'act.verdict').filled).toBe(true);
  });

  test('the reveal is a display order over values that had already arrived', async ({ page }) => {
    await observeTimers(page);
    const wire = recordWire(page);
    await page.goto(pageUrl(MEMORY_PAGE));
    await waitForReads(page);
    expect(await timersSoFar(page), 'nothing is scheduled while the reads are in flight').toEqual(
      [],
    );

    await pressTheGate(page);
    await wire.settle();

    const payload = JSON.parse(gateRunIn(wire).text) as {
      data: { generated_at: string; beats: unknown[] };
    };
    const timers = await timersSoFar(page);
    expect(
      timers.length,
      'the reveal steps between beats and nowhere else: one timer per gap',
    ).toBe(payload.data.beats.length - 1);
    for (const timer of timers) {
      // The proof that the timer was constructed inside the scope holding the parsed body:
      // the page had ALREADY painted the payload's own generated_at when it was scheduled.
      expect(
        timer.generatedAt,
        'a timer was scheduled before the response had been parsed and painted',
      ).toBe(payload.data.generated_at);
    }
    // The reveal delay is never rendered as a duration (R-M7.2): every elapsed figure on
    // screen belongs to the payload, which the corpus test proves exhaustively.
    const cells = await readCells(page);
    for (const timer of timers) {
      expect(
        cells.some((cell) => cell.filled && cell.text.includes(`${timer.delay} ms`)),
        `the reveal step ${timer.delay} ms appears on screen as if it were a measurement`,
      ).toBe(false);
    }
  });

  test('a failed read renders its status and its path, and never a stale value', async ({
    page,
  }) => {
    // Phase 1: a healthy load, to learn what the cell says when the read answers.
    await page.goto(pageUrl(MEMORY_PAGE_INSTANT));
    await waitForReads(page);
    const healthy = cellById(await readCells(page), 'retrieve.recall.started_at');
    expect(healthy.error).toBe(false);
    expect(healthy.text.length).toBeGreaterThan(0);

    // Phase 2: the ONE fault injection in this file. R-M10 cannot be observed without a
    // failure, and breaking the kernel to produce one would be worse than stubbing a route.
    await page.route('**/v1/recall-runs/**', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'stubbed_by_spec', detail: 'this read was refused by the spec' },
        }),
      }),
    );
    await page.goto(pageUrl(MEMORY_PAGE_INSTANT));
    await page.waitForFunction(
      () =>
        document
          .querySelector('[data-cell="retrieve.recall.started_at"]')
          ?.getAttribute('data-filled') === 'true',
    );

    const cells = await readCells(page);
    const failed = cellById(cells, 'retrieve.recall.started_at');
    expect(failed.error, 'a failed read must mark its cell as an error').toBe(true);
    expect(failed.state).toBe('failed');
    expect(failed.chip, 'a failure is not a column and wears no chip').toBeNull();
    expect(failed.text, 'the HTTP status goes in the cell that needed the value').toContain('503');
    expect(failed.text, 'and so does the path, so a viewer knows which read failed').toContain(
      '/v1/recall-runs/',
    );
    expect(
      failed.text,
      'R-M10: no cell may fall back to a previously fetched value, a fixture or a default',
    ).not.toContain(healthy.text);

    // Every other read still renders. A failure states itself; it does not blank the page.
    const origin = cellById(cells, 'retrieve.armed.origin');
    expect(origin.filled).toBe(true);
    expect(origin.error).toBe(false);
    const event = cellById(cells, 'store.event.ref');
    expect(event.filled).toBe(true);
    expect(event.error).toBe(false);

    // The two annotations that depend on the failed read fail WITH it, rather than being
    // computed from whatever was left lying around.
    expect(cellById(cells, 'annot.gap.recall_to_check').error).toBe(true);
    expect(cellById(cells, 'annot.gap.event_to_check').error).toBe(false);
  });

  test('the SYNTHETIC prefix survives to the DOM unstripped', async ({ page }) => {
    const wire = recordWire(page);
    await page.goto(pageUrl(MEMORY_PAGE_INSTANT));
    await waitForReads(page);
    await wire.settle();

    const reads = readsIn(wire);
    const checks = JSON.parse(mustRead(reads, 'checks').text) as {
      data: { checks: { precursor: { title: string } }[] };
    };
    const ancestry = JSON.parse(mustRead(reads, 'ancestry').text) as {
      data: { blame_edges: { attribution: string }[] };
    };
    const title = checks.data.checks[0]?.precursor.title ?? '';
    const attribution = ancestry.data.blame_edges[0]?.attribution ?? '';
    expect(title, 'the seeded title carries the prefix this test is about').toContain('SYNTHETIC');
    expect(attribution, 'so does the seeded attribution').toContain('SYNTHETIC');

    const cells = await readCells(page);
    // R-M13: the prefix is a column value. Not stripped, not trimmed, not styled away — and
    // the assertion is equality with the byte the server sent, not merely "starts with".
    expect(cellById(cells, 'store.event.title').text).toBe(title);
    expect(cellById(cells, 'store.edge.attribution').text).toBe(attribution);
    expect(cellById(cells, 'store.event.title').text).toContain('SYNTHETIC');
    expect(cellById(cells, 'store.edge.attribution').text).toContain('SYNTHETIC');

    // And it is readable, rather than hidden by a stylesheet that "handles" the prefix.
    const visible = await page.$eval('[data-cell="store.event.title"]', (element) => {
      const style = getComputedStyle(element);
      return {
        display: style.display,
        visibility: style.visibility,
        fontSize: Number.parseFloat(style.fontSize),
        opacity: Number.parseFloat(style.opacity),
      };
    });
    expect(visible.display).not.toBe('none');
    expect(visible.visibility).toBe('visible');
    expect(visible.fontSize).toBeGreaterThan(6);
    expect(visible.opacity).toBeGreaterThan(0.5);
  });
});
