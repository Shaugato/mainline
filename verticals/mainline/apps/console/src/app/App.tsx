// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The shell.
 *
 * It renders four things and asserts nothing: the honesty chrome (permanent), the
 * surface navigation (derived from the registry, never from a hand-maintained list), the
 * composition root's own source chrome, and one surface. The shell holds no evidentiary
 * state, computes no gate condition and composes no message about any record — D5, one
 * hop downstream.
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
 */

import { Suspense, lazy, type ReactNode } from 'react';

import { Composition } from './composition';
import { ErrorBoundary } from './ErrorBoundary';
import { HonestyChrome } from './HonestyChrome';
import { HonestyProvider } from './HonestyProvider';
import { SurfaceHost } from './SurfaceHost';
import { hrefFor, useRoute } from './router';
import styles from './shell.module.css';
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

function Nav({
  entries,
  activePath,
}: {
  readonly entries: readonly SurfaceEntry[];
  readonly activePath: string;
}): ReactNode {
  return (
    <nav className={styles.nav} aria-label="Surfaces">
      <ol className={styles.navList}>
        {entries.map((entry) => (
          <li key={entry.id}>
            <a
              className={styles.navLink}
              href={hrefFor(entry.path)}
              aria-current={entry.path === activePath ? 'page' : undefined}
              data-status={entry.status}
              data-register={entry.register}
            >
              <span className={styles.navTitle}>{entry.title}</span>
              {entry.status !== 'loadable' && (
                // The navigation tells the truth about what is behind each link before
                // the reader spends a click on it.
                <span className={styles.navPending}>{entry.milestone}</span>
              )}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

function NoSuchSurface({
  route,
  entries,
}: {
  readonly route: { readonly path: string; readonly raw: string };
  readonly entries: readonly SurfaceEntry[];
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
            <a href={hrefFor(entry.path)}>
              <code>{entry.path}</code>
            </a>{' '}
            — {entry.title} ({entry.status})
          </li>
        ))}
      </ul>
    </section>
  );
}

export function App({
  entries = SURFACE_REGISTRY,
}: {
  readonly entries?: readonly SurfaceEntry[];
}): ReactNode {
  const route = useRoute(entries);
  const active = entries.find((entry) => entry.id === route.surfaceId) ?? null;

  return (
    <HonestyProvider
      initial={{
        buildId: typeof __MAINLINE_BUILD_ID__ === 'string' ? __MAINLINE_BUILD_ID__ : 'dev',
        signaturePath:
          typeof __MAINLINE_SIGNATURE_PATH__ === 'string' ? __MAINLINE_SIGNATURE_PATH__ : 'unknown',
      }}
    >
      <Composition>
        {(sourceChrome) => (
          <div className={styles.shell}>
            {/*
              The chrome is outside the surface boundary on purpose: a surface that throws
              must not be able to take the console's own must-not-claim control off screen.
            */}
            <HonestyChrome />
            <div className={styles.body}>
              <Nav entries={entries} activePath={route.path} />
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
                    <NoSuchSurface route={route} entries={entries} />
                  ) : (
                    <SurfaceHost entry={active} />
                  )}
                </ErrorBoundary>
              </main>
            </div>
          </div>
        )}
      </Composition>
    </HonestyProvider>
  );
}
