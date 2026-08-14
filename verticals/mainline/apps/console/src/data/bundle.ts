// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The EvidenceBundle player (D7).
 *
 * An EvidenceBundle is a content-addressed directory — `manifest.json`, `frames/`,
 * `ledger/`, `sql/` — produced by `scripts/capture-bundle.ts`. The player mounts it
 * behind the SAME client interface the live transport implements, so `LIVE` and
 * `REPLAY` differ in one line of composition and in one badge.
 *
 * Why this is not a mock, stated as a mechanism rather than a promise:
 *
 *   **`BundleTransport` cannot serve a single frame before manifest verification has
 *   RESOLVED, and it has no verifier of its own.** There is no default verifier in this
 *   module and no "skip verification" option, because a default that passes is a lie
 *   with a configuration flag in front of it. The verifier is injected — it is the
 *   in-browser RFC 8785 / RFC 6962 / ECDSA implementation owned by the
 *   verifier-custody-room worker — and until it returns `verified`, every `exchange`
 *   raises. A tampered fixture therefore renders a failure state, never a screen.
 *
 * This file computes NO digest and verifies NO signature. It does exactly three things
 * the verifier cannot do for it:
 *
 *   1. it holds the byte cache, so the bytes the verifier hashed are literally the
 *      bytes the transport later serves — a second read of a hostile source cannot
 *      return different content after the check has passed;
 *   2. it refuses a file whose declared `bytes` length disagrees with what arrived,
 *      which is a length comparison, not a hash, and which turns a truncated download
 *      into a clear error rather than a digest mismatch nobody can interpret;
 *   3. it refuses a frame that is not listed in the manifest at all, because an
 *      unlisted file is outside everything the verifier checked.
 */

import type { SchemaRegistry } from './schema';
import { formatErrors } from './schema';
import type {
  Exchange,
  MainlineTransport,
  TransportDescription,
} from './transport';
import { TransportError, finishExchange } from './transport';
import type { ResourceRequest } from './resources';
import { resolveRequest } from './resources';

// ── Bundle shapes ──────────────────────────────────────────────────────────

export const BUNDLE_SCHEMA_ID = 'https://console.mainline.trappoint.org/contracts/1.0/bundle.schema.json';
export const MANIFEST_PATH = 'manifest.json';

export interface BundleFileEntry {
  readonly path: string;
  readonly sha256: string;
  readonly bytes: number;
  readonly media_type?: string | null;
  /**
   * Frames only: the canonical request key this frame answers, verbatim.
   *
   * This is how a frame is ADDRESSED. The file name is a content address
   * (`<METHOD>-<sha256(key)[:16]>.json`, written by `scripts/capture-bundle.ts`) and is
   * deliberately opaque here — `src/data/**` computes no digests, so it could not
   * re-derive a name even if it wanted to. Carrying the request line in the manifest
   * puts it inside the sealed set the verifier hashes, which is a stronger place for it
   * than a directory entry nothing checks. The frame repeats its own key and the
   * transport compares the two below.
   *
   * OPTIONAL BUT NEVER NULL, and the difference is the contract's, not a preference.
   * `contracts/bundle.schema.json#/$defs/file_entry` declares `key` as
   * `{"type": "string", "minLength": 1}` — absent is allowed, null is not — and
   * `BundleTransport.manifest()` validates every parsed manifest against that document
   * before returning it, so a null key is refused at the door and cannot reach any
   * consumer of this interface. This field read `string | null` until 2026-08-14, which
   * was a claim the validated input could never satisfy; `types.generated.ts` had no
   * `key` at all at the time, so the subtype assertion in `tests/unit/data/types.test.ts`
   * could not see the disagreement. Regenerating the types made it visible.
   *
   * The runtime narrowing in `keyFromManifestEntry` is deliberately NOT relaxed to match:
   * defence at the boundary is cheap, and this type describes what the contract permits
   * rather than what a defensive reader tolerates.
   */
  readonly key?: string;
}

export interface BundleClusterFingerprint {
  readonly source: 'observed' | 'declared';
  readonly product: string;
  readonly version: string;
  readonly cluster_version?: string | null;
  readonly tier?: string | null;
  readonly region: string;
  readonly evidence_ref?: string | null;
}

export interface BundleCheckpointRef {
  readonly site_code: string;
  readonly tree_size: number;
  readonly root_hex: string;
  readonly note_path: string;
  readonly custody_bundle_path?: string | null;
}

export interface BundleManifest {
  readonly manifest_version: 1;
  readonly bundle_id: string;
  readonly captured_at: string;
  readonly generator?: string | null;
  readonly cluster_fingerprint: BundleClusterFingerprint;
  readonly schema_version: string;
  readonly staged: boolean;
  readonly staged_note?: string | null;
  readonly checkpoint: BundleCheckpointRef | null;
  readonly files: readonly BundleFileEntry[];
}

export interface BundleNamedValue {
  readonly name: string;
  readonly value: string;
}

export interface BundleFrame {
  readonly frame_version: 1;
  readonly key: string;
  readonly request: {
    readonly method: 'GET' | 'POST';
    readonly path: string;
    readonly query?: readonly BundleNamedValue[];
    readonly body_b64?: string | null;
  };
  readonly response: {
    readonly status: number;
    readonly headers?: readonly BundleNamedValue[];
    readonly body_b64: string;
  };
  readonly captured_at: string;
  readonly duration_ms?: number | null;
}

// ── The source ─────────────────────────────────────────────────────────────

/** Where a bundle's bytes come from. Deliberately tiny: one method, no seeking. */
export interface BundleSource {
  /** A name a human can read in an error message: a URL, or a fixture id. */
  readonly id: string;
  /** Rejects when the path is absent. Paths are bundle-relative and forward-slashed. */
  read(path: string, signal?: AbortSignal): Promise<Uint8Array>;
}

/** Reads a bundle served as static files. The demo URL's normal case. */
export class FetchBundleSource implements BundleSource {
  readonly id: string;
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(baseUrl: string, fetchImpl?: typeof fetch) {
    this.baseUrl = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;
    this.id = this.baseUrl;
    this.fetchImpl = fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  async read(path: string, signal?: AbortSignal): Promise<Uint8Array> {
    const url = new URL(path, this.baseUrl).toString();
    const init: RequestInit = signal === undefined ? {} : { signal };
    const response = await this.fetchImpl(url, init);
    if (!response.ok) {
      throw new Error(`GET ${url} → HTTP ${response.status}`);
    }
    return new Uint8Array(await response.arrayBuffer());
  }
}

/** Reads a bundle already in memory. Tests and the cinema harness use this. */
export class MemoryBundleSource implements BundleSource {
  readonly id: string;
  private readonly files: ReadonlyMap<string, Uint8Array>;

  constructor(id: string, files: ReadonlyMap<string, Uint8Array> | Record<string, Uint8Array>) {
    this.id = id;
    this.files =
      files instanceof Map ? files : new Map(Object.entries(files));
  }

  read(path: string): Promise<Uint8Array> {
    const bytes = this.files.get(path);
    if (bytes === undefined) {
      return Promise.reject(new Error(`${this.id}: no such file in bundle: ${path}`));
    }
    return Promise.resolve(bytes);
  }
}

// ── The verification hook ──────────────────────────────────────────────────

export interface BundleFinding {
  /** Bundle-relative path, or `manifest.json`, or a checkpoint identifier. */
  readonly subject: string;
  /** The named check that produced it, e.g. `manifest-digest`, `inclusion-proof`. */
  readonly check: string;
  /** Verbatim. Rendered on screen without paraphrase. */
  readonly detail: string;
}

/**
 * `verified` — every check the verifier ran passed.
 * `failed`   — at least one check failed. Findings say which.
 *
 * There is deliberately no third value. "Unverified" is not a verdict this hook may
 * return: a verifier that cannot check something reports it as a finding with a named
 * SKIP reason and decides, itself, whether the bundle is still servable. The transport
 * must never be in a position to interpret an ambiguous verdict optimistically.
 */
export type BundleVerdict = 'verified' | 'failed';

export interface BundleVerificationReport {
  readonly verdict: BundleVerdict;
  /** SHA-256 of the manifest bytes, lowercase hex. Computed by the verifier, not here. */
  readonly manifestDigest: string;
  /** How many of `manifest.files` the verifier actually checked. */
  readonly filesChecked: number;
  /** A one-line summary, verbatim, for the honesty chrome. */
  readonly summary: string;
  readonly findings: readonly BundleFinding[];
}

export interface BundleVerificationInput {
  readonly manifestBytes: Uint8Array;
  readonly manifest: BundleManifest;
  /**
   * Reads a bundle file through the transport's cache. Using this — rather than the
   * source directly — is what makes "the bytes I checked are the bytes you serve" true.
   */
  readonly read: (path: string) => Promise<Uint8Array>;
  readonly signal?: AbortSignal;
}

/** Implemented by the in-browser verifier (worker: verifier-custody-room). */
export interface BundleVerifier {
  readonly name: string;
  verify(input: BundleVerificationInput): Promise<BundleVerificationReport>;
}

// ── The transport ──────────────────────────────────────────────────────────

export interface BundleTransportOptions {
  readonly source: BundleSource;
  readonly registry: SchemaRegistry;
  /**
   * REQUIRED. There is no default and no null case. A bundle player with no verifier
   * is a mock, and this console does not ship one.
   */
  readonly verifier: BundleVerifier;
  readonly now?: () => number;
}

const textDecoder = new TextDecoder('utf-8', { fatal: true });

export class BundleTransport implements MainlineTransport {
  private readonly source: BundleSource;
  private readonly registry: SchemaRegistry;
  private readonly verifier: BundleVerifier;
  private readonly now: () => number;

  /** path → bytes. Populated on first read and never invalidated. */
  private readonly cache = new Map<string, Uint8Array>();
  private readonly inflight = new Map<string, Promise<Uint8Array>>();

  private opening: Promise<OpenedBundle> | null = null;
  private opened: OpenedBundle | null = null;

  constructor(options: BundleTransportOptions) {
    this.source = options.source;
    this.registry = options.registry;
    this.verifier = options.verifier;
    this.now = options.now ?? Date.now;
  }

  describe(): TransportDescription {
    const opened = this.opened;
    return {
      mode: 'replay',
      source: opened?.manifest.bundle_id ?? this.source.id,
      // Null until the verifier has reported one. The chrome shows "unknown" rather
      // than a digest nobody has computed.
      bundleDigestPrefix:
        opened === null ? null : opened.report.manifestDigest.slice(0, 12),
      staged: opened?.manifest.staged ?? true,
      stagedNote:
        opened?.manifest.staged_note ??
        (opened === null ? 'The bundle has not been opened, so nothing about it is established yet.' : null),
    };
  }

  /** The manifest, once opened. Null before that — never a guess. */
  manifest(): BundleManifest | null {
    return this.opened?.manifest ?? null;
  }

  /** The verifier's report, once it has resolved. Null before that. */
  report(): BundleVerificationReport | null {
    return this.opened?.report ?? null;
  }

  /**
   * Opens and verifies. Idempotent: concurrent callers share one promise, and a
   * failure is remembered rather than retried, because a bundle that failed
   * verification does not become verified by asking again.
   */
  async open(signal?: AbortSignal): Promise<OpenedBundle> {
    this.opening ??= this.doOpen(signal);
    return this.opening;
  }

  private async doOpen(signal?: AbortSignal): Promise<OpenedBundle> {
    const manifestBytes = await this.readCached(MANIFEST_PATH, signal);
    const manifestText = decodeUtf8(MANIFEST_PATH, manifestBytes);

    let parsed: unknown;
    try {
      parsed = JSON.parse(manifestText);
    } catch (error) {
      throw new TransportError('malformed', MANIFEST_PATH, `manifest is not JSON: ${String(error)}`);
    }

    const validation = this.registry.validate(BUNDLE_SCHEMA_ID, parsed);
    if (!validation.valid) {
      throw new TransportError(
        'contract',
        MANIFEST_PATH,
        `manifest does not satisfy ${BUNDLE_SCHEMA_ID}.\n${formatErrors(validation.errors)}`,
        validation.errors,
      );
    }
    const manifest = parsed as BundleManifest;

    const byPath = new Map<string, BundleFileEntry>();
    const byKey = new Map<string, BundleFileEntry>();
    for (const entry of manifest.files) {
      if (byPath.has(entry.path)) {
        throw new TransportError(
          'malformed',
          MANIFEST_PATH,
          `manifest lists "${entry.path}" twice. Two digests for one path is a contradiction, not a duplicate.`,
        );
      }
      byPath.set(entry.path, entry);

      // The request index. A frame is served by KEY, so two entries claiming one key
      // would make which answer is served depend on manifest order — refuse instead of
      // picking, and name both files while both are still in hand.
      const key = entry.key ?? null;
      if (key === null || key === '') continue;
      const rival = byKey.get(key);
      if (rival !== undefined) {
        throw new TransportError(
          'malformed',
          MANIFEST_PATH,
          `manifest files "${rival.path}" and "${entry.path}" both answer ${JSON.stringify(key)}. ` +
            'One request has one captured answer; a bundle offering two cannot say which it means.',
        );
      }
      byKey.set(key, entry);
    }
    if (byPath.has(MANIFEST_PATH)) {
      throw new TransportError(
        'malformed',
        MANIFEST_PATH,
        'the manifest lists itself. A file cannot carry its own digest, and a manifest that ' +
          'claims to is asserting something no reader can check.',
      );
    }

    const report = await this.verifier.verify({
      manifestBytes,
      manifest,
      read: (path: string) => this.readListed(path, byPath, signal),
      ...(signal === undefined ? {} : { signal }),
    });

    if (report.verdict !== 'verified') {
      throw new TransportError(
        'tampered',
        MANIFEST_PATH,
        `${this.verifier.name} refused this bundle: ${report.summary}\n` +
          report.findings.map((f) => `  ${f.subject}  ${f.check}: ${f.detail}`).join('\n'),
      );
    }

    const openedBundle: OpenedBundle = { manifest, report, files: byPath, frames: byKey };
    this.opened = openedBundle;
    return openedBundle;
  }

  async exchange<T = unknown>(request: ResourceRequest, signal?: AbortSignal): Promise<Exchange<T>> {
    const resolved = resolveRequest(request);

    // Identical to the live transport: an already-aborted caller gets nothing done on
    // its behalf. Replay is not an excuse to ignore cancellation — the surfaces are
    // written against one behaviour, so there is one behaviour.
    if (signal?.aborted === true) {
      throw new TransportError('aborted', resolved.key, String(signal.reason ?? 'aborted before start'));
    }

    // THE GATE. Nothing below this line runs until verification has resolved, and a
    // failed verification throws out of `open()` rather than returning a degraded state.
    const opened = await this.open(signal);

    // Addressed by KEY, through the manifest. The frame's file name is a content address
    // this module cannot compute — `src/data/**` hashes nothing — so the manifest's
    // `key` field is the index, and it is inside the set the verifier already sealed.
    const entry = opened.frames.get(resolved.key);
    if (entry === undefined) {
      throw new TransportError(
        'missing_frame',
        resolved.key,
        `bundle "${opened.manifest.bundle_id}" has no frame for this request. ` +
          'It captured a different set of exchanges; it is not incomplete for this one.',
      );
    }
    const framePath = entry.path;

    const frameBytes = await this.readListed(framePath, opened.files, signal);
    const frameText = decodeUtf8(framePath, frameBytes);

    let parsedFrame: unknown;
    try {
      parsedFrame = JSON.parse(frameText);
    } catch (error) {
      throw new TransportError('malformed', resolved.key, `${framePath} is not JSON: ${String(error)}`);
    }

    const frameValidation = this.registry.validate(BUNDLE_SCHEMA_ID, parsedFrame, '/$defs/frame');
    if (!frameValidation.valid) {
      throw new TransportError(
        'contract',
        resolved.key,
        `${framePath} does not satisfy ${BUNDLE_SCHEMA_ID}#/$defs/frame.\n${formatErrors(frameValidation.errors)}`,
        frameValidation.errors,
      );
    }
    const frame = parsedFrame as BundleFrame;

    if (frame.key !== resolved.key) {
      throw new TransportError(
        'mismatch',
        resolved.key,
        `${framePath} carries key "${frame.key}". The file name and the key inside it must agree; ` +
          'a frame filed under the wrong name is how a swapped fixture presents.',
      );
    }

    assertBodyMatches(resolved.key, framePath, frame, resolved.body);

    const responseText = decodeBase64ToText(framePath, frame.response.body_b64);
    return finishExchange<T>(
      this.registry,
      resolved,
      frame.response.status,
      responseText,
      'replay',
      this.now(),
    );
  }

  private async readCached(path: string, signal?: AbortSignal): Promise<Uint8Array> {
    const cached = this.cache.get(path);
    if (cached !== undefined) return cached;

    const existing = this.inflight.get(path);
    if (existing !== undefined) return existing;

    const promise = this.source
      .read(path, signal)
      .then((bytes) => {
        this.cache.set(path, bytes);
        this.inflight.delete(path);
        return bytes;
      })
      .catch((error: unknown) => {
        this.inflight.delete(path);
        throw new TransportError('missing_frame', path, String(error));
      });
    this.inflight.set(path, promise);
    return promise;
  }

  /**
   * Reads a file that the manifest lists, and refuses one it does not.
   *
   * The byte-length check is the only integrity assertion this file makes, and it is
   * deliberately not a hash: a truncated response produces a clear "declared N bytes,
   * received M" instead of a digest mismatch that reads like tampering.
   */
  private async readListed(
    path: string,
    files: ReadonlyMap<string, BundleFileEntry>,
    signal?: AbortSignal,
  ): Promise<Uint8Array> {
    const entry = files.get(path);
    if (entry === undefined) {
      throw new TransportError(
        'missing_frame',
        path,
        'this path is not listed in manifest.files, so nothing has checked it. ' +
          'An unlisted file is outside the verified set and is never served.',
      );
    }
    const bytes = await this.readCached(path, signal);
    if (bytes.byteLength !== entry.bytes) {
      throw new TransportError(
        'tampered',
        path,
        `manifest declares ${entry.bytes} bytes, received ${bytes.byteLength}.`,
      );
    }
    return bytes;
  }
}

export interface OpenedBundle {
  readonly manifest: BundleManifest;
  readonly report: BundleVerificationReport;
  readonly files: ReadonlyMap<string, BundleFileEntry>;
  /** The frame index: canonical request key -> the manifest entry that answers it. */
  readonly frames: ReadonlyMap<string, BundleFileEntry>;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function decodeUtf8(path: string, bytes: Uint8Array): string {
  try {
    return textDecoder.decode(bytes);
  } catch (error) {
    throw new TransportError('malformed', path, `not valid UTF-8: ${String(error)}`);
  }
}

/**
 * Base64 → text, via the platform decoder.
 *
 * Bodies are carried base64 so a capture is byte-for-byte: a frame that stored a
 * re-serialised JSON object would be testing our JSON writer rather than the server's
 * output, and a whitespace difference would silently change every digest computed over
 * it.
 */
export function decodeBase64ToText(path: string, b64: string): string {
  let binary: string;
  try {
    binary = atob(b64);
  } catch (error) {
    throw new TransportError('malformed', path, `body_b64 is not base64: ${String(error)}`);
  }
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return decodeUtf8(path, bytes);
}

/**
 * A replayed POST must be the POST that was captured.
 *
 * Replay answers the question that was asked when the bundle was made. Serving a
 * captured response to a different request body would let the console appear to
 * transact — a signature with different text, a merge of a different subject — and
 * report the old outcome. That is precisely the fabricated screen the whole design
 * exists to make impossible, so a divergence is a hard failure and there is no
 * "loose matching" option.
 */
function assertBodyMatches(
  requestKey: string,
  framePath: string,
  frame: BundleFrame,
  body: unknown,
): void {
  const capturedB64 = frame.request.body_b64 ?? null;
  if (frame.request.method !== 'POST') return;

  const captured: unknown =
    capturedB64 === null ? null : JSON.parse(decodeBase64ToText(framePath, capturedB64));
  const sent: unknown = body ?? {};

  if (!deepEqual(captured ?? {}, sent)) {
    throw new TransportError(
      'mismatch',
      requestKey,
      `${framePath} captured a different request body. Replay answers the exchange that was ` +
        'captured; it cannot answer a new one. Capture a bundle for the request you want to make.',
    );
  }
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a === null || b === null) return false;
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((item, index) => deepEqual(item, b[index]));
  }
  if (typeof a === 'object' && typeof b === 'object') {
    const aKeys = Object.keys(a).sort();
    const bKeys = Object.keys(b).sort();
    if (aKeys.length !== bKeys.length || !aKeys.every((key, index) => key === bKeys[index])) {
      return false;
    }
    return aKeys.every((key) =>
      deepEqual((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key]),
    );
  }
  return false;
}
