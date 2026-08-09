// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The verifier, as the rest of the console sees it: one interface, two transports.
 *
 * `WorkerVerifier` posts to a real Web Worker. `InlineVerifier` calls the same handler on
 * the calling thread. They are the SAME code path in the sense that matters — both go
 * through `handleVerifierRequest`, so neither can drift into a more permissive
 * implementation than the other — and they differ only in whether a message crossed a
 * thread.
 *
 * `createVerifier()` tries the worker and falls back to inline, carrying the REASON it
 * fell back all the way to `describe().transportNote`, which the custody surface prints.
 * A silent fallback would make "verified in a worker" a claim nobody could check; a
 * fallback that threw would make the console unusable in jsdom, in a sandboxed iframe, and
 * on any host whose CSP forbids worker construction — three environments this product has
 * to work in.
 *
 * There is no cache and no memoisation of results. A verification is cheap, and a cached
 * verdict is a verdict about bytes that may no longer be the bytes on screen.
 */

import type { CheckReport, LedgerPayload } from './ledger';
import type { CheckpointResult } from './checkpoint';
import type { VerifierConfig } from './config';
import type { BoundaryOutcome, SilenceBoundaryInput } from './silenceroot';
import {
  handleVerifierRequest,
  type VerifierDescription,
  type VerifierRequest,
  type VerifierResponse,
  type VerifierResult,
} from './worker';

export type VerifierTransport = 'worker' | 'inline';

export interface VerifierInfo extends VerifierDescription {
  readonly transport: VerifierTransport;
  /** Verbatim. Empty when a worker was used and nothing needs explaining. */
  readonly transportNote: string;
}

export interface Verifier {
  describe(): Promise<VerifierInfo>;
  sha256(bytes: Uint8Array): Promise<string>;
  verifyLedgerPayload(
    payload: LedgerPayload,
    config: VerifierConfig,
    at?: string,
  ): Promise<CheckReport>;
  verifyCheckpointNote(note: string, vkeys: readonly string[]): Promise<CheckpointResult>;
  verifyBoundaryPair(input: SilenceBoundaryInput): Promise<BoundaryOutcome>;
  /** Releases the worker. Idempotent. */
  dispose(): void;
}

let counter = 0;
function nextId(): string {
  counter += 1;
  return `v${counter}`;
}

function unwrap<K extends VerifierResult['kind']>(
  response: VerifierResponse,
  kind: K,
): Extract<VerifierResult, { kind: K }> {
  if (!response.ok) throw new Error(`verifier: ${response.error}`);
  if (response.result.kind !== kind) {
    throw new Error(
      `verifier answered a ${response.result.kind} request with a ${kind} one. The protocol ` +
        'correlates by id and kind; a mismatch is a bug, not a value to interpret.',
    );
  }
  return response.result as Extract<VerifierResult, { kind: K }>;
}

// ── Inline ─────────────────────────────────────────────────────────────────

export class InlineVerifier implements Verifier {
  private readonly note: string;
  private readonly host: { readonly crypto?: Crypto };

  constructor(note: string, host: { readonly crypto?: Crypto } = globalThis) {
    this.note = note;
    this.host = host;
  }

  private send(request: VerifierRequest): Promise<VerifierResponse> {
    return handleVerifierRequest(request, this.host);
  }

  async describe(): Promise<VerifierInfo> {
    const result = unwrap(await this.send({ kind: 'describe', id: nextId() }), 'describe');
    return { ...result.description, transport: 'inline', transportNote: this.note };
  }

  async sha256(bytes: Uint8Array): Promise<string> {
    return unwrap(await this.send({ kind: 'sha256', id: nextId(), bytes }), 'sha256').hex;
  }

  async verifyLedgerPayload(
    payload: LedgerPayload,
    config: VerifierConfig,
    at?: string,
  ): Promise<CheckReport> {
    const request: VerifierRequest = {
      kind: 'ledger',
      id: nextId(),
      payload,
      config,
      ...(at === undefined ? {} : { at }),
    };
    return unwrap(await this.send(request), 'ledger').report;
  }

  async verifyCheckpointNote(note: string, vkeys: readonly string[]): Promise<CheckpointResult> {
    return unwrap(await this.send({ kind: 'note', id: nextId(), note, vkeys }), 'note').result;
  }

  async verifyBoundaryPair(input: SilenceBoundaryInput): Promise<BoundaryOutcome> {
    return unwrap(await this.send({ kind: 'boundary', id: nextId(), input }), 'boundary').outcome;
  }

  dispose(): void {
    // Nothing to release: the inline verifier owns no thread.
  }
}

// ── Worker ─────────────────────────────────────────────────────────────────

/** The subset of `Worker` this client uses. Narrow so a test double is three lines. */
export interface WorkerLike {
  postMessage(message: unknown): void;
  addEventListener(type: 'message', listener: (event: MessageEvent<unknown>) => void): void;
  addEventListener(type: 'error', listener: (event: unknown) => void): void;
  terminate(): void;
}

export class WorkerVerifier implements Verifier {
  private readonly worker: WorkerLike;
  private readonly pending = new Map<string, (response: VerifierResponse) => void>();
  private disposed = false;
  private fatal: string | null = null;

  constructor(worker: WorkerLike) {
    this.worker = worker;
    this.worker.addEventListener('message', (event: MessageEvent<unknown>) => {
      const response = event.data as VerifierResponse;
      const resolve = this.pending.get(response.id);
      if (resolve === undefined) return;
      this.pending.delete(response.id);
      resolve(response);
    });
    this.worker.addEventListener('error', (event: unknown) => {
      // A worker that died takes every outstanding request with it. Rejecting them beats
      // leaving a surface in `verifying` for ever, which reads as "still checking".
      this.fatal = `the verification worker failed: ${describeError(event)}`;
      for (const [id, resolve] of this.pending) {
        resolve({ ok: false, id, error: this.fatal });
      }
      this.pending.clear();
    });
  }

  private send(request: VerifierRequest): Promise<VerifierResponse> {
    if (this.fatal !== null) {
      return Promise.resolve({ ok: false, id: request.id, error: this.fatal });
    }
    if (this.disposed) {
      return Promise.resolve({ ok: false, id: request.id, error: 'the verifier has been disposed' });
    }
    return new Promise<VerifierResponse>((resolve) => {
      this.pending.set(request.id, resolve);
      this.worker.postMessage(request);
    });
  }

  async describe(): Promise<VerifierInfo> {
    const result = unwrap(await this.send({ kind: 'describe', id: nextId() }), 'describe');
    return { ...result.description, transport: 'worker', transportNote: '' };
  }

  async sha256(bytes: Uint8Array): Promise<string> {
    return unwrap(await this.send({ kind: 'sha256', id: nextId(), bytes }), 'sha256').hex;
  }

  async verifyLedgerPayload(
    payload: LedgerPayload,
    config: VerifierConfig,
    at?: string,
  ): Promise<CheckReport> {
    const request: VerifierRequest = {
      kind: 'ledger',
      id: nextId(),
      payload,
      config,
      ...(at === undefined ? {} : { at }),
    };
    return unwrap(await this.send(request), 'ledger').report;
  }

  async verifyCheckpointNote(note: string, vkeys: readonly string[]): Promise<CheckpointResult> {
    return unwrap(await this.send({ kind: 'note', id: nextId(), note, vkeys }), 'note').result;
  }

  async verifyBoundaryPair(input: SilenceBoundaryInput): Promise<BoundaryOutcome> {
    return unwrap(await this.send({ kind: 'boundary', id: nextId(), input }), 'boundary').outcome;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.pending.clear();
    this.worker.terminate();
  }
}

function describeError(event: unknown): string {
  if (event instanceof Error) return event.message;
  if (typeof event === 'object' && event !== null && 'message' in event) {
    return String(event.message);
  }
  return String(event);
}

// ── Composition ────────────────────────────────────────────────────────────

/**
 * A verifier, preferring a worker and saying so when it could not have one.
 *
 * `new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })` is the form
 * Vite recognises statically, which is what makes the worker a real build artefact rather
 * than a runtime fetch of a path that will not exist after bundling.
 */
export function createVerifier(): Verifier {
  if (typeof Worker !== 'function') {
    return new InlineVerifier(
      'This environment has no Worker constructor, so verification ran on the main thread. ' +
        'The arithmetic is identical — both paths call the same handler — but it was not ' +
        'isolated behind a message boundary.',
    );
  }
  try {
    const worker = new Worker(new URL('./worker.ts', import.meta.url), {
      type: 'module',
      name: 'mainline-verify',
    });
    return new WorkerVerifier(worker);
  } catch (error) {
    return new InlineVerifier(
      'The verification worker could not be constructed (' +
        (error instanceof Error ? error.message : String(error)) +
        '), so verification ran on the main thread. A Content-Security-Policy without ' +
        "`worker-src` is the usual cause. The arithmetic is identical — both paths call the " +
        'same handler — but it was not isolated behind a message boundary.',
    );
  }
}
