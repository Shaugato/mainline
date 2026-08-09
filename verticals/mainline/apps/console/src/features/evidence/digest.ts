// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The one arithmetic primitive this surface needs: SHA-256 over bytes.
 *
 * `docs/leads/ui.md` D6 says the console re-derives, in the browser, every claim it
 * displays. On this surface the claim is narrow and completely checkable — *are these
 * the bytes that were sealed?* — and the arithmetic behind it is one call to WebCrypto.
 *
 * Three properties are deliberate.
 *
 * **It is a PORT, not a hard dependency.** `DigestOracle` is an interface with one
 * method, so the audit can be driven by the platform's WebCrypto, by the offline
 * verifier once `src/verify/` lands, or by a test double that is deliberately wrong.
 * A surface whose only hash function is spelled inline cannot be shown to be checking
 * anything.
 *
 * **Absence is a first-class outcome, not an exception.** `crypto.subtle` is undefined
 * on an insecure origin, so a console served over plain `http://` genuinely cannot hash
 * anything. That must render as "not checked, and here is why" — never as a failure
 * (which would accuse the bundle) and never as a pass (which would be a lie). Hence
 * `resolveDigestOracle()` returns a discriminated union rather than throwing or
 * returning `null`: the REASON travels with the absence, all the way to the screen.
 *
 * **The bytes are copied into a fresh `ArrayBuffer` before hashing.** A `Uint8Array`
 * may be a view with a non-zero `byteOffset` over a larger (or shared) buffer; copying
 * makes "the digest is over exactly these bytes" true by construction instead of true
 * by careful reading.
 */

/** One method. Anything that can hash bytes can drive the audit. */
export interface DigestOracle {
  /** Named on screen beside the seal, so the reader knows what did the arithmetic. */
  readonly name: string;
  /** Lowercase hex, 64 characters. */
  sha256(bytes: Uint8Array): Promise<string>;
}

export type DigestOracleResolution =
  | { readonly ok: true; readonly oracle: DigestOracle }
  | { readonly ok: false; readonly reason: string };

/** Bytes → lowercase hex. Exported because the tests compare hex, not buffers. */
export function toHex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

/**
 * A digest oracle over a `SubtleCrypto`.
 *
 * The subtle interface is taken as a parameter rather than read from the global inside
 * the method: a test that wants a deliberately-wrong oracle supplies one, and there is
 * no code path in which this function silently falls back to something else.
 */
export function webCryptoDigestOracle(subtle: SubtleCrypto, name = 'WebCrypto SHA-256'): DigestOracle {
  return {
    name,
    async sha256(bytes: Uint8Array): Promise<string> {
      const buffer = new ArrayBuffer(bytes.byteLength);
      new Uint8Array(buffer).set(bytes);
      return toHex(await subtle.digest('SHA-256', buffer));
    },
  };
}

/**
 * The platform's oracle, or the reason there is not one.
 *
 * `crypto.subtle` is exposed only in a secure context (HTTPS, `localhost`, or
 * `file://` in some engines). That is not an edge case for this product: the free demo
 * URL (G6) is exactly the kind of host that can end up on plain HTTP, and the console
 * must then say "nothing on this page has been checked, because this origin is not
 * secure" rather than quietly showing an unverified inventory that looks verified.
 */
export function resolveDigestOracle(host: { readonly crypto?: Crypto } = globalThis): DigestOracleResolution {
  const platform = host.crypto;
  if (platform === undefined) {
    return {
      ok: false,
      reason:
        'this environment exposes no `crypto` object, so no digest can be recomputed here. ' +
        'Nothing below has been checked.',
    };
  }
  // `subtle` is typed as always-present but is genuinely absent on insecure origins;
  // the check is a runtime fact the type system does not model.
  const subtle: SubtleCrypto | undefined = platform.subtle;
  if (subtle === undefined) {
    return {
      ok: false,
      reason:
        '`crypto.subtle` is unavailable, which means this page is not running in a secure ' +
        'context (WebCrypto is exposed only over HTTPS, on localhost, or from a local file). ' +
        'No digest can be recomputed here, so nothing below has been checked. Serve the ' +
        'console over HTTPS and reload.',
    };
  }
  return { ok: true, oracle: webCryptoDigestOracle(subtle) };
}
