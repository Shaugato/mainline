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

import { Disclosure, ProvenanceChip } from '../../../design/primitives';
import {
  capReading,
  capsPlain,
  completeness,
  type AuditCell,
  type AuditView,
  type EmptinessReason,
} from '../model';
import styles from '../audit.module.css';

/**
 * "No rows", and then the reason there are none — R3.
 *
 * The reason is TWO things and they are kept apart on purpose. The first is this console's
 * sentence about what a zero is: a fact about what was reachable here, never a claim that
 * nothing exists. The second is the kernel's own sentence about this deployment, quoted
 * verbatim in the mono face, because R8 forbids paraphrasing `unreachable[].probe` and
 * because a reader has to be able to see how far the kernel's claim actually reaches.
 *
 * What is NOT here: any assertion that the quoted sentence explains THIS view's zero. The
 * emitter said what it said. The console prints it and lets the reader judge.
 */
function EmptyRow({
  columns,
  emptiness,
  view,
}: {
  readonly columns: number;
  readonly emptiness: EmptinessReason;
  readonly view: string;
}): ReactNode {
  return (
    <tr>
      <td colSpan={Math.max(columns, 1)}>
        <p className={styles.detail} data-testid={`empty-${view}`}>
          <strong>No rows — </strong>
          {emptiness.category} An empty aggregate is a statement about what was reachable under
          the caps above, not a statement that nothing exists.
        </p>
        {emptiness.quoted.map((sentence) => (
          <pre className={styles.statement} key={sentence} data-testid={`empty-probe-${view}`}>
            {sentence}
          </pre>
        ))}
        {emptiness.unquoted === null ? null : (
          <p className={styles.detail} data-testid={`empty-unquoted-${view}`}>
            {emptiness.unquoted}
          </p>
        )}
        {emptiness.quoted.length === 0 ? null : (
          <p className={styles.columnType}>
            Quoted above, unchanged, from this payload&rsquo;s own account of what the connection
            that produced it can and cannot reach. It is the kernel&rsquo;s sentence and not this
            console&rsquo;s.
          </p>
        )}
      </td>
    </tr>
  );
}

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

export function ViewTable({
  view,
  emptiness,
}: {
  readonly view: AuditView;
  readonly emptiness: EmptinessReason;
}): ReactNode {
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
      {/*
        * THE PLAIN SENTENCE IS VISIBLE IN BOTH MODES; THE PRECISE READING IS ONE CLICK AWAY.
        *
        * R6 lists byte and row caps among the things PLAIN collapses, and the brief requires a
        * lay reader to get one sentence saying these are the limits the read-only auditor
        * account runs under — with the exact numbers still on the page. Both hold here: the
        * plain sentence is painted, `capReading().detail` is inside the disclosure with every
        * number intact, and `caps-<view>` still contains both, so a reader searching the page
        * for "very probably discarded" finds it whether the control is open or shut.
        */}
      <div className={styles.limit} data-testid={`caps-${view.view}`}>
        <span className={styles.limitTitle}>caps</span>
        <p className={styles.detail}>{capsPlain(view)}</p>
        <Disclosure summary="Show what this view's caps mean for whether the answer is complete">
          <p className={styles.detail} data-testid={`caps-detail-${view.view}`}>
            {caps.detail}
          </p>
        </Disclosure>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption>
            Rows are positional against the declared columns. Values are rendered as the driver
            produced them; this console does not coerce.
          </caption>
          <thead>
            {/*
              * THE DECLARED TYPE STAYS BESIDE ITS OWN COLUMN, AND THAT IS A RULING.
              *
              * R6 lists "column type lists" among the things PLAIN collapses, and the obvious
              * reading of that is a disclosure under the table pairing each name with its type.
              * It was built that way and then REVERTED, for a reason worth writing down: it put
              * every column name in the DOM twice, which made `getByText(name, { exact: true })`
              * ambiguous — a by-text query in another surface's test, and, far more importantly,
              * a reader's own Ctrl-F. A page where searching for a column name lands you in a
              * type table rather than in the data is worse for BOTH audiences.
              *
              * The distinction that survives: a `sql_type` is one short token attached to one
              * heading, not a list anybody wades through. The genuine column list on this
              * screen — the eight columns of `mainline_meas.external_attestation` — IS collapsed,
              * in `ReachPanel`, where collapsing costs nothing and duplicates nothing.
              */}
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
              <EmptyRow
                columns={view.columns.length}
                emptiness={emptiness}
                view={view.view}
              />
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
        /*
         * R6 lists SQL statements among the things PLAIN collapses. It is collapsed and never
         * removed: the statement is in the DOM in both modes, is found by a text search, and is
         * open by default in FULL DETAIL. It is rendered VERBATIM inside — this is the exact
         * text the database executed, and paraphrasing it would make it unreproducible.
         */
        <Disclosure summary="Show the exact statement the database ran to produce this table">
          <pre className={styles.statement} data-testid={`statement-${view.view}`}>
            {view.statement}
          </pre>
        </Disclosure>
      )}
    </section>
  );
}
