// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PLAYWRIGHT CONFIG — added by W7, and declared here as an addition to the file list.
 *
 * ── WHY THIS FILE EXISTS AT ALL, SAID PLAINLY ────────────────────────────────────────
 *
 * `package.json` has carried `"test:browser": "playwright test"` since the console was
 * created, and no config has ever existed beside it. With no config Playwright takes the
 * working directory as `testDir` and its default `testMatch` collects
 * `**\/*.@(spec|test).?(c|m)[jt]s?(x)` — which sweeps up all of `tests/unit/**`, where every
 * file imports Vitest. `pnpm run test:browser` therefore does not run the browser tier
 * today; it errors out on the unit tier. `operator-systems-plan.md` §4 gives W7 three
 * Playwright specs and requires them to run under that command, so the command has to work.
 *
 * `eslint.config.js:316` already names `playwright.config.ts` in its Node-tooling override.
 * The file the repository was already configured for is the file that was missing.
 *
 * `docs/leads/console-live-plan.md` R7 forbade creating this file **in that wave**, whose
 * subject was `scripts/drive-console.mjs`; its stated reason was that the config belonged to
 * the `cinema-conformance-harness` worker, who never landed it. That ruling is not repeated
 * anywhere in `operator-systems-plan.md`, and W7's brief overrides it for this wave. It is
 * named here rather than quietly stepped over.
 *
 * ── WHAT IT DELIBERATELY DOES NOT DO ─────────────────────────────────────────────────
 *
 * It collects **only** `operator-*.spec.ts`. The five older specs in this directory —
 * `ancestry-walk`, `audit`, `custody`, `diff`, `gate`, `propagation`, `silence` — are red by
 * design (`gate.spec.ts` §PL-2 says so in its own header: they need a `baseURL` onto the
 * built console and a composed `BundleTransport` + verifier that the shell does not yet
 * provide). Collecting them here would turn `pnpm run test:browser` red for reasons that
 * have nothing to do with the operator surface, and marking them skipped would be worse:
 * a skip reads as "handled". They are left exactly as they are — uncollected, unclaimed,
 * and named in this comment so that whoever revives them adds a second project rather than
 * discovering the omission.
 *
 * ── THE TARGET IS ALWAYS THE LOCAL EMULATOR, NEVER THE DEPLOYED URL ──────────────────
 *
 * `scripts/deploy/local_furl.py` runs the real `mainline_demo_api.app.handler` in-process
 * over the local CockroachDB node and stamps `X-Mainline-Emulator: local_furl` on every
 * response. Nothing in this config, and nothing in the operator specs, may be pointed at
 * `*.lambda-url.*.on.aws`: the deployed subject is a single shared public row and a spec
 * suite hammering `POST /v1/demo/gate-run` at it is a spec suite doing load testing on the
 * thing a judge is about to open. `operator-network-honesty.spec.ts` asserts the emulator
 * header is present, which makes a run against the deployment fail loudly rather than
 * silently succeed.
 *
 * ── THE FILMING CONFIGURATION IS THE TEST CONFIGURATION ──────────────────────────────
 *
 * 1024 x 576 CSS at `deviceScaleFactor: 2.5` renders a 2560 x 1440 frame. That is
 * r5-craft §2.1's "175-200 % browser zoom at 1440p", pushed to 250 % because W7's 480-test
 * measurement found the SQLSTATE value, the constraint name, the reason set and the
 * mandatory disclosure line all BELOW the 2 %-of-frame-height floor at 200 %. Testing at
 * the geometry we film at is the only way a legibility assertion means anything.
 */

import { defineConfig, devices } from '@playwright/test';

/** The emulator's default port in `scripts/deploy/local_furl.py` is 8731; W7 uses 8741. */
const PORT = Number(process.env['MAINLINE_OPERATOR_PORT'] ?? 8741);

/**
 * Where the operator specs point. Overridable so a rehearsal on another port works, but the
 * default is loopback and the specs refuse anything without the emulator header anyway.
 */
const BASE_URL = process.env['MAINLINE_OPERATOR_BASE_URL'] ?? `http://127.0.0.1:${PORT}`;

/** The repository root, four levels up from `verticals/mainline/apps/console`. */
const REPO_ROOT = new URL('../../../../', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');

/**
 * The interpreter that has `psycopg` installed. `uv` is not on PATH on this machine, so the
 * venv is addressed directly and the variable exists for CI to point elsewhere.
 */
const PYTHON =
  process.env['MAINLINE_PYTHON'] ??
  (process.platform === 'win32' ? `${REPO_ROOT}.venv/Scripts/python.exe` : `${REPO_ROOT}.venv/bin/python`);

/**
 * The local node, and the database the demo world is seeded into.
 *
 * Not a credential: `root` over loopback on an insecure single-node container. The seeded
 * world lives in `mainline_demo`, NOT in `defaultdb` — measured 2026-08-15, `defaultdb` on
 * this node has no `mainline` schema at all and `/v1/demo/subjects` answers 500 against it.
 */
const DSN = process.env['MAINLINE_DSN'] ?? 'postgresql://root@localhost:26257/defaultdb?sslmode=disable';
const DATABASE = process.env['MAINLINE_DEMO_DATABASE'] ?? 'mainline_demo';

/**
 * The seeded permit. `gate_run.py` resolves its subject from `$MAINLINE_DEMO_PERMIT_ID` and
 * answers `422 demo_history_not_seeded` without it — which is the endpoint being honest, not
 * a failure to route.
 */
const PERMIT_ID =
  process.env['MAINLINE_DEMO_PERMIT_ID'] ?? 'dec0de00-0006-4000-8000-000000000001';

export default defineConfig({
  testDir: './tests/browser',
  // Only W7's specs. See the header for why the other seven are not collected here.
  testMatch: /operator-.*\.spec\.ts$/,

  // The emulator caches ONE psycopg connection at module scope and `--concurrency
  // serialized` puts the handler behind one lock. Parallel workers would queue behind that
  // lock and time out; one worker is the faithful shape, not a workaround.
  workers: 1,
  fullyParallel: false,

  // A `.only` left in a spec must not silently shrink the suite in CI.
  forbidOnly: Boolean(process.env['CI']),
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },

  /**
   * `out/` and not Playwright's conventional `test-results/`, deliberately.
   *
   * `.gitignore` covers `out/` at any depth and does NOT cover `test-results/` or
   * `playwright-report/`. Its own longest comment is about `collected.txt` — a build output
   * committed by accident in `eefae1c`, which reddened the REUSE gate because a scratch dump
   * names no licence and must not be given one. Traces, screenshots and a JUnit file are the
   * same class of artefact, and the default directory would put them one `git commit -A`
   * away from the same failure. Writing them somewhere already ignored removes the hazard
   * rather than relying on the next person to notice.
   *
   * The two missing `.gitignore` lines are reported to whoever owns that file; this config
   * does not need them, and a later change back to `test-results/` does.
   */
  outputDir: './out/playwright',

  reporter: [['list'], ['junit', { outputFile: 'out/playwright/operator-junit.xml' }]],

  use: {
    baseURL: BASE_URL,
    // The filming geometry. See the header.
    viewport: { width: 1024, height: 576 },
    deviceScaleFactor: 2.5,
    trace: 'retain-on-failure',
    video: 'off',
    screenshot: 'only-on-failure',
    // No `extraHTTPHeaders`, no `serviceWorkers: 'block'`, no route handlers anywhere in
    // this tier. Every byte these specs assert on came off a real socket.
  },

  projects: [
    {
      name: 'operator',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 576 }, deviceScaleFactor: 2.5 },
    },
  ],

  /**
   * Starts the emulator if nothing is already listening. `reuseExistingServer` is true in
   * both directions on purpose: during a filming rehearsal the founder has one running and
   * a second process would fight it for the port and the connection.
   */
  webServer: {
    command: [
      `"${PYTHON}"`,
      `"${REPO_ROOT}scripts/deploy/local_furl.py"`,
      `--port ${PORT}`,
      `--web-root "${REPO_ROOT}verticals/mainline/apps/console/dist"`,
      '--require-web-root',
      `--dsn "${DSN}"`,
      `--database ${DATABASE}`,
      `--permit-id ${PERMIT_ID}`,
      '--quiet',
    ].join(' '),
    url: `${BASE_URL}/v1/demo/subjects`,
    reuseExistingServer: true,
    timeout: 90_000,
    stdout: 'pipe',
    stderr: 'pipe',
    /**
     * The rate limiter, RAISED and still armed.
     *
     * `mainline_demo_api.ratelimit` defaults to 10 rps / 100 burst globally and 5 rps / 50
     * burst per source. Those numbers bound the AWS bill: a Function URL under
     * `authorization_type = NONE` is open, and the module's own docstring says the limit is
     * there so a flood cannot run up a charge. On loopback there is no charge, and the only
     * thing the default bounds is this suite — which was measured on 2026-08-15 taking a real
     * `429 rate_limited` on `GET /v1/permits/{id}` two thirds of the way through a full run,
     * because each spec loads the page afresh and each load fires eight reads at once.
     *
     * These four names ARE the module's supported interface (Interface I3), every value is
     * clamped to a finite maximum, and the module states that no environment variable can
     * disarm it. So the limiter still refuses — at 200 rps rather than 10. That is a
     * different number, not a disabled control, and 200 was chosen over the 10,000 ceiling
     * precisely so a runaway spec still hits it.
     *
     * These apply only when Playwright starts the emulator. Against one you started
     * yourself, pass the same variables or expect a flaky 429.
     */
    env: {
      MAINLINE_RATE_GLOBAL_RPS: '200',
      MAINLINE_RATE_GLOBAL_BURST: '400',
      MAINLINE_RATE_IP_RPS: '200',
      MAINLINE_RATE_IP_BURST: '400',
    },
  },
});
