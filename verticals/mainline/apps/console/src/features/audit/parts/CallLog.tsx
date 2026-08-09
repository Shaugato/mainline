// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Every question the read-only auditor account asked, and what came back.
 *
 * The point of this table is not observability. It is that *the agent could not have
 * written anything* stops being a sentence somebody says and becomes something a reader
 * can check: the SQL role that executed each call, the scopes it was granted, the single
 * statement it sent, and the SQLSTATE when the database refused it.
 *
 * `plan_fragment` is labelled a PLAN, never a measurement. `EXPLAIN ANALYZE` is not
 * available on the Managed MCP surface, so every fragment here is what the optimizer said
 * it would do, not what it did. A column headed "cost" beside a fragment headed "plan"
 * would be read as a timing by everyone who has ever seen a query profiler.
 *
 * A refused call is rendered in the severity accent and is NOT an error state of this
 * screen. A refusal is the product working.
 */

import { type ReactNode } from 'react';

import { Digest, Sqlstate } from '../../../design/primitives';
import { tallyCalls, type McpCall } from '../model';
import styles from '../audit.module.css';

export function CallLog({ calls }: { readonly calls: readonly McpCall[] }): ReactNode {
  const tally = tallyCalls(calls);

  return (
    <section className={styles.section} aria-label="Managed MCP calls">
      <h3 className={styles.sectionTitle}>What the read-only account asked</h3>

      <dl className={styles.facts}>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>calls</dt>
          <dd className={styles.factValue} data-testid="call-total">
            {tally.total}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>ok / refused / error / abstained</dt>
          <dd className={styles.factValue} data-testid="call-outcomes">
            {tally.ok} / {tally.refused} / {tally.error} / {tally.abstained}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>roles (each maps 1:1 to a SQL role)</dt>
          <dd className={styles.factValue}>{tally.roles.join(', ') || 'none'}</dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>granted scopes</dt>
          <dd className={styles.factValue} data-testid="call-scopes">
            {tally.scopes.join(', ') || 'none recorded'}
          </dd>
        </div>
      </dl>

      <p className={styles.detail} data-testid="write-scope-reading">
        {tally.readOnly
          ? 'No call in this log was granted a write verb. That is a reading of the log, not an ' +
            'enforcement: the console cannot stop an agent from writing, and the reason it does ' +
            'not need to is that the write surface is INSERT-only and bound to one table — see ' +
            'below.'
          : `Calls in this log were granted write scopes: ${tally.writeScopes.join(', ')}. The ` +
            'Managed MCP write surface is INSERT-only and bound to ' +
            'mainline_meas.external_attestation; anything wider than that is a finding.'}
      </p>

      <div className={styles.tableWrap}>
        <table className={styles.table} data-testid="call-table">
          <caption>
            One row per Managed-MCP round trip, from mainline_meas.agent_action. The plan
            fragment is a PLAN: EXPLAIN ANALYZE is not available on this surface, so nothing
            here is a measurement.
          </caption>
          <thead>
            <tr>
              <th scope="col">at</th>
              <th scope="col">role</th>
              <th scope="col">tool · transport</th>
              <th scope="col">outcome</th>
              <th scope="col">statement</th>
              <th scope="col">plan fragment</th>
              <th scope="col">model</th>
              <th scope="col">latency (ms)</th>
              <th scope="col">input · output digest</th>
            </tr>
          </thead>
          <tbody>
            {calls.length === 0 ? (
              <tr>
                <td colSpan={9}>
                  No call was carried. An empty log is a claim that nothing was recorded, not a
                  claim that nothing ran.
                </td>
              </tr>
            ) : (
              calls.map((call) => (
                <tr key={call.action_id} className={styles.callRow} data-outcome={call.outcome}>
                  <th scope="row" className={styles.cell}>
                    {call.at}
                  </th>
                  <td className={styles.cell}>{call.agent_role}</td>
                  <td className={styles.cell}>
                    {call.tool} · {call.transport}
                  </td>
                  <td className={styles.outcome}>
                    {call.outcome}
                    {call.sqlstate === null || call.sqlstate === undefined ? null : (
                      <>
                        {' '}
                        <Sqlstate code={call.sqlstate} />
                      </>
                    )}
                  </td>
                  <td>
                    {call.statement === null || call.statement === undefined ? (
                      <span className={styles.cellNull}>none recorded</span>
                    ) : (
                      <pre className={styles.statement}>{call.statement}</pre>
                    )}
                  </td>
                  <td>
                    {call.plan_fragment === null || call.plan_fragment === undefined ? (
                      <span className={styles.cellNull}>no plan returned</span>
                    ) : (
                      <pre className={styles.statement}>{call.plan_fragment}</pre>
                    )}
                  </td>
                  <td className={styles.cell}>
                    {call.model_id ?? 'none'}
                    {call.prompt_version === null || call.prompt_version === undefined
                      ? ''
                      : ` · ${call.prompt_version}`}
                  </td>
                  <td className={styles.cell}>{call.latency_ms ?? 'not recorded'}</td>
                  <td>
                    {call.input_sha256 === null || call.input_sha256 === undefined ? (
                      <span className={styles.cellNull}>no input digest</span>
                    ) : (
                      <Digest value={call.input_sha256} label="in" copyable={false} />
                    )}
                    {call.output_sha256 === null || call.output_sha256 === undefined ? (
                      <span className={styles.cellNull}>no output digest</span>
                    ) : (
                      <Digest value={call.output_sha256} label="out" copyable={false} />
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
