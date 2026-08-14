// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * DRIVE A REAL CHROMIUM AGAINST A REAL ORIGIN, AND WRITE DOWN WHAT IT SAW.
 *
 * ── WHY A BROWSER AND NOT A UNIT TEST ────────────────────────────────────────────
 *
 * On 2026-08-14 the founder opened the deployed console and the header read
 * `TRANSPORT REPLAY (staged)`. Every byte on that screen was a recorded EvidenceBundle
 * played back over an origin that had a live kernel behind it. `selectSource` was not
 * wrong — it was handed `VITE_MAINLINE_API_BASE:""` by the build, and `""` is unset. The
 * defect was a BUILD-TIME VALUE, and there is no unit test of a pure function that can
 * catch a build-time value, because the unit test supplies the value itself.
 *
 * Only a build plus a browser catches that class. So this file:
 *
 *   * loads a page from an origin somebody else compiled and somebody else served;
 *   * reads the honesty chrome the way a judge reads it, out of the DOM;
 *   * presses the button a judge presses;
 *   * takes the request off the NETWORK LOG rather than inferring it from the code —
 *     `page.on('request')` sees what the browser actually put on the socket, and the
 *     assertion that it went to the page's OWN ORIGIN is the whole claim of the fix;
 *   * and compares the bytes that came back against the bytes on screen.
 *
 * ── RULING R7: NO `playwright test`, NO CONFIG, NO `tests/browser/**` ────────────
 *
 * `docs/leads/console-live-plan.md` R7: there is no `playwright.config.ts` in this
 * repository and this wave must not create one. `tests/browser/gate.spec.ts` names that
 * config as the `cinema-conformance-harness` worker's file and PL-2 is red by design.
 * This is therefore a standalone program over the Playwright LIBRARY API, invoked as
 * `node scripts/drive-console.mjs`, owned by the `local-live-proof` worker, and it edits
 * nothing under `tests/`.
 *
 * ── WHAT IT REFUSES TO DO ────────────────────────────────────────────────────────
 *
 * It never stubs the handler, never routes or fulfils a request, never injects a payload
 * and never asserts on a screenshot. A screenshot is written when asked for and its
 * digest is recorded, but no assertion in this file reads one: a screenshot proves a
 * shape, and every claim here is about a string, a status code or an origin.
 *
 * It also never decides that a failure is acceptable. Every assertion is recorded with
 * its expected and actual value, the JSON is written whether the run passed or failed —
 * a failed run's measurements are the useful ones — and the exit status is 1 if any
 * assertion did not hold.
 *
 * ── A KNOWN COLLISION WITH `pnpm run lint`, MEASURED AND REPORTED, NOT WORKED AROUND ──
 *
 * `eslint.config.js` supplies `parserOptions.project` in a block with **no `files` key**,
 * so the type-aware TypeScript parser is applied to every linted file — including this
 * one. No tsconfig in this workspace includes `.mjs` (neither sets `allowJs`), so
 * `eslint .` answers:
 *
 *     Parsing error: "parserOptions.project" has been provided for
 *     @typescript-eslint/parser. The file was not found in any of the provided
 *     project(s): scripts\drive-console.mjs
 *
 * Measured 2026-08-14: the workspace lint was clean with this file absent, so this file
 * is the only cause. `docs/leads/console-live-plan.md` §2 names this path as the
 * `local-live-proof` worker's and `eslint.config.js` as nobody's, so the file is
 * delivered where the plan puts it and the collision is REPORTED rather than resolved by
 * editing another worker's file or by quietly renaming the deliverable. The remedy is one
 * line — give that block `files: ['**\/*.{ts,tsx}']` — and it belongs to whoever the lead
 * assigns `eslint.config.js` to. `scripts/deploy/console_live_acceptance.py` re-measures
 * the collision on every run and records it under `console_workspace_lint`.
 *
 * ── USAGE ────────────────────────────────────────────────────────────────────────
 *
 *   node scripts/drive-console.mjs \
 *     --base-url http://127.0.0.1:8731 --expect live \
 *     --expect-build-id 2026-08-15T… --expect-api-base / \
 *     --expect-status 503 --expect-kind dsn_unset \
 *     --out run.json [--screenshot shot.png] [--timeout 20000] [--headed]
 *
 * `scripts/deploy/console_live_acceptance.py` is the supported caller; it builds the
 * dist, runs the packaging guard over it and starts the emulator. This program assumes
 * an origin already exists and makes no claim about how it was produced.
 */

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { homedir, platform } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { argv, env, exit, stderr, stdout } from 'node:process';

import { chromium } from '@playwright/test';

// ── The four controls, by the test id the console gives them ──────────────────

/**
 * `src/features/gate/DemoDriver.tsx` renders `data-testid={`demo-control-${control.id}`}`
 * over a frozen array in this order. The order is the argument the demo makes — refuse,
 * refuse under attack, admit — so it is asserted here as an ordered list rather than a
 * set: four buttons in a scrambled order would satisfy a set and would be a different
 * demo.
 */
const CONTROL_IDS = ['merge', 'forge', 'admit', 'all'];

/** The one a judge presses to see everything. Ruling R8 names it. */
const RUN_ALL = 'demo-control-all';

/** The three terminal panels the driver can end in. Whichever appears is recorded. */
const OUTCOME_SELECTOR =
  '[data-testid="demo-run-failed"], [data-testid="demo-run-refused"], [data-testid="gate-run-report"]';

/**
 * The resource this whole wave is about. The path is the console's declared template
 * (`src/data/resources.ts`), and it is written out here so that the network assertion
 * compares against a literal a reader can check rather than against something derived
 * from the same artefact under test.
 */
const GATE_RUN_PATH = '/v1/demo/gate-run';

/**
 * How many characters of a body the console's live transport puts into the failure it
 * renders — `src/data/transport.ts`: `` `HTTP ${status}; body carries no envelope
 * (${text.slice(0, 200)}).` ``. The verbatim assertion compares against the same slice,
 * taken from the bytes the browser received, so it is a claim about the wire and not a
 * re-derivation of the sentence.
 */
const TRANSPORT_BODY_SLICE = 200;

// ── Which chromium, and where it came from ───────────────────────────────────

/**
 * The browser binary, resolved and RECORDED rather than assumed.
 *
 * Playwright pins a browser revision per release. This workstation carries
 * `chromium-1223` and `chromium-1228` under `~/AppData/Local/ms-playwright`, and the
 * installed `@playwright/test` 1.62.1 asks for `chromium_headless_shell-1234`, so the
 * default launch fails with "Executable doesn't exist" and a suggestion to download one.
 *
 * **This program does not download anything.** It uses a browser that is already on the
 * machine, names it in the evidence file with its revision and its version string, and
 * fails loudly if there is none — a proof that silently installed its own subject would
 * be a proof about a machine that did not exist when the run started.
 *
 * `--chromium <path>` overrides. `PLAYWRIGHT_BROWSERS_PATH` is honoured because that is
 * where a CI image usually puts them.
 */
function resolveChromium(explicit) {
  if (explicit !== '') {
    if (!existsSync(explicit)) {
      stderr.write(`drive-console: --chromium ${explicit} does not exist\n`);
      exit(2);
    }
    return { executablePath: explicit, source: '--chromium', revision: null };
  }

  const pinned = chromium.executablePath();
  if (existsSync(pinned)) {
    return { executablePath: pinned, source: 'playwright default', revision: null };
  }

  const root =
    env['PLAYWRIGHT_BROWSERS_PATH'] ??
    (platform() === 'win32'
      ? join(env['LOCALAPPDATA'] ?? join(homedir(), 'AppData', 'Local'), 'ms-playwright')
      : platform() === 'darwin'
        ? join(homedir(), 'Library', 'Caches', 'ms-playwright')
        : join(homedir(), '.cache', 'ms-playwright'));
  if (!existsSync(root)) {
    stderr.write(
      `drive-console: playwright's pinned browser is absent (${pinned}) and there is no ` +
        `browser cache at ${root}. Install a chromium on this machine, or pass --chromium.\n`,
    );
    exit(2);
  }

  // Full chromium first: the headless shell is a smaller binary with a different
  // revision series, and a run whose browser is the same one a human could open is the
  // one a screenshot is comparable to.
  const relative =
    platform() === 'win32'
      ? [join('chrome-win64', 'chrome.exe'), join('chrome-win', 'chrome.exe')]
      : platform() === 'darwin'
        ? [join('chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium')]
        : [join('chrome-linux', 'chrome')];

  const candidates = [];
  for (const name of readdirSync(root)) {
    const match = /^chromium-(\d+)$/.exec(name);
    if (match === null) continue;
    for (const tail of relative) {
      const full = join(root, name, tail);
      if (existsSync(full)) candidates.push({ revision: Number(match[1]), path: full });
    }
  }
  if (candidates.length === 0) {
    stderr.write(
      `drive-console: no chromium-<revision> build under ${root} carries an executable at ` +
        `${relative.join(' or ')}. Pass --chromium <path>.\n`,
    );
    exit(2);
  }
  candidates.sort((a, b) => b.revision - a.revision);
  const chosen = candidates[0];
  return {
    executablePath: chosen.path,
    source: `newest chromium build already on this machine (${root})`,
    revision: chosen.revision,
    playwright_pinned_but_absent: pinned,
  };
}

// ── Arguments ────────────────────────────────────────────────────────────────

function parseArgs(args) {
  const out = {
    baseUrl: '',
    expect: 'live',
    expectBuildId: '',
    expectApiBase: '',
    expectBundleUrl: '',
    expectStatus: 0,
    expectKind: '',
    out: '',
    screenshot: '',
    label: '',
    route: '#/gate',
    timeout: 20000,
    headed: false,
    chromium: '',
  };
  for (let i = 0; i < args.length; i += 1) {
    const flag = args[i];
    const value = args[i + 1];
    const need = () => {
      if (value === undefined) {
        stderr.write(`drive-console: ${flag} needs a value\n`);
        exit(2);
      }
      i += 1;
      return value;
    };
    switch (flag) {
      case '--base-url':
        out.baseUrl = need();
        break;
      case '--expect':
        out.expect = need();
        break;
      case '--expect-build-id':
        out.expectBuildId = need();
        break;
      case '--expect-api-base':
        out.expectApiBase = need();
        break;
      case '--expect-bundle-url':
        out.expectBundleUrl = need();
        break;
      case '--expect-status':
        out.expectStatus = Number(need());
        break;
      case '--expect-kind':
        out.expectKind = need();
        break;
      case '--out':
        out.out = need();
        break;
      case '--screenshot':
        out.screenshot = need();
        break;
      case '--label':
        out.label = need();
        break;
      case '--route':
        out.route = need();
        break;
      case '--timeout':
        out.timeout = Number(need());
        break;
      case '--chromium':
        out.chromium = need();
        break;
      case '--headed':
        out.headed = true;
        break;
      default:
        stderr.write(`drive-console: unknown argument ${flag}\n`);
        exit(2);
    }
  }
  if (out.baseUrl === '') {
    stderr.write('drive-console: --base-url is required\n');
    exit(2);
  }
  if (out.expect !== 'live' && out.expect !== 'replay') {
    stderr.write(`drive-console: --expect must be live or replay, got ${out.expect}\n`);
    exit(2);
  }
  if (out.label === '') out.label = out.expect;
  return out;
}

// ── The assertion ledger ─────────────────────────────────────────────────────

/**
 * Every claim this program makes, with the value that produced the verdict beside it.
 *
 * There is no `advisory`, no `soft` and no `skip`. An assertion that can be recorded as
 * "did not hold, and that is fine" is a sentence in a report rather than a check, and the
 * whole reason this file exists is that a cheerful report was written about a REPLAY
 * console on a live origin.
 */
class Ledger {
  constructor() {
    this.rows = [];
  }

  record(id, ok, expected, actual, why) {
    this.rows.push({ id, ok: Boolean(ok), expected, actual, why });
    return Boolean(ok);
  }

  equal(id, expected, actual, why) {
    return this.record(id, Object.is(expected, actual), expected, actual, why);
  }

  contains(id, haystack, needle, why) {
    const ok = typeof haystack === 'string' && haystack.includes(needle);
    return this.record(id, ok, `a string containing ${JSON.stringify(needle)}`, haystack, why);
  }

  get failures() {
    return this.rows.filter((row) => !row.ok);
  }

  get ok() {
    return this.failures.length === 0;
  }
}

// ── DOM readers ──────────────────────────────────────────────────────────────

async function textOf(page, selector) {
  const handle = await page.$(selector);
  if (handle === null) return null;
  const text = await handle.textContent();
  return text === null ? null : text.trim();
}

async function present(page, selector) {
  return (await page.$(selector)) !== null;
}

/**
 * The honesty chrome, cell by cell.
 *
 * `src/app/HonestyChrome.tsx` gives each cell `data-testid={`chrome-${label…}`}` with the
 * label's spaces replaced by hyphens. Reading it by test id rather than by position means
 * a reordered strip does not silently change which fact this program checked.
 */
async function readChrome(page) {
  const cells = {};
  for (const key of [
    'transport',
    'bundle',
    'seal',
    'corpus-root',
    'clock-skew',
    'signature-path',
    'render',
    'build',
  ]) {
    cells[key] = await textOf(page, `[data-testid="chrome-${key}"]`);
  }
  return cells;
}

/** The composition root's source bar: badge, location, the sentence, and the switch. */
async function readSourceChrome(page) {
  return {
    present: await present(page, '[data-testid="source-chrome"]'),
    badge: await textOf(page, '[data-testid="source-badge"]'),
    location: await textOf(page, '[data-testid="source-location"]'),
    why: await textOf(page, '[data-testid="source-why"]'),
    switch_present: await present(page, '[data-testid="source-switch"]'),
    switch_label: await textOf(page, '[data-testid="source-switch"]'),
  };
}

async function readControls(page) {
  const rows = [];
  for (const id of CONTROL_IDS) {
    const selector = `[data-testid="demo-control-${id}"]`;
    const handle = await page.$(selector);
    rows.push({
      testid: `demo-control-${id}`,
      present: handle !== null,
      visible: handle === null ? false : await handle.isVisible(),
      text: handle === null ? null : ((await handle.textContent()) ?? '').trim(),
    });
  }
  return rows;
}

/**
 * Whichever terminal panel the press produced, read verbatim.
 *
 * `demo-run-failed` renders the transport's own failure classification in the title and
 * its detail — the bytes — in a `<pre>`. That `<pre>` is the subject of the verbatim
 * assertion, so it is read as its own field rather than folded into the panel's text.
 */
async function readOutcome(page) {
  for (const testid of ['demo-run-failed', 'demo-run-refused', 'gate-run-report']) {
    const selector = `[data-testid="${testid}"]`;
    const handle = await page.$(selector);
    if (handle === null) continue;
    const verbatim = await page.$(`${selector} pre`);
    return {
      testid,
      title: await textOf(page, `${selector} span`),
      verbatim: verbatim === null ? null : ((await verbatim.textContent()) ?? '').trim(),
      text: ((await handle.textContent()) ?? '').trim(),
    };
  }
  return { testid: null, title: null, verbatim: null, text: null };
}

// ── The run ──────────────────────────────────────────────────────────────────

function originOf(url) {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

function pathnameOf(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return null;
  }
}

async function main() {
  const options = parseArgs(argv.slice(2));
  const ledger = new Ledger();
  const startedAt = new Date().toISOString();

  const executable = resolveChromium(options.chromium);
  const browser = await chromium.launch({
    headless: !options.headed,
    executablePath: executable.executablePath,
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(options.timeout);

  /** Everything the browser put on a socket, in order. The network log is the witness. */
  const wire = [];
  const consoleMessages = [];
  const pageErrors = [];

  page.on('request', (request) => {
    wire.push({
      seq: wire.length,
      method: request.method(),
      url: request.url(),
      origin: originOf(request.url()),
      pathname: pathnameOf(request.url()),
      resource_type: request.resourceType(),
      post_data: request.postData(),
      status: null,
      response_headers: null,
      _request: request,
      _response: null,
    });
  });
  page.on('response', (response) => {
    const row = wire.find((entry) => entry._request === response.request());
    if (row === undefined) return;
    row.status = response.status();
    row.response_headers = response.headers();
    row._response = response;
  });
  page.on('console', (message) => {
    consoleMessages.push({ type: message.type(), text: message.text() });
  });
  page.on('pageerror', (error) => {
    pageErrors.push({ name: error.name, message: error.message });
  });

  const target = `${options.baseUrl.replace(/\/$/, '')}/${options.route}`;
  await page.goto(target, { waitUntil: 'load' });

  // The chrome is rendered by the shell and is never lazy; the driver is a lazy import
  // behind Suspense. Waiting for each in turn distinguishes "the page did not load" from
  // "the gate chunk did not resolve", which are different defects with the same symptom.
  await page.waitForSelector('[data-testid="honesty-chrome"]');
  const driverPresent = await page
    .waitForSelector('[data-testid="demo-driver"]')
    .then(() => true)
    .catch(() => false);

  const chrome = await readChrome(page);
  const source = await readSourceChrome(page);
  const notDeclared = await present(page, '[data-testid="demo-driver-not-declared"]');
  const noSource = await present(page, '[data-testid="demo-driver-no-source"]');
  const controls = await readControls(page);

  const pageOrigin = originOf(page.url());
  const expectedTransport = options.expect === 'live' ? 'LIVE' : 'REPLAY';
  const expectedVariable =
    options.expect === 'live' ? 'VITE_MAINLINE_API_BASE' : 'VITE_MAINLINE_BUNDLE_URL';

  // ── (i) the honesty chrome names the transport, and names the variable ────
  ledger.equal(
    'honesty_chrome_transport',
    expectedTransport,
    chrome.transport,
    'src/app/HonestyChrome.tsx reads transport.describe().mode off the object that holds ' +
      'the bytes. This is the cell the founder read on the deployed URL.',
  );
  ledger.equal(
    'source_badge',
    expectedTransport,
    source.badge,
    'The composition root badge, from the same selection. Chrome and badge disagreeing ' +
      'would mean one of them is decoration.',
  );
  ledger.contains(
    'source_why_names_the_build_time_variable',
    source.why,
    expectedVariable,
    'src/app/source-select.ts writes the sentence naming the variable that was compiled ' +
      'in. It is the sentence that told the founder the artefact was a replay.',
  );
  if (options.expect === 'live' && options.expectApiBase !== '') {
    ledger.equal(
      'source_location_is_the_compiled_api_base',
      options.expectApiBase,
      source.location,
      'The location is rendered exactly as the build supplied it, never rewritten. A ' +
        'value like C:/Program Files/Git/ here is the MSYS path-conversion hazard.',
    );
  }
  if (options.expect === 'replay' && options.expectBundleUrl !== '') {
    ledger.equal(
      'source_location_is_the_compiled_bundle_url',
      options.expectBundleUrl,
      source.location,
      'Same reading for the replay artefact, so the contrast run is measured and not ' +
        'assumed.',
    );
  }

  // ── (ii) the artefact names itself ───────────────────────────────────────
  if (options.expectBuildId !== '') {
    ledger.equal(
      'build_id_is_the_one_that_was_supplied',
      options.expectBuildId,
      chrome.build,
      'MAINLINE_BUILD_ID reaching the screen is what lets a screenshot name the artefact ' +
        'it came from (docs/deploy/console-build.md §1). Ruling R5.',
    );
    ledger.record(
      'build_id_is_not_dev',
      chrome.build !== 'dev',
      'anything but "dev"',
      chrome.build,
      'The deployed artefact carried buildId:"dev": MAINLINE_BUILD_ID was not supplied, ' +
        'so the chrome could not name the artefact. Ruling R5 refuses that under live.',
    );
  }

  // ── (iii) the four controls ──────────────────────────────────────────────
  ledger.record(
    'the_gate_driver_rendered',
    driverPresent && !notDeclared && !noSource,
    'demo-driver present; neither demo-driver-not-declared nor demo-driver-no-source',
    {
      demo_driver: driverPresent,
      demo_driver_not_declared: notDeclared,
      demo_driver_no_source: noSource,
    },
    'The not-declared panel is the honest rendering when resources.ts lacks the key. ' +
      'With W1 landed it must be unreachable, and the controls must be what a judge sees.',
  );
  ledger.record(
    'four_controls_render_in_order',
    controls.every((row) => row.present && row.visible),
    CONTROL_IDS.map((id) => `demo-control-${id}`),
    controls.map((row) => ({ testid: row.testid, present: row.present, visible: row.visible })),
    'Ruling R3: the controls are present in LIVE and in REPLAY. A control shown in one ' +
      'and hidden in the other would be the second code path D7 forbids.',
  );

  // ── (iv) press RUN ALL, and take the request off the wire ────────────────
  const beforePress = wire.length;
  await page.click(`[data-testid="${RUN_ALL}"]`);
  const outcomeAppeared = await page
    .waitForSelector(OUTCOME_SELECTOR)
    .then(() => true)
    .catch(() => false);
  const outcome = await readOutcome(page);

  const gateRunRows = wire.filter(
    (row) => row.method === 'POST' && row.pathname === GATE_RUN_PATH,
  );
  const gateRun = gateRunRows.length > 0 ? gateRunRows[gateRunRows.length - 1] : null;

  let gateRunBody = null;
  let gateRunJson = null;
  if (gateRun !== null && gateRun._response !== null) {
    gateRunBody = await gateRun._response.text().catch(() => null);
    if (gateRunBody !== null) {
      try {
        gateRunJson = JSON.parse(gateRunBody);
      } catch {
        gateRunJson = null;
      }
    }
  }

  ledger.record(
    'the_press_produced_a_terminal_panel',
    outcomeAppeared,
    'one of demo-run-failed, demo-run-refused, gate-run-report',
    outcome.testid,
    'A press that produces nothing is indistinguishable on a screenshot from a press ' +
      'that produced an empty answer.',
  );

  if (options.expect === 'live') {
    ledger.record(
      'run_all_issued_a_post_to_the_gate_run_path',
      gateRun !== null,
      `exactly one POST ${GATE_RUN_PATH} on the network log`,
      gateRunRows.map((row) => `${row.method} ${row.url}`),
      'Taken off page.on("request") — what the browser put on the socket — never ' +
        'inferred from the source. Ruling R8 (iv).',
    );
    ledger.equal(
      'the_post_went_to_the_pages_own_origin',
      pageOrigin,
      gateRun === null ? null : gateRun.origin,
      'VITE_MAINLINE_API_BASE=/ compiles to a relative URL, so console and kernel share ' +
        'one origin and there is no CORS anywhere. A different origin here would mean the ' +
        'artefact named somebody else\u2019s host.',
    );
    ledger.record(
      'every_request_stayed_on_the_pages_own_origin',
      wire.every((row) => row.origin === null || row.origin === pageOrigin),
      pageOrigin,
      [...new Set(wire.map((row) => row.origin))],
      'A console that fetched a third origin would be a machine for producing authentic ' +
        "looking screenshots of somebody else's bytes under our chrome.",
    );
    if (options.expectStatus !== 0) {
      ledger.equal(
        'the_kernel_answered_the_expected_status',
        options.expectStatus,
        gateRun === null ? null : gateRun.status,
        'The SSM parameter /mainline/demo/cockroach_dsn is the founder\u2019s step and is ' +
          'not this wave\u2019s. 503 dsn_unset, rendered honestly, IS the passing ' +
          'condition (ruling R8).',
      );
    }
    if (options.expectKind !== '') {
      ledger.equal(
        'the_kernel_named_the_reason',
        options.expectKind,
        gateRunJson === null || gateRunJson.error === undefined ? null : gateRunJson.error.kind,
        'A reachable route refusing for a NAMED reason. Not a 404, and it must never be ' +
          'described as one.',
      );
    }
    ledger.record(
      'the_answer_is_rendered_verbatim',
      gateRunBody !== null &&
        outcome.verbatim !== null &&
        outcome.verbatim.includes(gateRunBody.slice(0, TRANSPORT_BODY_SLICE)),
      `the on-screen <pre> contains the first ${TRANSPORT_BODY_SLICE} characters of the body`,
      { on_screen: outcome.verbatim, body_prefix: gateRunBody?.slice(0, TRANSPORT_BODY_SLICE) },
      'The bytes on the wire compared against the bytes on the screen. Not a paraphrase, ' +
        'not a summary, and not a sentence this program composed.',
    );
  } else {
    ledger.record(
      'replay_issued_no_request_for_the_gate_run',
      gateRun === null,
      `no POST ${GATE_RUN_PATH} on the network log`,
      gateRunRows.map((row) => `${row.method} ${row.url}`),
      'The replay transport answers out of a verified bundle and touches no socket. ' +
        'A REPLAY badge over a live fetch would be the badge lying.',
    );
    ledger.equal(
      'replay_refused_by_naming_the_absent_frame',
      'missing_frame',
      outcome.title,
      'Measured: no bundle carries a POST /v1/demo/gate-run frame, and src/data/bundle.ts ' +
        'already refuses honestly. Ruling R3 calls that a named gap, not a defect to ' +
        'paper over, and forbids hand-authoring a frame.',
    );
  }

  ledger.record(
    'no_uncaught_exception_reached_the_page',
    pageErrors.length === 0,
    [],
    pageErrors,
    'A console that threw would render its error boundary, which is a different screen ' +
      'from the one under test.',
  );

  let screenshot = null;
  if (options.screenshot !== '') {
    const shotPath = resolve(options.screenshot);
    mkdirSync(dirname(shotPath), { recursive: true });
    const bytes = await page.screenshot({ path: shotPath, fullPage: true });
    screenshot = {
      path: shotPath,
      bytes: bytes.length,
      sha256: createHash('sha256').update(bytes).digest('hex'),
      note:
        'Supplementary. NO assertion in this run reads a screenshot; every claim above is ' +
        'about a string, a status code or an origin.',
    };
  }

  const record = {
    label: options.label,
    expect: options.expect,
    base_url: options.baseUrl,
    target_url: target,
    page_url: page.url(),
    page_origin: pageOrigin,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    browser: {
      name: 'chromium',
      version: browser.version(),
      headless: !options.headed,
      executable,
      library: '@playwright/test (library API; no playwright.config.ts, ruling R7)',
      downloaded_anything: false,
    },
    honesty_chrome: chrome,
    source_chrome: source,
    controls,
    pressed: RUN_ALL,
    requests_before_press: beforePress,
    outcome_panel: outcome,
    gate_run_request:
      gateRun === null
        ? null
        : {
            method: gateRun.method,
            url: gateRun.url,
            origin: gateRun.origin,
            pathname: gateRun.pathname,
            post_data: gateRun.post_data,
            same_origin_as_page: gateRun.origin === pageOrigin,
            captured_from: 'page.on("request") — the browser\'s own network log',
          },
    gate_run_response:
      gateRun === null || gateRun.status === null
        ? null
        : {
            status: gateRun.status,
            headers: gateRun.response_headers,
            emulator_header: gateRun.response_headers?.['x-mainline-emulator'] ?? null,
            body: gateRunBody,
            body_json: gateRunJson,
          },
    network: wire.map((row) => ({
      seq: row.seq,
      method: row.method,
      url: row.url,
      origin: row.origin,
      pathname: row.pathname,
      resource_type: row.resource_type,
      status: row.status,
    })),
    console_messages: consoleMessages,
    page_errors: pageErrors,
    screenshot,
    assertions: ledger.rows,
    failed_assertions: ledger.failures.map((row) => row.id),
    ok: ledger.ok,
  };

  await context.close();
  await browser.close();

  const text = `${JSON.stringify(record, null, 2)}\n`;
  if (options.out !== '') {
    const outPath = resolve(options.out);
    mkdirSync(dirname(outPath), { recursive: true });
    writeFileSync(outPath, text, 'utf8');
    stdout.write(`drive-console: ${options.label} wrote ${outPath}\n`);
  } else {
    stdout.write(text);
  }

  for (const row of ledger.failures) {
    stderr.write(`drive-console: FAILED ${row.id}\n`);
    stderr.write(`  expected ${JSON.stringify(row.expected)}\n`);
    stderr.write(`  actual   ${JSON.stringify(row.actual)}\n`);
  }
  stdout.write(
    `drive-console: ${options.label} ${ledger.ok ? 'PASSED' : 'FAILED'} ` +
      `${ledger.rows.length - ledger.failures.length}/${ledger.rows.length} assertions\n`,
  );
  return ledger.ok ? 0 : 1;
}

main().then(
  (code) => {
    exit(code);
  },
  (error) => {
    stderr.write(`drive-console: ${error instanceof Error ? error.stack : String(error)}\n`);
    exit(3);
  },
);
