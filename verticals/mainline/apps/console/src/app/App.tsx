// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The shell.
 *
 * It renders five things and asserts nothing: the honesty chrome (permanent), the
 * surface navigation (derived from the registry, never from a hand-maintained list), the
 * detail-mode control, the composition root's own source chrome, and one surface. The
 * shell holds no evidentiary state, computes no gate condition and composes no message
 * about any record — D5, one hop downstream.
 *
 * ── WHAT CHANGED WHEN THE TRANSPORT ARRIVED ──────────────────────────────────────
 *
 * `Composition` (see `composition.tsx`) wraps the whole tree and provides ONE transport
 * to every surface context. It sits INSIDE `HonestyProvider` because the badge it
 * publishes — LIVE or REPLAY, read off `transport.describe()` — is a slot in the chrome,
 * and outside `ErrorBoundary` because a surface that throws must not be able to take the
 * source chrome or the must-not-claim control off screen.
 *
 * The demo driver is mounted here rather than inside the gate surface for two reasons
 * that are both mechanical: it is the console's entry point for a judge, so it must paint
 * before a surface chunk resolves; and it is a LAZY import, so the four beats cost the
 * evidentiary shell nothing on any screen that is not the gate (D13 — every feature chunk
 * stays off the critical path, and `budgets.json` is the test).
 *
 * ── WHAT CHANGED WHEN THE NAVIGATION LEARNED WHICH SUBJECT (2026-08-15) ──────────
 *
 * Every link in the navigation used to be a bare `#/path`. Five of the surfaces behind
 * those links render ONE subject and are addressed by its identifier, so a reader clicking
 * down the sidebar arrived at a screen that had to work out its own subject and could not
 * show, in the address bar, which one it had chosen. Now the link carries it — the value
 * the kernel named at `GET /v1/demo/subjects`, resolved through the same memoised exchange
 * the surfaces use, so the shell opens no second read.
 *
 * **The link never carries a value the console invented.** `subjectParamsFor` returns an
 * empty list whenever the index has not resolved, the route did not answer, or the kernel
 * named nothing for that slot, and a bare `#/path` is exactly what shipped before. The
 * surface then renders its own named absence, which is where the reason belongs. The whole
 * degradation path is a function that returns `[]`.
 *
 * The detail mode rides in the same address. R6: one control in the shell, PLAIN on
 * arrival, `?detail=full` propagated by every link, and NO storage — a screenshot has to
 * reproduce from its URL, and this console has to run from `file://`. The mode itself is
 * `src/app/detail-mode.ts`'s; the shell is where it is READ off the address and published,
 * once, through `DetailModeContext`, which is what every `Disclosure` on every screen below
 * reads. This file writes no `detail` parameter of its own — `hrefWithDetail` does, so
 * there is one function that decides whether a link keeps a reader in FULL DETAIL.
 */

import { Suspense, lazy, useEffect, useState, type ReactNode } from 'react';

import type { SubjectIndex } from '../data/demo-subjects';
import type { MainlineTransport } from '../data/transport';

import { Composition } from './composition';
import {
  DetailModeContext,
  hrefWithDetail,
  useDetailModeFromAddress,
  type DetailMode,
} from './detail-mode';
import { ErrorBoundary } from './ErrorBoundary';
import { HonestyChrome } from './HonestyChrome';
import { HonestyProvider } from './HonestyProvider';
import { SurfaceHost } from './SurfaceHost';
import { useRoute } from './router';
import styles from './shell.module.css';
import { SUBJECT_SLOTS, detailToggleHref, subjectHref, subjectParamsFor } from './subjects';
import { SURFACE_REGISTRY, type SurfaceEntry } from './surfaces';

/**
 * The surface the demo driver belongs to. Named once: the driver drives the gate, and a
 * console that offered it above the custody ledger would be offering a control that has
 * nothing to do with the screen under it.
 */
const DEMO_SURFACE_ID = 'gate';

const DemoDriver = lazy(async () => {
  const module = await import('../features/gate/DemoDriver');
  return { default: module.DemoDriver };
});

declare const __MAINLINE_BUILD_ID__: string;
declare const __MAINLINE_SIGNATURE_PATH__: 'webauthn' | 'oidc_envelope' | 'unknown';

/**
 * What is behind a link, said before the click is spent.
 *
 * This used to be the milestone id in a small badge — `K3` beside a struck-through title.
 * A judge walking the sidebar top to bottom read `K3` as a version, a lane or a nothing,
 * clicked, and met a NOT-BUILT-YET card. The words are now the marker and the milestone is
 * the detail beside them, because "K3" is only informative to a reader who already knows
 * what K3 is, and the reader this navigation exists for does not.
 *
 * It is a statement, not an apology: the console promised the screen, the screen has not
 * landed, and the milestone that owes it is named. Nothing here is dressed up as progress
 * and nothing is dressed down as a disappointment.
 */
function NavMarker({ entry }: { readonly entry: SurfaceEntry }): ReactNode {
  if (entry.status === 'loadable') return null;

  const [label, detail] =
    entry.status === 'declared-missing'
      ? (['NOT BUILT YET', `${entry.milestone} owes it`] as const)
      : // A surface that self-registered without appearing in the promise list. It is a
        // real screen and it opens, so this is not the same claim as the one above.
        (['NOT PROMISED', 'self-registered'] as const);

  return (
    <span className={styles.navMarker} data-marker={entry.status}>
      <span className={styles.navMarkerLabel}>{label}</span>{' '}
      <span className={styles.navMarkerDetail}>{detail}</span>
    </span>
  );
}

/**
 * Why this link carries no subject — one sentence, chosen by what actually happened.
 *
 * Four states, four sentences, and the difference between them is the whole point: "nobody
 * gave this console a source", "the read has not landed yet", "the read did not answer"
 * and "the kernel answered and named nothing" are four different findings, and a single
 * "no subject" would be the shell flattening them. Only shown in FULL DETAIL — the surface
 * below says all of this at length, in the kernel's own words, in both modes.
 */
function whyNoSubject(surfaceId: string, index: SubjectIndex): string {
  if (!SUBJECT_SLOTS.has(surfaceId)) return 'this screen takes no subject in its address';
  if (index.status === 'no_source') return 'no transport composed — nothing was asked';
  if (index.status === 'resolving') return 'asking GET /v1/demo/subjects';
  // Not "the route answered 404" — `unavailable` also covers a browser that could not load
  // the module that would have asked, and the shell must not report one as the other. The
  // classification is carried verbatim; the surface below prints the whole report.
  if (index.status === 'unavailable') return `subject index unavailable — ${index.failure}`;
  return 'GET /v1/demo/subjects answered and named none';
}

/**
 * THE SUBJECT INDEX, THROUGH A CHUNK THE EVIDENTIARY SHELL DOES NOT CARRY.
 *
 * `src/data/demo-subjects.ts` is imported here **dynamically**, and the reason is 1,061
 * bytes, measured rather than assumed. That module carries the four absence panels the five
 * subject-bearing surfaces render — several hundred bytes of runtime prose that minification
 * cannot touch because it is string data, not comment. A static import from the shell puts
 * all of it in the entry chunk, and on 2026-08-15 the demo build measured **139,017 B
 * gzip-9 against `static_site.DEFAULT_MAX_RESPONSE_BYTES` of 139,264** — 247 B of headroom
 * for the whole console, where one byte over the ceiling is a **413** rather than a slow
 * page. The same build with this import made dynamic measured 137,956 B. So the shell asks
 * for the module the way it asks for a surface.
 *
 * `resolveDemoSubjects` memoises against the transport object, so this is not a second
 * exchange: whichever of the shell and the five surfaces reaches it first starts the one
 * request, and the others await it.
 *
 * A module that fails to load is reported as `unavailable` carrying its own reason, never
 * left in `resolving`. "The chunk did not arrive" and "the route did not answer" are
 * different findings and `whyNoSubject` above keeps them apart.
 */
function useShellSubjects(transport: MainlineTransport | null): SubjectIndex {
  const [index, setIndex] = useState<SubjectIndex>(() =>
    transport === null ? { status: 'no_source' } : { status: 'resolving' },
  );

  useEffect(() => {
    if (transport === null) {
      setIndex({ status: 'no_source' });
      return undefined;
    }

    let live = true;
    setIndex({ status: 'resolving' });

    // No `AbortSignal`, for `demo-subjects.ts`'s own reason: the promise is memoised for
    // the session, so aborting it on an unmount — which React's development double-invoke
    // performs immediately — would poison the one answer every surface is waiting on.
    void import('../data/demo-subjects').then(
      (module) => {
        void module.resolveDemoSubjects(transport).then((outcome) => {
          if (live) setIndex(outcome);
        });
      },
      (error: unknown) => {
        if (!live) return;
        setIndex({
          status: 'unavailable',
          failure: 'module',
          detail:
            'src/data/demo-subjects.ts did not load in this browser, so the read that names ' +
            `this deployment's subjects was never performed: ${
              error instanceof Error ? error.message : String(error)
            }`,
        });
      },
    );

    return () => {
      live = false;
    };
  }, [transport]);

  return index;
}

/**
 * The exact address a link opens, under the link, for the reader who wants to check it.
 *
 * FULL DETAIL only — this is what the mode changes in the SHELL; on the screen below it is
 * `src/design/primitives/Disclosure.tsx` that reads the same context and opens. It is
 * chosen rather than decorative: the identifier in that string is the answer to "which row
 * am I looking at", and it is the difference between a console that opens on a subject and
 * a console that appears to.
 */
function NavAddress({
  href,
  named,
  why,
}: {
  readonly href: string;
  readonly named: boolean;
  readonly why: string;
}): ReactNode {
  return (
    <p className={styles.navAddress} data-testid="nav-address">
      <code className={styles.navAddressHref}>{href}</code>
      <span className={styles.navAddressNote}>
        {named ? 'subject named by GET /v1/demo/subjects' : why}
      </span>
    </p>
  );
}

function Nav({
  entries,
  activePath,
  detail,
  index,
}: {
  readonly entries: readonly SurfaceEntry[];
  readonly activePath: string;
  readonly detail: DetailMode;
  readonly index: SubjectIndex;
}): ReactNode {
  return (
    <nav className={styles.nav} aria-label="Surfaces">
      <ol className={styles.navList}>
        {entries.map((entry) => {
          const pairs = subjectParamsFor(entry.id, index);
          const href = subjectHref(entry.id, entry.path, index, detail);
          return (
            <li key={entry.id}>
              <a
                className={styles.navLink}
                href={href}
                aria-current={entry.path === activePath ? 'page' : undefined}
                data-status={entry.status}
                data-register={entry.register}
                data-subject={pairs.length > 0 ? 'named' : 'none'}
              >
                <span className={styles.navTitle}>{entry.title}</span>
                <NavMarker entry={entry} />
              </a>
              {detail === 'full' && (
                <NavAddress
                  href={href}
                  named={pairs.length > 0}
                  why={whyNoSubject(entry.id, index)}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/**
 * PLAIN / FULL DETAIL — two links, not a button, and not a stored preference.
 *
 * Links because the mode is part of the address (R6): the control's target IS the URL a
 * reader would copy, so the browser's own "copy link address" produces a reproducible
 * screenshot without the console having to serialise anything. A button would hold the
 * mode in state the address could not carry.
 *
 * Everything else in the address survives the switch — an identifier a reader typed into
 * `#/gate?permit=…` is still there afterwards, because `detailToggleHref` copies every
 * parameter but this one.
 *
 * It is deliberately NOT inside the honesty chrome: D16 makes that strip non-dismissible
 * and control-free, and `tests/unit/app/shell.test.tsx` requires zero buttons and zero
 * inputs inside it.
 */
function DetailControl({
  path,
  params,
  detail,
}: {
  readonly path: string;
  readonly params: URLSearchParams;
  readonly detail: DetailMode;
}): ReactNode {
  return (
    <section className={styles.detailControl} aria-label="How much detail" data-detail={detail}>
      <span className={styles.detailLabel}>How much detail</span>
      <span className={styles.detailChoices}>
        <a
          className={styles.detailChoice}
          href={detailToggleHref(path, params, 'plain')}
          aria-current={detail === 'plain' ? 'true' : undefined}
          data-testid="detail-plain"
        >
          Plain
        </a>
        <a
          className={styles.detailChoice}
          href={detailToggleHref(path, params, 'full')}
          aria-current={detail === 'full' ? 'true' : undefined}
          data-testid="detail-full"
        >
          Full detail
        </a>
      </span>
      <p className={styles.detailNote}>
        The choice travels in the link as <code>?detail=full</code>, so a screenshot
        reproduces from its URL. Full detail opens every disclosure on the screen below, and
        shows the exact address each link above opens. Plain collapses the exact detail
        behind a labelled control; it never removes it.
      </p>
    </section>
  );
}

function NoSuchSurface({
  route,
  entries,
  detail,
}: {
  readonly route: { readonly path: string; readonly raw: string };
  readonly entries: readonly SurfaceEntry[];
  readonly detail: DetailMode;
}): ReactNode {
  return (
    <section className={styles.failure} role="alert" data-failure="no-such-surface">
      <h2 className={styles.failureTitle}>No surface at this address</h2>
      <pre className={styles.verbatim}>{route.raw === '' ? '(empty hash)' : route.raw}</pre>
      <p className={styles.failureNote}>
        The console resolved that to <code>{route.path}</code>, which no registered surface claims.
        The addresses that exist right now:
      </p>
      <ul className={styles.plainList}>
        {entries.map((entry) => (
          <li key={entry.id}>
            <a href={hrefWithDetail(entry.path, detail)}>
              <code>{entry.path}</code>
            </a>{' '}
            — {entry.title} ({entry.status})
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Everything below the composition root.
 *
 * A component rather than the render prop's body, because it calls hooks — `useRoute`,
 * `useDetailModeFromAddress` and `useDemoSubjects` — and a hook inside a callback belongs
 * to whichever component happened to invoke the callback. That is exactly the kind of
 * ordering nobody can see in a diff.
 *
 * Exported so `tests/unit/app/shell.test.tsx` can drive the four states of the subject
 * index directly. `App` composes a transport out of `import.meta.env`, which is not a seam
 * a test can hand four different answers to; this is.
 */
export function Shell({
  entries,
  sourceChrome,
  transport,
}: {
  readonly entries: readonly SurfaceEntry[];
  readonly sourceChrome: ReactNode;
  readonly transport: MainlineTransport | null;
}): ReactNode {
  const route = useRoute(entries);
  const active = entries.find((entry) => entry.id === route.surfaceId) ?? null;

  // Read HERE and nowhere else, and published below. `detail-mode.ts` says why: two
  // subscribers reading the address independently is two places for the answer to differ.
  const detail = useDetailModeFromAddress();

  // ONE exchange for the whole page, out of a chunk the entry does not carry. See
  // `useShellSubjects` for the 1,061 bytes that decides.
  const index = useShellSubjects(transport);

  return (
    // Published ONCE, here, wrapping everything. Every `Disclosure` on every screen below
    // reads this context, so the reader's choice reaches ten surfaces without any of them
    // parsing the address for themselves.
    <DetailModeContext value={detail}>
      <div className={styles.shell} data-detail={detail}>
        {/*
          The chrome is outside the surface boundary on purpose: a surface that throws
          must not be able to take the console's own must-not-claim control off screen.
        */}
        <HonestyChrome />
        <div className={styles.body}>
          <div className={styles.rail}>
            <Nav entries={entries} activePath={route.path} detail={detail} index={index} />
            <DetailControl path={route.path} params={route.params} detail={detail} />
          </div>
          <main className={styles.main} id="main" tabIndex={-1}>
            {/*
              Outside the boundary, beside the chrome and for the same reason: the
              strip that says where these bytes came from, and the panel that says a
              bundle failed verification, must survive a surface that throws.
            */}
            {sourceChrome}
            {active?.id === DEMO_SURFACE_ID && (
              <ErrorBoundary boundary="demo-driver">
                <Suspense fallback={null}>
                  <DemoDriver />
                </Suspense>
              </ErrorBoundary>
            )}
            <ErrorBoundary boundary="shell">
              {active === null ? (
                <NoSuchSurface route={route} entries={entries} detail={detail} />
              ) : (
                <SurfaceHost entry={active} />
              )}
            </ErrorBoundary>
          </main>
        </div>
      </div>
    </DetailModeContext>
  );
}

export function App({
  entries = SURFACE_REGISTRY,
}: {
  readonly entries?: readonly SurfaceEntry[];
}): ReactNode {
  return (
    <HonestyProvider
      initial={{
        buildId: typeof __MAINLINE_BUILD_ID__ === 'string' ? __MAINLINE_BUILD_ID__ : 'dev',
        signaturePath:
          typeof __MAINLINE_SIGNATURE_PATH__ === 'string' ? __MAINLINE_SIGNATURE_PATH__ : 'unknown',
      }}
    >
      <Composition>
        {(sourceChrome, transport) => (
          <Shell entries={entries} sourceChrome={sourceChrome} transport={transport} />
        )}
      </Composition>
    </HonestyProvider>
  );
}
