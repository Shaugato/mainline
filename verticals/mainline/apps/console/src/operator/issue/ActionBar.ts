// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ACTION BAR — where a supervisor issues a permit and a database refuses.
 *
 *     ┌──────────────────────────────────────────────────────────────────────────────┐
 *     │  1 obligation outstanding                       [ Save draft ]  [ ISSUE ▸ ]  │
 *     └──────────────────────────────────────────────────────────────────────────────┘
 *
 * The button says **ISSUE** — HSG250 Figure 1 element 9, *"signature (issuing authority)
 * confirming that isolations have been made and precautions taken"*. Not "Merge", which is
 * our kernel's word for the transition and nobody else's; not "Submit", which is a web
 * form's word. A supervisor issues a permit.
 *
 * ┌──────────────────────────────────────────────────────────────────────────────────┐
 * │ R4 — THE ISSUE BUTTON CALLS `POST /v1/demo/gate-run`.                             │
 * │ IT MUST NEVER CALL `POST /v1/permits/{id}/merge`.                                 │
 * │                                                                                   │
 * │ That route answers **423 Locked** on the seeded demo subject, with `use_instead`   │
 * │ naming the gate-run route (docs/deploy/gate-run-contract.md §7). The demo permit   │
 * │ is a single shared public copy and a merge on it is irreversible — one judge       │
 * │ pressing one button must not brick the demo for the next — so the deployment       │
 * │ refuses to mutate it. **A 423 is the demo protecting itself, not a gate refusal.** │
 * │ Its message is about a lock, not about an obligation. Rendering one inside a       │
 * │ refusal banner would put a fabricated exhibit in front of a judge, which is the    │
 * │ single most likely wrong turn available to a builder of this screen                │
 * │ (r3-operator §5.5, operator-systems-plan M8/R4).                                   │
 * │                                                                                   │
 * │ `GATE_RUN_PATH` from `beats.ts` is the only path posted to here, and there is      │
 * │ exactly one `post(...)` call in this file.                                         │
 * └──────────────────────────────────────────────────────────────────────────────────┘
 *
 * ONE PRESS, ONE REQUEST, FOUR REAL BEATS. The response carries all four; `disclosure.ts`
 * reveals them in order under the operator's own controls and carries the permanent line
 * that says so. `pending.ts` drives the wait off the real promise with a real clock —
 * **no timer schedules anything anywhere in this directory**, there is no optimistic state
 * and no skeleton that pretends to be work. A unit test greps these files for the two
 * scheduling primitives and fails on either. Every per-beat duration on screen is the
 * payload's own `elapsed_ms`.
 */

import { disclosureLine, runGate, type GateRunResult } from '../kernel/gate-run';

import {
  GATE_RUN_PATH,
  admissionReading,
  formatMs,
  observedOutstanding,
  outstandingLine,
  persistenceReading,
  readRun,
  type BeatView,
} from './beats';
import { renderRefusalBanner, renderUndecidedNotice } from './RefusalBanner';
import { advanceLabel, createDisclosure, renderDisclosureLine } from './disclosure';
import { PENDING_NOTE, createPending, pendingLabel, type PendingState } from './pending';

import type { GateRun } from '../../data/types.generated';

import './issue.css';

/** How much one press shows before the operator asks the next question (R5). */
const BEATS_REVEALED_ON_PRESS = 2;

export interface ActionBarOptions {
  /**
   * Obligations outstanding on this permit, read from the API by the screen that owns the
   * permit. `null` when no read supplied one — the bar then says so rather than showing a
   * zero, because a zero here is a claim about a permit.
   */
  readonly outstanding: number | null;
  /** A real external reference for the precursor, if a read supplied one. Never invented. */
  readonly precursorLabel?: string | undefined;
  /** Notified with the real exchange so the screen's request log can record it. */
  readonly onExchange?: ((exchange: unknown) => void) | undefined;
}

export interface ActionBarHandle {
  readonly element: HTMLElement;
  /** The same work the button does. Exposed for the capture harness, not for a fixture. */
  press(): Promise<void>;
}

export function mountActionBar(options: ActionBarOptions): ActionBarHandle {
  const root = el('div', 'cow-issue');

  const bar = el('section', 'cow-actionbar');
  bar.dataset.locked = 'false';

  const standing = el('p', 'cow-actionbar__standing');
  standing.dataset.standing = 'true';
  standing.textContent = outstandingLine(options.outstanding);

  const controls = el('div', 'cow-actionbar__controls');

  const saveDraft = el('button', 'cow-btn') as HTMLButtonElement;
  saveDraft.type = 'button';
  saveDraft.textContent = 'Save draft';
  saveDraft.dataset.action = 'save-draft';
  // Named, never populated. No route in this deployment stores a draft, so the control is
  // present and disabled with the reason beside it rather than wired to something that
  // would have to pretend. R9's rule for a field with no column, applied to an action.
  saveDraft.disabled = true;
  saveDraft.setAttribute('aria-describedby', 'cow-save-note');

  const issue = el('button', 'cow-btn cow-btn--issue') as HTMLButtonElement;
  issue.type = 'button';
  issue.textContent = 'ISSUE ▸';
  issue.dataset.action = 'issue';

  controls.append(saveDraft, issue);
  bar.append(standing, controls);

  const saveNote = el('p', 'cow-actionbar__note');
  saveNote.id = 'cow-save-note';
  saveNote.textContent = 'Save draft — not carried by this deployment.';

  const lock = el('p', 'cow-actionbar__lock');
  lock.dataset.lock = 'true';
  lock.hidden = true;

  const pendingBox = el('div', 'cow-issue__pending');
  pendingBox.dataset.pending = 'true';
  pendingBox.hidden = true;

  const result = el('div', 'cow-issue__result');
  result.dataset.result = 'true';

  root.append(bar, saveNote, lock, pendingBox, result);

  let inFlight = false;

  function setLock(reason: string | null): void {
    if (reason === null) {
      bar.dataset.locked = 'false';
      lock.hidden = true;
      lock.textContent = '';
      issue.disabled = false;
      return;
    }
    bar.dataset.locked = 'true';
    lock.hidden = false;
    lock.textContent = reason;
    issue.disabled = true;
    issue.setAttribute('aria-describedby', 'cow-lock-note');
    lock.id = 'cow-lock-note';
  }

  function clearPending(): void {
    pendingBox.hidden = true;
    pendingBox.replaceChildren();
  }

  function renderPending(state: PendingState): void {
    if (state.phase !== 'in_flight') {
      clearPending();
      return;
    }
    pendingBox.hidden = false;
    const label = el('p', 'cow-issue__pending-label');
    label.textContent = pendingLabel(state);
    const note = el('p', 'cow-issue__pending-note');
    note.textContent = PENDING_NOTE;
    pendingBox.replaceChildren(label, note);
    issue.textContent = pendingLabel(state);
  }

  async function press(): Promise<void> {
    // One press is one POST. A second press while the first is open would put two
    // transactions on the wire behind one button, and the disclosure line would then be
    // saying "one request" about two.
    if (inFlight) return;
    inFlight = true;
    setLock(null);
    issue.disabled = true;
    result.replaceChildren();

    const pending = createPending();
    const unsubscribe = pending.subscribe(renderPending);

    try {
      // ── THE ONLY REQUEST THIS SCREEN MAKES. R4: gate-run, never permits/{id}/merge. ──
      // `runGate()` is the kernel client's gate-run call: one POST, one transaction, four
      // beats, and it never rejects — a 503 carrying an envelope is a run, not an error.
      const gate = await pending.track(runGate());
      options.onExchange?.(gate.exchange);
      render(gate);
    } catch (error: unknown) {
      renderTransportFailure(error);
    } finally {
      unsubscribe();
      clearPending();
      issue.textContent = 'ISSUE ▸';
      inFlight = false;
    }
  }

  function render(gate: GateRunResult): void {
    const exchange = gate.exchange;
    const reading = readRun({
      status: exchange.status,
      wireBytes: exchange.wireBytes,
      receivedAt: exchange.receivedAt,
      data: gate.run,
    });

    // R4, checked rather than trusted: the path that actually went on the wire is the
    // gate-run route. If it were ever anything else, the screen says so instead of
    // rendering whatever came back as though it were a gate answer.
    if (exchange.path !== GATE_RUN_PATH) {
      result.replaceChildren(
        problemPanel(
          'THIS SCREEN ASKED THE WRONG QUESTION',
          `The request went to ${exchange.path}. The ISSUE button posts to ${GATE_RUN_PATH} ` +
            'and nothing on this screen may render an answer from any other route as a gate answer.',
        ),
      );
      issue.disabled = false;
      return;
    }

    if (reading.kind === 'unreadable') {
      // No gate-run payload came back. Whatever this was, it was not a refusal, and it is
      // not dressed as one. The kernel's own sentence is rendered verbatim when it wrote one.
      const said = exchange.problem?.detail ?? exchange.failure?.detail ?? null;
      result.replaceChildren(
        problemPanel(
          'NO ANSWER TO RENDER',
          `The request returned HTTP ${reading.httpStatus} and no gate-run payload. ` +
            'Nothing was refused and nothing was issued.' +
            (said === null ? '' : ` The deployment said: ${said}`),
        ),
      );
      issue.disabled = false;
      return;
    }

    // Composed by the kernel client beside the request that produced it — never here.
    const line = renderDisclosureLine(disclosureLine(gate));

    if (reading.kind === 'undecided') {
      const notice = renderUndecidedNotice(reading);
      result.replaceChildren(line);
      if (notice !== null) result.append(notice);
      const anomalies = anomalyPanel(gate);
      if (anomalies !== null) result.append(anomalies);
      // No lock: nothing refused this write, so nothing is locking the button.
      issue.disabled = false;
      return;
    }

    const beats = reading.beats;
    const first = beats[0];
    if (first !== undefined) {
      const seen = observedOutstanding(first);
      if (seen !== null) standing.textContent = outstandingLine(seen);
    }

    const disclosure = createDisclosure(beats.length, Math.min(BEATS_REVEALED_ON_PRESS, beats.length));
    const stage = el('div', 'cow-issue__stage');

    const paint = (): void => {
      stage.replaceChildren();
      let refusals = 0;
      let lockReason: string | null = null;

      for (const beat of beats.slice(0, disclosure.revealed)) {
        if (beat.isRefusal) {
          const banner = renderRefusalBanner(beat, {
            priorRefusals: refusals,
            precursorLabel: options.precursorLabel,
          });
          if (banner !== null) stage.append(banner);
          refusals += 1;
          lockReason =
            beat.constraint === null
              ? 'ISSUE is locked: the database refused this write.'
              : `ISSUE is locked: ${beat.constraint} refused this write.`;
        } else {
          stage.append(beatPanel(beat));
        }
      }

      if (disclosure.canAdvance) {
        const next = beats[disclosure.revealed];
        const label = advanceLabel(next);
        if (label !== null) {
          const advance = el('button', 'cow-btn cow-btn--advance') as HTMLButtonElement;
          advance.type = 'button';
          advance.textContent = label;
          advance.dataset.action = 'advance';
          advance.addEventListener('click', () => {
            disclosure.advance();
          });
          stage.append(advance);
        }
      } else {
        stage.append(runFooter(reading.run));
        const anomalies = anomalyPanel(gate);
        if (anomalies !== null) stage.append(anomalies);
      }

      setLock(lockReason);
    };

    disclosure.subscribe(paint);
    paint();
    result.replaceChildren(line, stage);
  }

  function renderTransportFailure(error: unknown): void {
    // A transport failure is the correct diagnosis for "the request did not complete".
    // It is not a refusal and it never renders as one.
    const detail = error instanceof Error ? error.message : String(error);
    result.replaceChildren(
      problemPanel(
        'THE REQUEST DID NOT COMPLETE',
        `${detail} — nothing was refused and nothing was issued.`,
      ),
    );
    issue.disabled = false;
  }

  issue.addEventListener('click', () => {
    void press();
  });

  return { element: root, press };
}

// ───────────────────────────────────────────────────────────────────────────────────────
// Panels for the beats that are not refusals
// ───────────────────────────────────────────────────────────────────────────────────────

function beatPanel(beat: BeatView): HTMLElement {
  const admission = admissionReading(beat);
  const panel = el('section', admission === null ? 'cow-beat' : 'cow-beat cow-beat--admitted');
  panel.dataset.beat = beat.name;
  panel.dataset.ordinal = String(beat.ordinal);
  panel.dataset.outcome = beat.outcome;

  if (admission !== null) {
    // R16 — the film does not end on a refusal. A gate that always refuses is broken,
    // not safe. One signed disposition and the same issue is admitted.
    const headline = el('p', 'cow-beat__headline');
    headline.textContent = 'ISSUE ADMITTED';
    panel.append(headline);
  }

  const label = el('p', 'cow-beat__label');
  label.textContent = beat.label;
  panel.append(label);

  const rows = el('dl', 'cow-refusal__rows');
  if (beat.sqlstate !== null) row(rows, 'SQLSTATE', beat.sqlstate);

  const observed = beat.observed;
  if (observed.state !== undefined) row(rows, 'state', observed.state);
  if (observed.open_blocking_projected !== undefined) {
    row(rows, 'open_blocking (projected column)', String(observed.open_blocking_projected));
  }
  if (observed.open_blocking_derived !== undefined) {
    row(rows, 'open_blocking (re-derived)', String(observed.open_blocking_derived));
  }
  if (observed.gate_epoch !== undefined) row(rows, 'gate_epoch', String(observed.gate_epoch));
  if (observed.head_seq !== undefined) row(rows, 'head_seq', String(observed.head_seq));
  if (observed.blocking_check_id !== undefined && observed.blocking_check_id !== null) {
    row(rows, 'blocking obligation', observed.blocking_check_id);
  }

  if (admission !== null) {
    if (admission.dispositionId !== null) row(rows, 'disposition', admission.dispositionId);
    if (admission.dispositionKind !== null) row(rows, 'disposition kind', admission.dispositionKind);
    if (admission.openBlockingAfterSignature !== null) {
      row(rows, 'open_blocking after the signature', String(admission.openBlockingAfterSignature));
    }
    if (admission.clearanceDigest !== null) {
      row(rows, 'clearance digest (server-computed)', admission.clearanceDigest);
    }
    if (admission.mergedAt !== null) row(rows, 'merged_at', admission.mergedAt);
    if (admission.permitState !== null) row(rows, 'permit state', admission.permitState);
  }

  row(rows, 'elapsed (server-measured)', formatMs(beat.elapsedMs));
  if (beat.statement !== null) row(rows, 'statement', beat.statement);
  if (!beat.matchedExpectation) {
    row(rows, 'DID NOT MATCH EXPECTATION', `expected ${beat.expectedOutcome}; observed ${beat.outcome}`);
    if (beat.note !== null) row(rows, 'note', beat.note);
  }
  panel.append(rows);
  return panel;
}

/** The verdict, the single-transaction witness, and the proof that nothing persisted. */
function runFooter(run: GateRun): HTMLElement {
  const panel = el('section', 'cow-run');
  panel.dataset.verdict = run.verdict;

  const headline = el('p', 'cow-run__headline');
  headline.textContent = `VERDICT ${run.verdict}`;
  panel.append(headline);

  if (run.failures.length > 0) {
    const list = el('ul', 'cow-run__failures');
    for (const failure of run.failures) {
      const item = document.createElement('li');
      item.textContent = failure;
      list.append(item);
    }
    panel.append(list);
  }

  const rows = el('dl', 'cow-refusal__rows');
  row(rows, 'isolation', run.transaction.isolation);
  row(rows, 'transaction', run.transaction.disposition);
  row(
    rows,
    'one transaction (equal cluster logical timestamps)',
    `${run.transaction.single_transaction} · ${run.transaction.opened_logical_timestamp} → ${
      run.transaction.closed_logical_timestamp ?? 'not read'
    }`,
  );
  row(rows, 'savepoints', run.transaction.savepoints.join(', '));

  // `self_persisted`, not `identical`. `identical` is a statement about the whole shared
  // database and goes false the moment any other caller commits a row — which is not this
  // run's doing. It is reported beside this reading, never in place of it.
  const persistence = persistenceReading(run);
  row(rows, 'this run persisted anything', String(persistence.selfPersisted));
  row(
    rows,
    'minted disposition after rollback',
    `${persistence.mintedDispositionId ?? 'none minted'} · ${persistence.mintedRowsAfterRollback} rows`,
  );
  row(rows, 'permit row unchanged', String(persistence.permitRowIdentical));
  row(rows, 'whole database unchanged', String(persistence.identical));
  for (const write of persistence.concurrentWrites) {
    row(rows, `another caller wrote to ${write.table}`, write.counts.join(' → '));
  }
  panel.append(rows);

  const note = el('p', 'cow-run__note');
  note.textContent = persistence.note;
  panel.append(note);

  return panel;
}

/**
 * The transport's own reading of the payload against the contract, when it found something.
 *
 * Labelled as THIS CLIENT's reading, not the kernel's words, because that is what it is.
 * Empty is the normal case; a non-empty one means the deployment sent something the
 * contract does not allow, and that is worth seeing rather than smoothing over.
 */
function anomalyPanel(gate: GateRunResult): HTMLElement | null {
  if (gate.anomalies.length === 0) return null;
  const panel = el('section', 'cow-problem');
  panel.setAttribute('role', 'status');
  const title = el('p', 'cow-problem__headline');
  title.textContent = 'THIS CLIENT READ THE PAYLOAD AGAINST THE CONTRACT AND DISAGREED';
  panel.append(title);
  const list = el('ul', 'cow-run__failures');
  for (const anomaly of gate.anomalies) {
    const item = document.createElement('li');
    item.textContent = anomaly;
    list.append(item);
  }
  panel.append(list);
  return panel;
}

function problemPanel(headline: string, body: string): HTMLElement {
  const panel = el('section', 'cow-problem');
  panel.setAttribute('role', 'status');
  const title = el('p', 'cow-problem__headline');
  title.textContent = headline;
  const text = el('p', 'cow-problem__body');
  text.textContent = body;
  panel.append(title, text);
  return panel;
}

// ───────────────────────────────────────────────────────────────────────────────────────
// DOM helpers. No framework reaches this entry (R1).
// ───────────────────────────────────────────────────────────────────────────────────────

function el(tag: string, className: string): HTMLElement {
  const element = document.createElement(tag);
  element.className = className;
  return element;
}

function row(list: HTMLElement, label: string, value: string): void {
  const term = document.createElement('dt');
  term.textContent = label;
  const detail = document.createElement('dd');
  const value_ = document.createElement('code');
  value_.className = 'cow-refusal__value';
  value_.textContent = value;
  detail.append(value_);
  list.append(term, detail);
}
