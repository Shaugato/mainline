// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The `arithmetic` blob, expanded readably — every leaf, with its path and its kind.
 *
 * This is the difference between *"we did not show it"* and *"it scored 0.31 against a
 * threshold of 0.45, calibrated on a temporally-blocked gold set; here is the calibration
 * commit"*. So the blob is expanded rather than pretty-printed: a `<pre>` of JSON is
 * technically complete and practically unreadable, and the one row that matters —
 * `tau/severity_5: 0`, the numeric form of *a fatality is always recalled* — would be
 * buried in it.
 *
 * ── THE RULE THIS COMPONENT ENFORCES ─────────────────────────────────────────────
 *
 * A raw similarity is never displayed without a calibrated `p_relevant` beside it.
 * `mainline_meas.recall_candidate.p_relevant` is calibrated and the DDL comment is blunt:
 * *raw cosine never reaches a human*. A cosine of 0.58 reads as "58% relevant" to every
 * reader who has not spent a week with the calibration curve, and on a screen whose whole
 * purpose is to be quoted in a dispute that is not a rendering defect, it is a
 * misstatement.
 *
 * When no calibrated value accompanies the blob, this component WITHHOLDS the raw values —
 * the rows stay, the paths stay, the kinds stay, and the numbers are replaced by a marker
 * that names what is missing. Withholding a number and saying so is honest; showing it
 * with a caption nobody reads is not.
 */

import { type ReactNode } from 'react';

import { Mono } from '../../design/primitives';

import { arithmeticView, type ArithmeticLeaf } from './model';
import styles from './silence.module.css';
import type { JsonObject, JsonValue, SilenceEntry } from '../../data/types.generated';

export interface ArithmeticViewProps {
  readonly arithmetic: JsonObject;
  readonly entry: Pick<SilenceEntry, 'score' | 'policy_version'>;
  /** Distinguishes the tables when several entries are on screen. */
  readonly testId: string;
}

function renderValue(value: JsonValue): string {
  if (value === null) return 'null';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return '[] (empty)';
  return '{} (empty)';
}

function Row({
  leaf,
  withheld,
}: {
  readonly leaf: ArithmeticLeaf;
  readonly withheld: boolean;
}): ReactNode {
  return (
    <tr data-testid="arithmetic-row" data-kind={leaf.kind} data-pointer={leaf.pointer}>
      <td>{leaf.path.join(' · ')}</td>
      <td>
        {withheld ? (
          <span className={styles.withheld} data-testid="arithmetic-withheld">
            withheld — no calibrated p_relevant accompanies it
          </span>
        ) : (
          renderValue(leaf.value)
        )}
      </td>
      <td className={styles.kindTag}>{leaf.kind}</td>
    </tr>
  );
}

export function ArithmeticView({ arithmetic, entry, testId }: ArithmeticViewProps): ReactNode {
  const view = arithmeticView(arithmetic, entry);

  return (
    <div data-testid={testId} data-raw-admissible={view.rawAdmissible ? 'true' : 'false'}>
      <h4 className={styles.kicker}>the arithmetic</h4>

      <dl className={styles.facts}>
        <dt>policy_version</dt>
        <dd>
          {view.policyVersion === null ? (
            <span className={styles.withheld} data-testid="arithmetic-no-policy">
              absent
            </span>
          ) : (
            <Mono data-testid="arithmetic-policy-version">{view.policyVersion}</Mono>
          )}
        </dd>
        <dt>calibration commit</dt>
        <dd>
          {view.calibrator === null ? (
            <span className={styles.withheld} data-testid="arithmetic-no-calibrator">
              absent — this blob names no calibration artefact
            </span>
          ) : (
            <Mono data-testid="arithmetic-calibrator">{view.calibrator}</Mono>
          )}
        </dd>
        <dt>calibrated p_relevant</dt>
        <dd>
          {view.calibrated === null ? (
            <span className={styles.withheld} data-testid="arithmetic-no-calibrated">
              absent
            </span>
          ) : (
            <>
              <Mono data-testid="arithmetic-calibrated">{view.calibrated.value}</Mono>{' '}
              <span className={styles.slotPointer}>
                from the {view.calibrated.source === 'column' ? 'score column' : 'arithmetic blob'}
              </span>
            </>
          )}
        </dd>
      </dl>

      {view.rawAdmissible ? null : (
        <p className={styles.prose} data-testid="arithmetic-raw-refused">
          This blob carries {view.rawSimilarities.length} raw similarity value(s) and no
          calibrated <Mono>p_relevant</Mono>. Their numbers are withheld below. A raw cosine
          reads as a percentage to anybody who has not studied the calibration curve, and this
          screen is written to be quoted in a dispute — so the console shows that the values
          exist, shows where they sit in the blob, and does not print them alone.
        </p>
      )}

      <table className={styles.arithmetic}>
        <caption className={styles.srOnly}>
          Every leaf of the arithmetic blob, with its path, its value and its kind.
        </caption>
        <thead>
          <tr>
            <th scope="col">path</th>
            <th scope="col">value</th>
            <th scope="col">kind</th>
          </tr>
        </thead>
        <tbody>
          {view.leaves.map((leaf) => (
            <Row
              key={leaf.pointer}
              leaf={leaf}
              withheld={leaf.kind === 'raw_similarity' && !view.rawAdmissible}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
