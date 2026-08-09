// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * One `mainline_audit.v_*` view, rendered generically from the columns it declares.
 *
 * The console holds no column list. `contracts/audit.schema.json` carries the columns and
 * the rows positionally, and this component renders whatever arrives — because the column
 * contracts belong to the recall and MCP domains, and a console that hard-coded them would
 * be asserting something about a view it does not own.
 *
 * Two things are shown ABOVE the data, deliberately, because both change what the numbers
 * mean:
 *
 *   • the completeness flag — `ancestry_complete` or its equivalent. A view whose closures
 *     were truncated is an UNDERCOUNT, and by how much is not knowable from here.
 *   • the caps the read ran under. A result AT the row cap is very probably cut, and 25
 *     rows returned against a cap of 25 is not "25 groups exist".
 *
 * Values are rendered exactly as the driver produced them. `null` renders as the word
 * `null` in a distinct style rather than as an empty cell, because an empty cell and a
 * SQL NULL mean different things and only one of them is a value.
 */

import { type ReactNode } from 'react';

import { ProvenanceChip } from '../../../design/primitives';
import { capReading, completeness, type AuditCell, type AuditView } from '../model';
import styles from '../audit.module.css';

function Cell({ value }: { readonly value: AuditCell }): ReactNode {
  if (value === null) {
    return (
      <span className={`${styles.cell} ${styles.cellNull}`} data-null="true">
        null
      </span>
    );
  }
  return (
    <span className={styles.cell} data-kind={typeof value}>
      {typeof value === 'boolean' ? String(value) : value}
    </span>
  );
}

export function ViewTable({ view }: { readonly view: AuditView }): ReactNode {
  const caps = capReading(view);
  const complete = completeness(view);

  return (
    <section
      className={styles.viewBlock}
      data-view={view.view}
      data-cap={caps.state}
      data-complete={complete.known ? String(complete.complete) : 'unknown'}
      aria-label={view.view}
    >
      <div className={styles.headerTop}>
        <span className={styles.viewName}>{view.view}</span>
        <ProvenanceChip kind="db:column" detail={`${view.columns.length} declared column(s)`} />
      </div>

      <p className={styles.detail} data-testid={`completeness-${view.view}`}>
        <strong>Completeness. </strong>
        {complete.detail}
      </p>
      <p className={styles.detail} data-testid={`caps-${view.view}`}>
        <strong>Caps. </strong>
        {caps.detail}
      </p>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption>
            Rows are positional against the declared columns. Values are rendered as the driver
            produced them; this console does not coerce.
          </caption>
          <thead>
            <tr>
              {view.columns.map((column) => (
                <th key={column.name} scope="col">
                  {column.name}
                  <span className={styles.columnType}>{column.sql_type ?? 'type not declared'}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.rows.length === 0 ? (
              <tr>
                <td colSpan={Math.max(view.columns.length, 1)}>
                  No rows. An empty aggregate is a statement about what was reachable under the
                  caps above, not a statement that nothing exists.
                </td>
              </tr>
            ) : (
              view.rows.map((row, rowIndex) => (
                <tr key={`row-${rowIndex}`}>
                  {view.columns.map((column, columnIndex) => (
                    <td key={column.name}>
                      <Cell value={row[columnIndex] ?? null} />
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {view.statement === null || view.statement === undefined ? (
        <p className={styles.detail}>
          This view carried no statement, so what produced these rows is not shown. The Managed
          MCP surface allows one statement per call; a result with no statement beside it cannot
          be reproduced by a reader.
        </p>
      ) : (
        <pre className={styles.statement} data-testid={`statement-${view.view}`}>
          {view.statement}
        </pre>
      )}
    </section>
  );
}
