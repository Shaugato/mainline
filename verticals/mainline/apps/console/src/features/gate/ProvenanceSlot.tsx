// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The provenance slot beside a value on the gate screen.
 *
 * Three renderings, and the third is the one that matters:
 *
 *   1. a kind in the design package's closed vocabulary → the shared `ProvenanceChip`;
 *   2. `derived` → a chip drawn here, because the wire contract has five kinds and the
 *      design package has four (see `provenance.ts`), and dropping the fifth would hide
 *      a claim the emitter actually made;
 *   3. nothing declared → an explicit UNDECLARED marker carrying the JSON pointer that
 *      was looked up.
 *
 * (3) is not noise. `contracts/common.schema.json` says an unclaimed provenance is
 * better than a comfortable default; an EMPTY slot and an UNDECLARED slot look the same
 * to a reader, and only one of them is a statement. Showing the pointer means a reviewer
 * can tell the emitter exactly which key to declare.
 *
 * An `inherited` chip — one declared on an ancestor pointer — is rendered with both
 * pointers, so it is visibly a weaker claim than an exact one.
 */

import { type ReactNode } from 'react';

import { ProvenanceChip } from '../../design/primitives';

import styles from './gate.module.css';
import { isDesignChipKind, lookupProvenance, type ProvenanceEntry } from './provenance';

export interface ProvenanceSlotProps {
  /** The envelope's `provenance` list, verbatim. */
  readonly provenance: readonly ProvenanceEntry[] | undefined;
  /** RFC 6901 pointer into the envelope's `data`. */
  readonly pointer: string;
  readonly 'data-testid'?: string;
}

export function ProvenanceSlot({
  provenance,
  pointer,
  'data-testid': testId,
}: ProvenanceSlotProps): ReactNode {
  const found = lookupProvenance(provenance, pointer);

  if (found.kind === 'undeclared') {
    return (
      <span className={styles.slot} data-testid={testId} data-provenance="undeclared">
        <span className={styles.chipUndeclared}>
          <span>undeclared</span>
        </span>
        <span className={styles.slotPointer}>{pointer}</span>
      </span>
    );
  }

  const detail = found.kind === 'inherited' ? `${found.pointer} ⊇ ${pointer}` : pointer;

  return (
    <span
      className={styles.slot}
      data-testid={testId}
      data-provenance={found.kind}
      data-chip={found.chip}
    >
      {isDesignChipKind(found.chip) ? (
        <ProvenanceChip kind={found.chip} detail={detail} />
      ) : (
        <span className={styles.chipDerived}>
          <span>{found.chip}</span>
          <span className={styles.slotPointer}>{detail}</span>
        </span>
      )}
    </span>
  );
}
