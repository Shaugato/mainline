// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * USE CASE 2, HALF TWO — what the search declined to put in front of anybody.
 *
 * Ruling R9 of `docs/leads/two-audience-ux-plan.md` selects this as the case no competitor
 * demonstrates, and gives the reason: it requires the product to volunteer its own negative
 * space. The fleet half is on the propagation surface; this half is the ledger of what was
 * looked at and not shown, and the receipt that says how far the search's own claim reaches.
 *
 * ── THE SENTENCE THIS PANEL EXISTS TO KEEP HONEST ────────────────────────────────
 *
 * The tempting version of this screen says *nothing was withheld from you*. That sentence
 * is not available and this panel does not go near it. What Proof of Exhausted Recall
 * establishes is narrower and is stated in the receipt's own words, which the payload
 * carries and which this console reproduces character for character:
 *
 *   > PER proves exhaustion of the retrieval that ran, not of the corpus.
 *
 * Everything in this panel is written to sit UNDER that sentence rather than around it. In
 * particular, when the ledger is empty — which is what the seeded demo permit answers with
 * today: `entries: []` and a full receipt — the plain reading is **not** "nothing was
 * withheld". It is: on this subject the search surfaced everything it found at or above the
 * threshold, and here is the receipt that makes the search's own boundary checkable. The
 * difference between those two sentences is the entire product.
 *
 * ── NUMBERS COME FROM THE PAYLOAD OR THEY DO NOT APPEAR ──────────────────────────
 *
 * `theta`, `s`, `n` and the row count are read off the model this screen already holds. If
 * the exchange has not landed, this panel prints no numbers and says which nothing it is.
 * Nothing here is illustrative and nothing is a placeholder.
 *
 * ── LAZY ─────────────────────────────────────────────────────────────────────────
 *
 * `SilenceScreen` reaches this module through `React.lazy`, so the prose is its own chunk,
 * fetched after the surface paints. `budgets.json` is untouched by this wave (R10).
 */

import { type ReactNode } from 'react';

import { hrefWithDetail, useDetailMode } from '../../app/detail-mode';
import { Mono } from '../../design/primitives';

import { PER_BOUND_GLOSS } from './model';
import styles from './silence.module.css';
import type { SilenceModel } from './useSilenceData';

export interface UseCaseTwoProps {
  /** The screen's model. Read, never re-fetched: this panel performs no exchange. */
  readonly model: SilenceModel;
  /** True when no transport was provided at all — a different nothing from a failure. */
  readonly noSource: boolean;
}

/** The kicker, so the two halves of the case are recognisable as one case. */
const KICKER = 'use case 2 — what the system did not tell you';

/** Which nothing the screen is showing, in the model's own vocabulary. */
function absenceOf(model: SilenceModel, noSource: boolean): string | null {
  if (noSource) {
    return 'No transport was provided to this surface, so no read was attempted.';
  }
  const silence = model.silence;
  if (silence.status === 'idle' || silence.status === 'loading') {
    return 'The read is still in flight.';
  }
  if (silence.status === 'failed') {
    return `The read did not complete: ${silence.failure}.`;
  }
  if (silence.status === 'refused') {
    return `The database refused this read, under ${silence.refusal.constraint}.`;
  }
  return null;
}

export function UseCaseTwo({ model, noSource }: UseCaseTwoProps): ReactNode {
  const mode = useDetailMode();
  const propagationHref = hrefWithDetail('/propagation', mode);

  const absence = absenceOf(model, noSource);
  const data = absence === null ? model.data : null;
  const receipt = data?.receipt ?? null;
  const rows = data?.entries.length ?? 0;

  return (
    <aside
      className={styles.useCase}
      aria-label="Use case: what was not surfaced"
      data-testid="silence-use-case"
      data-payload={data === null ? 'absent' : 'present'}
    >
      <p className={styles.useCaseKicker}>{KICKER}</p>
      <h2 className={styles.sectionTitle}>Half two — what was not put in front of anybody</h2>

      <p className={styles.prose}>
        Every system that ranks things also decides what not to show. That second decision is
        normally invisible, and it is the one most likely to matter after an incident: nobody
        can tell afterwards whether a warning was absent because there was nothing to find, or
        because nothing was looked at.
      </p>

      {data === null ? (
        <p className={styles.prose} data-testid="silence-use-case-absent">
          There are no numbers in this walkthrough, because the read this screen depends on has
          not produced a payload. {absence ?? 'The panel below says which nothing that is.'} No
          figure has been supplied from anywhere else to fill the gap.
        </p>
      ) : (
        <ol className={styles.useCaseSteps} data-testid="silence-use-case-steps">
          <li className={styles.useCaseStep}>
            {rows === 0 ? (
              <>
                The ledger of declined items on this permit holds{' '}
                <Mono data-testid="use-case-row-count">0</Mono> rows. Read that carefully: it says
                this run declined nothing, not that nothing was withheld from you. The second
                claim is one this screen will not make, and the receipt below is what makes the
                first one checkable instead of asserted.
              </>
            ) : (
              <>
                The ledger holds <Mono data-testid="use-case-row-count">{rows}</Mono> row
                {rows === 1 ? '' : 's'} — every precursor this run looked at and decided not to
                surface. Each is listed below in full, with the score it was given, the threshold
                it was measured against, the calibration artefact behind that threshold, and the
                policy version in force. A count on its own would be the artefact that lets an
                organisation know the number without ever reading them.
              </>
            )}
          </li>

          {receipt === null ? (
            <li className={styles.useCaseStep} data-testid="use-case-no-receipt">
              No receipt was issued for this run, so nothing here certifies exhaustion of
              anything at all. That is a weaker position than a receipt with a bound, and the
              screen shows it as the weaker position rather than leaving the space blank.
            </li>
          ) : (
            <li className={styles.useCaseStep} data-testid="use-case-receipt">
              A receipt was issued. It says the search ranked{' '}
              <Mono data-testid="use-case-n">{receipt.n}</Mono> candidates, kept the first{' '}
              <Mono data-testid="use-case-s">{receipt.s}</Mono>, and measured every one of them
              against a threshold of <Mono data-testid="use-case-theta">{receipt.theta}</Mono>.
              Because the ranking is sorted by score, showing the two items either side of that
              cut-off is enough to establish that nothing above the threshold was quietly
              dropped — without revealing a single thing that was not shown.
            </li>
          )}

          <li className={styles.useCaseStep}>
            The receipt also names the universe it drew from: the version of the archive it
            searched, the index generation it ran under, and the observed query plan, each as a
            fingerprint that travels with the claim. An exhibit cannot be produced without them.
          </li>

          <li className={styles.useCaseStep}>
            What you would learn here: whether the silence was earned, or whether nobody can
            tell. Those are different answers and this screen refuses to render them the same
            way.
          </li>
        </ol>
      )}

      {receipt === null ? null : (
        <div className={styles.useCaseBound} data-testid="use-case-bound">
          <p className={styles.useCaseKicker}>
            the limit of the claim, in the receipt&apos;s own words
          </p>
          <pre className={styles.verbatim} data-testid="use-case-bound-statement">
            {receipt.bound.statement}
          </pre>
          <p className={styles.prose} data-testid="use-case-bound-gloss">
            {PER_BOUND_GLOSS}
          </p>
        </div>
      )}

      <p className={styles.prose}>
        The other half of this case is the same discipline pointed outward:{' '}
        <a className={styles.useCaseLink} href={propagationHref} data-testid="silence-use-case-link">
          which sibling sites took the control change and which did not
        </a>
        , and every conflict still open.
      </p>
    </aside>
  );
}
