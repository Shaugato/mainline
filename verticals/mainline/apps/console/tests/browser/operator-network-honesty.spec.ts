// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * W7 — THE DEVTOOLS-HONESTY SPEC. The one that answers the question
 * `operator-systems-plan.md` §7 leaves open.
 *
 * ── THE QUESTION ─────────────────────────────────────────────────────────────────────
 *
 * R5 chose ONE press, four beats, progressively revealed. A judge with devtools open then
 * sees **one** request and **three** UI transitions. That is exactly the silhouette of a
 * faked demo — a `setTimeout` chain over a canned payload looks identical from the outside.
 * R5's mitigation is the mandatory disclosure line. §7 says W7 must decide, against a real
 * capture, whether the mitigation holds; if it does not, the fallback is three presses and
 * three real round trips.
 *
 * This file is the machine half of that decision. It asserts, **from the browser's own
 * network events and nothing else**, the five properties that separate the honest shape
 * from the dishonest one:
 *
 *   1. One press ⇒ exactly ONE `POST /v1/demo/gate-run`, and zero requests of any kind to
 *      `POST /v1/permits/{id}/merge` (R4 — that route answers `423 Locked` and rendering it
 *      as a refusal is the most deniable lie available on this screen).
 *   2. Every SQLSTATE, every constraint name and every duration on screen is present in the
 *      bytes of that one response. Nothing on screen was composed by the client.
 *   3. The mandatory disclosure line is present, has R5's exact shape, and carries no
 *      dismiss control — no button, no `hidden`, no `<details>` ancestor.
 *   4. No timer separates a reveal from its data. Asserted two ways: the page's own
 *      `setTimeout`/`setInterval` calls are recorded and must carry no positive delay across
 *      the press-to-final-beat window, and each reveal is measured to land inside a frame.
 *   5. The raw-payload affordance shows the response body BYTE FOR BYTE (R18) — the thing a
 *      judge diffs against the Network panel's Response tab.
 *
 * ── HOW IT OBSERVES, AND WHAT IT REFUSES TO DO ───────────────────────────────────────
 *
 * There is no `page.route`, no `fulfil`, no `abort`, no stubbed handler and no injected
 * payload anywhere in this file. Every byte asserted on came off a real socket from
 * `scripts/deploy/local_furl.py`, which runs the real `mainline_demo_api.app.handler`
 * in-process against the local CockroachDB node.
 *
 * The ONE thing this file adds to the page is an observer, and it is worth being precise
 * about it: `recordTimers()` wraps `window.setTimeout` and `window.setInterval` in functions
 * that push `{delay, stack}` onto an array and then **call the original with the original
 * arguments and return the original's return value**. It changes no data, no timing, no
 * response and no rendering path. A spec that asserted "no timer ran" by reading the source
 * would be asserting about a file; this asserts about the running page. The capture harness
 * (`scripts/operator-capture.mjs`) installs nothing at all, for the stricter reason that a
 * capture must be reproducible by a human with a plain browser.
 *
 * ── RUNNING IT ───────────────────────────────────────────────────────────────────────
 *
 *   pnpm run build                      # dist/operator.html must exist
 *   pnpm run test:browser               # playwright.config.ts starts local_furl for you
 *
 * or against an emulator you already have:
 *
 *   MAINLINE_OPERATOR_BASE_URL=http://127.0.0.1:8741 pnpm run test:browser
 */

import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page, type Request, type Response } from '@playwright/test';

// ── Where things are ───────────────────────────────────────────────────────────────────

const HERE = dirname(fileURLToPath(import.meta.url));
/** `verticals/mainline/apps/console/tests/browser` → repository root. */
const REPO_ROOT = resolve(HERE, '../../../../../..');
const CAPTURE_JSON = resolve(REPO_ROOT, 'evidence/demo/operator-capture.json');

const OPERATOR_URL = '/operator.html#/permit';

/** R4's route, written once. The spec asserts the page uses this and never the merge route. */
const GATE_RUN_PATH = '/v1/demo/gate-run';
/** The route that answers 423 Locked. Any request matching this is a design failure. */
const MERGE_ROUTE = /\/v1\/permits\/[^/]+\/merge$/;

// ── The payload's own shape, as the contract declares it ───────────────────────────────

interface BeatPayload {
  readonly ordinal: number;
  readonly name: string;
  readonly outcome: string;
  readonly sqlstate: string | null;
  readonly constraint: string | null;
  readonly constraint_source: string | null;
  readonly elapsed_ms: number;
  readonly message: string | null;
}

interface GateRunPayload {
  readonly run_id: string;
  readonly verdict: string;
  readonly outcome: string;
  readonly persisted: boolean;
  readonly beats: readonly BeatPayload[];
}

/** What one press produced: the request, the response and the exact bytes. */
interface PressObservation {
  readonly gateRunRequests: readonly string[];
  readonly mergeRequests: readonly string[];
  readonly status: number;
  readonly emulator: string | null;
  readonly bodyText: string;
  readonly bodyBytes: number;
  readonly payload: GateRunPayload;
}

/** Every timer the page scheduled, with the delay it asked for. */
interface TimerCall {
  readonly kind: 'setTimeout' | 'setInterval';
  readonly delay: number;
}

declare global {
  /* A global declaration needs `var`: `let` here declares a module binding that
     `globalThis.__w7Timers` never sees. */
  var __w7Timers: TimerCall[] | undefined;
}

// ── The observer ───────────────────────────────────────────────────────────────────────

/**
 * Records every timer the page schedules and CALLS THROUGH unchanged.
 *
 * Installed with `addInitScript` so it is in place before the operator module evaluates. Each
 * wrapper records the delay it was asked for, then calls the original with the original
 * arguments and returns the original’s handle — so `clearTimeout` still works and a
 * zero-delay callback still runs on the same turn. Nothing here changes what the page sees;
 * it only writes down what the page asked for.
 *
 * The two `as unknown as` bridges are the honest cost of this workspace typechecking browser
 * specs under `tsconfig.node.json`, where `@types/node` unions its own `setTimeout` (returning
 * `Timeout`, carrying `__promisify__`) into the DOM one. Writing the wrapper against the DOM
 * signature and casting at the assignment keeps the wrapper body fully typed; the alternative,
 * `any` parameters, would type-erase the very arguments being forwarded.
 */
async function recordTimers(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const calls: { kind: 'setTimeout' | 'setInterval'; delay: number }[] = [];
    (globalThis as unknown as { __w7Timers: typeof calls }).__w7Timers = calls;

    type Fn = (handler: TimerHandler, timeout?: number, ...args: unknown[]) => number;
    const realTimeout = window.setTimeout.bind(window) as unknown as Fn;
    const realInterval = window.setInterval.bind(window) as unknown as Fn;

    const wrappedTimeout: Fn = (handler, timeout, ...rest) => {
      calls.push({ kind: 'setTimeout', delay: timeout ?? 0 });
      return realTimeout(handler, timeout, ...rest);
    };
    const wrappedInterval: Fn = (handler, timeout, ...rest) => {
      calls.push({ kind: 'setInterval', delay: timeout ?? 0 });
      return realInterval(handler, timeout, ...rest);
    };

    window.setTimeout = wrappedTimeout as unknown as typeof window.setTimeout;
    window.setInterval = wrappedInterval as unknown as typeof window.setInterval;
  });
}

async function timersSince(page: Page, from: number): Promise<readonly TimerCall[]> {
  const all = await page.evaluate(() => globalThis.__w7Timers ?? []);
  return all.slice(from);
}

async function timerCount(page: Page): Promise<number> {
  return page.evaluate(() => globalThis.__w7Timers?.length ?? 0);
}

// ── Driving one press ──────────────────────────────────────────────────────────────────

/**
 * Loads the permit screen, presses ISSUE once, and returns everything the socket carried.
 *
 * The response body is taken with `Response.body()` — the decoded bytes — and never
 * re-serialised, because the byte-identity assertion below is the whole point of R18.
 */
async function pressIssueOnce(page: Page): Promise<PressObservation> {
  const gateRunRequests: string[] = [];
  const mergeRequests: string[] = [];

  const onRequest = (request: Request): void => {
    const path = new URL(request.url()).pathname;
    if (request.method() === 'POST' && path === GATE_RUN_PATH) gateRunRequests.push(request.url());
    if (MERGE_ROUTE.test(path)) mergeRequests.push(`${request.method()} ${path}`);
  };
  page.on('request', onRequest);

  await page.goto(OPERATOR_URL, { waitUntil: 'networkidle' });
  await expect(page.locator('[data-action="issue"]')).toBeEnabled();

  const waitForRun = page.waitForResponse(
    (response: Response) => new URL(response.url()).pathname === GATE_RUN_PATH,
  );
  await page.locator('[data-action="issue"]').click();
  const response = await waitForRun;

  const body = await response.body();
  const bodyText = body.toString('utf8');

  // Let any further request the page might make settle, so `gateRunRequests` is complete.
  await page.waitForLoadState('networkidle');
  page.off('request', onRequest);

  const envelope = JSON.parse(bodyText) as { data: GateRunPayload };

  return {
    gateRunRequests,
    mergeRequests,
    status: response.status(),
    emulator: (await response.headerValue('x-mainline-emulator')) ?? null,
    bodyText,
    bodyBytes: Buffer.byteLength(bodyText, 'utf8'),
    payload: envelope.data,
  };
}

/** Reveals every remaining beat, returning how many presses it took. */
async function revealAll(page: Page): Promise<number> {
  let presses = 0;
  for (;;) {
    const advance = page.locator('[data-action="advance"]');
    if ((await advance.count()) === 0) break;
    await advance.first().click();
    presses += 1;
    if (presses > 8) throw new Error('the advance control never went away; this is a loop, not a reveal.');
  }
  return presses;
}

/** The three renderings `src/operator/issue/beats.ts` `formatMs` can produce, re-derived. */
function renderingsOf(ms: number): readonly string[] {
  return [`${(ms / 1000).toFixed(2)} s`, `${ms.toFixed(3)} ms`, `${ms.toFixed(1)} ms`];
}

// ═══════════════════════════════════════════════════════════════════════════════════════
// 1 · ONE PRESS, ONE REQUEST, AND NOT THE ROUTE THAT ANSWERS 423
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('one press is one request', () => {
  test('produces exactly one POST to /v1/demo/gate-run', async ({ page }) => {
    const seen = await pressIssueOnce(page);
    expect(seen.gateRunRequests).toHaveLength(1);
    expect(seen.status).toBe(200);
  });

  test('never touches POST /v1/permits/{id}/merge — that route answers 423 Locked', async ({
    page,
  }) => {
    const seen = await pressIssueOnce(page);
    await revealAll(page);
    // Checked over the WHOLE page load, not just the press: a read of the merge route would
    // be as wrong as a write of it, and R4 is a statement about the screen, not the button.
    expect(seen.mergeRequests).toEqual([]);
  });

  test('is talking to the local emulator, not the deployed URL', async ({ page }) => {
    const seen = await pressIssueOnce(page);
    // `local_furl.py` stamps this on every response so a rehearsal capture can never be
    // passed off as the deployment. Its absence here means the suite is pointed at AWS,
    // which W7 is forbidden to do.
    expect(seen.emulator).toBe('local_furl');
    await expect(page.locator('[data-cw-field="emulator"]')).toContainText('local_furl');
  });

  test('the run it returned is a real one: PROVEN, four beats, persisted nothing', async ({
    page,
  }) => {
    const seen = await pressIssueOnce(page);
    expect(seen.payload.outcome).toBe('completed');
    expect(seen.payload.persisted).toBe(false);
    expect(seen.payload.beats).toHaveLength(4);
    expect(seen.payload.run_id).toMatch(/^[0-9a-f-]{36}$/);
    // Guard, not formality: if the fixture degenerated to an empty run every assertion
    // below would compare '' with '' and pass.
    expect(seen.payload.beats.filter((beat) => beat.outcome === 'refused')).toHaveLength(2);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// 2 · EVERY NUMBER ON SCREEN IS IN THOSE BYTES
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('nothing on screen was composed by the client', () => {
  test('every rendered beat matches the payload beat of the same ordinal', async ({ page }) => {
    const seen = await pressIssueOnce(page);
    await revealAll(page);

    const rendered = await page.$$eval('[data-beat]', (nodes) =>
      nodes.map((node) => ({
        ordinal: Number((node as HTMLElement).dataset['ordinal']),
        name: (node as HTMLElement).dataset['beat'] ?? '',
        outcome: (node as HTMLElement).dataset['outcome'] ?? '',
        sqlstate: (node as HTMLElement).dataset['sqlstate'] ?? null,
      })),
    );

    expect(rendered).toHaveLength(seen.payload.beats.length);
    for (const view of rendered) {
      const beat = seen.payload.beats.find((candidate) => candidate.ordinal === view.ordinal);
      expect(beat, `no payload beat has ordinal ${view.ordinal}`).toBeDefined();
      expect(view.name).toBe(beat?.name);
      expect(view.outcome).toBe(beat?.outcome);
      if (view.sqlstate !== null) expect(view.sqlstate).toBe(beat?.sqlstate);
    }
  });

  test('every value the screen labels SQLSTATE is a beat’s own sqlstate', async ({ page }) => {
    const seen = await pressIssueOnce(page);
    await revealAll(page);

    // Read what the screen PRESENTS as a SQLSTATE — the `dd` beside every `dt` that says so.
    // Scanning prose for a five-character [0-9A-Z] shape was tried first and matched CHECK,
    // WRITE, ISSUE and a fragment of an ISO timestamp: a heuristic that cries wolf is a
    // heuristic nobody reads twice.
    const labelled = await page.$$eval('[data-result="true"] dt', (nodes) =>
      nodes
        .filter((node) => node.textContent.trim() === 'SQLSTATE')
        .map((node) => (node.nextElementSibling?.textContent ?? '').trim()),
    );
    expect(labelled.length, 'no SQLSTATE row on screen at all').toBeGreaterThan(0);

    const inPayload = new Set(
      seen.payload.beats.flatMap((beat) => (beat.sqlstate === null ? [] : [beat.sqlstate])),
    );
    for (const code of labelled) {
      expect(
        inPayload.has(code) && seen.bodyText.includes(`"${code}"`),
        `"${code}" is labelled SQLSTATE on screen and is not a beat's sqlstate in the ` +
          `${seen.bodyBytes} bytes the server returned.`,
      ).toBe(true);
    }
    // One row per beat that carried a code — none dropped, none duplicated.
    expect(labelled).toHaveLength(
      seen.payload.beats.filter((beat) => beat.sqlstate !== null).length,
    );
  });

  test('no modelled SQLSTATE appears on screen that the payload does not carry', async ({
    page,
  }) => {
    const seen = await pressIssueOnce(page);
    await revealAll(page);
    const text = await page.locator('[data-result="true"]').innerText();

    // `40001` is the one that matters. `gate-run-contract.md` §2: an undecided transaction has
    // no reason set, so it never carries a refusal. A screen that printed it beside one would
    // be claiming the gate said no when the database said "ask me again".
    const taxonomy = ['00000', '23514', '23503', '23505', '40001', 'P0001', '42P01', '22P02'];
    const foreign = taxonomy.filter(
      (code) => text.includes(code) && !seen.bodyText.includes(`"${code}"`),
    );
    expect(
      foreign,
      `SQLSTATE(s) on screen that the ${seen.bodyBytes}-byte response does not carry: ` +
        foreign.join(', '),
    ).toEqual([]);
  });


  test('every constraint name on screen is in the response bytes', async ({ page }) => {
    const seen = await pressIssueOnce(page);
    await revealAll(page);

    const names = await page.$$eval('dd[data-row="constraint"] .cow-refusal__value', (nodes) =>
      nodes.map((node) => node.textContent.trim()),
    );
    expect(names.length).toBeGreaterThan(0);

    const declared = new Set(
      seen.payload.beats.flatMap((beat) => (beat.constraint === null ? [] : [beat.constraint])),
    );
    for (const name of names) {
      expect(declared.has(name), `constraint "${name}" is on screen and not in the payload`).toBe(
        true,
      );
      expect(seen.bodyText).toContain(`"${name}"`);
    }
  });

  test('every duration on screen is that beat’s own elapsed_ms, formatted', async ({ page }) => {
    const seen = await pressIssueOnce(page);
    await revealAll(page);

    const durations = await page.$$eval('[data-beat]', (nodes) =>
      nodes.map((node) => ({
        ordinal: Number((node as HTMLElement).dataset['ordinal']),
        // Every duration string the beat renders, whatever element carries it.
        found: [...(node.textContent.match(/\d+\.\d+ (?:ms|s)/g) ?? [])],
      })),
    );

    for (const { ordinal, found } of durations) {
      const beat = seen.payload.beats.find((candidate) => candidate.ordinal === ordinal);
      expect(beat, `no payload beat has ordinal ${ordinal}`).toBeDefined();
      expect(found.length, `beat ${ordinal} rendered no duration at all`).toBeGreaterThan(0);
      const allowed = renderingsOf(beat?.elapsed_ms ?? Number.NaN);
      for (const shown of found) {
        expect(
          allowed,
          `beat ${ordinal} shows "${shown}"; its payload elapsed_ms is ${beat?.elapsed_ms}. ` +
            `A duration on this screen may only ever be the server's own measurement of that beat.`,
        ).toContain(shown);
      }
    }
  });

  test('the message and the CHECK predicate are the database’s verbatim words', async ({
    page,
  }) => {
    const seen = await pressIssueOnce(page);
    await revealAll(page);

    const messages = await page.$$eval('dd[data-row="message"]', (nodes) =>
      nodes.map((node) => node.textContent.trim()),
    );
    expect(messages.length).toBeGreaterThan(0);
    const declared = seen.payload.beats.flatMap((beat) => (beat.message === null ? [] : [beat.message]));
    for (const shown of messages) {
      expect(
        declared.some((candidate) => candidate.trim() === shown),
        `the message on screen is not verbatim any beat's message:\n  screen: ${shown}`,
      ).toBe(true);
    }
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// 3 · THE MANDATORY DISCLOSURE LINE
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the disclosure line R5 makes mandatory', () => {
  test('is present, and has R5’s exact shape with the run’s real values in it', async ({
    page,
  }) => {
    const seen = await pressIssueOnce(page);

    const line = page.locator('[data-disclosure="line"]');
    await expect(line).toBeVisible();
    const sentence = ((await line.textContent()) ?? '').trim();

    // The shape, transcribed from operator-systems-plan.md R5 rather than from the module
    // that renders it — a regex imported from the code under test asserts nothing.
    expect(sentence).toMatch(
      /^one request · \d+ beats · POST \/v1\/demo\/gate-run · run_id \S+ · response received \S+ · \d+ bytes$/,
    );
    expect(sentence).toContain(`one request · ${seen.payload.beats.length} beats`);
    expect(sentence).toContain(`run_id ${seen.payload.run_id}`);
    // The byte count in the sentence is the byte count of the body the browser received.
    expect(sentence).toContain(`${seen.bodyBytes} bytes`);
    await expect(page.locator('.cow-disclosure')).toHaveAttribute('data-shape', 'expected');
  });

  test('is non-dismissible: no control, no hidden, no disclosure ancestor', async ({ page }) => {
    await pressIssueOnce(page);

    const strip = page.locator('.cow-disclosure');
    await expect(strip).toHaveAttribute('data-permanent', 'true');
    expect(await strip.locator('button, a[href], [role="button"], input').count()).toBe(0);
    expect(
      await strip.evaluate((node) => node.closest('details') !== null),
      'the mandatory disclosure line is inside a <details>, so it is dismissible',
    ).toBe(false);
    expect(await strip.evaluate((node) => node.hasAttribute('hidden'))).toBe(false);
  });

  test('survives every reveal — it is not a splash that goes away', async ({ page }) => {
    await pressIssueOnce(page);
    const before = ((await page.locator('[data-disclosure="line"]').textContent()) ?? '').trim();
    await revealAll(page);
    const after = ((await page.locator('[data-disclosure="line"]').textContent()) ?? '').trim();
    expect(after).toBe(before);
    await expect(page.locator('[data-disclosure="line"]')).toBeVisible();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// 4 · NO TIMER SEPARATES A REVEAL FROM ITS DATA
// ═══════════════════════════════════════════════════════════════════════════════════════

test.describe('the reveal is driven by the operator, not by a clock', () => {
  test('the page schedules no delayed timer between the press and the last beat', async ({
    page,
  }) => {
    await recordTimers(page);
    await page.goto(OPERATOR_URL, { waitUntil: 'networkidle' });

    // Everything before the press is somebody else's business — the asset graph, a font, the
    // reads. The window that matters is press → final beat.
    const mark = await timerCount(page);

    const waitForRun = page.waitForResponse(
      (response) => new URL(response.url()).pathname === GATE_RUN_PATH,
    );
    await page.locator('[data-action="issue"]').click();
    await waitForRun;
    await revealAll(page);

    const scheduled = await timersSince(page, mark);
    const delayed = scheduled.filter((call) => call.delay > 0);
    expect(
      delayed,
      `${delayed.length} delayed timer(s) were scheduled between the press and the final beat: ` +
        `${JSON.stringify(delayed)}. R5 forbids any of them — a reveal separated from its data ` +
        `by a clock is faked latency however real the payload is.`,
    ).toEqual([]);
    expect(scheduled.filter((call) => call.kind === 'setInterval')).toEqual([]);
  });

  test('each reveal lands inside a frame of the click that asked for it', async ({ page }) => {
    await pressIssueOnce(page);

    for (;;) {
      const advance = page.locator('[data-action="advance"]');
      if ((await advance.count()) === 0) break;
      const before = await page.locator('[data-beat]').count();
      const started = Date.now();
      await advance.first().click();
      await expect(page.locator('[data-beat]')).toHaveCount(before + 1);
      const elapsed = Date.now() - started;
      // 250 ms is generous for a click round trip through the driver; a staged reveal in this
      // repository's own research is 360-480 ms, so the two are not confusable.
      expect(
        elapsed,
        `a beat took ${elapsed} ms to appear after its click. Nothing here computes; the data ` +
          `was already in hand. A delay is either a timer or a repaint stall, and both read as staged.`,
      ).toBeLessThan(250);
    }
  });

  test('the second and third beats are in the DOM only after their control is pressed', async ({
    page,
  }) => {
    await pressIssueOnce(page);
    const first = await page.locator('[data-beat]').count();
    // Progressive disclosure is a real property: the beats are NOT all painted and hidden by
    // CSS, which would be a different (and less honest) thing than revealing them.
    expect(first).toBeGreaterThan(0);
    expect(first).toBeLessThan(4);
    const presses = await revealAll(page);
    expect(await page.locator('[data-beat]').count()).toBe(4);
    expect(presses).toBe(4 - first);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// 5 · R18 — THE RAW PAYLOAD, BYTE FOR BYTE
// ═══════════════════════════════════════════════════════════════════════════════════════

/**
 * `operator-systems-plan.md` R18: *"Every screen carries a RAW PAYLOAD affordance and a
 * REQUEST LOG. One click shows the verbatim JSON that produced what is on screen... it is
 * what a judge in devtools will cross-check."*
 *
 * `src/operator/kernel/raw.ts` implements it — `renderRawPayload()` and
 * `renderRequestLog()`, both written to insert `Exchange.raw` with `textContent` and never
 * `JSON.stringify(JSON.parse(raw))`. Measured 2026-08-15: **nothing calls either function.**
 * The permit screen renders no `<details>`, no `<pre>` of a response body and no request log
 * at all; the change screen renders four `pre.moc-raw` drawers of its own.
 *
 * This test is therefore RED, and it is left red on purpose. The gate-run response is the
 * ONE payload a judge will diff against the Network panel, and it is the one with no drawer.
 */
test.describe('the raw payload a judge cross-checks', () => {
  test('the gate-run response body is on screen, byte for byte', async ({ page }) => {
    const seen = await pressIssueOnce(page);
    await revealAll(page);

    const drawers = await page.$$eval('pre, code[data-raw], .mlk-raw__body', (nodes) =>
      nodes.map((node) => node.textContent),
    );
    const exact = drawers.filter((text) => text.trim() === seen.bodyText.trim());

    expect(
      exact.length,
      'R18: no element on the permit screen carries the verbatim gate-run response body.\n' +
        `The response was ${seen.bodyBytes} bytes; ${drawers.length} <pre>/raw element(s) were ` +
        'found and none matched it.\n' +
        'OWNER: W5 (src/operator/issue/**) with W2 (src/operator/kernel/raw.ts). ' +
        '`renderRawPayload()` and `renderRequestLog()` exist, are correct, and are called by ' +
        'nobody. One call site on the result region closes this.',
    ).toBeGreaterThan(0);
  });

  test('the request log lists the one POST with its status and bytes', async ({ page }) => {
    const seen = await pressIssueOnce(page);
    const rows = page.locator('.mlk-log__row');
    await expect(
      rows,
      'R18: the permit screen renders no request log. src/operator/kernel/raw.ts ' +
        '`renderRequestLog()` is implemented and unmounted. OWNER: W5 / W2.',
    ).not.toHaveCount(0);
    await expect(rows.filter({ hasText: GATE_RUN_PATH }).first()).toContainText(
      String(seen.bodyBytes),
    );
  });
});

// ═══════════════════════════════════════════════════════════════════════════════════════
// 6 · THE COMMITTED EVIDENCE MAY NEVER DISAGREE WITH THE LIVE PAGE
// ═══════════════════════════════════════════════════════════════════════════════════════

/**
 * `scripts/operator-capture.mjs` writes `evidence/demo/operator-capture.json`. That file is
 * what a reader who cannot run the emulator will read, so it gets a guard: the invariants
 * asserted live above are re-asserted over the committed bytes. An evidence file that
 * drifted from the behaviour it documents is worse than no evidence file.
 */
test.describe('evidence/demo/operator-capture.json', () => {
  test('records one gate-run POST, no merge request, and the emulator header', () => {
    expect(
      existsSync(CAPTURE_JSON),
      `${CAPTURE_JSON} does not exist. Run: node scripts/operator-capture.mjs`,
    ).toBe(true);

    const capture = JSON.parse(readFileSync(CAPTURE_JSON, 'utf8')) as {
      target: { emulator_header: string | null };
      network: readonly { method: string; path: string; status: number }[];
      assertions: readonly { id: string; held: boolean; detail: string }[];
    };

    expect(capture.target.emulator_header).toBe('local_furl');

    const posts = capture.network.filter(
      (entry) => entry.method === 'POST' && entry.path === GATE_RUN_PATH,
    );
    expect(posts).toHaveLength(1);
    expect(posts[0]?.status).toBe(200);
    expect(capture.network.filter((entry) => MERGE_ROUTE.test(entry.path))).toEqual([]);

    // The capture records its own verdicts. Any that did not hold are printed here rather
    // than swallowed, because the file is written whether the run passed or failed.
    const broken = capture.assertions.filter((entry) => !entry.held);
    expect(broken.map((entry) => `${entry.id}: ${entry.detail}`)).toEqual([]);
  });
});
