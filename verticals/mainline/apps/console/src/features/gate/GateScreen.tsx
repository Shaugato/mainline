// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE GATE SCREEN — the refusal, its irreducible reason set, and the clause diff that
 * armed it.
 *
 * Top to bottom, and the order is the argument:
 *
 *   0. the plain-language band — three sentences about THIS permit, the SYNTHETIC
 *      marker, and how this screen came to be about it;
 *   1. the subject, and the one control that attempts the transition;
 *   2. the refusal bar — constraint name, SQLSTATE, `constraint_source`, subject, gate
 *      epoch, all verbatim, under a plain-language lead;
 *   3. the minimal unsatisfiable subset and the nearest admissible alternative;
 *   3b. every FURTHER refusal the same run produced — because the four-beat run refuses
 *      twice and the second refusal is the rarer claim;
 *   4. the weld — every projected counter under the CHECK that reads it;
 *   5. the precursors — the materialised obligations and what wrote their clauses;
 *   6. the clause diff — the edit, its control delta, and the witnesses behind it.
 *
 * ── WHERE THE BAND'S REFUSAL COMES FROM (R7) ─────────────────────────────────────
 *
 * TWO exchanges can refuse this subject and the screen watches both.
 *
 *   `POST /v1/permits/{id}/merge`   the control ON THIS SCREEN. `useGateData` owns it.
 *   `POST /v1/demo/gate-run`        the four-beat demonstration the driver above drives,
 *                                   published verbatim through Contract B
 *                                   (`last-run.ts`) and adapted by `refusal-from-run.ts`.
 *
 * Until 2026-08-15 the band watched only the first, so a reader who pressed MERGE in the
 * driver saw `beat 2 · merge · REFUSED · 23514 · gate_closed_when_issued` in one panel and
 * **NO ATTEMPT — NOTHING HAS BEEN REFUSED** in the panel built to display exactly that.
 * `docs/leads/demo-story-plan.md` §0.4(i) measured it and R7 rules on it.
 *
 * The precedence lives in `selectBand` and is stated on the page: a reader's own press
 * always holds the headline band; a run's refusal can only take a band this screen's own
 * attempt left in the `none` state, and when it does, the screen says which run and which
 * beat it came from and that the run's transaction was rolled back (R11). With no
 * completed run — `useLastGateRun()` returning `null` — every element below renders
 * exactly as it rendered before this was wired, which is the other half of R7: the console
 * must never predict a refusal it has not seen.
 *
 * ── WHAT THE BAND IS, AND WHAT IT IS NOT ─────────────────────────────────────────
 *
 * `docs/leads/two-audience-ux-plan.md` §1: a band ABOVE the mechanism, never a summary
 * instead of it. Every sentence in it is built in `model.ts` from a payload field —
 * `permit.external_ref`, `permit.counters.open_blocking` — and the SYNTHETIC marker is
 * the demonstration seed's own text, rendered verbatim because R5 forbids re-wording a
 * marker the data already carries. The reading mode is the SHELL's — `?detail=full`,
 * published through `DetailModeContext`, read by every `Disclosure` below without this
 * screen threading it anywhere. PLAIN collapses predicates and statements into labelled
 * disclosures; it never hides the refusal bar, the SQLSTATE, the constraint name, a
 * provenance chip, a STAGED badge or that marker. FULL DETAIL is exactly this screen
 * with every disclosure open.
 *
 * Nothing on this screen is composed by the console except the band and the prose that
 * describes an ABSENCE. Every value is a payload field, rendered in the mono face with a
 * provenance chip. This component computes no gate condition (D5) and imports no
 * animation library — the directory is EVIDENCE and
 * `tests/unit/design/register-boundary.test.ts` walks the real module graph to prove it.
 */

import { useMemo, type ReactNode } from 'react';

import { Digest, Disclosure, Gloss, Mono, PlainBand, StagedBadge } from '../../design/primitives';

import { ClauseDiff } from './ClauseDiff';
import styles from './gate.module.css';
import { useLastGateRun } from './last-run';
import { plainGateBand, REASON_SET_TITLE, WELD_TITLE } from './model';
import { PrecursorList } from './PrecursorList';
import { ProvenanceSlot } from './ProvenanceSlot';
import { ReasonSet } from './ReasonSet';
import {
  RUN_ABSENCE_SENTENCE,
  refusalLead,
  refusalsFromRun,
  runAttribution,
  selectBand,
  type RunRefusal,
  type RunRefusalModel,
} from './refusal-from-run';
import { RefusalBar } from './RefusalBar';
import type { SubjectOrigin } from './addressing';
import { WeldDiagram } from './WeldDiagram';
import type { GateModel } from './useGateData';
import type { RefusalPayload } from '../../data/types.generated';
import type { ResourceState } from '../../data/useResource';

export interface GateScreenProps {
  readonly permitId: string;
  readonly model: GateModel;
  /** True when no transport has been provided. Renders the NO SOURCE panel. */
  readonly noSource?: boolean;
  /** How this screen came to be about this permit. `null` before anything named one. */
  readonly origin?: SubjectOrigin | null;
  /** The sentence for {@link GateScreenProps.origin}, so the screen says it on the page. */
  readonly originSentence?: string | null;
}

/**
 * THE SYNTHETIC MARKER (R5), AS A SLOT THE PAYLOAD FILLS.
 *
 * `PlainBand` takes the marker as a node rather than a boolean, deliberately: the console
 * must not be able to produce the marker on its own. What goes in here is derived from
 * the demonstration seed's own `SYNTHETIC —` prefix, found in text the database returned
 * — and when no payload on the screen carries that prefix, the slot says so, in words,
 * rather than going quiet. A screen that showed nothing there would be indistinguishable
 * from a screen that forgot to check.
 */
function SyntheticMarker({ marker }: { readonly marker: string | null }): ReactNode {
  if (marker === null) {
    return (
      <span
        className={styles.syntheticAbsent}
        data-testid="synthetic-marker"
        data-synthetic="undeclared"
      >
        no synthetic marker on these payloads
      </span>
    );
  }
  return (
    <Gloss term="synthetic" data-testid="gloss-synthetic">
      <span className={styles.synthetic} data-testid="synthetic-marker" data-synthetic="declared">
        synthetic
      </span>
    </Gloss>
  );
}

function ReadFailure<T>({
  state,
  what,
}: {
  readonly state: ResourceState<T>;
  readonly what: string;
}): ReactNode {
  if (state.status !== 'failed') return null;
  return (
    <div className={styles.absent} role="alert" data-testid={`read-failed-${what}`}>
      <span className={styles.absentTitle}>
        {what} read failed — <Mono>{state.failure}</Mono>
      </span>
      <pre className={styles.refusalMessage}>{state.detail}</pre>
      <p className={styles.prose}>
        A read that did not complete is an absence of evidence on this screen. Nothing about the
        gate follows from it, and no part of this surface fills the hole with a default.
      </p>
    </div>
  );
}

/**
 * THE R9 ON-RAMP, ABOVE THE BAND AND NEVER INSTEAD OF IT.
 *
 * `docs/leads/demo-story-plan.md` R9: *every screen gains a lead — one short paragraph in
 * plain language, above the fold — and every existing sentence stays, below it. If a
 * rewrite makes a claim vaguer, weaker, or less checkable, it is wrong.* So this renders
 * ABOVE `RefusalBar` and changes nothing inside it: the constraint name, the SQLSTATE,
 * the `constraint_source`, the verbatim message, the provenance chips and the reason set
 * are all still there, in the same words, further down.
 *
 * The sentences come from `refusalLead`, which is pure and unit-tested, and every clause
 * of every one of them points at the payload member the disclosure below lists. The count
 * comes off `mus.length`; the alternative is `naa.description` quoted verbatim, in
 * quotation marks, because it is the database's sentence and not this console's. There is
 * no branch here that chooses a sentence from a SQLSTATE (D18).
 */
function RefusalLead({
  refusal,
  scope = null,
}: {
  readonly refusal: RefusalPayload;
  /** Suffixes this lead's identifiers when the page carries more than one band. */
  readonly scope?: string | null;
}): ReactNode {
  const lead = refusalLead(refusal);
  const id = (name: string): string => (scope === null ? name : `${name}-${scope}`);
  return (
    <section
      className={styles.refusalLead}
      data-testid={id('refusal-lead')}
      aria-label="What the database said, in plain language"
    >
      <span className={styles.refusalKicker}>{lead.kicker}</span>
      {lead.sentences.map((sentence) => (
        <p className={styles.prose} key={sentence}>
          {sentence}
        </p>
      ))}
      <Disclosure
        summary="Show which payload members this paragraph was built from"
        note="Every clause above is read off one of these; none of them is the console's own wording."
        data-testid={id('refusal-lead-basis')}
      >
        <ul className={styles.plainBasis}>
          {lead.basis.map((member) => (
            <li key={member}>
              <Mono>{member}</Mono>
            </li>
          ))}
        </ul>
      </Disclosure>
    </section>
  );
}

/**
 * A REFUSAL FROM THE SAME RUN THAT IS NOT ON THE HEADLINE BAND.
 *
 * The four-beat run refuses TWICE, and the second one is the whole reason the demo is
 * worth watching: the projected counter has been forced to zero out of band, the CHECK
 * constraint the first refusal named is now SATISFIED, and the merge is refused anyway
 * because `mainline.fn_permit_merge_gate` re-derives the count rather than trusting the
 * column. A screen that showed only the first refusal would be telling half the argument,
 * so every further refusal gets the same treatment as the first: its own lead, its own
 * band, its own reason set.
 *
 * It carries NO provenance list. The gate-run payload published through Contract B is the
 * `data` member, not its envelope, so this console holds no provenance claims for these
 * values — and `ProvenanceSlot` renders that as UNDECLARED with the pointer it looked up,
 * which is the true statement. Borrowing the merge exchange's chips would attach one
 * exchange's provenance to another's values.
 */
function FurtherRefusal({
  beat,
  model,
}: {
  readonly beat: RunRefusal;
  readonly model: RunRefusalModel;
}): ReactNode {
  const scope = `beat-${String(beat.ordinal)}`;
  return (
    <>
      <section
        className={styles.panel}
        aria-labelledby={`${scope}-title`}
        data-testid="further-refusal"
        data-beat={beat.ordinal}
      >
        <span className={styles.refusalKicker}>another refusal from the same run</span>
        <h2 className={styles.panelTitle} id={`${scope}-title`}>
          Beat {beat.ordinal} — {beat.label}
        </h2>
        <p className={styles.panelNote} data-testid="further-refusal-attribution">
          {runAttribution(model, beat)}
        </p>
        <div className={styles.facts}>
          <span className={styles.fact}>
            <span className={styles.label}>beat</span>
            <Mono>{beat.name}</Mono>
          </span>
          <span className={styles.fact}>
            <span className={styles.label}>elapsed_ms</span>
            <Mono data-testid="further-refusal-elapsed">{beat.elapsedMs}</Mono>
          </span>
          <span className={styles.fact}>
            <span className={styles.label}>matched_expectation</span>
            <Mono>{String(beat.matchedExpectation)}</Mono>
          </span>
        </div>
        {beat.note === null ? null : (
          <p className={styles.panelNote} data-testid="further-refusal-note">
            {beat.note}
          </p>
        )}
        {beat.statement === null ? null : (
          <Disclosure
            summary="Show the parameterised SQL this beat sent, so it can be run again"
            data-testid="further-refusal-statement"
          >
            <pre className={styles.refusalMessage}>{beat.statement}</pre>
          </Disclosure>
        )}
      </section>

      {beat.state.kind === 'refused' ? (
        <RefusalLead refusal={beat.state.refusal} scope={scope} />
      ) : null}
      <RefusalBar state={beat.state} provenance={undefined} scope={scope} />
      {beat.state.kind === 'refused' ? (
        <ReasonSet refusal={beat.state.refusal} provenance={undefined} scope={scope} />
      ) : null}
    </>
  );
}

function NoSource(): ReactNode {
  return (
    <div className={styles.surface} data-testid="gate-no-source">
      <section className={styles.refusalBar} data-state="none" aria-label="Refusal">
        <span className={styles.refusalKicker}>no source — nothing has been read</span>
        <p className={styles.prose}>
          This surface has been given neither a live kernel nor a verified evidence bundle, so it
          holds no bytes and shows no claims. It does not construct a transport of its own: a bundle
          player without a verifier is a mock, and{' '}
          <Mono>src/data/bundle.ts</Mono> ships no default verifier on purpose.
        </p>
        <p className={styles.prose}>
          To feed it, provide a <Mono>MainlineTransport</Mono> through{' '}
          <Mono>GateTransportContext</Mono> — an <Mono>HttpTransport</Mono> pointed at the kernel,
          or a <Mono>BundleTransport</Mono> over a verified EvidenceBundle.
        </p>
      </section>
    </div>
  );
}

export function GateScreen({
  permitId,
  model,
  noSource = false,
  origin = null,
  originSentence = null,
}: GateScreenProps): ReactNode {
  // Contract B, read BEFORE the early return: hooks are unconditional, and `null` — no
  // completed run in this session — is the value that keeps every band below exactly as
  // it renders today.
  const lastRun = useLastGateRun();
  const runModel = useMemo(() => refusalsFromRun(lastRun, permitId), [lastRun, permitId]);

  if (noSource) return <NoSource />;

  const {
    permitData,
    checkRows,
    clauseData,
    ancestryData,
    refusalState,
    weld,
    diffSubject,
    namedByReasonSet,
    permitProvenance,
    checksProvenance,
    clauseProvenance,
    attemptProvenance,
    attempted,
    beginAttempt,
    staged,
    stagedNote,
  } = model;

  const busy = model.attempt.status === 'loading';

  // The precedence rule lives in `selectBand` and is decided in ONE place. `primary` is
  // what the headline band renders; `further` is every refusal the run produced that the
  // headline band did not take.
  const selection = selectBand(refusalState, runModel);

  const band = plainGateBand({
    permitId,
    permit: permitData,
    checks: checkRows,
    ancestry: ancestryData,
  });

  return (
    <div className={styles.surface} data-testid="gate-surface">
      {/*
        ── 0. The plain-language band ──

        The SHELL already mounts a lede saying what this KIND of screen is for
        (`src/app/SurfaceHost.tsx`, `src/copy/onramp.ts`). This band is the other half and
        only the surface can write it: what THIS permit is, read off this permit's own
        payload — the seed's SYNTHETIC marker, the external reference, and the number of
        obligations the database itself says are still open.
      */}
      <PlainBand
        kicker="what this permit is"
        sentences={band.sentences}
        marker={<SyntheticMarker marker={band.marker} />}
        data-testid="plain-band"
      >
        {band.marker === null ? (
          <p className={styles.sourceLine} data-testid="synthetic-marker-absent">
            Nothing read onto this screen opens with the demonstration seed&rsquo;s own
            &ldquo;SYNTHETIC&nbsp;&mdash;&rdquo; prefix. That is a fact about these payloads, and
            the console will not assert either way on their behalf.
          </p>
        ) : (
          <>
            <pre className={styles.canon} data-testid="synthetic-marker-quote">
              {band.marker}
            </pre>
            <p className={styles.sourceLine} data-testid="synthetic-marker-field">
              read from <Mono>{band.markerField}</Mono>
            </p>
          </>
        )}

        {band.quotes.slice(1).map((quote) => (
          <div key={quote.field} data-testid="plain-quote">
            <span className={styles.label}>{quote.label}</span>
            <pre className={styles.canon}>{quote.text}</pre>
            <p className={styles.sourceLine}>
              read from <Mono>{quote.field}</Mono>
            </p>
          </div>
        ))}

        {originSentence === null ? null : (
          <p className={styles.panelNote} data-testid="subject-origin" data-origin={origin}>
            {originSentence}
          </p>
        )}

        <Disclosure
          summary="Show which payload members these sentences were built from"
          note="Every clause above is read off one of these; none of them is the console's own number."
          data-testid="plain-band-basis"
        >
          {/*
            Keyed by POSITION as well as by value. `plainGateBand` legitimately lists the
            same member twice — with no permit payload it reports `no permit payload` for
            both the subject line and the count — and React warned about the duplicate key
            on every render of the not-yet-loaded screen. The list is ordered and the order
            is meaningful, so position is the right identity; the rendered text is
            unchanged.
          */}
          <ul className={styles.plainBasis}>
            {band.basis.map((member, index) => (
              <li key={`${String(index)}:${member}`}>
                <Mono>{member}</Mono>
              </li>
            ))}
          </ul>
        </Disclosure>
      </PlainBand>

      {/* ── 1. The subject and the one control ── */}
      <section className={styles.panel} aria-labelledby="gate-subject-title" data-testid="gate-subject">
        <h1 className={styles.panelTitle} id="gate-subject-title">
          Permit <Mono>{permitData?.external_ref ?? permitId}</Mono>
        </h1>
        <div className={styles.facts}>
          <span className={styles.fact}>
            <span className={styles.label}>permit_id</span>
            <Mono>{permitId}</Mono>
          </span>
          {permitData === null ? null : (
            <>
              <span className={styles.fact}>
                <span className={styles.label}>ref_name</span>
                <Mono>{permitData.ref_name}</Mono>
              </span>
              <span className={styles.fact}>
                <span className={styles.label}>state</span>
                <Mono data-testid="permit-state">{permitData.state}</Mono>
                <ProvenanceSlot provenance={permitProvenance} pointer="/state" />
              </span>
              <span className={styles.fact}>
                <span className={styles.label}>gate_epoch</span>
                <Mono data-testid="permit-gate-epoch">{permitData.gate_epoch}</Mono>
                <ProvenanceSlot provenance={permitProvenance} pointer="/gate_epoch" />
              </span>
              <span className={styles.fact}>
                <span className={styles.label}>under_hold</span>
                <Mono>{permitData.under_hold}</Mono>
              </span>
              {permitData.slice_digest === null || permitData.slice_digest === undefined ? null : (
                <Digest value={permitData.slice_digest} label="slice digest" />
              )}
            </>
          )}
          {staged ? <StagedBadge what="every value on this screen came from a staged bundle" /> : null}
        </div>

        {permitData === null ? null : (
          <Gloss term="gate-epoch" layout="stack" data-testid="gloss-gate-epoch">
            <Mono>gate_epoch</Mono>
          </Gloss>
        )}
        {staged ? (
          <Gloss term="staged" layout="stack" data-testid="gloss-staged">
            <Mono>STAGED</Mono>
          </Gloss>
        ) : null}

        {staged && stagedNote !== null ? (
          <p className={styles.panelNote} data-testid="staged-note">
            {stagedNote}
          </p>
        ) : null}

        <div className={styles.attempt}>
          {/*
            R7: the control keeps the exact method and path — they are the whole claim
            that this button is one HTTP request against a real database — and gains a
            label that says what pressing it DOES. Both are inside the button, so the
            accessible name carries both and a screenshot of the control alone still
            names the request.
          */}
          <button
            type="button"
            className={styles.attemptButton}
            onClick={beginAttempt}
            disabled={attempted || permitData === null}
            data-testid="attempt-merge"
          >
            <span className={styles.attemptLabel}>Ask the database to merge this permit</span>
            <span className={styles.attemptWire}>POST /v1/permits/{permitId}/merge</span>
          </button>
          <span className={styles.panelNote}>
            {attempted
              ? 'Attempted once. There is no automatic retry anywhere in this console — spec/wire/refusal.md C-1.'
              : 'Calls trappoint.merge_permit() in one serializable transaction. The database refuses it, by name, or it commits. Nothing on this screen predicts which.'}
          </span>
        </div>

        <ReadFailure state={model.permit} what="permit" />
        <ReadFailure state={model.checks} what="blocking-checks" />
        <ReadFailure state={model.clause} what="clause-version" />
        <ReadFailure state={model.ancestry} what="clause-ancestry" />
      </section>

      {/* ── 2. The refusal bar ── */}
      {selection.primary.kind === 'refused' ? (
        <RefusalLead refusal={selection.primary.refusal} />
      ) : null}
      {/*
        THE PROVENANCE BELONGS TO THE EXCHANGE THAT CARRIED THE VALUES, AND ONLY THAT ONE.
        `attemptProvenance` is the merge exchange's envelope list. When the band is showing
        a REFUSAL FROM A RUN, this console holds no provenance list for those values —
        Contract B publishes the gate-run `data`, not its envelope — so the slots render
        UNDECLARED with the pointer they looked up, which is the true statement. Lending
        one exchange's chips to another exchange's values would be a provenance claim
        nobody made.
      */}
      <RefusalBar
        state={selection.primary}
        provenance={selection.primarySource === 'attempt' ? attemptProvenance : undefined}
      />
      {selection.primarySource === 'run' && selection.primaryBeat !== null ? (
        <p className={styles.sourceLine} data-testid="refusal-from-run">
          {runAttribution(runModel, selection.primaryBeat)}
        </p>
      ) : null}
      {/*
        WHICH NOTHING THIS IS. A run that answered and contributed nothing to THIS screen
        is not the same statement as no run at all, so the three cases that are not
        `no-run` say so. `no-run` renders nothing, deliberately: R7 requires the un-pressed
        screen to be byte-identical to what it was.
      */}
      {runModel.absence === null || runModel.absence === 'no-run' ? null : (
        <p
          className={styles.sourceLine}
          data-testid="run-absence"
          data-absence={runModel.absence}
        >
          {RUN_ABSENCE_SENTENCE[runModel.absence]}
        </p>
      )}

      {/* ── 3. The reason set ── */}
      {selection.primary.kind === 'refused' ? (
        <ReasonSet
          refusal={selection.primary.refusal}
          provenance={selection.primarySource === 'attempt' ? attemptProvenance : undefined}
        />
      ) : (
        <section className={styles.panel} data-testid="reason-set-absent" aria-label="Reason set">
          <h2 className={styles.panelTitle}>{REASON_SET_TITLE}</h2>
          <Gloss term="minimal-unsatisfiable-subset" layout="stack">
            <Mono>minimal unsatisfiable subset</Mono>
          </Gloss>
          <div className={styles.absent}>
            <span className={styles.absentTitle}>no reason set</span>
            <p className={styles.prose}>
              A minimal unsatisfiable subset exists only for a refusal that happened. There is no
              refusal on this screen{busy ? ' yet' : ''}, so there is nothing to decompose.
            </p>
          </div>
        </section>
      )}

      {/* ── 3b. Every further refusal the same run produced ── */}
      {selection.further.map((beat) => (
        <FurtherRefusal beat={beat} key={`${String(beat.ordinal)}:${beat.name}`} model={runModel} />
      ))}

      {/* ── 4. The weld ── */}
      {weld === null || permitData === null ? (
        <section className={styles.panel} data-testid="weld-absent" aria-label={WELD_TITLE}>
          <h2 className={styles.panelTitle}>{WELD_TITLE}</h2>
          <div className={styles.absent}>
            <span className={styles.absentTitle}>permit not carried</span>
            <p className={styles.prose}>
              The permit read has not landed, so the projected counters and the constraints that
              read them are not available. The console shows no counters rather than zeroes.
            </p>
          </div>
        </section>
      ) : (
        <WeldDiagram
          weld={weld}
          permit={permitData}
          provenance={permitProvenance}
          checks={checkRows}
        />
      )}

      {/* ── 5. The precursors ── */}
      <PrecursorList
        checks={checkRows}
        provenance={checksProvenance}
        ancestry={ancestryData}
        namedByReasonSet={namedByReasonSet}
      />

      {/* ── 6. The clause diff ── */}
      <ClauseDiff
        clause={clauseData}
        selection={diffSubject.selection}
        provenance={clauseProvenance}
      />
    </div>
  );
}
