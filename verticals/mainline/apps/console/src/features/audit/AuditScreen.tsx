// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The audit surface — aggregate-first, generic, and honest about its own caps.
 *
 * `ARCHITECTURE.md` §17: the `mainline_audit.v_*` views are a PRODUCT SURFACE and their
 * size limit is a functional requirement — ≤ 25 rows, ≤ 10 KiB, aggregate-first, carrying
 * `ancestry_complete` or an equivalent truncation flag. This screen renders them from the
 * columns they declare, prints the caps each read ran under above the data, and puts the
 * completeness flag where a reader sees it before the numbers rather than after.
 *
 * It is an EVIDENCE-register surface: nothing moves, everything prints, and every number
 * is rendered verbatim. It computes no aggregate of its own — the tallies it shows
 * (`ok / refused / error`, distinct scopes) are counts of ROWS THE PAYLOAD CARRIED, which
 * is arithmetic over what is on screen rather than a claim about what is in the database.
 *
 * The bytes reaching this screen came through a bundle the in-browser verifier already
 * checked; the seal for that is the honesty chrome's, not this screen's, because this
 * screen has no per-claim recomputation to show. Saying so, rather than borrowing the
 * custody surface's seal, is the difference between a verified claim and a decorated one.
 */

import { type ReactNode } from 'react';

import { useResource } from '../../data/useResource';
import { ProvenanceChip, RegisterFrame, StagedBadge } from '../../design/primitives';

import styles from './audit.module.css';
import { tallyCalls, type AuditPayload } from './model';
import { CallLog } from './parts/CallLog';
import { ReachPanel } from './parts/ReachPanel';
import { ViewTable } from './parts/ViewTable';
import { useAuditTransport } from './transport-context';

function NoSource(): ReactNode {
  return (
    <div className={styles.surface} data-testid="audit-no-source">
      <section className={styles.failure} aria-label="No source">
        <span className={styles.kicker}>no source</span>
        <p className={styles.prose}>
          No transport has been composed for this surface, so no audit payload has reached this
          browser. This screen does not build its own transport: <code>BundleTransport</code> has
          no default verifier, and manufacturing a permissive one to make a screen paint is
          exactly the lie the transport was shaped to prevent.
        </p>
      </section>
    </div>
  );
}

export function AuditScreen(): ReactNode {
  const transport = useAuditTransport();
  const resource = useResource<AuditPayload>(transport, { resource: 'audit' });

  if (transport === null) return <NoSource />;

  const payload = resource.state.status === 'ready' ? resource.state.data : null;
  const envelope = resource.state.status === 'ready' ? resource.state.exchange.envelope : null;
  const calls = payload?.calls ?? [];
  const tally = tallyCalls(calls);

  return (
    <RegisterFrame register="evidence" as="section" label="Audit" data-testid="audit-surface">
      <div className={styles.surface}>
        <header className={styles.header}>
          <div className={styles.headerTop}>
            <span className={styles.kicker}>audit · the MCP surface</span>
            <h2 className={styles.title}>mainline_audit</h2>
            {envelope?.staged === true ? (
              <StagedBadge what={envelope.staged_note ?? 'no note supplied'} />
            ) : null}
            <ProvenanceChip
              kind="db:column"
              detail="every value below is rendered verbatim from the payload"
            />
          </div>

          <p className={styles.prose}>
            These views are a product surface, and their size limit is a functional requirement:
            each returns at most 25 rows and 10 KiB, is aggregate-first, depends on no system
            catalog, and carries <code>ancestry_complete</code> or an equivalent truncation flag.
            The console holds no column list for any of them — the column contracts belong to the
            recall and MCP domains, and each table below is rendered from the columns its own
            payload declared.
          </p>

          <dl className={styles.facts}>
            <div className={styles.fact}>
              <dt className={styles.factLabel}>views carried</dt>
              <dd className={styles.factValue} data-testid="view-count">
                {payload?.views.length ?? 0}
              </dd>
            </div>
            <div className={styles.fact}>
              <dt className={styles.factLabel}>MCP calls carried</dt>
              <dd className={styles.factValue}>{tally.total}</dd>
            </div>
            <div className={styles.fact}>
              <dt className={styles.factLabel}>observed at</dt>
              <dd className={styles.factValue}>{envelope?.observed_at ?? 'not stated'}</dd>
            </div>
          </dl>

          <p className={styles.detail} data-testid="audit-seal-note">
            No seal is shown on this screen. The bytes reached it through a bundle whose every
            file digest and whose checkpoint were recomputed in this browser — that verification
            is reported in the honesty strip above and, in full, on the custody surface. This
            screen has no per-claim arithmetic of its own to display, and a tick with nothing
            behind it is decoration.
          </p>
        </header>

        {resource.state.status === 'failed' ? (
          <section className={styles.failure} role="alert" data-testid="audit-transport-failure">
            <span className={styles.kicker}>{resource.state.failure}</span>
            <p className={styles.detail}>{resource.state.detail}</p>
          </section>
        ) : null}

        {resource.state.status === 'loading' ? (
          <section className={styles.section} data-testid="audit-loading">
            <p className={styles.prose}>Reading the audit views…</p>
          </section>
        ) : null}

        {payload === null ? null : (
          <>
            <section className={styles.section} aria-label="Audit views">
              <h3 className={styles.sectionTitle}>The aggregates</h3>
              {payload.views.length === 0 ? (
                <p className={styles.prose} data-testid="audit-no-views">
                  No view was carried. That is a claim that nothing was read, not a claim that
                  nothing exists.
                </p>
              ) : (
                payload.views.map((view) => <ViewTable key={view.view} view={view} />)
              )}
            </section>

            <CallLog calls={calls} />

            <ReachPanel probes={payload.unreachable ?? []} />

            <section className={styles.section} aria-label="What this surface does not show">
              <h3 className={styles.sectionTitle}>What this surface does not show</h3>
              <ul className={styles.plainList}>
                <li>
                  No timing. <code>EXPLAIN ANALYZE</code> is not available on the Managed MCP
                  surface, so every plan fragment above is a plan and never a measurement.
                </li>
                <li>
                  No per-person measure. Those live in <code>mainline_qa</code>, gated to the
                  quality-assurance role, with every SELECT writing a <code>profile_read</code>{' '}
                  ledger entry — and no MCP service account is ever issued for that schema.
                </li>
                <li>
                  No completeness claim beyond the flags above. A view with no truncation flag
                  makes none, and this screen says so rather than filling the gap.
                </li>
              </ul>
            </section>
          </>
        )}
      </div>
    </RegisterFrame>
  );
}
