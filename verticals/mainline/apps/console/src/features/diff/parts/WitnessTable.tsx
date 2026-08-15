// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `mainline.delta_witness` — the only thing on this screen that says WHY.
 *
 * Three states, and the difference between the last two is the reason this component
 * exists at all:
 *
 *   rows present   → the table, verbatim. Every cell is mono, nothing is truncated,
 *                    nothing is re-worded, and the `note` column carries the database's
 *                    sentence exactly as it was written.
 *   `witnesses: []`→ "the emitter reports that there are none". A CLAIM by the emitter.
 *   `witnesses:null`→ **WITNESS UNAVAILABLE**. The payload carries no witness member and
 *                    the emitter said nothing about whether any exist. NOT a claim, and
 *                    rendered as an absence rather than as a reassurance.
 *
 * `contracts/clause.schema.json` states that distinction on `$defs.delta_verdict` and
 * `docs/leads/ui.md` §4 requires this surface to hold to it. A single "no witnesses"
 * string covering both would turn a silence into an assertion, on the one screen where
 * the assertion decides whether a permit can merge.
 *
 * The binding column is the console's own arithmetic — did this browser observe a change
 * where the row says one happened — and it is rendered in the SANS face, beside a state
 * word, so it can never be mistaken for something the database emitted. No chip in this
 * table says `recomputed`; the reason for a change is never something we computed.
 */

import { type ReactNode } from 'react';

import { ProvenanceChip } from '../../../design/primitives';
import styles from '../diff.module.css';
import type { WitnessBinding } from '../model';
import { Disclosure, Gloss } from './Plain';

const STATE_WORD: Readonly<Record<string, string>> = {
  bound: 'corroborated',
  no_observed_change: 'no observed change',
  unresolvable_field: 'field not recognised',
  uncorroborable: 'nothing to compare',
};

export function WitnessTable({ binding }: { readonly binding: WitnessBinding }): ReactNode {
  return (
    <section
      className={styles.section}
      data-testid="delta-witnesses"
      aria-labelledby="diff-witness-head"
    >
      <div className={styles.sectionHead}>
        <h3 className={styles.sectionTitle} id="diff-witness-head">
          Why — the delta witnesses
        </h3>
        <span className={styles.verdictLabel}>
          minimal:{' '}
          {binding.minimal === null
            ? 'not established'
            : binding.minimal
              ? 'yes'
              : 'no'}
        </span>
      </div>

      <Gloss>
        A <em>witness</em> is a row the database wrote at the same moment as the edit, naming one
        field that changed and saying, in its own words, why. It is the only thing on this screen
        that gives a reason: everything else here is either the wording itself or arithmetic this
        browser did over it. <em>Minimal</em> above says whether the database claims these rows
        are the smallest set that accounts for the change; <strong>not established</strong> means
        it made no such claim, which is not the same as claiming they are not.
      </Gloss>

      {binding.availability === 'unavailable' ? (
        <div className={styles.absence}>
          <p className={styles.absenceHead}>WITNESS UNAVAILABLE</p>
          <p className={styles.absenceBody}>
            This payload carries no <code className={styles.mono}>witnesses</code> member. The
            emitter has not said that there are none — it has said nothing. The console shows
            the changes it observed above and offers no account of them, because the only
            account it could offer would be one it invented.
          </p>
        </div>
      ) : binding.availability === 'asserted_none' ? (
        <div className={styles.absence}>
          <p className={styles.absenceHead}>NO WITNESSES</p>
          <p className={styles.absenceBody}>
            The payload carries an empty <code className={styles.mono}>witnesses</code> array:
            the emitter reports that there are none. That is a claim, and it is a different
            claim from an absent witness member.
          </p>
        </div>
      ) : (
        <>
          <div className={styles.chips}>
            <ProvenanceChip kind="db:column" detail="mainline.delta_witness" />
          </div>
          {/*
           * The ROWS collapse; the three states above never do.
           *
           * WITNESS UNAVAILABLE and NO WITNESSES are stated absences, and R6 forbids
           * collapsing one — a reader who does not click must still be told that the
           * database said nothing, and told that it is different from the database saying
           * there is nothing. Only the populated table is behind the click, and it is
           * verbatim on both sides of it.
           */}
          <Disclosure
            summary="Show the database’s own reasons, row by row"
            testId="diff-witness-disclosure"
          >
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <caption className={styles.caption}>
                  Every row below was written by the database in the same transaction as the
                  clause version. Nothing in this table was composed by the console.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">rule_id</th>
                    <th scope="col">field</th>
                    <th scope="col">from_repr</th>
                    <th scope="col">to_repr</th>
                    <th scope="col">note</th>
                    <th scope="col">this browser</th>
                  </tr>
                </thead>
                <tbody>
                  {binding.witnesses.map((bound, index) => (
                    <tr key={`${bound.witness.rule_id}-${bound.witness.field}-${index}`}>
                      <th scope="row" className={styles.mono}>
                        {bound.witness.rule_id}
                      </th>
                      <td className={styles.mono}>{bound.witness.field}</td>
                      <td className={styles.mono}>{bound.witness.from_repr}</td>
                      <td className={styles.mono}>{bound.witness.to_repr}</td>
                      <td>{bound.witness.note}</td>
                      <td>
                        <span className={styles.state} data-state={bound.state}>
                          {STATE_WORD[bound.state] ?? bound.state}
                        </span>
                        <span className={styles.visuallyHidden}>. </span>
                        <p className={styles.note}>{bound.bindingNote}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Disclosure>
        </>
      )}
    </section>
  );
}
