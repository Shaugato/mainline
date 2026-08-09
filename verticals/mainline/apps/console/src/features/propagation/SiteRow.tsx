// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * ONE site's answer to one lesson — adopted, declined, or not yet answered.
 *
 * ── EQUAL PROMINENCE IS STRUCTURAL, NOT STYLISTIC ────────────────────────────────
 *
 * Every row renders through this component, with one class (`.site`), the same grid, the
 * same type scale and the same blocks in the same order, whatever `state` says. There is
 * no muted variant, no collapsed variant, no "declined" tint and no `<details>` wrapper
 * that would let a refusal start life folded away.
 *
 * That is the product claim on this surface. A fleet view that renders adoptions loudly
 * and declinations quietly reports adoption — which is precisely the report a fleet
 * safety programme wants and precisely the report that gets an operator sued. A site
 * saying NO, with a named kind, a named predicate and an expiry, is the most useful row
 * on the screen.
 *
 * `data-prominence="equal"` is written onto every row so a spec can assert the invariant
 * as an invariant, and `tests/browser/propagation.spec.ts` additionally compares the
 * COMPUTED font size, weight and opacity of the adopted and declined rows — because a
 * later stylesheet edit could break the claim without touching this file.
 *
 * ── WHAT THIS ROW DOES NOT DO ────────────────────────────────────────────────────
 *
 * It renders no verdict about a declination. `declination_kind` is a column; the CHECK
 * that makes each kind falsifiable is named beside it, together with the value of the
 * column that CHECK requires. Where that column is empty the row says the column is
 * empty. It does not say the row is invalid — the database decides that, and it says so
 * with a constraint name and a SQLSTATE, not with a colour on a card.
 */

import { type ReactNode } from 'react';

import { Digest, Mono } from '../../design/primitives';

import { Instant } from './Instant';
import type { FleetRow } from './model';
import styles from './propagation.module.css';
import { ProvenanceSlot } from './ProvenanceSlot';
import { pointer, type ProvenanceEntry } from './provenance';

export interface SiteRowProps {
  readonly row: FleetRow;
  /** Index into `data.propagations`, for the JSON pointers the chips look up. */
  readonly index: number;
  readonly provenance: readonly ProvenanceEntry[] | undefined;
}

function Declination({ row }: { readonly row: FleetRow }): ReactNode {
  const declination = row.declination;

  if (declination === null) {
    return (
      <div className={styles.block} data-testid="site-no-declination">
        <h4 className={styles.blockTitle}>declination</h4>
        <p className={styles.prose}>
          <Mono>declination_kind</Mono> is NULL on this row. This site has not refused the
          lesson; whether it has answered at all is the <Mono>state</Mono> column above.
        </p>
      </div>
    );
  }

  return (
    <div
      className={styles.declination}
      data-testid="site-declination"
      data-declination-kind={declination.kind}
    >
      <h4 className={styles.blockTitle}>declination</h4>
      <p>
        <span className={styles.declinationKind} data-testid="site-declination-kind">
          <Mono>{declination.kind}</Mono>
        </span>{' '}
        <span className={styles.slotPointer}>{declination.gloss}</span>
      </p>

      <dl className={styles.facts}>
        <dt>governed by</dt>
        <dd>
          <Mono data-testid="site-declination-constraint">{declination.constraint}</Mono>{' '}
          <span className={styles.slotPointer}>
            requires <Mono>{declination.requires}</Mono>
          </span>
        </dd>

        <dt>{declination.requires}</dt>
        <dd>
          {declination.requiredValue === null ? (
            <span className={styles.absent} data-testid="site-declination-required-absent">
              absent in this payload
            </span>
          ) : (
            <Mono data-testid="site-declination-required">{declination.requiredValue}</Mono>
          )}
        </dd>

        {declination.predicateId === null ? null : (
          <>
            <dt>predicate</dt>
            <dd>
              <Mono data-testid="site-declination-predicate">{declination.predicateId}</Mono>
              <p className={styles.note}>
                A machine-checkable predicate, named by id. `mechanism_absent` without one is
                not a representable row — that is what makes the refusal falsifiable rather
                than an opinion.
              </p>
            </dd>
          </>
        )}

        <dt>expires</dt>
        <dd>
          <Instant
            label="declination_expires_at"
            value={declination.expiresAt}
            interval={declination.expiry}
            data-testid="site-declination-expiry"
          />
          {declination.kind === 'waiver' && declination.expiresAt === null ? (
            <p className={styles.note}>
              A waiver with no expiry is refused by <Mono>waiver_expires</Mono>. This payload
              carries none, which is a fact about the payload.
            </p>
          ) : null}
        </dd>
      </dl>
    </div>
  );
}

export function SiteRow({ row, index, provenance }: SiteRowProps): ReactNode {
  const propagation = row.propagation;
  // Normalised once: the payload types these as `T | null | undefined`, and a ternary
  // over the raw field narrows neither branch.
  const adoptedCommit = propagation.adopted_commit ?? null;
  const alreadyPresent = propagation.already_present_clause ?? null;

  return (
    <li
      className={styles.site}
      data-testid="site-row"
      data-site={row.label}
      data-state={row.state}
      data-standing={row.standing}
      data-declination-kind={row.declination?.kind}
      // The invariant, written where a spec can read it: every state renders through the
      // same component with the same class and the same blocks.
      data-prominence="equal"
    >
      <div className={styles.siteHead}>
        <span className={styles.siteLabel} data-testid="site-label">
          <Mono>{row.label}</Mono>
        </span>
        <span className={styles.siteState} data-testid="site-state">
          <Mono>{row.state}</Mono>
        </span>
        <ProvenanceSlot
          provenance={provenance}
          pointer={pointer('propagations', index, 'state')}
          data-testid="site-state-provenance"
        />
      </div>

      <div className={styles.siteBody}>
        <div className={styles.block}>
          <h4 className={styles.blockTitle}>the clock</h4>
          <Instant
            label="proposed_at"
            value={propagation.proposed_at}
            interval={null}
            data-testid="site-proposed"
          />
          <Instant
            label="due_by"
            value={propagation.due_by}
            interval={row.due}
            standing={row.standing}
            data-testid="site-due"
          />
          <p className={styles.note}>
            The SLA clock is severity-scaled and it is a fact, not a demand. A site that has
            not answered is displayed as not having answered — never as compliant by default,
            and never as a countdown that nags. Intervals are measured against the payload's
            own <Mono>observed_at</Mono>, never against this browser&apos;s clock.
          </p>
        </div>

        <div className={styles.block}>
          <h4 className={styles.blockTitle}>the appraisal</h4>
          <dl className={styles.facts}>
            <dt>score</dt>
            <dd>
              <Mono data-testid="site-score">{propagation.score}</Mono>
            </dd>
            <dt>model_version</dt>
            <dd>
              <Mono data-testid="site-model-version">{propagation.model_version}</Mono>
            </dd>
            <dt>open_conflicts</dt>
            <dd>
              <Mono data-testid="site-open-conflicts">{propagation.open_conflicts}</Mono>
            </dd>
          </dl>
          <p className={styles.note}>
            The score is a fleet-appraisal model&apos;s applicability estimate, always rendered
            beside the model version that produced it. It is not a gate value: no state
            transition on this screen reads it.
          </p>
        </div>

        <div className={styles.block}>
          <h4 className={styles.blockTitle}>what the site did</h4>
          <dl className={styles.facts}>
            <dt>adopted_commit</dt>
            <dd>
              {adoptedCommit === null ? (
                <span className={styles.absent}>none</span>
              ) : (
                <Digest
                  value={adoptedCommit}
                  label="adopted_commit"
                  data-testid="site-adopted-commit"
                />
              )}
            </dd>
            <dt>already_present_clause</dt>
            <dd>
              {alreadyPresent === null ? (
                <span className={styles.absent}>none</span>
              ) : (
                <>
                  <Mono data-testid="site-already-present">{alreadyPresent}</Mono>
                  <p className={styles.note}>
                    Convergent evolution: the site already carried the control. That is
                    evidence FOR the site and it is rendered as such.
                  </p>
                </>
              )}
            </dd>
          </dl>
        </div>

        <Declination row={row} />
      </div>
    </li>
  );
}
