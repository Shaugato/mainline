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
import {
  Digest,
  Disclosure,
  Gloss,
  Mono,
  PlainBand,
  ProvenanceChip,
  RegisterFrame,
  StagedBadge,
  VerificationSeal,
  labelFor,
  productWord,
} from '../../design/primitives';
import { useVerification } from '../../verify/useVerification';
import { resolveVerifierConfig } from '../../verify/config';
import { PER_BOUND, noteTextInput, type LedgerPayload } from '../../verify/ledger';

import type { SiteOrigin } from './CustodyRoot';
import styles from './custody.module.css';
import { chainLayers, custodyVerdict, overallSeal, quorumShape, signatureReading, tally } from './model';
import { ChainView } from './parts/ChainView';
import { CheckList } from './parts/CheckList';
import { CheckpointPanel } from './parts/CheckpointPanel';
import { FindingsBand } from './parts/FindingsBand';
import { WitnessPanel } from './parts/WitnessPanel';
import {
  useCustodyConfig,
  useCustodyTransport,
  useCustodyVerifier,
} from './transport-context';

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

// ── The words on this page ─────────────────────────────────────────────────

/**
 * The ruled definition, read out of `src/design/glossary.ts` rather than retyped.
 *
 * R7 fixes one sentence per product word and requires it to be used IDENTICALLY on every
 * screen. Retyping it here would give this screen its own copy to drift, so the sentence
 * is fetched at module scope and the fetch failing is a loud module-evaluation error —
 * which `SurfaceHost` already renders as a NOT-BUILT-YET card naming the import failure.
 * A screen that silently opened without its own definition would be the exact regression
 * this band exists to prevent.
 */
const CUSTODY_WORD = productWord('custody');
if (CUSTODY_WORD === null) {
  throw new Error(
    'CustodyScreen: src/design/glossary.ts carries no product word "custody". R7 fixes one ' +
      'sentence per product word and requires every screen to use it identically; this screen ' +
      'will not compose a replacement, because a second sentence for the same word is how two ' +
      'screens come to teach a reader two different vocabularies.',
  );
}

/**
 * Bound at module scope, where the throw above has already narrowed it.
 *
 * TypeScript's control-flow narrowing does not reach INTO a function body from a
 * module-level guard — a closure could be called before the guard in principle — so the
 * value is pinned here rather than re-asserted with `!` at the point of use. The guard
 * stays the mechanism; this is only how the component reads its result.
 */
const CUSTODY_SENTENCE: string = CUSTODY_WORD.sentence;

/**
 * The terms this page uses that `glossary.ts` does not carry.
 *
 * Both are ledger vocabulary that R7's table does not reach, so their sentences are written
 * here — beside the term and never instead of it (R8), in exactly the shape `Gloss` gives
 * the terms the glossary does hold. They are candidates for `glossary.ts` the moment that
 * file's owner wants them; until then this is the honest place for them, because the
 * alternative is a reader meeting `tree_size` with nothing beside it.
 */
const LOCAL_GLOSSES: readonly { readonly term: string; readonly sentence: string }[] = [
  {
    term: 'checkpoint',
    sentence:
      'a signed statement of what the whole log looked like at one moment — how many entries it ' +
      'held, and one number standing for all of them.',
  },
  {
    term: 'tree_size',
    sentence: 'how many entries the log held when that statement was made.',
  },
];

/** The glossary keys this screen's own words come from, in the order a reader meets them. */
const GLOSSED_HERE: readonly string[] = [
  'custody',
  'seal',
  'inclusion-proof',
  'consistency-proof',
  'canonicalisation',
  'transport',
  'staged',
  'provenance-chip',
  'corpus-root',
];

/**
 * `siteCode` IS REQUIRED, and it is answered by the kernel rather than by a constant.
 *
 * Until 2026-08-15 this component exported a default site code and `CustodyRoot` fell back
 * to it whenever `?site=` was absent — which is every arrival from the navigation. It was a
 * fixture string no seed in this repository has ever written, it answered `HTTP 404` against
 * the live kernel, and a default is exactly how it stayed invisible: the screen always had
 * an answer to "which site?", so nobody upstream was ever forced to have one. The value is
 * recorded in `docs/leads/screens-work-plan.md` §2.2 and appears in no source file.
 *
 * A required prop moves that question to the caller, where `CustodyRoot` answers it from the
 * address, from the subject index, or from the ledger naming its own site. Replacing the old
 * literal with a luckier literal would rebuild the same defect with a value that happens to
 * work today.
 *
 * `siteOrigin` travels with it because WHICH of those three named the subject is a fact the
 * reader is owed, not an implementation detail: a site a reader typed and a site a database
 * volunteered are different epistemic situations, exactly as a build-time key and a key out
 * of a query string are.
 */
export function CustodyScreen({
  siteCode,
  siteOrigin,
}: {
  readonly siteCode: string;
  readonly siteOrigin: SiteOrigin;
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
  const signature = signatureReading(report, config);

  /*
   * THE RED, GIVEN A SUBJECT — and given one from the report, never instead of it.
   *
   * `overallSeal` still carries the verifier's own summary word for word and still says
   * FAILED; the tally above still counts every check. This adds the sentence a judge needs
   * next: WHICH checks disagreed, and WHICH of this payload's checkpoints they disagreed
   * about — the attribution being a join between a row's `claimed` digest and a checkpoint's
   * `root_hex`, not a parse of any prose. See `model.ts`.
   */
  const verdict = custodyVerdict(report, payload);

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
        <PlainBand
          kicker="custody, in plain words"
          data-testid="custody-plain-band"
          sentences={[
            `Custody — ${CUSTODY_SENTENCE}`,
            'This page takes the record kept for one site and re-does the arithmetic behind that ' +
              'proof here, in your own browser, from the bytes it was handed a moment ago — not ' +
              'on our servers, and not by asking us.',
            'Each claim below is marked one of three ways: re-done here and it agreed, re-done ' +
              'here and it DISAGREED, or never attempted at all — and a claim nobody could ' +
              'attempt is shown as loudly as one that failed.',
          ]}
        >
          <Disclosure
            summary="Show what each word on this page means"
            note="the exact terms stay; this adds a sentence beside each one"
            data-testid="custody-glossary"
          >
            <ul className={styles.plainList}>
              {GLOSSED_HERE.map((key) => (
                <li key={key}>
                  <Gloss term={key} layout="stack">
                    <Mono>{labelFor(key) ?? key}</Mono>
                  </Gloss>
                </li>
              ))}
              {LOCAL_GLOSSES.map((entry) => (
                <li key={entry.term}>
                  {/*
                    * These two are not in `glossary.ts`, so `Gloss` would render the term with
                    * nothing beside it and mark itself `data-gloss-missing`. The sentence is
                    * written out here instead, in its own element beside the term exactly as
                    * R8 requires — never inside it, and never in place of it.
                    */}
                  <Mono>{entry.term}</Mono> <span className={styles.chainPurpose}>— {entry.sentence}</span>
                </li>
              ))}
            </ul>
          </Disclosure>
        </PlainBand>

        <header className={styles.header}>
          <div className={styles.headerTop}>
            <span className={styles.kicker}>custody · the chain</span>
            <h2 className={styles.title}>Site {siteCode}</h2>
            <VerificationSeal {...overallSeal(report, at)} data-testid="custody-overall-seal" />
            {envelope?.staged === true ? (
              <StagedBadge what={envelope.staged_note ?? 'no note supplied'} />
            ) : null}
          </div>

          {/*
            * IMMEDIATELY UNDER THE SEAL, because the seal is what a stranger reads first and a
            * red with no subject is what this band exists to end. It renders only once the
            * worker has answered — before that the section below already says, in words, that
            * nothing has been recomputed yet.
            */}
          <FindingsBand verdict={verdict} />

          {/*
            * WHO NAMED THIS SITE — visible in both reading modes, because it is provenance.
            *
            * R6 forbids PLAIN from hiding a provenance chip, and this is one: it is the same
            * distinction the verifier config draws between a key compiled into the build and a
            * key out of a query string. A site a reader typed is their assertion; a site the
            * kernel volunteered is the database's. Neither is this console's.
            */}
          <p className={styles.detail} data-testid="custody-site-origin" data-origin={siteOrigin}>
            <strong>Which site, and who said so. </strong>
            {siteOrigin === 'address'
              ? 'This site was named in the address of this page, by whoever wrote the link.'
              : siteOrigin === 'index'
                ? 'This site was named by the kernel, at GET /v1/demo/subjects, which reports the ' +
                  'identifiers this deployment actually seeded.'
                : 'This site was named by the ledger itself: GET /v1/ledger, asked with no ' +
                  'site_code at all, answered with the site it holds. Nothing about it is written ' +
                  'into this console.'}{' '}
            <span className={styles.chainPurpose}>
              No identifier on this screen is a value this console carries in its own source. A
              console that named a row would be making a claim about a database it did not write.
            </span>
          </p>

          {/*
            * The list used to end "...and the ECDSA P-256 signature over the checkpoint note",
            * flat, as though all four had run. Three of them always do. The fourth runs only
            * when a checkpoint carries a signature AND this reader holds a key out of band, and
            * on this demo log neither is true — so the sentence was crediting this browser with
            * work it had not done, on the screen whose subject is what was actually done. The
            * claim is not softened: what each check did or did not do is stated per check
            * below, verbatim, and the tally two lines down counts the ones that did not run.
            *
            * It is now inside a disclosure rather than above the fold, and NOT ONE WORD of it
            * changed. R6: PLAIN collapses canonicalisation detail and the RFC citations into a
            * labelled control; it never removes them, and FULL DETAIL opens them all at once.
            */}
          <Disclosure
            summary="Show exactly what arithmetic ran here, and which published standards it follows"
            data-testid="custody-arithmetic-detail"
          >
            <p className={styles.prose}>
              Nothing on this screen is the database&rsquo;s word. Every seal below is the result
              of arithmetic this browser performed on the bytes it was served: RFC 8785
              canonicalisation, and RFC 6962 leaf, node, inclusion and consistency hashing. The
              ECDSA P-256 signature over the checkpoint note is checked too — whenever a
              checkpoint carries one and a verification key reached this page from outside the
              payload; where it did not, the check below says so in words rather than going quiet
              or going red. The recomputations are shown, and a stranger can run the same
              arithmetic offline with <code>pipx run trappoint-verify</code>.
            </p>
          </Disclosure>

          {/*
            * THE SIGNATURE CHECK, NAMED. Amber, never green and never red — R4.
            *
            * `.env.demo` ships VITE_MAINLINE_LOG_VKEY empty, so on the demo build this check
            * cannot be attempted and the honest word for that is SKIPPED. It is derived from the
            * report and the config rather than written down, because a branch that printed the
            * skip sentence unconditionally would print it on a build that DOES carry a key.
            */}
          <div className={styles.limit} data-testid="custody-signature-state" data-state={signature.state}>
            <span className={styles.limitTitle}>checkpoint signature — {signature.headline}</span>
            <p className={styles.detail}>{signature.detail}</p>
            <p className={styles.chainPurpose}>
              A signature check that was not attempted is not a failure and is not a pass. It is a
              gap in what you are being shown, and this page names it rather than leaving the space
              blank or filling it with a tick.
            </p>
          </div>

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

          {/*
            * The glosses sit OUTSIDE the definition list rather than inside its rows: a `div`
            * inside a `dl` may contain only `dt` and `dd`, and console prose smuggled into a
            * `dd` would also be prose sharing an element with a measured value, which R8
            * forbids for exactly the reason it reads badly here.
            */}
          <p className={styles.chainPurpose} data-testid="custody-facts-gloss">
            Three numbers, never two: how many claims were re-done here and agreed, how many were
            re-done and disagreed, and how many were never attempted at all. Offline means a check
            needs no access to our database and no cooperation from us — a stranger with these bytes
            and a laptop reaches the same answer.
          </p>

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
                  {/*
                    * The verifier's own sentence, verbatim, exactly as it has always been —
                    * it is what reaches the honesty chrome and it is not this screen's to
                    * rewrite. The line under it points at the band that names the same
                    * finding; naming and quoting are different jobs and both are done.
                    */}
                  <p className={styles.detail} data-testid="custody-summary">
                    {report.summary}
                  </p>
                  <p className={styles.chainPurpose} data-testid="custody-summary-pointer">
                    That is the verifier&rsquo;s own sentence, verbatim. Which checks those were,
                    and which checkpoint each disagreement was measured against, is named in the
                    band under the seal at the top of this page.
                  </p>
                  <CheckList checks={report.checks} at={report.at} />
                </>
              )}
            </section>

            {payload.checkpoints.map((checkpoint) => (
              <CheckpointPanel
                key={`${checkpoint.site_code}-${checkpoint.tree_size}`}
                checkpoint={checkpoint}
                noteTextSha256={
                  report?.checks
                    .find((check) => check.name === 'log_signature')
                    ?.recomputations.find(
                      (entry) => entry.input === noteTextInput(checkpoint.tree_size),
                    )?.computed ?? ''
                }
                signatureStatus={
                  report?.checks.find((check) => check.name === 'log_signature')?.status ?? null
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
