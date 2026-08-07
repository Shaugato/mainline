// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The provider half of the honesty context (D16).
 *
 * Separated from `honesty.ts` because a component module that also exports hooks and
 * constants breaks fast refresh, and because the split makes the ownership obvious: the
 * shell provides the store, other domains fill the slots, and nobody but the chrome
 * reads them.
 */

import { useCallback, useMemo, useState, type ReactNode } from 'react';

import {
  HonestyContext,
  UNKNOWN_HONESTY,
  type HonestyContextValue,
  type HonestyPatch,
  type HonestyState,
} from './honesty';

export function HonestyProvider({
  children,
  initial,
}: {
  readonly children: ReactNode;
  readonly initial?: HonestyPatch;
}): ReactNode {
  const [state, setState] = useState<HonestyState>(() => ({ ...UNKNOWN_HONESTY, ...initial }));

  const publish = useCallback((patch: HonestyPatch) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, []);

  const value = useMemo<HonestyContextValue>(() => ({ state, publish }), [state, publish]);
  return <HonestyContext.Provider value={value}>{children}</HonestyContext.Provider>;
}
