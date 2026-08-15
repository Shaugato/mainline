// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * (1) THE REFUSAL BAR — the money band, and the strictest component in the console.
 *
 * `docs/leads/ui.md` D18: refusals are rendered from `spec/wire/refusal.md` payloads
 * ONLY — constraint, SQLSTATE, minimal unsatisfiable subset, nearest admissible
 * alternative — never from a message the console composes. A prettified refusal is a
 * different refusal.
 *
 * Four rules this file makes structural rather than remembered:
 *
 *   • **There is no prop for a message.** The only prose this component can emit is
 *     about the ABSENCE of a refusal or about a defect in the payload; there is nowhere
 *     to put a sentence about a record.
 *   • **The SQLSTATE is never translated.** `Sqlstate` reports the expectation class
 *     from `spec/errors.md`'s closed taxonomy, which is a fact about the CODE. The human
 *     meaning is a fact about the refusal, and the refusal carries its own words in
 *     `message`, rendered verbatim in mono.
 *   • **A refusal the payload did not contain is never rendered.** `readRefusal`
 *     narrows; a payload missing a required field lands in the `defect` state naming the
 *     field. `spec/wire/refusal.md` C-5 — a fabricated payload is the worst artefact
 *     this system could emit.
 *   • **`constraint_source: "parsed"` is announced as a weakened diagnosis** (C-4). The
 *     constraint name was recovered from message text rather than reported by the
 *     driver, and a reader must not have to know that to know it.
 *
 * The `none` state is not an empty state. Before anything has been attempted the
 * database has refused nothing, and saying so is a stronger claim than a blank band:
 * this screen shows refusals that happened, and only those.
 *
 * ── `constraint_source` IS AN EXHIBIT, NOT ONLY A WARNING (R7) ────────────────────
 *
 * The band used to render `constraint_source` only when it was `parsed`, as the weakened
 * notice below. A reader of a REPORTED refusal therefore had no way to see that it was
 * reported — the strongest thing this payload says about its own constraint name was
 * legible only by its absence. `docs/leads/demo-story-plan.md` R7 requires the band to
 * show *the constraint, the SQLSTATE and the `constraint_source`*, so the value is now a
 * fact of its own, rendered verbatim in all three of its states:
 *
 *   `reported`  the driver's diagnostics carried the name.
 *   `parsed`    it was recovered from the message text — the weakened notice still fires.
 *   *absent*    the emitter stated neither. `spec/wire/refusal.md` makes the member
 *               optional, and an absent member is NOT `reported`: it is rendered as
 *               undeclared, because the alternative is this console upgrading a silence
 *               into the stronger of the two claims.
 *
 * ── WHY THERE IS A SCOPE ─────────────────────────────────────────────────────────
 *
 * A four-beat gate run refuses TWICE — once on ancestry and once after the projected
 * counter was forged — and both belong on the screen, so one page can carry more than one
 * band. `scope` suffixes this component's test identifiers so two bands are addressable
 * apart. It defaults to `null`, which renders every identifier exactly as it renders
 * today; the primary band never passes one.
 */

import { type ReactNode } from 'react';

import {
  ConstraintName,
  Digest,
  Disclosure,
  Gloss,
  Mono,
  Sqlstate,
} from '../../design/primitives';

import styles from './gate.module.css';
import { ProvenanceSlot } from './ProvenanceSlot';
import type { ProvenanceEntry } from './provenance';
import type { RefusalPayload } from '../../data/types.generated';

export type RefusalBarState =
  /** Nothing has been attempted. The database has refused nothing. */
  | { readonly kind: 'none' }
  /** A transition is in flight. */
  | { readonly kind: 'attempting' }
  /** The transition COMMITTED. The gate opened; this screen says so plainly. */
  | { readonly kind: 'committed'; readonly mergedCommit: string | null }
  /** SQLSTATE 40001 — an UNDECIDED transaction. Not a refusal, and it has no reason set. */
  | { readonly kind: 'retry' }
  /** The database refused, and this is the payload it emitted. */
  | { readonly kind: 'refused'; readonly refusal: RefusalPayload }
  /** A refusal arrived that this console cannot read verbatim. */
  | { readonly kind: 'defect'; readonly reason: string }
  /** The exchange did not complete. Not a refusal; the transport's own words. */
  | { readonly kind: 'failed'; readonly failure: string; readonly detail: string };

export interface RefusalBarProps {
  readonly state: RefusalBarState;
  /** The invoke envelope's `provenance` list, for the chips beside the verbatim values. */
  readonly provenance: readonly ProvenanceEntry[] | undefined;
  /**
   * Suffix for this band's test identifiers, when a page carries more than one band.
   * `null` — the default, and what the primary band always passes — leaves every
   * identifier byte-identical to what it was before this prop existed.
   */
  readonly scope?: string | null;
}

function Fact({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}): ReactNode {
  return (
    <span className={styles.fact}>
      <span className={styles.label}>{label}</span>
      {children}
    </span>
  );
}

export function RefusalBar({ state, provenance, scope = null }: RefusalBarProps): ReactNode {
  /** Identifiers are unchanged when unscoped; a second band on the page gets its own. */
  const id = (name: string): string => (scope === null ? name : `${name}-${scope}`);

  if (state.kind === 'none') {
    return (
      <section
        className={styles.refusalBar}
        data-state="none"
        data-testid={id('refusal-bar')}
        aria-label="Refusal"
      >
        <span className={styles.refusalKicker}>no attempt — nothing has been refused</span>
        <p className={styles.prose}>
          This band shows a refusal only after the database has issued one. No merge has been
          attempted against this subject in this session, so there is no constraint name, no
          SQLSTATE and no reason set to show — and the console will not predict one.
        </p>
      </section>
    );
  }

  if (state.kind === 'attempting') {
    return (
      <section
        className={styles.refusalBar}
        data-state="attempting"
        data-testid={id('refusal-bar')}
        aria-label="Refusal"
        aria-busy="true"
      >
        <span className={styles.refusalKicker}>attempting the transition…</span>
      </section>
    );
  }

  if (state.kind === 'committed') {
    return (
      <section
        className={styles.refusalBar}
        data-state="committed"
        data-testid={id('refusal-bar')}
        aria-label="Refusal"
      >
        <span className={styles.refusalKicker}>committed — the gate was open</span>
        <p className={styles.prose}>
          The database accepted the transition. Nothing was refused, so there is no reason set on
          this screen.
        </p>
        {state.mergedCommit === null ? null : (
          <Digest value={state.mergedCommit} label="merged commit" />
        )}
      </section>
    );
  }

  if (state.kind === 'retry') {
    return (
      <section
        className={styles.refusalBar}
        data-state="retry"
        data-testid={id('refusal-bar')}
        aria-label="Refusal"
      >
        <span className={styles.refusalKicker}>undecided — SQLSTATE 40001</span>
        <p className={styles.prose}>
          A serialisation conflict left the transaction UNDECIDED. That is not a refusal: it has no
          constraint name and no reason set, and the console offers no automatic retry — pressing
          the control again is a decision with an author.
        </p>
      </section>
    );
  }

  if (state.kind === 'defect') {
    return (
      <section
        className={styles.refusalBar}
        data-state="defect"
        data-testid={id('refusal-bar')}
        role="alert"
        aria-label="Refusal"
      >
        <span className={styles.refusalKicker}>unreadable refusal payload</span>
        <p className={styles.prose}>
          The kernel reported a refusal, but the payload does not satisfy the shape
          <Mono> spec/wire/refusal.md</Mono> §2 requires, so this console will not render it as a
          refusal. Verbatim reason:
        </p>
        <pre className={styles.refusalMessage}>{state.reason}</pre>
      </section>
    );
  }

  if (state.kind === 'failed') {
    return (
      <section
        className={styles.refusalBar}
        data-state="failed"
        data-testid={id('refusal-bar')}
        role="alert"
        aria-label="Refusal"
      >
        <span className={styles.refusalKicker}>
          exchange failed — <Mono>{state.failure}</Mono>
        </span>
        <p className={styles.prose}>
          The attempt did not reach a verdict. This is a transport failure, not a refusal: nothing
          about the gate follows from it.
        </p>
        <pre className={styles.refusalMessage}>{state.detail}</pre>
      </section>
    );
  }

  const { refusal } = state;
  const parsed = refusal.constraint_source === 'parsed';

  return (
    <section
      className={styles.refusalBar}
      data-state="refused"
      data-testid={id('refusal-bar')}
      data-constraint={refusal.constraint}
      data-sqlstate={refusal.sqlstate}
      data-constraint-source={refusal.constraint_source ?? 'undeclared'}
      role="alert"
      aria-label="Refusal"
    >
      <span className={styles.refusalKicker}>
        the database refused this transition, by name
      </span>

      <div className={styles.refusalHead}>
        {/*
          R8: the gloss goes BESIDE the exact string, never instead of it and never
          inside the same element. `ConstraintName` and `Sqlstate` render the database's
          own words, verbatim, in the mono face; `Gloss` sets the console's sentence next
          to them in the sans face, so a reader can see at a glance which words are
          whose. The SQLSTATE gloss is a lookup in the closed table `design/glossary.ts`
          holds — it says what the CODE names, and an unmodelled code gets no sentence
          rather than an invented one.
        */}
        <span className={styles.refusalConstraintSlot}>
          <Gloss term="constraint" layout="stack" data-testid={id('gloss-constraint')}>
            <ConstraintName
              name={refusal.constraint}
              tone="refuse"
              data-testid={id('refusal-constraint')}
            />
          </Gloss>
        </span>
        <span className={styles.refusalSqlstateSlot}>
          <Gloss sqlstate={refusal.sqlstate} layout="stack" data-testid={id('gloss-sqlstate')}>
            <Sqlstate
              code={refusal.sqlstate}
              tone="refuse"
              showClass
              data-testid={id('refusal-sqlstate')}
            />
          </Gloss>
        </span>
      </div>

      <div className={styles.facts}>
        <Fact label="constraint">
          <ProvenanceSlot provenance={provenance} pointer="/refusal/constraint" />
        </Fact>
        <Fact label="sqlstate">
          <ProvenanceSlot provenance={provenance} pointer="/refusal/sqlstate" />
        </Fact>
        {/*
          HOW THE CONSTRAINT NAME ABOVE WAS OBTAINED — rendered in every case, not only
          the weak one. An absent member is `undeclared` and never `reported`: the
          emitter said nothing, and a console that filled that silence with the stronger
          of the two claims would be manufacturing the very distinction C-4 exists to
          preserve.
        */}
        <Fact label="constraint_source">
          {refusal.constraint_source === undefined ? (
            <span
              className={styles.chipUndeclared}
              data-testid={id('refusal-constraint-source-absent')}
            >
              <span>not stated by the emitter</span>
            </span>
          ) : (
            <Mono data-testid={id('refusal-constraint-source')}>
              {refusal.constraint_source}
            </Mono>
          )}
        </Fact>
      </div>

      {parsed ? (
        <p className={styles.weakened} data-testid={id('refusal-parsed')}>
          <strong>WEAKENED DIAGNOSIS.</strong> <Mono>constraint_source</Mono> is{' '}
          <Mono>parsed</Mono>: the constraint name above was recovered from the message text, not
          reported by the driver&rsquo;s diagnostics. <Mono>spec/wire/refusal.md</Mono> C-4 requires
          a consumer to say so.
        </p>
      ) : null}

      <pre className={styles.refusalMessage} data-testid={id('refusal-message')}>
        {refusal.message}
      </pre>

      <div className={styles.facts}>
        <Fact label="subject">
          <Mono data-testid={id('refusal-subject')}>
            {refusal.subject_kind} {refusal.subject_id}
          </Mono>
        </Fact>
        <Fact label="gate_epoch">
          <Mono data-testid={id('refusal-gate-epoch')}>{refusal.gate_epoch}</Mono>
          <ProvenanceSlot provenance={provenance} pointer="/gate_epoch" />
        </Fact>
        <Fact label="diagnosis">
          <Mono data-testid={id('refusal-diagnosis')}>{refusal.diagnosis}</Mono>
        </Fact>
      </div>

      <Gloss term="gate-epoch" layout="stack">
        <Mono>gate_epoch</Mono>
      </Gloss>

      <Disclosure
        summary="Show the identifiers for this exact refusal — the ones a report would cite"
        data-testid={id('refusal-identifiers')}
      >
        <div className={styles.facts}>
          <Fact label="probe_calls">
            <Mono>{refusal.probe_calls}</Mono>
          </Fact>
          <Fact label="observed_at">
            <Mono>{refusal.observed_at}</Mono>
          </Fact>
          <Fact label="spec_version">
            <Mono>{refusal.spec_version}</Mono>
          </Fact>
          {refusal.profile === undefined ? null : (
            <Fact label="profile">
              <Mono>{refusal.profile}</Mono>
            </Fact>
          )}
          <Fact label="refusal_id">
            <Mono>{refusal.refusal_id}</Mono>
          </Fact>
        </div>
      </Disclosure>
    </section>
  );
}
