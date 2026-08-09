// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The silence surface's two reads, and the pointer that chains them.
 *
 *   `GET /v1/permits/{permit_id}/silence`   the ledger rows and the PER receipt
 *   `GET /v1/recall-runs/{run_id}`          the conservation arithmetic behind them
 *
 * The second is addressed by `receipt.run_id`, so it is enabled only once the first has
 * landed with a receipt. That ordering is deliberate rather than incidental: the run id is
 * a fact the payload supplies, and a console that guessed one — from the URL, from a
 * cached value, from the most recent run for this permit — could show a conservation
 * identity belonging to a DIFFERENT retrieval than the silences underneath it. Two
 * internally consistent panels describing two different runs is the most convincing wrong
 * screen this surface could produce.
 *
 * When the receipt is null the run read never fires and the screen says the identity is
 * unavailable and why. There is no fallback fetch, because there is no honest one.
 *
 * Neither read is a transition and neither has a retry. `useResource` holds the four-state
 * machine, and there is no state meaning "stale counts plus a failure".
 */

import { useResource, type ResourceState } from '../../data/useResource';
import type { MainlineTransport } from '../../data/transport';
import type { RecallRun } from '../../data/types.generated';

import type { SilenceData } from './model';

/** A path value that satisfies `resources.ts`'s unreserved-token rule while disabled. */
const PLACEHOLDER = 'disabled';

export interface SilenceModel {
  readonly silence: ResourceState<SilenceData>;
  readonly run: ResourceState<RecallRun>;
  readonly data: SilenceData | null;
  readonly runData: RecallRun | null;
  /** The run id the receipt named, or `null` when there is no receipt to name one. */
  readonly runId: string | null;
  readonly clockSkewMs: number | null;
}

export function useSilenceData(
  transport: MainlineTransport | null,
  permitId: string,
): SilenceModel {
  const { state: silence } = useResource<SilenceData>(
    transport,
    { resource: 'silence', path: { permit_id: permitId } },
    { enabled: permitId !== '' },
  );

  const data = silence.status === 'ready' ? silence.data : null;
  const runId = data?.receipt?.run_id ?? null;

  const { state: run } = useResource<RecallRun>(
    transport,
    { resource: 'recall_run', path: { run_id: runId ?? PLACEHOLDER } },
    { enabled: runId !== null },
  );

  return {
    silence,
    run,
    data,
    runData: run.status === 'ready' ? run.data : null,
    runId,
    clockSkewMs:
      (run.status === 'ready' ? run.exchange.clockSkewMs : null) ??
      (silence.status === 'ready' ? silence.exchange.clockSkewMs : null),
  };
}
