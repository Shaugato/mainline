// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Where the verifier's trust anchors come from — and where they must never come from.
 *
 * A public key is not a secret, so nothing here is confidential. The rule that matters is
 * different and is stated in `contracts/ledger.schema.json`:
 *
 *   > A bundle that carries its own trust anchor proves nothing, so a checkpoint verified
 *   > against a key from this field alone is reported as PASS(self-asserted-key) — a
 *   > distinct verdict.
 *
 * So the anchor arrives out of band, and WHERE it arrived from is carried all the way to
 * the screen. A key baked into the build, a key pasted into the URL by whoever sent you
 * the link, and a key typed in by an operator are three different epistemic situations,
 * and a console that rendered the same green tick for all three would be flattening the
 * only distinction that matters.
 *
 * `source: 'none'` is a first-class outcome. With no anchor the signature check reports
 * SKIP with a named reason and the seal is amber — never green, and never red, because a
 * checkpoint nobody could check has not been accused of anything.
 */

declare global {
  // Declaration merging onto the interface `src/env.d.ts` owns. Adding the member there
  // would mean editing another worker's file; merging is the same result with no collision.
  interface ImportMetaEnv {
    /** C2SP vkey for the log signing key: `<origin>+<8 hex id>+<base64(0x02 ‖ DER SPKI)>`. */
    readonly VITE_MAINLINE_LOG_VKEY?: string;
    /** SHA-256 of the canonicaliser source, pinned in spec/custody/canon-registry.yaml. */
    readonly VITE_MAINLINE_CANON_SHA256?: string;
  }
}

export type AnchorSource = 'build' | 'url' | 'operator' | 'none';

export interface VerifierConfig {
  /** C2SP vkeys the verifier will trust. Empty means the signature check is SKIPPED. */
  readonly logVkeys: readonly string[];
  /** Where those keys came from. Rendered verbatim beside every checkpoint seal. */
  readonly source: AnchorSource;
  /** One sentence, verbatim, describing the provenance of the anchor. */
  readonly sourceNote: string;
  /** `canon_src_sha256` this reader pins, or null when they pin nothing (check 10 SKIPs). */
  readonly canonSrcSha256: string | null;
}

export const NO_ANCHOR: VerifierConfig = Object.freeze({
  logVkeys: Object.freeze([]),
  source: 'none' as const,
  sourceNote:
    'No log verification key is configured, so no checkpoint signature on this screen has ' +
    'been checked. That is a gap in what you are being shown, not a finding against the ' +
    'ledger. Supply a key with VITE_MAINLINE_LOG_VKEY at build time, or ?log_vkey= in this ' +
    'page\'s query string, and reload.',
  canonSrcSha256: null,
});

const VKEY_SHAPE = /^[^\s+]+\+[0-9a-f]{8}\+[A-Za-z0-9+/]+={0,2}$/;

/**
 * Resolve the anchor from the build and the URL, in that order of precedence.
 *
 * Build wins over URL deliberately. A deployment that pinned a key at build time has made
 * a decision about what it trusts, and a link someone sends you must not be able to
 * override it — that would make the green seal a function of the URL.
 */
export function resolveVerifierConfig(
  options: {
    readonly env?: { readonly VITE_MAINLINE_LOG_VKEY?: string; readonly VITE_MAINLINE_CANON_SHA256?: string };
    readonly search?: string;
  } = {},
): VerifierConfig {
  const env = options.env ?? import.meta.env;
  const search = options.search ?? (typeof location === 'undefined' ? '' : location.search);

  const buildKey = env.VITE_MAINLINE_LOG_VKEY?.trim() ?? '';
  const canonPin = env.VITE_MAINLINE_CANON_SHA256?.trim() ?? '';
  const canonSrcSha256 = /^[0-9a-f]{64}$/.test(canonPin) ? canonPin : null;

  if (buildKey !== '') {
    if (!VKEY_SHAPE.test(buildKey)) {
      return {
        ...NO_ANCHOR,
        canonSrcSha256,
        sourceNote:
          'VITE_MAINLINE_LOG_VKEY was set at build time but is not a C2SP vkey ' +
          '(<name>+<8 hex key id>+<base64 key material>). It has been discarded rather than ' +
          'used, because a malformed anchor that half-works is worse than none.',
      };
    }
    return {
      logVkeys: Object.freeze([buildKey]),
      source: 'build',
      sourceNote:
        'The log verification key was compiled into this build (VITE_MAINLINE_LOG_VKEY). It ' +
        'did not arrive with the bundle, and a link cannot override it.',
      canonSrcSha256,
    };
  }

  const urlKey = new URLSearchParams(search).get('log_vkey')?.trim() ?? '';
  if (urlKey !== '') {
    if (!VKEY_SHAPE.test(urlKey)) {
      return {
        ...NO_ANCHOR,
        canonSrcSha256,
        sourceNote:
          'A ?log_vkey= parameter was present in this page\'s URL but is not a C2SP vkey. It ' +
          'has been discarded rather than used.',
      };
    }
    return {
      logVkeys: Object.freeze([urlKey]),
      source: 'url',
      sourceNote:
        'The log verification key came from this page\'s query string, which means it was ' +
        'chosen by whoever sent you this link. It is out of band with respect to the BUNDLE — ' +
        'which is what the check needs — but it is not out of band with respect to the LINK. ' +
        'Compare it against a key you obtained independently before reading the seal below as ' +
        'evidence.',
      canonSrcSha256,
    };
  }

  return { ...NO_ANCHOR, canonSrcSha256 };
}

/** An anchor an operator pasted in. Kept separate so the note can say so. */
export function operatorConfig(vkey: string, canonSrcSha256: string | null = null): VerifierConfig {
  const trimmed = vkey.trim();
  if (!VKEY_SHAPE.test(trimmed)) {
    return {
      ...NO_ANCHOR,
      canonSrcSha256,
      sourceNote:
        'The key that was entered is not a C2SP vkey (<name>+<8 hex key id>+<base64 key ' +
        'material>). Nothing has been verified against it.',
    };
  }
  return {
    logVkeys: Object.freeze([trimmed]),
    source: 'operator',
    sourceNote:
      'The log verification key was entered on this page by its reader. Its provenance is ' +
      'whatever the reader knows it to be, and this console makes no claim about it.',
    canonSrcSha256,
  };
}
