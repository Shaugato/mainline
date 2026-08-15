// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * HOW THE GATE LEARNS WHICH PERMIT IT IS ABOUT.
 *
 * Two things live here and neither is a React component, so this module can be imported
 * by the surface chunk and by the lazily-loaded demo driver without either of them
 * pulling the other in.
 *
 * ── 1. THE ROUTE'S PARAMETERS ────────────────────────────────────────────────────
 *
 * The same merge the shell's router performs (`src/app/router.ts`) — search plus hash
 * query, hash winning — reused rather than reimplemented, so `?permit=…` behaves
 * identically in either position.
 *
 * The READING MODE is deliberately not here. `?detail=full` is an address concern the
 * shell parses once and publishes through `DetailModeContext`; `src/app/detail-mode.ts`
 * says why two independent subscribers would be two places for the answer to differ. This
 * surface consumes that context and parses nothing of its own.
 *
 * ── 2. THE SUBJECT THE DEMO RUN NAMED ITSELF ─────────────────────────────────────
 *
 * `POST /v1/demo/gate-run` answers with the permit it drove — `subject.subject_id`,
 * `subject.blocking_check_id`, and the clause the reason set names in
 * `beats[].refusal.mus[].clause_id`. That is a subject THE KERNEL STATED, in the same
 * exchange a reader deliberately triggered, and it needs no new route: the gate can learn
 * its permit from a run even where `GET /v1/demo/subjects` is not deployed. Measured
 * 2026-08-15 against the live URL, which answers that read **404** while answering
 * `gate-run` **200**.
 *
 * It is a module-level store rather than a React context because the demo driver and the
 * gate surface are SIBLINGS in `src/app/App.tsx` — the driver is mounted above the surface
 * host so it paints before a surface chunk resolves — and a context would have to be
 * hoisted into the shell, which this worker does not own and which would put a gate
 * concern into the console's frame.
 *
 * **What it is not.** It is not a default, a guess, or a literal. Nothing is published
 * until an exchange has RETURNED; the value published is the payload's own, verbatim; and
 * {@link SUBJECT_ORIGIN_SENTENCE} makes the console say on screen which of the three ways
 * it came to be addressing this permit. A screen that quietly filled in an identifier
 * would be doing the thing `src/data/demo-subjects.ts` exists to prevent.
 */

import { useMemo, useSyncExternalStore } from 'react';

import { parseRoute } from '../../app/router';

// ── 1. The route ───────────────────────────────────────────────────────────

function subscribeToLocation(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  window.addEventListener('popstate', onChange);
  return () => {
    window.removeEventListener('hashchange', onChange);
    window.removeEventListener('popstate', onChange);
  };
}

function locationKey(): string {
  return typeof window === 'undefined' ? '' : `${window.location.search}${window.location.hash}`;
}

/** The route's merged query parameters — search plus hash query, hash winning. */
export function useRouteParams(): URLSearchParams {
  const key = useSyncExternalStore(subscribeToLocation, locationKey, () => '');
  return useMemo(() => {
    const hashAt = key.indexOf('#');
    const search = hashAt >= 0 ? key.slice(0, hashAt) : key;
    const hash = hashAt >= 0 ? key.slice(hashAt) : '';
    return parseRoute(hash, search, []).params;
  }, [key]);
}

// ── 2. The subject a demo run named ────────────────────────────────────────

/**
 * What one `gate-run` answer said about its own subject.
 *
 * Every member is copied out of the payload. `null` means the payload carried `null`
 * there, which is a statement the emitter made and not one this module invented.
 */
export interface GateRunSubjectRef {
  readonly permitId: string;
  readonly blockingCheckId: string | null;
  readonly clauseId: string | null;
  readonly externalRef: string | null;
  /** The run that said so, so a reader can tie the screen to one exchange. */
  readonly runId: string;
}

let published: GateRunSubjectRef | null = null;
const watchers = new Set<() => void>();

/**
 * Records the subject a completed run named. Called from the demo driver's effect, once
 * per answered exchange, and never from a render path that has not seen a payload.
 */
export function publishGateRunSubject(next: GateRunSubjectRef): void {
  if (published !== null && published.permitId === next.permitId && published.runId === next.runId) {
    return;
  }
  published = next;
  for (const watcher of watchers) watcher();
}

/** Forgets the published subject. For tests, which must not read another case's run. */
export function resetGateRunSubject(): void {
  published = null;
  for (const watcher of watchers) watcher();
}

function subscribeToGateRunSubject(onChange: () => void): () => void {
  watchers.add(onChange);
  return () => {
    watchers.delete(onChange);
  };
}

function gateRunSubjectSnapshot(): GateRunSubjectRef | null {
  return published;
}

/** The subject the most recent answered run named, or `null` when none has answered. */
export function useGateRunSubject(): GateRunSubjectRef | null {
  return useSyncExternalStore(subscribeToGateRunSubject, gateRunSubjectSnapshot, () => null);
}

/**
 * Where the identifier this screen is rendering came from.
 *
 * `address` — a reader typed it. `index` — `GET /v1/demo/subjects` named it. `demo-run` —
 * a `POST /v1/demo/gate-run` this reader triggered answered with it. There is no fourth
 * value, and in particular there is no `default`.
 */
export type SubjectOrigin = 'address' | 'index' | 'demo-run';

export const SUBJECT_ORIGIN_SENTENCE: Readonly<Record<SubjectOrigin, string>> = Object.freeze({
  address: 'You named this permit in the address bar, and an address always wins here.',
  index:
    'The console asked this deployment which permit it seeded, at GET /v1/demo/subjects, and ' +
    'this is the identifier that read returned.',
  'demo-run':
    'The console did not choose this permit. The demonstration you ran returned it as the ' +
    'subject it had driven, and the screen followed the payload.',
});
