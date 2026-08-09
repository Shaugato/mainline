// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The verifier's message protocol, and the Web Worker that speaks it.
 *
 * ── WHY A WORKER, WHEN THE ARITHMETIC IS FAST ─────────────────────────────────────
 *
 * Not for speed. A bundle is a few hundred kilobytes and SHA-256 over it is milliseconds.
 * The worker exists for two reasons that outlive the benchmark:
 *
 *   1. **The main thread must not be able to lie about a result it computed itself.**
 *      Verification lives behind a message boundary with a typed protocol and no shared
 *      state, so a component cannot reach into the verifier and adjust an outcome. That is
 *      a weak guarantee against a hostile author and a strong one against an ordinary
 *      refactor, and ordinary refactors are what actually erode a claim over a year.
 *   2. **A 40 000-leaf tree must not freeze the refusal screen.** The demo corpus is
 *      small; the product's ledgers are not, and a verifier that has to be re-architected
 *      the first time it meets a real log is a verifier that will be turned off instead.
 *
 * ── THE PROTOCOL, AND ITS ONE RULE ────────────────────────────────────────────────
 *
 * Request → response, correlated by `id`, one response per request, no streaming, no
 * broadcast. Every response is either `{ ok: true, result }` or `{ ok: false, error }`;
 * there is no partial result, because a partially verified bundle rendered beside an error
 * looks like a finding.
 *
 * This module is BOTH the worker entry point and the implementation the inline fallback
 * calls. `handleVerifierRequest` is a pure function of its request plus the platform's
 * crypto; the `self.onmessage` installation at the bottom is guarded so that importing
 * this file from a test or from the main thread does not register a handler on the window.
 */

import type { CheckReport, LedgerPayload } from './ledger';
import { verifyLedger } from './ledger';
import type { CheckpointResult } from './checkpoint';
import { parseVerificationKey, verifyNote } from './checkpoint';
import type { VerifierConfig } from './config';
import { NO_ANCHOR } from './config';
import { resolveSha256, type Sha256Oracle } from './sha256';
import type { BoundaryOutcome, SilenceBoundaryInput } from './silenceroot';
import { verifyBoundary } from './silenceroot';
import { toHex } from './bytes';

// ── Requests ───────────────────────────────────────────────────────────────

export interface Sha256Request {
  readonly kind: 'sha256';
  readonly id: string;
  readonly bytes: Uint8Array;
}

export interface LedgerRequest {
  readonly kind: 'ledger';
  readonly id: string;
  readonly payload: LedgerPayload;
  readonly config: VerifierConfig;
  /** ISO-8601 instant to stamp the report with. Supplied so cinema mode is deterministic. */
  readonly at?: string;
}

export interface NoteRequest {
  readonly kind: 'note';
  readonly id: string;
  readonly note: string;
  readonly vkeys: readonly string[];
}

export interface BoundaryRequest {
  readonly kind: 'boundary';
  readonly id: string;
  readonly input: SilenceBoundaryInput;
}

export interface DescribeRequest {
  readonly kind: 'describe';
  readonly id: string;
}

export type VerifierRequest =
  | Sha256Request
  | LedgerRequest
  | NoteRequest
  | BoundaryRequest
  | DescribeRequest;

// ── Responses ──────────────────────────────────────────────────────────────

export interface VerifierDescription {
  /** `WebCrypto SHA-256` or `software SHA-256 (FIPS 180-4)`. */
  readonly oracleName: string;
  /** Empty when WebCrypto was available; otherwise the reason it was not, verbatim. */
  readonly oracleNote: string;
  /** True when `crypto.subtle` is present, which is what the signature check needs. */
  readonly subtleAvailable: boolean;
}

export type VerifierResult =
  | { readonly kind: 'sha256'; readonly hex: string }
  | { readonly kind: 'ledger'; readonly report: CheckReport }
  | { readonly kind: 'note'; readonly result: CheckpointResult }
  | { readonly kind: 'boundary'; readonly outcome: BoundaryOutcome }
  | { readonly kind: 'describe'; readonly description: VerifierDescription };

export type VerifierResponse =
  | { readonly ok: true; readonly id: string; readonly result: VerifierResult }
  | { readonly ok: false; readonly id: string; readonly error: string };

// ── The handler ────────────────────────────────────────────────────────────

/**
 * Handle one request. Total: every input shape produces a response, and a thrown error
 * becomes `{ ok: false }` rather than an unhandled rejection inside a worker nobody is
 * watching.
 */
export async function handleVerifierRequest(
  request: VerifierRequest,
  host: { readonly crypto?: Crypto } = globalThis,
): Promise<VerifierResponse> {
  const { oracle, note } = resolveSha256(host);
  try {
    switch (request.kind) {
      case 'sha256':
        return ok(request.id, { kind: 'sha256', hex: toHex(await oracle.digest(request.bytes)) });

      case 'ledger': {
        const at = request.at;
        const report = await verifyLedger(request.payload, {
          oracle,
          config: request.config,
          subtle: host.crypto?.subtle,
          ...(at === undefined ? {} : { now: (): Date => new Date(at) }),
        });
        return ok(request.id, { kind: 'ledger', report });
      }

      case 'note': {
        const result = await verifyNote({
          note: request.note,
          keys: await parseKeys(oracle, request.vkeys),
          oracle,
          subtle: host.crypto?.subtle,
        });
        return ok(request.id, { kind: 'note', result });
      }

      case 'boundary':
        return ok(request.id, {
          kind: 'boundary',
          outcome: await verifyBoundary(oracle, request.input),
        });

      case 'describe':
        return ok(request.id, {
          kind: 'describe',
          description: {
            oracleName: oracle.name,
            oracleNote: note,
            subtleAvailable: host.crypto?.subtle !== undefined,
          },
        });

      default:
        return {
          ok: false,
          id: (request as { id?: string }).id ?? 'unknown',
          error: `unknown request kind ${JSON.stringify((request as { kind?: string }).kind)}`,
        };
    }
  } catch (error) {
    return { ok: false, id: request.id, error: error instanceof Error ? error.message : String(error) };
  }
}

async function parseKeys(
  oracle: Sha256Oracle,
  vkeys: readonly string[],
): Promise<Awaited<ReturnType<typeof parseVerificationKey>>[]> {
  const keys = [];
  for (const vkey of vkeys) keys.push(await parseVerificationKey(oracle, vkey));
  return keys;
}

function ok(id: string, result: VerifierResult): VerifierResponse {
  return { ok: true, id, result };
}

/** The config a caller sends when it has no anchor. Re-exported so callers need one import. */
export const NO_VERIFIER_ANCHOR: VerifierConfig = NO_ANCHOR;

// ── Worker installation ────────────────────────────────────────────────────

/**
 * A DedicatedWorkerGlobalScope has no `document`. The main thread and jsdom both do.
 *
 * The guard is a capability test rather than a build-time flag because this exact module
 * is imported by the inline fallback, by the unit tests, and by the worker; a flag would
 * have to be right in three places.
 */
interface MessagePosting {
  postMessage(message: unknown): void;
  addEventListener(type: 'message', listener: (event: MessageEvent<unknown>) => void): void;
}

export function installWorkerHandler(scope: MessagePosting, host: { readonly crypto?: Crypto }): void {
  scope.addEventListener('message', (event: MessageEvent<unknown>) => {
    const request = event.data as VerifierRequest;
    void handleVerifierRequest(request, host).then(
      (response) => {
        scope.postMessage(response);
      },
      (error: unknown) => {
        scope.postMessage({
          ok: false,
          id: request.id,
          error: error instanceof Error ? error.message : String(error),
        } satisfies VerifierResponse);
      },
    );
  });
}

const globalScope = globalThis as unknown as {
  readonly document?: unknown;
  readonly postMessage?: unknown;
  readonly addEventListener?: unknown;
};

if (
  globalScope.document === undefined &&
  typeof globalScope.postMessage === 'function' &&
  typeof globalScope.addEventListener === 'function'
) {
  installWorkerHandler(globalThis, globalThis);
}
