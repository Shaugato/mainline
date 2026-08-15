// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The non-textual half of the diff, and the gap the witnesses do not cover.
 *
 * ── Anchors ──────────────────────────────────────────────────────────────────────
 *
 * A dropped anchor is not a formatting detail: `anchor_drop` is a declared reason in
 * `mainline.identity_residue` (ARCHITECTURE.md §5.3), which is the blocking artefact of
 * Conservation of Blame Mass. So dropped anchors get their own list, by name, in the
 * ancestor's order, and the panel says plainly that the comparison is exact string
 * equality — because a reader who assumes it is fuzzy will read an absence as a match.
 *
 * ── The Control Assertion Tuple ──────────────────────────────────────────────────
 *
 * Rendered as pointers and canonical JSON, with no interpretation of any key. The
 * contract says the shape is the algorithms domain's and that the console "asserts
 * nothing about its internals"; a panel that knew `countersignature` was special would be
 * a second, undeclared copy of the lattice living in TypeScript.
 *
 * ── The gap ──────────────────────────────────────────────────────────────────────
 *
 * `UnwitnessedPanel` is the one that matters. It lists changes this browser observed for
 * which no witness row accounts, and it does nothing else with them — no reason, no rank,
 * no adjective. An unwitnessed change may be entirely innocent. What it may not be is
 * invisible, and on every competing product it is.
 */

import { type ReactNode } from 'react';

import { ProvenanceChip } from '../../../design/primitives';
import styles from '../diff.module.css';
import type { AnchorResidue, CatDiff, ScalarChange, UnwitnessedChange } from '../model';
import { Disclosure, Gloss } from './Plain';

export function AnchorResidueView({ anchors }: { readonly anchors: AnchorResidue }): ReactNode {
  const changed = anchors.dropped.length + anchors.added.length;
  return (
    <section
      className={styles.section}
      data-testid="anchor-residue"
      aria-labelledby="diff-anchor-head"
    >
      <div className={styles.sectionHead}>
        <h3 className={styles.sectionTitle} id="diff-anchor-head">
          Anchors
        </h3>
        <span className={styles.verdictLabel}>
          {anchors.dropped.length} dropped · {anchors.added.length} added · {anchors.kept.length}{' '}
          kept
        </span>
      </div>

      <div className={styles.chips}>
        <ProvenanceChip kind="db:column" detail="clause_version.anchor_set" />
        <ProvenanceChip kind="recomputed" detail="set difference, exact string equality" />
      </div>

      <Gloss>
        An <em>anchor</em> is one of the fixed handles a rule is filed under — the short names
        that let a later reader find this rule again and tell it apart from a similar one. A
        handle that disappears between two versions is how a rule quietly stops being found, so
        the count above is stated whether or not anything changed.
      </Gloss>

      <p className={styles.note}>
        Compared by exact string equality — no case folding, no trimming, no fuzzy match.
        Deciding that two spellings are one anchor is an identity judgement, and identity
        judgements belong to the cascade, not to this screen.
      </p>

      {changed === 0 ? (
        <p className={styles.settled}>The anchor set is unchanged.</p>
      ) : (
        <Disclosure
          summary="Show which handles were dropped and which were added"
          testId="diff-anchor-disclosure"
        >
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption className={styles.caption}>
                Anchors present in one version and not the other. An anchor dropped between
                versions is a declared reason for an{' '}
                <code className={styles.mono}>anchor_drop</code> row in{' '}
                <code className={styles.mono}>mainline.identity_residue</code>.
              </caption>
              <thead>
                <tr>
                  <th scope="col">anchor</th>
                  <th scope="col">state</th>
                </tr>
              </thead>
              <tbody>
                {anchors.dropped.map((value) => (
                  <tr key={`dropped-${value}`}>
                    <th scope="row" className={styles.mono}>
                      {value}
                    </th>
                    <td className={styles.changedCell}>dropped</td>
                  </tr>
                ))}
                {anchors.added.map((value) => (
                  <tr key={`added-${value}`}>
                    <th scope="row" className={styles.mono}>
                      {value}
                    </th>
                    <td className={styles.changedCell}>added</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Disclosure>
      )}

      {anchors.duplicatedInParent.length + anchors.duplicatedInVersion.length === 0 ? null : (
        <p className={styles.note}>
          Repeated values in the stored array:{' '}
          <code className={styles.mono}>
            {[...anchors.duplicatedInParent, ...anchors.duplicatedInVersion].join(', ')}
          </code>
          . The comparison above is over distinct values, so a repeat is reported rather than
          absorbed.
        </p>
      )}
    </section>
  );
}

export function CatDeltaView({ cat }: { readonly cat: CatDiff }): ReactNode {
  return (
    <section className={styles.section} data-testid="cat-delta" aria-labelledby="diff-cat-head">
      <div className={styles.sectionHead}>
        <h3 className={styles.sectionTitle} id="diff-cat-head">
          Control Assertion Tuple
        </h3>
        <span className={styles.verdictLabel}>
          {cat.availability === 'both'
            ? `${cat.changes.length} change(s)`
            : `cat_json present on: ${cat.availability.replace('_', ' ')}`}
        </span>
      </div>

      <div className={styles.chips}>
        <ProvenanceChip kind="db:column" detail="clause_version.cat_json" />
        <ProvenanceChip kind="recomputed" detail="structural walk, RFC 6901 pointers" />
      </div>

      {cat.truncated === null ? null : (
        <div className={styles.absence}>
          <p className={styles.absenceHead}>TRUNCATED</p>
          <p className={styles.absenceBody}>
            The walk stopped at {cat.truncated.cap} changes. The list below is a prefix of the
            real difference, not the whole of it.
          </p>
        </div>
      )}

      <Gloss>
        The <em>Control Assertion Tuple</em> is the machine-readable half of the rule: the same
        requirement written as structured fields rather than as a sentence, so that a check can
        be run against it. This console displays those fields and their addresses and states
        nothing about what any one of them means — that meaning belongs to the rule-book, not to
        a screen.
      </Gloss>

      {cat.changes.length === 0 ? (
        <p className={styles.settled}>
          {cat.availability === 'neither'
            ? 'Neither version carries a Control Assertion Tuple.'
            : 'The Control Assertion Tuple is unchanged.'}
        </p>
      ) : (
        <Disclosure
          summary="Show the structured fields that changed, one address at a time"
          testId="diff-cat-disclosure"
        >
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption className={styles.caption}>
                Field-level differences, as JSON Pointers into{' '}
                <code className={styles.mono}>cat_json</code>. The console renders the tuple as
                structured data and asserts nothing about what any key means.
              </caption>
              <thead>
                <tr>
                  <th scope="col">pointer</th>
                  <th scope="col">kind</th>
                  <th scope="col">ancestor</th>
                  <th scope="col">this version</th>
                </tr>
              </thead>
              <tbody>
                {cat.changes.map((change) => (
                  <tr key={`${change.pointer}-${change.kind}`}>
                    <th scope="row" className={styles.mono}>
                      {change.pointer === '' ? '(root)' : change.pointer}
                    </th>
                    <td>{change.kind}</td>
                    <td className={styles.mono}>{change.fromRepr ?? '∅'}</td>
                    <td className={styles.mono}>{change.toRepr ?? '∅'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Disclosure>
      )}

      <p className={styles.note}>
        <code className={styles.mono}>cat_key</code>{' '}
        {cat.keyChanged === null
          ? 'was absent on at least one side, so no comparison was made'
          : cat.keyChanged
            ? 'differs between the two versions'
            : 'is unchanged'}
        . <code className={styles.mono}>cat_confidence</code>{' '}
        {cat.confidenceChanged === null
          ? 'was absent on at least one side'
          : cat.confidenceChanged
            ? 'differs'
            : 'is unchanged'}
        .
      </p>
    </section>
  );
}

export function ScalarTable({ scalars }: { readonly scalars: readonly ScalarChange[] }): ReactNode {
  return (
    <section
      className={styles.section}
      data-testid="scalar-columns"
      aria-labelledby="diff-scalar-head"
    >
      <div className={styles.sectionHead}>
        <h3 className={styles.sectionTitle} id="diff-scalar-head">
          Columns
        </h3>
        <span className={styles.verdictLabel}>
          {scalars.filter((scalar) => scalar.changed).length} changed
        </span>
      </div>
      <div className={styles.chips}>
        <ProvenanceChip kind="db:column" detail="mainline.clause_version" />
      </div>
      <Gloss>
        Everything the database stores about each of the two versions, side by side, with no
        selection: the fields that changed and the fields that did not. It is the longest thing
        on this screen and the least interpreted, which is why it is the one behind a click.
      </Gloss>
      <Disclosure
        summary="Show every stored field for both versions, side by side"
        testId="diff-scalar-disclosure"
      >
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption className={styles.caption}>
              Every compared column of{' '}
              <code className={styles.mono}>mainline.clause_version</code>, both sides, verbatim.
              Columns marked <em>presentation only</em> are never identity — a renumber is not an
              edit.
            </caption>
            <thead>
              <tr>
                <th scope="col">column</th>
                <th scope="col">ancestor</th>
                <th scope="col">this version</th>
                <th scope="col">state</th>
              </tr>
            </thead>
            <tbody>
              {scalars.map((scalar) => (
                <tr key={scalar.column} data-changed={scalar.changed ? 'true' : 'false'}>
                  <th scope="row" className={styles.mono}>
                    {scalar.column}
                    {scalar.presentationOnly ? (
                      <span className={styles.note}> presentation only</span>
                    ) : null}
                  </th>
                  <td
                    className={`${styles.mono} ${scalar.changed ? styles.changedCell : styles.unchangedCell}`}
                  >
                    {scalar.fromRepr}
                  </td>
                  <td
                    className={`${styles.mono} ${scalar.changed ? styles.changedCell : styles.unchangedCell}`}
                  >
                    {scalar.toRepr}
                  </td>
                  <td>{scalar.changed ? 'changed' : 'unchanged'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Disclosure>
    </section>
  );
}

export function UnwitnessedPanel({
  unwitnessed,
  comparable,
}: {
  readonly unwitnessed: readonly UnwitnessedChange[];
  readonly comparable: boolean;
}): ReactNode {
  return (
    <section
      className={styles.section}
      data-testid="unwitnessed"
      aria-labelledby="diff-unwitnessed-head"
    >
      <div className={styles.sectionHead}>
        <h3 className={styles.sectionTitle} id="diff-unwitnessed-head">
          Changes no witness accounts for
        </h3>
        <span className={styles.verdictLabel}>{unwitnessed.length}</span>
      </div>

      {!comparable ? (
        <p className={styles.settled}>
          Nothing was compared, so nothing can be said about what the witnesses do or do not
          cover.
        </p>
      ) : unwitnessed.length === 0 ? (
        <p className={styles.settled}>
          Every change this browser observed is named by a witness row.
        </p>
      ) : (
        <>
          <p className={styles.note}>
            The console states these and stops. It does not say what any of them means: only
            the database may say why a control changed, and for these it has not.
          </p>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption className={styles.caption}>
                Observed by this browser; not named by any{' '}
                <code className={styles.mono}>delta_witness</code> row in this payload.
              </caption>
              <thead>
                <tr>
                  <th scope="col">subject</th>
                  <th scope="col">where</th>
                  <th scope="col">observation</th>
                </tr>
              </thead>
              <tbody>
                {unwitnessed.map((entry, index) => (
                  <tr key={`${entry.kind}-${entry.subject}-${index}`}>
                    <th scope="row" className={styles.mono}>
                      {entry.subject}
                    </th>
                    <td className={styles.mono}>{entry.kind}</td>
                    <td>{entry.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
