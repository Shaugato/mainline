// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The `BundleVerifier` that `BundleTransport` refuses to serve a frame without.
 *
 * `src/data/bundle.ts` states the contract precisely: the transport computes no digest and
 * verifies no signature, it has no default verifier and no skip option, and `exchange()`
 * cannot return before `verify()` has RESOLVED with `verdict: 'verified'`. This module is
 * the other half — the half that actually hashes.
 *
 * ── WHAT MAKES A BUNDLE FAIL, AND WHAT ONLY MAKES IT BOUNDED ──────────────────────
 *
 * FAIL (no frame is served, the console shows the failure and why):
 *   • a listed file whose SHA-256 does not match `manifest.files[].sha256`;
 *   • a listed file that cannot be read at all;
 *   • a checkpoint note that will not parse, or whose signed tree size / root disagrees
 *     with what `manifest.checkpoint` claims.
 *
 * SKIP, recorded as a finding, bundle still servable:
 *   • no log verification key is configured, so the checkpoint SIGNATURE was not checked;
 *   • the manifest declares no checkpoint at all.
 *
 * That split is the whole judgement in this file, and it is deliberate. A digest mismatch
 * means the bytes on the wire are not the bytes that were sealed — nothing downstream can
 * be trusted, so nothing downstream runs. An unconfigured trust anchor means WE cannot
 * check something; it is a gap in the reader's evidence, not an accusation against the
 * bundle, and refusing to render would punish the reader for our own missing configuration.
 * Both outcomes are visible: the honesty chrome shows the seal, and the custody surface
 * lists every finding verbatim.
 *
 * ── WHY IT READS THROUGH THE TRANSPORT'S CACHE ────────────────────────────────────
 *
 * `BundleVerificationInput.read` goes through `BundleTransport`'s byte cache. Using it —
 * rather than the source directly — is what makes *the bytes I checked are the bytes you
 * serve* true rather than hopeful: a second read of a hostile source cannot return
 * different content after the check has passed.
 */

import type {
  BundleFinding,
  BundleManifest,
  BundleVerificationInput,
  BundleVerificationReport,
  BundleVerifier,
} from '../data/bundle';

import { fromUtf8 } from './bytes';
import type { Verifier } from './client';
import { createVerifier } from './client';
import type { VerifierConfig } from './config';
import { NO_ANCHOR } from './config';

export const VERIFIER_NAME = 'src/verify (RFC 8785 · RFC 6962 · ECDSA P-256, in this browser)';

export interface InBrowserBundleVerifierOptions {
  /** Defaults to a worker-backed verifier. Injected in tests and by the cinema harness. */
  readonly verifier?: Verifier;
  /** Trust anchors. With none, the signature check is a SKIP finding, never a pass. */
  readonly config?: VerifierConfig;
  /**
   * Cap on how many listed files are hashed. `Infinity` by default: a verifier that checks
   * "enough" files is a verifier whose coverage an attacker chooses.
   */
  readonly maxFiles?: number;
}

export class InBrowserBundleVerifier implements BundleVerifier {
  readonly name = VERIFIER_NAME;

  private readonly verifier: Verifier;
  private readonly config: VerifierConfig;
  private readonly maxFiles: number;

  constructor(options: InBrowserBundleVerifierOptions = {}) {
    this.verifier = options.verifier ?? createVerifier();
    this.config = options.config ?? NO_ANCHOR;
    this.maxFiles = options.maxFiles ?? Number.POSITIVE_INFINITY;
  }

  async verify(input: BundleVerificationInput): Promise<BundleVerificationReport> {
    const findings: BundleFinding[] = [];
    const manifestDigest = await this.verifier.sha256(input.manifestBytes);

    let filesChecked = 0;
    let mismatches = 0;

    for (const entry of input.manifest.files) {
      if (filesChecked >= this.maxFiles) break;
      if (input.signal?.aborted === true) {
        findings.push({
          subject: entry.path,
          check: 'aborted',
          detail: 'verification was aborted before this file was read.',
        });
        break;
      }

      let bytes: Uint8Array;
      try {
        bytes = await input.read(entry.path);
      } catch (error) {
        mismatches += 1;
        findings.push({
          subject: entry.path,
          check: 'file-read',
          detail:
            'the manifest lists this file but it could not be read: ' +
            (error instanceof Error ? error.message : String(error)),
        });
        continue;
      }

      filesChecked += 1;
      const digest = await this.verifier.sha256(bytes);
      if (digest !== entry.sha256) {
        mismatches += 1;
        findings.push({
          subject: entry.path,
          check: 'file-digest',
          detail:
            `manifest declares SHA-256 ${entry.sha256}; the bytes served hash to ${digest} ` +
            `(${bytes.byteLength} bytes read). These are not the bytes that were sealed.`,
        });
      }
    }

    const checkpointOutcome = await this.checkCheckpoint(input, findings);

    const verdict = mismatches > 0 || checkpointOutcome === 'fail' ? 'failed' : 'verified';
    const skips = findings.filter((finding) => finding.check.startsWith('skip:')).length;

    const summary =
      verdict === 'failed'
        ? `${mismatches} file digest mismatch(es) and ${filesChecked} file(s) checked; this ` +
          'bundle is not the bundle that was sealed.'
        : skips > 0
          ? `${filesChecked} file digest(s) recomputed in this browser and all matched; ` +
            `${skips} check(s) were NOT RUN and are listed below.`
          : `${filesChecked} file digest(s) recomputed in this browser and all matched.`;

    return { verdict, manifestDigest, filesChecked, summary, findings };
  }

  /**
   * Verify what the manifest says about its checkpoint against the checkpoint's own bytes.
   *
   * The manifest is not itself signed. Its `checkpoint.tree_size` and `checkpoint.root_hex`
   * are therefore claims by the capture script, and the note is the signed artefact. A
   * disagreement between them is how a bundle assembled around a different checkpoint
   * presents, so it is a hard failure rather than a display preference.
   */
  private async checkCheckpoint(
    input: BundleVerificationInput,
    findings: BundleFinding[],
  ): Promise<'pass' | 'skip' | 'fail'> {
    const checkpoint: BundleManifest['checkpoint'] = input.manifest.checkpoint;
    if (checkpoint === null) {
      findings.push({
        subject: 'manifest.json',
        check: 'skip:checkpoint-absent',
        detail:
          'this manifest declares no checkpoint, so nothing in the bundle is bound to a signed ' +
          'commitment. The frames are byte-checked against the manifest and the manifest is ' +
          'checked against nothing.',
      });
      return 'skip';
    }

    let noteText: string;
    try {
      noteText = fromUtf8(await input.read(checkpoint.note_path), checkpoint.note_path);
    } catch (error) {
      findings.push({
        subject: checkpoint.note_path,
        check: 'checkpoint-note',
        detail: `the manifest names this checkpoint note but it could not be read: ${
          error instanceof Error ? error.message : String(error)
        }`,
      });
      return 'fail';
    }

    const result = await this.verifier.verifyCheckpointNote(noteText, this.config.logVkeys);

    if (result.verdict === 'malformed') {
      findings.push({
        subject: checkpoint.note_path,
        check: 'checkpoint-note',
        detail: `the checkpoint note will not parse: ${result.reason}`,
      });
      return 'fail';
    }

    const parsed = result.note;
    if (parsed !== null) {
      if (parsed.treeSize !== checkpoint.tree_size) {
        findings.push({
          subject: checkpoint.note_path,
          check: 'checkpoint-binding',
          detail:
            `the manifest claims tree_size ${checkpoint.tree_size}; the note text says ` +
            `${parsed.treeSize}. The note is the signed artefact and the manifest is not.`,
        });
        return 'fail';
      }
      if (parsed.rootHex !== checkpoint.root_hex) {
        findings.push({
          subject: checkpoint.note_path,
          check: 'checkpoint-binding',
          detail:
            `the manifest claims root ${checkpoint.root_hex}; the note text says ${parsed.rootHex}.`,
        });
        return 'fail';
      }
    }

    if (result.verdict === 'failed') {
      findings.push({
        subject: checkpoint.note_path,
        check: 'checkpoint-signature',
        detail: result.reason,
      });
      return 'fail';
    }

    if (result.verdict === 'skipped') {
      findings.push({
        subject: checkpoint.note_path,
        check: 'skip:checkpoint-signature',
        detail: `${result.reason}\n\n${this.config.sourceNote}`,
      });
      return 'skip';
    }

    findings.push({
      subject: checkpoint.note_path,
      check: 'checkpoint-signature',
      detail:
        `the checkpoint note verifies under ECDSA P-256 / SHA-256 against ` +
        `${result.verifiedBy.join(', ')}. ${this.config.sourceNote}`,
    });
    return 'pass';
  }
}

/** Convenience for the composition root: the verifier the console ships with. */
export function inBrowserVerifier(config?: VerifierConfig): BundleVerifier {
  return new InBrowserBundleVerifier(config === undefined ? {} : { config });
}
