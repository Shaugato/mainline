// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Which retrieval channels ran, and which of them did not.
 *
 * `arms_degraded` is the run's own admission that the fusion was performed with a channel
 * missing. When it is true this panel is the loudest thing on the screen after the
 * conservation identity, because every silence below was computed by a retrieval that was
 * not the retrieval the policy describes — and a reader who does not know that will read
 * the scores as though it was.
 *
 * When it is false the panel still renders, quietly, saying so. A prominent warning that
 * appears only in the bad case teaches readers that its absence means nothing was checked;
 * a permanent statement that flips between two states teaches them where to look.
 *
 * `index_hinted` per arm is here because of a measured platform fact: at demo-corpus scale
 * an unhinted prefix-constrained ANN query does not traverse the vector index at all — the
 * plan degrades to a scan. An arm that returned rows without a hint returned them the slow
 * and less deterministic way, and that is a property of the run worth showing beside the
 * counts rather than discovering later in a plan digest.
 */

import { type ReactNode } from 'react';

import { Mono } from '../../design/primitives';

import styles from './silence.module.css';
import type { RecallRun } from '../../data/types.generated';

export interface ArmsPanelProps {
  readonly run: RecallRun;
}

export function ArmsPanel({ run }: ArmsPanelProps): ReactNode {
  const arms = run.arms ?? [];
  const degradedArms = arms.filter((arm) => arm.degraded);

  return (
    <section aria-label="Retrieval arms" data-testid="arms-panel">
      <h2 className={styles.sectionTitle}>the arms that ran</h2>

      {run.arms_degraded ? (
        <div className={styles.degraded} data-testid="arms-degraded" data-degraded="true">
          <p className={styles.degradedTitle}>
            <Mono>arms_degraded = true</Mono>
          </p>
          <p className={styles.prose}>
            This run completed with {degradedArms.length === 0 ? 'at least one' : degradedArms.length}{' '}
            channel(s) degraded. The gate still blocked — the degraded path is designed to block,
            not to fail open — but every score below was fused from fewer channels than the
            policy describes, and no number on this screen should be compared with a run that
            was not degraded.
          </p>
        </div>
      ) : (
        <p className={styles.panel} data-testid="arms-degraded" data-degraded="false">
          <Mono>arms_degraded = false</Mono> — the run reports every channel returned. This
          statement is rendered in both cases on purpose: a warning that only appears when
          something is wrong teaches readers that silence means nothing was checked.
        </p>
      )}

      {arms.length === 0 ? (
        <p className={styles.note} data-testid="arms-none">
          The payload carries no per-arm breakdown. The run-level{' '}
          <Mono>arms_degraded</Mono> flag above is then the only channel-level fact available,
          and the absence of the breakdown is itself displayed rather than filled in.
        </p>
      ) : (
        <table className={styles.arms} data-testid="arms-table">
          <caption className={styles.srOnly}>
            Retrieval arms, whether each degraded, how many rows it returned, and whether it
            pinned its index explicitly.
          </caption>
          <thead>
            <tr>
              <th scope="col">arm</th>
              <th scope="col">degraded</th>
              <th scope="col">n_returned</th>
              <th scope="col">index_hinted</th>
              <th scope="col">detail</th>
            </tr>
          </thead>
          <tbody>
            {arms.map((arm) => (
              <tr key={arm.arm} data-testid="arm-row" data-arm={arm.arm} data-degraded={arm.degraded}>
                <td>{arm.arm}</td>
                <td>{String(arm.degraded)}</td>
                <td>{arm.n_returned ?? '—'}</td>
                <td>{(arm.index_hinted ?? null) === null ? '—' : String(arm.index_hinted)}</td>
                <td>{arm.detail ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
