// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * THE DEMO'S FRONT DOOR — four controls over `POST /v1/demo/gate-run`.
 *
 * The product's whole claim is three beats, and this is where a stranger presses them:
 *
 *   MERGE                            → REFUSED, `23514` `gate_closed_when_issued`
 *   FORGE THE COUNTER AND MERGE      → REFUSED ANYWAY, `P0001` `mainline.fn_permit_merge_gate`
 *   SIGN A DISPOSITION AND MERGE     → ADMITTED, `00000`
 *
 * The middle one is the product. The projected counter is forced to zero out of band —
 * exactly what a disarmed projector or a careless `UPDATE` leaves behind — so the CHECK
 * constraint is now satisfied and would admit the merge. The merge is refused anyway,
 * because `mainline.fn_permit_merge_gate` RE-DERIVES the open count instead of trusting
 * the column. The third one matters too: a gate that always refuses is broken, not safe.
 *
 * ── RUN ALL IS THE PRIMARY CONTROL (`docs/leads/demo-story-plan.md` §5) ──────────
 *
 * It is first in the list and first in the tab order, and the three named controls keep
 * their argument order underneath it. The lead's reading is that RUN ALL tells the whole
 * argument — refuse, refuse under a forged counter, admit on a signature — in ONE
 * exchange, which is what the transaction discipline below already forces; the ordering
 * therefore embraces a constraint instead of apologising for it. The other three are not
 * demoted and not hidden: a reader who wants one beat at a time still has one press for
 * each.
 *
 * ── THE REVEAL IS PRESENTATION, AND SAYS SO (R11) ───────────────────────────────
 *
 * The four beats arrive TOGETHER. They cannot arrive any other way — see the transaction
 * discipline below — so showing them one after another is a READING AID over a completed
 * exchange, never a re-enactment of it, and the panel states that in one sentence beside
 * the paragraph that states the transaction discipline.
 *
 * Two consequences, both structural rather than remembered:
 *
 *   • **The staging is CSS.** `src/features/gate/beats.ts` computes a step INDEX per
 *     beat; `demo-driver.module.css` turns it into a delay expressed as
 *     `--tp-duration-evidence`, under the EVIDENCE ceiling, and cancels itself entirely
 *     under `prefers-reduced-motion`. No timer advances any value in this module.
 *   • **Every duration on screen is the payload's.** `elapsedText` reads
 *     `beat.elapsed_ms` and takes a beat rather than a number, so no call site can hand
 *     it a reveal delay. Measured on the live URL: the four beats reported `0.011`,
 *     `527.051`, `472.401` and `392.347` ms — four different numbers, which is exactly
 *     what a uniform reveal delay printed in their place would have destroyed.
 *
 * ── WHAT THIS MODULE PUBLISHES ──────────────────────────────────────────────────
 *
 * Two things, both only after an exchange has RETURNED, and both the payload's own
 * values verbatim: the subject the run drove (`src/features/gate/addressing.ts`, so the
 * gate surface can open on the permit a run named), and the whole completed payload
 * (`src/features/gate/last-run.ts`, Contract B — the screen below this panel subscribes
 * and does its own adapting). This module is the producer for both and consumes neither.
 *
 * ── WHY FOUR CONTROLS AND ONE ENDPOINT ───────────────────────────────────────────
 *
 * `docs/deploy/gate-run-contract.md` §2 pins the transaction discipline: the four beats
 * run inside ONE `SERIALIZABLE` transaction, each write beat fenced by its own
 * `SAVEPOINT`, and the whole transaction is rolled back — which is why fifty judges can
 * press these buttons at once and the fifth sees what the first did. A browser cannot
 * hold a savepoint, so the beats CANNOT be driven one HTTP call at a time. Each control
 * therefore performs the same exchange and shows the beat it names; RUN ALL shows all
 * four with the run's own witnesses. The panel says so on screen rather than implying
 * that each button is its own transaction.
 *
 * The body is `{}` for all four controls, deliberately. The request key is what names a
 * frame inside an EvidenceBundle (`src/data/resources.ts`), so an identical body means
 * ONE captured frame serves all four controls in REPLAY. A `run_id` in the body would
 * mint a new key per press and make the replay path uncapturable.
 *
 * ── D18, ENFORCED BY WHAT THIS FILE DOES NOT CONTAIN ─────────────────────────────
 *
 * Every SQLSTATE and every constraint name below is rendered through
 * `src/design/primitives/Sqlstate.tsx` and `ConstraintName.tsx`, verbatim, from the
 * payload. There is no string in this module that describes what the database said, and
 * no branch that chooses a sentence based on a code. `constraint_source: 'parsed'` is
 * rendered AS a weakened diagnosis, because on CockroachDB v26.2.5 a PL/pgSQL `RAISE`
 * carries no `constraint_name` and the exhibit was recovered from the message — a run
 * whose exhibits were inferred must never look like a run whose exhibits were reported.
 *
 * ── EVIDENCE REGISTER ────────────────────────────────────────────────────────────
 *
 * `src/features/gate` is EVIDENCE (`docs/leads/ui.md` §1.1): mono for anything the
 * database emitted, no easing over 160 ms, nothing that moves that a screenshot could not
 * reproduce, no `motion`, no `@react-three/*`. Styles are in `demo-driver.module.css`.
 *
 * R12 adds the reveal's own share of that law, and each clause is checked by
 * `tests/unit/gate/demo-driver.test.tsx` rather than remembered: each step is one
 * `--tp-duration-evidence`, `prefers-reduced-motion` renders all four beats at once, and
 * the RESTING state after the sequence is the complete panel — so a screenshot taken at
 * any moment is a truthful screenshot rather than a frame of something in flight.
 */

import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from 'react';

import { RESOURCES } from '../../data/resources';
import { useResource } from '../../data/useResource';
import { ConstraintName, Disclosure, Mono, Sqlstate } from '../../design/primitives';

import { publishGateRunSubject } from './addressing';
import {
  clauseIdFromRun,
  elapsedText,
  revealPlan,
  type BeatCue,
  type GateRunPermitRow,
  type GateRunPersistence,
  type GateRunData,
  type Reveal,
} from './beats';
import styles from './demo-driver.module.css';
import { publishLastGateRun } from './last-run';
import { useGateTransport } from './transport-context';

/**
 * The payload's shape, re-exported from where it now lives.
 *
 * `src/features/gate/beats.ts` owns these declarations so that a subscriber to Contract B
 * can name the payload without importing this lazily-loaded component chunk. They are
 * re-exported here because several suites and another worker's module already import them
 * from this path, and moving a type is not a reason to make anybody else edit a file.
 */
export type {
  BeatCue,
  GateRunBeat,
  GateRunData,
  GateRunFingerprint,
  GateRunPermitRow,
  GateRunPersistence,
  GateRunSelfEvidence,
  GateRunSubject,
  GateRunTransaction,
  Reveal,
} from './beats';

// ── The resource, and the files that must name it ──────────────────────────

/**
 * The resource key the console would address. It is checked against `RESOURCES` at
 * render time rather than assumed, because a `resolveRequest` on an undeclared key throws
 * a stack trace where a reader deserves a sentence.
 */
export const DEMO_GATE_RUN = 'demo_gate_run';

/**
 * WHAT WOULD STILL BE MISSING IF THIS PANEL EVER RENDERED — AND WHAT WOULD NOT BE.
 *
 * `DeclarationGapPanel` is UNREACHABLE in this build. `demo_gate_run` is declared in
 * `src/data/resources.ts`, so `RESOURCES.has(DEMO_GATE_RUN)` is true and the controls
 * render instead; `tests/unit/data/resources.test.ts` pins that, and both
 * `tests/unit/app/composition.test.tsx` and `tests/unit/gate/demo-driver.test.tsx` render
 * the driver against the REAL registry and require the panel to be absent. The list is
 * nevertheless KEPT, and kept accurate, because a build that ever strips the declaration
 * must still tell its reader what to restore rather than fail silently — an absence a
 * reader can act on beats an absence they have to go and diagnose.
 *
 * Every repository path any line below names is READ OFF DISK by
 * `tests/unit/gate/demo-driver.test.tsx`. That is the whole remedy for how this list went
 * stale: prose about another file is only as true as the last time somebody checked, so
 * the checking is now a test rather than a habit.
 *
 * ── THE CORRECTION, 2026-08-14 ───────────────────────────────────────────────────
 *
 * The third entry used to say of `app.py` that *"the route table declares the four kernel
 * POSTs and no demo route, so the endpoint 404s."* **THAT WAS FALSE**, and a founder read
 * it off a deployed screen. `app.py:229` carries
 * `Route("POST", "/v1/demo/gate-run", "demo_gate_run")`, `app.py:188-206` describes it as
 * the seventeenth route, `demo-api/tests/test_routes_gate_run.py` pins it, and the live
 * URL answers **503 `dsn_unset`** — a reachable route refusing for a NAMED reason, which
 * is not a 404 and must not be described as one.
 *
 * Prose that sends a reader to go and fix something already fixed is a defect of the same
 * family as prose that hides something broken: both make the screen a worse guide to the
 * system than reading the system would be.
 */
const DECLARATION_GAP: readonly string[] = [
  'verticals/mainline/apps/console/src/data/resources.ts — a declare() for this key: ' +
    "declare('demo_gate_run', 'POST', '/v1/demo/gate-run', <contract prefix>gate-run.schema.json, " +
    "'kernel', …). Without it the key is undeclared and resolveRequest() would throw rather " +
    'than build a request.',
  'verticals/mainline/apps/console/src/data/contracts.ts — gate-run.schema.json registered in ' +
    'CONTRACT_SOURCES as an explicit ?raw import, a verbatim copy of ' +
    'verticals/mainline/apps/demo-api/contracts/gate-run.schema.json. The transport validates ' +
    'every response against its contract before returning it, and a schema $id nobody registered ' +
    'raises rather than passes.',
  'verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py — ALREADY DONE, and this entry ' +
    'says so rather than sending anybody to repeat it. Route("POST", "/v1/demo/gate-run", ' +
    '"demo_gate_run") is on the route table and ' +
    'verticals/mainline/apps/demo-api/tests/test_routes_gate_run.py pins it. Its ' +
    'contract id is gate_run.GATE_RUN_SCHEMA_ID and NOT envelope.SCHEMA_IDS — deliberately, so ' +
    'that the branch which reports a missing write surface cannot itself raise KeyError while ' +
    'doing it. The deployed URL answers 503 dsn_unset: a reachable route refusing for a named ' +
    'reason, never a 404. What is outstanding there is operational, not a code edit — the SSM ' +
    'parameter /mainline/demo/cockroach_dsn is unset, so the kernel refuses by name until an ' +
    'operator sets it. That refusal is the honest answer and this console renders it as one.',
];

// ── The controls ───────────────────────────────────────────────────────────

interface Control {
  readonly id: string;
  readonly reveal: Reveal;
  readonly label: string;
  /** What this beat was WRITTEN against. Compared on screen against what came back. */
  readonly expectation: string;
  /**
   * The one control a stranger should press first. Exactly one entry carries it, and
   * `tests/unit/gate/demo-driver.test.tsx` asserts both that it is exactly one and that
   * it is the one that reveals every beat.
   */
  readonly primary?: true;
}

/**
 * RUN ALL leads; the three named controls keep the argument's order underneath it.
 *
 * The order of the last three is unchanged and is still the argument — refuse; refuse
 * under attack; admit. A demo that showed the admission first would be a demo about a
 * database that says yes.
 *
 * What changed is what comes BEFORE them (`docs/leads/demo-story-plan.md` §5): the whole
 * argument is one exchange, because the transaction discipline below makes it one, and
 * the control that performs that exchange should be the one a stranger reaches first.
 * The three named controls each perform the same exchange and show one beat of it, so
 * nothing is lost by putting them second — and a reader who wants one beat at a time is
 * one press away from it either way.
 */
const CONTROLS: readonly Control[] = Object.freeze([
  {
    id: 'all',
    reveal: 'all',
    label: 'RUN ALL',
    expectation: 'all four beats, one transaction, rolled back — with the evidence for both claims',
    primary: true,
  },
  {
    id: 'merge',
    reveal: 2,
    label: 'MERGE',
    expectation: 'expect REFUSED — 23514, gate_closed_when_issued, reported by the driver',
  },
  {
    id: 'forge',
    reveal: 3,
    label: 'FORGE THE COUNTER AND MERGE',
    expectation:
      'expect REFUSED ANYWAY — P0001, mainline.fn_permit_merge_gate. The counter is set to zero out of band first.',
  },
  {
    id: 'admit',
    reveal: 4,
    label: 'SIGN A DISPOSITION AND MERGE',
    expectation: 'expect ADMITTED — 00000, with a server-computed clearance digest',
  },
]);

// ── USE CASE 1, IN WORDS: "the obvious tamper does not work" ───────────────

/**
 * THE WALKTHROUGH.
 *
 * `docs/leads/two-audience-ux-plan.md` R9 selects two use cases this platform can
 * demonstrate live, against a real database, in front of a judge. This is the first of
 * them, and these paragraphs are the plain-language half of it: what is about to be
 * attempted, how to read what comes back, and why the MIDDLE beat is the product.
 *
 * ── WHY THIS IS PROSE AND NOT A NARRATION OF THE RESULT ──────────────────────────
 *
 * Every sentence here describes the DEMONSTRATION — what the four beats do, which is a
 * fact about `docs/deploy/gate-run-contract.md` and about the statements the beats send.
 * Not one of them describes what came back. That is R8, and it is the same discipline
 * this module already documents about itself: there is no branch anywhere below that
 * picks a sentence from a SQLSTATE, from a constraint name or from an outcome, and
 * `tests/unit/gate/demo-driver.test.tsx` reads the file to prove it. What happened is
 * shown by the beats themselves, in the database's own words, underneath.
 *
 * The paragraphs are data rather than JSX so the walkthrough can be asserted as a whole —
 * a count, and a check that no code literal leaked into it — rather than scraped out of a
 * render.
 */
interface WalkthroughStep {
  readonly id: string;
  readonly title: string;
  readonly body: string;
}

const WALKTHROUGH: readonly WalkthroughStep[] = Object.freeze([
  {
    id: 'attempt',
    title: 'What is about to be attempted',
    body:
      'The demonstration is built around one permit that still has an obligation against it — ' +
      'something that has to be answered before a permit is allowed to take effect. Beat 1 reads ' +
      'that subject and shows the counts the database holds. Beat 2 asks the database to merge ' +
      'the permit anyway, and what came back is printed below in the database\u2019s own words, ' +
      'with the name of the rule beside it.',
  },
  {
    id: 'tamper',
    title: 'The middle beat is the product',
    body:
      'The check the database runs is instant because it reads a running total kept in a column ' +
      'rather than counting the rows every time. Beat 3 forces that total to zero out of band — ' +
      'exactly what a disarmed projector or a careless UPDATE leaves behind — so the check is now ' +
      'satisfied and would admit the merge. It is refused anyway, because the function re-derives ' +
      'the count from the rows instead of trusting the column, and beat 3 below is where you read ' +
      'what the database actually did.',
  },
  {
    id: 'admit',
    title: 'The fourth beat matters too',
    body:
      'Beat 4 records one signature against the open obligation and asks again. A gate that always ' +
      'refuses is broken, not safe — so a demonstration that stopped after the refusals would be ' +
      'showing you a wall rather than a gate, and beat 4 below is where you check that the gate ' +
      'opens once the obligation has actually been answered.',
  },
  {
    id: 'nothing-kept',
    title: 'Nothing you press is kept',
    body:
      'All four beats run inside one transaction that is rolled back, so pressing these controls ' +
      'writes nothing to the database and fifty people can press them at once. The panel does not ' +
      'ask you to take that on faith: the run reports the row counts and the permit row it read ' +
      'before and after itself, and you can compare them below.',
  },
]);

function Walkthrough(): ReactNode {
  return (
    <div className={styles.walkthrough} data-testid="demo-walkthrough">
      {WALKTHROUGH.map((step) => (
        <section className={styles.walkthroughStep} key={step.id} data-step={step.id}>
          <h3 className={styles.walkthroughTitle}>{step.title}</h3>
          <p className={styles.driverProse}>{step.body}</p>
        </section>
      ))}
    </div>
  );
}

// ── The driver ─────────────────────────────────────────────────────────────

export function DemoDriver(): ReactNode {
  const transport = useGateTransport();
  const [reveal, setReveal] = useState<Reveal | null>(null);

  const declared = RESOURCES.has(DEMO_GATE_RUN);

  const { state, reload } = useResource<GateRunData>(
    transport,
    // The body is `{}` for every control. See the module header: one body, one request
    // key, one captured frame that serves all four controls under REPLAY.
    { resource: DEMO_GATE_RUN, body: {} },
    // `declared` gates the exchange as well as the render, so an undeclared key never
    // reaches `resolveRequest` and the reader gets the panel below instead of a stack.
    { enabled: declared && reveal !== null },
  );

  const press = useCallback(
    (next: Reveal) => {
      setReveal(next);
      // Every press is a fresh exchange. There is no automatic retry anywhere in this
      // console; a human pressing a button again is a decision with an author.
      reload();
    },
    [reload],
  );

  /*
   * SELF-ADDRESSING, WITH NO NEW ROUTE AND NO DEPLOY.
   *
   * A run answers with the subject it drove. Publishing it lets the gate surface
   * below open on that permit even where `GET /v1/demo/subjects` is not deployed —
   * measured 2026-08-15: the live URL answers that read 404 and this one 200. Nothing is
   * published until an exchange has RETURNED, and what is published is the payload's own
   * identifiers, verbatim; the surface says on the page that it learned them this way
   * rather than presenting them as its own choice.
   *
   * `state` is the whole dependency deliberately: the effect must re-run when a second
   * press replaces one answer with another, and `useResource` returns a new state object
   * for each.
   */
  const answered = state.status === 'ready' ? state.data : null;
  useEffect(() => {
    if (answered === null) return;
    publishGateRunSubject({
      permitId: answered.subject.subject_id,
      blockingCheckId: answered.subject.blocking_check_id,
      clauseId: clauseIdFromRun(answered.beats),
      externalRef: answered.subject.external_ref,
      runId: answered.run_id,
    });
  }, [answered]);

  /*
   * CONTRACT B — the completed run, published for the screen below this panel.
   *
   * `docs/leads/demo-story-plan.md` §7.1: this module is the PRODUCER and
   * `src/features/gate/last-run.ts` is the channel. The payload goes across VERBATIM,
   * including each refusing beat's whole refusal object; a consumer adapts it in its own
   * module and this one has no opinion about how.
   *
   * A SECOND effect rather than a line in the one above, because the two publications
   * answer different questions and are read by different screens: one says WHICH SUBJECT
   * this console is now about, the other says WHAT HAPPENED to it. A single effect would
   * make either one impossible to remove without reasoning about the other.
   *
   * Nothing is published while a run is in flight, and nothing is published for a
   * transport failure or an endpoint refusal — `null` on that channel means NO COMPLETED
   * RUN, which is the only state the subscriber's un-pressed rendering is true of.
   */
  useEffect(() => {
    if (answered === null) return;
    publishLastGateRun(answered);
  }, [answered]);

  if (transport === null) {
    return (
      <section className={styles.absent} data-testid="demo-driver-no-source">
        <span className={styles.absentTitle}>no source</span>
        <p className={styles.driverProse}>
          The composition root built no transport, so there is nothing to drive. This build carries
          neither <Mono>VITE_MAINLINE_API_BASE</Mono> nor <Mono>VITE_MAINLINE_BUNDLE_URL</Mono>. That
          is a fact about this deployment, not about any record.
        </p>
      </section>
    );
  }

  if (!declared) {
    return <DeclarationGapPanel resources={RESOURCES} />;
  }

  return (
    <section className={styles.driver} data-testid="demo-driver">
      <div className={styles.driverHead}>
        <h2 className={styles.driverTitle}>See the database refuse, and then refuse a tamper</h2>
        <Walkthrough />
        <p className={styles.driverProse}>
          Each control performs one <Mono>POST /v1/demo/gate-run</Mono> and shows the beat it names.
          The four beats share ONE <Mono>SERIALIZABLE</Mono> transaction, each write beat fenced by
          its own <Mono>SAVEPOINT</Mono>, and the whole transaction is rolled back — so they are
          produced together and cannot be driven one HTTP call at a time from a browser. Nothing you
          press here persists, and the payload carries the evidence for that rather than the claim.
        </p>
        {/*
          R11, in one sentence and on the page rather than in a comment. It sits BESIDE the
          paragraph above, which is unchanged: that one states the transaction discipline,
          this one states what the console does with a result that discipline delivers all
          at once. Both have to be readable at the same time, which is why this is a
          sibling paragraph and not an edit to that one.
        */}
        <p className={styles.driverProse} data-testid="demo-reveal-note">
          The beats below appear one after another as a reading aid, not as a replay: they were all
          produced by the single exchange above, and the <Mono>elapsed_ms</Mono> printed beside each
          one is that beat&apos;s own measurement from the payload rather than the pace of this
          reveal.
        </p>
      </div>

      <div className={styles.controls}>
        {CONTROLS.map((control) => (
          <button
            key={control.id}
            type="button"
            className={styles.control}
            data-testid={`demo-control-${control.id}`}
            data-primary={control.primary === true ? 'true' : undefined}
            aria-pressed={reveal === control.reveal}
            onClick={() => {
              press(control.reveal);
            }}
          >
            <span className={styles.controlLabel}>{control.label}</span>
            <span className={styles.controlExpect}>{control.expectation}</span>
          </button>
        ))}
      </div>

      {state.status === 'loading' && (
        <p className={styles.driverProse} role="status" data-testid="demo-run-loading">
          Running the four beats…
        </p>
      )}

      {state.status === 'failed' && (
        <div className={styles.absent} role="alert" data-testid="demo-run-failed">
          <span className={styles.absentTitle}>{state.failure}</span>
          <pre className={styles.verbatim}>{state.detail}</pre>
          <p className={styles.driverProse}>
            This is a transport failure, not the database refusing. Nothing on this screen is a claim
            about any record.
          </p>
        </div>
      )}

      {state.status === 'refused' && (
        <div className={styles.absent} role="alert" data-testid="demo-run-refused">
          <span className={styles.absentTitle}>the endpoint itself was refused</span>
          <div className={styles.exhibits}>
            <Sqlstate code={state.refusal.sqlstate} tone="refuse" showClass />
            <ConstraintName name={state.refusal.constraint} tone="refuse" />
          </div>
          <pre className={styles.verbatim}>{state.refusal.message}</pre>
        </div>
      )}

      {state.status === 'ready' && reveal !== null && (
        <GateRunReport run={state.data} reveal={reveal} />
      )}
    </section>
  );
}

// ── The honest fallback ────────────────────────────────────────────────────

/**
 * THE PANEL FOR A BUILD THAT STRIPPED THE DECLARATION — unreachable in this one.
 *
 * It takes the registry it reports about rather than reading `RESOURCES` itself, and the
 * reason is a test rather than a taste. The panel says *"`demo_gate_run` is not one of
 * the N this console declares"*, which is FALSE of the shipped registry — so the only way
 * to render it and read it back is to hand it a registry in which the sentence is true.
 * A parameter does that without touching the real declaration, which a module mock or a
 * `delete` on the shared map would both have to do, and either of those would leave the
 * suite one accident away from testing a console nobody ships.
 *
 * `tests/unit/gate/demo-driver.test.tsx` holds both halves: this panel rendered against a
 * stubbed registry, and `DemoDriver` rendered against the real one with the panel proven
 * absent. The fallback keeps its coverage; it merely stops being what a judge sees.
 */
export function DeclarationGapPanel({
  resources,
}: {
  readonly resources: ReadonlyMap<string, unknown>;
}): ReactNode {
  return (
    <section className={styles.absent} data-testid="demo-driver-not-declared">
      <span className={styles.absentTitle}>
        POST /v1/demo/gate-run is not addressable from this console
      </span>
      <p className={styles.driverProse}>
        The four beats are produced by one endpoint, inside one <Mono>SERIALIZABLE</Mono>{' '}
        transaction that is rolled back. This console addresses a server only through declared
        resources, and <Mono>{DEMO_GATE_RUN}</Mono> is not one of the <Mono>{resources.size}</Mono>{' '}
        it declares. Reaching the endpoint with a bare <Mono>fetch</Mono> would skip envelope and
        contract validation and would have no REPLAY counterpart — which is exactly the second code
        path D7 forbids — so the driver refuses to do that and says what is missing instead.
      </p>
      <ol className={styles.absentList}>
        {DECLARATION_GAP.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ol>
      <p className={styles.driverProse}>
        The contract these three would satisfy already exists and has been measured:{' '}
        <Mono>docs/deploy/gate-run-contract.md</Mono>.
      </p>
    </section>
  );
}

// ── The report ─────────────────────────────────────────────────────────────

/**
 * THE REPORT.
 *
 * The reading mode is the shell's and every `Disclosure` below reads it from
 * `DetailModeContext` — R6, and `src/app/detail-mode.ts` says why it is not threaded.
 * What PLAIN folds away here is the run's own WITNESS TABLES: the transaction's
 * savepoints, the before/after fingerprint, the row counts, the statement each beat
 * sent. The verdict, `persisted`, every beat, every SQLSTATE, every constraint name,
 * every verbatim message and the weakened-diagnosis notice are visible in both modes,
 * always.
 *
 * ── THE ONE THING THE LIST DOES THAT LOOKS LIKE A TRICK, AND IS NOT ──────────────
 *
 * `key={run.run_id}` on the `<ol>`. A CSS animation runs when an element ENTERS the
 * document, so a second press that reused the same list elements would leave the reveal
 * playing once and never again — the second reader of the same screen would see a
 * different screen from the first. The run identifier is the payload's own, one per
 * exchange, so keying on it makes each answered run a new list and each press behave like
 * the last. It is not a remount for its own sake and it is not a cache buster; it is the
 * identity of the thing being shown.
 */
export function GateRunReport({
  run,
  reveal,
}: {
  readonly run: GateRunData;
  readonly reveal: Reveal;
}): ReactNode {
  const cues = revealPlan(run.beats, reveal);

  return (
    <div data-testid="gate-run-report" data-verdict={run.verdict} data-reveal={String(reveal)}>
      <div className={styles.verdict}>
        <span className={styles.metaKey}>verdict</span>
        <span className={styles.verdictValue} data-verdict={run.verdict} data-testid="gate-run-verdict">
          {run.verdict}
        </span>
        <span className={styles.metaKey}>persisted</span>
        <Mono data-testid="gate-run-persisted">{String(run.persisted)}</Mono>
        <span className={styles.metaKey}>one transaction</span>
        <Mono data-testid="gate-run-single-transaction">
          {String(run.transaction.single_transaction)}
        </Mono>
        <span className={styles.metaKey}>run</span>
        <Mono>{run.run_id}</Mono>
      </div>

      {run.failures.length > 0 && (
        <ul className={styles.failures} data-testid="gate-run-failures">
          {run.failures.map((failure) => (
            <li key={failure}>{failure}</li>
          ))}
        </ul>
      )}

      <ol className={styles.beatList} data-testid="gate-run-beats" key={run.run_id}>
        {cues.map((cue) => (
          <Beat key={cue.beat.ordinal} cue={cue} />
        ))}
      </ol>

      {reveal === 'all' && (
        <>
          <Disclosure
            summary="Show the transaction this run opened, and the savepoint it fenced each write with"
            data-testid="gate-run-transaction-disclosure"
          >
            <Facts
              testId="gate-run-transaction"
              title="the transaction"
              entries={[
                ['isolation', run.transaction.isolation],
                ['disposition', run.transaction.disposition],
                ['opened', run.transaction.opened_logical_timestamp],
                ['closed', run.transaction.closed_logical_timestamp ?? '—'],
                ['savepoints', run.transaction.savepoints.join(' ')],
                ['retry sqlstate', run.transaction.retry_sqlstate ?? '—'],
                ['canonicalisation', run.transaction.canonicalisation],
              ]}
            />
          </Disclosure>
          <Facts
            testId="gate-run-subject"
            title="the subject, as the run opened"
            entries={[
              ['subject', `${run.subject.subject_kind} ${run.subject.subject_id}`],
              ['external ref', run.subject.external_ref],
              ['state', run.subject.state],
              ['gate epoch', String(run.subject.gate_epoch)],
              ['open_blocking (projected)', String(run.subject.open_blocking)],
              ['open_blocking (re-derived)', String(run.subject.open_blocking_derived)],
              ['site', run.subject.site_code],
            ]}
          />
          {/*
            THE ORDER IS THE ARGUMENT, again. `self_persisted` is first because it is what
            the verdict keys on; `identical` keeps its place beside it because it is a
            true statement about a different subject — the database, not this run — and
            removing it would have hidden a real reading rather than corrected a misread
            one. `concurrent_writes` is the third because it is the answer to the question
            a false `identical` raises: WHOSE rows moved.
          */}
          <Facts
            testId="gate-run-persistence"
            title="what this run left behind, and what the database did meanwhile"
            entries={[
              ['self_persisted', String(run.persistence_check.self_persisted)],
              ['identical', String(run.persistence_check.identical)],
              ['concurrent_writes', concurrentWrites(run.persistence_check.concurrent_writes)],
              ['tables compared', String(run.persistence_check.tables.length)],
              ['note', run.persistence_check.note],
            ]}
          />
          <Disclosure
            summary="Show the row counts and the permit row this run compared against itself, before and after"
            data-testid="gate-run-fingerprint-disclosure"
          >
            <Facts
              testId="gate-run-persistence-self"
              title="how self_persisted was computed — recompute it, do not take it"
              entries={[
                [
                  'minted disposition',
                  run.persistence_check.self_evidence.minted_disposition_id ?? '—',
                ],
                [
                  'rows carrying it after the rollback',
                  String(
                    run.persistence_check.self_evidence.minted_disposition_rows_after_rollback,
                  ),
                ],
                [
                  'permit row identical',
                  String(run.persistence_check.self_evidence.permit_row_identical),
                ],
              ]}
            />
            <BeforeAfter
              testId="gate-run-fingerprint"
              title="the fingerprint those readings were taken from"
              rows={fingerprintRows(run.persistence_check)}
            />
          </Disclosure>
        </>
      )}
    </div>
  );
}

/**
 * ONE BEAT, and the three attributes that carry the reading order into the stylesheet.
 *
 * `--beat-step` is the only value this component hands to CSS, and it is an INDEX — 0, 1,
 * 2, 3. The stylesheet multiplies it by `--tp-duration-evidence` to get a delay, so the
 * pace of the reveal is declared in one place, in the token the EVIDENCE register already
 * publishes, and no millisecond count is written in TypeScript or read by a reader.
 *
 * `data-refusal-index` is the beat's position among the refusals of this run. The
 * stylesheet gives the SECOND refusal a heavier rule than the first, because being
 * refused after the counter was forged is the rarer and stronger claim — and it does that
 * from a POSITION, never from a code. No sentence anywhere below is chosen by a SQLSTATE,
 * a constraint name or an outcome; D18, and `tests/unit/gate/demo-driver.test.tsx` reads
 * this file to prove it.
 *
 * `elapsed_ms` is labelled with the payload's own member name rather than a prose label,
 * for the reason the `Observed` docstring gives, and its value is the payload's number
 * with nothing done to it.
 */
function Beat({ cue }: { readonly cue: BeatCue }): ReactNode {
  const { beat } = cue;
  const tone = beat.outcome === 'refused' ? 'refuse' : 'neutral';

  return (
    <li
      className={styles.beat}
      data-outcome={beat.outcome}
      data-reveal-step={cue.stepIndex}
      data-refusal-index={cue.refusalIndex ?? undefined}
      style={{ '--beat-step': cue.stepIndex } as CSSProperties}
      data-testid={`gate-run-beat-${beat.ordinal}`}
    >
      <div className={styles.beatHead}>
        <span className={styles.beatOrdinal}>beat {beat.ordinal}</span>
        <span className={styles.beatName}>{beat.name}</span>
        <span className={styles.beatOutcome} data-outcome={beat.outcome}>
          {beat.outcome.toUpperCase()}
        </span>
        <span className={styles.metaKey}>elapsed_ms</span>
        <Mono data-testid={`gate-run-beat-${beat.ordinal}-elapsed`}>{elapsedText(beat)}</Mono>
        {!beat.matched_expectation && (
          <span className={styles.mismatch} data-testid={`gate-run-beat-${beat.ordinal}-mismatch`}>
            did not match its expectation ({beat.expected.outcome})
          </span>
        )}
      </div>

      <p className={styles.beatLabel}>{beat.label}</p>

      <div className={styles.exhibits}>
        {beat.sqlstate !== null && (
          <Sqlstate
            code={beat.sqlstate}
            tone={tone}
            showClass
            data-testid={`gate-run-beat-${beat.ordinal}-sqlstate`}
          />
        )}
        {beat.constraint !== null && (
          <ConstraintName
            name={beat.constraint}
            tone={tone}
            data-testid={`gate-run-beat-${beat.ordinal}-constraint`}
          />
        )}
      </div>

      {beat.constraint_source === 'parsed' && (
        <p className={styles.weakened} data-testid={`gate-run-beat-${beat.ordinal}-parsed`}>
          The exhibit above was PARSED out of the database&apos;s own message, not reported by the
          driver. That is a WEAKENED diagnosis and is shown as one: on this platform a PL/pgSQL RAISE
          carries no constraint name, so the raising object was recovered from the text.
        </p>
      )}

      {beat.message !== null && beat.message !== '' && (
        <pre className={styles.verbatim} data-testid={`gate-run-beat-${beat.ordinal}-message`}>
          {beat.message}
        </pre>
      )}

      <Observed observed={beat.observed} ordinal={beat.ordinal} />

      {beat.statement !== null && beat.statement !== '' && (
        <Disclosure
          summary="Show the exact statement this beat sent to the database"
          data-testid={`gate-run-beat-${beat.ordinal}-statement`}
        >
          <pre className={styles.verbatim}>{beat.statement}</pre>
        </Disclosure>
      )}

      {beat.note !== null && beat.note !== '' && <p className={styles.note}>{beat.note}</p>}
    </li>
  );
}

/**
 * What the beat SAW, rendered as key and value with no interpretation between them.
 *
 * The keys are the payload's own member names rather than prose labels, deliberately: a
 * label is a sentence the console wrote, and `open_blocking_projected` beside
 * `open_blocking_derived` says the thing the product is about without anybody phrasing it.
 */
function Observed({
  observed,
  ordinal,
}: {
  readonly observed: Readonly<Record<string, unknown>>;
  readonly ordinal: number;
}): ReactNode {
  const entries = Object.entries(observed);
  if (entries.length === 0) return null;

  return (
    <dl className={styles.meta} data-testid={`gate-run-beat-${ordinal}-observed`}>
      {entries.map(([key, value]) => (
        <div key={key} className={styles.metaRow}>
          <dt className={styles.metaKey}>{key}</dt>
          <dd className={styles.metaValue}>{renderValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function renderValue(value: unknown): string {
  if (value === null) return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value) ?? '—';
}

/**
 * `concurrent_writes`, rendered as the tables it names and the counts it carries.
 *
 * `null` is the contract's word for "`identical` was true, so there is nothing to name",
 * and it is shown as the same em dash every other absent value on this screen uses. The
 * arrow is a separator between two numbers the payload supplied; no number here is
 * computed by this module.
 */
function concurrentWrites(writes: GateRunPersistence['concurrent_writes']): string {
  if (writes === null) return '—';
  const entries = Object.entries(writes);
  if (entries.length === 0) return '{}';
  return entries.map(([table, [before, after]]) => `${table} ${before} → ${after}`).join('   ');
}

/**
 * The union of two records' keys, sorted.
 *
 * A union rather than the keys of `before`, because a table that appears on ONE side only
 * is exactly the reading a reader must not lose — and iterating one side would drop it
 * silently.
 */
function unionKeys(
  left: Readonly<Record<string, unknown>>,
  right: Readonly<Record<string, unknown>>,
): readonly string[] {
  return [...new Set([...Object.keys(left), ...Object.keys(right)])].sort((a, b) =>
    a.localeCompare(b),
  );
}

/**
 * The permit row as a walkable record, and `{}` for the row that was not there.
 *
 * `GateRunPermitRow` is an interface, and TypeScript gives an interface no implicit index
 * signature, so it cannot be handed to `unionKeys` as a record. Copying it through
 * `Object.entries` keeps the declared columns declared — a reader still sees the seven
 * the contract names — while letting the walk below iterate whatever the payload actually
 * carried, which is the behaviour a contract amendment needs.
 */
function permitColumns(row: GateRunPermitRow | null): Readonly<Record<string, unknown>> {
  const columns: Record<string, unknown> = {};
  if (row === null) return columns;
  for (const [column, value] of Object.entries(row)) columns[column] = value;
  return columns;
}

/**
 * Every reading the two fingerprints carry, as `[member, before, after]`.
 *
 * The row labels are the payload's own member paths — `row_counts.mainline.permit`,
 * `permit_row.open_blocking` — and not prose, for the reason the `Observed` docstring
 * gives: a label is a sentence the console wrote. The permit row's COLUMNS are walked
 * rather than listed here, so a column added to the contract appears on screen without
 * this module being edited to admit it.
 */
function fingerprintRows(
  check: GateRunPersistence,
): readonly (readonly [string, string, string])[] {
  const rows: (readonly [string, string, string])[] = [];

  for (const table of unionKeys(check.before.row_counts, check.after.row_counts)) {
    rows.push([
      `row_counts.${table}`,
      renderValue(check.before.row_counts[table]),
      renderValue(check.after.row_counts[table]),
    ]);
  }

  for (const table of unionKeys(check.before.subject_row_counts, check.after.subject_row_counts)) {
    rows.push([
      `subject_row_counts.${table}`,
      renderValue(check.before.subject_row_counts[table]),
      renderValue(check.after.subject_row_counts[table]),
    ]);
  }

  const beforeRow = permitColumns(check.before.permit_row);
  const afterRow = permitColumns(check.after.permit_row);
  for (const column of unionKeys(beforeRow, afterRow)) {
    rows.push([
      `permit_row.${column}`,
      renderValue(beforeRow[column]),
      renderValue(afterRow[column]),
    ]);
  }

  return rows;
}

/**
 * Two readings of the same member, side by side, with the comparison left to the reader.
 *
 * `data-moved` is derived from the two strings on the row and from nothing else, so a
 * browser spec can find the rows that moved without this module having to say which ones
 * are interesting. It is an attribute rather than a colour: an EVIDENCE surface may not
 * make a claim that only survives in a screenshot.
 */
function BeforeAfter({
  title,
  rows,
  testId,
}: {
  readonly title: string;
  readonly rows: readonly (readonly [string, string, string])[];
  readonly testId: string;
}): ReactNode {
  return (
    <table className={styles.compare} data-testid={testId}>
      <caption className={styles.metaKey}>{title}</caption>
      <thead>
        <tr>
          <th scope="col">reading</th>
          <th scope="col">before</th>
          <th scope="col">after</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([member, before, after]) => (
          <tr key={member} data-testid={`${testId}-${member}`} data-moved={String(before !== after)}>
            <th scope="row" className={styles.compareMember}>
              {member}
            </th>
            <td className={styles.metaValue}>{before}</td>
            <td className={styles.metaValue}>{after}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Facts({
  title,
  entries,
  testId,
}: {
  readonly title: string;
  readonly entries: readonly (readonly [string, string])[];
  readonly testId: string;
}): ReactNode {
  return (
    <section data-testid={testId}>
      <p className={styles.metaKey}>{title}</p>
      <dl className={styles.meta}>
        {entries.map(([key, value]) => (
          <div key={key} className={styles.metaRow}>
            <dt className={styles.metaKey}>{key}</dt>
            <dd className={styles.metaValue}>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
