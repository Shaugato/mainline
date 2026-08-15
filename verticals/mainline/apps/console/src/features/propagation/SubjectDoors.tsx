// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE DOORS OUT OF A NAMED ABSENCE — one click, no UUID typed.
 *
 * This surface renders ONE lesson and does not choose one for you. That rule is correct and
 * this component does not touch it. What it fixes is the dead end underneath it: a reader
 * who arrives at `#/propagation` with nothing named was told, accurately, that an explicit
 * identifier would work — and was then left to produce a UUID from somewhere.
 *
 * So when the kernel's subject index answered and named subjects for OTHER surfaces, each of
 * those becomes a live, addressed link. Nothing is invented: every href is built by
 * `src/app/subjects.ts` out of `GET /v1/demo/subjects`' own answer, and a slot the index left
 * null produces NO link — `subjectParamsFor` returns an empty list and nothing is rendered
 * for it.
 *
 * ── WHY THIS SURFACE'S OWN DOOR IS NOT IN THE LIST ───────────────────────────────
 *
 * The lesson is the subject this screen needs, and if the index had named one this panel
 * would not be rendering — `PropagationSurfaceRoot` would have addressed itself. A
 * `#/propagation?lesson=…` door here could never be live, and a link that can never be live
 * reads as a subject that exists and cannot be reached.
 *
 * ── THE STAGED LABEL TRAVELS WITH THE LINK ───────────────────────────────────────
 *
 * This surface's own payload is STAGED — `_staged_uuid` / `_staged_digest` derivations, and
 * the envelope flags them. `docs/leads/demo-story-plan.md` §4 rules that it may be linked
 * under a STAGED label and may not be narrated. Nothing here narrates it, and no door out of
 * this screen presents staged data as measured.
 */

import { type ReactNode } from 'react';

import { useDetailMode } from '../../app/detail-mode';
import { subjectHref, subjectParamsFor } from '../../app/subjects';
import type { SubjectIndex } from '../../data/demo-subjects';
import { Mono } from '../../design/primitives';

import styles from './propagation.module.css';

/**
 * Where a reader can go from here, and what they will find when they arrive.
 *
 * `id` is the surface's registry id and `path` its route — URL grammar, not an identifier.
 * No row is named here; every identifier arrives from the wire.
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
    id: 'silence',
    path: '/silence',
    label: 'what the recall did not surface, for that same permit',
    what: 'every candidate the retrieval declined to show, with the threshold that declined it.',
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
];

export function SubjectDoors({ index }: { readonly index: SubjectIndex }): ReactNode {
  const mode = useDetailMode();
  const live = DOORS.map((door) => ({
    door,
    pairs: subjectParamsFor(door.id, index),
  })).filter((entry) => entry.pairs.length > 0);

  if (live.length === 0) return null;

  return (
    <aside className={styles.useCase} data-testid="propagation-subject-doors">
      <span className={styles.useCaseKicker}>what this deployment did name</span>
      <p className={styles.prose}>
        No lesson was named, so there is nothing for this screen to read. The same answer from{' '}
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
