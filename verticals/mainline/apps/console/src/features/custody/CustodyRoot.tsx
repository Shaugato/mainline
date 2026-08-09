// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The custody surface's root.
 *
 * It lives beside `surface.tsx` so that the registration module exports a descriptor and
 * nothing else — React Fast Refresh degrades when one module exports both a component and
 * a value, and the console lints at `--max-warnings 0`.
 *
 * Two jobs: read the site from the URL (`#/custody?site=BLK-07`), and fill the honesty
 * chrome slots this surface is in a position to fill (D16). It asserts nothing itself —
 * the transport establishes the mode and the bundle digest, and the verifier establishes
 * everything else.
 */

import { useEffect, useMemo, useSyncExternalStore, type ReactNode } from 'react';

import { useHonestyPublisher } from '../../app/honesty';
import { parseRoute } from '../../app/router';

import { CustodyScreen, DEFAULT_SITE_CODE } from './CustodyScreen';
import { useCustodyTransport } from './transport-context';

/** `#/custody?site=BLK-07`. */
export const SITE_PARAM = 'site';

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

export function CustodyRoot(): ReactNode {
  const params = useRouteParams();
  const transport = useCustodyTransport();
  const publish = useHonestyPublisher();

  const site = params.get(SITE_PARAM);
  const siteCode = site === null || site === '' ? DEFAULT_SITE_CODE : site;

  const description = transport?.describe() ?? null;
  const mode = description?.mode ?? null;
  const digestPrefix = description?.bundleDigestPrefix ?? null;

  useEffect(() => {
    publish({
      transport: mode ?? 'unknown',
      bundleDigestPrefix: digestPrefix,
    });
  }, [publish, mode, digestPrefix]);

  return <CustodyScreen siteCode={siteCode} />;
}
