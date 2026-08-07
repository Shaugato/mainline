// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The shell.
 *
 * It renders three things and asserts nothing: the honesty chrome (permanent), the
 * surface navigation (derived from the registry, never from a hand-maintained list),
 * and one surface. The shell holds no evidentiary state, computes no gate condition
 * and composes no message about any record — D5, one hop downstream.
 */

import { type ReactNode } from 'react';

import { ErrorBoundary } from './ErrorBoundary';
import { HonestyChrome } from './HonestyChrome';
import { HonestyProvider } from './HonestyProvider';
import { SurfaceHost } from './SurfaceHost';
import { hrefFor, useRoute } from './router';
import styles from './shell.module.css';
import { SURFACE_REGISTRY, type SurfaceEntry } from './surfaces';

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
      <div className={styles.shell}>
        {/*
          The chrome is outside the surface boundary on purpose: a surface that throws
          must not be able to take the console's own must-not-claim control off screen.
        */}
        <HonestyChrome />
        <div className={styles.body}>
          <Nav entries={entries} activePath={route.path} />
          <main className={styles.main} id="main" tabIndex={-1}>
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
    </HonestyProvider>
  );
}
