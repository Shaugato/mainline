// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE KERNEL CLIENT. The only code in the operator surface that touches the network.
 *
 * Four screens render what this module returns, so its shape is a contract
 * (operator-systems-plan §4.2) and its honesty is the demo's. Six rules, each with the
 * measurement that forced it:
 *
 * 1. **SAME-ORIGIN, ALWAYS.** Every URL is `new URL(path, location.origin)`, built by
 *    `origin.resolveApiUrl` and nowhere else. No absolute URL, no compiled-in hostname, and
 *    no API base read from a build-time variable. `infra/modules/demo-api/main.tf:434-447` records that the
 *    Function URL carries **no CORS block** on purpose, so a page on any other origin can
 *    read neither the body nor the headers. Same-origin is not a preference here; it is
 *    the only configuration in which this file works at all — and it is what makes
 *    `X-Mainline-Emulator` and `Date` readable.
 *
 * 2. **THE RAW BYTES ARE KEPT, VERBATIM.** {@link Exchange.raw} is the exact text
 *    `Response.text()` returned. Nothing here re-serialises it, and the raw drawer (R18)
 *    renders that string, not a pretty-printed round trip of the parsed object. A
 *    `JSON.stringify(JSON.parse(x))` would reorder nothing today and would still be a lie
 *    about what arrived, because it is no longer what arrived.
 *
 * 3. **NOTHING IS FAKED AND NOTHING IS DELAYED.** No JavaScript timer is scheduled in this
 *    file or anywhere under `src/operator/kernel/**`. The request deadline is
 *    `AbortSignal.timeout`, enforced by the platform. Every duration reported is measured:
 *    {@link Exchange.elapsedMs} is a `performance.now()` difference across the actual
 *    round trip and is labelled as the CLIENT's measurement, never mixed with the payload's
 *    own `elapsed_ms`.
 *
 * 4. **A FAILURE IS NAMED, NEVER AN EMPTY STATE.** `get`/`post` never reject and never
 *    return `undefined`. A timeout, a dropped socket, a body that is not JSON and a path
 *    that is not addressable all come back as an {@link Exchange} whose {@link Failure} says
 *    which of those happened. A screen that renders "nothing" because a fetch threw is a
 *    screen that has quietly turned a broken deployment into a clean one.
 *
 * 5. **STATUS DOES NOT DECIDE SHAPE.** The body is parsed on its merits. This is not
 *    fastidiousness: `POST /v1/demo/gate-run` answers **503 with a full envelope** when a
 *    `40001` left the transaction undecided (`transitions.py:_demo_gate_run`,
 *    `docs/deploy/gate-run-contract.md` §2), and a client that treated `status >= 400` as
 *    "problem body" would throw that run's four beats away and render a refusal that never
 *    happened.
 *
 * 6. **EVERY EXCHANGE IS LOGGED.** `log.record` is called here, once, before the promise
 *    settles. The request log (R18) is therefore complete by construction, not by every
 *    screen remembering.
 */

import { type Envelope, parseEnvelope } from './envelope';
import { record } from './log';
import { noteResponse, resolveApiUrl } from './origin';

/**
 * The request deadline. Generous, because beat 3 of a gate run is a real SERIALIZABLE
 * transaction against a real cluster and the payload's own `elapsed_ms` has been seconds,
 * not milliseconds. A deadline that fired before the kernel answered would manufacture a
 * failure the kernel did not have.
 */
const DEFAULT_TIMEOUT_MS = 30_000;

/** `{"error": {...}}` — the demo API's error contract (`app.py:_problem`). */
export interface Problem {
  /** `error.kind`, e.g. `no_route`, `dsn_unset`, `method_not_allowed`. Verbatim. */
  readonly kind: string;
  /** `error.status`, as the body itself stated it. */
  readonly status: number;
  /** `error.detail` — the sentence the API wrote. Rendered verbatim, never paraphrased. */
  readonly detail: string;
  /** Everything else `_problem` attached: `declared`, `allow`, `resource`, `schema_id`. */
  readonly extra: Readonly<Record<string, unknown>>;
}

/**
 * Why an exchange produced no usable payload. Each value is a different sentence and the
 * screens render whichever is true rather than a single "could not load".
 */
export type FailureKind =
  /** The deadline fired. The kernel was asked and had not answered. */
  | 'timeout'
  /** A caller-supplied signal aborted it — a human changed their mind, not a fault. */
  | 'aborted'
  /** `fetch` rejected: DNS, TCP, TLS, or the page is offline. No status exists. */
  | 'network'
  /** Bytes arrived and are not JSON. They are still in `raw`, and still rendered. */
  | 'unparseable'
  /** JSON arrived claiming an envelope version this reader does not know (D-envelope). */
  | 'unrecognised_envelope'
  /** JSON arrived that is neither an envelope nor either of the two error contracts. */
  | 'unrecognised_body'
  /** The envelope answered a different `resource` than the one requested (envelope §resource). */
  | 'wrong_resource'
  /** The path was not an addressable same-origin `/v1/…` path. A programming error. */
  | 'unaddressable';

/** A named failure. `detail` is a sentence, not a code. */
export interface Failure {
  readonly kind: FailureKind;
  readonly detail: string;
}

/**
 * One real HTTP round trip, and everything about it that a screen — or a judge — may need.
 *
 * The members operator-systems-plan §4.2 fixed are all present with the semantics it gave
 * them. The rest are additions, and every one of them is a value observed on the wire or
 * measured by this client; none is composed.
 */
export interface Exchange<T> {
  readonly method: 'GET' | 'POST';
  /** The path as asked for, e.g. `/v1/permits/…`. Always same-origin. */
  readonly path: string;
  /** The absolute URL that was actually fetched. What devtools will show. */
  readonly url: string;
  /** True when `url`'s origin is the document's own. False is a defect, and visible. */
  readonly sameOrigin: boolean;
  /** The HTTP status. **0 when no response arrived at all** — see `failure`. */
  readonly status: number;
  /** `Response.ok`. False for 4xx/5xx and for a failure. */
  readonly ok: boolean;
  /**
   * Bytes of the response body as UTF-8, measured from {@link Exchange.raw}.
   *
   * This is the DECODED body length. The transfer may have been gzipped — the packer
   * ships pre-compressed siblings and `app.py` negotiates them — so this number is the
   * payload's size and not the number of bytes on the socket. Rendered as
   * "body bytes (decoded)" wherever there is room to say so.
   */
  readonly wireBytes: number;
  /** ISO instant this client sent the request, from THIS BROWSER's clock. */
  readonly requestedAt: string;
  /** ISO instant this client finished reading the body, from THIS BROWSER's clock. */
  readonly receivedAt: string;
  /** Round trip measured by `performance.now()`, in ms. The CLIENT's measurement. */
  readonly elapsedMs: number;
  /** The `Date` response header, verbatim. Readable only because we are same-origin. */
  readonly serverDate: string | null;
  /** `X-Mainline-Emulator`, verbatim, or null. `local_furl` means this is a rehearsal. */
  readonly emulator: string | null;
  /** `X-Mainline-Not-The-Demo-Url`, verbatim, or null. */
  readonly notTheDemoUrl: string | null;
  /** `x-mainline-read-ms` — the SERVER's own measurement of the read, or null. */
  readonly serverReadMs: number | null;
  /** The `content-type` response header, verbatim, or null. */
  readonly contentType: string | null;
  /** The parsed envelope, or null on a problem+json body, a failure, or an empty body. */
  readonly envelope: Envelope | null;
  /**
   * `envelope.data`, asserted to `T`.
   *
   * **Asserted, not validated.** The console's runtime contract validator
   * (`src/data/schema.ts`) is out of bounds for this entry point (R1: it would drag the
   * whole read stack into a bundle that must add zero bytes to the existing one). So every
   * screen renders absence for a null field, and the raw drawer puts the bytes one click
   * away — which is the check that actually holds, because it is the one a judge performs.
   */
  readonly data: T | null;
  /** The verbatim response text. **Never re-serialised.** `''` when nothing arrived. */
  readonly raw: string;
  /** The parsed `{"error": …}` body, or null. */
  readonly problem: Problem | null;
  /** Why there is no payload, or null. */
  readonly failure: Failure | null;
}

/** Per-call knobs. Every one is optional and every default is stated above. */
export interface RequestOptions {
  /** Override the deadline, in ms. */
  readonly timeoutMs?: number;
  /** A caller's own abort signal, combined with the deadline. */
  readonly signal?: AbortSignal;
  /**
   * The `resource` the envelope must name. The envelope contract requires the transport to
   * assert this — *"a frame that answers a different question than the one asked is a
   * tampered bundle, not a convenience"* — and it is one of the few contract checks this
   * client can afford to make.
   */
  readonly expectResource?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Read an error body. **THIS DEPLOYMENT HAS TWO ERROR CONTRACTS AND BOTH ARE REAL.**
 *
 * Measured against `scripts/deploy/local_furl.py` on 2026-08-15, not inferred:
 *
 *   nested — `app.py:_problem` — `{"error": {"kind", "status", "detail", …extra}}`
 *            e.g. `no_route`, `dsn_unset`, `method_not_allowed`.
 *   flat   — `transitions.py:_error` — `{"error": "<kind>", "detail": "…", …extra}`
 *            e.g. `POST /v1/demo/gate-run` → 422 `demo_history_not_seeded` when the
 *            scenario's permit is not in the database this process is pointed at.
 *
 * The transition module's own comment says the flat one is *"NOT an envelope, on purpose"*.
 * A client that knew only the nested shape would hand a screen an exchange with no
 * envelope, no problem and no failure — a blank panel where the kernel had written a
 * sentence naming exactly what was wrong. That is the empty state rule 4 forbids, and it
 * was found by running this client against the real handler rather than against a fixture.
 *
 * `status` on the flat form is the HTTP status, because the body does not restate it.
 */
function parseProblem(value: unknown, httpStatus: number): Problem | null {
  if (!isRecord(value)) {
    return null;
  }
  const error = value.error;

  if (isRecord(error)) {
    const { kind, status, detail, ...extra } = error;
    if (typeof kind !== 'string' || typeof detail !== 'string') {
      return null;
    }
    return { kind, status: typeof status === 'number' ? status : httpStatus, detail, extra };
  }

  if (typeof error === 'string') {
    const detail = value.detail;
    if (typeof detail !== 'string') {
      return null;
    }
    const extra: Record<string, unknown> = {};
    for (const [key, member] of Object.entries(value)) {
      if (key !== 'error' && key !== 'detail') {
        extra[key] = member;
      }
    }
    return { kind: error, status: httpStatus, detail, extra };
  }

  return null;
}

/**
 * The request deadline, as a signal.
 *
 * `AbortSignal.timeout` and `AbortSignal.any` are platform primitives, and they are used
 * here specifically so that no file under `src/operator/kernel/**` schedules a JavaScript
 * timer. The rule against faked latency is enforced by a grep (W7 and
 * `tests/unit/operator/kernel/client.test.ts`), and a deadline hand-rolled from a timer
 * would make that grep unrunnable for everyone else — a real delay and a fabricated one
 * would look identical in the source.
 */
function deadlineSignal(options: RequestOptions | undefined): AbortSignal {
  const timeout = AbortSignal.timeout(options?.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const caller = options?.signal;
  return caller === undefined ? timeout : AbortSignal.any([caller, timeout]);
}

function classifyThrown(thrown: unknown): Failure {
  if (thrown instanceof DOMException && thrown.name === 'TimeoutError') {
    return {
      kind: 'timeout',
      detail: `no response within ${DEFAULT_TIMEOUT_MS} ms; the request was aborted by this browser, not refused by the kernel.`,
    };
  }
  if (thrown instanceof DOMException && thrown.name === 'AbortError') {
    return { kind: 'aborted', detail: 'the request was aborted before a response arrived.' };
  }
  const detail = thrown instanceof Error ? `${thrown.name}: ${thrown.message}` : String(thrown);
  return {
    kind: 'network',
    detail: `the request did not complete (${detail}). No HTTP status exists for it.`,
  };
}

/** UTF-8 length of the body text. One encoder, reused; it holds no state between calls. */
const encoder = new TextEncoder();

async function exchange<T>(
  method: 'GET' | 'POST',
  path: string,
  body: unknown,
  options: RequestOptions | undefined,
): Promise<Exchange<T>> {
  const requestedAt = new Date().toISOString();
  const startedAt = performance.now();

  let url: URL;
  try {
    url = resolveApiUrl(path);
  } catch (thrown) {
    // A path this client cannot address is a programming error, and it is reported as one
    // rather than thrown: `get`/`post` never reject, so no screen needs a try/catch and no
    // screen can turn a bad path into a blank panel.
    return settle<T>({
      method,
      path,
      url: path,
      sameOrigin: false,
      status: 0,
      response: null,
      raw: '',
      requestedAt,
      startedAt,
      failure: {
        kind: 'unaddressable',
        detail: thrown instanceof Error ? thrown.message : String(thrown),
      },
      expectResource: options?.expectResource ?? null,
    });
  }

  const init: RequestInit = {
    method,
    // A cached answer is not an answer this page load received, and the whole claim being
    // made on screen is that the bytes arrived just now. `app.py` sends `no-store` on
    // transitions already; this makes the reads say it from the other side too.
    cache: 'no-store',
    credentials: 'omit',
    headers:
      body === undefined
        ? { accept: 'application/json' }
        : { accept: 'application/json', 'content-type': 'application/json' },
    signal: deadlineSignal(options),
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  };

  let response: Response | null = null;
  let raw = '';
  let failure: Failure | null = null;
  try {
    response = await fetch(url, init);
    raw = await response.text();
  } catch (thrown) {
    failure = classifyThrown(thrown);
  }

  return settle<T>({
    method,
    path,
    url: url.href,
    sameOrigin: url.origin === location.origin,
    status: response === null ? 0 : response.status,
    response,
    raw,
    requestedAt,
    startedAt,
    failure,
    expectResource: options?.expectResource ?? null,
  });
}

interface Settlement {
  readonly method: 'GET' | 'POST';
  readonly path: string;
  readonly url: string;
  readonly sameOrigin: boolean;
  readonly status: number;
  readonly response: Response | null;
  readonly raw: string;
  readonly requestedAt: string;
  readonly startedAt: number;
  readonly failure: Failure | null;
  readonly expectResource: string | null;
}

/** Build the Exchange, tell `origin.ts` what the headers disclosed, and log it. */
function settle<T>(s: Settlement): Exchange<T> {
  const headers = s.response?.headers ?? null;
  const emulator = headers?.get('x-mainline-emulator') ?? null;
  const notTheDemoUrl = headers?.get('x-mainline-not-the-demo-url') ?? null;
  const serverDate = headers?.get('date') ?? null;
  const readMsHeader = headers?.get('x-mainline-read-ms') ?? null;
  const serverReadMs =
    readMsHeader !== null && readMsHeader !== '' && Number.isFinite(Number(readMsHeader))
      ? Number(readMsHeader)
      : null;

  let failure = s.failure;
  let parsed: unknown = null;
  if (failure === null && s.raw !== '') {
    try {
      parsed = JSON.parse(s.raw) as unknown;
    } catch (thrown) {
      failure = {
        kind: 'unparseable',
        detail: `the response body is not JSON (${
          thrown instanceof Error ? thrown.message : String(thrown)
        }). The bytes are shown as they arrived.`,
      };
    }
  }

  const problem = parseProblem(parsed, s.status);
  let envelope: Envelope | null = null;
  let data: T | null = null;
  if (problem === null && parsed !== null) {
    const read = parseEnvelope(parsed);
    if (read.ok) {
      envelope = read.envelope;
      data = read.data as T | null;
      if (s.expectResource !== null && read.envelope.resource !== s.expectResource) {
        failure ??= {
          kind: 'wrong_resource',
          detail:
            `asked for "${s.expectResource}" and the envelope names "${read.envelope.resource}". ` +
            `A frame that answers a different question than the one asked is not a convenience.`,
        };
      }
    } else if (read.reason !== null) {
      failure ??= { kind: 'unrecognised_envelope', detail: read.reason };
    } else {
      // JSON arrived that is neither envelope nor either error contract. The bytes are in
      // `raw` and the drawer shows them; what must not happen is a screen with nothing on
      // it and no sentence saying why. Rule 4 has no exceptions.
      failure ??= {
        kind: 'unrecognised_body',
        detail:
          `HTTP ${s.status} carried JSON that is neither a read envelope nor an error this ` +
          `client knows. The bytes are shown as they arrived.`,
      };
    }
  }

  const exchanged: Exchange<T> = {
    method: s.method,
    path: s.path,
    url: s.url,
    sameOrigin: s.sameOrigin,
    status: s.status,
    ok: s.response?.ok ?? false,
    wireBytes: encoder.encode(s.raw).length,
    requestedAt: s.requestedAt,
    receivedAt: new Date().toISOString(),
    elapsedMs: performance.now() - s.startedAt,
    serverDate,
    emulator,
    notTheDemoUrl,
    serverReadMs,
    contentType: headers?.get('content-type') ?? null,
    envelope,
    data,
    raw: s.raw,
    problem,
    failure,
  };

  noteResponse({
    emulator,
    notTheDemoUrl,
    serverDate,
    requestOrigin: s.sameOrigin ? location.origin : safeOrigin(s.url),
  });
  record(exchanged);
  return exchanged;
}

function safeOrigin(href: string): string {
  try {
    return new URL(href).origin;
  } catch {
    return href;
  }
}

/**
 * `GET` one same-origin API path.
 *
 * Never rejects. Never returns undefined. See rule 4 in the module note.
 */
export function get<T>(path: string, options?: RequestOptions): Promise<Exchange<T>> {
  return exchange<T>('GET', path, undefined, options);
}

/**
 * `POST` one same-origin API path, with an optional JSON body.
 *
 * Never rejects. Never returns undefined. Note rule 5: a 4xx or 5xx may still carry a full
 * envelope, and this client parses it.
 */
export function post<T>(
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<Exchange<T>> {
  return exchange<T>('POST', path, body, options);
}
