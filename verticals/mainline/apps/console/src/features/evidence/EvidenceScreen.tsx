// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE EVIDENCE VIEW — the screen on which the console audits its own inputs.
 *
 * Every other surface renders a claim about a permit, a clause or a ledger. This one
 * renders a claim about the console: *this browser read every file the bundle lists and
 * recomputed the SHA-256 of each one against the digest the manifest declares.* It is the
 * surface that makes `docs/leads/ui.md` D6 checkable rather than asserted — a reader with
 * `sha256sum` and the same directory reproduces every number on the page.
 *
 * WHOSE BYTES THESE ARE, WHICH IS NOT ALWAYS THE OTHER SCREENS'. Until 2026-08-15 this
 * screen opened by asserting that every byte on every other surface came from the table
 * below. In REPLAY that is exactly true and it is still said, verbatim. On the LIVE
 * deployment it is false — `VITE_MAINLINE_API_BASE` is `/`, the transport is
 * `HttpTransport`, and no other screen has read a bundle byte — so the sentence is now
 * chosen by `model.ts`'s `transportCaveat` from the mode the composition root published
 * off `transport.describe()`. This screen reads that mode; it does not publish one, and it
 * does not guess when nobody has.
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
 *
 * ── TWO READERS, ONE SCREEN (2026-08-15) ─────────────────────────────────────────
 *
 * `docs/leads/two-audience-ux-plan.md` R6. **Nothing was deleted and no sentence got
 * vaguer.** What changed is the order a reader meets things in, and which of them start
 * collapsed:
 *
 *   always open — the seal and its reason, the transport note, the coverage arithmetic and
 *                 its conservation line, every finding, every declared resource with no
 *                 captured exchange, what a clean audit does NOT establish, the STAGED
 *                 badge, and the not-established-versus-none-found sentence. R6 forbids
 *                 collapsing any of these and this screen collapses none of them.
 *   one click   — the manifest's own digest, the capture's identity block, and the
 *                 file-by-file inventory with its declared and recomputed digests. All are
 *                 in the DOM in both states and all print open.
 */

import { useEffect, useMemo, type ReactNode } from 'react';

import { useHonesty, useHonestyPublisher, type TransportMode } from '../../app/honesty';
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
import { resourcesWithoutFrame, transportCaveat } from './model';
import { Disclosure, Gloss, PlainBand } from './Plain';
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
  /**
   * Overrides the mode this screen READS from the honesty chrome, for tests.
   *
   * It is only ever read. The chrome's `transport` slot belongs to the composition root,
   * which fills it from `transport.describe().mode` — off the object that holds the bytes.
   * A surface that published its own mode would be guessing, and this one has no transport
   * at all: it reads a directory.
   */
  readonly transport?: TransportMode;
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
        <Mono data-testid="evidence-source-id">{audit.sourceId}</Mono>
        <p className={styles.note}>
          The absolute location this browser resolved and requested — not the value that was
          configured. The build compiles a RELATIVE bundle URL on purpose, so that the artefact
          names no hostname and runs from a bucket root, a sub-path or <code>file://</code>; it is
          resolved against this document&rsquo;s own base before anything is fetched. Every path
          below was requested under exactly this prefix.
        </p>
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
        {/*
         * Every number in this sentence is a field of `audit.coverage`, and the same fields
         * are rendered as counters with their provenance chips a section below. It restates
         * them in a sentence; it computes nothing, decides nothing, and adds no adjective —
         * a reader who distrusts it can check it against the arithmetic without leaving the
         * page.
         */}
        <p className={styles.note} data-testid="evidence-seal-plain">
          In plain terms: <code>manifest.json</code> lists {audit.coverage.filesDeclared} file(s).
          This browser asked for each one, worked out a fingerprint from the bytes that came
          back, and compared it with the fingerprint the manifest declares.{' '}
          {audit.coverage.digestsMatched} agreed, {audit.coverage.digestsMismatched} disagreed,{' '}
          {audit.coverage.filesUnreadable} could not be read. That is the whole of what the seal
          above is about.
        </p>

        <Disclosure
          summary="Show the manifest’s own fingerprint, and which capture this is"
          testId="evidence-identity-disclosure"
        >
          <Gloss>
            A <em>fingerprint</em> — the manifest calls it a SHA-256 — is a short code worked out
            from a file&rsquo;s bytes. Change one byte anywhere in the file and the code changes
            completely, which is what makes it useful for telling two people they are holding the
            same bytes without either of them sending the file.
          </Gloss>
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
        </Disclosure>
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
        <Gloss>
          One row per file the manifest declares: what it is called, how big it was said to be,
          the fingerprint declared for it and the fingerprint this browser worked out. It is the
          longest thing on this screen and the least interpreted, which is why it is the one
          behind a click rather than the one in front of you.
        </Gloss>
        {/*
         * COLLAPSED, NOT REMOVED. Every row, every declared digest and every recomputed
         * digest is in the DOM in both states — `a11y/contract.ts` promises a reader can
         * "read every declared file with its expected digest and its recomputed digest, as
         * selectable text", and a <details> keeps that promise while a deletion would break
         * it. Any row that DISAGREED is also reported, uncollapsed, in Findings below.
         */}
        <Disclosure
          summary="Show every file, with the fingerprint declared and the fingerprint computed here"
          testId="evidence-inventory-disclosure"
        >
          <InventoryTable rows={audit.rows} />
        </Disclosure>
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

/**
 * Whose bytes are on the other screens — read from the chrome, never asserted here.
 *
 * Rendered above the audit rather than below it, because a reader who scrolls straight to
 * a green seal must have already been told what the seal is about. It is the first thing
 * on the screen after the standfirst for exactly that reason.
 */
function TransportNote({ mode }: { readonly mode: TransportMode }): ReactNode {
  const caveat = transportCaveat(mode);
  return (
    <section
      className={styles.sourceNote}
      data-testid="evidence-transport-note"
      data-mode={caveat.mode}
      aria-labelledby="evidence-transport-heading"
    >
      <p className={styles.sourceNoteTitle} id="evidence-transport-heading">
        {caveat.headline}
      </p>
      <p className={styles.standfirst}>{caveat.body}</p>
    </section>
  );
}

export function EvidenceScreen(props: EvidenceScreenProps): ReactNode {
  const { source, oracle, registry, clock, params, env, transport } = props;
  const publish = useHonestyPublisher();
  const chrome = useHonesty();
  const mode: TransportMode = transport ?? chrome.transport;

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

        {/*
         * The plain band sits BETWEEN the title and the standfirst, and the standfirst is
         * untouched. A reader meets the ordinary-language version first and the exact one
         * immediately after it, on the same screen, with nothing hidden and nothing softened
         * — which is the whole of what R6 asks for and the whole of what it permits.
         */}
        <PlainBand label="What a bundle is, in plain words">
          <p className={styles.plainLead}>
            A <em>bundle</em> is a capture of a past session: the actual answers this console was
            given, saved as ordinary files, plus one file called <code>manifest.json</code> that
            lists every one of them and states a fingerprint for each.
          </p>
          <p className={styles.plainLead}>
            A fingerprint is a short code worked out from a file&rsquo;s bytes; change one byte
            and the code changes. This browser works out every fingerprint again, from the bytes
            it just received, before anything below is shown — so what you are reading is this
            machine&rsquo;s arithmetic and not the capture&rsquo;s own word for itself.
          </p>
          <p className={styles.plainLead}>
            What you can read below: whether every fingerprint agreed, which ones did not, which
            files could not be read at all, and which checks could not be attempted — and what a
            clean result still does not prove.
          </p>
        </PlainBand>

        <p className={styles.standfirst}>
          This browser read every file this bundle lists and recomputed each one&rsquo;s SHA-256
          against the digest <code>manifest.json</code> declares. Nothing here is the
          database&rsquo;s word for it; it is arithmetic you can repeat with <code>sha256sum</code>.
        </p>
      </header>

      <TransportNote mode={mode} />

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
          <pre className={styles.verbatim} data-testid="evidence-unusable-detail">
            {state.audit.detail}
          </pre>
          <p className={styles.note}>
            Source: <Mono data-testid="evidence-unusable-source">{state.audit.sourceId}</Mono> —
            the absolute location this browser resolved and asked for, not the value that was
            configured. The line above is that request and its answer, verbatim and unedited: a
            status and a path a reader can repeat with <code>curl</code>. The transport refuses
            such a bundle before serving anything, so no screen in this console can be fed from it.
          </p>
        </section>
      )}
    </RegisterFrame>
  );
}
