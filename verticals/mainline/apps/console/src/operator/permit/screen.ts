// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PERMIT MODULE'S REGISTRATION, AND NOTHING ELSE.
 *
 * `src/operator/route.ts` states the contract in one line:
 *
 *   > `src/operator/permit/screen.ts` calls `registerScreen('permit', mount)` at module scope.
 *
 * and `boot.ts` discovers exactly this path with an enumerated `import.meta.glob`. So the
 * file exists at the name the shell looks for, and the screen itself lives in
 * `PermitScreen.ts` where W3's brief puts it. Two files rather than one, because the shell's
 * registry is inverted on purpose (it must expand to nothing while a screen is unbuilt) and
 * renaming either side would break somebody else's published contract.
 *
 * `ScreenMount` is synchronous and returns a teardown or nothing. Mounting is asynchronous —
 * it opens real HTTP reads — so the promise is started here and its failure is rendered
 * rather than swallowed: an unhandled rejection would leave the supervisor looking at an
 * empty form, which is the one thing `route.ts` says must never be confused with a screen
 * that has no data in it.
 */

import { registerScreen } from '../route';

import { mountPermitScreen } from './PermitScreen';
import { absenceBlock, el } from './typed-fields';

registerScreen('permit', (host) => {
  const controller = new AbortController();

  void mountPermitScreen(host).catch((error: unknown) => {
    if (controller.signal.aborted) {
      return;
    }
    const box = el('div', 'cow-permit');
    box.appendChild(
      absenceBlock(
        'the permit screen did not mount',
        error instanceof Error ? `${error.name}: ${error.message}` : String(error),
      ),
    );
    host.replaceChildren(box);
  });

  return () => {
    controller.abort();
  };
});
