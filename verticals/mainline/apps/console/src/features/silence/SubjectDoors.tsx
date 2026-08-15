// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE DOORS OUT OF A NAMED ABSENCE — one click, no UUID typed.
 *
 * This surface renders ONE permit and does not choose one for you. That rule is correct and
 * this component does not touch it. What it fixes is the dead end underneath it: a reader
 * who arrives at `#/silence` with nothing named was told, accurately, that an explicit
 * identifier would work — and was then left to produce a UUID from somewhere. A judge with
 * three minutes does not have one.
 *
 * So when the kernel's subject index answered and named subjects for OTHER surfaces, each of
 * those becomes a live, addressed link. Nothing is invented: every href is built by
 * `src/app/subjects.ts` out of `GET /v1/demo/subjects`' own answer, and a slot the index
 * left null produces NO link at all — `subjectParamsFor` returns an empty list and this
 * component renders nothing for it.
 *
 * ── WHY THIS SURFACE'S OWN DOOR IS NOT IN THE LIST ───────────────────────────────
 *
 * The permit is the subject this screen needs, and if the index had named one this panel
 * would not be rendering — `SilenceSurfaceRoot` would have addressed itself and gone
 * straight to the ledger. A `#/silence?permit=…` door here would therefore be a link that
 * can never be live, which is worse than no link: it reads as a subject that exists and
 * cannot be reached. The absence of the permit is stated in words instead, by the panel
 * above, in the emitter's own sentence.
 *
 * ── AND WHY IT RENDERS NOTHING WHEN NOTHING WAS NAMED ────────────────────────────
 *
 * With the index unresolved, unavailable, or resolved-and-empty, every door is dead and the
 * honest rendering is no doors — the panel above already says which of those it is, with the
 * transport's own report verbatim. A "nothing here either" list is not information.
 */

import { type ReactNode } from 'react';

import { useDetailMode } from '../../app/detail-mode';
import { subjectHref, subjectParamsFor } from '../../app/subjects';
import type { SubjectIndex } from '../../data/demo-subjects';
import { Mono } from '../../design/primitives';

import styles from './silence.module.css';

/**
 * Where a reader can go from here, and what they will find when they arrive.
 *
 * `id` is the surface's registry id and `path` its route — URL grammar, not an identifier,
 * exactly as `src/app/subjects.ts` says of the parameter names it pins. No row is named
 * here; the identifiers arrive from the wire.
 */
const DOORS: readonly {
  readonly id: string;
  readonly path: string;
  readonly label: string;
  readonly what: string;
}[] = [
  {
    id: 'gate',
    path: '/gate',
    label: 'the gate, on the permit this deployment seeded',
    what: 'the merge this database refuses, and the one unanswered obligation that causes it.',
  },
  {
    id: 'custody',
    path: '/custody',
    label: 'the custody log, on the site this deployment seeded',
    what: 'every claim about the log re-computed in your own browser, agreements and disagreements alike.',
  },
  {
    id: 'diff',
    path: '/diff',
    label: 'the clause version the blame reaches',
    what: 'the text of the rule a 2019 incident named, at the exact commit the permit relies on.',
  },
  {
    id: 'propagation',
    path: '/propagation',
    label: 'the lesson, across the fleet',
    what: 'where one lesson travelled and what is still open against it. Its payload is badged STAGED, and the badge is on the screen.',
  },
];

export function SubjectDoors({ index }: { readonly index: SubjectIndex }): ReactNode {
  const mode = useDetailMode();
  const live = DOORS.map((door) => ({
    door,
    pairs: subjectParamsFor(door.id, index),
  })).filter((entry) => entry.pairs.length > 0);

  if (live.length === 0) return null;

  return (
    <aside className={styles.useCase} data-testid="silence-subject-doors">
      <span className={styles.useCaseKicker}>what this deployment did name</span>
      <p className={styles.prose}>
        No permit was named, so there is nothing for this screen to read. The same answer from{' '}
        <Mono>GET /v1/demo/subjects</Mono> did name other subjects, and each link below is
        addressed to one of them — a screen that will render, with no identifier to type.
      </p>
      <ul className={styles.useCaseSteps}>
        {live.map(({ door, pairs }) => (
          <li className={styles.useCaseStep} key={door.id} data-door={door.id}>
            <a className={styles.useCaseLink} href={subjectHref(door.id, door.path, index, mode)}>
              {door.label}
            </a>{' '}
            — {door.what}
            <br />
            {pairs.map(([name, value]) => (
              <Mono key={name}>
                {name}={value}{' '}
              </Mono>
            ))}
          </li>
        ))}
      </ul>
      <p className={styles.note}>
        Every identifier above came off the wire in that one read. None of them is written into
        this console, and a slot the kernel left null produced no link at all.
      </p>
    </aside>
  );
}
