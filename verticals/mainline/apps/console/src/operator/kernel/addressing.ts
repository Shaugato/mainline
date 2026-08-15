// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * ADDRESSING — which subjects THIS deployment seeded, asked of the deployment.
 *
 * **NO UUID LITERAL APPEARS ANYWHERE IN `src/operator/**`.** Every identifier the operator
 * screens put in a path comes from one `GET /v1/demo/subjects` per page load, and this
 * module is the only place that call is made.
 *
 * The argument is `subjects.py:24-27`, and it is worth quoting because it is the reason
 * this file exists rather than a constant: *"The obvious repair is the same bug with a
 * luckier constant. Pasting `dec0de00-0006-…` into a `.tsx` file produces a console that
 * works today, fails the moment the seed changes, and cannot say which of the two it is
 * doing."* It is not hypothetical — `CustodyScreen.tsx` shipped `DEFAULT_SITE_CODE =
 * 'BLK-07'` and `ClauseDiffScreen.tsx` shipped a clause-and-commit pair, and both were
 * measured as HTTP 404 against the live URL on 2026-08-15.
 *
 * ABSENCE IS A PAYLOAD, NOT A GAP. When a subject is not in the database it has no key in
 * `subjects` and no identifier anywhere — the emitter refuses to manufacture one — and it
 * is named in `absent[]` with the relation it is absent from and the reason, in the
 * kernel's own words. {@link absenceOf} hands a screen that entry verbatim. A screen
 * renders those words; it does not summarise them and it does not substitute a placeholder.
 *
 * CACHED PER PAGE LOAD. One in-flight promise, shared. Two screens mounting at once make
 * one request, and a second read of the same page load returns the same answer — so the
 * request log shows exactly one `GET /v1/demo/subjects`, which is what it should show.
 */

import { get, type Exchange } from './client';

/** The route, written once. */
const SUBJECTS_PATH = '/v1/demo/subjects';

/** The envelope `resource` key this route answers with (`app.py` ROUTES, eighteenth). */
const SUBJECTS_RESOURCE = 'demo_subjects';

/**
 * One subject that was looked for and not found, exactly as the payload states it.
 * `subjects.schema.json#/$defs/absence`: it carries no identifier, because there is none.
 */
export interface SubjectAbsence {
  /** The key this subject would have occupied in `subjects`. */
  readonly subject: string;
  /** The relation, as the database's own `to_regclass` resolved it. Verbatim. */
  readonly relation: string;
  /** Why it is absent, in words. The one member of the payload the database did not write. */
  readonly reason: string;
}

/** Why addressing could not be resolved at all. Distinct from a subject being absent. */
export interface AddressingFailure {
  /** `problem.kind`, `failure.kind`, or `http_<status>`. */
  readonly kind: string;
  /** The sentence the kernel or the client wrote. Verbatim. */
  readonly detail: string;
}

/**
 * The addressing vector, plus the absences.
 *
 * Members are the ones operator-systems-plan §4.2 fixed, with `siteId`, `lessonId`,
 * `subjects`, `resolved`, `failure` and `exchange` added. Every one is null until the
 * kernel says otherwise; there is no default and no fallback.
 */
export interface Addressing {
  readonly permitId: string | null;
  readonly crId: string | null;
  readonly checkId: string | null;
  readonly receiptId: string | null;
  readonly clauseUuid: string | null;
  readonly commitId: string | null;
  readonly runId: string | null;
  readonly lessonId: string | null;
  readonly siteCode: string | null;
  readonly siteId: string | null;
  /** Verbatim `absent[]`. Empty means every indexed subject is present. */
  readonly absent: readonly SubjectAbsence[];
  /**
   * The `subjects` map as it arrived — counts and the columns the vector has no slot for
   * (`permit.external_ref`, `permit.state`, `blocking_check.subject_kind`, …). Left as
   * JSON on purpose: screens read the members they need and render the rest through the
   * raw drawer, rather than this module re-declaring a contract it does not own.
   */
  readonly subjects: Readonly<Record<string, unknown>>;
  /** True when the route answered with an envelope. False when it could not be read. */
  readonly resolved: boolean;
  /** Why not, when `resolved` is false. Null otherwise. */
  readonly failure: AddressingFailure | null;
  /** The exchange itself, so a screen can show the raw payload behind its own addresses. */
  readonly exchange: Exchange<SubjectIndexWire>;
}

/** The `data` member of the subjects envelope, as far as this module reads it. */
interface SubjectIndexWire {
  readonly site_id?: unknown;
  readonly site_code?: unknown;
  readonly permit_id?: unknown;
  readonly cr_id?: unknown;
  readonly check_id?: unknown;
  readonly receipt_id?: unknown;
  readonly clause_uuid?: unknown;
  readonly commit_id?: unknown;
  readonly run_id?: unknown;
  readonly lesson_id?: unknown;
  readonly subjects?: unknown;
  readonly absent?: unknown;
}

let pending: Promise<Addressing> | null = null;

function str(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null;
}

function parseAbsent(value: unknown): readonly SubjectAbsence[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const out: SubjectAbsence[] = [];
  for (const item of value as readonly unknown[]) {
    if (typeof item !== 'object' || item === null) {
      continue;
    }
    const row = item as Record<string, unknown>;
    const subject = row.subject;
    const relation = row.relation;
    const reason = row.reason;
    if (typeof subject !== 'string' || typeof relation !== 'string' || typeof reason !== 'string') {
      continue;
    }
    // Verbatim. Not trimmed, not sentence-cased, not truncated.
    out.push({ subject, relation, reason });
  }
  return out;
}

function failureOf(exchange: Exchange<SubjectIndexWire>): AddressingFailure | null {
  if (exchange.failure !== null) {
    return { kind: exchange.failure.kind, detail: exchange.failure.detail };
  }
  if (exchange.problem !== null) {
    return { kind: exchange.problem.kind, detail: exchange.problem.detail };
  }
  if (exchange.envelope === null) {
    return {
      kind: `http_${exchange.status}`,
      detail: `${SUBJECTS_PATH} answered ${exchange.status} and the body carried no envelope.`,
    };
  }
  return null;
}

function build(exchange: Exchange<SubjectIndexWire>): Addressing {
  const failure = failureOf(exchange);
  const data = exchange.data;
  const subjects =
    typeof data?.subjects === 'object' && data.subjects !== null && !Array.isArray(data.subjects)
      ? (data.subjects as Readonly<Record<string, unknown>>)
      : {};
  return {
    permitId: str(data?.permit_id),
    crId: str(data?.cr_id),
    checkId: str(data?.check_id),
    receiptId: str(data?.receipt_id),
    clauseUuid: str(data?.clause_uuid),
    commitId: str(data?.commit_id),
    runId: str(data?.run_id),
    lessonId: str(data?.lesson_id),
    siteCode: str(data?.site_code),
    siteId: str(data?.site_id),
    absent: parseAbsent(data?.absent),
    subjects,
    resolved: failure === null,
    failure,
    exchange,
  };
}

/**
 * `GET /v1/demo/subjects`, once per page load, cached.
 *
 * Never rejects: a route that 404s or a cluster with no demo world comes back as an
 * {@link Addressing} whose `resolved` is false and whose `failure` carries the kernel's own
 * sentence. Screens render that sentence. They do not fall back to an identifier.
 */
export function resolveAddressing(): Promise<Addressing> {
  pending ??= get<SubjectIndexWire>(SUBJECTS_PATH, {
    expectResource: SUBJECTS_RESOURCE,
  }).then(build);
  return pending;
}

/**
 * The `absent[]` entry for one subject key, or null.
 *
 * The keys are the enum `subjects.schema.json` fixes: `permit`, `blocking_check`, `clause`,
 * `event`, `change_request`, `recall_run`, `exposure_receipt`.
 */
export function absenceOf(addressing: Addressing, subject: string): SubjectAbsence | null {
  for (const entry of addressing.absent) {
    if (entry.subject === subject) {
      return entry;
    }
  }
  return null;
}

/**
 * Drop the cached answer. **Test-only.** No operator module calls it: re-asking mid-demo
 * would put a second `GET /v1/demo/subjects` in the request log with nothing on screen to
 * account for it.
 */
export function resetAddressing(): void {
  pending = null;
}
