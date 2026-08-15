// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The custody surface's root.
 *
 * It lives beside `surface.tsx` so that the registration module exports a descriptor and
 * nothing else — React Fast Refresh degrades when one module exports both a component and
 * a value, and the console lints at `--max-warnings 0`.
 *
 * Two jobs: resolve the site this screen is about, and fill the honesty chrome slots this
 * surface is in a position to fill (D16). It asserts nothing itself — the transport
 * establishes the mode and the bundle digest, and the verifier establishes everything else.
 *
 * ── WHERE THE SITE COMES FROM, AND WHY IT IS NOT A CONSTANT ──────────────────────
 *
 * It used to be one: `CustodyScreen` exported a default site code, and this root fell back
 * to it whenever `?site=` was absent — which is every arrival from the navigation. That
 * code was a fixture string that had leaked out of `tests/vectors/` into a shipped
 * default, and no seed in this repository has ever written it. Measured against the live
 * URL on 2026-08-15 it answered `404 — no mainline.ledger_checkpoint rows`, which is what
 * a judge saw when they clicked Custody. The value is recorded in
 * `docs/leads/screens-work-plan.md` §2.2 and appears in no source file.
 *
 * The repair is not a better constant. There are THREE sources here and every one of them
 * is somebody else naming the subject — never this artefact:
 *
 *   1. **The address.** `#/custody?site=<code>` is a reader stating what they want, and it
 *      wins outright, including while anything below is still in flight.
 *   2. **The subject index.** `src/data/demo-subjects.ts` asks the kernel which site this
 *      deployment seeded — `GET /v1/demo/subjects`.
 *   3. **The ledger naming itself.** `GET /v1/ledger` with **no** `site_code` answers with
 *      the site it holds, in a `site_code` member `contracts/ledger.schema.json` makes
 *      REQUIRED. Measured against the live URL on 2026-08-15: 200, with checkpoints at
 *      tree_size 1, 2 and 4.
 *
 * Source 3 exists because source 2 is a route the live deployment does not carry yet —
 * measured the same day, `GET /v1/demo/subjects` answers **404** there, and R11 forbids
 * anyone on this plan from redeploying to change that. Without it this screen would render
 * a named absence over a kernel that is, in fact, holding the answer and willing to say it.
 * With it, Custody opens on the seeded ledger against the deployment that is live TODAY.
 *
 * The line between source 3 and the defect it replaces is the line R1 draws: a literal is
 * the console GUESSING, and a read is the console ASKING. Nothing below writes an
 * identifier down, and when all three are silent this surface renders a named absence
 * saying which of the several possible nothings it is.
 */

import { useEffect, useMemo, useSyncExternalStore, type ReactNode } from 'react';

import { useHonestyPublisher } from '../../app/honesty';
import { parseRoute } from '../../app/router';
import {
  addressSubject,
  subjectAbsence,
  useDemoSubjects,
  type SubjectAddressShape,
  type SubjectIndex,
} from '../../data/demo-subjects';
import { useResource, type ResourceState } from '../../data/useResource';
import { Mono } from '../../design/primitives';
import type { LedgerPayload } from '../../verify/ledger';

import styles from './custody.module.css';
import { CustodyScreen } from './CustodyScreen';
import { siteNamedByLedger } from './model';
import { useCustodyTransport } from './transport-context';

/** `#/custody?site=<code>`. */
export const SITE_PARAM = 'site';

/** Where the site this screen is rendering came from. Shown to the reader, never inferred. */
export type SiteOrigin = 'address' | 'index' | 'ledger';

/** What this surface asks the subject index for, and how a reader overrides it. */
const ADDRESS: SubjectAddressShape = {
  noun: 'site',
  member: 'site_code',
  example: `#/custody?${SITE_PARAM}=<code>`,
};

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  window.addEventListener('popstate', onChange);
  return () => {
    window.removeEventListener('hashchange', onChange);
    window.removeEventListener('popstate', onChange);
  };
}

function locationKey(): string {
  return typeof window === 'undefined' ? '' : `${window.location.search}${window.location.hash}`;
}

function useRouteParams(): URLSearchParams {
  const key = useSyncExternalStore(subscribe, locationKey, () => '');
  return useMemo(() => {
    const hashAt = key.indexOf('#');
    const search = hashAt >= 0 ? key.slice(0, hashAt) : key;
    const hash = hashAt >= 0 ? key.slice(hashAt) : '';
    return parseRoute(hash, search, []).params;
  }, [key]);
}

/**
 * THE TESTID NAMES THE STATE, AND `no_source` KEEPS THE NAME IT ALREADY HAD.
 *
 * With no transport composed there is nothing to ask the subject index either, so the
 * finding is the one this surface has always reported — NO SOURCE — and renaming it would
 * make a composition gap look like a new class of failure. The subject question only
 * becomes the reader's problem once bytes are reachable and still nothing named a site.
 */
function absenceTestId(index: SubjectIndex): string {
  return index.status === 'no_source' ? 'custody-no-source' : 'custody-no-subject';
}

/**
 * The named absence, with the SECOND read's outcome appended.
 *
 * `subjectAbsence` reports what happened to `GET /v1/demo/subjects`. When that came back
 * empty this root asked the ledger to name its own site, and the reader is owed the result
 * of that attempt too — otherwise the panel describes one of the two reads and leaves the
 * other invisible, which is the shape of every absence that gets mistaken for a bug.
 */
function NoSubject({
  index,
  ledgerNote,
}: {
  readonly index: SubjectIndex;
  readonly ledgerNote: string | null;
}): ReactNode {
  const absence = subjectAbsence(index, ADDRESS);
  return (
    <div className={styles.surface} data-testid={absenceTestId(index)}>
      <section className={styles.failure} data-index={index.status} aria-label="No subject">
        <span className={styles.kicker}>{absence.kicker}</span>
        {absence.paragraphs.map((paragraph) => (
          <p className={styles.prose} key={paragraph}>
            {paragraph}
          </p>
        ))}
        {ledgerNote === null ? null : (
          <p className={styles.prose} data-testid="custody-ledger-fallback-note">
            {ledgerNote}
          </p>
        )}
        <p className={styles.prose}>
          {absence.override} <Mono>{absence.example}</Mono>
        </p>
        {absence.detail !== null && (
          <pre className={styles.detail} data-testid="custody-subject-index-detail">
            {absence.detail}
          </pre>
        )}
      </section>
    </div>
  );
}

export function CustodyRoot(): ReactNode {
  const params = useRouteParams();
  const transport = useCustodyTransport();
  const publish = useHonestyPublisher();

  const index = useDemoSubjects(transport);
  const addressed = addressSubject(params.get(SITE_PARAM), index, (subjects) => subjects.siteCode);

  /*
   * ENABLED ONLY WHEN THE FIRST TWO SOURCES HAVE FINISHED AND SAID NOTHING.
   *
   * `addressed.value === null` is true while the index is still RESOLVING as well as after
   * it has failed, and firing on the former would put a second ledger read on the wire for
   * every arrival — including the overwhelming majority where the index is about to answer.
   * So the gate is the index's own settled status, not the absence of a value.
   */
  const askLedger =
    addressed.value === null && (index.status === 'unavailable' || index.status === 'resolved');

  const fallback = useResource<LedgerPayload>(
    transport,
    { resource: 'ledger' },
    { enabled: askLedger },
  );

  const ledgerSite = siteNamedByLedger(
    fallback.state.status === 'ready' ? fallback.state.data : null,
  );

  const site = addressed.value ?? ledgerSite;
  const origin: SiteOrigin | null =
    addressed.source === 'address'
      ? 'address'
      : addressed.source === 'index'
        ? 'index'
        : ledgerSite === null
          ? null
          : 'ledger';

  const description = transport?.describe() ?? null;
  const mode = description?.mode ?? null;
  const digestPrefix = description?.bundleDigestPrefix ?? null;

  useEffect(() => {
    publish({
      transport: mode ?? 'unknown',
      bundleDigestPrefix: digestPrefix,
    });
  }, [publish, mode, digestPrefix]);

  if (site === null || origin === null) {
    return <NoSubject index={index} ledgerNote={ledgerFallbackNote(askLedger, fallback.state)} />;
  }

  return <CustodyScreen siteCode={site} siteOrigin={origin} />;
}

/**
 * What the second read did, in one sentence, or `null` when it was never attempted.
 *
 * Every branch names the route and what came back. `failed` renders the transport's own
 * classification and its report verbatim — a 404 from a deployment that has no ledger for
 * anybody and a contract refusal are different findings, and only one of them is about
 * this screen.
 */
function ledgerFallbackNote(
  attempted: boolean,
  state: ResourceState<LedgerPayload>,
): string | null {
  if (!attempted) return null;
  if (state.status === 'loading' || state.status === 'idle') {
    return 'So it is asking the ledger to name its own site, at GET /v1/ledger with no site_code.';
  }
  if (state.status === 'failed') {
    return (
      'So it asked the ledger to name its own site, at GET /v1/ledger with no site_code, and ' +
      `that did not answer either. The transport classified the failure as "${state.failure}" ` +
      `and its report was: ${state.detail}`
    );
  }
  if (state.status === 'refused') {
    return (
      'So it asked the ledger to name its own site, at GET /v1/ledger with no site_code, and ' +
      `the database refused the read: ${state.refusal.sqlstate} ${state.refusal.message}`
    );
  }
  return (
    'So it asked the ledger to name its own site, at GET /v1/ledger with no site_code. The ' +
    'read answered, and the site_code it carried was empty — which is a statement about what ' +
    'this database holds, not a defect in this screen.'
  );
}
