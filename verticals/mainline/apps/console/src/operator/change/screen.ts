// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CHANGE MODULE'S REGISTRATION, AND THE ONE PLACE THE REAL KERNEL IS BOUND.
 *
 * `src/operator/route.ts` states the contract in one line:
 *
 *   > `src/operator/change/screen.ts` calls `registerScreen('change', mount)` at module scope.
 *
 * and `boot.ts` discovers exactly that path with an enumerated `import.meta.glob`. So the
 * file exists at the name the shell looks for, and the screen itself lives in
 * `ChangeScreen.ts` where this worker's brief puts it.
 *
 * ── WHY THE KERNEL IS BOUND HERE AND NOWHERE ELSE ────────────────────────────────────
 *
 * `ChangeScreen.ts` takes its kernel as a parameter typed by a structural port. This file
 * is the only place in `src/operator/change/**` that names W2's modules, so there is
 * exactly one line in the module to read in order to know where every byte on that screen
 * came from — and there is no second data source it could quietly acquire, because there
 * is no second call site.
 *
 * `get` and `resolveAddressing` satisfy the port with no adapter: the port is a subset of
 * the interfaces `docs/demo/operator-systems-plan.md` §4.2 fixed, so this is a plain
 * structural match rather than a translation layer that could drop or reshape a field.
 *
 * ── FAILURE ──────────────────────────────────────────────────────────────────────────
 *
 * `ScreenMount` is synchronous; mounting opens real HTTP reads, so the promise is started
 * here and its rejection is RENDERED rather than swallowed. `route.ts` is explicit that an
 * unbuilt screen and a screen whose data came back empty must never look the same; a
 * screen whose reads threw is a third case and it gets its own sentence. An unhandled
 * rejection would leave a safety engineer looking at a half-filled form with no
 * indication that anything had gone wrong, which is the worst of the three.
 */

import { resolveAddressing } from '../kernel/addressing';
import { get } from '../kernel/client';
import { registerScreen } from '../route';

import { mountChangeScreen } from './ChangeScreen';
import { el } from './ribbon';

registerScreen('change', (host) => {
  const handle = mountChangeScreen(host, { get, resolveAddressing });

  void handle.ready.catch((error: unknown) => {
    const failure = el('div', 'moc-absent');
    failure.append(
      el(
        'p',
        undefined,
        'The management-of-change screen did not finish reading. What is above is what ' +
          'landed before the failure; nothing has been filled in from anywhere else.',
      ),
    );
    failure.append(
      el(
        'p',
        'moc-exchange',
        error instanceof Error ? `${error.name}: ${error.message}` : String(error),
      ),
    );
    handle.root.append(failure);
  });

  return () => {
    handle.root.remove();
  };
});
