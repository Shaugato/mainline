// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The negative assertion, and the one writable table.
 *
 * ── THE NEGATIVE ASSERTION ────────────────────────────────────────────────────────
 *
 * `mainline_qa` holds the per-named-person deliberation measures — median deliberation
 * time, `mechanism_absent` share, floor-unmet counts. No MCP service account is ever
 * issued for that schema, on any tier, ever. The nightly surface test asserts it is
 * UNREACHABLE, and this panel renders the probes that assert it.
 *
 * An empty probe list is displayed as an ABSENCE, in the same weight as a finding, because
 * `contracts/audit.schema.json` is explicit: *an empty array is a claim that nothing was
 * checked, not a claim that nothing is reachable*. The three outcomes stay distinct all the
 * way to the pixel — `refused` is the assertion, `not_probed` establishes nothing, and
 * `reachable` would be a finding against the deployment.
 *
 * ── THE ONE WRITABLE TABLE ────────────────────────────────────────────────────────
 *
 * `mainline_meas.external_attestation` is the only MCP-writable table in the deployment,
 * INSERT-only and trigger-free by construction. It is represented here READ-ONLY: this
 * console never writes an evidentiary row (D5), and a form on this screen that could
 * insert an attestation would make the console a party to the record it displays.
 */

import { type ReactNode } from 'react';

import { Disclosure, Sqlstate } from '../../../design/primitives';
import { readUnreachable, type UnreachableProbe } from '../model';
import styles from '../audit.module.css';

/** The columns of `mainline_meas.external_attestation`, as ARCHITECTURE.md §5.7 declares them. */
const ATTESTATION_COLUMNS: readonly { readonly name: string; readonly note: string }[] = [
  { name: 'attestation_id', note: 'UUID, defaulted by the database' },
  { name: 'attestor', note: 'who is attesting, as they identify themselves' },
  { name: 'attestor_kind', note: 'witness | auditor | regulator | insurer | judge' },
  { name: 'subject_kind', note: 'checkpoint | exhibit_opening | view_result' },
  { name: 'subject_ref', note: 'what was attested to' },
  { name: 'outcome', note: 'verified | failed | indeterminate' },
  { name: 'detail_sha256', note: 'digest of the detail the attestor holds; the detail stays theirs' },
  { name: 'recorded_at', note: 'defaulted by the database, never supplied by the writer' },
];

export function ReachPanel({
  probes,
}: {
  readonly probes: readonly UnreachableProbe[];
}): ReactNode {
  const reading = readUnreachable(probes);

  return (
    <>
      <section className={styles.section} aria-label="Schemas that must be unreachable">
        <h3 className={styles.sectionTitle}>What the audit account cannot reach</h3>

        {/*
          * The plain sentence, above the table, because it changes what the table IS.
          * A reader who does not already know that `mainline_qa` holds per-named-person
          * measures reads this panel as a list of database names; a reader who does reads it
          * as the assertion the whole screen turns on.
          */}
        <p className={styles.prose} data-testid="unreachable-plain">
          Some tables in this system hold measures about named people — how long someone took to
          decide, how often a control was missing when they signed. No automated agent is ever
          given an account that can read them, on any tier, ever. This panel is where that promise
          is either demonstrated or shown not to have been tested.
        </p>

        <div className={styles.limit} data-testid="unreachable-reading">
          <span className={styles.limitTitle}>
            {reading.allRefused ? 'refused, and here is the refusal' : 'not established'}
          </span>
          <p className={styles.detail}>{reading.detail}</p>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table} data-testid="unreachable-table">
            <caption>
              Negative probes. The schema mainline_qa holds per-named-person deliberation
              measures; no MCP service account is ever issued for it, on any tier, ever.
            </caption>
            <thead>
              <tr>
                <th scope="col">schema</th>
                <th scope="col">probe</th>
                <th scope="col">outcome</th>
                <th scope="col">sqlstate</th>
              </tr>
            </thead>
            <tbody>
              {reading.probes.length === 0 ? (
                <tr>
                  <td colSpan={4}>No probe was carried.</td>
                </tr>
              ) : (
                reading.probes.map((probe) => (
                  <tr key={probe.schema_name} data-outcome={probe.outcome}>
                    <th scope="row" className={styles.cell}>
                      {probe.schema_name}
                    </th>
                    <td>
                      <pre className={styles.statement}>{probe.probe}</pre>
                    </td>
                    <td className={styles.outcome}>{probe.outcome}</td>
                    <td>
                      {probe.sqlstate === null || probe.sqlstate === undefined ? (
                        <span className={styles.cellNull}>none</span>
                      ) : (
                        <Sqlstate code={probe.sqlstate} showClass tone="refuse" />
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.section} aria-label="The write surface">
        <h3 className={styles.sectionTitle}>The only thing the MCP surface can write</h3>

        <p className={styles.prose}>
          The Managed MCP surface is read-only by default. Its entire write capability is a
          single INSERT into <code>mainline_meas.external_attestation</code> — one table,
          trigger-free by construction, into which an outside party records that they checked
          something and what they concluded.
        </p>

        <div className={styles.limit} data-testid="attestation-read-only">
          <span className={styles.limitTitle}>read-only here</span>
          <p className={styles.detail}>
            This console never writes an evidentiary row. The table is shown as a shape, not as
            a form: an attestation is a statement by an outside party, and a console that could
            compose one would make itself a party to the record it displays.
          </p>
        </div>

        {/*
          * A column list, so R6 collapses it in PLAIN and opens it in FULL DETAIL. Every
          * column and every note is unchanged and in the DOM in both modes; what changes is
          * whether a reader who came here to learn that the console cannot write has to scroll
          * past eight column definitions to find out that it cannot.
          */}
        <Disclosure summary="Show the eight columns an outside attestor would fill in">
          <div className={styles.tableWrap}>
            <table className={styles.table} data-testid="attestation-shape">
              <caption>
                mainline_meas.external_attestation — the columns an attestor supplies, and the two
                the database supplies for them.
              </caption>
              <thead>
                <tr>
                  <th scope="col">column</th>
                  <th scope="col">what it carries</th>
                </tr>
              </thead>
              <tbody>
                {ATTESTATION_COLUMNS.map((column) => (
                  <tr key={column.name}>
                    <th scope="row" className={styles.cell}>
                      {column.name}
                    </th>
                    <td>{column.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Disclosure>
      </section>
    </>
  );
}
