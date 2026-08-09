// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The custody room.
 *
 * Every seal on this screen is green ONLY because the Web Worker in `src/verify/`
 * recomputed the claim behind it in this browser, from the same bytes `trappoint-verify`
 * consumes — and the recomputation is displayed beside the seal, so a reader who does not
 * believe the tick can read the digits and repeat the arithmetic in Python.
 *
 * The screen is a pure rendering of two objects: the `ledger` payload the transport
 * served, and the `CheckReport` the worker produced. It computes no verdict itself. That
 * is D5 one hop downstream — if this component could decide that a check passed, the
 * flagship claim would be launderable in TypeScript.
 *
 * Four states, and none of them is a partial render:
 *
 *   NO SOURCE      no transport was composed. Says what is missing, shows nothing else.
 *   loading        the payload is in flight.
 *   failed         the transport refused — which, in replay, is what a tampered bundle
 *                  looks like. The detail is shown verbatim, because it names the file
 *                  and both digests.
 *   ready          the payload arrived; the verification report is rendered as it settles.
 */

import { useEffect, useMemo, type ReactNode } from 'react';

import { useHonestyPublisher, type SealState } from '../../app/honesty';
import { useResource } from '../../data/useResource';
import { Digest, ProvenanceChip, RegisterFrame, StagedBadge, VerificationSeal } from '../../design/primitives';
import { useVerification } from '../../verify/useVerification';
import { resolveVerifierConfig } from '../../verify/config';
import { PER_BOUND, type LedgerPayload } from '../../verify/ledger';

import styles from './custody.module.css';
import { chainLayers, overallSeal, quorumShape, tally } from './model';
import { ChainView } from './parts/ChainView';
import { CheckList } from './parts/CheckList';
import { CheckpointPanel } from './parts/CheckpointPanel';
import { WitnessPanel } from './parts/WitnessPanel';
import {
  useCustodyConfig,
  useCustodyTransport,
  useCustodyVerifier,
} from './transport-context';

export const DEFAULT_SITE_CODE = 'BLK-07';

function NoSource(): ReactNode {
  return (
    <div className={styles.surface} data-testid="custody-no-source">
      <section className={styles.failure} aria-label="No source">
        <span className={styles.kicker}>no source</span>
        <p className={styles.prose}>
          No transport has been composed for this surface, so no bytes have reached this
          browser and nothing has been verified. This screen does not build its own transport:{' '}
          <code>BundleTransport</code> has no default verifier, and manufacturing a permissive
          one to make a screen paint is exactly the lie the transport was shaped to prevent.
        </p>
      </section>
    </div>
  );
}

export function CustodyScreen({
  siteCode = DEFAULT_SITE_CODE,
}: {
  readonly siteCode?: string;
}): ReactNode {
  const transport = useCustodyTransport();
  const suppliedVerifier = useCustodyVerifier();
  const suppliedConfig = useCustodyConfig();

  const resource = useResource<LedgerPayload>(transport, {
    resource: 'ledger',
    query: { site_code: siteCode },
  });

  const payload = resource.state.status === 'ready' ? resource.state.data : null;
  const envelope = resource.state.status === 'ready' ? resource.state.exchange.envelope : null;

  /*
   * MEMOISED, and the memo is load-bearing rather than a performance nicety.
   *
   * `resolveVerifierConfig()` reads the build constants and the URL and returns a FRESH
   * object every call. Passing it inline would give `useVerification` a new `config`
   * identity on every render, its effect would re-run, its `setState` would render again,
   * and the screen would spin without ever settling — an infinite loop that presents as a
   * verification that never finishes, which is the worst possible failure mode for a
   * surface whose whole subject is whether the arithmetic ran.
   */
  const config = useMemo(() => suppliedConfig ?? resolveVerifierConfig(), [suppliedConfig]);

  const verification = useVerification({
    payload,
    reason:
      transport === null
        ? 'No transport has been composed, so no ledger payload has reached this browser.'
        : 'The ledger payload has not arrived yet, so nothing has been recomputed.',
    config,
    ...(suppliedVerifier === null ? {} : { verifier: suppliedVerifier }),
  });

  const report = verification.status === 'settled' ? verification.report : null;
  const info = verification.status === 'settled' ? verification.info : null;
  const counts = tally(report);
  const at = report?.at ?? '';

  /*
   * The honesty chrome's seal (D16) is published from HERE, because this is the only
   * place in the console that holds a verification report. `bounded` maps to
   * `unverified`, not to `verified`: a report containing a SKIP is not a clean report,
   * and an amber seal beside a screen with six unrun checks is the truthful rendering.
   */
  const publish = useHonestyPublisher();
  const sealState: SealState =
    verification.status === 'verifying'
      ? 'verifying'
      : report === null
        ? 'unverified'
        : report.overall === 'fail'
          ? 'failed'
          : report.overall === 'bounded'
            ? 'unverified'
            : 'verified';
  const sealDetail = report?.summary ?? null;
  useEffect(() => {
    publish({ seal: sealState, sealDetail });
  }, [publish, sealState, sealDetail]);

  if (transport === null) return <NoSource />;

  return (
    <RegisterFrame register="evidence" as="section" label="Custody" data-testid="custody-surface">
      <div className={styles.surface}>
        <header className={styles.header}>
          <div className={styles.headerTop}>
            <span className={styles.kicker}>custody · the chain</span>
            <h2 className={styles.title}>Site {siteCode}</h2>
            <VerificationSeal {...overallSeal(report, at)} data-testid="custody-overall-seal" />
            {envelope?.staged === true ? (
              <StagedBadge what={envelope.staged_note ?? 'no note supplied'} />
            ) : null}
          </div>

          <p className={styles.prose}>
            Nothing on this screen is the database&rsquo;s word. Every seal below is the result
            of arithmetic this browser performed on the bytes it was served: RFC 8785
            canonicalisation, RFC 6962 leaf, node, inclusion and consistency hashing, and the
            ECDSA P-256 signature over the checkpoint note. The recomputations are shown, and a
            stranger can run the same arithmetic offline with{' '}
            <code>pipx run trappoint-verify</code>.
          </p>

          <dl className={styles.facts}>
            <div className={styles.fact}>
              <dt className={styles.factLabel}>verifier</dt>
              <dd className={styles.factValue} data-testid="verifier-transport">
                {info === null ? 'starting' : `${info.transport} · ${info.oracleName}`}
              </dd>
            </div>
            <div className={styles.fact}>
              <dt className={styles.factLabel}>checks passed / failed / not run</dt>
              <dd className={styles.factValue} data-testid="check-tally">
                {counts.pass} / {counts.fail} / {counts.skip}
              </dd>
            </div>
            <div className={styles.fact}>
              <dt className={styles.factLabel}>offline checks</dt>
              <dd className={styles.factValue}>
                {counts.offline} — need no access to our database and no cooperation from us
              </dd>
            </div>
            <div className={styles.fact}>
              <dt className={styles.factLabel}>recomputed at</dt>
              <dd className={styles.factValue}>{at === '' ? 'not yet' : at}</dd>
            </div>
          </dl>

          {info === null || info.transportNote === '' ? null : (
            <p className={styles.detail} data-testid="verifier-transport-note">
              {info.transportNote}
            </p>
          )}
          {info === null || info.oracleNote === '' ? null : (
            <p className={styles.detail} data-testid="verifier-oracle-note">
              {info.oracleNote}
            </p>
          )}
        </header>

        {resource.state.status === 'failed' ? (
          <section className={styles.failure} role="alert" data-testid="custody-transport-failure">
            <span className={styles.kicker}>{resource.state.failure}</span>
            <p className={styles.detail}>{resource.state.detail}</p>
            <p className={styles.prose}>
              No frame was served, so nothing below has been rendered from bundle bytes. In
              replay this is what a tampered bundle looks like: the transport cannot serve a
              frame until the verifier has resolved, and it does not become verified by asking
              again.
            </p>
          </section>
        ) : null}

        {resource.state.status === 'loading' ? (
          <section className={styles.section} data-testid="custody-loading">
            <p className={styles.prose}>Reading the ledger…</p>
          </section>
        ) : null}

        {verification.status === 'failed' ? (
          <section className={styles.failure} role="alert" data-testid="custody-verifier-failure">
            <span className={styles.kicker}>the verifier itself failed</span>
            <p className={styles.detail}>{verification.detail}</p>
            <p className={styles.prose}>
              This is not a finding against the ledger. The verifier could not complete, so
              nothing has been established either way, and no seal on this screen is green.
            </p>
          </section>
        ) : null}

        {payload === null ? null : (
          <>
            <section className={styles.section} aria-label="The custody chain">
              <h3 className={styles.sectionTitle}>The chain, layer by layer</h3>
              <ChainView
                layers={chainLayers(
                  payload,
                  report?.checks.find((check) => check.name === 'inclusion_proof')?.recomputations[0]
                    ?.computed ?? null,
                )}
              />
            </section>

            <section className={styles.section} aria-label="Checks">
              <h3 className={styles.sectionTitle}>
                What was recomputed in this browser, and what was not
              </h3>
              {report === null ? (
                <p className={styles.prose} data-testid="custody-verifying">
                  {verification.status === 'verifying'
                    ? 'The worker is recomputing. No seal is green until it answers.'
                    : verification.status === 'idle'
                      ? verification.reason
                      : 'The verifier did not complete.'}
                </p>
              ) : (
                <>
                  <p className={styles.detail} data-testid="custody-summary">
                    {report.summary}
                  </p>
                  <CheckList checks={report.checks} at={report.at} />
                </>
              )}
            </section>

            {payload.checkpoints.map((checkpoint) => (
              <CheckpointPanel
                key={`${checkpoint.site_code}-${checkpoint.tree_size}`}
                checkpoint={checkpoint}
                signedTextSha256={
                  report?.checks
                    .find((check) => check.name === 'log_signature')
                    ?.recomputations.find((entry) =>
                      entry.input.endsWith(String(checkpoint.tree_size)),
                    )?.computed ?? ''
                }
              />
            ))}

            <WitnessPanel
              quorum={quorumShape(payload)}
              cosignatures={payload.cosignatures ?? []}
              debt={payload.unwitnessed_debt ?? []}
            />

            <section className={styles.section} aria-label="What this does not prove">
              <h3 className={styles.sectionTitle}>What this screen does not prove</h3>
              <ul className={styles.plainList}>
                <li>
                  Not that a disposition was sincere. Non-repudiation is cryptographic, not
                  moral.
                </li>
                <li>
                  Not that the narrative in an ingested document is true. Content authenticity is
                  out of scope; provenance — who submitted it, when, its hash, its Object Lock
                  version — is in scope.
                </li>
                <li>{PER_BOUND}</li>
                <li>
                  Not anything about state at a past time via <code>AS OF SYSTEM TIME</code>: the
                  cluster&rsquo;s garbage-collection window is 75 minutes, so long-horizon
                  versioning is the application-level commit DAG and nothing here reaches
                  further.
                </li>
              </ul>
              <div className={styles.facts}>
                <ProvenanceChip
                  kind="recomputed"
                  detail="every digest on this screen was computed in this browser"
                />
                {envelope === null ? null : (
                  <Digest
                    value={envelope.schema_id}
                    label="contract"
                    prefixLength={64}
                    copyable={false}
                  />
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </RegisterFrame>
  );
}
