// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE EVIDENCE VIEW — the screen on which the console audits its own inputs.
 *
 * Every other surface renders a claim about a permit, a clause or a ledger. This one
 * renders a claim about the console: *every byte the other screens showed you came from
 * a file in this table, and this browser recomputed the SHA-256 of each one against the
 * digest the manifest declares.* It is the surface that makes `docs/leads/ui.md` D6
 * checkable rather than asserted — a reader with `sha256sum` and the same directory
 * reproduces every number on the page.
 *
 * FOUR THINGS THIS SCREEN WILL NOT DO.
 *
 * 1. It will not show a seal it did not earn. No digest oracle (an insecure origin, so
 *    no WebCrypto) produces `unverified` with the reason, never `verified` and never
 *    `failed` — the bundle has not been accused of anything, and "we could not check"
 *    must not read as either verdict.
 * 2. It will not render a partial inventory beside an error. The audit settles or it
 *    does not; a half-table looks like a finding.
 * 3. It will not summarise a finding. `{subject, check, detail}` reaches the DOM exactly
 *    as the audit produced it.
 * 4. It will not claim the absence of a smuggled file unless the source could enumerate
 *    itself. `not established` is a different word from `none`.
 *
 * The screen publishes into the honesty chrome (D16) only what it actually established:
 * the manifest digest prefix, the seal state, and a detail that NAMES the check so a
 * stronger seal from the custody verifier is visibly a different sentence.
 */

import { useEffect, useMemo, type ReactNode } from 'react';

import { useHonestyPublisher } from '../../app/honesty';
import type { BundleSource } from '../../data/bundle';
import type { SchemaRegistry } from '../../data/schema';
import {
  Digest,
  Mono,
  ProvenanceChip,
  RegisterFrame,
  Rule,
  StagedBadge,
  VerificationSeal,
} from '../../design/primitives';

import { CoveragePanel } from './CoveragePanel';
import type { AuditedBundle } from './audit';
import { resolveDigestOracle, type DigestOracle } from './digest';
import styles from './evidence.module.css';
import { FindingsPanel, GapsPanel, LimitsPanel } from './FindingsPanel';
import { InventoryTable } from './InventoryTable';
import { resourcesWithoutFrame } from './model';
import {
  bundleSourceFor,
  paramsFromLocation,
  resolveBundleLocation,
  type BundleEnvironment,
} from './source';
import { useBundleAudit } from './useBundleAudit';

export interface EvidenceScreenProps {
  /** Overrides the location-derived source. `null` forces the not-configured state. */
  readonly source?: BundleSource | null;
  /** Overrides the platform oracle. `null` forces the not-checked state. */
  readonly oracle?: DigestOracle | null;
  readonly registry?: SchemaRegistry;
  /** ISO-8601 UTC instant. Frozen by cinema mode (D12) so screenshots are stable. */
  readonly clock?: () => string;
  readonly params?: URLSearchParams;
  readonly env?: BundleEnvironment;
}

function locationKey(): string {
  if (typeof window === 'undefined') return '';
  return `${window.location.search}${window.location.hash}`;
}

function Identity({ audit }: { readonly audit: AuditedBundle }): ReactNode {
  const { manifest } = audit;
  const fingerprint = manifest.cluster_fingerprint;
  return (
    <dl className={styles.identity} data-testid="evidence-identity">
      <dt>Bundle</dt>
      <dd>
        <Mono>{manifest.bundle_id}</Mono>
      </dd>

      <dt>Read from</dt>
      <dd>
        <Mono>{audit.sourceId}</Mono>
      </dd>

      <dt>Captured</dt>
      <dd>
        <Mono>{manifest.captured_at}</Mono>
      </dd>

      <dt>Generator</dt>
      <dd>
        <Mono>{manifest.generator ?? 'not declared'}</Mono>
      </dd>

      <dt>Schema</dt>
      <dd>
        <Mono>{manifest.schema_version}</Mono>
      </dd>

      <dt>Cluster</dt>
      <dd>
        <Mono>
          {fingerprint.product} {fingerprint.version}
          {fingerprint.cluster_version === null || fingerprint.cluster_version === undefined
            ? ''
            : ` · cluster ${fingerprint.cluster_version}`}
          {fingerprint.tier === null || fingerprint.tier === undefined
            ? ''
            : ` · ${fingerprint.tier}`}{' '}
          · {fingerprint.region}
        </Mono>{' '}
        <ProvenanceChip
          kind={fingerprint.source === 'observed' ? 'db:column' : 'staged'}
          detail={
            fingerprint.source === 'observed'
              ? 'read from the cluster during this capture'
              : 'declared by whoever produced the bundle; not observed'
          }
        />
        {fingerprint.evidence_ref === null || fingerprint.evidence_ref === undefined ? null : (
          <p className={styles.note}>{fingerprint.evidence_ref}</p>
        )}
      </dd>

      <dt>Checkpoint</dt>
      <dd>
        {manifest.checkpoint === null ? (
          <span className={styles.kind}>none carried</span>
        ) : (
          <>
            <Mono>
              {manifest.checkpoint.site_code} · tree size {manifest.checkpoint.tree_size} ·{' '}
              {manifest.checkpoint.note_path}
            </Mono>
            <p className={styles.note}>
              Its root and its signature are NOT checked here — that is the custody surface&rsquo;s
              RFC 6962 and ECDSA work. On this screen the note is one more file with one more
              digest.
            </p>
          </>
        )}
      </dd>
    </dl>
  );
}

function Audited({ audit }: { readonly audit: AuditedBundle }): ReactNode {
  const gaps = useMemo(() => resourcesWithoutFrame(audit.rows), [audit.rows]);
  const failureReason =
    audit.findings[0] === undefined
      ? 'no finding was recorded, yet the verdict is failed — report this as a defect in the audit.'
      : `${audit.findings.length} finding(s); first: ${audit.findings[0].check} on ${audit.findings[0].subject}`;

  return (
    <>
      <section aria-labelledby="evidence-bundle-heading">
        <h3 className={styles.sectionTitle} id="evidence-bundle-heading">
          The bundle
        </h3>
        <div className={styles.sealRow}>
          {audit.verdict === 'verified' ? (
            <VerificationSeal
              state="verified"
              subject="manifest integrity"
              data-testid="evidence-seal"
              recomputation={{
                algorithm: `SHA-256 over the sealed bytes (${audit.oracleName})`,
                at: audit.at,
                digestPrefix: audit.manifestDigest.slice(0, 12),
              }}
            />
          ) : (
            <VerificationSeal
              state="failed"
              subject="manifest integrity"
              data-testid="evidence-seal"
              reason={failureReason}
            />
          )}
          {audit.manifest.staged ? (
            <StagedBadge
              what={
                audit.manifest.staged_note ??
                'the manifest says staged but gives no note, which is itself a defect in the bundle'
              }
              data-testid="evidence-staged"
            />
          ) : null}
        </div>
        <Digest
          value={audit.manifestDigest}
          label="manifest.json sha256, recomputed here"
          data-testid="evidence-manifest-digest"
        />
        <p className={styles.note}>
          manifest.json is the one file whose digest is not inside itself. Compare this value
          against one you obtained by another route; nothing on this page can do that for you.
        </p>
        <Rule variant="section" />
        <Identity audit={audit} />
      </section>

      <section aria-labelledby="evidence-coverage-heading">
        <h3 className={styles.sectionTitle} id="evidence-coverage-heading">
          Coverage
        </h3>
        <CoveragePanel coverage={audit.coverage} />
      </section>

      <section aria-labelledby="evidence-inventory-heading">
        <h3 className={styles.sectionTitle} id="evidence-inventory-heading">
          Inventory
        </h3>
        <InventoryTable rows={audit.rows} />
      </section>

      <section aria-labelledby="evidence-findings-heading">
        <h3 className={styles.sectionTitle} id="evidence-findings-heading">
          Findings
        </h3>
        <FindingsPanel findings={audit.findings} />
      </section>

      <section aria-labelledby="evidence-gaps-heading">
        <h3 className={styles.sectionTitle} id="evidence-gaps-heading">
          Declared resources with no captured exchange
        </h3>
        <GapsPanel gaps={gaps} />
      </section>

      <section aria-labelledby="evidence-limits-heading">
        <h3 className={styles.sectionTitle} id="evidence-limits-heading">
          What a clean audit does not establish
        </h3>
        <LimitsPanel />
      </section>
    </>
  );
}

export function EvidenceScreen(props: EvidenceScreenProps): ReactNode {
  const { source, oracle, registry, clock, params, env } = props;
  const publish = useHonestyPublisher();

  const key = locationKey();
  const effectiveParams = useMemo(() => {
    if (params !== undefined) return params;
    const mark = key.indexOf('#');
    return paramsFromLocation(mark >= 0 ? key.slice(0, mark) : key, mark >= 0 ? key.slice(mark) : '');
  }, [params, key]);

  const environment: BundleEnvironment = env ?? import.meta.env;
  const location = useMemo(
    () => resolveBundleLocation(effectiveParams, environment),
    [effectiveParams, environment],
  );
  const derivedSource = useMemo(() => bundleSourceFor(location), [location]);
  const activeSource = source === undefined ? derivedSource : source;

  const oracleResolution = useMemo(() => resolveDigestOracle(), []);
  const derivedOracle = oracleResolution.ok ? oracleResolution.oracle : null;
  const activeOracle = oracle === undefined ? derivedOracle : oracle;

  const reason =
    activeSource === null
      ? location.why
      : activeOracle === null
        ? oracleResolution.ok
          ? 'no digest oracle was supplied to this screen, so nothing below has been hashed.'
          : oracleResolution.reason
        : '';

  const state = useBundleAudit({
    source: activeSource,
    oracle: activeOracle,
    reason,
    ...(registry === undefined ? {} : { registry }),
    ...(clock === undefined ? {} : { clock }),
  });

  // Only what this screen actually established reaches the chrome. `transport` is not
  // published here: this surface reads a directory, it is not the transport, and a
  // surface that told the chrome what mode the console is in would be guessing.
  useEffect(() => {
    if (state.status === 'settled' && state.audit.kind === 'audited') {
      const audit = state.audit;
      publish({
        seal: audit.verdict === 'verified' ? 'verified' : 'failed',
        bundleDigestPrefix: audit.manifestDigest.slice(0, 12),
        sealDetail:
          `manifest integrity only: ${audit.coverage.digestsMatched} of ` +
          `${audit.coverage.filesDeclared} listed file(s) hash to their declared SHA-256, ` +
          `recomputed in this browser by ${audit.oracleName}. The carried ledger is NOT ` +
          'verified by this check.',
      });
      return;
    }
    if (state.status === 'unavailable') {
      publish({ seal: 'unverified', sealDetail: state.reason });
      return;
    }
    if (state.status === 'auditing') {
      publish({ seal: 'verifying', sealDetail: 'hashing the files this bundle lists' });
    }
  }, [state, publish]);

  return (
    // `?? ''` because `noUncheckedIndexedAccess` types a CSS-module lookup as
    // `string | undefined`, and RegisterFrame's `className` is exactly-optional.
    <RegisterFrame register="evidence" className={styles.screen ?? ''} data-testid="evidence-screen">
      <header>
        <h2 className={styles.title}>Evidence — the bundle this console is reading</h2>
        <p className={styles.standfirst}>
          Every byte on every other screen came from a file listed below. This browser read each
          one and recomputed its SHA-256 against the digest <code>manifest.json</code> declares.
          Nothing here is the database&rsquo;s word for it; it is arithmetic you can repeat with{' '}
          <code>sha256sum</code>.
        </p>
      </header>

      {state.status === 'idle' ? (
        <section className={styles.absent} role="status" data-testid="evidence-no-bundle">
          <p className={styles.absentTitle}>No bundle to audit</p>
          <p className={styles.standfirst}>{state.reason}</p>
        </section>
      ) : state.status === 'unavailable' ? (
        <section className={styles.absent} role="status" data-testid="evidence-no-oracle">
          <p className={styles.absentTitle}>Nothing has been checked</p>
          <p className={styles.standfirst}>{state.reason}</p>
          <VerificationSeal
            state="unverified"
            subject="manifest integrity"
            reason="no digest oracle on this origin"
            data-testid="evidence-seal"
          />
        </section>
      ) : state.status === 'auditing' ? (
        <p className={styles.status} role="status" data-testid="evidence-auditing">
          Hashing {state.total === null ? 'the files this bundle lists' : `${state.done} of ${state.total} files`}…
        </p>
      ) : state.status === 'error' ? (
        <section className={styles.failure} role="alert" data-testid="evidence-error">
          <p className={styles.failureTitle}>The audit itself failed</p>
          <pre className={styles.verbatim}>{state.detail}</pre>
          <p className={styles.note}>
            This is a fault in the console, not a claim about the bundle. Nothing has been
            established either way.
          </p>
        </section>
      ) : state.audit.kind === 'audited' ? (
        <Audited audit={state.audit} />
      ) : (
        <section className={styles.failure} role="alert" data-testid="evidence-unusable">
          <p className={styles.failureTitle}>
            {state.audit.kind === 'unreadable'
              ? `Could not read ${state.audit.where}`
              : `${state.audit.where} is not a manifest this console can read`}
          </p>
          <pre className={styles.verbatim}>{state.audit.detail}</pre>
          <p className={styles.note}>
            Source: <Mono>{state.audit.sourceId}</Mono>. The transport refuses such a bundle
            before serving anything, so no screen in this console can be fed from it.
          </p>
        </section>
      )}
    </RegisterFrame>
  );
}
