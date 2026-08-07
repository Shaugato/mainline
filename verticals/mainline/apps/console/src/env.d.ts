// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/// <reference types="vite/client" />

/**
 * Build-time constants, substituted by `define` in vite.config.ts.
 *
 * They are constants rather than runtime lookups on purpose: D17 makes the
 * signature-capture path a RENDER-TIME SWITCH decided by the GT-15 attestation, so the
 * shipped bundle contains exactly one capture path and cannot be talked into the other
 * one at runtime. An unverified capability must not reach a rendered artefact.
 */
declare const __MAINLINE_BUILD_ID__: string;
declare const __MAINLINE_SIGNATURE_PATH__: 'webauthn' | 'oidc_envelope' | 'unknown';
/** `'g1-attestation.json'` when one was read at build time, `'absent'` when none was. */
declare const __MAINLINE_ATTESTATION_SOURCE__: string;

/**
 * `navigator.deviceMemory` and `navigator.connection` are not in the DOM lib because
 * they are not on the standards track everywhere. The capability probe reads them
 * structurally and treats absence as `null` — see src/app/capability.ts.
 */
interface NavigatorDeviceMemory {
  readonly deviceMemory?: number;
}

interface NavigatorConnection {
  readonly connection?: { readonly saveData?: boolean };
}

interface ImportMetaEnv {
  /**
   * Optional transport hint for local development. The honesty chrome NEVER reads this
   * — the transport declares itself at runtime, because a build-time claim about
   * whether the bytes are live is exactly the kind of claim this console refuses.
   */
  readonly VITE_MAINLINE_BUNDLE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
