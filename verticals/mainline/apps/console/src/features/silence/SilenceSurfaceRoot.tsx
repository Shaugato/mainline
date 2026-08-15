// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The silence surface's root component.
 *
 * It lives beside `surface.tsx` so the registration module exports a descriptor and nothing
 * else — React Fast Refresh degrades when a module exports both a component and a value,
 * and the console lints that at `--max-warnings 0`.
 *
 * Three jobs:
 *
 *   1. resolve the subject — `#/silence?permit=<uuid>` if the reader named one, otherwise
 *      whichever permit the kernel says this deployment seeded. The console still does not
 *      GUESS which permit you meant; it ASKS, at `GET /v1/demo/subjects`, and when there is
 *      no answer this surface says so and shows nothing. It never falls back to an
 *      identifier written into its own source — see `src/data/demo-subjects.ts`;
 *   2. take a transport from `SilenceTransportContext`, and render the NO SOURCE panel when
 *      nobody has provided one;
 *   3. fill the honesty chrome slots it can establish — transport mode, bundle digest
 *      prefix, clock skew, and the corpus root the PER receipt was issued against (D16).
 *
 * The corpus root is worth the extra line: it is the one value on this surface that ties
 * the silences to a specific state of the archive, and the chrome is where a reader looks
 * for it when they are checking whether two screenshots describe the same corpus.
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
import { Mono, RegisterFrame } from '../../design/primitives';

import styles from './silence.module.css';
import { SilenceScreen } from './SilenceScreen';
import { SubjectDoors } from './SubjectDoors';
import { useSilenceTransport } from './transport-context';
import { useSilenceData } from './useSilenceData';

/** The query parameter that addresses a subject: `#/silence?permit=<uuid>`. */
export const PERMIT_PARAM = 'permit';

/** What this surface asks the subject index for, and how a reader overrides it. */
const ADDRESS: SubjectAddressShape = {
  noun: 'permit',
  member: 'permit_id',
  subjectKey: 'permit',
  example: `#/silence?${PERMIT_PARAM}=<uuid>`,
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

function NoSubject({ index }: { readonly index: SubjectIndex }): ReactNode {
  const absence = subjectAbsence(index, ADDRESS);
  return (
    <RegisterFrame register="evidence">
      <div className={styles.surface} data-testid="silence-no-subject">
        <h1 className={styles.title}>Silence — what was not surfaced</h1>
        <section className={styles.panel} data-index={index.status}>
          <span className={styles.kicker}>{absence.kicker}</span>
          {absence.paragraphs.map((paragraph) => (
            <p className={styles.prose} key={paragraph}>
              {paragraph}
            </p>
          ))}
          <p className={styles.prose}>
            {absence.override} <Mono>{absence.example}</Mono> — and the console will read every
            row the recall declined to surface for it, together with the run that declined them.
          </p>
          {absence.detail !== null && (
            <pre className={styles.verbatim} data-testid="silence-subject-index-detail">
              {absence.detail}
            </pre>
          )}
        </section>

        {/*
          * ONE CLICK, NEVER A TYPED UUID — and never a link to a subject nobody named.
          *
          * The rule above is unchanged: this surface still refuses to choose a permit and
          * still says so in the emitter's own words. What follows is the way out, built out
          * of the SAME answer — every href comes from `GET /v1/demo/subjects`, and a slot
          * the kernel left null renders nothing at all.
          */}
        <SubjectDoors index={index} />
      </div>
    </RegisterFrame>
  );
}

export function SilenceSurfaceRoot(): ReactNode {
  const params = useRouteParams();
  const transport = useSilenceTransport();
  const publish = useHonestyPublisher();

  const index = useDemoSubjects(transport);
  const addressed = addressSubject(params.get(PERMIT_PARAM), index, (subjects) => subjects.permitId);
  const permitId = addressed.value;

  // Hooks run unconditionally; the empty subject is handled below, and `useSilenceData`
  // performs no exchange when the transport is null.
  const model = useSilenceData(transport, permitId ?? '');

  const description = transport?.describe() ?? null;
  const mode = description?.mode ?? null;
  const digestPrefix = description?.bundleDigestPrefix ?? null;
  const corpusRoot = model.data?.receipt?.corpus_root ?? null;
  const { clockSkewMs } = model;

  useEffect(() => {
    publish({
      transport: mode ?? 'unknown',
      bundleDigestPrefix: digestPrefix,
      clockSkewMs,
      corpusRoot,
    });
  }, [publish, mode, digestPrefix, clockSkewMs, corpusRoot]);

  if (permitId === null) return <NoSubject index={index} />;

  return <SilenceScreen permitId={permitId} model={model} noSource={transport === null} />;
}
