// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE REFUSAL, AS AN OPERATIONS SYSTEM WOULD SHOW IT.
 *
 * R15. A **banner over a locked action**, never a modal. Not one vendor source in the
 * control-of-work market describes a modal dialog for a blocked submission; several
 * describe locking progress and listing the reasons beside it (r3-operator §2.5). A modal
 * reads as a website. A banner over a disabled ISSUE button, with the obligation card
 * still visible behind it, reads as the system a supervisor actually works in — and it is
 * the shape that keeps the reason legible while the refusal is on screen.
 *
 * TWO STACKED REGISTERS, and the second is what makes the first believable:
 *
 *   the supervisor's sentence   — the permit was not issued, what is outstanding, and
 *                                 which precursor has never been answered for this permit
 *   the database's own words    — SQLSTATE, constraint name, how that name was obtained,
 *                                 the CHECK predicate, the statement, the message
 *
 * EVERY VALUE IN THE SECOND REGISTER IS COPIED OUT OF THE BEAT PAYLOAD. There is no
 * SQLSTATE, no constraint name and no message text written down in this file; a unit test
 * greps this directory for them. Where the payload does not carry something — the relation
 * a reported CHECK was declared on, a nearest admissible alternative — this banner prints
 * the absence and how it knows, which is the only honest alternative to a plausible guess.
 *
 * TWO BEATS, TWO TEMPERATURES.
 *
 *   **Beat 2 is filmed calm.** A CHECK constraint refusing a write is table stakes; every
 *   database on earth can do it. If it is staged as the climax, the demo peaks early on
 *   the least differentiated claim we own. It renders in the quiet register.
 *
 *   **Beat 3 is the peak.** The projected counter now reads zero — somebody falsified the
 *   number the gate reads — and the merge is refused ANYWAY, because the gate re-derived
 *   the count from the obligations instead of trusting the column. That is the difference
 *   between a checkbox and a control. And its own DIAGNOSIS is weaker, not stronger: the
 *   exhibit was `parsed` out of the message rather than reported by the driver, and the
 *   engine could not compute a nearest admissible alternative. Both are rendered as
 *   plainly as the refusal itself. A system that reports what it cannot compute, on its
 *   best refusal, is telling you what kind of system it is.
 *
 * `renderRefusalBanner` returns **null** for anything that is not a refusal — an absent
 * beat, the read, the admission, and in particular an UNDECIDED transaction (40001), which
 * carries no refusal payload and gets `renderUndecidedNotice` instead.
 */

import {
  checkPredicate,
  counterForge,
  exhibitIsWeakened,
  formatMs,
  nearestAdmissible,
  observedOutstanding,
  outstandingLine,
  precursorEvents,
  raisedBy,
  reasonAtomLine,
  reasonSet,
  type BeatView,
  type RunReading,
} from './beats';

export interface RefusalBannerOptions {
  /**
   * How many refusals are already on screen. Zero renders "PERMIT NOT ISSUED"; anything
   * above renders "PERMIT STILL NOT ISSUED", which is the sentence beat 3 earns.
   */
  readonly priorRefusals: number;
  /**
   * A human-readable reference for the precursor, IF a real read supplied one. Absent by
   * default: the refusal's reason set carries event identifiers, not external references,
   * and inventing a reference here would be a fabricated exhibit.
   */
  readonly precursorLabel?: string | undefined;
}

// ───────────────────────────────────────────────────────────────────────────────────────
// The banner
// ───────────────────────────────────────────────────────────────────────────────────────

export function renderRefusalBanner(
  beat: BeatView | null | undefined,
  options: RefusalBannerOptions,
): HTMLElement | null {
  // No beat, or a beat the database did not refuse. A read, an admission, an undecided
  // transaction and a skipped beat all land here and all render NOTHING. A banner that
  // appears for a non-refusal is a fabricated refusal, whatever it says inside.
  if (beat === null || beat === undefined) return null;
  if (!beat.isRefusal) return null;

  const forge = counterForge(beat);
  const banner = section('cow-refusal', {
    beat: beat.name,
    ordinal: String(beat.ordinal),
    outcome: beat.outcome,
    emphasis: forge === null ? 'calm' : 'peak',
  });
  banner.setAttribute('role', 'alert');
  if (beat.sqlstate !== null) banner.dataset.sqlstate = beat.sqlstate;

  banner.append(operatorRegister(beat, forge, options));
  banner.append(databaseRegister(beat));
  return banner;
}

/** Register one: what the supervisor is being told, in the supervisor's own language. */
function operatorRegister(
  beat: BeatView,
  forge: ReturnType<typeof counterForge>,
  options: RefusalBannerOptions,
): HTMLElement {
  const box = div('cow-refusal__operator');

  const headline = document.createElement('p');
  headline.className = 'cow-refusal__headline';
  headline.textContent = options.priorRefusals > 0 ? 'PERMIT STILL NOT ISSUED' : 'PERMIT NOT ISSUED';
  box.append(headline);

  const facts = document.createElement('ul');
  facts.className = 'cow-refusal__facts';

  if (forge === null) {
    // Beat 2, calm. The count comes from what the beat observed, or from the size of the
    // refusal's own reason set — never from a constant.
    const outstanding = observedOutstanding(beat) ?? obligationAtomCount(beat);
    facts.append(li(outstandingLine(outstanding)));
    for (const sentence of precursorSentences(beat, options.precursorLabel)) {
      facts.append(li(sentence));
    }
  } else {
    // Beat 3, the peak. Every number below is the payload's.
    facts.append(li(`The outstanding-obligation counter now reads ${forge.forcedTo}.`));
    facts.append(li('The permit was refused anyway.'));
    if (forge.derived !== null) {
      facts.append(
        li(
          'The gate did not trust the counter. It counted again, from the obligations ' +
            `themselves, and got ${forge.derived}.`,
        ),
      );
    }
    if (forge.attack !== null) {
      const attack = li(forge.attack);
      attack.className = 'cow-refusal__verbatim';
      facts.append(attack);
    }
  }

  box.append(facts);
  return box;
}

/** Register two: the database's own words, copied. */
function databaseRegister(beat: BeatView): HTMLElement {
  const box = div('cow-refusal__database');

  const lead = document.createElement('p');
  lead.className = 'cow-refusal__register';
  lead.textContent = 'The database refused this write. Everything below is what it returned.';
  box.append(lead);

  const rows = document.createElement('dl');
  rows.className = 'cow-refusal__rows';

  if (beat.sqlstate !== null) row(rows, 'SQLSTATE', code(beat.sqlstate), 'sqlstate');

  if (beat.constraint !== null) {
    const cell = div('cow-refusal__cell');
    cell.append(code(beat.constraint));
    if (beat.constraintSource !== null) {
      cell.append(chip(beat.constraintSource));
    }
    if (exhibitIsWeakened(beat)) {
      // The contract's own words for what `parsed` costs. A run whose exhibits were
      // recovered from a sentence must never look like a run whose exhibits were reported.
      cell.append(
        note(
          'Recovered from the message text rather than reported by the driver — a weakened ' +
            'diagnosis, and it is labelled as one.',
        ),
      );
    }
    row(rows, 'constraint', cell, 'constraint');
  }

  const predicate = checkPredicate(beat.message);
  if (predicate !== null) {
    const cell = div('cow-refusal__cell');
    cell.append(code(predicate.text));
    cell.append(note(`Read out of the ${predicate.from} below; no field carries it.`));
    row(rows, 'CHECK predicate', cell, 'predicate');
  }

  const source = raisedBy(beat);
  const sourceCell = div('cow-refusal__cell');
  if (source === null) {
    // The honest answer to "which table did this come from". See beats.ts raisedBy().
    sourceCell.append(
      note(
        'Not named in this payload. This refusal carries the constraint’s name, not the ' +
          'relation it was declared on. The statement below names the objects the beat addressed.',
      ),
    );
  } else {
    sourceCell.append(code(source.object));
    sourceCell.append(chip(source.how === 'constraint_field' ? 'from the exhibit' : 'from the message'));
  }
  row(rows, 'raised by', sourceCell, 'raised-by');

  if (beat.statement !== null) row(rows, 'statement', code(beat.statement), 'statement');
  if (beat.message !== null) row(rows, 'message', code(beat.message), 'message');

  const refusal = beat.refusal;
  if (refusal !== null) {
    const diagnosis = div('cow-refusal__cell');
    diagnosis.append(code(refusal.diagnosis));
    diagnosis.append(chip(`${refusal.probe_calls} probe calls`));
    row(rows, 'diagnosis', diagnosis, 'diagnosis');

    const atoms = reasonSet(refusal);
    if (atoms.length > 0) {
      const list = document.createElement('ul');
      list.className = 'cow-refusal__atoms';
      for (const atom of atoms) list.append(li(reasonAtomLine(atom)));
      row(rows, 'reason set', list, 'mus');
    }

    const alternative = nearestAdmissible(refusal);
    if (alternative !== null) {
      const cell = div('cow-refusal__cell');
      if (alternative.kind === 'computed') {
        cell.append(text(alternative.naa.description));
        cell.append(chip(alternative.naa.kind));
      } else {
        // Beat 3 lands here. The engine that produced the refusal says it cannot compute
        // the nearest admissible alternative, and names its reason. Rendered plainly.
        cell.append(text('NOT COMPUTABLE for this refusal.'));
        if (alternative.reason !== null) cell.append(chip(alternative.reason));
      }
      row(rows, 'nearest admissible alternative', cell, 'naa');
    }

    row(rows, 'gate_epoch', code(String(refusal.gate_epoch)), 'gate-epoch');
    row(rows, 'refusal_id', code(refusal.refusal_id), 'refusal-id');
  }

  const timing = div('cow-refusal__cell');
  timing.append(code(formatMs(beat.elapsedMs)));
  timing.append(note('Measured by the server for this beat — not a reveal delay.'));
  row(rows, 'elapsed', timing, 'elapsed');

  if (!beat.matchedExpectation) {
    const cell = div('cow-refusal__cell');
    cell.append(text(`Expected ${beat.expectedOutcome}; observed ${beat.outcome}.`));
    if (beat.note !== null) cell.append(note(beat.note));
    row(rows, 'DID NOT MATCH EXPECTATION', cell, 'unmatched');
  }

  box.append(rows);
  return box;
}

/**
 * The precursor sentence, built only from what the reason set names.
 *
 * If a caller supplied a reference obtained from a real read it is used; otherwise the
 * event identifier the refusal itself carries is shown. If the reason set names no event,
 * no sentence is produced — the screen does not assert a precursor it cannot point at.
 */
function precursorSentences(beat: BeatView, label: string | undefined): readonly string[] {
  const events = precursorEvents(beat.refusal);
  if (events.length === 0) return [];
  if (label !== undefined && label.length > 0 && events.length === 1) {
    return [`${label} has never been answered for this permit.`];
  }
  return events.map((id) => `Precursor event ${id} has never been answered for this permit.`);
}

function obligationAtomCount(beat: BeatView): number | null {
  const atoms = reasonSet(beat.refusal).filter((atom) => atom.kind === 'obligation');
  return atoms.length === 0 ? null : atoms.length;
}

// ───────────────────────────────────────────────────────────────────────────────────────
// The undecided transaction — which is NOT a refusal and is never dressed as one
// ───────────────────────────────────────────────────────────────────────────────────────

/**
 * SQLSTATE 40001: the transaction was rolled back UNDECIDED.
 *
 * `spec/wire/refusal.schema.json` excludes that code from its enum on purpose — an
 * undecided transaction has no reason set, so there is nothing to refuse WITH. The HTTP
 * status is 503, never 409, and this notice says so.
 *
 * **There is no auto-retry here and there will not be one.** A helper that re-sent a merge
 * because a socket closed is a helper that can issue a permit twice. The button is offered
 * back to the operator; a caller pressing it again is a decision with an author.
 */
export function renderUndecidedNotice(reading: RunReading): HTMLElement | null {
  if (reading.kind !== 'undecided') return null;

  const box = section('cow-undecided', { outcome: reading.run.outcome });
  box.setAttribute('role', 'status');

  const headline = document.createElement('p');
  headline.className = 'cow-undecided__headline';
  headline.textContent = 'NOT DECIDED — the permit was neither issued nor refused.';
  box.append(headline);

  const said = document.createElement('p');
  said.className = 'cow-undecided__body';
  said.textContent =
    'The transaction was rolled back before it reached a verdict, so there is no refusal ' +
    'to show: an undecided transaction has no reason set. Nothing was written. Pressing ' +
    'ISSUE again sends a new transaction, and that is your decision to make.';
  box.append(said);

  const rows = document.createElement('dl');
  rows.className = 'cow-refusal__rows';
  if (reading.retrySqlstate !== null) row(rows, 'SQLSTATE', code(reading.retrySqlstate), 'sqlstate');
  row(rows, 'HTTP', code(String(reading.httpStatus)), 'http');
  row(rows, 'transaction', code(reading.run.transaction.disposition), 'disposition');
  box.append(rows);

  return box;
}

// ───────────────────────────────────────────────────────────────────────────────────────
// DOM helpers. Deliberately tiny; this entry imports no framework (R1).
// ───────────────────────────────────────────────────────────────────────────────────────

function section(className: string, data: Readonly<Record<string, string>>): HTMLElement {
  const element = document.createElement('section');
  element.className = className;
  for (const [key, value] of Object.entries(data)) element.dataset[key] = value;
  return element;
}

function div(className: string): HTMLElement {
  const element = document.createElement('div');
  element.className = className;
  return element;
}

function li(content: string): HTMLLIElement {
  const element = document.createElement('li');
  element.textContent = content;
  return element;
}

function code(content: string): HTMLElement {
  const element = document.createElement('code');
  element.className = 'cow-refusal__value';
  element.textContent = content;
  return element;
}

function chip(content: string): HTMLElement {
  const element = document.createElement('span');
  element.className = 'cow-refusal__chip';
  element.textContent = content;
  return element;
}

function note(content: string): HTMLElement {
  const element = document.createElement('p');
  element.className = 'cow-refusal__note';
  element.textContent = content;
  return element;
}

function text(content: string): HTMLElement {
  const element = document.createElement('p');
  element.className = 'cow-refusal__text';
  element.textContent = content;
  return element;
}

function row(list: HTMLElement, label: string, value: HTMLElement, key: string): void {
  const term = document.createElement('dt');
  term.textContent = label;
  term.dataset.row = key;
  const detail = document.createElement('dd');
  detail.dataset.row = key;
  detail.append(value);
  list.append(term, detail);
}
