// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The check suite, with the arithmetic SHOWN.
 *
 * A green tick that says "verified" and nothing else is a rendering of an assertion
 * somebody else made — the exact thing `docs/leads/ui.md` §0 says a React component cannot
 * authenticate. So every passing check displays its recomputation table: what bytes were
 * hashed, how many of them, what this browser computed, what the payload claimed, and
 * whether the two agree. A reader who does not believe the tick can read the digits.
 *
 * `detail` is rendered VERBATIM in a `pre`-wrapped block. It is written by the verifier
 * for the person who has to act on it, and paraphrasing a finding is how a finding becomes
 * a summary becomes a colour.
 *
 * SKIP is styled as loudly as FAIL, in the warn accent rather than the neutral one,
 * because `spec/custody/checks.yaml` says so in its own header: *a verifier that quietly
 * passes because it did not look is the single worst artefact this domain could ship*.
 *
 * ── WHAT PLAIN COLLAPSES HERE, AND WHAT IT MAY NOT ──────────────────────────────
 *
 * The recomputation table is a wall of 64-character hex, and it is the single most
 * valuable thing on the screen to a reader who can use it and the single most alienating
 * to one who cannot. So in PLAIN it starts collapsed behind a control that says what is
 * inside it, and in FULL DETAIL it starts open (R6). It is in the DOM either way: a text
 * search finds it, a keyboard reaches it, and `@media print` opens every one of them.
 *
 * The seal, the check name, the provenance chip and the verifier's `detail` — which is a
 * kernel-side string written for the person who has to act on it — are NEVER collapsed, in
 * either mode. Those are the finding; the table is the working.
 */

import { type ReactNode } from 'react';

import { Disclosure, ProvenanceChip, VerificationSeal } from '../../../design/primitives';
import type { CheckResult, Recomputed } from '../../../verify/ledger';
import { sealFor } from '../model';
import styles from '../custody.module.css';

function RecomputationTable({
  rows,
  checkName,
}: {
  readonly rows: readonly Recomputed[];
  readonly checkName: string;
}): ReactNode {
  if (rows.length === 0) return null;
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} data-testid={`recomputation-${checkName}`}>
        <caption>
          The arithmetic this browser ran. Every row is one recomputation: the bytes that went
          in, the digest that came out, and the value the payload carried.
        </caption>
        <thead>
          <tr>
            <th scope="col">algorithm</th>
            <th scope="col">bytes hashed</th>
            <th scope="col">computed here</th>
            <th scope="col">carried by the payload</th>
            <th scope="col">verdict</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={`${row.input}-${index}`}
              className={styles.row}
              /*
               * Three states, not two. A row whose `claimed` is empty is one this browser
               * computed and the payload never asserted — the SHA-256 of a note text is the
               * standing example, because a checkpoint does not publish a digest of itself.
               * Rendering that as DISAGREES would print a red word about an agreement nobody
               * ever proposed, which on this screen is worse than printing nothing.
               */
              data-agrees={row.claimed === '' ? 'uncompared' : row.agrees ? 'true' : 'false'}
            >
              <th scope="row">
                {row.algorithm}
                <br />
                <span className={styles.checkId}>{row.input}</span>
              </th>
              <td className={styles.verdictCell}>{row.inputBytes}</td>
              <td className={styles.hash}>{row.computed}</td>
              <td className={styles.hash}>
                {row.claimed === '' ? 'nothing carried to compare' : row.claimed}
              </td>
              <td className={styles.verdictCell}>
                {row.claimed === '' ? 'not compared' : row.agrees ? 'agrees' : 'DISAGREES'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CheckList({
  checks,
  at,
}: {
  readonly checks: readonly CheckResult[];
  readonly at: string;
}): ReactNode {
  return (
    <ol className={styles.checks} data-testid="custody-checks">
      {checks.map((check) => (
        <li
          key={`${check.id}-${check.name}`}
          className={styles.check}
          data-status={check.status}
          data-check={check.name}
        >
          <div className={styles.checkHead}>
            <span className={styles.checkId}>
              {check.id === 0 ? 'discrepancy report' : `check ${check.id}`}
            </span>
            <span className={styles.checkName}>{check.name}</span>
            <VerificationSeal {...sealFor(check, at)} data-testid={`seal-${check.name}`} />
            <ProvenanceChip
              kind={check.status === 'pass' ? 'recomputed' : 'db:column'}
              detail={
                check.offline
                  ? 'offline: needs no access to our database and no cooperation from us'
                  : 'requires our cooperation'
              }
            />
          </div>
          <p className={styles.detail}>{check.detail}</p>
          {check.bounded === null ? null : (
            <p className={styles.bounded} data-testid={`bounded-${check.name}`}>
              <strong>Bounded. </strong>
              {check.bounded}
            </p>
          )}
          {check.recomputations.length === 0 ? null : (
            <Disclosure
              summary={`Show the ${check.recomputations.length} exact digit-by-digit comparison(s) behind this verdict`}
            >
              <RecomputationTable rows={check.recomputations} checkName={check.name} />
            </Disclosure>
          )}
        </li>
      ))}
    </ol>
  );
}
