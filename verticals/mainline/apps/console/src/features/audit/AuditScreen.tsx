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
 * ── HOW THESE BYTES GOT HERE IS A FACT ABOUT THE TRANSPORT, NOT A CONSTANT ───────
 *
 * This screen shows no seal, and it has to say WHY without claiming a check that did not
 * run. Under REPLAY the bytes came through a bundle whose every file digest and whose
 * checkpoint were recomputed in this browser before a frame was served. Under LIVE they
 * came off the wire and NO bundle was consulted at all. Those are different sentences and
 * the screen prints whichever one is true of the transport that is actually mounted —
 * `describe().mode`, off the object holding the bytes.
 *
 * It shipped for a while printing the REPLAY sentence unconditionally, on a LIVE demo,
 * two inches under an honesty strip that said no bundle had been opened. That is a
 * must-not-claim violation on the screen whose subject is auditability, and it is the
 * reason this paragraph is written down rather than assumed.
 */

import { type ReactNode } from 'react';

import { useResource } from '../../data/useResource';
import {
  Disclosure,
  Gloss,
  Mono,
  PlainBand,
  ProvenanceChip,
  RegisterFrame,
  StagedBadge,
  labelFor,
} from '../../design/primitives';

import styles from './audit.module.css';
import { emptinessReason, readCarriage, tallyCalls, type AuditPayload } from './model';
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

/**
 * The two true sentences, keyed by the transport that is actually mounted.
 *
 * Both say the same thing about THIS screen — it has no per-claim arithmetic of its own,
 * so it shows no seal — and they differ only in what they are allowed to say about how
 * the bytes arrived. Neither is a summary of the other and neither may be used as a
 * default: a screen with no transport never reaches this point, because `NoSource`
 * returns first.
 */
const SEAL_NOTE: Readonly<Record<'live' | 'replay', string>> = {
  replay:
    'No seal is shown on this screen. The bytes reached it through a bundle whose every ' +
    'file digest and whose checkpoint were recomputed in this browser — that verification ' +
    'is reported in the honesty strip above and, in full, on the custody surface. This ' +
    'screen has no per-claim arithmetic of its own to display, and a tick with nothing ' +
    'behind it is decoration.',
  live:
    'No seal is shown on this screen, and no bundle was consulted to produce it. The bytes ' +
    'reached it from the live kernel over the wire, so nothing on this screen was ' +
    'recomputed in this browser and the honesty strip above says exactly that. The ' +
    'arithmetic that IS recomputed against live bytes is the custody surface’s — it reruns ' +
    'the RFC 6962 inclusion and consistency hashes over the ledger it was served and prints ' +
    'its own verdict there. This screen has no per-claim arithmetic of its own to display, ' +
    'and a tick with nothing behind it is decoration.',
};

/**
 * The terms this screen uses, glossed beside them and never instead of them (R8).
 *
 * `row cap` and `byte cap` are not in `glossary.ts` — R7's table does not reach them — so
 * their sentences are written beside them where they are used, in `capsPlain()`, which
 * derives every number from the view's own declared limits rather than writing one down.
 */
const GLOSSED_HERE: readonly string[] = ['sqlstate', 'transport', 'staged', 'provenance-chip'];

export function AuditScreen(): ReactNode {
  const transport = useAuditTransport();
  const resource = useResource<AuditPayload>(transport, { resource: 'audit' });

  if (transport === null) return <NoSource />;

  const mode = transport.describe().mode;
  const payload = resource.state.status === 'ready' ? resource.state.data : null;
  const envelope = resource.state.status === 'ready' ? resource.state.exchange.envelope : null;
  const calls = payload?.calls ?? [];
  const tally = tallyCalls(calls);
  const carriage = readCarriage(payload?.views ?? []);

  /*
   * COMPUTED ONCE AND HANDED DOWN, so every zero on this screen is answered by the SAME
   * sentence out of the SAME payload. Two panels composing their own explanation is two
   * chances for one of them to say something softer than the other, and the softer one is
   * the one a judge would quote.
   */
  const emptiness = emptinessReason(payload?.unreachable ?? []);

  return (
    <RegisterFrame register="evidence" as="section" label="Audit" data-testid="audit-surface">
      <div className={styles.surface}>
        <PlainBand
          kicker="this screen, in plain words"
          data-testid="audit-plain-band"
          sentences={[
            'Every question an automated agent asks this database is written down: which account ' +
              'asked, the one statement it sent, the limits it was allowed, and what came back — ' +
              'including a refusal.',
            'This page is that record, read back. It is the read-only account looking at itself, ' +
              'so nothing here can be a claim about a person: the tables that hold per-person ' +
              'measures are named below as ones this account cannot reach.',
            'Where a table below is empty, the page says why it is empty rather than leaving a ' +
              'blank — and an empty answer is a fact about what was reachable here, never a claim ' +
              'that nothing exists.',
          ]}
        >
          <Disclosure
            summary="Show what each word on this page means"
            note="the exact terms stay; this adds a sentence beside each one"
            data-testid="audit-glossary"
          >
            <ul className={styles.plainList}>
              {GLOSSED_HERE.map((key) => (
                <li key={key}>
                  <Gloss term={key} layout="stack">
                    <Mono>{labelFor(key) ?? key}</Mono>
                  </Gloss>
                </li>
              ))}
              <li>
                <Mono>aggregate</Mono>{' '}
                <span className={styles.columnType}>
                  — a view that answers with counts and totals rather than with the underlying
                  rows, so a reader learns the shape of the data without being handed the data.
                </span>
              </li>
              <li>
                <Mono>row cap · byte cap</Mono>{' '}
                <span className={styles.columnType}>
                  — the most rows and the most bytes this account is allowed in one answer. They
                  are limits on the QUESTION, not properties of the data, and each table below
                  states the exact numbers it ran under.
                </span>
              </li>
              <li>
                <Mono>truncation flag</Mono>{' '}
                <span className={styles.columnType}>
                  — a column a view carries to say whether what it counted was complete. A view
                  that carries none makes no completeness claim, and this page says so rather than
                  filling the gap.
                </span>
              </li>
            </ul>
          </Disclosure>
        </PlainBand>

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

          {/*
            * R6: PLAIN collapses the byte and row caps and the column contracts into a control
            * that names what is inside it. Not one word of this paragraph changed and nothing was
            * removed — the plain band above now carries the reading a first-time reader needs,
            * and the exact statement of the functional requirement is one click away in PLAIN and
            * open by default in FULL DETAIL.
            */}
          <Disclosure
            summary="Show the exact size limit these views are built to, and who owns their columns"
            data-testid="audit-product-surface-detail"
          >
            <p className={styles.prose}>
              These views are a product surface, and their size limit is a functional requirement:
              each returns at most 25 rows and 10 KiB, is aggregate-first, depends on no system
              catalog, and carries <code>ancestry_complete</code> or an equivalent truncation flag.
              The console holds no column list for any of them — the column contracts belong to the
              recall and MCP domains, and each table below is rendered from the columns its own
              payload declared.
            </p>
          </Disclosure>

          <dl className={styles.facts}>
            <div className={styles.fact}>
              <dt className={styles.factLabel}>views carried</dt>
              <dd className={styles.factValue} data-testid="view-count">
                {carriage.total}
              </dd>
            </div>
            <div className={styles.fact}>
              <dt className={styles.factLabel}>views that returned rows</dt>
              <dd className={styles.factValue} data-testid="views-carrying-rows">
                {carriage.carrying.length} of {carriage.total}
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

          <p className={styles.detail} data-testid="audit-seal-note" data-transport={mode}>
            {SEAL_NOTE[mode]}
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
              {carriage.total === 0 ? (
                <p className={styles.prose} data-testid="audit-no-views">
                  No view was carried. That is a claim that nothing was read, not a claim that
                  nothing exists.
                </p>
              ) : (
                <>
                  {/*
                    Above the tables, because it changes how the first one is read: the
                    reader who scrolled an empty `v_agent_actions` and concluded the whole
                    surface was empty was reading six views' worth of rows further down.
                  */}
                  <p className={styles.detail} data-testid="audit-carriage">
                    {carriage.detail}
                  </p>
                  {carriage.ordered.map((view) => (
                    <ViewTable key={view.view} view={view} emptiness={emptiness} />
                  ))}
                </>
              )}
            </section>

            <CallLog calls={calls} emptiness={emptiness} />

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
