// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE OPERATOR ENTRY POINT — `operator.html` → this module → the chrome → a screen.
 *
 * ── THE ONE RULE THIS FILE EXISTS TO KEEP ────────────────────────────────────────────
 *
 * It imports NOTHING from `src/app`, `src/design`, `src/features`, `src/verify` or `src/data`,
 * and it imports no framework: no React, no motion library, no 3D. That is not a stylistic
 * preference, it is arithmetic. The console's entry chunk sits 1,108 bytes under the response
 * ceiling `static_site.py` serves objects at (docs/STATE-OF-THE-BUILD.md §12.9), so the
 * operator surface may add ZERO bytes to it. A single shared import would put both entries in
 * one closure and spend that headroom (operator-systems-plan.md R1/R2).
 *
 * `eslint.config.js` refuses those imports where they are typed and
 * `tests/unit/operator/shell/boundary.test.ts` refuses them over the file text, so the rule
 * survives an inline suppression and an edit to the lint config.
 *
 * ── HOW THE TWO SCREENS ARRIVE ───────────────────────────────────────────────────────
 *
 * They self-register (see route.ts). The glob below is enumerated rather than wildcarded so
 * that the set of screen modules is written down in one place, and it expands to nothing while
 * those modules are unbuilt — which is why this file compiles today and picks them up
 * unchanged the moment they land.
 */

import './chrome/tokens.css';
import './chrome/chrome.css';

import { createAppBar } from './chrome/AppBar';
import { createOriginStrip, installExchangeBridge } from './chrome/OriginStrip';
import { createRail } from './chrome/Rail';
import { createWatermark } from './chrome/Watermark';
import { currentRoute, moduleFor, onRouteChange, screenFor, type OperatorRoute } from './route';

/**
 * Every screen module, imported for its registration side effect.
 *
 * `eager: true` on purpose: a lazily-imported screen would be a separate chunk outside the
 * `operator-surface` budget's static closure, and a budget that does not cover the thing it is
 * a budget for is decorative.
 */
const SCREEN_MODULES: Record<string, unknown> = import.meta.glob(
  ['./permit/screen.ts', './change/screen.ts'],
  { eager: true },
);

/** How many screen modules this build actually found. Printed when a route has none. */
export function discoveredScreenModules(): readonly string[] {
  return Object.keys(SCREEN_MODULES).sort();
}

/**
 * Builds the frame a route with no registered screen gets.
 *
 * It says the module is not in this build. It does NOT render an empty form: an unbuilt
 * screen and a screen whose data came back empty must never look the same, which is the same
 * rule the rail applies to a register this deployment does not carry.
 */
function unbuiltNotice(route: OperatorRoute, doc: Document): HTMLElement {
  const panel = doc.createElement('section');
  panel.className = 'cw-unbuilt';
  panel.setAttribute('data-cw', 'unbuilt');

  const heading = doc.createElement('h2');
  heading.textContent = 'Module not in this build';

  const first = doc.createElement('p');
  first.textContent =
    `${moduleFor(route).name} has no screen registered in this bundle, so there is nothing here ` +
    'to fill in. This is an absent module, not an empty one.';

  const second = doc.createElement('p');
  const found = discoveredScreenModules();
  second.textContent =
    found.length === 0
      ? 'No screen module was found at build time.'
      : `Screen modules found at build time: ${found.join(', ')}.`;

  panel.append(heading, first, second);
  return panel;
}

/**
 * Mounts the chrome into `root` and keeps the module frame in step with the hash.
 *
 * Returns a teardown that removes the listeners and the screen. Nothing here schedules a
 * timer, and nothing here delays a render to make anything feel like work.
 */
export function mountOperatorShell(
  root: HTMLElement,
  win: Window = window,
  doc: Document = document,
): () => void {
  const route = currentRoute(win);

  const shell = doc.createElement('div');
  shell.className = 'cw-shell';

  const watermark = createWatermark(doc);
  const appBar = createAppBar(route, doc);
  const rail = createRail(route, doc);
  const originStrip = createOriginStrip(win, doc);

  const body = doc.createElement('div');
  body.className = 'cw-body';

  const moduleHost = doc.createElement('main');
  moduleHost.className = 'cw-module';
  moduleHost.id = 'cw-module';
  moduleHost.setAttribute('data-cw', 'module-host');
  // A programmatic focus target for the skip that the module screens own; -1 so it is
  // reachable by script and not by Tab.
  moduleHost.tabIndex = -1;

  body.append(rail.element, moduleHost);
  shell.append(watermark, appBar.element, body, originStrip.element);
  root.replaceChildren(shell);

  let teardownScreen: (() => void) | null = null;

  const paint = (next: OperatorRoute): void => {
    if (teardownScreen !== null) {
      teardownScreen();
      teardownScreen = null;
    }
    moduleHost.replaceChildren();
    moduleHost.setAttribute('data-cw-route', next);
    appBar.setRoute(next);
    rail.setRoute(next);

    const mount = screenFor(next);
    if (mount === null) {
      moduleHost.append(unbuiltNotice(next, doc));
      return;
    }
    teardownScreen = mount(moduleHost) ?? null;
  };

  paint(route);

  const stopRouting = onRouteChange(paint, win);
  const stopBridge = installExchangeBridge(doc);

  return () => {
    stopRouting();
    stopBridge();
    if (teardownScreen !== null) teardownScreen();
    originStrip.destroy();
    root.replaceChildren();
  };
}

/*
 * The boot. The notice in operator.html is removed only AFTER the shell has mounted, so a
 * module that throws at import time leaves the sentence on screen instead of a white
 * rectangle — the same discipline `src/main.tsx` keeps for the console.
 */
const rootElement = document.getElementById('operator-root');
if (rootElement !== null) {
  mountOperatorShell(rootElement);
  document.getElementById('boot-notice')?.remove();
}
