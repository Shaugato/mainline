// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SECOND REFUSAL — reading `POST /v1/demo/cr-gate-run`, and rendering only what it sent.
 *
 * ── WHAT THIS EXISTS TO CLOSE ────────────────────────────────────────────────────────
 *
 * The permit screen shows that a supervisor cannot ISSUE a permit which relies on a clause
 * a past incident's blame still reaches. The obvious next question — *fine, so couldn't
 * somebody just rewrite the rule?* — was answerable by this deployment's database and by
 * nothing this console could reach: `mainline.change_request` carries
 * `cr_gate_closed_when_merged` as a CHECK and `fn_cr_merge_gate` as a BEFORE UPDATE
 * trigger, both keyed `WHEN NEW.state = 'merged'`, and there was **no HTTP path on which to
 * attempt the edit and be refused.** This module renders the answer to the attempt.
 *
 * ── THE FOUR PROPERTIES THIS MODULE IS BUILT AROUND ──────────────────────────────────
 *
 * 1. **It composes nothing.** Every SQLSTATE, constraint name, message, count, digest,
 *    verdict and duration below is a member of the payload, printed. There is no branch in
 *    this file that produces a code, a name or a number that did not arrive over HTTP, and
 *    no default that would stand in for one. Where a member is absent the screen says
 *    "absent" in the payload's own vocabulary and prints nothing in its place.
 *
 * 2. **It reads the payload as `unknown` and narrows one member at a time.** The demo API
 *    owns `cr-gate-run.schema.json`; this console holds a verbatim copy of it and pins it
 *    against the original in both directions, but the operator entry deliberately does not
 *    carry the runtime validator (the console's read stack is out of this bundle by the
 *    byte ruling that governs it). So nothing here asserts a shape onto the response: a
 *    member that is the wrong type is treated exactly as a member that is missing, and the
 *    verbatim bytes are one click away either way.
 *
 * 3. **`persisted: false` is never re-stated as a claim.** The endpoint takes a fingerprint
 *    before the transaction opens and again after it closes and puts BOTH in the payload;
 *    what this module renders is those two readings side by side, with the ones that moved
 *    marked. The sentence "nothing persisted" is only ever on screen next to the readings
 *    it is a conclusion from, and if a reading DID move, the mark says so rather than the
 *    summary line swallowing it.
 *
 * 4. **A beat that did not raise is not a beat that passed.** `matched_expectation` is the
 *    payload's own field and is printed as it arrived. A run whose verdict is not `PROVEN`
 *    renders as not proven, with the payload's `failures` listed verbatim — saying so is
 *    the discipline, and a screen that quietly rendered four green rows would be the one
 *    fabrication this whole surface exists to make impossible.
 */

import { el, txt } from './ribbon';

/* ══ narrowing ═════════════════════════════════════════════════════════════════════ */

function record(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function str(row: Record<string, unknown>, key: string): string | null {
  const value = row[key];
  return typeof value === 'string' && value !== '' ? value : null;
}

function num(row: Record<string, unknown>, key: string): number | null {
  const value = row[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function bool(row: Record<string, unknown>, key: string): boolean | null {
  const value = row[key];
  return typeof value === 'boolean' ? value : null;
}

/** One line of the payload, printed the way JSON would print it. Never re-typed. */
function scalar(value: unknown): string | null {
  if (value === null) return 'null';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value === 'boolean') return String(value);
  return null;
}

/**
 * One beat of the run, as the payload carried it.
 *
 * The member names are the contract's. They are kept rather than renamed into console
 * vocabulary so that a judge reading the raw drawer beside this table is looking at the
 * same words in both places.
 */
export interface CrGateBeat {
  readonly ordinal: number | null;
  readonly name: string | null;
  readonly label: string | null;
  readonly outcome: string | null;
  readonly sqlstate: string | null;
  readonly constraint: string | null;
  readonly constraintSource: string | null;
  readonly message: string | null;
  readonly statement: string | null;
  readonly matchedExpectation: boolean | null;
  readonly elapsedMs: number | null;
  /** The beat's own sentence about what happened, when it carried one. */
  readonly note: string | null;
  /** `observed`, flattened — what the beat actually read, as it read it. */
  readonly observed: readonly (readonly [string, string])[];
  /** True when the beat carried a refusal payload of its own. Not a re-derivation. */
  readonly carriedRefusal: boolean;
}

/** One fingerprint reading, before the transaction and after it. */
export interface CrGateReading {
  /** The payload's own path to the value, e.g. `change_request/open_blocking`. */
  readonly name: string;
  readonly before: string;
  readonly after: string;
  /** `before !== after`. A comparison of two printed values, not a judgement. */
  readonly moved: boolean;
}

export interface CrGateRun {
  readonly runId: string | null;
  readonly generatedAt: string | null;
  readonly outcome: string | null;
  readonly verdict: string | null;
  readonly persisted: boolean | null;
  readonly elapsedMs: number | null;
  readonly failures: readonly string[];
  readonly beats: readonly CrGateBeat[];
  /** `persistence_check.before` against `persistence_check.after`, leaf by leaf. */
  readonly readings: readonly CrGateReading[];
  /** Every other member of `persistence_check`, flattened to `path → printed value`. */
  readonly persistenceMembers: readonly (readonly [string, string])[];
  /**
   * Every member of the run this module does not render above, flattened the same way.
   *
   * This is where the run's DECLARED ABSENCES land — the beat it did not play, the reason,
   * and the grant rows behind the reason — so they reach the screen as the payload's own
   * words rather than being filtered out by a renderer that only knew about the beats that
   * did run. A stated absence that nothing displays is a silent one.
   */
  readonly otherMembers: readonly (readonly [string, string])[];
}

/** Flatten an object to `path → printed scalar` pairs. Arrays keep their index. */
function leaves(
  value: unknown,
  prefix: string,
  out: Map<string, string>,
  depth = 0,
): Map<string, string> {
  if (depth > 4) return out;
  const printed = scalar(value);
  if (printed !== null) {
    out.set(prefix, printed);
    return out;
  }
  if (Array.isArray(value)) {
    // A list of scalars is printed as one line rather than one line per index. Nothing is
    // dropped and nothing is summarised — the items are joined, in order, exactly as they
    // arrived — but a ten-table list stops costing ten rows in a panel a judge has to read.
    const items = value.map(scalar);
    if (items.every((item) => item !== null)) {
      out.set(prefix, items.join(', '));
      return out;
    }
    value.forEach((item, index) => leaves(item, `${prefix}/${String(index)}`, out, depth + 1));
    return out;
  }
  const row = record(value);
  if (row === null) return out;
  for (const key of Object.keys(row).sort()) {
    leaves(row[key], prefix === '' ? key : `${prefix}/${key}`, out, depth + 1);
  }
  return out;
}

function readBeat(value: unknown): CrGateBeat | null {
  const row = record(value);
  if (row === null) return null;
  return {
    ordinal: num(row, 'ordinal'),
    name: str(row, 'name'),
    label: str(row, 'label'),
    outcome: str(row, 'outcome'),
    sqlstate: str(row, 'sqlstate'),
    constraint: str(row, 'constraint'),
    constraintSource: str(row, 'constraint_source'),
    message: str(row, 'message'),
    statement: str(row, 'statement'),
    matchedExpectation: bool(row, 'matched_expectation'),
    elapsedMs: num(row, 'elapsed_ms'),
    note: str(row, 'note'),
    observed: [...leaves(row.observed, '', new Map())].map(
      ([name, value]) => [name, value] as const,
    ),
    carriedRefusal: record(row.refusal) !== null,
  };
}

/** Members this module renders explicitly; everything else is listed as it arrived. */
const RUN_KEYS = new Set([
  'run_id',
  'generated_at',
  'outcome',
  'verdict',
  'persisted',
  'elapsed_ms',
  'failures',
  'beats',
  'persistence_check',
]);

/**
 * Narrow a `POST /v1/demo/cr-gate-run` payload.
 *
 * Returns `null` when what arrived is not a run at all — a problem body, an empty body, a
 * different resource — so a caller can never mistake "we could not read it" for "the run
 * carried no beats". The distinction is the whole of rule 1 above.
 */
export function readCrGateRun(data: unknown): CrGateRun | null {
  const row = record(data);
  if (row === null) return null;
  const beatsRaw = row.beats;
  if (!Array.isArray(beatsRaw)) return null;

  const beats: CrGateBeat[] = [];
  for (const item of beatsRaw) {
    const beat = readBeat(item);
    if (beat !== null) beats.push(beat);
  }

  const failures: string[] = [];
  const failuresRaw = row.failures;
  if (Array.isArray(failuresRaw)) {
    for (const item of failuresRaw) {
      const printed = scalar(item);
      if (printed !== null) failures.push(printed);
    }
  }

  const readings: CrGateReading[] = [];
  const persistenceMembers: (readonly [string, string])[] = [];
  const check = record(row.persistence_check);
  if (check !== null) {
    const before = leaves(check.before, '', new Map());
    const after = leaves(check.after, '', new Map());
    for (const name of [...new Set([...before.keys(), ...after.keys()])].sort()) {
      const b = before.get(name) ?? 'absent';
      const a = after.get(name) ?? 'absent';
      readings.push({ name, before: b, after: a, moved: b !== a });
    }
    // Every other member, flattened rather than filtered. `tables`, `subject_tables` and
    // `self_evidence` are a list and an object, and a renderer that only printed scalars
    // would silently drop exactly the members that say WHICH tables the claim covers.
    for (const key of Object.keys(check).sort()) {
      if (key === 'before' || key === 'after') continue;
      for (const [name, value] of leaves(check[key], key, new Map())) {
        persistenceMembers.push([name, value] as const);
      }
    }
  }

  // Same treatment for the run's own remaining members, and it is the reason the declared
  // ABSENCES reach the screen: `admission_beat: null` with its reason and the grant rows
  // behind it, and the kernel-procedure beat that was dropped with the SQLSTATE that caused
  // the drop. Those are the payload saying what it did NOT play, and dropping them here
  // would turn a stated absence back into a silent one.
  const otherMembers: (readonly [string, string])[] = [];
  for (const key of Object.keys(row).sort()) {
    if (RUN_KEYS.has(key)) continue;
    for (const [name, value] of leaves(row[key], key, new Map())) {
      otherMembers.push([name, value] as const);
    }
  }

  return {
    runId: str(row, 'run_id'),
    generatedAt: str(row, 'generated_at'),
    outcome: str(row, 'outcome'),
    verdict: str(row, 'verdict'),
    persisted: bool(row, 'persisted'),
    elapsedMs: num(row, 'elapsed_ms'),
    failures,
    beats,
    readings,
    persistenceMembers,
    otherMembers,
  };
}

/** True exactly when the payload says the transaction was left undecided. Never a refusal. */
export function isUndecided(run: CrGateRun): boolean {
  return run.outcome === 'retry';
}

/* ══ rendering ═════════════════════════════════════════════════════════════════════ */

function cell(row: HTMLElement, className: string, value: string | null, absent: string): void {
  if (value === null) {
    row.append(el('td', className, el('span', 'moc-absent-inline', absent)));
    return;
  }
  row.append(el('td', className, value));
}

/**
 * The beats, one row each, with the SQLSTATE and the constraint name the DRIVER reported.
 *
 * `constraint_source` is printed beside the constraint on purpose. A name parsed out of an
 * error message and a name the driver's diagnostics carried are two different qualities of
 * evidence, and a table that showed only the name would let a reader assume the stronger
 * one. The payload distinguishes them; so does this.
 */
function renderBeats(beats: readonly CrGateBeat[]): HTMLElement {
  const scroll = el('div', 'moc-scroll');
  const table = el('table', 'moc-table');
  const caption = el('caption');
  caption.append(
    document.createTextNode(
      'The beats this run played, in payload order. Every SQLSTATE and constraint name below ' +
        'is the one the driver reported for that statement — none is written in this page.',
    ),
  );
  table.append(caption);

  const thead = el('thead');
  const headRow = el('tr');
  for (const heading of [
    '#',
    'beat',
    'outcome',
    'sqlstate',
    'constraint',
    'reported by',
    'matched expectation',
    'elapsed_ms',
  ]) {
    headRow.append(el('th', undefined, heading));
  }
  thead.append(headRow);
  table.append(thead);

  const tbody = el('tbody');
  for (const beat of beats) {
    const tr = el('tr');
    cell(tr, 'moc-num', beat.ordinal === null ? null : String(beat.ordinal), '—');
    cell(tr, 'moc-kind', beat.label ?? beat.name, 'unnamed');
    cell(tr, 'moc-kind', beat.outcome, 'no outcome');
    cell(tr, 'moc-kind', beat.sqlstate, 'none');
    cell(tr, 'moc-kind', beat.constraint, 'none');
    cell(tr, 'moc-kind', beat.constraintSource, 'not stated');
    cell(
      tr,
      'moc-kind',
      beat.matchedExpectation === null ? null : String(beat.matchedExpectation),
      'not stated',
    );
    cell(tr, 'moc-num', beat.elapsedMs === null ? null : String(beat.elapsedMs), '—');
    tbody.append(tr);
  }
  table.append(tbody);
  scroll.append(table);
  return scroll;
}

/** The statement a beat ran and the message it came back with, verbatim. */
function renderBeatDetail(beat: CrGateBeat): HTMLElement {
  const wrap = el('div', 'moc-beat');
  wrap.append(el('p', 'moc-label', beat.label ?? beat.name ?? 'beat'));
  if (beat.statement !== null) {
    wrap.append(el('pre', 'moc-raw', beat.statement));
  } else {
    wrap.append(el('p', 'moc-absent', 'This beat carried no statement text in the payload.'));
  }
  if (beat.message !== null) {
    wrap.append(el('p', 'moc-quote', beat.message));
  }
  if (beat.note !== null) {
    wrap.append(txt(beat.note));
  }
  for (const [name, value] of beat.observed) {
    const line = el('p', 'moc-exchange');
    line.append(document.createTextNode(`${name} = `));
    line.append(el('code', 'moc-db', value));
    wrap.append(line);
  }
  const provenance = beat.carriedRefusal
    ? 'The database attached a refusal payload to this beat — the reason set, not a message ' +
      'this page composed.'
    : 'No refusal payload was attached to this beat.';
  wrap.append(txt(provenance));
  return wrap;
}

/**
 * The persistence proof: two readings and the arithmetic between them.
 *
 * This is the panel that makes `persisted: false` checkable rather than assertable. Both
 * columns are in the response; the third is `before !== after` computed here on two strings
 * that both arrived, and it is labelled as this browser's comparison of the payload's own
 * numbers.
 */
function renderPersistence(run: CrGateRun): HTMLElement {
  const wrap = el('div');

  if (run.readings.length === 0) {
    wrap.append(
      el(
        'p',
        'moc-absent',
        'This payload carried no before/after fingerprint, so nothing on this screen supports ' +
          'a claim about what the run did or did not leave behind. The verbatim bytes are below.',
      ),
    );
    return wrap;
  }

  const scroll = el('div', 'moc-scroll');
  const table = el('table', 'moc-table');
  const caption = el('caption');
  caption.append(
    document.createTextNode(
      'The fingerprint the endpoint took before the transaction opened, beside the one it took ' +
        'after the transaction closed. Both columns are in the response.',
    ),
  );
  table.append(caption);

  const thead = el('thead');
  const headRow = el('tr');
  for (const heading of ['reading', 'before', 'after', 'moved']) {
    headRow.append(el('th', undefined, heading));
  }
  thead.append(headRow);
  table.append(thead);

  const tbody = el('tbody');
  for (const reading of run.readings) {
    const tr = el('tr');
    tr.append(el('td', 'moc-kind', reading.name));
    tr.append(el('td', 'moc-num', reading.before));
    tr.append(el('td', 'moc-num', reading.after));
    tr.append(el('td', 'moc-kind', reading.moved ? 'MOVED' : 'no'));
    if (reading.moved) tr.className = 'moc-moved';
    tbody.append(tr);
  }
  table.append(tbody);
  scroll.append(table);
  wrap.append(scroll);

  const moved = run.readings.filter((reading) => reading.moved);
  wrap.append(
    txt(
      moved.length === 0
        ? 'No reading in the fingerprint moved. The "moved" column is this browser comparing the ' +
            'two columns beside it; the columns themselves are the endpoint’s measurements.'
        : `${String(moved.length)} reading${moved.length === 1 ? '' : 's'} moved between the two ` +
            'fingerprints, and the rows are marked. That is shown rather than summarised away.',
    ),
  );

  for (const [name, value] of run.persistenceMembers) {
    const line = el('p', 'moc-exchange');
    line.append(document.createTextNode(`persistence_check.${name} = `));
    line.append(el('code', 'moc-db', value));
    wrap.append(line);
  }
  return wrap;
}

export interface CrGateRunView {
  /** The narrowed run, or `null` when the response was not a run. */
  readonly run: CrGateRun | null;
  /** The verbatim request line the response arrived on. */
  readonly line: string;
  /** The verbatim response bytes. Rendered whole, never re-serialised. */
  readonly raw: string;
  /** The HTTP status, as observed. */
  readonly status: number;
}

/**
 * Render one attempt, whatever it turned out to be.
 *
 * Four different sentences, and they are four different things:
 *   • no run came back — the bytes are shown and nothing is claimed;
 *   • the transaction was left undecided (`retry`) — **not** a refusal, and it does not get
 *     a refusal's chrome, because "the database said no" and "the database said ask me
 *     again" are different answers and only one of them is this demo's point;
 *   • the run completed and proved what it was written against;
 *   • the run completed and something did not hold — the payload's own `failures`, listed.
 */
export function renderCrGateRun(view: CrGateRunView): HTMLElement {
  const wrap = el('section', 'moc-run');
  wrap.setAttribute('aria-label', 'Change-request gate run');

  const { run } = view;
  if (run === null) {
    wrap.append(
      el(
        'p',
        'moc-absent',
        `The attempt returned ${String(view.status)}, and the body is not a gate run this page ` +
          'can read. Nothing is rendered in its place; the bytes are below exactly as they arrived.',
      ),
    );
    wrap.append(txt(view.line, 'moc-exchange'));
    wrap.append(el('pre', 'moc-raw', view.raw));
    return wrap;
  }

  const headline = el('p', 'moc-verdict');
  if (isUndecided(run)) {
    headline.append(
      document.createTextNode('The transaction was left undecided. Outcome '),
      el('code', 'moc-db', run.outcome ?? 'retry'),
      document.createTextNode(
        '. That is not a refusal — an undecided transaction has no reason set — so no ' +
          'constraint is claimed here. Press again if you want another attempt; nothing ' +
          'in this page re-sends on its own.',
      ),
    );
  } else {
    headline.append(document.createTextNode('verdict '));
    headline.append(el('code', 'moc-db', run.verdict ?? 'not stated'));
    headline.append(document.createTextNode(' · outcome '));
    headline.append(el('code', 'moc-db', run.outcome ?? 'not stated'));
    headline.append(document.createTextNode(' · persisted '));
    headline.append(
      el('code', 'moc-db', run.persisted === null ? 'not stated' : String(run.persisted)),
    );
  }
  wrap.append(headline);

  if (run.failures.length > 0) {
    const list = el('ul', 'moc-routes');
    for (const failure of run.failures) {
      list.append(el('li', 'moc-route moc-route-missing', failure));
    }
    wrap.append(el('p', 'moc-label', 'What the run says did not hold, in its own words'));
    wrap.append(list);
  }

  if (run.beats.length > 0) {
    wrap.append(renderBeats(run.beats));
    for (const beat of run.beats) {
      if (beat.outcome === 'refused' || beat.message !== null) {
        wrap.append(renderBeatDetail(beat));
      }
    }
  } else {
    wrap.append(el('p', 'moc-absent', 'The payload carried no beats, so none is shown.'));
  }

  wrap.append(el('p', 'moc-label', 'What the run left behind'));
  wrap.append(renderPersistence(run));

  for (const [name, value] of run.otherMembers) {
    const line = el('p', 'moc-exchange');
    line.append(document.createTextNode(`${name} = `));
    line.append(el('code', 'moc-db', value));
    wrap.append(line);
  }

  const identity = el('p', 'moc-exchange');
  identity.append(document.createTextNode('run_id '));
  identity.append(el('code', 'moc-db', run.runId ?? 'not stated'));
  if (run.generatedAt !== null) {
    identity.append(document.createTextNode(' · generated_at '));
    identity.append(el('code', 'moc-db', run.generatedAt));
  }
  if (run.elapsedMs !== null) {
    identity.append(document.createTextNode(' · elapsed_ms '));
    identity.append(el('code', 'moc-db', String(run.elapsedMs)));
  }
  wrap.append(identity);
  wrap.append(txt(view.line, 'moc-exchange'));

  const raw = el('pre', 'moc-raw', view.raw);
  raw.setAttribute('aria-label', 'verbatim cr-gate-run response body');
  wrap.append(raw);
  return wrap;
}
