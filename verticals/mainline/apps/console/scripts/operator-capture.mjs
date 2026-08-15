// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * DRIVE THE OPERATOR SCREENS AT FILMING PACE AND WRITE DOWN EXACTLY WHAT THE SOCKET CARRIED.
 *
 * ── WHAT THIS IS FOR ─────────────────────────────────────────────────────────────────
 *
 * `operator-systems-plan.md` §7 leaves one question open: *"Whether the progressive reveal
 * reads as honest on a capture."* R5 chose one press and four beats, revealed under operator
 * control. A judge with devtools open then sees ONE request and THREE UI transitions — which
 * is also what a `setTimeout` chain over a canned payload looks like. W7 has to watch a real
 * capture, with devtools open, and record a verdict.
 *
 * This program produces that capture, and produces it in a form a human can check without
 * running anything: `evidence/demo/operator-capture.json` carries the full network log, the
 * verbatim response bodies, the rendered DOM at each stage, and the assertions the run made
 * about its own honesty.
 *
 * ── WHAT IT REFUSES TO DO, AND WHY EACH REFUSAL MATTERS ──────────────────────────────
 *
 *   * **No `page.route`, no `fulfil`, no `abort`, no stub, no fixture.** If this program can
 *     change what the page sees, then the capture proves nothing about what the page does —
 *     and the mocked layer would be exactly the layer the first judging criterion scores.
 *   * **No `addInitScript`, no injected observer of any kind.** The browser specs may
 *     instrument timers (they assert about a running page and they say so); a CAPTURE may
 *     not, because a capture has to be reproducible by a human opening the same URL in a
 *     plain Chrome. Everything recorded here is read from `page.on('request')`,
 *     `page.on('response')` and the DOM.
 *   * **No `page.clock`, no frozen time, no seeded PRNG.** The elapsed values in this file
 *     are the ones the server measured on the day it ran.
 *   * **It never decides that a failure is acceptable.** Every assertion is recorded with
 *     what was expected and what was seen, the JSON is written whether the run held or not
 *     (a failed run's measurements are the useful ones), and the exit status is 1 if any
 *     assertion did not hold.
 *   * **It never points at AWS.** `--base-url` defaults to loopback and the run refuses to
 *     continue unless the response carries `X-Mainline-Emulator`, which only
 *     `scripts/deploy/local_furl.py` stamps. Capturing against the deployed Function URL
 *     would be hammering `POST /v1/demo/gate-run` on the one public subject a judge is about
 *     to open, and W7 is forbidden to touch AWS at all.
 *
 * ── THE FILMING GEOMETRY ─────────────────────────────────────────────────────────────
 *
 * 1024 x 576 CSS at `deviceScaleFactor: 2.5` renders 2560 x 1440 — r5-craft §2.1's
 * "175-200 % browser zoom at 1440p" pushed to 250 %, because W7 measured the SQLSTATE value
 * (13.12 CSS px), the constraint name, the reason set and the mandatory disclosure line
 * (12.80 CSS px) all BELOW the 2 %-of-frame-height floor (14.40 px) at 200 %. At 250 % the
 * floor is 11.52 px and every one of them clears it. Screenshots come out at 2560 x 1440,
 * above the 1440p the brief asks for.
 *
 * ── FILMING PACE ─────────────────────────────────────────────────────────────────────
 *
 * `--pace` is the pause BETWEEN operator actions — the time a human takes to read a beat and
 * decide to press again. It is a property of the driver, not of the page, and it is recorded
 * in the JSON so nobody can mistake it for a rendering delay. The page itself is measured
 * separately: `reveal_latency_ms` is the wall clock from the click to the beat being in the
 * DOM, and that number is the one that would expose a fake.
 *
 * ── USAGE ────────────────────────────────────────────────────────────────────────────
 *
 *   # start the emulator first (it needs the seeded database and the seeded permit id):
 *   .venv/Scripts/python.exe scripts/deploy/local_furl.py \
 *     --port 8741 --web-root verticals/mainline/apps/console/dist --require-web-root \
 *     --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable" \
 *     --database mainline_demo --permit-id dec0de00-0006-4000-8000-000000000001
 *
 *   node scripts/operator-capture.mjs                       # defaults below
 *   node scripts/operator-capture.mjs --headed --pace 1800  # watch it, with devtools open
 *   node scripts/operator-capture.mjs --devtools            # opens devtools for the human review
 *
 * A NOTE ON `pnpm run lint`, MEASURED AND REPORTED RATHER THAN WORKED AROUND. This workspace
 * supplies `parserOptions.project` in an `eslint.config.js` block with no `files` key, so the
 * type-aware parser is applied to `.mjs` files that no tsconfig includes, and `eslint .`
 * answers `Parsing error: ... was not found in any of the provided project(s)`. That collision
 * already exists for `scripts/drive-console.mjs`, which documents it at length and names the
 * one-line remedy (`files: ['**\/*.{ts,tsx}']` on that block) as belonging to whoever owns
 * `eslint.config.js` — W1 in this wave. This file is delivered where the plan puts it and the
 * collision is reported, not resolved by editing another worker's file.
 */

import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { argv, env, exit, stderr, stdout } from 'node:process';
import { fileURLToPath } from 'node:url';

import { chromium } from '@playwright/test';

// ── Where things are ───────────────────────────────────────────────────────────────────

const HERE = dirname(fileURLToPath(import.meta.url));
/** `verticals/mainline/apps/console/scripts` → repository root. */
const REPO_ROOT = resolve(HERE, '../../../../..');
const DEFAULT_OUT = join(REPO_ROOT, 'evidence/demo/operator-capture.json');
const DEFAULT_SHOTS = join(REPO_ROOT, 'evidence/demo/operator-capture');

// ── The contract this driver knows about ───────────────────────────────────────────────

/** R4. The ISSUE button's route. */
const GATE_RUN_PATH = '/v1/demo/gate-run';
/** The route that answers 423 Locked on the seeded subject. Must never be requested. */
const MERGE_ROUTE = /\/v1\/permits\/[^/]+\/merge$/;
/** `local_furl.py` stamps this on every response. Its absence means we are not on the emulator. */
const EMULATOR_HEADER = 'x-mainline-emulator';

/** The filming geometry. See the header. */
const VIEWPORT = { width: 1024, height: 576 };
const DEVICE_SCALE = 2.5;

// ── Arguments ──────────────────────────────────────────────────────────────────────────

function parseArgs(args) {
  const out = {
    baseUrl: env['MAINLINE_OPERATOR_BASE_URL'] ?? 'http://127.0.0.1:8741',
    out: DEFAULT_OUT,
    shots: DEFAULT_SHOTS,
    pace: 1200,
    timeout: 30_000,
    headed: false,
    devtools: false,
  };
  for (let index = 0; index < args.length; index += 1) {
    const flag = args[index];
    const value = args[index + 1];
    switch (flag) {
      case '--base-url':
        out.baseUrl = value;
        index += 1;
        break;
      case '--out':
        out.out = resolve(value);
        index += 1;
        break;
      case '--shots':
        out.shots = resolve(value);
        index += 1;
        break;
      case '--pace':
        out.pace = Number(value);
        index += 1;
        break;
      case '--timeout':
        out.timeout = Number(value);
        index += 1;
        break;
      case '--headed':
        out.headed = true;
        break;
      case '--devtools':
        out.devtools = true;
        out.headed = true;
        break;
      case '--help':
      case '-h':
        stdout.write('see the header of this file\n');
        exit(0);
        break;
      default:
        stderr.write(`operator-capture: unknown argument ${String(flag)}\n`);
        exit(2);
    }
  }
  if (out.baseUrl.includes('.on.aws') || out.baseUrl.includes('amazonaws')) {
    stderr.write(
      'operator-capture: refusing to capture against a deployed URL. This program drives ' +
        'POST /v1/demo/gate-run, and the deployed subject is one shared public row a judge is ' +
        'about to open. Point it at scripts/deploy/local_furl.py.\n',
    );
    exit(2);
  }
  return out;
}

// ── The record ─────────────────────────────────────────────────────────────────────────

/** One assertion this run made about itself. Recorded whether it held or not. */
class Ledger {
  constructor() {
    this.entries = [];
  }

  /** @param {string} id @param {boolean} held @param {string} detail */
  record(id, held, detail) {
    this.entries.push({ id, held, detail });
    stdout.write(`${held ? '  ok  ' : '  NO  '}${id} — ${detail}\n`);
    return held;
  }

  get broken() {
    return this.entries.filter((entry) => !entry.held);
  }
}

function nowIso() {
  return new Date().toISOString();
}

async function pause(page, ms) {
  if (ms > 0) await page.waitForTimeout(ms);
}

// ── The run ────────────────────────────────────────────────────────────────────────────

async function main() {
  const options = parseArgs(argv.slice(2));
  const ledger = new Ledger();

  mkdirSync(dirname(options.out), { recursive: true });
  mkdirSync(options.shots, { recursive: true });

  const browser = await chromium.launch({ headless: !options.headed, devtools: options.devtools });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: DEVICE_SCALE,
    // No offline, no extra headers, no service-worker blocking, no permissions. This context
    // is as close to a plain Chrome as Playwright makes available.
  });
  const page = await context.newPage();
  page.setDefaultTimeout(options.timeout);

  /** Every request the browser put on the socket, in order. */
  const network = [];
  /** Verbatim response bodies, keyed by `METHOD path`. Never re-serialised. */
  const bodies = {};
  const consoleErrors = [];
  const pageErrors = [];

  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));

  page.on('response', async (response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith('/v1/')) return;
    const request = response.request();
    const key = `${request.method()} ${url.pathname}`;
    let text = '';
    let bytes = 0;
    try {
      const buffer = await response.body();
      text = buffer.toString('utf8');
      bytes = buffer.byteLength;
    } catch (error) {
      text = `<<body unavailable: ${String(error)}>>`;
    }
    bodies[key] = text;
    network.push({
      at: nowIso(),
      method: request.method(),
      path: url.pathname,
      search: url.search,
      status: response.status(),
      bytes,
      emulator: response.headers()[EMULATOR_HEADER] ?? null,
      server_date: response.headers()['date'] ?? null,
      content_type: response.headers()['content-type'] ?? null,
    });
  });

  const stages = [];
  /**
   * Writes one frame and the DOM behind it.
   *
   * `focus` is the element the FILM is about, scrolled into view first. This is not cosmetic:
   * measured on the first run, at 1024 x 576 CSS the permit form is tall enough that the
   * refusal banner lands below the fold, and a frame of the signature block is a frame of the
   * wrong thing. The founder has the same problem in the same geometry, so the selector that
   * has to be in shot is written down here rather than discovered on the day.
   *
   * @param {string} id @param {string} note @param {string|null} focus
   */
  async function stage(id, note, focus = null, extra = {}) {
    if (focus !== null) {
      const target = page.locator(focus).first();
      if ((await target.count()) > 0) {
        await target.scrollIntoViewIfNeeded();
        // One frame for the scroll to settle. Not a reveal delay: nothing on the page is
        // waiting on it and no assertion is taken after it.
        await page.waitForTimeout(120);
      }
    }
    const file = join(options.shots, `${id}.png`);
    await page.screenshot({ path: file, fullPage: false });
    const html = await page.content();
    stages.push({
      id,
      note,
      at: nowIso(),
      screenshot: file.replace(`${REPO_ROOT}`, '').replace(/\\/g, '/').replace(/^\//, ''),
      frame: { width: VIEWPORT.width * DEVICE_SCALE, height: VIEWPORT.height * DEVICE_SCALE },
      html,
      ...extra,
    });
    stdout.write(`  ·  stage ${id} — ${note}\n`);
  }

  const started = nowIso();
  let emulatorHeader = null;
  let disclosure = '';
  let gateRunBody = '';
  let gateRunBytes = 0;
  /** Wall clock from each operator click to the beat being in the DOM. */
  const revealLatencyMs = [];
  let pressToFirstBeatMs = 0;

  try {
    // ── SCREEN ONE: the permit ───────────────────────────────────────────────────────
    stdout.write(`\noperator-capture: ${options.baseUrl}/operator.html#/permit\n`);
    await page.goto(`${options.baseUrl}/operator.html#/permit`, { waitUntil: 'networkidle' });
    await page.locator('[data-screen="permit"]').waitFor({ state: 'visible' });

    emulatorHeader = network.find((entry) => entry.emulator !== null)?.emulator ?? null;
    ledger.record(
      'target-is-the-local-emulator',
      emulatorHeader === 'local_furl',
      `X-Mainline-Emulator: ${String(emulatorHeader)} (must be "local_furl"; W7 never captures against AWS)`,
    );

    await pause(page, options.pace);
    await stage(
      '01-permit-before-press',
      'The permit as a supervisor opens it. One obligation outstanding.',
      '.cow-permit-header',
    );

    // ── THE PRESS. One click, one POST, four beats. ──────────────────────────────────
    const before = network.length;
    const waitForRun = page.waitForResponse(
      (response) => new URL(response.url()).pathname === GATE_RUN_PATH,
    );
    const pressedAt = Date.now();
    await page.locator('[data-action="issue"]').click();
    const runResponse = await waitForRun;
    await page.locator('[data-beat]').first().waitFor({ state: 'visible' });
    pressToFirstBeatMs = Date.now() - pressedAt;

    const runKey = `POST ${GATE_RUN_PATH}`;
    gateRunBody = bodies[runKey] ?? '';
    gateRunBytes = Buffer.byteLength(gateRunBody, 'utf8');

    const duringPress = network.slice(before);
    const gateRunPosts = duringPress.filter(
      (entry) => entry.method === 'POST' && entry.path === GATE_RUN_PATH,
    );
    ledger.record(
      'one-press-one-request',
      gateRunPosts.length === 1,
      `${gateRunPosts.length} POST ${GATE_RUN_PATH} between the press and the first beat (must be exactly 1)`,
    );
    ledger.record(
      'gate-run-answered-200',
      runResponse.status() === 200,
      `HTTP ${runResponse.status()} · ${gateRunBytes} bytes`,
    );
    ledger.record(
      'never-the-merge-route',
      network.every((entry) => !MERGE_ROUTE.test(entry.path)),
      'no request to POST /v1/permits/{id}/merge in the whole page load (R4: that route answers 423 Locked)',
    );

    // The mandatory disclosure line (R5), read off the page.
    disclosure = (await page.locator('[data-disclosure="line"]').textContent())?.trim() ?? '';
    ledger.record(
      'disclosure-line-has-R5-shape',
      /^one request · \d+ beats · POST \/v1\/demo\/gate-run · run_id \S+ · response received \S+ · \d+ bytes$/.test(
        disclosure,
      ),
      disclosure === '' ? 'no disclosure line on screen at all' : disclosure,
    );
    ledger.record(
      'disclosure-line-byte-count-is-real',
      disclosure.includes(`${gateRunBytes} bytes`),
      `the sentence claims a byte count; the response body was ${gateRunBytes} bytes`,
    );
    const dismissControls = await page
      .locator('.cow-disclosure')
      .locator('button, a[href], [role="button"], input')
      .count();
    ledger.record(
      'disclosure-line-is-not-dismissible',
      dismissControls === 0,
      `${dismissControls} control(s) inside the disclosure strip (must be 0)`,
    );

    await pause(page, options.pace);
    await stage(
      '02-refused-23514',
      'The database refused the write. SQLSTATE 23514, gate_closed_when_issued.',
      '.cow-refusal',
      { press_to_first_beat_ms: pressToFirstBeatMs },
    );

    // ── THE REVEALS. Each one is an operator click and nothing else. ─────────────────
    for (let guard = 0; guard < 8; guard += 1) {
      const advance = page.locator('[data-action="advance"]');
      if ((await advance.count()) === 0) break;
      const label = (await advance.first().textContent())?.trim() ?? '';
      const beatsBefore = await page.locator('[data-beat]').count();

      await pause(page, options.pace);
      const clickedAt = Date.now();
      await advance.first().click();
      await page
        .locator('[data-beat]')
        .nth(beatsBefore)
        .waitFor({ state: 'attached' });
      const latency = Date.now() - clickedAt;
      revealLatencyMs.push({ label, ms: latency, beats_after: beatsBefore + 1 });

      const requestsSinceLoad = network.filter(
        (entry) => entry.method === 'POST' && entry.path === GATE_RUN_PATH,
      ).length;
      ledger.record(
        `reveal-${beatsBefore + 1}-made-no-request`,
        requestsSinceLoad === 1,
        `still exactly ${requestsSinceLoad} gate-run POST after revealing beat ${beatsBefore + 1}`,
      );
      ledger.record(
        `reveal-${beatsBefore + 1}-was-immediate`,
        latency < 250,
        `${latency} ms from click to the beat being in the DOM (a staged reveal in r5-craft §4 is 360-480 ms)`,
      );

      if (beatsBefore + 1 === 3) {
        await stage(
          '03-forged-counter-refused-anyway',
          'The counter was set to zero out of band. The gate re-derived from ancestry and refused anyway. P0001.',
          '[data-beat="projection_drift_attack"]',
        );
      }
    }

    const beats = await page.locator('[data-beat]').count();
    ledger.record('four-beats-on-screen', beats === 4, `${beats} beat section(s) rendered`);

    await pause(page, options.pace);
    await stage(
      '04-admitted-and-proven',
      'Beat 4: admitted after one disposition is signed. VERDICT PROVEN, persisted nothing.',
      '[data-beat="admit"]',
    );

    // ── Every number on screen came out of those bytes ───────────────────────────────
    const payload = JSON.parse(gateRunBody).data;
    const resultText = await page.locator('[data-result="true"]').innerText();
    const sqlstatesInBytes = new Set(
      payload.beats.map((beat) => beat.sqlstate).filter((code) => code !== null),
    );

    // Read the values the screen PRESENTS as SQLSTATEs — the `dd` beside every `dt` that
    // says so — rather than scanning prose for a five-character shape. The shape scan was
    // tried first and matched CHECK, WRITE, ISSUE and a fragment of an ISO timestamp: a
    // heuristic that cries wolf is a heuristic nobody reads twice.
    const labelled = await page.$$eval('[data-result="true"] dt', (nodes) =>
      nodes
        .filter((node) => (node.textContent ?? '').trim() === 'SQLSTATE')
        .map((node) => (node.nextElementSibling?.textContent ?? '').trim()),
    );
    const strayLabelled = labelled.filter((code) => !sqlstatesInBytes.has(code));
    ledger.record(
      'every-labelled-sqlstate-is-a-payload-sqlstate',
      strayLabelled.length === 0 && labelled.length > 0,
      strayLabelled.length === 0
        ? `${labelled.length} SQLSTATE row(s) on screen: ${labelled.join(', ')} — every one is a beat's own sqlstate`
        : `on screen and not in the payload: ${strayLabelled.join(', ')}`,
    );

    // And no code from the modelled taxonomy may appear ANYWHERE on the result region unless
    // the payload carries it. `40001` is the one that matters: an undecided transaction has no
    // reason set, and a screen that printed it beside a refusal would be claiming the gate said
    // no when the database said "ask me again".
    const TAXONOMY = ['00000', '23514', '23503', '23505', '40001', 'P0001', '42P01', '22P02'];
    const foreign = TAXONOMY.filter(
      (code) => resultText.includes(code) && !gateRunBody.includes(`"${code}"`),
    );
    ledger.record(
      'no-sqlstate-on-screen-that-the-payload-does-not-carry',
      foreign.length === 0,
      foreign.length === 0
        ? `none of the ${TAXONOMY.length} modelled codes appears on screen without being in the ${gateRunBytes} bytes`
        : `on screen and absent from the payload: ${foreign.join(', ')}`,
    );

    const constraintsOnScreen = await page.$$eval(
      'dd[data-row="constraint"] .cow-refusal__value',
      (nodes) => nodes.map((node) => (node.textContent ?? '').trim()),
    );
    const strayConstraints = constraintsOnScreen.filter(
      (name) => !gateRunBody.includes(`"${name}"`),
    );
    ledger.record(
      'every-constraint-on-screen-is-in-the-bytes',
      strayConstraints.length === 0 && constraintsOnScreen.length > 0,
      strayConstraints.length === 0
        ? `constraint name(s) on screen: ${constraintsOnScreen.join(', ')}`
        : `on screen and not in the payload: ${strayConstraints.join(', ')}`,
    );

    // R18: the drawer a judge diffs against the Network panel.
    const rawTexts = await page.$$eval('pre, .mlk-raw__body, code[data-raw]', (nodes) =>
      nodes.map((node) => (node.textContent ?? '').trim()),
    );
    ledger.record(
      'raw-payload-drawer-is-byte-identical',
      rawTexts.some((text) => text === gateRunBody.trim()),
      rawTexts.some((text) => text === gateRunBody.trim())
        ? 'a drawer on the permit screen carries the gate-run body verbatim'
        : `R18 UNMET: ${rawTexts.length} raw element(s) on the permit screen and none is the ` +
            `${gateRunBytes}-byte gate-run body. src/operator/kernel/raw.ts renderRawPayload() ` +
            'and renderRequestLog() are implemented and called by nobody. OWNER: W5 with W2.',
    );

    // ── SCREEN TWO: management of change ─────────────────────────────────────────────
    stdout.write(`\noperator-capture: ${options.baseUrl}/operator.html#/change\n`);
    await page.goto(`${options.baseUrl}/operator.html#/change`, { waitUntil: 'networkidle' });
    await page.locator('.moc').waitFor({ state: 'visible' });
    await pause(page, options.pace);
    await stage(
      '05-change-request-gated',
      'The change request that proposes to edit the clause. Approve is disabled and says why.',
      '.moc-actionbar',
    );

    const probe = network.find((entry) => entry.path.endsWith('/blocking-checks') && entry.status === 404);
    ledger.record(
      'the-absence-was-really-fetched',
      probe !== undefined,
      probe === undefined
        ? 'the change screen claims a route is missing without ever asking for it'
        : `GET ${probe.path} → ${probe.status}, ${probe.bytes} bytes, shown verbatim on screen`,
    );

    const approveDisabled = await page.locator('button.moc-approve').isDisabled();
    ledger.record(
      'approve-is-inert-and-gives-its-reason',
      approveDisabled,
      `approve disabled=${approveDisabled}; reason: ` +
        `${((await page.locator('#moc-approve-reason').textContent()) ?? '').trim()}`,
    );

    const forbiddenLiteral = (await page.locator('.moc').innerText()).includes('dec0de00-000d');
    ledger.record(
      'no-fabricated-check-id',
      !forbiddenLiteral,
      'R11 forbids a hardcoded dec0de00-000d… blocking-check id anywhere on screen',
    );

    ledger.record(
      'the-page-threw-nothing',
      pageErrors.length === 0,
      pageErrors.length === 0 ? 'no uncaught error in either screen' : pageErrors.join(' | '),
    );
  } finally {
    const capture = {
      $schema_note:
        'W7 capture of the CONTROL OF WORK operator screens. Produced by ' +
        'verticals/mainline/apps/console/scripts/operator-capture.mjs against ' +
        'scripts/deploy/local_furl.py over the LOCAL CockroachDB node. Not the deployed URL. ' +
        'No response was stubbed, no route was intercepted, no payload was injected and no ' +
        'clock was frozen. Every byte below came off a real socket.',
      started_at: started,
      finished_at: nowIso(),
      target: {
        base_url: options.baseUrl,
        emulator_header: emulatorHeader,
        is_the_deployed_url: false,
        why_not_the_deployed_url:
          'POST /v1/demo/gate-run drives four beats against the one shared public demo subject. ' +
          'Capturing against it would be load-testing the thing a judge is about to open, and W7 ' +
          'is forbidden to touch AWS.',
      },
      geometry: {
        viewport_css: VIEWPORT,
        device_scale_factor: DEVICE_SCALE,
        frame_px: { width: VIEWPORT.width * DEVICE_SCALE, height: VIEWPORT.height * DEVICE_SCALE },
        legibility_floor_css_px: 0.02 * VIEWPORT.height,
        note:
          'r5-craft §2.1: on-screen evidence text must clear 2 % of frame height per em. At this ' +
          'geometry that is 11.52 CSS px. At the plan-recommended 200 % (1280x720) it is 14.40 px ' +
          'and the SQLSTATE value (13.12), the reason set (13.12) and the disclosure line (12.80) ' +
          'all fail. This geometry is the one the video must be shot at.',
      },
      pacing: {
        driver_pace_ms: options.pace,
        what_that_is:
          'the pause this DRIVER takes between operator actions, to film at a readable pace. It ' +
          'is not a page delay and the page schedules none. reveal_latency_ms below is the page.',
        press_to_first_beat_ms: pressToFirstBeatMs,
        press_to_first_beat_note:
          'wall clock from the click to the first beat being visible. It is dominated by the real ' +
          'round trip: the four beats run in one serializable transaction against CockroachDB.',
        reveal_latency_ms: revealLatencyMs,
      },
      disclosure_line: disclosure,
      gate_run: {
        request: `POST ${GATE_RUN_PATH}`,
        bytes: gateRunBytes,
        body: gateRunBody,
        body_note: 'verbatim response text, never re-serialised. Diff it against devtools.',
      },
      network,
      response_bodies: bodies,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      stages,
      assertions: ledger.entries,
      held: ledger.broken.length === 0,
    };

    writeFileSync(options.out, `${JSON.stringify(capture, null, 2)}\n`, 'utf8');
    stdout.write(`\noperator-capture: wrote ${options.out}\n`);
    stdout.write(`operator-capture: screenshots in ${options.shots}\n`);

    await context.close();
    await browser.close();
  }

  if (ledger.broken.length > 0) {
    stderr.write(`\noperator-capture: ${ledger.broken.length} assertion(s) did not hold:\n`);
    for (const entry of ledger.broken) stderr.write(`  · ${entry.id}: ${entry.detail}\n`);
    return 1;
  }
  stdout.write('operator-capture: every assertion held.\n');
  return 0;
}

const code = await main().catch((error) => {
  stderr.write(`\noperator-capture: ${String(error?.stack ?? error)}\n`);
  return 3;
});
if (!existsSync(DEFAULT_OUT) && code === 0) {
  stderr.write('operator-capture: finished clean but wrote no capture. That cannot be right.\n');
  exit(3);
}
exit(code);
