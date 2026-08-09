// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The provenance slot beside a value on the fleet surface.
 *
 * Three renderings, and the third is the one that matters:
 *
 *   1. a kind in the design package's closed vocabulary → the shared `ProvenanceChip`;
 *   2. `derived` → a chip drawn here, because the wire contract has five kinds and the
 *      design package has four, and dropping the fifth would hide a claim the emitter
 *      actually made;
 *   3. nothing declared → an explicit UNDECLARED marker carrying the pointer looked up.
 *
 * (3) is not noise. An EMPTY slot and an UNDECLARED slot look identical to a reader and
 * only one of them is a statement; showing the pointer means a reviewer can tell the
 * emitter exactly which key to declare.
 */

import { type ReactNode } from 'react';

import { ProvenanceChip } from '../../design/primitives';

import styles from './propagation.module.css';
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
