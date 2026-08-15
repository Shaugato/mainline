// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * CONTRACT B — the last COMPLETED gate run, published for the screen below the driver.
 *
 * `docs/leads/demo-story-plan.md` §7.1 fixes this contract so that nobody negotiates it:
 *
 *   > A React context publishing the last completed gate-run payload, or `null` before
 *   > any press. W3 publishes; W4 subscribes and adapts via its own `refusal-from-run.ts`.
 *   > Neither worker edits the other's file. `null` must keep W4's `NO ATTEMPT` state
 *   > exactly as it renders today.
 *
 * This module is the PRODUCER half and nothing else. It reads no transport, renders no
 * element, adapts no payload into anybody's props, and has no opinion about what a
 * subscriber does with what it gets. What it publishes is `GateRunData` VERBATIM — the
 * whole payload, including each refusing beat's `spec/wire/refusal.md` object with its
 * minimal unsatisfiable subset and its nearest admissible alternative — because a
 * producer that pre-digested the payload would be choosing, on the consumer's behalf,
 * which of the emitter's statements survive.
 *
 * ── THE DEFECT THIS EXISTS TO FIX ────────────────────────────────────────────────
 *
 * `docs/leads/demo-story-plan.md` §0.4(i), measured on the live console: pressing MERGE
 * put `beat 2 · merge · REFUSED · 23514 · gate_closed_when_issued` in the driver panel
 * while, further down the same page, the screen's own refusal band still read **NO
 * ATTEMPT — NOTHING HAS BEEN REFUSED**. The product's entire argument had happened and
 * the component built to display it said nothing had. The two components are SIBLINGS in
 * `src/app/App.tsx` — the driver is mounted above the surface host so it paints before a
 * surface chunk resolves — so they had no way to hear each other. This is that way.
 *
 * ── WHY A STORE *AND* A CONTEXT ──────────────────────────────────────────────────
 *
 * A context alone would need a provider above BOTH subtrees, which means editing
 * `src/app/App.tsx` — another worker's file, and a gate concern hoisted into the
 * console's frame. So the default is a module-level store read through
 * `useSyncExternalStore`, exactly as `src/features/gate/addressing.ts` does for the
 * subject a run named, and {@link LastGateRunContext} exists ON TOP of it for a caller
 * that wants to state the value explicitly — a test pinning the `null` case, or a
 * composition that renders the surface without a driver at all. A provider WINS where one
 * is present; where none is, the store answers. There is no third source.
 *
 * ── WHAT IS NEVER PUBLISHED ──────────────────────────────────────────────────────
 *
 * A run that is in flight, a run that failed in transport, and a run the endpoint
 * refused. `null` means *no completed run*, which is the state W4's `NO ATTEMPT` band is
 * a true rendering of. A press does not clear the previous answer either: "the last
 * COMPLETED gate-run payload" is what the contract says, and blanking a real refusal the
 * moment somebody presses again would take a true exhibit off screen in favour of
 * nothing.
 */

import { createContext, useContext, useSyncExternalStore } from 'react';

import type { GateRunData } from './beats';

/**
 * The published payload, or `null` before any run has completed in this session.
 *
 * Module-level, so the driver and the gate surface see the same value without a shared
 * ancestor. It is not persisted anywhere: a reload is a session with no completed run,
 * and a screen that remembered a refusal across a reload would be claiming an attempt
 * that this page never made.
 */
let published: GateRunData | null = null;

const watchers = new Set<() => void>();

function announce(): void {
  for (const watcher of watchers) watcher();
}

/**
 * Records a run that COMPLETED. Called once per answered exchange, from the driver's
 * effect, and never from a render path that has not seen a payload.
 *
 * Re-publishing the identical object is a no-op, so an effect that re-runs because React
 * handed it a new state wrapper does not wake every subscriber for a value that did not
 * change.
 */
export function publishLastGateRun(run: GateRunData): void {
  if (published === run) return;
  published = run;
  announce();
}

/**
 * Forgets the published run. For tests, which must not read another case's run, and for
 * any caller that needs the `null` state back deliberately.
 */
export function resetLastGateRun(): void {
  if (published === null) return;
  published = null;
  announce();
}

/** The store's current value, without subscribing. For assertions, not for rendering. */
export function lastGateRunSnapshot(): GateRunData | null {
  return published;
}

function subscribe(onChange: () => void): () => void {
  watchers.add(onChange);
  return () => {
    watchers.delete(onChange);
  };
}

/** No window ⇒ no session ⇒ no completed run. A static render has pressed nothing. */
function serverSnapshot(): GateRunData | null {
  return null;
}

/**
 * An explicit override of the published run.
 *
 * `undefined` is the NO-PROVIDER sentinel and is the default deliberately: `null` is a
 * meaningful value on this channel — *no run has completed* — so it cannot also mean
 * *nobody is providing*. A provider must state one or the other.
 */
export const LastGateRunContext = createContext<GateRunData | null | undefined>(undefined);

/**
 * The last completed gate run, or `null`.
 *
 * Both sources are read on every render because hooks are unconditional; the provider
 * decides which answer is returned, not which is computed.
 */
export function useLastGateRun(): GateRunData | null {
  const provided = useContext(LastGateRunContext);
  const stored = useSyncExternalStore(subscribe, lastGateRunSnapshot, serverSnapshot);
  return provided === undefined ? stored : provided;
}
