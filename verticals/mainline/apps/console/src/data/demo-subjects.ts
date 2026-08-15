// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * WHICH SUBJECT — asked, never guessed, and never written down here.
 *
 * Five surfaces address a subject by identifier, and until now none of them could learn
 * one. `GateSurfaceRoot` refused to choose and opened on NO SUBJECT ADDRESSED — which was
 * the right principle with no mechanism behind it. The others reached for a constant
 * instead: a site code that had leaked out of a test vector into a shipped default, and a
 * clause-plus-commit pair a docstring called "the address the capture bundle carries".
 * Measured against the live URL on 2026-08-15, all three answered **404** — no seed in
 * this repository has ever written any of them, and the capture bundle does not carry them
 * either. The measurements are recorded in `docs/leads/screens-work-plan.md` §1–2.3; they
 * are deliberately not repeated in any source file, because a console file that names a
 * row is a console asserting a fact about a database it did not write, and it becomes
 * false the first time a deployment seeds a different history.
 *
 * ── THE DISTINCTION THIS MODULE EXISTS TO PRESERVE ───────────────────────────────
 *
 * `GateSurfaceRoot`'s docstring says: *"The console does not guess which permit you
 * meant."* That is still true, and it is the reason this module is a network read rather
 * than a table of defaults. **The console does not GUESS a subject; it ASKS the kernel for
 * one.** The two are not the same act and the difference is auditable: a guess is a value
 * this artefact carries, an answer is a value this deployment's database produced and can
 * be re-SELECTed by anyone holding the DSN.
 *
 * So there is exactly one way for a subject to reach a surface without appearing in the
 * URL, and it goes over the wire, through the same contract-validating transport as every
 * other read. If the read does not answer, the surfaces say so **in words** and render
 * nothing — see {@link subjectAbsence}. There is no fallback literal in this file, and
 * adding one would rebuild the same defect with a luckier value. That rule is asserted
 * over the bytes of these files by `tests/unit/data/demo-subjects.test.ts`.
 *
 * ── PRECEDENCE ───────────────────────────────────────────────────────────────────
 *
 * An explicit query parameter always wins. `#/gate?permit=<uuid>` is a reader stating
 * which subject they want, and no index may overrule it — {@link addressSubject} is the
 * one place that ordering is decided, so the five surfaces cannot drift apart on it.
 *
 * ── ONE READ PER SESSION ─────────────────────────────────────────────────────────
 *
 * The answer is memoised against the transport instance, so five surfaces and a dozen
 * navigations perform ONE exchange. The memo holds a promise that never rejects: a
 * failure is *remembered* rather than retried, which is the same rule
 * `BundleTransport.open()` follows and for the same reason — a read that silently
 * re-fires on every mount turns one unavailable route into a request storm behind a
 * screen that looks merely blank. A human pressing reload is the only retry.
 */

import { useEffect, useState } from 'react';

import { refusalFrom } from '../app/refusal';

import type { MainlineTransport } from './transport';
import { TransportError } from './transport';

// ── The subject index ──────────────────────────────────────────────────────

/** The resource key declared in `resources.ts`, and the request line it resolves to. */
export const DEMO_SUBJECTS_RESOURCE = 'demo_subjects';
export const DEMO_SUBJECTS_ROUTE = 'GET /v1/demo/subjects';

/**
 * The identifiers this deployment seeded, one per addressed slot.
 *
 * `null` means the emitter looked and found no such row. It is a fact about the database
 * and it is rendered as a named absence — never repaired, never defaulted.
 */
export interface DemoSubjects {
  /** `{permit_id}` — permit, blocking_checks, silence, and the three transitions. */
  readonly permitId: string | null;
  /** `{cr_id}` — change_request. */
  readonly crId: string | null;
  /** `{check_id}` — disposition. */
  readonly checkId: string | null;
  /** `{receipt_id}` — exposure_receipt. */
  readonly receiptId: string | null;
  /** `{clause_uuid}` — clause_version, clause_ancestry. */
  readonly clauseUuid: string | null;
  /** `{commit_id}` — clause_version. Addresses no version without a clause. */
  readonly commitId: string | null;
  /** `{run_id}` — recall_run. */
  readonly runId: string | null;
  /** `{lesson_id}` — propagation. */
  readonly lessonId: string | null;
  /** `?site_code=` — ledger. Opaque; the seed writes it and nothing here parses it. */
  readonly siteCode: string | null;
  /** Carried for correlation. No resource is addressed by it today. */
  readonly siteId: string | null;
  /**
   * Every subject the emitter looked for and did not find, in ITS words.
   *
   * The contract calls `reason` *"the one member of the payload the database did not
   * produce … prose for the reason that there is no row to speak for itself"*. The
   * surfaces quote it verbatim beside the absence, so a reader learns which predicate
   * returned nothing rather than only that something is missing.
   */
  readonly absent: readonly SubjectAbsenceRecord[];
}

/** One entry of the index's `absent` array. Carries no identifier — there is none. */
export interface SubjectAbsenceRecord {
  readonly subject: string;
  readonly relation: string;
  readonly reason: string;
}

/**
 * The structural shape of `contracts/subjects.schema.json`'s `data` member.
 *
 * Declared here as well as generated into `types.generated.ts`, for the reason
 * `transport.ts` gives for the envelope: a module that cannot compile until a code
 * generator has been executed is a module nobody can bisect past. The payload has already
 * satisfied the contract before this shape is applied — the transport validates, this
 * only names.
 */
interface SubjectsWire {
  readonly permit_id: string | null;
  readonly cr_id: string | null;
  readonly check_id: string | null;
  readonly receipt_id: string | null;
  readonly clause_uuid: string | null;
  readonly commit_id: string | null;
  readonly run_id: string | null;
  readonly lesson_id: string | null;
  readonly site_code: string | null;
  readonly site_id: string | null;
  /**
   * The payload's second half. `subjects` carries, per subject that EXISTS, the row count
   * the choice was made from and the columns the addressing vector has no slot for; this
   * module reads none of it, because addressing is all it does. `absent` it does read.
   */
  readonly absent: readonly SubjectAbsenceRecord[];
}

export type SubjectIndex =
  /** No transport has been composed, so nothing has been asked. */
  | { readonly status: 'no_source' }
  /** The exchange is in flight. */
  | { readonly status: 'resolving' }
  | { readonly status: 'resolved'; readonly subjects: DemoSubjects }
  /**
   * The route did not answer. `failure` is the transport's own classification — `status`
   * for an HTTP code with no envelope, `contract` for a payload this console's schema
   * refuses, `network`, and so on — and `detail` is its report, verbatim.
   */
  | { readonly status: 'unavailable'; readonly failure: string; readonly detail: string };

function subjectsFrom(wire: SubjectsWire): DemoSubjects {
  return Object.freeze({
    permitId: wire.permit_id,
    crId: wire.cr_id,
    checkId: wire.check_id,
    receiptId: wire.receipt_id,
    clauseUuid: wire.clause_uuid,
    commitId: wire.commit_id,
    runId: wire.run_id,
    lessonId: wire.lesson_id,
    siteCode: wire.site_code,
    siteId: wire.site_id,
    absent: Object.freeze([...wire.absent]),
  });
}

/** A settled outcome. Never `resolving`, never `no_source` — those are not answers. */
export type SubjectIndexOutcome =
  | { readonly status: 'resolved'; readonly subjects: DemoSubjects }
  | { readonly status: 'unavailable'; readonly failure: string; readonly detail: string };

/**
 * Performs the read and classifies whatever came back. **It never rejects.**
 *
 * A rejected promise in the session memo would be a rejection handed to every future
 * caller, and one of them would eventually be an unhandled one. The failure is data here,
 * because the surfaces render it.
 */
async function askTheKernel(transport: MainlineTransport): Promise<SubjectIndexOutcome> {
  try {
    const exchange = await transport.exchange<SubjectsWire>({ resource: DEMO_SUBJECTS_RESOURCE });
    return { status: 'resolved', subjects: subjectsFrom(exchange.data) };
  } catch (error: unknown) {
    const refusal = refusalFrom(error);
    if (refusal !== null) {
      // A read is not a transition and the kernel has nothing to refuse here, so this is
      // recorded rather than routed anywhere: if it ever happens, the screen shows the
      // database's own words and somebody has a real finding to chase.
      return {
        status: 'unavailable',
        failure: `refused (${refusal.sqlstate})`,
        detail: `${refusal.constraint}: ${refusal.message}`,
      };
    }
    if (error instanceof TransportError) {
      return { status: 'unavailable', failure: error.failure, detail: error.detail };
    }
    return {
      status: 'unavailable',
      failure: 'unknown',
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

/**
 * One outcome per transport, for the life of the page.
 *
 * Keyed by the transport object rather than by a module-level singleton because REPLAY and
 * LIVE are two different transports over two different byte sources, and an index resolved
 * from one of them is not an answer about the other. A `WeakMap` so that switching source
 * does not retain the old transport's answer forever.
 */
let session = new WeakMap<MainlineTransport, Promise<SubjectIndexOutcome>>();

/** The memoised read. Callers share one exchange; the second caller awaits the first. */
export function resolveDemoSubjects(transport: MainlineTransport): Promise<SubjectIndexOutcome> {
  const pending = session.get(transport);
  if (pending !== undefined) return pending;
  const started = askTheKernel(transport);
  session.set(transport, started);
  return started;
}

/**
 * Forgets every memoised answer.
 *
 * For tests, which build a fresh transport per case and would otherwise be reading another
 * case's answer. A `WeakMap` cannot be enumerated, so the map is replaced wholesale. It is
 * deliberately NOT a retry control: see the module header on why a failure is remembered.
 */
export function resetDemoSubjects(): void {
  session = new WeakMap<MainlineTransport, Promise<SubjectIndexOutcome>>();
}

// ── The hook the five surfaces use ─────────────────────────────────────────

/**
 * The index, as a React state.
 *
 * `no_source` and `resolving` are distinct states rather than one falsy value, because
 * "nobody gave this console a source" and "the read has not landed yet" are different
 * findings and the panels say different things about them. Collapsing them is how a
 * composition gap comes to look like a slow network.
 */
export function useDemoSubjects(transport: MainlineTransport | null): SubjectIndex {
  const [index, setIndex] = useState<SubjectIndex>(
    transport === null ? { status: 'no_source' } : { status: 'resolving' },
  );

  useEffect(() => {
    if (transport === null) {
      setIndex({ status: 'no_source' });
      return undefined;
    }

    let live = true;
    setIndex({ status: 'resolving' });

    // No AbortSignal, on purpose, and for `BundleTransport.open()`'s reason: the promise
    // is memoised for the session, so aborting it on an unmount — which React's
    // development double-invoke performs immediately — would poison the one answer every
    // other surface is waiting on. The `live` flag cancels the state update instead.
    void resolveDemoSubjects(transport).then((outcome) => {
      if (live) setIndex(outcome);
    });

    return () => {
      live = false;
    };
  }, [transport]);

  return index;
}

// ── Addressing ─────────────────────────────────────────────────────────────

/** Where the identifier a surface is rendering came from. */
export type SubjectSource = 'address' | 'index';

export interface AddressedSubject {
  /** The identifier to render, or `null` when nothing named one. */
  readonly value: string | null;
  /** `null` exactly when `value` is null. */
  readonly source: SubjectSource | null;
}

/**
 * THE PRECEDENCE RULE, written once.
 *
 * An explicit query parameter wins outright, and it wins even when the index is still
 * resolving or has failed — a reader who typed an identifier is not made to wait for a
 * read they did not ask for. Only when the address names nothing does the index answer.
 */
export function addressSubject(
  explicit: string | null | undefined,
  index: SubjectIndex,
  pick: (subjects: DemoSubjects) => string | null,
): AddressedSubject {
  if (explicit !== null && explicit !== undefined && explicit !== '') {
    return { value: explicit, source: 'address' };
  }
  if (index.status !== 'resolved') return { value: null, source: null };
  const fromIndex = pick(index.subjects);
  if (fromIndex === null || fromIndex === '') return { value: null, source: null };
  return { value: fromIndex, source: 'index' };
}

// ── The words a surface says when it has no subject ────────────────────────

export interface SubjectAddressShape {
  /** What the identifier names, in the surface's own vocabulary: `permit`, `site`. */
  readonly noun: string;
  /** The member of the index this surface reads: `permit_id`, `site_code`. */
  readonly member: string;
  /**
   * The key this subject occupies in the index's `subjects`/`absent` vocabulary —
   * `permit`, `clause`, `event`. Used only to find the kernel's own reason for an
   * absence; a surface whose subject has no such key omits it.
   */
  readonly subjectKey?: string;
  /** The addressable form, spelled out: `#/gate?permit=<uuid>`. */
  readonly example: string;
}

export interface SubjectAbsence {
  /** Two or three words, for the panel's kicker. Lower case; the CSS decides the rest. */
  readonly kicker: string;
  /** Paragraphs, in order. Every one of them is a statement somebody can check. */
  readonly paragraphs: readonly string[];
  /** The last sentence, which ends in a colon and is completed by {@link example}. */
  readonly override: string;
  /** The addressable form, rendered in mono by the surface. */
  readonly example: string;
  /** The transport's report, verbatim, for a `<pre>`. `null` when there was no failure. */
  readonly detail: string | null;
}

const PRINCIPLE =
  'and it does not carry one written into its own source: an identifier in a console file ' +
  'is a claim about rows this console did not write, and it is false the moment a ' +
  'deployment seeds a different history.';

/**
 * The absence panel's copy, built once and used by all five surfaces.
 *
 * They share it because a judge clicking down the navigation must meet ONE behaviour, and
 * five hand-written panels are five chances for one of them to say something softer than
 * the others. Nothing here reassures: each branch names the route that was asked, what
 * came back, and the address that still works.
 */
export function subjectAbsence(index: SubjectIndex, address: SubjectAddressShape): SubjectAbsence {
  const opening =
    `This surface renders ONE ${address.noun} and does not choose one for you. The console ` +
    `does not guess which ${address.noun} you meant, ${PRINCIPLE}`;
  const override =
    'An explicit identifier still works, and it still wins over anything the kernel would ' +
    'have named:';
  const tail = { override, example: address.example };

  if (index.status === 'no_source') {
    return {
      kicker: 'no subject addressed',
      paragraphs: [
        opening,
        `No transport has been composed for this console, so ${DEMO_SUBJECTS_ROUTE} — the read ` +
          `that would tell it which ${address.noun} this deployment seeded — has not been ` +
          'performed, and no bytes have reached this browser.',
      ],
      ...tail,
      detail: null,
    };
  }

  if (index.status === 'resolving') {
    return {
      kicker: 'asking the kernel',
      paragraphs: [
        opening,
        `So it is asking, at ${DEMO_SUBJECTS_ROUTE}, and it will address whichever ` +
          `${address.noun} this deployment says it seeded.`,
      ],
      ...tail,
      detail: null,
    };
  }

  if (index.status === 'unavailable') {
    return {
      kicker: 'no subject addressed',
      paragraphs: [
        opening,
        `So it asked the kernel instead, at ${DEMO_SUBJECTS_ROUTE}, and this deployment did ` +
          `not answer. The transport classified the failure as "${index.failure}" and its ` +
          'report is below, verbatim. Nothing is shown here because nothing was named.',
      ],
      ...tail,
      detail: index.detail,
    };
  }

  // The index answered and named nothing for this slot. Where the emitter said WHY, that
  // sentence is the kernel's, not the console's, and it is quoted rather than paraphrased.
  const record =
    address.subjectKey === undefined
      ? undefined
      : index.subjects.absent.find((entry) => entry.subject === address.subjectKey);

  const said =
    record === undefined
      ? []
      : [
          `The emitter said why, and this is its sentence rather than ours: “${record.reason}” ` +
            `It looked in ${record.relation}.`,
        ];

  return {
    kicker: 'no subject addressed',
    paragraphs: [
      opening,
      `The kernel answered ${DEMO_SUBJECTS_ROUTE} and named no ${address.noun}: the ` +
        `"${address.member}" member came back null. That is a statement about what this ` +
        'database holds, not a defect in this screen, and the console will not substitute ' +
        'a value for it.',
      ...said,
    ],
    ...tail,
    detail: null,
  };
}
