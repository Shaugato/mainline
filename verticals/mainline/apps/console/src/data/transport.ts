// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * ONE client interface, and the live implementation of it.
 *
 * D7 makes replay the default and live a transport swap: `LIVE` and `REPLAY` differ in
 * one line of composition and in one badge, never in a code path. That property is only
 * real if both implementations satisfy the same interface with the same post-conditions,
 * so the post-conditions are enforced HERE, in `finishExchange`, which both transports
 * call — not once per transport, where they could drift.
 *
 * Three rules this file holds to.
 *
 * **No retry helper, of any kind.** A blanket retry is banned repo-wide, and this is
 * the file where one would be added first. The reason is specific rather than stylistic:
 * the kernel's POST endpoints are transitions, SQLSTATE `40001` is an UNDECIDED
 * transaction rather than a failure, and a helper that re-sends a merge because a socket
 * closed is a helper that can issue a permit twice. A `retry` outcome is surfaced to the
 * caller, which decides — a human pressing a button again is a decision with an author.
 *
 * **Every response is validated against its contract before it is returned.** A payload
 * that does not satisfy the contract is not rendered in a degraded form; it raises, and
 * the surface shows a failure state. The console cannot show you a screen we made up,
 * and that has to include a screen the SERVER made up.
 *
 * **A refusal is a normal response, not an exception at the HTTP layer.** The kernel
 * answers a refused transition with an `invoke` envelope whose outcome is `refused` and
 * whose `refusal` member is the specification payload, verbatim (D18). This transport
 * turns that into a `RefusalError` carrying the payload — never a message it composed.
 */

import { RefusalError } from '../app/refusal';

import type { SchemaRegistry, ValidationError } from './schema';
import { formatErrors } from './schema';
import type { ResolvedRequest, ResourceRequest } from './resources';
import { resolveRequest, urlFor } from './resources';

// ── The interface ──────────────────────────────────────────────────────────

/** D7 / D16: which of the two the bytes came from. Rendered permanently. */
export type TransportMode = 'live' | 'replay';

export interface TransportDescription {
  readonly mode: TransportMode;
  /** For live: the base URL. For replay: the bundle id. */
  readonly source: string;
  /** First 12 hex characters of the bundle manifest digest, or null when live. */
  readonly bundleDigestPrefix: string | null;
  /** True when any datum this transport can serve is hand-authored. */
  readonly staged: boolean;
  /** Why it is staged, verbatim. Null when it is not. */
  readonly stagedNote: string | null;
}

/** What a completed exchange yields. `data` is the validated `envelope.data`. */
export interface Exchange<T = unknown> {
  readonly request: ResolvedRequest;
  readonly envelope: ReadEnvelopeShape;
  readonly data: T;
  readonly httpStatus: number;
  /** server − client in milliseconds, or null when the payload named no server clock. */
  readonly clockSkewMs: number | null;
  readonly mode: TransportMode;
}

/**
 * The structural shape of `contracts/envelope.schema.json`.
 *
 * It is declared here as well as generated into `types.generated.ts` because this file
 * must not depend on the generator having run — a transport that cannot compile until a
 * code generator has been executed is a transport nobody can bisect past.
 */
export type ProvenanceChipShape = 'db:column' | 'db:constraint' | 'recomputed' | 'staged' | 'derived';

export interface ReadEnvelopeShape {
  readonly envelope_version: 1;
  readonly resource: string;
  readonly schema_id: string;
  readonly observed_at?: string | null;
  readonly server_date?: string | null;
  readonly staged: boolean;
  readonly staged_note?: string | null;
  readonly provenance: readonly {
    readonly pointer: string;
    readonly chip: ProvenanceChipShape;
  }[];
  readonly data: unknown;
}

/** The ONE client interface. Both transports implement exactly this. */
export interface MainlineTransport {
  describe(): TransportDescription;
  /**
   * Performs a read or an invoke. `signal` is honoured by both implementations —
   * replay is not an excuse to ignore cancellation, because the surfaces are written
   * against one behaviour.
   *
   * Throws `RefusalError` when the kernel refused the transition, `TransportError`
   * for everything else.
   */
  exchange<T = unknown>(request: ResourceRequest, signal?: AbortSignal): Promise<Exchange<T>>;
}

// ── Errors ─────────────────────────────────────────────────────────────────

export type TransportFailure =
  | 'network'
  | 'aborted'
  | 'status'
  | 'malformed'
  | 'contract'
  | 'mismatch'
  | 'unverified'
  | 'missing_frame'
  | 'tampered';

export class TransportError extends Error {
  readonly failure: TransportFailure;
  readonly requestKey: string;
  readonly detail: string;
  readonly validation: readonly ValidationError[];

  constructor(
    failure: TransportFailure,
    requestKey: string,
    detail: string,
    validation: readonly ValidationError[] = [],
  ) {
    super(`${failure}: ${requestKey} — ${detail}`);
    this.name = 'TransportError';
    this.failure = failure;
    this.requestKey = requestKey;
    this.detail = detail;
    this.validation = validation;
  }
}

// ── Shared post-conditions ─────────────────────────────────────────────────

const REFUSAL_SCHEMA_ID = 'https://spec.trappoint.org/1.0/wire/refusal.schema.json';

interface RefusalShape {
  readonly sqlstate: string;
  readonly constraint: string;
  readonly message: string;
  readonly constraint_source?: 'reported' | 'parsed';
  readonly subject_kind?: string;
  readonly subject_id?: string;
  readonly gate_epoch?: number;
}

interface InvokeShape {
  readonly outcome: 'committed' | 'refused' | 'retry';
  readonly refusal: RefusalShape | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Everything both transports must do to a decoded body before returning it.
 *
 * Order matters and is load-bearing:
 *   1. parse — a body that is not JSON never reaches a schema;
 *   2. validate against the resource's contract — including the envelope;
 *   3. assert the envelope answers the question that was asked;
 *   4. translate a `refused` invoke outcome into a `RefusalError`.
 *
 * Step 3 is the one a reviewer should look at twice. A frame that answers a different
 * resource, or names a different contract than the one the console holds, is not a
 * convenience to route around — in replay it is exactly what a swapped fixture looks
 * like, so it is a hard failure.
 */
export function finishExchange<T>(
  registry: SchemaRegistry,
  request: ResolvedRequest,
  httpStatus: number,
  bodyText: string,
  mode: TransportMode,
  clientNow: number,
): Exchange<T> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(bodyText);
  } catch (error) {
    throw new TransportError('malformed', request.key, `response body is not JSON: ${String(error)}`);
  }

  const result = registry.validate(request.resource.schemaId, parsed);
  if (!result.valid) {
    throw new TransportError(
      'contract',
      request.key,
      `response does not satisfy ${request.resource.schemaId}.\n${formatErrors(result.errors)}`,
      result.errors,
    );
  }

  const envelope = parsed as ReadEnvelopeShape;

  if (envelope.resource !== request.resource.key) {
    throw new TransportError(
      'mismatch',
      request.key,
      `payload declares resource "${envelope.resource}" but the request was for "${request.resource.key}".`,
    );
  }
  if (envelope.schema_id !== request.resource.schemaId) {
    throw new TransportError(
      'mismatch',
      request.key,
      `payload declares schema_id "${envelope.schema_id}" but this resource is governed by ` +
        `"${request.resource.schemaId}". A payload that names a contract we do not hold is not ` +
        'forward compatibility; it is an unverifiable claim.',
    );
  }

  const serverDate = envelope.server_date ?? null;
  const clockSkewMs = serverDate === null ? null : Date.parse(serverDate) - clientNow;

  const exchange: Exchange<T> = {
    request,
    envelope,
    data: envelope.data as T,
    httpStatus,
    clockSkewMs: clockSkewMs !== null && Number.isFinite(clockSkewMs) ? clockSkewMs : null,
    mode,
  };

  if (request.resource.schemaId.endsWith('/invoke.schema.json') && isRecord(envelope.data)) {
    const invoke = envelope.data as unknown as InvokeShape;
    if (invoke.outcome === 'refused' && invoke.refusal !== null) {
      // The contract has already established that this object satisfies
      // spec/wire/refusal.schema.json — validated above, as part of the envelope.
      throw new RefusalError(invoke.refusal);
    }
  }

  return exchange;
}

/** Exposed so a caller can name the specification contract without importing contracts.ts. */
export { REFUSAL_SCHEMA_ID };

// ── The live transport ─────────────────────────────────────────────────────

export interface HttpTransportOptions {
  readonly baseUrl: string;
  readonly registry: SchemaRegistry;
  /**
   * Injected so tests need no network and no global patching. Defaults to the platform
   * `fetch`; a caller that wants credentials, a proxy or a header supplies its own.
   */
  readonly fetchImpl?: typeof fetch;
  /** Milliseconds after which the request is aborted. 0 disables the timeout. */
  readonly timeoutMs?: number;
  /** Clock, injectable for cinema mode (D12), which freezes Date.now. */
  readonly now?: () => number;
}

export class HttpTransport implements MainlineTransport {
  private readonly baseUrl: string;
  private readonly registry: SchemaRegistry;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  private readonly now: () => number;

  constructor(options: HttpTransportOptions) {
    this.baseUrl = options.baseUrl;
    this.registry = options.registry;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.timeoutMs = options.timeoutMs ?? 15_000;
    this.now = options.now ?? Date.now;
  }

  describe(): TransportDescription {
    return {
      mode: 'live',
      source: this.baseUrl,
      bundleDigestPrefix: null,
      // A live kernel is never staged. If it were, it would say so in each envelope,
      // and the honesty chrome reads that per-payload rather than trusting this.
      staged: false,
      stagedNote: null,
    };
  }

  async exchange<T = unknown>(request: ResourceRequest, signal?: AbortSignal): Promise<Exchange<T>> {
    const resolved = resolveRequest(request);

    // An already-aborted caller gets nothing performed on its behalf. Relying on
    // `fetch` to notice the signal would make the behaviour depend on the fetch
    // implementation, and the two transports have to behave identically here.
    if (signal?.aborted === true) {
      throw new TransportError('aborted', resolved.key, String(signal.reason ?? 'aborted before start'));
    }

    // AbortController, composed: the caller's signal AND our own timeout. There is no
    // retry, no backoff and no circuit breaker here, and there will not be one.
    const controller = new AbortController();
    const onAbort = (): void => {
      controller.abort(signal?.reason);
    };
    if (signal !== undefined) {
      if (signal.aborted) controller.abort(signal.reason);
      else signal.addEventListener('abort', onAbort, { once: true });
    }
    const timer =
      this.timeoutMs > 0
        ? setTimeout(() => {
            controller.abort(new Error(`timed out after ${this.timeoutMs} ms`));
          }, this.timeoutMs)
        : null;

    try {
      const init: RequestInit = {
        method: resolved.method,
        signal: controller.signal,
        headers:
          resolved.method === 'POST'
            ? { accept: 'application/json', 'content-type': 'application/json' }
            : { accept: 'application/json' },
      };
      const withBody: RequestInit =
        resolved.method === 'POST'
          ? { ...init, body: JSON.stringify(resolved.body ?? {}) }
          : init;

      let response: Response;
      try {
        response = await this.fetchImpl(urlFor(resolved, this.baseUrl), withBody);
      } catch (error) {
        if (controller.signal.aborted) {
          throw new TransportError('aborted', resolved.key, String(controller.signal.reason ?? error));
        }
        throw new TransportError('network', resolved.key, String(error));
      }

      const text = await response.text();

      // A refusal arrives with a non-2xx status AND a well-formed envelope. Only a
      // status with no parseable envelope is a transport failure.
      if (!response.ok && !looksLikeEnvelope(text)) {
        throw new TransportError(
          'status',
          resolved.key,
          `HTTP ${response.status}; body carries no envelope (${text.slice(0, 200)}).`,
        );
      }

      return finishExchange<T>(this.registry, resolved, response.status, text, 'live', this.now());
    } finally {
      if (timer !== null) clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    }
  }
}

function looksLikeEnvelope(text: string): boolean {
  try {
    const parsed: unknown = JSON.parse(text);
    return isRecord(parsed) && parsed.envelope_version === 1;
  } catch {
    return false;
  }
}
