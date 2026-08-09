// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The cosignature set, the open unwitnessed debt, and the sentence that bounds both.
 *
 * `SPLIT_VIEW_LIMIT` is rendered as LITERAL TEXT, from the exported constant, on every
 * render of this panel — not conditionally, not on hover, not behind a disclosure. It is
 * the one claim about this ledger that a reader is most likely to over-read, and
 * `spec/wire/checkpoint.md` §5.3 and ARCHITECTURE.md §7.6 both refuse it in terms:
 *
 *   > Not split-view resistance until a genuinely adverse witness is live.
 *
 * `tests/browser/custody.spec.ts` asserts the rendered text against the constant, so
 * softening the sentence breaks a spec rather than passing review.
 *
 * The `adverse` column is a claim about LEGAL INTEREST, not a cryptographic property. A
 * witness in our own trust domain can produce a perfectly valid cosignature and still be
 * useless against a split view, because the attack it defeats requires a party who would
 * rather we lost. That distinction is drawn in the column header, where a reader will see
 * it, rather than in a footnote.
 */

import { type ReactNode } from 'react';

import { Mono } from '../../../design/primitives';
import { SPLIT_VIEW_LIMIT, type LedgerCosignature, type LedgerDebt } from '../../../verify/ledger';
import type { QuorumShape } from '../model';
import styles from '../custody.module.css';

export function WitnessPanel({
  quorum,
  cosignatures,
  debt,
}: {
  readonly quorum: QuorumShape;
  readonly cosignatures: readonly LedgerCosignature[];
  readonly debt: readonly LedgerDebt[];
}): ReactNode {
  const open = debt.filter((row) => row.discharged_tree_size === null);

  return (
    <section className={styles.section} aria-label="Witnesses and unwitnessed debt">
      <h3 className={styles.sectionTitle}>Witnesses</h3>

      <dl className={styles.facts}>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>cosignatures over the head</dt>
          <dd className={styles.factValue} data-testid="quorum-count">
            {quorum.cosignatures}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>distinct trust domains</dt>
          <dd className={styles.factValue}>
            {quorum.distinctDomains.length === 0 ? 'none' : quorum.distinctDomains.join(', ')}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>declared adverse</dt>
          <dd className={styles.factValue} data-testid="quorum-adverse">
            {quorum.adverse}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt className={styles.factLabel}>open unwitnessed debt</dt>
          <dd className={styles.factValue} data-testid="quorum-debt">
            {quorum.openDebt}
          </dd>
        </div>
      </dl>

      <div className={styles.limit} data-testid="split-view-limit">
        <span className={styles.limitTitle}>the honest limit</span>
        <p className={styles.limitText}>{SPLIT_VIEW_LIMIT}</p>
        <p className={styles.detail}>
          {quorum.adversePresent
            ? 'At least one cosignature over this head is declared adverse, which meets the ' +
              'PRECONDITION of the claim. The claim itself still requires that witness to have ' +
              'been running the cosigning service independently, which this console cannot see ' +
              'and does not assert.'
            : 'Every cosignature over this head is over our own infrastructure. A witness with ' +
              'no adverse legal interest will cosign whatever it is shown, so the count above ' +
              'says the mechanism runs — it does not say anybody who would rather we lost has ' +
              'looked at it.'}
        </p>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table} data-testid="cosignature-table">
          <caption>
            Cosignatures as carried. The signature BYTES are not verified by this browser: no
            witness verification key is configured and cosignature verification is not
            implemented here.
          </caption>
          <thead>
            <tr>
              <th scope="col">witness</th>
              <th scope="col">trust domain</th>
              <th scope="col">adverse (a claim about legal interest, not a cryptographic property)</th>
              <th scope="col">tree size</th>
              <th scope="col">received</th>
            </tr>
          </thead>
          <tbody>
            {cosignatures.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  No cosignature is carried at all. Going dark stays possible and self-reports:
                  see the debt table below.
                </td>
              </tr>
            ) : (
              cosignatures.map((row) => (
                <tr key={`${row.witness_id}-${row.tree_size}`} data-adverse={String(row.adverse)}>
                  <th scope="row" className={styles.checkName}>
                    {row.witness_id}
                  </th>
                  <td className={styles.verdictCell}>{row.trust_domain}</td>
                  <td className={styles.verdictCell}>{String(row.adverse)}</td>
                  <td className={styles.verdictCell}>{row.tree_size}</td>
                  <td className={styles.verdictCell}>{row.received_at}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table} data-testid="debt-table">
          <caption>
            Unwitnessed debt. Permits still merge when a witness is unreachable; each merge
            inserts a debt row, and no later checkpoint is admissible while debt is open.
            Going dark stays possible and self-reports.
          </caption>
          <thead>
            <tr>
              <th scope="col">debt</th>
              <th scope="col">permit</th>
              <th scope="col">incurred</th>
              <th scope="col">discharged at tree size</th>
            </tr>
          </thead>
          <tbody>
            {debt.length === 0 ? (
              <tr>
                <td colSpan={4}>
                  No debt row is carried. That is a claim that none was incurred, not a claim
                  that none exists — this payload shows what the read returned.
                </td>
              </tr>
            ) : (
              debt.map((row) => (
                <tr key={row.debt_id} data-open={String(row.discharged_tree_size === null)}>
                  <th scope="row" className={styles.hash}>
                    <Mono>{row.debt_id}</Mono>
                  </th>
                  <td className={styles.hash}>{row.permit_id}</td>
                  <td className={styles.verdictCell}>{row.incurred_at}</td>
                  <td className={styles.verdictCell}>
                    {row.discharged_tree_size ?? 'OPEN'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {open.length === 0 ? null : (
        <p className={styles.detail} data-testid="open-debt-note">
          {open.length} debt row(s) are open, so no later checkpoint at this site is admissible
          until they are discharged.
        </p>
      )}
    </section>
  );
}
