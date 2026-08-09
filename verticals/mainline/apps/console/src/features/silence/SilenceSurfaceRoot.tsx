// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The silence surface's root component.
 *
 * It lives beside `surface.tsx` so the registration module exports a descriptor and nothing
 * else — React Fast Refresh degrades when a module exports both a component and a value,
 * and the console lints that at `--max-warnings 0`.
 *
 * Three jobs:
 *
 *   1. read the subject from the URL — `#/silence?permit=<uuid>`. The console does not
 *      guess which permit you meant;
 *   2. take a transport from `SilenceTransportContext`, and render the NO SOURCE panel when
 *      nobody has provided one;
 *   3. fill the honesty chrome slots it can establish — transport mode, bundle digest
 *      prefix, clock skew, and the corpus root the PER receipt was issued against (D16).
 *
 * The corpus root is worth the extra line: it is the one value on this surface that ties
 * the silences to a specific state of the archive, and the chrome is where a reader looks
 * for it when they are checking whether two screenshots describe the same corpus.
 */

import { useEffect, useMemo, useSyncExternalStore, type ReactNode } from 'react';

import { useHonestyPublisher } from '../../app/honesty';
import { parseRoute } from '../../app/router';
import { Mono, RegisterFrame } from '../../design/primitives';

import styles from './silence.module.css';
import { SilenceScreen } from './SilenceScreen';
import { useSilenceTransport } from './transport-context';
import { useSilenceData } from './useSilenceData';

/** The query parameter that addresses a subject: `#/silence?permit=<uuid>`. */
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
    <RegisterFrame register="evidence">
      <div className={styles.surface} data-testid="silence-no-subject">
        <h1 className={styles.title}>Silence — what was not surfaced</h1>
        <section className={styles.panel}>
          <p className={styles.prose}>
            This surface renders the silence ledger of ONE subject and does not choose one for
            you. Address a permit by its identifier —{' '}
            <Mono>#/silence?{PERMIT_PARAM}=&lt;uuid&gt;</Mono> — and the console will read every
            row the recall declined to surface for it, together with the run that declined them.
          </p>
        </section>
      </div>
    </RegisterFrame>
  );
}

export function SilenceSurfaceRoot(): ReactNode {
  const params = useRouteParams();
  const permitId = params.get(PERMIT_PARAM);
  const transport = useSilenceTransport();
  const publish = useHonestyPublisher();

  // Hooks run unconditionally; the empty subject is handled below, and `useSilenceData`
  // performs no exchange when the transport is null.
  const model = useSilenceData(transport, permitId ?? '');

  const description = transport?.describe() ?? null;
  const mode = description?.mode ?? null;
  const digestPrefix = description?.bundleDigestPrefix ?? null;
  const corpusRoot = model.data?.receipt?.corpus_root ?? null;
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

  return <SilenceScreen permitId={permitId} model={model} noSource={transport === null} />;
}
