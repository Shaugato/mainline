// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE COMPOSITION ROOT — the one place in the console where a transport is constructed.
 *
 * Every `src/features/<id>/transport-context.ts` in this workspace says the same thing in
 * its own words: *"The composition root is the shell (`src/app`), which does not yet
 * provide one."* This module is that provider, and it is deliberately the only one. A
 * surface that could build its own transport would have to choose a verifier, and
 * `src/data/bundle.ts` ships no default because *a bundle player with no verifier is a
 * mock, and this console does not ship one*. Centralising the construction here is what
 * lets every surface keep its honest `null` default instead of inventing a permissive
 * stand-in to make itself paint.
 *
 * ── THE ONE PROPERTY THIS FILE EXISTS TO PRESERVE ────────────────────────────────
 *
 * D7: **`LIVE` and `REPLAY` differ in one line of composition and in one badge, never in
 * a code path.** Read `buildTransport` below and count: it is one `if`, two constructor
 * calls, and the same `MainlineTransport` returned either way. Nothing downstream of this
 * function branches on the mode — not `useResource`, not a surface, not the demo driver.
 * The moment a second branch appears anywhere else, the badge stops being a fact about
 * the bytes and becomes a label somebody maintains.
 *
 * The badge itself is read from `transport.describe().mode`, off the object that actually
 * holds the bytes — never from `source-select.ts`'s answer, and never from a flag beside
 * it. Two places for one fact is one place for them to disagree.
 *
 * ── VERIFICATION IS A GATE, NOT A DECORATION ─────────────────────────────────────
 *
 * In REPLAY this module injects the real in-browser verifier — the RFC 8785 / RFC 6962 /
 * ECDSA implementation owned by the verifier-custody-room worker — and then DRIVES it,
 * eagerly, before any surface asks for a frame. There is no permissive fallback and no
 * `?skip_verification`. If the bundle does not verify, `BundleTransport.exchange` raises
 * for every request (`src/data/bundle.ts` gates on it), the honesty chrome's seal reads
 * VERIFICATION FAILED, and the chrome under the navigation renders the verifier's own
 * summary and findings verbatim. **A failure state, not a screen.**
 *
 * `open()` is called WITHOUT an `AbortSignal`, on purpose. `BundleTransport.open()`
 * memoises its promise so that a failure is remembered rather than retried; passing a
 * signal and aborting it on unmount — which React's development double-invoke does
 * immediately — would poison the one verification the transport will ever perform and
 * report a tampered bundle where there is none. The effect guards with a `live` flag
 * instead, which cancels the state update without cancelling the arithmetic.
 *
 * ── WHY `children` IS A FUNCTION ─────────────────────────────────────────────────
 *
 * The shell needs the source chrome INSIDE `<main>`, above the surface, while the
 * transport contexts must wrap everything. A render prop gives the shell both without a
 * second context to carry the verification state, and without this module knowing where
 * in the layout its own chrome lands.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { BundleTransport, FetchBundleSource, type BundleFinding, type BundleVerifier } from '../data/bundle';
import { contractRegistry } from '../data/contracts';
import type { SchemaRegistry } from '../data/schema';
import { HttpTransport, TransportError, type MainlineTransport } from '../data/transport';
import { AuditTransportContext } from '../features/audit/transport-context';
import { CustodyTransportContext } from '../features/custody/transport-context';
import { DiffTransportContext } from '../features/diff/transport-context';
import { GateTransportContext } from '../features/gate/transport-context';
import { PropagationTransportContext } from '../features/propagation/transport-context';
import { SilenceTransportContext } from '../features/silence/transport-context';
import { inBrowserVerifier } from '../verify/bundle-verifier';
import { resolveVerifierConfig } from '../verify/config';

import { useHonestyPublisher } from './honesty';
import {
  SourceModeContext,
  paramsFromAddress,
  selectSource,
  sourceFor,
  type ConfiguredSource,
  type ConsoleEnvironment,
  type SourceKind,
  type SourceModeValue,
  type SourceSelection,
} from './source-select';
import styles from '../features/gate/demo-driver.module.css';

// ── State ──────────────────────────────────────────────────────────────────

type ReplaySeal =
  | { readonly status: 'none' }
  | { readonly status: 'verifying' }
  | {
      readonly status: 'verified';
      readonly summary: string;
      readonly digest: string;
      readonly findings: readonly BundleFinding[];
    }
  | {
      readonly status: 'failed';
      /** The transport's own detail, verbatim. Never summarised. */
      readonly detail: string;
      readonly findings: readonly BundleFinding[];
    };

interface Built {
  readonly transport: MainlineTransport | null;
  /** Non-null exactly in REPLAY; the concrete type is needed to drive `open()`. */
  readonly bundle: BundleTransport | null;
  readonly active: ConfiguredSource | null;
}

export interface CompositionProps {
  /** Given the source chrome to place. The shell puts it inside `<main>`. */
  readonly children: (chrome: ReactNode) => ReactNode;
  /** Build-time variables. Defaults to `import.meta.env`; injected by tests. */
  readonly env?: ConsoleEnvironment;
  /** Address parameters. Defaults to this page's; injected by tests. */
  readonly params?: URLSearchParams;
  /** Defaults to the memoised contract registry. */
  readonly registry?: SchemaRegistry;
  /** Defaults to the platform `fetch`. */
  readonly fetchImpl?: typeof fetch;
  /**
   * Defaults to the in-browser RFC 8785 / RFC 6962 / ECDSA verifier. There is no
   * permissive default and there is no null case: `BundleTransportOptions.verifier` is
   * required, and this module will not manufacture one.
   */
  readonly verifier?: BundleVerifier;
  /** Clock, injectable for cinema mode (D12), which freezes `Date.now`. */
  readonly now?: () => number;
}

// ── The one line ───────────────────────────────────────────────────────────

/**
 * THE choice. One `if`, two constructors, one interface out.
 *
 * Everything else in this module is chrome, state and honesty plumbing around these
 * fourteen lines. If a reader wants to check D7 for themselves, this is the function to
 * read, and its shape is the evidence.
 */
function buildTransport(
  active: ConfiguredSource | null,
  options: {
    readonly registry: SchemaRegistry;
    readonly fetchImpl?: typeof fetch;
    readonly verifier?: BundleVerifier;
    readonly now?: () => number;
  },
): Built {
  if (active === null) return { transport: null, bundle: null, active: null };

  if (active.kind === 'live') {
    const transport = new HttpTransport({
      baseUrl: active.location,
      registry: options.registry,
      ...(options.fetchImpl === undefined ? {} : { fetchImpl: options.fetchImpl }),
      ...(options.now === undefined ? {} : { now: options.now }),
    });
    return { transport, bundle: null, active };
  }

  const location = absoluteBundleUrl(active.location);
  const bundle = new BundleTransport({
    source:
      options.fetchImpl === undefined
        ? new FetchBundleSource(location)
        : new FetchBundleSource(location, options.fetchImpl),
    registry: options.registry,
    // The real one, or the one a test injected. Never a permissive one, and never none.
    verifier: options.verifier ?? inBrowserVerifier(resolveVerifierConfig()),
    ...(options.now === undefined ? {} : { now: options.now }),
  });
  return { transport: bundle, bundle, active };
}

/**
 * Resolves a bundle location against this document, so `./bundle/` is a legal value.
 *
 * `FetchBundleSource` reads with `new URL(path, baseUrl)`, which REQUIRES an absolute
 * base — a relative one raises `Invalid base URL` on the first read, which would surface
 * as "the bundle could not be opened" and send a reader hunting for a missing file. The
 * resolution happens once, here, so `.env.demo` can carry a location that does not name
 * the deployment's hostname: the console is built with `base: './'` precisely so it can
 * be served from a bucket root, from a sub-path, and from `file://`, and a bundle URL
 * that hard-coded an origin would undo all three.
 *
 * This can only ever produce a SAME-ORIGIN location from a relative one. An absolute
 * location is returned unchanged — the operator who set it at build time is the operator
 * who built the artefact, which is the distinction `src/features/evidence/source.ts`
 * draws and this module keeps.
 */
function absoluteBundleUrl(location: string): string {
  if (typeof document === 'undefined') return location;
  try {
    return new URL(location, document.baseURI).toString();
  } catch {
    // Returned unchanged rather than repaired: a location this cannot resolve is one the
    // reader needs to see verbatim in the failure that follows.
    return location;
  }
}

function defaultParams(): URLSearchParams {
  if (typeof window === 'undefined') return new URLSearchParams();
  return paramsFromAddress(window.location.search, window.location.hash);
}

// ── The provider ───────────────────────────────────────────────────────────

export function Composition({
  children,
  env,
  params,
  registry,
  fetchImpl,
  verifier,
  now,
}: CompositionProps): ReactNode {
  const publish = useHonestyPublisher();

  // Read once. `?source=` selects between sources the build already carries and cannot
  // introduce one; re-reading it on every hash change would let back-navigation tear the
  // transport down mid-exchange for no gain.
  const [addressParams] = useState<URLSearchParams>(() => params ?? defaultParams());
  const environment: ConsoleEnvironment = env ?? import.meta.env;

  const selection: SourceSelection = useMemo(
    () => selectSource(environment, addressParams),
    [environment, addressParams],
  );

  const [kind, setKind] = useState<SourceKind | null>(() => selection.initial?.kind ?? null);
  const active = kind === null ? null : sourceFor(selection, kind);

  const resolvedRegistry = registry ?? contractRegistry();
  const built = useMemo(
    () =>
      buildTransport(active, {
        registry: resolvedRegistry,
        ...(fetchImpl === undefined ? {} : { fetchImpl }),
        ...(verifier === undefined ? {} : { verifier }),
        ...(now === undefined ? {} : { now }),
      }),
    [active, resolvedRegistry, fetchImpl, verifier, now],
  );

  // THE BADGE. Read off the transport, which is the object that holds the bytes — never
  // off `selection`, which is a statement about the build rather than about the payload.
  const mode = built.transport?.describe().mode ?? 'unknown';

  useEffect(() => {
    publish({ transport: mode });
  }, [publish, mode]);

  const [seal, setSeal] = useState<ReplaySeal>({ status: 'none' });

  /**
   * Whether THIS component has ever published a seal.
   *
   * It exists so that the `no bundle` branch can distinguish two situations a boolean on
   * the state alone cannot: a live-only build, where the seal belongs to whichever
   * surface recomputed something (`CustodyScreen`, `EvidenceScreen`) and must not be
   * stamped over on mount; and a switch AWAY from a bundle, where leaving
   * `VERIFICATION FAILED` on screen beside LIVE bytes would be the chrome reporting a
   * verdict about something nobody is looking at any more.
   */
  const publishedSeal = useRef(false);

  useEffect(() => {
    const bundle = built.bundle;
    if (bundle === null) {
      setSeal({ status: 'none' });
      if (publishedSeal.current) {
        publishedSeal.current = false;
        publish({ seal: 'unverified', sealDetail: null, bundleDigestPrefix: null });
      }
      return undefined;
    }

    let live = true;
    publishedSeal.current = true;
    setSeal({ status: 'verifying' });
    publish({ seal: 'verifying', sealDetail: null });

    // No AbortSignal: see the module header. `open()` memoises, so an abort here is
    // permanent.
    bundle.open().then(
      (opened) => {
        if (!live) return;
        setSeal({
          status: 'verified',
          summary: opened.report.summary,
          digest: opened.report.manifestDigest,
          findings: opened.report.findings,
        });
        publish({
          seal: 'verified',
          sealDetail: opened.report.summary,
          bundleDigestPrefix: opened.report.manifestDigest.slice(0, 12),
        });
      },
      (error: unknown) => {
        if (!live) return;
        const detail =
          error instanceof TransportError
            ? error.detail
            : error instanceof Error
              ? error.message
              : String(error);
        const report = bundle.report();
        setSeal({ status: 'failed', detail, findings: report?.findings ?? [] });
        publish({
          seal: 'failed',
          sealDetail: detail,
          bundleDigestPrefix: report === null ? null : report.manifestDigest.slice(0, 12),
        });
      },
    );

    return () => {
      live = false;
    };
  }, [built, publish]);

  const sourceMode = useMemo<SourceModeValue>(
    () => ({
      selection,
      active,
      choose: (next: SourceKind) => {
        // A kind this build does not carry is refused rather than half-applied: the
        // alternative is a transport pointed at an empty string.
        if (sourceFor(selection, next) === null) return;
        setKind(next);
      },
    }),
    [selection, active],
  );

  const chrome = (
    <SourceChrome selection={selection} active={active} mode={mode} seal={seal} choose={sourceMode.choose} />
  );

  return (
    <SourceModeContext.Provider value={sourceMode}>
      {/*
        One transport, six sockets. The gate context is first because the gate surface IS
        the demo; the rest follow in the order `src/app/surfaces.ts` declares them.
      */}
      <GateTransportContext.Provider value={built.transport}>
        <AuditTransportContext.Provider value={built.transport}>
          <CustodyTransportContext.Provider value={built.transport}>
            <DiffTransportContext.Provider value={built.transport}>
              <SilenceTransportContext.Provider value={built.transport}>
                <PropagationTransportContext.Provider value={built.transport}>
                  {children(chrome)}
                </PropagationTransportContext.Provider>
              </SilenceTransportContext.Provider>
            </DiffTransportContext.Provider>
          </CustodyTransportContext.Provider>
        </AuditTransportContext.Provider>
      </GateTransportContext.Provider>
    </SourceModeContext.Provider>
  );
}

// ── The chrome ─────────────────────────────────────────────────────────────

/**
 * The source badge, the switch, and the replay seal.
 *
 * It renders NOTHING when the build carries no source. That is not an omission: every
 * surface already renders its own NO SOURCE panel naming what is missing, and a second
 * banner saying the same thing above it would be the shell asserting a fact the surfaces
 * are better placed to state. "Neither variable set → the existing NO SOURCE panel,
 * unchanged" is a requirement, and the way to leave a panel unchanged is to add nothing.
 *
 * The switch is a control, and it lives HERE rather than in the honesty chrome, because
 * the honesty chrome is non-dismissible and carries no controls at all (D16 — asserted by
 * `tests/unit/app/shell.test.tsx`, which requires zero buttons inside it). The MODE is
 * still shown up there, permanently, sourced from `describe()`.
 */
function SourceChrome({
  selection,
  active,
  mode,
  seal,
  choose,
}: {
  readonly selection: SourceSelection;
  readonly active: ConfiguredSource | null;
  readonly mode: 'live' | 'replay' | 'unknown';
  readonly seal: ReplaySeal;
  readonly choose: (kind: SourceKind) => void;
}): ReactNode {
  if (active === null) return null;

  const other: SourceKind = mode === 'live' ? 'replay' : 'live';
  const alternate = selection.switchable ? sourceFor(selection, other) : null;

  return (
    <section className={styles.sourceBar} data-testid="source-chrome" data-mode={mode}>
      <div className={styles.sourceHead}>
        <span className={styles.sourceBadge} data-mode={mode} data-testid="source-badge">
          {mode.toUpperCase()}
        </span>
        <code className={styles.sourceLocation} data-testid="source-location">
          {active.location}
        </code>
        {alternate !== null && (
          <button
            type="button"
            className={styles.sourceSwitch}
            data-testid="source-switch"
            onClick={() => {
              choose(other);
            }}
          >
            {other === 'replay'
              ? 'Show the same screen from the signed bundle (REPLAY)'
              : 'Show the same screen from the live database (LIVE)'}
          </button>
        )}
      </div>
      <p className={styles.sourceWhy} data-testid="source-why">
        {active.why}
      </p>

      {seal.status === 'verifying' && (
        <p className={styles.sourceWhy} role="status" data-testid="replay-verifying">
          Recomputing this bundle&apos;s digests in this browser. No frame is served until that
          resolves.
        </p>
      )}

      {seal.status === 'verified' && (
        <div className={styles.sealOk} data-testid="replay-verified">
          <span className={styles.sourceLabel}>verified in this browser</span>
          <code className={styles.sourceLocation}>{seal.digest}</code>
          <p className={styles.sourceWhy}>{seal.summary}</p>
          <FindingList findings={seal.findings} />
        </div>
      )}

      {seal.status === 'failed' && (
        <div className={styles.sealFailed} role="alert" data-testid="replay-verification-failed">
          <span className={styles.sourceLabel}>verification failed — no frame was served</span>
          <pre className={styles.verbatim}>{seal.detail}</pre>
          <FindingList findings={seal.findings} />
          <p className={styles.sourceWhy}>
            This is the whole point of the replay path: the bundle is checked before it is
            rendered, so a tampered or truncated one produces this panel instead of a screen. No
            surface below has been given a frame.
          </p>
        </div>
      )}
    </section>
  );
}

function FindingList({ findings }: { readonly findings: readonly BundleFinding[] }): ReactNode {
  if (findings.length === 0) return null;
  return (
    <ul className={styles.findingList} data-testid="replay-findings">
      {findings.map((finding) => (
        <li key={`${finding.subject}:${finding.check}`}>
          <code className={styles.sourceLocation}>{finding.subject}</code>{' '}
          <code className={styles.sourceLocation}>{finding.check}</code>
          <span className={styles.sourceWhy}> {finding.detail}</span>
        </li>
      ))}
    </ul>
  );
}
