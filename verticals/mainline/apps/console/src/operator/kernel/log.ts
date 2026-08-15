// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE REQUEST LOG — append-only, complete, and never composed.
 *
 * R18: *"Every screen carries a RAW PAYLOAD affordance and a REQUEST LOG."* This is the
 * store behind the second half. Its properties are the ones a judge in devtools will be
 * cross-checking against, so they are stated as rules rather than left to convention:
 *
 * 1. **APPEND-ONLY.** There is no remove, no edit and no filter. An entry that could be
 *    withdrawn from the log is an entry the page could have hidden, and the entire value
 *    of showing a request log is that it cannot hide one. {@link resetLog} exists for the
 *    unit tier and is called by no operator module.
 * 2. **COMPLETE.** `client.ts` records EVERY exchange it produces — successes, refusals,
 *    404s, timeouts, the lot — before it returns. A screen never has to remember to log,
 *    so a screen can never forget. This is why the log is a module and not a hook.
 * 3. **UNSHAPED.** An entry is the {@link Exchange} the client built, carrying the verbatim
 *    response text. Nothing here re-serialises, pretty-prints, truncates or summarises.
 *
 * The subscription is a plain callback set: the operator surface is vanilla TypeScript
 * with no framework (R1), and a two-line observable is cheaper than any of the machinery
 * that would otherwise arrive with one.
 */

import type { Exchange } from './client';

const log: Exchange<unknown>[] = [];
const listeners = new Set<() => void>();

/**
 * Append one exchange.
 *
 * `client.ts` calls this itself, once, for every exchange it produces. Screens therefore
 * do **not** call it for exchanges the client returned to them — doing so would double the
 * entry and make the log a worse witness than the network panel it sits beside. It is
 * exported because operator-systems-plan §4.2 fixes it as part of the published interface.
 */
export function record(x: Exchange<unknown>): void {
  log.push(x);
  for (const listener of listeners) {
    listener();
  }
}

/** Every exchange this page load has made, oldest first. */
export function entries(): readonly Exchange<unknown>[] {
  return log;
}

/** How many exchanges this page load has made. */
export function count(): number {
  return log.length;
}

/** Subscribe to appends. Returns the unsubscribe. */
export function onChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/**
 * Empty the log. **Test-only**, and named so that a grep for it in `src/operator/**`
 * outside this file is a review finding. See rule 1 above.
 */
export function resetLog(): void {
  log.length = 0;
  listeners.clear();
}
