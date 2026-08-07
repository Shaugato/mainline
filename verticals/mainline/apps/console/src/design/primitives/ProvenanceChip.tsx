// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * ProvenanceChip — how the console came to believe a number.
 *
 * `docs/leads/ui.md` D5: the console never computes a gate condition and never writes an
 * evidentiary row. It reads, it POSTs, and every gate-relevant number is rendered
 * verbatim with a chip saying where it came from. If the console could compute
 * `open_blocking`, the flagship claim would be launderable in TypeScript — P2, one hop
 * downstream.
 *
 * The vocabulary lives in `../provenance` and is closed. There is no `computed`, no
 * `derived` and no `estimated`; a number that is none of the four kinds has no business
 * on an evidentiary surface, and the absence of a chip for it is how that gets noticed.
 */

import { PROVENANCE_SPOKEN, type ProvenanceKind } from '../provenance';
import a11y from './a11y.module.css';
import styles from './chips.module.css';

import { type ReactNode } from 'react';

export interface ProvenanceChipProps {
  readonly kind: ProvenanceKind;
  /**
   * The specific source: `permit.open_blocking`, `gate_closed_when_issued`, or the name
   * of the check that was recomputed. Required in spirit for every kind except `staged`,
   * whose whole content is that there is no source yet.
   */
  readonly detail?: string;
  readonly 'data-testid'?: string;
}

/**
 * A chip whose `kind` names a source but whose `detail` is missing renders the word
 * `unspecified` in the detail slot rather than nothing.
 *
 * An empty slot looks like a chip that had nothing to say; the word `unspecified` looks
 * like a caller who did not fill it in. Those are different bugs and only one of them is
 * visible.
 */
export function ProvenanceChip({
  kind,
  detail,
  'data-testid': testId,
}: ProvenanceChipProps): ReactNode {
  const needsDetail = kind !== 'staged';
  const shown = detail ?? (needsDetail ? 'unspecified' : undefined);
  return (
    <span className={styles.chip} data-kind={kind} data-testid={testId}>
      <span className={a11y.visuallyHidden}>provenance: {PROVENANCE_SPOKEN[kind]}. </span>
      <span aria-hidden="true">{kind}</span>
      {shown === undefined ? null : <span className={styles.chipDetail}>{shown}</span>}
    </span>
  );
}
