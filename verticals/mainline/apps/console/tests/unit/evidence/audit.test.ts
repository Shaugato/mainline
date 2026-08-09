// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE AUDIT — PL-2 in its literal form.
 *
 * The product of this surface is a REFUSAL: a bundle whose bytes are not the bytes that
 * were sealed must not render as evidence. A suite that only ever sees an intact fixture
 * asserts nothing at all, so every negative case here is a REAL mutation of the sealed
 * bytes — a flipped hex digit, a truncated file, a deleted file, a smuggled file, a
 * renamed frame — hashed with real WebCrypto.
 *
 * The intact case is asserted in the same file, and that pairing is the point: a
 * verifier that refuses everything is exactly as useless as one that refuses nothing.
 *
 * The last block is the one that makes the claim in `audit.ts` true rather than
 * aspirational: the SAME function, injected into `BundleTransport` as its verifier,
 * makes the transport refuse to serve a single frame from the tampered bundle — so what
 * this screen shows and what the rest of the console is allowed to render are one
 * decision, not two that might drift.
 */

import { describe, expect, it } from 'vitest';

import {
  BundleTransport,
  MemoryBundleSource,
  type BundleManifest,
} from '../../../src/data/bundle';
import { contractRegistry } from '../../../src/data/contracts';
import { TransportError } from '../../../src/data/transport';
import {
  AuditAborted,
  auditBundle,
  manifestIntegrityVerifier,
  type AuditedBundle,
  type BundleAudit,
} from '../../../src/features/evidence/audit';
import { resolveDigestOracle, type DigestOracle } from '../../../src/features/evidence/digest';

import {
  FIXTURE_MANIFEST_SHA256,
  FIXTURE_PERMIT_ID,
  ListableMemorySource,
  OpaqueMemorySource,
  bundleFiles,
  deleteFile,
  editManifest,
  flipDeclaredDigest,
  renameFrame,
  smuggleFile,
  truncateFile,
} from './_fixture';

const ORACLE: DigestOracle = (() => {
  const resolved = resolveDigestOracle();
  if (!resolved.ok) {
    // Not a skip. A test environment with no WebCrypto would make every assertion below
    // pass by never hashing anything, which is the exact failure PL-2 exists to prevent.
    throw new Error(`this test environment has no digest oracle: ${resolved.reason}`);
  }
  return resolved.oracle;
})();

const CLOCK = (): string => '2026-08-04T00:00:00.000Z';

function audited(result: BundleAudit): AuditedBundle {
  if (result.kind !== 'audited') {
    throw new Error(`expected an audited bundle, got ${result.kind}: ${result.detail}`);
  }
  return result;
}

async function auditOpaque(files: Map<string, Uint8Array>): Promise<BundleAudit> {
  return auditBundle({
    source: new OpaqueMemorySource('test:opaque', files),
    oracle: ORACLE,
    registry: contractRegistry(),
    clock: CLOCK,
  });
}

const PERMIT_FRAME = `frames/GET~20~2Fv1~2Fpermits~2F${FIXTURE_PERMIT_ID}.json`;

describe('the committed bundle, intact', () => {
  it('verifies, with every listed file hashed and no finding', async () => {
    const result = audited(await auditOpaque(bundleFiles()));

    expect(result.verdict).toBe('verified');
    expect(result.findings).toEqual([]);
    expect(result.coverage.filesDeclared).toBe(21);
    expect(result.coverage.digestsMatched).toBe(21);
    expect(result.coverage.digestsMismatched).toBe(0);
    expect(result.coverage.filesUnreadable).toBe(0);
    expect(result.coverage.filesUnchecked).toBe(0);
    expect(result.coverage.conserved).toBe(true);
    expect(result.coverage.bytesRead).toBe(result.coverage.bytesDeclared);
    expect(result.at).toBe('2026-08-04T00:00:00.000Z');
    expect(result.oracleName).toBe('WebCrypto SHA-256');
  });

  it('recomputes the manifest digest that `sha256sum` reports for the committed file', async () => {
    // A constant taken from an INDEPENDENT tool. If this ever disagrees, either the
    // fixture moved or our hashing is wrong, and both are things a reader must be told.
    const result = audited(await auditOpaque(bundleFiles()));
    expect(result.manifestDigest).toBe(FIXTURE_MANIFEST_SHA256);
  });

  it('reports `unlisted` as null for a source that cannot enumerate itself', async () => {
    const result = audited(await auditOpaque(bundleFiles()));
    expect(result.coverage.unlisted).toBeNull();
  });

  it('reports an empty `unlisted` for a source that can, and finds nothing', async () => {
    const result = audited(
      await auditBundle({
        source: new ListableMemorySource('test:listable', bundleFiles()),
        oracle: ORACLE,
        registry: contractRegistry(),
        clock: CLOCK,
      }),
    );
    expect(result.coverage.unlisted).toEqual([]);
    expect(result.verdict).toBe('verified');
  });
});

describe('one flipped hex digit', () => {
  it('fails the audit, names the file, and leaves every other row matching', async () => {
    const result = audited(await auditOpaque(flipDeclaredDigest(bundleFiles(), PERMIT_FRAME)));

    expect(result.verdict).toBe('failed');
    expect(result.findings).toHaveLength(1);
    expect(result.findings[0]?.check).toBe('manifest-digest');
    expect(result.findings[0]?.subject).toBe(PERMIT_FRAME);
    expect(result.findings[0]?.detail).toContain('manifest declares sha256');

    // Targeted, not blanket. A verifier that condemns the whole bundle on one mismatch
    // tells a reader nothing about WHICH byte moved.
    expect(result.coverage.digestsMismatched).toBe(1);
    expect(result.coverage.digestsMatched).toBe(20);
    expect(result.rows.find((row) => row.path === PERMIT_FRAME)?.state).toBe('mismatch');
    expect(result.rows.filter((row) => row.state === 'match')).toHaveLength(20);
  });

  it('carries BOTH digests into the row detail, so the reader can compare them', async () => {
    const result = audited(await auditOpaque(flipDeclaredDigest(bundleFiles(), PERMIT_FRAME)));
    const row = result.rows.find((candidate) => candidate.path === PERMIT_FRAME);
    expect(row?.actualDigest).toMatch(/^[0-9a-f]{64}$/);
    expect(row?.detail).toContain(row?.actualDigest ?? 'MISSING');
    expect(row?.detail).toContain(row?.declaredDigest ?? 'MISSING');
  });
});

describe('bytes that do not arrive as declared', () => {
  it('reports a truncated file with the byte counts, not only a digest mismatch', async () => {
    const result = audited(await auditOpaque(truncateFile(bundleFiles(), PERMIT_FRAME, 128)));
    const finding = result.findings.find((candidate) => candidate.subject === PERMIT_FRAME);
    expect(finding?.check).toBe('manifest-digest');
    expect(finding?.detail).toContain('128 bytes arrived');
    expect(result.rows.find((row) => row.path === PERMIT_FRAME)?.actualBytes).toBe(128);
  });

  it('reports a file the manifest lists and the source does not have', async () => {
    const result = audited(await auditOpaque(deleteFile(bundleFiles(), PERMIT_FRAME)));
    expect(result.verdict).toBe('failed');
    expect(result.coverage.filesUnreadable).toBe(1);
    expect(result.coverage.digestsMatched).toBe(20);
    expect(result.coverage.conserved).toBe(true);
    const finding = result.findings.find((candidate) => candidate.subject === PERMIT_FRAME);
    expect(finding?.check).toBe('file-present');
    expect(finding?.detail).toContain('no such file in bundle');
  });
});

describe('files and names the producer would never have written', () => {
  it('reports a file present in the directory but absent from the manifest', async () => {
    const files = smuggleFile(bundleFiles(), 'frames/not-listed.json', '{"hello":"world"}\n');
    const result = audited(
      await auditBundle({
        source: new ListableMemorySource('test:listable', files),
        oracle: ORACLE,
        registry: contractRegistry(),
        clock: CLOCK,
      }),
    );
    expect(result.coverage.unlisted).toEqual(['frames/not-listed.json']);
    const finding = result.findings.find((candidate) => candidate.check === 'unlisted-file');
    expect(finding?.subject).toBe('frames/not-listed.json');
    expect(result.verdict).toBe('failed');
  });

  it('does NOT report a smuggled file when the source cannot enumerate itself', async () => {
    // The honest limit, asserted. A static host cannot list, so the console must not be
    // able to claim there is nothing extra — and must not falsely claim there is.
    const files = smuggleFile(bundleFiles(), 'frames/not-listed.json', '{"hello":"world"}\n');
    const result = audited(await auditOpaque(files));
    expect(result.coverage.unlisted).toBeNull();
    expect(result.findings).toEqual([]);
    expect(result.verdict).toBe('verified');
  });

  it('reports a frame filed under a non-canonical name', async () => {
    // `~47` decodes to `G`, so this name decodes to a perfectly good request key — but
    // the encoder never escapes an unreserved character, so it is not a name the
    // producer could have written. That is the whole reason the round trip is checked
    // rather than the decode alone: a decoder that "works" accepts many spellings.
    const files = renameFrame(bundleFiles(), PERMIT_FRAME, 'frames/~47ET~20~2Fv1~2Fpermits.json');
    const result = audited(await auditOpaque(files));
    const finding = result.findings.find(
      (candidate) => candidate.check === 'frame-name-non-canonical',
    );
    expect(
      finding,
      'a frame whose name is not the canonical encoding of the key it decodes to went unreported',
    ).toBeDefined();
    expect(finding?.detail).toContain('GET /v1/permits');
  });

  it('reports a frame whose name decodes to nothing at all', async () => {
    const files = renameFrame(bundleFiles(), PERMIT_FRAME, 'frames/~zz.json');
    const result = audited(await auditOpaque(files));
    expect(
      result.findings.map((finding) => finding.check),
    ).toContain('frame-name-undecodable');
  });
});

describe('a manifest that contradicts itself', () => {
  it('reports a manifest that lists itself', async () => {
    const files = editManifest(bundleFiles(), (manifest) => {
      const entries = manifest.files as { path: string; sha256: string; bytes: number }[];
      entries.push({ path: 'manifest.json', sha256: '0'.repeat(64), bytes: 1 });
    });
    const result = audited(await auditOpaque(files));
    expect(result.findings.map((finding) => finding.check)).toContain('manifest-lists-itself');
    expect(result.verdict).toBe('failed');
  });

  it('reports a path listed twice', async () => {
    const files = editManifest(bundleFiles(), (manifest) => {
      const entries = manifest.files as { path: string; sha256: string; bytes: number }[];
      const first = entries[0];
      if (first === undefined) throw new Error('the fixture manifest lists nothing');
      entries.push({ ...first });
    });
    const result = audited(await auditOpaque(files));
    expect(result.findings.map((finding) => finding.check)).toContain('manifest-duplicate-path');
  });
});

describe('a manifest that is not a manifest', () => {
  it('is `unreadable` when there is no manifest at all', async () => {
    const result = await auditOpaque(deleteFile(bundleFiles(), 'manifest.json'));
    expect(result.kind).toBe('unreadable');
    expect(result.kind === 'unreadable' ? result.detail : '').toContain('manifest.json');
  });

  it('is `malformed` when the manifest is not JSON', async () => {
    const files = bundleFiles();
    files.set('manifest.json', new TextEncoder().encode('{ not json'));
    const result = await auditOpaque(files);
    expect(result.kind).toBe('malformed');
    expect(result.kind === 'malformed' ? result.detail : '').toContain('not JSON');
  });

  it('is `malformed` when the manifest does not satisfy its contract', async () => {
    const files = editManifest(bundleFiles(), (manifest) => {
      delete manifest.bundle_id;
    });
    const result = await auditOpaque(files);
    expect(result.kind).toBe('malformed');
    const detail = result.kind === 'malformed' ? result.detail : '';
    expect(detail).toContain('bundle.schema.json');
    // The transport refuses the same manifest; saying so is what makes this screen the
    // place a reader goes to find out WHY nothing else in the console will render.
    expect(detail).toContain('transport would refuse');
  });
});

describe('cancellation', () => {
  it('throws AuditAborted rather than reporting a failed bundle', async () => {
    const controller = new AbortController();
    controller.abort(new Error('the reader navigated away'));
    await expect(
      auditBundle({
        source: new OpaqueMemorySource('test:opaque', bundleFiles()),
        oracle: ORACLE,
        registry: contractRegistry(),
        clock: CLOCK,
        signal: controller.signal,
      }),
    ).rejects.toBeInstanceOf(AuditAborted);
  });
});

describe('progress', () => {
  it('reports one step per listed file, ending at the declared total', async () => {
    const steps: [number, number][] = [];
    await auditBundle({
      source: new OpaqueMemorySource('test:opaque', bundleFiles()),
      oracle: ORACLE,
      registry: contractRegistry(),
      clock: CLOCK,
      onProgress: (done, total) => steps.push([done, total]),
    });
    expect(steps).toHaveLength(21);
    expect(steps.at(-1)).toEqual([21, 21]);
  });
});

describe('the same arithmetic, as the transport’s gate', () => {
  const registry = contractRegistry();
  const verifier = manifestIntegrityVerifier(ORACLE);

  it('lets the transport serve a frame from the intact bundle', async () => {
    const transport = new BundleTransport({
      source: new MemoryBundleSource('test:intact', bundleFiles()),
      registry,
      verifier,
    });
    const exchange = await transport.exchange({
      resource: 'permit',
      path: { permit_id: FIXTURE_PERMIT_ID },
    });
    expect(exchange.mode).toBe('replay');
    expect(exchange.envelope.resource).toBe('permit');
    expect(transport.report()?.verdict).toBe('verified');
    expect(transport.report()?.filesChecked).toBe(21);
  });

  it('makes the transport refuse EVERY frame from the tampered bundle', async () => {
    const transport = new BundleTransport({
      source: new MemoryBundleSource('test:tampered', flipDeclaredDigest(bundleFiles(), PERMIT_FRAME)),
      registry,
      verifier,
    });
    // Not "the tampered frame is refused" — NOTHING is servable, including files whose
    // own digests were untouched. That is what "verification is a precondition" means.
    const untouched = transport.exchange({ resource: 'audit' });
    await expect(untouched).rejects.toBeInstanceOf(TransportError);
    await expect(untouched).rejects.toThrow(/evidence-view:manifest-integrity refused/);
  });

  it('names the manifest digest it computed, so the chrome can show a real prefix', async () => {
    const files = bundleFiles();
    const manifestBytes = files.get('manifest.json');
    if (manifestBytes === undefined) throw new Error('the fixture has no manifest.json');
    const manifest = JSON.parse(new TextDecoder().decode(manifestBytes)) as BundleManifest;

    const report = await verifier.verify({
      manifestBytes,
      manifest,
      read: (path: string) => {
        const bytes = files.get(path);
        return bytes === undefined
          ? Promise.reject(new Error(`no such file: ${path}`))
          : Promise.resolve(bytes);
      },
    });
    expect(report.manifestDigest).toBe(FIXTURE_MANIFEST_SHA256);
    expect(report.verdict).toBe('verified');
    expect(report.summary).toContain('21 file(s)');
  });
});
