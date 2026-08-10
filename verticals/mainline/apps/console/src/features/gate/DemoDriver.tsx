// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

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

// ── The resource, and the three files that must name it ────────────────────

/**
 * The resource key the console would address. It is checked against `RESOURCES` at
 * render time rather than assumed, because a `resolveRequest` on an undeclared key throws
 * a stack trace where a reader deserves a sentence.
 */
export const DEMO_GATE_RUN = 'demo_gate_run';

/**
 * The three files that have to name this endpoint before the controls can fire, none of
 * which this worker owns. Rendered verbatim in the unavailable panel: an absence a reader
 * can act on beats an absence they have to go and diagnose.
 */
const DECLARATION_GAP: readonly string[] = [
  'verticals/mainline/apps/console/src/data/resources.ts — a seventeenth declare(): ' +
    "declare('demo_gate_run', 'POST', '/v1/demo/gate-run', <contract prefix>gate-run.schema.json, " +
    "'kernel', …). Sixteen resources are declared today and this is not one of them.",
  'verticals/mainline/apps/console/src/data/contracts.ts — gate-run.schema.json registered ' +
    'alongside the other sixteen, as a verbatim copy of ' +
    'verticals/mainline/apps/demo-api/contracts/gate-run.schema.json. The transport validates ' +
    'every response against its contract before returning it, and a schema $id nobody registered ' +
    'raises rather than passes.',
  'verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py — Route("POST", ' +
    '"/v1/demo/gate-run", "demo_gate_run") plus SCHEMA_IDS["demo_gate_run"]. The handler is ' +
    'complete (gate_run.py) and is reachable through handle_transition today; the route table ' +
    'declares the four kernel POSTs and no demo route, so the endpoint 404s.',
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

export interface GateRunPersistence {
  readonly identical: boolean;
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
    return (
      <section className={styles.absent} data-testid="demo-driver-not-declared">
        <span className={styles.absentTitle}>
          POST /v1/demo/gate-run is not addressable from this console
        </span>
        <p className={styles.driverProse}>
          The four beats are produced by one endpoint, inside one <Mono>SERIALIZABLE</Mono>{' '}
          transaction that is rolled back. This console addresses a server only through declared
          resources, and <Mono>{DEMO_GATE_RUN}</Mono> is not one of the{' '}
          <Mono>{RESOURCES.size}</Mono> it declares. Reaching the endpoint with a bare{' '}
          <Mono>fetch</Mono> would skip envelope and contract validation and would have no REPLAY
          counterpart — which is exactly the second code path D7 forbids — so the driver refuses to
          do that and says what is missing instead.
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
          <Facts
            testId="gate-run-persistence"
            title="what the database looked like before and after"
            entries={[
              ['identical', String(run.persistence_check.identical)],
              ['tables compared', String(run.persistence_check.tables.length)],
              ['note', run.persistence_check.note],
            ]}
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
