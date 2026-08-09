// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The two CHECK constraints on `mainline_meas.recall_run` that are product claims.
 *
 * ── candidates_conserved (MI17) ──────────────────────────────────────────────────
 *
 *     n_candidates = n_blocking + n_advisory + n_silenced + n_deduped
 *
 * Rendered as an EQUATION the reader adds up, not as five stat cards. The relationship is
 * the entire claim: every candidate the retrieval produced went to exactly one of four
 * places, and the count of the ones that went nowhere visible is on the screen with the
 * rest. A dashboard tile reading "11 silenced" says nothing; `17 = 2 + 3 + 11 + 1` says
 * that eleven is not a leftover.
 *
 * ── bonded_fatalities_all_blocking (MI16) ────────────────────────────────────────
 *
 *     n_bonded_sev5_blocking = n_bonded_sev5
 *
 * *"A fatality in your fonds is always recalled"* as a POSITIVE INVARIANT enforced by a
 * database constraint rather than by a score threshold somebody could tune. It is rendered
 * with the constraint's own name, because the name is what a reader greps the migrations
 * for; a paraphrase would be a weaker claim wearing the same words.
 *
 * ── WHAT THE CHIPS SAY, AND WHY THEY DIFFER ──────────────────────────────────────
 *
 * The five counts carry `db:column`. The SUM carries `recomputed` — this browser added
 * four numbers that are all on screen. The constraint NAMES carry `db:constraint`. Keeping
 * those three apart is the whole of D5 on this panel: the console did the addition, the
 * database did the enforcing, and a reader can tell which is which without being told.
 */

import { Fragment, type ReactNode } from 'react';

import { ConstraintName, Mono, ProvenanceChip } from '../../design/primitives';

import { bondedOf, conservationOf } from './model';
import { ProvenanceSlot } from './ProvenanceSlot';
import type { ProvenanceEntry } from './provenance';
import styles from './silence.module.css';
import type { RecallRun } from '../../data/types.generated';

export interface ConservationPanelProps {
  readonly run: RecallRun;
  readonly provenance: readonly ProvenanceEntry[] | undefined;
}

function Term({
  column,
  value,
  testId,
}: {
  readonly column: string;
  readonly value: number;
  readonly testId: string;
}): ReactNode {
  return (
    <span className={styles.equationTerm} data-column={column}>
      <span className={styles.equationValue} data-testid={testId}>
        {value}
      </span>
      <span className={styles.equationColumn}>{column}</span>
    </span>
  );
}

export function ConservationPanel({ run, provenance }: ConservationPanelProps): ReactNode {
  const conservation = conservationOf(run);
  const bonded = bondedOf(run);

  return (
    <section className={styles.panel} data-testid="conservation-panel" aria-label="Conservation">
      <span className={styles.kicker}>the recall run</span>
      <h2 className={styles.sectionTitle}>every candidate went exactly one of four places</h2>

      <p
        className={styles.equation}
        data-testid="conservation-equation"
        data-balances={conservation.balances ? 'true' : 'false'}
      >
        <Term
          column={conservation.total.column}
          value={conservation.total.value}
          testId="conservation-total"
        />
        <span className={styles.equationOperator} aria-label="equals">
          =
        </span>
        {conservation.terms.map((term, index) => (
          <Fragment key={term.column}>
            {index === 0 ? null : (
              <span className={styles.equationOperator} aria-hidden="true">
                +
              </span>
            )}
            <Term column={term.column} value={term.value} testId={`conservation-${term.column}`} />
          </Fragment>
        ))}
        <span className={styles.equationOperator} aria-hidden="true">
          →
        </span>
        <Term column="sum (recomputed here)" value={conservation.sum} testId="conservation-sum" />
      </p>

      <p className={styles.prose}>
        <ConstraintName
          name={conservation.constraint}
          data-testid="conservation-constraint"
          tone={conservation.balances ? 'neutral' : 'refuse'}
        />{' '}
        on <Mono>mainline_meas.recall_run</Mono> — a write that broke this identity would be
        refused with SQLSTATE <Mono>23514</Mono>. The five counts are columns; the sum is
        arithmetic this browser performed over them so that the identity can be checked rather
        than believed.
      </p>

      <p className={styles.slot}>
        <ProvenanceSlot
          provenance={provenance}
          pointer="/counts/n_candidates"
          data-testid="conservation-total-provenance"
        />
        <ProvenanceChip kind="recomputed" detail="sum of the four outcome columns" />
      </p>

      {conservation.balances ? (
        <p className={styles.note} data-testid="conservation-balances">
          The identity balances: <Mono>{conservation.total.value}</Mono> ={' '}
          <Mono>{conservation.sum}</Mono>, residual <Mono>{conservation.residual}</Mono>.
        </p>
      ) : (
        <p className={styles.imbalance} data-testid="conservation-imbalance">
          THIS IDENTITY DOES NOT BALANCE. residual{' '}
          <Mono>{conservation.residual}</Mono>. The database enforces{' '}
          <Mono>{conservation.constraint}</Mono>, so a payload that violates it did not come
          from a cluster that has that constraint. Nothing else on this screen should be read
          as a measurement until that is explained.
        </p>
      )}

      <h3 className={styles.sectionTitle}>a fatality in your fonds is always recalled</h3>
      <p
        className={styles.equation}
        data-testid="bonded-equation"
        data-holds={bonded.holds ? 'true' : 'false'}
      >
        <Term
          column={bonded.blocking.column}
          value={bonded.blocking.value}
          testId="bonded-blocking"
        />
        <span className={styles.equationOperator} aria-label="equals">
          =
        </span>
        <Term column={bonded.bonded.column} value={bonded.bonded.value} testId="bonded-total" />
      </p>
      <p className={styles.prose}>
        <ConstraintName
          name={bonded.constraint}
          data-testid="bonded-constraint"
          tone={bonded.holds ? 'neutral' : 'refuse'}
        />{' '}
        — a satisfied database constraint, not a score hack. Every severity-5 event bonded to
        the permit&apos;s activity node or any ancestor is blocking, unconditionally and
        regardless of what any model scored it.
      </p>
      <p className={styles.slot}>
        <ProvenanceSlot
          provenance={provenance}
          pointer="/counts/n_bonded_sev5_blocking"
          data-testid="bonded-provenance"
        />
      </p>

      <dl className={styles.facts}>
        <dt>run_id</dt>
        <dd>
          <Mono data-testid="run-id">{run.run_id}</Mono>
        </dd>
        <dt>policy_version</dt>
        <dd>
          <Mono data-testid="run-policy-version">{run.policy_version}</Mono>
        </dd>
        <dt>index_generation</dt>
        <dd>
          <Mono data-testid="run-index-generation">{run.index_generation}</Mono>
        </dd>
        <dt>index_plan_digest</dt>
        <dd>
          <Mono data-testid="run-index-plan-digest">{run.index_plan_digest}</Mono>
          <p className={styles.note}>
            The hash of the <Mono>EXPLAIN</Mono> output ACTUALLY OBSERVED, not of the plan
            anybody hoped for. On this platform an unhinted prefix-constrained ANN query does
            not traverse the vector index at demo-corpus scale, so every arm pins its index
            explicitly and this digest is how that is evidenced rather than asserted.
          </p>
        </dd>
        <dt>started_at</dt>
        <dd>
          <Mono>{run.started_at}</Mono>
        </dd>
        <dt>latency_ms</dt>
        <dd>{(run.latency_ms ?? null) === null ? <span>not recorded</span> : <Mono>{run.latency_ms}</Mono>}</dd>
      </dl>
    </section>
  );
}
