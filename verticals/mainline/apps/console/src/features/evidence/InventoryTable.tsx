// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The inventory: one row per file the manifest lists.
 *
 * Three decisions worth defending.
 *
 * **The full 64-character digest is in the DOM, unclipped.** A digest a reader cannot
 * select and paste into `sha256sum` is decoration. The column wraps rather than
 * truncating, and the table scrolls horizontally rather than eliding a value.
 *
 * **The state cell is a word, a weight and a colour — never a colour alone.** A red dot
 * is not a finding to a dichromat, to a photocopier or to a screen reader.
 *
 * **A frame says what it serves.** The file name decodes to a canonical request key,
 * the key matches a declared resource, and the resource names the backend domain that
 * owes the endpoint — or says that nobody does. `clause_ancestry` has no owner
 * (`docs/leads/ui.md` §4) and this table is where that stops being a footnote.
 */

import { type ReactNode } from 'react';

import { Mono } from '../../design/primitives';

import styles from './evidence.module.css';
import type { DigestState, InventoryRow } from './model';

const STATE_WORD: Readonly<Record<DigestState, string>> = Object.freeze({
  unchecked: 'not checked',
  match: 'match',
  mismatch: 'MISMATCH',
  unreadable: 'UNREADABLE',
});

const STATE_SPOKEN: Readonly<Record<DigestState, string>> = Object.freeze({
  unchecked: 'this file was not hashed',
  match: 'the bytes hash to the digest the manifest declares',
  mismatch: 'the bytes do NOT hash to the digest the manifest declares',
  unreadable: 'the file could not be read at all',
});

function Serves({ row }: { readonly row: InventoryRow }): ReactNode {
  if (row.kind !== 'frame') {
    return <span className={styles.kind}>carried verbatim; no request addresses it</span>;
  }
  if (row.frame === null) {
    return <span className={styles.state}>name does not decode to a request key</span>;
  }
  return (
    <>
      <Mono className={styles.servesKey ?? ''}>{row.frame.requestKey}</Mono>
      {row.frame.resourceKey === null ? (
        <span>no declared resource can produce this request</span>
      ) : (
        <span>
          {row.frame.resourceKey} · owed by {row.frame.owner ?? 'nobody — unassigned'}
        </span>
      )}
      {row.frame.canonical ? null : <span> · non-canonical file name</span>}
    </>
  );
}

export function InventoryTable({ rows }: { readonly rows: readonly InventoryRow[] }): ReactNode {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} data-testid="evidence-inventory">
        <caption>
          Every file <code>manifest.json</code> lists, in manifest order. The digest column is
          the value the manifest declares; the state column is what this browser computed.
        </caption>
        <thead>
          <tr>
            <th scope="col">Path</th>
            <th scope="col">Serves</th>
            <th scope="col">Declared bytes</th>
            <th scope="col">Read</th>
            <th scope="col">Declared SHA-256</th>
            <th scope="col">State</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.path} data-testid={`evidence-row:${row.path}`} data-state={row.state}>
              <th scope="row" className={styles.path}>
                {row.path}
              </th>
              <td className={styles.serves}>
                <Serves row={row} />
              </td>
              <td data-numeric="true">{row.declaredBytes}</td>
              <td data-numeric="true">{row.actualBytes ?? '—'}</td>
              <td className={styles.path}>{row.declaredDigest}</td>
              <td>
                <span className={styles.state} data-state={row.state}>
                  {STATE_WORD[row.state]}
                </span>
                <span className={styles.srOnly}> — {STATE_SPOKEN[row.state]}</span>
                {row.detail === null ? null : (
                  <p className={styles.rowDetail} data-testid={`evidence-row-detail:${row.path}`}>
                    {row.detail}
                  </p>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
