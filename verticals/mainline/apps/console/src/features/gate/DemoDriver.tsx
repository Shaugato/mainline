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
 */

import { useCallback, useState, type ReactNode } from 'react';

import { RESOURCES } from '../../data/resources';
import { useResource } from '../../data/useResource';
import { ConstraintName, Mono, Sqlstate } from '../../design/primitives';

import styles from './demo-driver.module.css';
import { useGateTransport } from './transport-context';

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

// ── The payload ────────────────────────────────────────────────────────────

/**
 * A STRUCTURAL reading of `gate-run.schema.json`, not a re-declaration of it.
 *
 * The normative contract is `verticals/mainline/apps/demo-api/contracts/gate-run.schema.json`
 * (`$id` `…/contracts/1.0/gate-run.schema.json`) and it is enforced by the transport, in
 * `finishExchange`, before any of this renders. What is declared here is only the subset
 * this screen reads — the same discipline `src/app/refusal.ts` applies to the refusal wire
 * payload, and for the same reason: a component that re-declares a whole contract is a
 * second copy of it that can drift.
 */
export interface GateRunBeat {
  readonly ordinal: number;
  readonly name: string;
  readonly label: string;
  readonly expected: { readonly outcome: string; readonly sqlstate?: string; readonly constraint?: string };
  readonly outcome: string;
  readonly sqlstate: string | null;
  readonly constraint: string | null;
  readonly constraint_source: 'reported' | 'parsed' | 'absent' | null;
  readonly message: string | null;
  readonly matched_expectation: boolean;
  readonly elapsed_ms: number;
  readonly statement: string | null;
  readonly observed: Readonly<Record<string, unknown>>;
  readonly note: string | null;
}

export interface GateRunTransaction {
  readonly isolation: string;
  readonly disposition: string;
  readonly opened_logical_timestamp: string;
  readonly closed_logical_timestamp: string | null;
  readonly single_transaction: boolean;
  readonly savepoints: readonly string[];
  readonly retry_sqlstate: string | null;
  readonly canonicalisation: string;
}

export interface GateRunSubject {
  readonly subject_kind: string;
  readonly subject_id: string;
  readonly external_ref: string;
  readonly state: string;
  readonly head_seq: number;
  readonly gate_epoch: number;
  readonly open_blocking: number;
  readonly open_blocking_derived: number;
  readonly blocking_check_id: string | null;
  readonly exposure_receipt_id: string | null;
  readonly site_code: string;
}

/**
 * The permit row's own columns, as a fingerprint reads them. `null` when the subject was
 * absent at that end of the run.
 *
 * These columns are here rather than a count because BEAT 3 IS A COLUMN EDIT: it forces
 * `open_blocking` to zero out of band, which moves nothing a `count(*)` can see. A
 * persistence check made only of counts would report `identical: true` over the one write
 * this demo exists to talk about.
 */
export interface GateRunPermitRow {
  readonly state: string;
  readonly head_seq: number;
  readonly gate_epoch: number;
  readonly open_blocking: number;
  readonly unmet_floor_count: number;
  readonly countersigned_count: number;
  readonly merged_commit: string | null;
}

export interface GateRunFingerprint {
  /** Every table the four beats can write, counted WHOLE — unscoped, deliberately. */
  readonly row_counts: Readonly<Record<string, number>>;
  /** The same question asked of THIS permit only. */
  readonly subject_row_counts: Readonly<Record<string, number>>;
  readonly permit_row: GateRunPermitRow | null;
}

/**
 * The run-scoped readings `self_persisted` is computed from — carried in the payload, the
 * contract says, "so that a reader can recompute the verdict rather than take it".
 * Rendering them is what makes that sentence true of this screen as well.
 */
export interface GateRunSelfEvidence {
  readonly minted_disposition_id: string | null;
  readonly minted_disposition_rows_after_rollback: number;
  readonly subject_row_counts_before: Readonly<Record<string, number>>;
  readonly subject_row_counts_after: Readonly<Record<string, number>>;
  readonly permit_row_identical: boolean;
}

/**
 * WIDENED 2026-08-14 — the contract moved and this reading had not.
 *
 * `gate-run.schema.json` requires eight members here: `before`, `after`, `identical`,
 * `self_persisted`, `self_evidence`, `concurrent_writes`, `tables`, `note`. This
 * interface declared three, and the three it declared were led by the one the contract's
 * own `persistence_check` description says the verdict does NOT key on:
 *
 *   `identical` is a statement about THE DATABASE — every one of those tables, counted
 *   whole. `self_persisted` is the statement about THIS RUN, and it is what the verdict
 *   keys on, because a whole-table count cannot distinguish "I persisted something" from
 *   "somebody else did".
 *
 * A screen that showed only `identical` therefore showed the wrong field with a straight
 * face: a busy shared cluster makes `identical` false for reasons that have nothing to do
 * with the run in front of the reader. Nothing was removed to fix that — `identical` is
 * still on screen, beside the field it was standing in for, and `concurrent_writes` names
 * the other caller's tables rather than letting the reader guess.
 */
export interface GateRunPersistence {
  readonly before: GateRunFingerprint;
  readonly after: GateRunFingerprint;
  readonly identical: boolean;
  readonly self_persisted: boolean;
  readonly self_evidence: GateRunSelfEvidence;
  /**
   * `null` when `identical` is true. Otherwise the tables whose unscoped count moved
   * while this run was open, each as `[before, after]` — ANOTHER caller's rows, reported
   * rather than blamed on the run.
   */
  readonly concurrent_writes: Readonly<Record<string, readonly [number, number]>> | null;
  readonly tables: readonly string[];
  readonly note: string;
}

export interface GateRunData {
  readonly schema_id: string;
  readonly run_id: string;
  readonly generated_at: string;
  readonly outcome: string;
  readonly verdict: string;
  readonly failures: readonly string[];
  readonly persisted: boolean;
  readonly elapsed_ms: number;
  readonly transaction: GateRunTransaction;
  readonly subject: GateRunSubject;
  readonly beats: readonly GateRunBeat[];
  readonly persistence_check: GateRunPersistence;
}

// ── The controls ───────────────────────────────────────────────────────────

/** Which beats a control reveals. `all` is every beat plus the run's own witnesses. */
export type Reveal = 2 | 3 | 4 | 'all';

interface Control {
  readonly id: string;
  readonly reveal: Reveal;
  readonly label: string;
  /** What this beat was WRITTEN against. Compared on screen against what came back. */
  readonly expectation: string;
}

/**
 * Fixed order, and the order is the argument. Refuse; refuse under attack; admit. A demo
 * that showed the admission first would be a demo about a database that says yes.
 */
const CONTROLS: readonly Control[] = Object.freeze([
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
  {
    id: 'all',
    reveal: 'all',
    label: 'RUN ALL',
    expectation: 'all four beats, one transaction, rolled back — with the evidence for both claims',
  },
]);

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
        <h2 className={styles.driverTitle}>Drive the gate</h2>
        <p className={styles.driverProse}>
          Each control performs one <Mono>POST /v1/demo/gate-run</Mono> and shows the beat it names.
          The four beats share ONE <Mono>SERIALIZABLE</Mono> transaction, each write beat fenced by
          its own <Mono>SAVEPOINT</Mono>, and the whole transaction is rolled back — so they are
          produced together and cannot be driven one HTTP call at a time from a browser. Nothing you
          press here persists, and the payload carries the evidence for that rather than the claim.
        </p>
      </div>

      <div className={styles.controls}>
        {CONTROLS.map((control) => (
          <button
            key={control.id}
            type="button"
            className={styles.control}
            data-testid={`demo-control-${control.id}`}
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

export function GateRunReport({
  run,
  reveal,
}: {
  readonly run: GateRunData;
  readonly reveal: Reveal;
}): ReactNode {
  const beats = reveal === 'all' ? run.beats : run.beats.filter((beat) => beat.ordinal === reveal);

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

      <ol className={styles.beatList} data-testid="gate-run-beats">
        {beats.map((beat) => (
          <Beat key={beat.ordinal} beat={beat} />
        ))}
      </ol>

      {reveal === 'all' && (
        <>
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
        </>
      )}
    </div>
  );
}

function Beat({ beat }: { readonly beat: GateRunBeat }): ReactNode {
  const tone = beat.outcome === 'refused' ? 'refuse' : 'neutral';

  return (
    <li className={styles.beat} data-outcome={beat.outcome} data-testid={`gate-run-beat-${beat.ordinal}`}>
      <div className={styles.beatHead}>
        <span className={styles.beatOrdinal}>beat {beat.ordinal}</span>
        <span className={styles.beatName}>{beat.name}</span>
        <span className={styles.beatOutcome} data-outcome={beat.outcome}>
          {beat.outcome.toUpperCase()}
        </span>
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
        <details className={styles.statement}>
          <summary>the statement this beat sent</summary>
          <pre className={styles.verbatim}>{beat.statement}</pre>
        </details>
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
