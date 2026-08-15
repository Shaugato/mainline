// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The gate surface's root component.
 *
 * It lives beside `surface.tsx` rather than inside it so that the registration module
 * exports a descriptor and nothing else — React Fast Refresh degrades when one module
 * exports both a component and a value, and the console lints that at
 * `--max-warnings 0`.
 *
 * This module does three things and no more:
 *
 *   1. resolves the subject — see below;
 *   2. takes a transport from `GateTransportContext` and renders the NO SOURCE panel
 *      when nobody has provided one (see `transport-context.ts` for why it does not
 *      build one itself);
 *   3. fills the honesty chrome's slots it is in a position to fill — the transport
 *      mode, the bundle digest prefix, the server-vs-local clock skew and the corpus
 *      root the ancestry was closed against (D16). Every one of those is a fact the
 *      transport or a payload established; the surface asserts none of them itself.
 *
 * ── HOW THIS SCREEN COMES TO BE ABOUT A PERMIT ───────────────────────────────────
 *
 * Three ways, in this order, and the screen SAYS WHICH ONE on the page:
 *
 *   `address`   `#/gate?permit=<uuid>`. A reader who typed an identifier wins outright,
 *               including while any read is still in flight — they are not made to wait
 *               for a read they did not ask for. `addressSubject` holds that ordering for
 *               all five addressed surfaces.
 *   `index`     `GET /v1/demo/subjects` — the console ASKS this deployment which permit it
 *               seeded. **It still does not GUESS.** That distinction is the whole of
 *               `src/data/demo-subjects.ts`: a guess is a value this artefact carries, an
 *               answer is a value this deployment's database produced.
 *   `demo-run`  the subject a `POST /v1/demo/gate-run` this reader triggered returned in
 *               its own payload. Measured 2026-08-15: the live URL answers the subjects
 *               read **404** and `gate-run` **200**, so this path is what makes the
 *               headline screen self-addressing WITH NO DEPLOY AT ALL. It is last because
 *               it is a by-product of a run rather than a read whose job is addressing,
 *               and it can only ever fill a slot the first two left empty.
 *
 * When none of the three names a permit the surface still shows nothing — but it says, in
 * plain language, what the screen is for and what it needs, quotes the kernel's own reason
 * verbatim, and offers a form to address one. An identifier written into this file would
 * be a claim about rows the console did not write, and would be false the moment a
 * deployment seeded a different history.
 */

import { useCallback, useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';

import { useHonestyPublisher } from '../../app/honesty';
import {
  addressSubject,
  subjectAbsence,
  useDemoSubjects,
  type SubjectAddressShape,
  type SubjectIndex,
} from '../../data/demo-subjects';
import {
  SUBJECT_ORIGIN_SENTENCE,
  useGateRunSubject,
  useRouteParams,
  type SubjectOrigin,
} from './addressing';
import styles from './gate.module.css';
import { GateScreen } from './GateScreen';
import { useGateData } from './useGateData';
import { useGateTransport } from './transport-context';
import { Mono, PlainBand } from '../../design/primitives';

/** The query parameter that addresses a subject: `#/gate?permit=<uuid>`. */
export const PERMIT_PARAM = 'permit';

/** What this surface asks the subject index for, and how a reader overrides it. */
const ADDRESS: SubjectAddressShape = {
  noun: 'permit',
  member: 'permit_id',
  subjectKey: 'permit',
  example: `#/gate?${PERMIT_PARAM}=<uuid>`,
};

/**
 * THE ADDRESS FORM — the panel's answer to "so what do I do now".
 *
 * The old panel ended on an instruction: *address a permit by its identifier
 * `#/gate?permit=<uuid>`*. That is exact, and it is a dead end for the reader it is
 * shown to, who now has to hand-edit a URL. The form writes the same address, so the
 * mechanism is unchanged and the reader is not asked to be the URL parser.
 *
 * It navigates and nothing else: no read, no validation of the identifier's shape, no
 * guess about what a half-typed value meant. A permit the database does not hold produces
 * the read failure it should produce, named, on the screen it belongs on.
 */
function AddressForm(): ReactNode {
  const [value, setValue] = useState('');

  const submit = useCallback(
    (event: SyntheticEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = value.trim();
      if (trimmed === '') return;
      const params = new URLSearchParams(
        window.location.hash.includes('?')
          ? window.location.hash.slice(window.location.hash.indexOf('?') + 1)
          : '',
      );
      params.set(PERMIT_PARAM, trimmed);
      window.location.hash = `/gate?${params.toString()}`;
    },
    [value],
  );

  return (
    <form className={styles.addressForm} onSubmit={submit} data-testid="gate-address-form">
      <label className={styles.addressLabel} htmlFor="gate-address-permit">
        Permit identifier
      </label>
      <input
        className={styles.addressInput}
        id="gate-address-permit"
        name={PERMIT_PARAM}
        type="text"
        autoComplete="off"
        spellCheck={false}
        placeholder="paste a permit identifier"
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
        }}
      />
      <button className={styles.addressButton} type="submit">
        Show this permit
      </button>
    </form>
  );
}

function NoSubject({ index }: { readonly index: SubjectIndex }): ReactNode {
  const absence = subjectAbsence(index, ADDRESS);

  return (
    <div className={styles.surface} data-testid="gate-no-subject">
      <PlainBand
        kicker="no permit named yet"
        sentences={[
          'A permit is a written authorisation for one specific piece of work; this screen shows ' +
            'one of them at a time, together with everything the database checks before it will ' +
            'let that authorisation take effect.',
          'It has not been told which permit to show, and it will not pick one for you — an ' +
            'identifier written into this console would be a claim about rows the console did not ' +
            'write.',
          'Paste an identifier below and this screen will show that permit; the demonstration ' +
            'controls above also name their own subject the moment you run them.',
        ]}
        data-testid="plain-band-no-subject"
      >
        <AddressForm />
      </PlainBand>

      <section
        className={styles.refusalBar}
        data-state="none"
        data-index={index.status}
        aria-label="Refusal"
      >
        <span className={styles.refusalKicker}>{absence.kicker}</span>
        {absence.paragraphs.map((paragraph) => (
          <p className={styles.prose} key={paragraph}>
            {paragraph}
          </p>
        ))}
        <p className={styles.prose}>
          {absence.override} <Mono>{absence.example}</Mono>
        </p>
        {absence.detail !== null && (
          <pre className={styles.refusalMessage} data-testid="gate-subject-index-detail">
            {absence.detail}
          </pre>
        )}
      </section>
    </div>
  );
}

export function GateSurfaceRoot(): ReactNode {
  const params = useRouteParams();
  const transport = useGateTransport();
  const publish = useHonestyPublisher();

  const index = useDemoSubjects(transport);
  const addressed = addressSubject(params.get(PERMIT_PARAM), index, (subjects) => subjects.permitId);
  const fromRun = useGateRunSubject();

  // The precedence rule, and the ONE place it is decided for this surface. `addressed`
  // already holds address-over-index; a run's subject can only fill the slot both of
  // those left empty, and it can never overrule an identifier a reader typed.
  const permitId = addressed.value ?? fromRun?.permitId ?? null;
  const origin: SubjectOrigin | null =
    addressed.source ?? (fromRun === null ? null : 'demo-run');

  // Hooks run unconditionally; the empty subject is handled by the render below, and
  // `useGateData` performs no exchange when the transport is null.
  const model = useGateData(transport, permitId ?? '');

  const description = transport?.describe() ?? null;
  const mode = description?.mode ?? null;
  const digestPrefix = description?.bundleDigestPrefix ?? null;
  const corpusRoot = model.ancestryData?.corpus_root ?? null;
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

  return (
    <GateScreen
      permitId={permitId}
      model={model}
      noSource={transport === null}
      origin={origin}
      originSentence={origin === null ? null : SUBJECT_ORIGIN_SENTENCE[origin]}
    />
  );
}
