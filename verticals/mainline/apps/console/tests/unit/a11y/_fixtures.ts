// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * DOM fixtures for the accessibility gate.
 *
 * Every violation this directory asserts is PLANTED as real markup and mounted in a real
 * jsdom document, for the same reason `tests/unit/design/fixtures/planted/` exists: the
 * production assertion ("the shell has no blocking finding") is green on the day it is
 * written, and that is exactly the condition under which a broken auditor is
 * indistinguishable from a clean console.
 *
 * Not a `.test.ts`, so Vitest's `include` does not collect it.
 */

const mounted: HTMLElement[] = [];

/** Mounts markup in the real document and returns its container. */
export function mount(html: string): HTMLElement {
  const container = document.createElement('div');
  container.innerHTML = html;
  document.body.appendChild(container);
  mounted.push(container);
  return container;
}

/** Removes everything `mount()` added. Call from `afterEach`. */
export function unmountAll(): void {
  while (mounted.length > 0) {
    mounted.pop()?.remove();
  }
}

/**
 * A structurally clean control panel: named controls, ordered headings, resolved
 * references, a labelled list.
 *
 * The CONTROL half of every assertion in `audit.test.ts`. A checker that flags this is
 * as useless as one that flags nothing, and without a clean fixture that failure mode
 * is invisible — every planted case would still be caught by a rule that returns a
 * finding for every element it sees.
 */
export const CLEAN_PANEL = `
  <section aria-labelledby="panel-heading" data-register="evidence">
    <h2 id="panel-heading">Blocking precursors</h2>
    <p id="panel-note">Six checks are open on this permit.</p>
    <ul>
      <li><a href="#/gate">Open the gate refusal</a></li>
      <li><button type="button" aria-describedby="panel-note">Dispose</button></li>
    </ul>
    <h3>Arithmetic</h3>
    <label for="threshold">Threshold</label>
    <input id="threshold" type="text" value="0.62" />
    <span data-severity="blood_fatal">fatality</span>
    <code data-provenance="db:column">open_blocking</code>
    <div role="alert" data-failure="refusal">
      <code data-sqlstate="23514">23514</code>
    </div>
  </section>
`;
