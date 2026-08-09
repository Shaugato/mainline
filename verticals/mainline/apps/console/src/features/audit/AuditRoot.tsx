// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The audit surface's root.
 *
 * Separate from `surface.tsx` so that the registration module exports a descriptor and
 * nothing else — React Fast Refresh degrades when one module exports both a component and
 * a value, and the console lints at `--max-warnings 0`.
 *
 * Its only job beyond rendering the screen is to fill the honesty-chrome slots it can
 * establish: the transport mode and the bundle digest prefix, both of which the transport
 * itself reports. It asserts nothing.
 */

import { useEffect, type ReactNode } from 'react';

import { useHonestyPublisher } from '../../app/honesty';

import { AuditScreen } from './AuditScreen';
import { useAuditTransport } from './transport-context';

export function AuditRoot(): ReactNode {
  const transport = useAuditTransport();
  const publish = useHonestyPublisher();

  const description = transport?.describe() ?? null;
  const mode = description?.mode ?? null;
  const digestPrefix = description?.bundleDigestPrefix ?? null;

  useEffect(() => {
    publish({ transport: mode ?? 'unknown', bundleDigestPrefix: digestPrefix });
  }, [publish, mode, digestPrefix]);

  return <AuditScreen />;
}
