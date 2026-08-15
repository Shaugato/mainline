// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE OVERVIEW — what this refuses, and two cases a stranger can follow to the end.
 *
 * This is the screen the console opens on (order 5, above the gate), and it exists because
 * of one finding: a judge who loads the bare URL used to arrive at a specialist screen and
 * meet RFC numbers before anybody had told them what the product does. The fix is an
 * ON-RAMP, never a dumbing-down — no sentence anywhere else in this console was made
 * vaguer to let this screen exist, and every precise sentence is still exactly where it
 * was.
 *
 * ── WHAT THIS SCREEN IS ALLOWED TO CLAIM ─────────────────────────────────────────
 *
 * Every line below is either (a) a description of what a reader will SEE on a screen this
 * console ships, or (b) a statement about where a rule lives, which is checkable in the
 * schema. There is no adjective about the platform and no verdict about a record: D5 puts
 * this surface one hop downstream of every claim, exactly like the others, and this one
 * holds no payload at all. Where a sentence predicts a screen, a reader who clicks and
 * sees something else has caught THIS file, which is the property that makes an overview
 * worth writing.
 *
 * ── ADDRESSING: ASKED, NEVER TYPED ───────────────────────────────────────────────
 *
 * Every door on this screen carries a subject resolved through `src/data/demo-subjects.ts`
 * — one `GET /v1/demo/subjects`, shared with the five surfaces it links to, memoised
 * against the transport. **No identifier appears in this file.** Pasting one here would
 * rebuild the defect this wave is undoing (`docs/leads/screens-work-plan.md` §2.2: a site
 * code that had leaked out of a test vector into a shipped default, and answered 404 on
 * the live URL for however long nobody clicked). When the kernel names nothing, the door
 * renders as a named absence carrying the resolver's own words, and there is no link.
 *
 * ── WHERE THE BYTES COME FROM ────────────────────────────────────────────────────
 *
 * `useGateTransport()`. The composition root (`src/app/composition.tsx`) constructs ONE
 * transport and provides it through six feature sockets; this surface constructs nothing
 * and adds no socket, because adding one means editing the composition root and this
 * screen is not worth a seventh provider. The gate socket rather than another is not
 * arbitrary: the gate is the screen case 1 sends a reader to, and
 * `src/features/gate/transport-context.ts` imports React and a type and nothing else, so
 * borrowing it costs this lazy chunk no weight.
 */

import { type ReactNode } from 'react';

import {
  DEMO_SUBJECTS_ROUTE,
  useDemoSubjects,
  type DemoSubjects,
  type SubjectIndex,
} from '../../data/demo-subjects';
import { hrefFor } from '../../app/router';
import { Mono, RegisterFrame } from '../../design/primitives';
import { useGateTransport } from '../gate/transport-context';

import styles from './overview.module.css';
import { UseCasePanel, type Destination } from './UseCasePanel';

/**
 * The query parameters the destination surfaces read, named once.
 *
 * They are the same strings `GateSurfaceRoot.PERMIT_PARAM`, `CustodyRoot.SITE_PARAM` and
 * `SilenceSurfaceRoot.PERMIT_PARAM` export. They are re-declared rather than imported
 * because those modules also export their surface's root component, and a static import
 * would pull three feature screens into this lazy chunk to read three short strings.
 * `tests/unit/app/onramp.test.tsx` imports the real constants and asserts these equal
 * them, so the duplication cannot drift without a red test.
 */
const PERMIT_PARAM = 'permit';
const SITE_PARAM = 'site';

/** `#/gate?permit=…`. Built, never written down: the value comes off the wire. */
function addressed(path: string, param: string, subject: string): string {
  return `${hrefFor(path)}?${param}=${encodeURIComponent(subject)}`;
}

/**
 * Why a door has no link, in the terms the read itself reported.
 *
 * Four branches for four different facts, and they are NOT collapsed into "unavailable":
 * "nobody gave this console a source", "the read has not landed", "the deployment did not
 * answer" and "the deployment answered and holds no such row" send a reader to four
 * different places, and only the last one is a statement about the database.
 */
function absenceFor(index: SubjectIndex, noun: string, member: string, subjectKey: string): {
  readonly absence: string;
  readonly detail: string | null;
} {
  if (index.status === 'no_source') {
    return {
      absence:
        `No transport has been composed for this console, so ${DEMO_SUBJECTS_ROUTE} — the read that ` +
        `would name which ${noun} this deployment seeded — has not been performed. This console does ` +
        'not carry one written into its own source.',
      detail: null,
    };
  }

  if (index.status === 'resolving') {
    return {
      absence: `Asking ${DEMO_SUBJECTS_ROUTE} which ${noun} this deployment seeded. The link appears when it answers.`,
      detail: null,
    };
  }

  if (index.status === 'unavailable') {
    return {
      absence:
        `This deployment did not answer ${DEMO_SUBJECTS_ROUTE}. The transport classified the failure ` +
        `as “${index.failure}” and its report is below, verbatim. No link is offered, because no ` +
        `${noun} was named and this console will not substitute one.`,
      detail: index.detail,
    };
  }

  const said = index.subjects.absent.find((entry) => entry.subject === subjectKey);
  const quoted =
    said === undefined
      ? ''
      : ` The emitter said why, and this is its sentence rather than ours: “${said.reason}” It looked in ${said.relation}.`;

  return {
    absence:
      `The kernel answered ${DEMO_SUBJECTS_ROUTE} and named no ${noun}: the “${member}” member came ` +
      `back null. That is a statement about what this database holds, not a defect in this screen.${quoted}`,
    detail: null,
  };
}

interface DoorSpec {
  readonly label: string;
  readonly path: string;
  readonly param: string;
  readonly noun: string;
  readonly member: string;
  readonly subjectKey: string;
  readonly pick: (subjects: DemoSubjects) => string | null;
}

function doorFor(index: SubjectIndex, spec: DoorSpec): Destination {
  const subject = index.status === 'resolved' ? spec.pick(index.subjects) : null;
  if (subject === null || subject === '') {
    const { absence, detail } = absenceFor(index, spec.noun, spec.member, spec.subjectKey);
    return { label: spec.label, href: null, subject: null, absence, detail };
  }
  return {
    label: spec.label,
    href: addressed(spec.path, spec.param, subject),
    subject,
    absence: null,
    detail: null,
  };
}

const GATE_DOOR: DoorSpec = {
  label: 'Open the Gate screen for this permit',
  path: '/gate',
  param: PERMIT_PARAM,
  noun: 'permit',
  member: 'permit_id',
  subjectKey: 'permit',
  pick: (subjects) => subjects.permitId,
};

const CUSTODY_DOOR: DoorSpec = {
  label: 'Open the Custody screen for this site',
  path: '/custody',
  param: SITE_PARAM,
  noun: 'site',
  member: 'site_code',
  subjectKey: 'site',
  pick: (subjects) => subjects.siteCode,
};

const SILENCE_DOOR: DoorSpec = {
  label: 'Open the Silence screen for this permit',
  path: '/silence',
  param: PERMIT_PARAM,
  noun: 'permit',
  member: 'permit_id',
  subjectKey: 'permit',
  pick: (subjects) => subjects.permitId,
};

const DRIVER_DOOR: DoorSpec = {
  label: 'Press the four beats yourself, on the Gate screen',
  path: '/gate',
  param: PERMIT_PARAM,
  noun: 'permit',
  member: 'permit_id',
  subjectKey: 'permit',
  pick: (subjects) => subjects.permitId,
};

export function OverviewScreen(): ReactNode {
  const transport = useGateTransport();
  const index = useDemoSubjects(transport);

  return (
    <RegisterFrame register="evidence" as="section" label="Overview" data-testid="overview-surface">
      <div className={styles.surface}>
        <header className={styles.header}>
          <p className={styles.kicker}>overview · what this refuses, and why</p>
          <h1 className={styles.title}>The answer this system is built to give is “no”.</h1>

          <p className={styles.standfirst}>
            A permit is a request to make a change that safety checks stand in front of. MAINLINE puts
            the last word about that request inside the database: while a check that guards the change
            is still open, the merge is refused there, by a rule with a name, and the name comes back
            with the refusal. That is worth something for one reason — a rule that lives in application
            code only binds writers who go through that application, and a rule recorded after the
            fact is a report rather than a control. Everything below is a screen you can open, holding
            a subject this deployment actually seeded.
          </p>

          <p className={styles.note}>
            Nothing on this screen is a claim about a record. It holds no payload, decides no verdict
            and quotes no database; it describes screens, and each description is a prediction you can
            check by clicking. The identifiers behind the links were read from{' '}
            <Mono>{DEMO_SUBJECTS_ROUTE}</Mono> just now — none of them is written into this console.
          </p>
        </header>

        <UseCasePanel
          ordinal={1}
          testId="usecase-refusal"
          title="A merge is refused by the database, and the refusal names itself"
          situation={[
            'One check on this permit is still open. Something asks to merge the change anyway — which is what happens when a person is in a hurry, or when a script writes to the table without ever meeting the application that was supposed to stop it.',
          ]}
          whatYouWillSee={[
            'The permit, and four controls that drive the demonstration. Press the first one and the console asks the database to merge; the answer comes back as a refusal carrying a SQLSTATE and the name of the rule that refused it, shown exactly as the database reported it rather than as this console’s summary of it.',
            'Below that, the counters this permit carries, each drawn underneath the single rule that reads it and nothing else. Every one of them was written onto the row by a trigger from the tables that own the fact — never by whoever asked for the merge, and never by this console.',
            'Each counter says which of three things it is: blocking, zero with the screen carrying what was examined to reach that zero, or zero with nothing here to establish what was examined. A zero nobody counted is not the same fact as a zero somebody counted, and the screen refuses to draw them the same way.',
          ]}
          whyItMatters={[
            'The rule is a constraint on the table, not a check in a service. It therefore applies to every writer that reaches that row, including the ones nobody thought about when the service was written.',
            'And the name is the exhibit: “the merge was refused by gate_closed_when_issued” is a sentence somebody can look up, argue with and act on. “The system reported an error” is not.',
          ]}
          destinations={[doorFor(index, GATE_DOOR)]}
        />

        <UseCasePanel
          ordinal={2}
          testId="usecase-forged-counter"
          title="Forging the number does not help, and you do not have to take our word for it"
          situation={[
            'The counter the rule reads is not typed in by whoever asks for the merge — a trigger writes it onto the row from the tables that own the facts. So the obvious attack is to go around that: set the counter to zero directly, and the rule now reads a zero and is satisfied.',
          ]}
          whatYouWillSee={[
            'On the Gate screen, the second beat does exactly that — it forces the counter to zero out of band and then asks for the merge. The merge is refused anyway, by a different code and a different name, because the function behind the merge re-derives the open count for itself instead of trusting the column.',
            'The third beat signs a disposition and merges, and is admitted. That matters just as much: a gate that refuses everything is broken, not safe.',
            'On the Custody screen, the record of all of this is a log that can only be appended to, and this browser re-does its arithmetic in front of you: each check reports its own verdict beside the numbers it was worked out from, including the ones this log cannot make attemptable at all.',
          ]}
          whyItMatters={[
            'Two independent refusals, one of which does not believe the other’s bookkeeping. Disarming the projection is not enough, and neither is being trusted about it.',
            'The log is checkable by somebody who does not trust us and cannot reach our database: the same arithmetic runs offline from the same bytes, with pipx run trappoint-verify.',
          ]}
          destinations={[doorFor(index, CUSTODY_DOOR), doorFor(index, DRIVER_DOOR)]}
        />

        <UseCasePanel
          ordinal={3}
          testId="usecase-silence"
          title="What was not put in front of anybody, and the arithmetic for leaving it out"
          situation={[
            'Every system that ranks things also decides what not to show. That decision is normally invisible, and it is the one most likely to matter after an incident: nobody can tell whether a warning was absent because there was nothing, or because nothing was looked at.',
          ]}
          whatYouWillSee={[
            'A STAGED badge, first, saying that no recall run produced these rows and that the payload was hand-authored for the demonstration. Read that before the rest: this is the one case of the three whose numbers were not produced by a run, and the screen says so itself rather than letting you find out later.',
            'Then the precursors the run declined to surface, each with the score it was given, the threshold it was measured against, the calibration artefact behind that threshold, and the policy version in force.',
            'And the conservation identity: every candidate went to exactly one of four places, with the sum recomputed in this browser from the five counts so that the identity can be checked rather than believed.',
          ]}
          whyItMatters={[
            'A silence that can be audited is a different object from a silence that cannot. The answer to “your system knew about this and did not show me” is arithmetic, or it is an adverse inference.',
            'And the badge is the same discipline as the two cases above, pointed at ourselves: a demonstration row is never allowed to pass as a measured one.',
          ]}
          destinations={[doorFor(index, SILENCE_DOOR)]}
        />
      </div>
    </RegisterFrame>
  );
}
