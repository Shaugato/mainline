// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * (4) THE PRECURSORS — every materialised obligation, and what wrote the clause it is
 * attached to.
 *
 * `severity`, `virulence` and `closure_gen` are PROJECTIONS overwritten by
 * `fn_check_project` from `clause_blame_current` (ARCHITECTURE.md §5.5, finding S1).
 * They are never inputs, which is precisely why they carry a `db:column` chip: nobody
 * who wrote the check chose them, and the console did not either.
 *
 * ── M11, CARRIED INTO PIXELS ─────────────────────────────────────────────────────
 *
 * *Gist may accuse; only verbatim may acquit.* A precursor whose event carries an
 * Object-Lock key AND a digest is one a third party can fetch and check without our
 * cooperation — a re-verifiable verbatim anchor. One that carries neither is an
 * accusation this system is making, and it is labelled as one. The two get visibly
 * different treatment because the asymmetry is a legal property, not a styling
 * preference, and a screenshot outlives the stylesheet.
 *
 * ── WHAT WROTE THE CLAUSE ────────────────────────────────────────────────────────
 *
 * There is NO commit-message column in the console's read model: `contracts/ancestry
 * .schema.json` exposes the commit chain (`commit_id`, `gen`, `committed_at`,
 * `control_delta`, `printed_label`) and the blame edges, and nothing else. So this panel
 * renders the introducing commit — the `control_delta = 'introduce'` link — and the
 * blame edge's `attribution`, which is the prose the database holds for a human to read,
 * with its basis and state beside it. When the ancestry payload has not arrived, the
 * panel says the origin is not carried. It never composes a sentence about why a clause
 * exists.
 *
 * D15 / I15 / §11.5: no person is named here. Events carry titles and severities; people
 * do not appear, and `attribution` is rendered exactly as the column holds it.
 */

import { type ReactNode } from 'react';

import { Digest, Mono, SeverityBand } from '../../design/primitives';
import { isVirulenceClass } from '../../design/severity';

import styles from './gate.module.css';
import { clauseOrigin, precursorAnchor, utcDate, type AncestryData } from './model';
import { ProvenanceSlot } from './ProvenanceSlot';
import { pointer, type ProvenanceEntry } from './provenance';
import type { BlockingCheck } from '../../data/types.generated';

export interface PrecursorListProps {
  /** Every check on the subject, or `null` when that read has not landed. */
  readonly checks: readonly BlockingCheck[] | null;
  readonly provenance: readonly ProvenanceEntry[] | undefined;
  /** The ancestry payload for the diff subject's clause, when one arrived. */
  readonly ancestry: AncestryData | null;
  /** Check ids the refusal's reason set names. Rendered as a marker, never inferred. */
  readonly namedByReasonSet: ReadonlySet<string>;
}

function Kv({ k, children }: { readonly k: string; readonly children: ReactNode }): ReactNode {
  return (
    <span className={styles.fact}>
      <span className={styles.label}>{k}</span>
      <span className={styles.factValue}>{children}</span>
    </span>
  );
}

function Origin({
  check,
  ancestry,
}: {
  readonly check: BlockingCheck;
  readonly ancestry: AncestryData | null;
}): ReactNode {
  // The ancestry payload is about ONE clause. Applying it to a different clause's check
  // would attribute the wrong history to the wrong control.
  const applicable = ancestry !== null && ancestry.clause_uuid === check.clause_uuid;
  const origin = clauseOrigin(applicable ? ancestry : null, check.precursor_event_id ?? null);

  if (origin.introducing === null && origin.blame === null) {
    return (
      <div className={styles.absent} data-testid="origin-absent">
        <span className={styles.absentTitle}>origin of the clause not carried</span>
        <p className={styles.prose}>
          No ancestry payload for <Mono>{check.clause_uuid}</Mono> reached this screen, so the commit
          that introduced the clause and the blame edge behind this check are not shown. The console
          does not reconstruct either.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="origin">
      {origin.introducing === null ? null : (
        <div className={styles.facts} data-testid="origin-commit">
          <Kv k="introduced by commit">
            <Digest value={origin.introducing.commit_id} label="commit" prefixLength={12} />
          </Kv>
          <Kv k="committed_at">
            {utcDate(origin.introducing.committed_at)} ({origin.introducing.committed_at})
          </Kv>
          <Kv k="control_delta">{origin.introducing.control_delta}</Kv>
          <Kv k="printed_label">{origin.introducing.printed_label ?? 'none'}</Kv>
          <Kv k="gen">{origin.introducing.gen}</Kv>
        </div>
      )}
      {origin.blame === null ? null : (
        <>
          <div className={styles.facts} data-testid="origin-blame">
            <Kv k="blame basis">{origin.blame.basis}</Kv>
            <Kv k="blame state">{origin.blame.state}</Kv>
            {origin.blame.p_link === null || origin.blame.p_link === undefined ? null : (
              <Kv k="p_link">{origin.blame.p_link}</Kv>
            )}
            <span className={styles.fact}>
              <span
                className={styles.anchorStrength}
                data-anchor={
                  origin.blame.evidence_quote_sha256 === null ||
                  origin.blame.evidence_quote_sha256 === undefined
                    ? 'gist'
                    : 'verbatim'
                }
              >
                {origin.blame.evidence_quote_sha256 === null ||
                origin.blame.evidence_quote_sha256 === undefined
                  ? 'no quoted anchor'
                  : 'quoted anchor'}
              </span>
            </span>
          </div>
          {origin.blame.attribution === null || origin.blame.attribution === undefined ? null : (
            <p className={styles.canon} data-testid="origin-attribution">
              {origin.blame.attribution}
            </p>
          )}
        </>
      )}
    </div>
  );
}

function CheckItem({
  check,
  index,
  provenance,
  ancestry,
  named,
}: {
  readonly check: BlockingCheck;
  readonly index: number;
  readonly provenance: readonly ProvenanceEntry[] | undefined;
  readonly ancestry: AncestryData | null;
  readonly named: boolean;
}): ReactNode {
  const precursor = check.precursor ?? null;
  const anchor = precursorAnchor(precursor);

  return (
    <li
      className={styles.item}
      id={`gate-check-${check.check_id}`}
      data-testid="precursor"
      data-check-id={check.check_id}
      data-open={check.open ? 'true' : 'false'}
      data-anchor={anchor}
    >
      <div className={styles.itemHead}>
        <Mono data-testid="precursor-origin">{check.origin}</Mono>
        {isVirulenceClass(check.virulence) ? (
          <SeverityBand
            virulence={check.virulence}
            severity={check.severity}
            data-testid="precursor-band"
          />
        ) : (
          <Kv k="virulence">{check.virulence}</Kv>
        )}
        <span className={styles.weldState} data-testid="precursor-state">
          {check.open ? 'open' : 'dispositioned'}
        </span>
        {named ? (
          <span className={styles.refusalKicker} data-testid="precursor-named">
            named by the reason set
          </span>
        ) : null}
        <span className={styles.anchorStrength} data-anchor={anchor} data-testid="precursor-anchor">
          {anchor === 'verbatim'
            ? 'verbatim anchor — re-verifiable'
            : 'gist only — may accuse, may not acquit'}
        </span>
      </div>

      <div className={styles.facts}>
        <Kv k="check_id">{check.check_id}</Kv>
        <Kv k="clause">
          {check.clause_label ?? 'unlabelled'} <Mono>{check.clause_uuid}</Mono>
        </Kv>
        <Kv k="severity">{check.severity}</Kv>
        <ProvenanceSlot provenance={provenance} pointer={pointer('checks', index, 'severity')} />
        <Kv k="closure_gen">{check.closure_gen}</Kv>
        <ProvenanceSlot provenance={provenance} pointer={pointer('checks', index, 'closure_gen')} />
        <Kv k="control_delta">{check.control_delta ?? 'none recorded'}</Kv>
        <Kv k="materialised_at">{check.materialised_at}</Kv>
      </div>

      <p className={styles.canon} data-testid="precursor-evidence-summary">
        {check.evidence_summary}
      </p>

      {precursor === null ? (
        <div className={styles.absent}>
          <span className={styles.absentTitle}>no precursor event carried</span>
          <p className={styles.prose}>
            This check names no precursor event in the payload, so there is no incident record to
            show beside it.
          </p>
        </div>
      ) : (
        <div data-testid="precursor-event">
          <div className={styles.facts}>
            <Kv k="event">{precursor.kind}</Kv>
            <Kv k="external_ref">{precursor.external_ref ?? 'none'}</Kv>
            <Kv k="occurred_at">
              {utcDate(precursor.occurred_at)} ({precursor.occurred_at})
            </Kv>
            <Kv k="severity_gate">{precursor.severity_gate}</Kv>
            <Kv k="severity_basis">{precursor.severity_basis}</Kv>
          </div>
          <p className={styles.canon} data-testid="precursor-title">
            {precursor.title}
          </p>
          {anchor === 'verbatim' ? (
            <div className={styles.facts}>
              <Kv k="source object">{precursor.source_object_key}</Kv>
              {precursor.source_sha256 === null || precursor.source_sha256 === undefined ? null : (
                <Digest value={precursor.source_sha256} label="source sha256" />
              )}
            </div>
          ) : (
            <p className={styles.panelNote} data-testid="precursor-gist-note">
              This event carries no Object-Lock key and no digest in the payload, so nothing here
              can be re-fetched and checked by a third party. Under M11 (ARCHITECTURE.md §3.3) an
              unanchored record may raise an obligation; it may not clear one.
            </p>
          )}
        </div>
      )}

      <Origin check={check} ancestry={ancestry} />
    </li>
  );
}

export function PrecursorList({
  checks,
  provenance,
  ancestry,
  namedByReasonSet,
}: PrecursorListProps): ReactNode {
  return (
    <section className={styles.panel} aria-labelledby="gate-precursors-title" data-testid="precursors">
      <h2 className={styles.panelTitle} id="gate-precursors-title">
        Precursors — the materialised obligations
      </h2>
      <p className={styles.panelNote}>
        <Mono>severity</Mono>, <Mono>virulence</Mono> and <Mono>closure_gen</Mono> are projections
        written by <Mono>fn_check_project</Mono> from <Mono>clause_blame_current</Mono>; nobody who
        wrote a check chose them (ARCHITECTURE.md §5.5, S1).
      </p>

      {checks === null ? (
        <div className={styles.absent} data-testid="precursors-unavailable">
          <span className={styles.absentTitle}>blocking checks not carried</span>
          <p className={styles.prose}>
            The <Mono>blocking_checks</Mono> read has not landed, so this screen holds no witness
            rows for <Mono>open_blocking</Mono>. That is an absence of evidence on this screen, not
            a claim that there are none.
          </p>
        </div>
      ) : checks.length === 0 ? (
        <div className={styles.absent} data-testid="precursors-empty">
          <span className={styles.absentTitle}>no blocking checks on this subject</span>
          <p className={styles.prose}>
            The payload carries an empty list. That is the emitter asserting there are none — a
            different claim from the read not having landed.
          </p>
        </div>
      ) : (
        <ol className={styles.list} data-testid="precursor-list">
          {checks.map((check, index) => (
            <CheckItem
              key={check.check_id}
              check={check}
              index={index}
              provenance={provenance}
              ancestry={ancestry}
              named={namedByReasonSet.has(check.check_id)}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
