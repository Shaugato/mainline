// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The audit: read every file the manifest lists, hash it, and compare.
 *
 * ── WHAT THIS ESTABLISHES, AND WHAT IT DOES NOT ──────────────────────────────────
 *
 * It answers exactly one question — **are these the bytes that were sealed?** — and it
 * answers it with arithmetic a stranger can repeat with `sha256sum`. It says nothing
 * about whether the ledger inside the bundle verifies (that is the custody surface's
 * RFC 6962 and ECDSA work, owned by `src/verify/`), and nothing about whether the
 * numbers describe a real cluster (that is what `staged` is for). `model.ts`'s `LIMITS`
 * says both of those on screen, because a verification surface that overstates itself
 * is self-refuting.
 *
 * ── ONE IMPLEMENTATION, TWO CONSUMERS ────────────────────────────────────────────
 *
 * `auditFiles()` is the loop. `auditBundle()` wraps it for the screen; the
 * `manifestIntegrityVerifier()` wraps the same loop as the `BundleVerifier` that
 * `BundleTransport` demands before it will serve a single frame. That matters: the
 * transport's gate and the inventory on this screen are then the SAME arithmetic, so a
 * bundle that renders here as clean is a bundle the transport will play, and a bundle
 * that fails here cannot be played at all. Two implementations could disagree; one
 * cannot.
 *
 * The verifier is exported for the COMPOSITION ROOT to inject. `src/data/` must never
 * import it — the transport is deliberately verifier-agnostic, and a data layer that
 * reached into a feature directory for its verifier would invert the dependency and
 * make the "no default verifier" rule editable from the wrong place.
 *
 * ── WHY THE STRUCTURAL CONTRADICTIONS ARE FINDINGS HERE, NOT THROWS ──────────────
 *
 * `BundleTransport` refuses a manifest that lists itself, or lists a path twice, by
 * throwing: it must not serve anything. This screen is where a reader goes to find out
 * WHY the transport refused, so the same contradictions are recorded as named findings
 * and the inventory still renders. The verdict is `failed` either way.
 */

import {
  BUNDLE_SCHEMA_ID,
  MANIFEST_PATH,
  type BundleFinding,
  type BundleManifest,
  type BundleSource,
  type BundleVerificationInput,
  type BundleVerificationReport,
  type BundleVerifier,
} from '../../data/bundle';
import { formatErrors, type SchemaRegistry } from '../../data/schema';

import type { DigestOracle } from './digest';
import {
  buildInventory,
  summarise,
  type Coverage,
  type InventoryRow,
} from './model';
import { isListable } from './source';

/** Thrown when the caller's signal aborts mid-audit. Distinguishes it from a failure. */
export class AuditAborted extends Error {
  constructor(reason: string) {
    super(`audit aborted: ${reason}`);
    this.name = 'AuditAborted';
  }
}

function assertLive(signal: AbortSignal | undefined): void {
  if (signal?.aborted === true) {
    throw new AuditAborted(String(signal.reason ?? 'no reason given'));
  }
}

// ── The loop ───────────────────────────────────────────────────────────────

export interface AuditFilesInput {
  readonly manifest: BundleManifest;
  /** Reads one bundle-relative path. Rejects when the file is absent. */
  readonly read: (path: string) => Promise<Uint8Array>;
  readonly oracle: DigestOracle;
  /** Directory listing, when the source can produce one. `null` when it cannot. */
  readonly unlisted: readonly string[] | null;
  readonly signal?: AbortSignal;
  readonly onProgress?: (done: number, total: number) => void;
}

export interface AuditFilesResult {
  readonly rows: readonly InventoryRow[];
  readonly coverage: Coverage;
  readonly findings: readonly BundleFinding[];
}

/**
 * Hashes every listed file, in manifest order, one at a time.
 *
 * Sequential on purpose. Parallel reads would finish sooner and would make the
 * progress report meaningless, the abort semantics fuzzy, and the memory ceiling equal
 * to the whole bundle. A bundle is twenty files; there is nothing to win here.
 */
export async function auditFiles(input: AuditFilesInput): Promise<AuditFilesResult> {
  const { manifest, read, oracle, unlisted, signal, onProgress } = input;
  const declared = buildInventory(manifest);
  const findings: BundleFinding[] = [];
  const rows: InventoryRow[] = [];

  // Structural contradictions in the manifest itself, before a byte is read.
  const seen = new Set<string>();
  for (const entry of manifest.files) {
    if (seen.has(entry.path)) {
      findings.push({
        subject: entry.path,
        check: 'manifest-duplicate-path',
        detail:
          'manifest.files lists this path more than once. Two digests for one path is a ' +
          'contradiction, not a duplicate — BundleTransport refuses such a manifest outright.',
      });
    }
    seen.add(entry.path);
  }
  if (seen.has(MANIFEST_PATH)) {
    findings.push({
      subject: MANIFEST_PATH,
      check: 'manifest-lists-itself',
      detail:
        'the manifest lists itself. A file cannot carry its own digest, and a manifest that ' +
        'claims to is asserting something no reader can check.',
    });
  }

  let done = 0;
  for (const row of declared) {
    assertLive(signal);

    let bytes: Uint8Array;
    try {
      bytes = await read(row.path);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      rows.push({ ...row, state: 'unreadable', detail });
      findings.push({ subject: row.path, check: 'file-present', detail });
      done += 1;
      onProgress?.(done, declared.length);
      continue;
    }

    const actualDigest = await oracle.sha256(bytes);
    const actualBytes = bytes.byteLength;
    const digestAgrees = actualDigest === row.declaredDigest;
    const lengthAgrees = actualBytes === row.declaredBytes;

    if (digestAgrees && lengthAgrees) {
      rows.push({ ...row, state: 'match', actualDigest, actualBytes, detail: null });
    } else {
      // The byte length is reported separately from the digest, deliberately: a
      // truncated download and a substituted file are different accidents, and
      // "declared 9158 bytes, received 4096" is a diagnosis while a digest mismatch
      // alone is only an alarm.
      const detail = digestAgrees
        ? `manifest declares ${row.declaredBytes} bytes; ${actualBytes} arrived, yet the ` +
          'digest matched. The manifest is internally inconsistent.'
        : `manifest declares sha256 ${row.declaredDigest}; these bytes hash to ${actualDigest}` +
          (lengthAgrees ? '.' : ` (and ${actualBytes} bytes arrived, not ${row.declaredBytes}).`);
      rows.push({ ...row, state: 'mismatch', actualDigest, actualBytes, detail });
      findings.push({
        subject: row.path,
        check: digestAgrees ? 'manifest-byte-length' : 'manifest-digest',
        detail,
      });
    }

    if (row.kind === 'frame') {
      if (row.frame === null) {
        findings.push({
          subject: row.path,
          check: 'frame-name-undecodable',
          detail:
            'this file is under frames/ but its name is not a valid ~XX encoding of a request ' +
            'key, so no request can address it. It is a file no screen can ever read.',
        });
      } else if (!row.frame.canonical) {
        findings.push({
          subject: row.path,
          check: 'frame-name-non-canonical',
          detail:
            `the name decodes to "${row.frame.requestKey}", but the canonical encoding of that ` +
            'key is a different file name. A frame filed under a non-canonical name is what a ' +
            'hand-edited bundle looks like.',
        });
      }
    }

    done += 1;
    onProgress?.(done, declared.length);
  }

  for (const path of unlisted ?? []) {
    findings.push({
      subject: path,
      check: 'unlisted-file',
      detail:
        'present in the bundle directory but absent from manifest.files, so nothing has ' +
        'checked it. The transport never serves an unlisted file; it is reported here because ' +
        'a file nobody checked should not be in an evidence directory at all.',
    });
  }

  const coverage = summarise(rows, unlisted);
  if (!coverage.conserved) {
    findings.push({
      subject: MANIFEST_PATH,
      check: 'coverage-conservation',
      detail:
        `${coverage.filesDeclared} file(s) declared but ` +
        `${coverage.digestsMatched} + ${coverage.digestsMismatched} + ` +
        `${coverage.filesUnreadable} + ${coverage.filesUnchecked} accounted for. The audit's ` +
        'own bookkeeping does not balance, so no count on this screen may be relied on.',
    });
  }

  return { rows, coverage, findings };
}

// ── The screen's entry point ───────────────────────────────────────────────

export type AuditVerdict = 'verified' | 'failed';

export interface AuditedBundle {
  readonly kind: 'audited';
  readonly manifest: BundleManifest;
  /** SHA-256 of the manifest bytes themselves, recomputed here. */
  readonly manifestDigest: string;
  /** ISO-8601 UTC instant at which THIS BROWSER finished. */
  readonly at: string;
  readonly oracleName: string;
  readonly sourceId: string;
  readonly rows: readonly InventoryRow[];
  readonly coverage: Coverage;
  readonly findings: readonly BundleFinding[];
  readonly verdict: AuditVerdict;
}

export type BundleAudit =
  | AuditedBundle
  | {
      readonly kind: 'unreadable';
      readonly where: string;
      readonly detail: string;
      readonly sourceId: string;
    }
  | {
      readonly kind: 'malformed';
      readonly where: string;
      readonly detail: string;
      readonly sourceId: string;
    };

export interface AuditBundleOptions {
  readonly source: BundleSource;
  readonly oracle: DigestOracle;
  /** Defaults to the compiled contract registry; injectable for tests. */
  readonly registry?: SchemaRegistry;
  /** ISO-8601 UTC instant. Injectable so cinema mode (D12) can freeze it. */
  readonly clock?: () => string;
  readonly signal?: AbortSignal;
  readonly onProgress?: (done: number, total: number) => void;
}

const utf8 = new TextDecoder('utf-8', { fatal: true });

/**
 * The compiled contract registry, imported lazily.
 *
 * The seventeen `contracts/*.schema.json` documents are ~127 KB of raw text (~26 KB
 * gzipped). A static import would pin all of them into THIS surface's lazy chunk, where they
 * would be duplicated the moment a second consumer wanted them. A literal dynamic
 * import puts them in a shared async chunk instead, which is where a data-layer
 * artefact belongs — and this function is already async, so it costs nothing.
 *
 * The specifier is a literal, not a computed expression, so the module-graph walker
 * that enforces the register boundary can still follow it.
 */
async function defaultRegistry(): Promise<SchemaRegistry> {
  const { contractRegistry } = await import('../../data/contracts');
  return contractRegistry();
}

export async function auditBundle(options: AuditBundleOptions): Promise<BundleAudit> {
  const { source, oracle, signal, onProgress } = options;
  const registry = options.registry ?? (await defaultRegistry());
  const clock = options.clock ?? ((): string => new Date().toISOString());
  const sourceId = source.id;

  assertLive(signal);

  let manifestBytes: Uint8Array;
  try {
    manifestBytes = await source.read(MANIFEST_PATH, signal);
  } catch (error) {
    return {
      kind: 'unreadable',
      where: MANIFEST_PATH,
      sourceId,
      detail: error instanceof Error ? error.message : String(error),
    };
  }

  let manifestText: string;
  try {
    manifestText = utf8.decode(manifestBytes);
  } catch (error) {
    return {
      kind: 'malformed',
      where: MANIFEST_PATH,
      sourceId,
      detail: `manifest.json is not valid UTF-8: ${String(error)}`,
    };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(manifestText);
  } catch (error) {
    return {
      kind: 'malformed',
      where: MANIFEST_PATH,
      sourceId,
      detail: `manifest.json is not JSON: ${String(error)}`,
    };
  }

  const validation = registry.validate(BUNDLE_SCHEMA_ID, parsed);
  if (!validation.valid) {
    return {
      kind: 'malformed',
      where: MANIFEST_PATH,
      sourceId,
      detail:
        `manifest.json does not satisfy ${BUNDLE_SCHEMA_ID}. The transport would refuse this ` +
        `bundle before serving anything.\n${formatErrors(validation.errors)}`,
    };
  }
  const manifest = parsed as BundleManifest;

  let unlisted: readonly string[] | null = null;
  if (isListable(source)) {
    try {
      const present = await source.list();
      const declared = new Set(manifest.files.map((entry) => entry.path));
      unlisted = present
        .filter((path) => path !== MANIFEST_PATH && !declared.has(path))
        .sort((a, b) => a.localeCompare(b));
    } catch {
      // A listing that fails is not a bundle failure. `null` keeps the screen honest:
      // "not established" rather than "none found".
      unlisted = null;
    }
  }

  const manifestDigest = await oracle.sha256(manifestBytes);

  const audited = await auditFiles({
    manifest,
    read: (path: string) => source.read(path, signal),
    oracle,
    unlisted,
    ...(signal === undefined ? {} : { signal }),
    ...(onProgress === undefined ? {} : { onProgress }),
  });

  return {
    kind: 'audited',
    manifest,
    manifestDigest,
    at: clock(),
    oracleName: oracle.name,
    sourceId,
    rows: audited.rows,
    coverage: audited.coverage,
    findings: audited.findings,
    verdict: audited.findings.length === 0 ? 'verified' : 'failed',
  };
}

// ── The same arithmetic, as the transport's gate ───────────────────────────

/**
 * A `BundleVerifier` over `auditFiles()`, for the composition root to inject into
 * `BundleTransport`.
 *
 * Named for exactly what it checks. `BundleVerdict` has two values on purpose — the
 * transport must never be handed an ambiguous verdict to interpret optimistically — so
 * a reason this verifier could NOT check something is reported as a finding with a
 * named SKIP reason and makes the verdict `failed`, which is what `bundle.ts` asks for.
 *
 * It cannot enumerate the directory (the transport gives it `read`, not a listing), so
 * `unlisted` is `null` here and the corresponding claim is simply not made.
 */
export function manifestIntegrityVerifier(
  oracle: DigestOracle,
  name = 'evidence-view:manifest-integrity',
): BundleVerifier {
  return {
    name,
    async verify(input: BundleVerificationInput): Promise<BundleVerificationReport> {
      const result = await auditFiles({
        manifest: input.manifest,
        read: input.read,
        oracle,
        unlisted: null,
        ...(input.signal === undefined ? {} : { signal: input.signal }),
      });
      const checked = result.coverage.digestsMatched + result.coverage.digestsMismatched;
      return {
        verdict: result.findings.length === 0 ? 'verified' : 'failed',
        manifestDigest: await oracle.sha256(input.manifestBytes),
        filesChecked: checked,
        summary:
          result.findings.length === 0
            ? `${checked} file(s) hash to the digests manifest.json declares.`
            : `${result.findings.length} finding(s) against manifest.json; ${checked} file(s) hashed.`,
        findings: result.findings,
      };
    },
  };
}
