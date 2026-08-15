// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * WHERE THE OPERATOR SURFACE IS, AND WHO ANSWERED IT.
 *
 * Every request the operator screens make is built here, as
 * `new URL(path, location.origin)`, and nowhere else. There is no compiled-in hostname,
 * no API base read from a build-time variable, no environment read at all, and no way for a screen to address a
 * different host — `resolveApiUrl` refuses a path that resolves off-origin.
 *
 * THE MEASUREMENT THAT SETTLES THIS (operator-systems-plan M1 / R3):
 * `infra/modules/demo-api/main.tf:434-447` records that the Function URL deliberately
 * carries **no `cors` block**. A page served from any other origin therefore cannot read
 * these answers at all — not the body and, decisively, not the response headers. Serving
 * the page FROM the origin is not a convenience; it is the only shape in which
 * `X-Mainline-Emulator` and `Date` are readable, which is the only reason the screens can
 * tell a rehearsal from the deployment.
 *
 * THE TWO HEADERS, AND WHY THEY ARE CAPTURED HERE RATHER THAN GUESSED AT:
 * `scripts/deploy/local_furl.py:30-42` stamps `X-Mainline-Emulator: local_furl` and
 * `X-Mainline-Not-The-Demo-Url: <path to that file>` on **every** response it produces,
 * and states that these two headers are the only divergence from what the handler
 * returned. A capture taken against the local rehearsal can therefore never be passed off
 * as one taken against the deployment — provided something reads them. This module is
 * that something. `client.ts` calls {@link noteResponse} once per exchange; W1's origin
 * strip reads {@link originFacts}.
 *
 * Nothing in this file invents a value. When a header is absent the answer is `null`,
 * which the strip renders as an absence and never as "deployed".
 */

/**
 * The API prefix, as `mainline_demo_api.static_site.is_api_path` defines it: everything
 * under `/v1` is the JSON API and everything else is the bundled site. A path outside it
 * would be answered with HTML, so this client refuses to build one.
 */
const API_PREFIX = '/v1/';

/**
 * The DOM event the operator shell listens for, spelled here rather than imported.
 *
 * `src/operator/chrome/OriginStrip.ts` offers two ways for the header to reach it and says
 * of this one: *"no import at all"*. That is the point — the shell must not import the
 * kernel and the kernel must not import the shell, so the name is duplicated on purpose and
 * `OriginStrip.EXCHANGE_EVENT` is its authority. The detail carries `{ emulator }` and
 * nothing else, because the strip ignores a detail with no `emulator` key rather than
 * treating it as null: "the event did not mention the header" and "the response did not
 * carry the header" are different statements.
 */
const EXCHANGE_EVENT = 'mainline-operator:exchange';

/** What a response told us about who answered it. Set by `client.ts`, read by W1's strip. */
interface ResponseWitness {
  /** `X-Mainline-Emulator`, verbatim, or null when the responder stamped none. */
  readonly emulator: string | null;
  /** `X-Mainline-Not-The-Demo-Url`, verbatim, or null. */
  readonly notTheDemoUrl: string | null;
  /** The `Date` response header, verbatim. Readable only because the page is same-origin. */
  readonly serverDate: string | null;
  /** The origin of the URL that was actually fetched. */
  readonly requestOrigin: string;
}

/**
 * What the operator chrome may state about where it is running.
 *
 * Every member is either read from `location` or observed on a real response. There is no
 * "deployed" flag: a page cannot know it is the deployment, it can only know that nothing
 * has claimed to be an emulator. That distinction is the whole point of the two headers.
 */
export interface OriginFacts {
  /** `location.origin`, verbatim. `'null'` when the document came from `file://`. */
  readonly origin: string;
  /** `location.href` with the hash removed — the page a judge could type in. */
  readonly href: string;
  /** `location.protocol`, verbatim (`'https:'`, `'http:'`, `'file:'`). */
  readonly protocol: string;
  /**
   * True when `origin` is an http(s) origin an API request can be built against. False
   * from `file://`, where `location.origin` is the string `'null'` and no same-origin
   * request exists to make.
   */
  readonly originUsable: boolean;
  /**
   * True when every request this client has resolved so far landed on `origin`. It starts
   * true and can only be falsified — a claim that is checked rather than asserted.
   */
  readonly sameOrigin: boolean;
  /** How many exchanges have been observed. Zero means nothing has been checked yet. */
  readonly responsesObserved: number;
  /** The most recent `X-Mainline-Emulator`, verbatim, or null when none has been seen. */
  readonly emulator: string | null;
  /** ISO instant, from this browser's clock, at which `emulator` was last observed. */
  readonly emulatorObservedAt: string | null;
  /** The most recent `X-Mainline-Not-The-Demo-Url`, verbatim, or null. */
  readonly notTheDemoUrl: string | null;
  /** The most recent `Date` response header, verbatim, or null. */
  readonly serverDate: string | null;
}

let sameOrigin = true;
let responsesObserved = 0;
let emulator: string | null = null;
let emulatorObservedAt: string | null = null;
let notTheDemoUrl: string | null = null;
let serverDate: string | null = null;

const listeners = new Set<() => void>();

/** `location.origin`. Exposed as a function so a test can relocate the document. */
export function pageOrigin(): string {
  return location.origin;
}

/**
 * Build the URL for one API path against the document's own origin.
 *
 * Throws {@link TypeError} — never returns a fallback — when the path is not an absolute
 * `/v1/…` path or when it resolves off-origin. `client.ts` catches this and reports it as
 * a named failure, so no caller has to write a try/catch and no screen can silently
 * address a host nobody chose.
 */
export function resolveApiUrl(path: string): URL {
  if (!path.startsWith(API_PREFIX)) {
    throw new TypeError(
      `operator kernel: "${path}" is not an API path. Every request is same-origin and ` +
        `every API path begins with "${API_PREFIX}" (static_site.is_api_path). A path ` +
        `outside it is answered with HTML, and an absolute URL cannot be read at all — ` +
        `the Function URL carries no CORS block (infra/modules/demo-api/main.tf:434-447).`,
    );
  }
  const url = new URL(path, pageOrigin());
  if (url.origin !== pageOrigin()) {
    throw new TypeError(
      `operator kernel: "${path}" resolved to ${url.origin}, which is not this page's ` +
        `origin ${pageOrigin()}. The operator surface is only ever a client of the origin ` +
        `that served it.`,
    );
  }
  return url;
}

/** True when `url` is on the document's own origin. */
export function isSameOrigin(url: URL): boolean {
  return url.origin === pageOrigin();
}

/**
 * Record what one real response disclosed. Called by `client.ts` after every exchange,
 * including a failed one (where every header is null and the witness still counts).
 */
export function noteResponse(witness: ResponseWitness): void {
  responsesObserved += 1;
  if (witness.requestOrigin !== pageOrigin()) {
    sameOrigin = false;
  }
  if (witness.emulator !== null) {
    emulator = witness.emulator;
    emulatorObservedAt = new Date().toISOString();
  }
  if (witness.notTheDemoUrl !== null) {
    notTheDemoUrl = witness.notTheDemoUrl;
  }
  if (witness.serverDate !== null) {
    serverDate = witness.serverDate;
  }
  // The import-free bridge to the origin strip. Dispatched for EVERY response, including
  // one that carried no emulator header — `emulator: null` is the finding "nothing on the
  // wire declared itself an emulator", and withholding it would leave the strip saying
  // "no response observed yet" after a response had been observed.
  if (typeof document !== 'undefined') {
    document.dispatchEvent(
      new CustomEvent(EXCHANGE_EVENT, { detail: { emulator: witness.emulator } }),
    );
  }
  for (const listener of listeners) {
    listener();
  }
}

/** A snapshot of everything the chrome may state about where this page is running. */
export function originFacts(): OriginFacts {
  const origin = pageOrigin();
  return {
    origin,
    href: `${location.origin}${location.pathname}${location.search}`,
    protocol: location.protocol,
    originUsable: origin.startsWith('http:') || origin.startsWith('https:'),
    sameOrigin,
    responsesObserved,
    emulator,
    emulatorObservedAt,
    notTheDemoUrl,
    serverDate,
  };
}

/** Subscribe to origin-fact changes. Returns the unsubscribe. */
export function onOriginChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/**
 * Forget every observation. **Test-only.** No operator module calls it: a page that could
 * clear the record of having been answered by an emulator is a page that could hide it.
 */
export function resetOrigin(): void {
  sameOrigin = true;
  responsesObserved = 0;
  emulator = null;
  emulatorObservedAt = null;
  notTheDemoUrl = null;
  serverDate = null;
  listeners.clear();
}
