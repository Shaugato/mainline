// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The fleet surface's ONE read.
 *
 * `GET /v1/lessons/{lesson_id}/propagation` — the lesson, every site's answer, and every
 * conflict. There is no write here and there is no control on this surface that could
 * cause one: adopting a lesson, declining it and resolving a conflict are all state
 * transitions that belong to the kernel's procedures, and a fleet dashboard that could
 * apply a recorded resolution with one click is the rubber-stamp accelerant this design
 * exists not to build.
 *
 * `useResource` holds the four-state machine — there is no fifth state and, in particular,
 * no state meaning "stale rows plus a failure". A fleet view that renders the previous
 * lesson's adoptions while the current read is failing is worse than one that renders
 * nothing, because the adoptions look current.
 */

import { useResource, type ResourceState } from '../../data/useResource';
import type { MainlineTransport } from '../../data/transport';

import type { PropagationData } from './model';

export function usePropagationData(
  transport: MainlineTransport | null,
  lessonId: string,
): ResourceState<PropagationData> {
  const { state } = useResource<PropagationData>(
    transport,
    {
      resource: 'propagation',
      path: { lesson_id: lessonId },
    },
    // `resources.ts` refuses a path parameter that is not an unreserved token, so an empty
    // subject must not reach it. The surface renders its NO SUBJECT panel in that case.
    { enabled: lessonId !== '' },
  );
  return state;
}
