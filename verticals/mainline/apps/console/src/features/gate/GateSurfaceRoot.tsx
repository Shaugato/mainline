// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The gate surface's root component.
 *
 * It lives beside `surface.tsx` rather than inside it so that the registration module
 * exports a descriptor and nothing else — React Fast Refresh degrades when one module
 * exports both a component and a value, and the console lints that at
 * `--max-warnings 0`.
 *
 * This module does three things and no more:
 *
 *   1. reads the subject from the URL — `#/gate?permit=<uuid>`. The console does not
 *      guess which permit you meant, and a surface with no subject says so;
 *   2. takes a transport from `GateTransportContext` and renders the NO SOURCE panel
 *      when nobody has provided one (see `transport-context.ts` for why it does not
 *      build one itself);
 *   3. fills the honesty chrome's slots it is in a position to fill — the transport
 *      mode, the bundle digest prefix, the server-vs-local clock skew and the corpus
 *      root the ancestry was closed against (D16). Every one of those is a fact the
 *      transport or a payload established; the surface asserts none of them itself.
 */

import { useEffect, useMemo, useSyncExternalStore, type ReactNode } from 'react';

import { useHonestyPublisher } from '../../app/honesty';
import { parseRoute } from '../../app/router';
import styles from './gate.module.css';
import { GateScreen } from './GateScreen';
import { useGateData } from './useGateData';
import { useGateTransport } from './transport-context';
import { Mono } from '../../design/primitives';

/** The query parameter that addresses a subject: `#/gate?permit=<uuid>`. */
export const PERMIT_PARAM = 'permit';

function subscribe(onChange: () => void): () => void {
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

/**
 * The route's merged query parameters (search plus hash query, hash winning) — the same
 * parsing the shell's router performs, reused rather than reimplemented so that
 * `?cinema=1&seed=…` and `?permit=…` behave identically in either position.
 */
function useRouteParams(): URLSearchParams {
  const key = useSyncExternalStore(subscribe, locationKey, () => '');
  return useMemo(() => {
    const hashAt = key.indexOf('#');
    const search = hashAt >= 0 ? key.slice(0, hashAt) : key;
    const hash = hashAt >= 0 ? key.slice(hashAt) : '';
    return parseRoute(hash, search, []).params;
  }, [key]);
}

function NoSubject(): ReactNode {
  return (
    <div className={styles.surface} data-testid="gate-no-subject">
      <section className={styles.refusalBar} data-state="none" aria-label="Refusal">
        <span className={styles.refusalKicker}>no subject addressed</span>
        <p className={styles.prose}>
          This surface renders the gate of ONE subject and does not choose one for you. Address a
          permit by its identifier — <Mono>#/gate?{PERMIT_PARAM}=&lt;uuid&gt;</Mono> — and the
          console will read that permit, its blocking checks, and the clause behind them.
        </p>
      </section>
    </div>
  );
}

export function GateSurfaceRoot(): ReactNode {
  const params = useRouteParams();
  const permitId = params.get(PERMIT_PARAM);
  const transport = useGateTransport();
  const publish = useHonestyPublisher();

  // Hooks run unconditionally; the empty subject is handled by the render below, and
  // `useGateData` performs no exchange when the transport is null.
  const model = useGateData(transport, permitId ?? '');

  const description = transport?.describe() ?? null;
  const mode = description?.mode ?? null;
  const digestPrefix = description?.bundleDigestPrefix ?? null;
  const corpusRoot = model.ancestryData?.corpus_root ?? null;
  const { clockSkewMs } = model;

  useEffect(() => {
    publish({
      transport: mode ?? 'unknown',
      bundleDigestPrefix: digestPrefix,
      clockSkewMs,
      corpusRoot,
    });
  }, [publish, mode, digestPrefix, clockSkewMs, corpusRoot]);

  if (permitId === null || permitId === '') return <NoSubject />;

  return <GateScreen permitId={permitId} model={model} noSource={transport === null} />;
}
