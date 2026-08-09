// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The provenance slot beside a value on the silence ledger.
 *
 * Three renderings, and the third is the one that matters: a declared kind, the wire
 * contract's fifth kind (`derived`, which the design package's closed vocabulary does not
 * carry), or an explicit UNDECLARED marker naming the pointer that was looked up.
 *
 * An empty slot and an undeclared slot look identical to a reader, and only one of them is
 * a statement. On a surface whose entire subject is what was NOT said, an unmarked absence
 * is the last thing that should be allowed on screen.
 */

import { type ReactNode } from 'react';

import { ProvenanceChip } from '../../design/primitives';

import { isDesignChipKind, lookupProvenance, type ProvenanceEntry } from './provenance';
import styles from './silence.module.css';

export interface ProvenanceSlotProps {
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
