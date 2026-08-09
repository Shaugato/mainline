// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The three panels that carry everything this screen refuses to smooth over.
 *
 * `FindingsPanel` — what disagreed, verbatim. A finding is `{subject, check, detail}`
 * as the audit produced it; nothing here rewrites a detail into a friendlier sentence,
 * because the check name is what a reader greps for and the detail is what they paste
 * into an issue.
 *
 * `GapsPanel` — declared resources with no captured exchange. In REPLAY a resource with
 * no frame is a screen that cannot be shown at all, and naming which ones is the
 * difference between "the demo covers most of it" and a claim a reader can check. It
 * also surfaces the unowned endpoint: `clause_ancestry` has no backend worker
 * (`docs/leads/ui.md` §4), and the console says so rather than letting the absence
 * read as an oversight.
 *
 * `LimitsPanel` — what a clean audit does NOT establish. It renders `model.ts`'s
 * `LIMITS`, which is data precisely so a test can assert it is present: a paragraph of
 * caveats in JSX can be deleted in a hurry, a constant with a test cannot.
 */

import { type ReactNode } from 'react';

import type { BundleFinding } from '../../data/bundle';

import styles from './evidence.module.css';
import { LIMITS, type ResourceGap } from './model';

export function FindingsPanel({
  findings,
}: {
  readonly findings: readonly BundleFinding[];
}): ReactNode {
  if (findings.length === 0) {
    return (
      <p className={styles.status} data-testid="evidence-findings-none">
        No finding. Every file the manifest lists was read, and every one hashed to the digest
        the manifest declares.
      </p>
    );
  }
  return (
    <ul className={styles.plainList} data-testid="evidence-findings">
      {findings.map((finding, index) => (
        <li
          className={styles.finding}
          key={`${finding.subject}|${finding.check}|${String(index)}`}
          data-check={finding.check}
        >
          <p className={styles.findingHead}>
            <span className={styles.findingCheck}>{finding.check}</span>
            <span>{finding.subject}</span>
          </p>
          <p className={styles.findingDetail}>{finding.detail}</p>
        </li>
      ))}
    </ul>
  );
}

export function GapsPanel({ gaps }: { readonly gaps: readonly ResourceGap[] }): ReactNode {
  if (gaps.length === 0) {
    return (
      <p className={styles.status} data-testid="evidence-gaps-none">
        Every resource declared in <code>src/data/resources.ts</code> has a captured exchange in
        this bundle.
      </p>
    );
  }
  return (
    <ul className={styles.plainList} data-testid="evidence-gaps">
      {gaps.map((gap) => (
        <li className={styles.gap} key={gap.key} data-resource={gap.key}>
          <p className={styles.gapHead}>
            {gap.method} {gap.template} · {gap.key} ·{' '}
            {gap.owner === null ? (
              <span className={styles.gapOwner}>no backend domain owes this endpoint</span>
            ) : (
              <>owed by {gap.owner}</>
            )}
          </p>
          <p className={styles.findingDetail}>{gap.purpose}</p>
        </li>
      ))}
    </ul>
  );
}

export function LimitsPanel(): ReactNode {
  return (
    <ul className={styles.plainList} data-testid="evidence-limits">
      {LIMITS.map((limit) => (
        <li className={styles.limit} key={limit.claim}>
          <p className={styles.limitClaim}>{limit.claim}</p>
          <p className={styles.limitWhy}>{limit.why}</p>
        </li>
      ))}
    </ul>
  );
}
