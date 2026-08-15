// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * L0 intake → L1 leaf → L2 node → L3 checkpoint (ARCHITECTURE.md §7.2).
 *
 * An ordered list, not a diagram. Four reasons, all of which outrank "it would look
 * better as an SVG": it prints, it is selectable text, a screen reader reads it in order,
 * and it cannot drift from the data because every cell is derived in `model.ts`.
 *
 * L0 renders as PRESENT-BUT-UNSEEN rather than being omitted. `ledger_intake` exists; it
 * is not part of the `ledger` read contract, and a chain drawn without it would teach a
 * reader that the sequencer has no input stage.
 */

import { type ReactNode } from 'react';

import { Digest } from '../../../design/primitives';
import type { ChainLayer } from '../model';
import styles from '../custody.module.css';

export function ChainView({ layers }: { readonly layers: readonly ChainLayer[] }): ReactNode {
  return (
    <ol className={styles.chain} data-testid="custody-chain">
      {layers.map((layer) => (
        <li
          key={layer.level}
          className={styles.chainCell}
          data-absent={layer.count === null ? 'true' : 'false'}
          data-level={layer.level}
        >
          <span className={styles.chainLevel}>
            {layer.level} · {layer.title}
          </span>
          <span className={styles.chainCount} data-testid={`chain-count-${layer.level}`}>
            {layer.count === null ? 'not visible from here' : `${layer.count} row(s)`}
          </span>
          {layer.digest === null ? (
            <span className={styles.chainLevel}>{layer.digestLabel}</span>
          ) : (
            <Digest value={layer.digest} label={layer.digestLabel} copyable={false} />
          )}
          <p className={styles.chainPurpose}>{layer.purpose}</p>
        </li>
      ))}
    </ol>
  );
}
