// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * USE CASE 2, HALF ONE — where a control change travelled, and where it stopped.
 *
 * Ruling R9 of `docs/leads/two-audience-ux-plan.md` selects two cases the platform can
 * demonstrate live against a real database, and this is the second one: *the system tells
 * you what it did NOT tell you*. It has two halves and this is the fleet half. The other
 * half is on the silence surface, and each links to the other, because "which sites took
 * it" and "what was never put in front of anybody" are the same argument seen from two
 * ends.
 *
 * ── WHAT THIS PANEL IS AND IS NOT ────────────────────────────────────────────────
 *
 * It is a plain-language walkthrough of the payload the screen has ALREADY read, and every
 * number in it is counted out of that payload at render time. It holds no fixture, no
 * example, no illustrative figure and no second read: if the exchange has not landed, the
 * panel says which nothing it is and prints no numbers at all. There is nothing here a
 * reader could mistake for a mock-up of what the product would do on data it does not
 * have.
 *
 * It is also not a replacement for anything. Every precise section of this screen — the
 * lesson panel, the census, each site row with its SLA clock and its named declination,
 * the three-way conflict digests, the inheritance panel — is still below it, unedited and
 * in the same order. This panel introduces; it never summarises a value it sits above,
 * because a summary of a digest is a worse digest.
 *
 * ── THE STAGED BADGE IS PART OF THE ARGUMENT, NOT AN APOLOGY ─────────────────────
 *
 * `demo-api/src/mainline_demo_api/reads.py::read_propagation` returns `staged: true` for
 * this whole resource, and says why in its own note: `mainline.lesson`,
 * `mainline.propagation` and `mainline.merge_conflict` are produced by no migration in
 * this repository. So the rows below came from a fixture the API composed, not from the
 * cluster — and the badge saying so is load-bearing evidence of the discipline this case
 * is about. It stays visible in PLAIN, it is not collapsible, and this panel repeats the
 * fact in one plain sentence rather than letting a reader meet it only as a badge.
 *
 * ── LAZY ─────────────────────────────────────────────────────────────────────────
 *
 * `PropagationScreen` reaches this module through `React.lazy`, so the prose is its own
 * chunk and is fetched after the surface has painted. R10 is a ceiling this wave does not
 * raise: `budgets.json` is untouched and the evidentiary shell carries none of this.
 */

import { type ReactNode } from 'react';

import { hrefWithDetail, useDetailMode } from '../../app/detail-mode';
import { Mono } from '../../design/primitives';
import { glossFor } from '../../design/glossary';

import type { FleetView } from './model';
import styles from './propagation.module.css';

export interface UseCaseTwoProps {
  /**
   * The built view, or `null` when the read has not produced one. `null` is not an error
   * state — it covers loading, failure, refusal and no-source alike, and the panel says
   * which of those the screen is reporting by quoting `absence` rather than guessing.
   */
  readonly view: FleetView | null;
  /** What the screen is showing instead of a view, in the screen's own words. */
  readonly absence: string | null;
  /** `envelope.staged` — true when no cluster produced these rows. */
  readonly staged: boolean;
}

/** The kicker, so the two halves of the case are recognisable as one case. */
const KICKER = 'use case 2 — what the system did not tell you';

export function UseCaseTwo({ view, absence, staged }: UseCaseTwoProps): ReactNode {
  const mode = useDetailMode();
  const silenceHref = hrefWithDetail('/silence', mode);

  const openConflicts =
    view === null ? 0 : view.attachedConflicts.length + view.orphanConflicts.length;
  const answered =
    view === null
      ? 0
      : view.rows.filter((row) => row.state !== 'proposed').length;

  return (
    <aside
      className={styles.useCase}
      aria-label="Use case: where the lesson travelled"
      data-testid="propagation-use-case"
      data-view={view === null ? 'absent' : 'present'}
    >
      <p className={styles.useCaseKicker}>{KICKER}</p>
      <h2 className={styles.sectionTitle}>Half one — where the change travelled, and where it stopped</h2>

      <p className={styles.prose}>
        When something goes wrong at one site, the useful question is not only what was fixed
        there. It is whether the same fix reached every other site that had the same problem.
        Most systems cannot answer that, because nothing ever wrote down which sites were asked.
      </p>

      {staged ? (
        <p className={styles.prose} data-testid="propagation-use-case-staged">
          Before the numbers: the rows on this screen came from a fixture, not from the live
          database. The tables they would come from are not created by any migration in this
          repository yet, so the demo API composes them and marks the whole payload{' '}
          <Mono>staged</Mono>. {glossFor('staged')}
        </p>
      ) : null}

      {view === null ? (
        <p className={styles.prose} data-testid="propagation-use-case-absent">
          There are no numbers in this walkthrough, because the read this screen depends on has
          not produced a payload. {absence ?? 'The panel below says which nothing that is.'} No
          figure has been supplied from anywhere else to fill the gap.
        </p>
      ) : (
        <ol className={styles.useCaseSteps} data-testid="propagation-use-case-steps">
          <li className={styles.useCaseStep}>
            One lesson was proposed to <Mono data-testid="use-case-site-count">{view.rows.length}</Mono>{' '}
            site{view.rows.length === 1 ? '' : 's'}, and{' '}
            <Mono data-testid="use-case-answered-count">{answered}</Mono> of them have answered.
            Each answer is one word the record chose — the census under this panel lists every
            word in the vocabulary, including the ones no site used, so a state that never
            happened is visible as a zero rather than missing.
          </li>
          <li className={styles.useCaseStep}>
            A site that said no is on the list with the same weight as a site that said yes, and
            it has to say WHICH no: the record names the kind of declination and the column that
            makes it checkable. A refusal nobody can check later is not on offer here.
          </li>
          <li className={styles.useCaseStep}>
            {openConflicts === 0 ? (
              <>
                No conflict is open against this lesson. That is a statement about these rows,
                not a promise about the fleet.
              </>
            ) : (
              <>
                <Mono data-testid="use-case-conflict-count">{openConflicts}</Mono> conflict
                {openConflicts === 1 ? ' is' : 's are'} still open. Each is shown with the three
                versions that disagree — the common ancestor, the site&apos;s own, and the one
                arriving — so a conflict is something a person can resolve rather than a warning
                somebody dismisses.
              </>
            )}
          </li>
          <li className={styles.useCaseStep}>
            What you would learn here: whether a safety change actually reached the places it was
            meant to reach, or stopped at the first site with a reason not to take it — and
            whether that reason was written down.
          </li>
        </ol>
      )}

      <p className={styles.prose}>
        The other half of this case is the same discipline pointed inward:{' '}
        <a className={styles.useCaseLink} href={silenceHref} data-testid="propagation-use-case-link">
          what the search declined to put in front of anybody
        </a>
        , with the arithmetic for each of those decisions.
      </p>
    </aside>
  );
}
