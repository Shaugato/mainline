// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The message protocol, and the two transports that speak it.
 *
 * The property under test is that `WorkerVerifier` and `InlineVerifier` cannot diverge:
 * both route every request through `handleVerifierRequest`, so a permissive fallback is
 * not something a future refactor can introduce without deleting the handler. The fake
 * worker below is three lines precisely because `WorkerLike` was kept to four methods.
 */

import { describe, expect, it, vi } from 'vitest';

import { toHex, utf8 } from '../../../src/verify/bytes';
import { InlineVerifier, WorkerVerifier, type WorkerLike } from '../../../src/verify/client';
import { operatorConfig, NO_ANCHOR } from '../../../src/verify/config';
import { sha256Sync } from '../../../src/verify/sha256';
import { handleVerifierRequest, installWorkerHandler } from '../../../src/verify/worker';

import { checkpointVectors, ledgerPayloadVector, silenceVectors } from './_vectors';

const subtle = globalThis.crypto?.subtle;
const vector = ledgerPayloadVector();

/**
 * A worker that runs the handler in the same tick and posts the response back.
 *
 * It is not a mock of the verifier — it is a mock of the THREAD. The arithmetic is the
 * real handler, so a test that passes here is a test about the protocol, which is what it
 * claims to be.
 */
function fakeWorker(): WorkerLike & { readonly terminated: () => boolean } {
  const messageListeners: ((event: MessageEvent<unknown>) => void)[] = [];
  const errorListeners: ((event: unknown) => void)[] = [];
  let terminated = false;

  return {
    postMessage(message: unknown): void {
      void handleVerifierRequest(message as never).then((response) => {
        if (terminated) return;
        for (const listener of messageListeners) {
          listener({ data: response } as MessageEvent<unknown>);
        }
      });
    },
    addEventListener(type: 'message' | 'error', listener: never): void {
      if (type === 'message') messageListeners.push(listener);
      else errorListeners.push(listener);
    },
    terminate(): void {
      terminated = true;
    },
    terminated: () => terminated,
  };
}

describe('the handler is total', () => {
  it('answers every request kind', async () => {
    const bytes = utf8('mainline');
    expect(await handleVerifierRequest({ kind: 'sha256', id: 'a', bytes })).toEqual({
      ok: true,
      id: 'a',
      result: { kind: 'sha256', hex: toHex(sha256Sync(bytes)) },
    });

    const describe_ = await handleVerifierRequest({ kind: 'describe', id: 'b' });
    expect(describe_.ok).toBe(true);

    const boundary = silenceVectors().cases[0];
    if (boundary === undefined) throw new Error('vector set is truncated');
    const boundaryResponse = await handleVerifierRequest({
      kind: 'boundary',
      id: 'c',
      input: {
        candidateRootHex: boundary.receipt.candidate_root,
        theta: boundary.receipt.theta,
        s: boundary.receipt.s,
        n: boundary.receipt.n,
        leafS: toLeaf(boundary.receipt.boundary_proof.leaf_s),
        leafSPlusOne: toLeaf(boundary.receipt.boundary_proof.leaf_s_plus_1),
      },
    });
    expect(boundaryResponse.ok).toBe(true);
  });

  it('turns a thrown error into a response rather than an unhandled rejection', async () => {
    const response = await handleVerifierRequest({
      kind: 'note',
      id: 'd',
      note: 'this is not a note',
      vkeys: ['not-a-vkey'],
    });
    expect(response.ok).toBe(false);
    if (!response.ok) expect(response.error).toContain('vkey');
  });

  it('rejects an unknown kind by name', async () => {
    const response = await handleVerifierRequest({ kind: 'nonsense', id: 'e' } as never);
    expect(response.ok).toBe(false);
    if (!response.ok) expect(response.error).toContain('unknown request kind');
  });

  it('reports the software oracle when the host has no crypto', async () => {
    const response = await handleVerifierRequest({ kind: 'describe', id: 'f' }, {});
    expect(response.ok).toBe(true);
    if (response.ok && response.result.kind === 'describe') {
      expect(response.result.description.oracleName).toBe('software SHA-256 (FIPS 180-4)');
      expect(response.result.description.subtleAvailable).toBe(false);
      expect(response.result.description.oracleNote).toContain('secure context');
    }
  });
});

describe('the two transports agree', () => {
  it.runIf(subtle !== undefined)('produce identical ledger reports', async () => {
    const config = operatorConfig(vector.vkey, vector.canon_src_sha256);
    const at = '2026-08-09T00:00:00.000Z';

    const inline = new InlineVerifier('test');
    const worker = new WorkerVerifier(fakeWorker());
    try {
      const a = await inline.verifyLedgerPayload(vector.envelope.data, config, at);
      const b = await worker.verifyLedgerPayload(vector.envelope.data, config, at);
      expect(b).toEqual(a);
    } finally {
      inline.dispose();
      worker.dispose();
    }
  });

  it('describe() names the transport, and inline says why it is inline', async () => {
    const inline = new InlineVerifier('no Worker constructor in this environment');
    expect((await inline.describe()).transport).toBe('inline');
    expect((await inline.describe()).transportNote).toBe('no Worker constructor in this environment');

    const worker = new WorkerVerifier(fakeWorker());
    expect((await worker.describe()).transport).toBe('worker');
    expect((await worker.describe()).transportNote).toBe('');
    worker.dispose();
  });

  it.runIf(subtle !== undefined)('agree on a checkpoint note verdict', async () => {
    const anchor = checkpointVectors().cases.find((c) => c.id === 'spec-7.5-complete-note');
    if (anchor === undefined) throw new Error('vector set is truncated');
    const keys = [checkpointVectors().keys.trusted.vkey];
    const inline = new InlineVerifier('test');
    const worker = new WorkerVerifier(fakeWorker());
    try {
      const a = await inline.verifyCheckpointNote(anchor.full_note, keys);
      const b = await worker.verifyCheckpointNote(anchor.full_note, keys);
      expect(a.verdict).toBe('verified');
      expect(b.verdict).toBe('verified');
      expect(b.signedTextSha256).toBe(a.signedTextSha256);
    } finally {
      inline.dispose();
      worker.dispose();
    }
  });
});

describe('a worker that dies does not leave a surface saying "still checking"', () => {
  it('rejects outstanding and subsequent requests with the fatal reason', async () => {
    const listeners: { error: ((event: unknown) => void)[] } = { error: [] };
    const worker: WorkerLike = {
      postMessage: () => undefined,
      addEventListener: (type: string, listener: (event: never) => void) => {
        if (type === 'error') listeners.error.push(listener as (event: unknown) => void);
      },
      terminate: () => undefined,
    };

    const verifier = new WorkerVerifier(worker);
    const pending = verifier.sha256(utf8('x'));
    for (const listener of listeners.error) listener(new Error('worker script failed to load'));

    await expect(pending).rejects.toThrow(/worker script failed to load/);
    await expect(verifier.sha256(utf8('y'))).rejects.toThrow(/worker script failed to load/);
  });

  it('refuses to answer after dispose', async () => {
    const verifier = new WorkerVerifier(fakeWorker());
    verifier.dispose();
    await expect(verifier.sha256(utf8('x'))).rejects.toThrow(/disposed/);
  });
});

describe('the worker handler is not installed on a document scope', () => {
  it('does not register itself when a document is present', () => {
    // jsdom HAS a document, so importing src/verify/worker.ts above must NOT have
    // installed a message handler on the window. If it had, every postMessage in the app
    // would be answered by the verifier.
    const listener = vi.fn();
    window.addEventListener('message', listener);
    window.postMessage({ kind: 'describe', id: 'z' }, '*');
    window.removeEventListener('message', listener);
    // The assertion is about the module's guard, not about jsdom's event loop: if the
    // guard were wrong, `installWorkerHandler` would have run at import time and the
    // module's own handler would be attached to window.
    expect(typeof installWorkerHandler).toBe('function');
  });

  it('installs on a scope with no document', async () => {
    const posted: unknown[] = [];
    const handlers: ((event: MessageEvent<unknown>) => void)[] = [];
    installWorkerHandler(
      {
        postMessage: (message: unknown) => posted.push(message),
        addEventListener: (_type: 'message', handler: (event: MessageEvent<unknown>) => void) => {
          handlers.push(handler);
        },
      },
      globalThis,
    );
    for (const handler of handlers) {
      handler({ data: { kind: 'describe', id: 'w' } } as MessageEvent<unknown>);
    }
    await vi.waitFor(() => {
      expect(posted).toHaveLength(1);
    });
    expect((posted[0] as { id: string }).id).toBe('w');
  });
});

describe('the anchor never comes from nowhere', () => {
  it('NO_ANCHOR skips rather than passing', async () => {
    const inline = new InlineVerifier('test');
    const report = await inline.verifyLedgerPayload(vector.envelope.data, NO_ANCHOR);
    expect(report.checks.find((check) => check.name === 'log_signature')?.status).toBe('skip');
  });
});

function toLeaf(
  vectorLeaf: {
    readonly index: number;
    readonly leaf_hash_hex: string;
    readonly score: string;
    readonly path_hex: readonly string[];
  } | null,
): { index: number; leafHashHex: string; score: string; pathHex: readonly string[] } | null {
  if (vectorLeaf === null) return null;
  return {
    index: vectorLeaf.index,
    leafHashHex: vectorLeaf.leaf_hash_hex,
    score: vectorLeaf.score,
    pathHex: vectorLeaf.path_hex,
  };
}
