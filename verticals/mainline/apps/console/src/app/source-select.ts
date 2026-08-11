// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * WHICH TRANSPORT THE COMPOSITION ROOT BUILDS — decided by a pure function of the
 * BUILD, and of nothing else.
 *
 * D7 makes `LIVE` and `REPLAY` one line of composition and one badge, never a code path.
 * That property survives only if the choice is made in exactly one place, from inputs a
 * reader can enumerate, and this module is that place. It builds nothing, imports no
 * transport and knows no verifier: it answers one question — *what sources did this
 * artefact ship with?* — and `composition.tsx` acts on the answer.
 *
 * ── THE THREE RULES ──────────────────────────────────────────────────────────────
 *
 *   both set → LIVE, with a control that can switch to REPLAY;
 *   one set  → that one, with no control, because a control that offers a source the
 *              build does not carry is a control that produces an error state on click;
 *   neither  → nothing is built, and every surface keeps its own NO SOURCE panel —
 *              unchanged, because that panel is already the honest rendering and
 *              replacing it with a shell-level banner would say the same thing twice.
 *
 * ── WHY BUILD-TIME ONLY ──────────────────────────────────────────────────────────
 *
 * `src/features/evidence/source.ts` establishes the precedent this module follows and
 * states the reason: **the build-time default may be absolute, because whoever set it is
 * the operator who built the artefact; a URL parameter is something a stranger can
 * send.** A console that fetched and rendered an API a query string chose would be a
 * machine for producing authentic-looking screenshots of somebody else's bytes under our
 * chrome. So `VITE_MAINLINE_API_BASE` and `VITE_MAINLINE_BUNDLE_URL` are the only
 * origins this module will ever name.
 *
 * `?source=` is admitted, and is NOT an exception to that: it can only select between
 * the sources the build already carries, it is ignored entirely unless the build carries
 * both, and it can therefore never introduce an origin. It exists because a demo video
 * and a screenshot have to be reproducible from a link — `#/gate?permit=…&source=replay`
 * has to land on the same screen every time.
 *
 * ── WHY THE BADGE IS NOT READ FROM HERE ──────────────────────────────────────────
 *
 * Nothing in this module decides what the honesty chrome says. The chrome reads
 * `transport.describe().mode`, off the object that actually holds the bytes. A selection
 * recorded here and a transport built over there are two places for one fact to live,
 * and the day they disagree is the day the badge is decoration. See `composition.tsx`.
 */

import { createContext, useContext } from 'react';

declare global {
  // Declaration merging onto the interface `src/env.d.ts` owns. Adding the member there
  // would mean editing another worker's file; merging is the same result with no
  // collision, and is the idiom `src/verify/config.ts` already uses for
  // VITE_MAINLINE_LOG_VKEY.
  interface ImportMetaEnv {
    /**
     * Base URL of a live MAINLINE demo API — scheme, host, optional port, no trailing
     * path. `https://d1234.cloudfront.net` in the deployed demo, where CloudFront routes
     * `/v1/*` to the Lambda Function URL and everything else to the site bucket, so the
     * console and its API share ONE origin and there is no CORS anywhere.
     */
    readonly VITE_MAINLINE_API_BASE?: string;
  }
}

// ── What a build can carry ─────────────────────────────────────────────────

export type SourceKind = 'live' | 'replay';

/** The build-time variable that carried a source. Rendered on screen, verbatim. */
export type SourceVariable = 'VITE_MAINLINE_API_BASE' | 'VITE_MAINLINE_BUNDLE_URL';

export interface ConfiguredSource {
  readonly kind: SourceKind;
  /** The base URL, exactly as the build supplied it. Never rewritten, never guessed. */
  readonly location: string;
  readonly variable: SourceVariable;
  /** One sentence a reader can check this against. Rendered beside the badge. */
  readonly why: string;
}

export interface SourceSelection {
  /** Every source THIS BUILD carries, live first. Empty when it carries none. */
  readonly configured: readonly ConfiguredSource[];
  /** The one to build first, or `null` when the build carries none. */
  readonly initial: ConfiguredSource | null;
  /** True exactly when both are configured, which is the only case with a control. */
  readonly switchable: boolean;
  /**
   * Why this build is in the state it is in — including, in the empty case, which two
   * variables were absent. A surface that shows nothing must say which of the several
   * possible nothings it is.
   */
  readonly why: string;
}

/** The query parameter that preselects a source. Honoured only when both are configured. */
export const SOURCE_PARAM = 'source';

export interface ConsoleEnvironment {
  readonly VITE_MAINLINE_API_BASE?: string;
  readonly VITE_MAINLINE_BUNDLE_URL?: string;
}

function trimmed(value: string | undefined): string | null {
  if (value === undefined) return null;
  const text = value.trim();
  return text === '' ? null : text;
}

export function isSourceKind(value: unknown): value is SourceKind {
  return value === 'live' || value === 'replay';
}

/**
 * The decision.
 *
 * Pure, total, and independent of the DOM: `params` is passed in rather than read from
 * `location`, so the whole rule set is exercised by a test with no browser at all.
 */
export function selectSource(
  env: ConsoleEnvironment,
  params?: URLSearchParams,
): SourceSelection {
  const apiBase = trimmed(env.VITE_MAINLINE_API_BASE);
  const bundleUrl = trimmed(env.VITE_MAINLINE_BUNDLE_URL);

  const configured: ConfiguredSource[] = [];
  if (apiBase !== null) {
    configured.push({
      kind: 'live',
      location: apiBase,
      variable: 'VITE_MAINLINE_API_BASE',
      why:
        `VITE_MAINLINE_API_BASE was compiled into this artefact as ${apiBase}. Every byte on ` +
        'screen was fetched from that kernel while you were looking at it.',
    });
  }
  if (bundleUrl !== null) {
    configured.push({
      kind: 'replay',
      location: bundleUrl,
      variable: 'VITE_MAINLINE_BUNDLE_URL',
      why:
        `VITE_MAINLINE_BUNDLE_URL was compiled into this artefact as ${bundleUrl}. The bytes on ` +
        'screen came from an EvidenceBundle captured from a real run, and no frame is served ' +
        'until this browser has recomputed the digests over it.',
    });
  }

  if (configured.length === 0) {
    return {
      configured: [],
      initial: null,
      switchable: false,
      why:
        'This build carries NO SOURCE. Neither VITE_MAINLINE_API_BASE nor ' +
        'VITE_MAINLINE_BUNDLE_URL was set when it was compiled, so the composition root ' +
        'constructed no transport and every surface renders its own NO SOURCE panel. That is ' +
        'a fact about this deployment, not about any record.',
    };
  }

  const live = configured.find((source) => source.kind === 'live') ?? null;
  const replay = configured.find((source) => source.kind === 'replay') ?? null;

  if (live === null || replay === null) {
    // Exactly one. `configured[0]` is that one; the non-null assertion is avoided by
    // reading through the two names above.
    const only = live ?? replay;
    if (only === null) {
      // Unreachable: `configured.length > 0` and every member is one of the two kinds.
      throw new Error('source-select: a non-empty configuration named neither source.');
    }
    return {
      configured,
      initial: only,
      switchable: false,
      why:
        `${only.why} This build carries only that one source, so there is no control to ` +
        'switch: an affordance offering a source the artefact does not contain would produce ' +
        'an error state on click and teach the reader to distrust the badge.',
    };
  }

  const requested = params?.get(SOURCE_PARAM) ?? null;
  const preselected = isSourceKind(requested) ? (requested === 'live' ? live : replay) : null;

  return {
    configured,
    initial: preselected ?? live,
    switchable: true,
    why:
      'This build carries BOTH sources. LIVE is the default because a demo that can reach the ' +
      'database should; REPLAY is one control away and shows the same screen from signed bytes. ' +
      (preselected === null
        ? `A ?${SOURCE_PARAM}=live or ?${SOURCE_PARAM}=replay in this page's address preselects ` +
          'one, which is how a screenshot of either is reproducible from a link. It cannot ' +
          'introduce a source this build does not carry.'
        : `?${SOURCE_PARAM}=${preselected.kind} in this page's address preselected ${
            preselected.kind === 'live' ? 'LIVE' : 'REPLAY'
          }.`),
  };
}

/** The configured source of a given kind, or `null` when this build has none. */
export function sourceFor(
  selection: SourceSelection,
  kind: SourceKind,
): ConfiguredSource | null {
  return selection.configured.find((source) => source.kind === kind) ?? null;
}

/**
 * Query parameters from both positions, hash winning — the same merge `src/app/router.ts`
 * performs and `src/features/evidence/source.ts` restates.
 *
 * Written out here for the third time, deliberately and for the reason that module gives:
 * `parseRoute` also needs the surface registry, and this module must stay a pure function
 * of two strings so that `composition.test.tsx` can call it with no DOM and no registry.
 * Five lines of duplication buys a decision function a test can drive directly.
 */
export function paramsFromAddress(search: string, hash: string): URLSearchParams {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const withoutHash = hash.startsWith('#') ? hash.slice(1) : hash;
  const mark = withoutHash.indexOf('?');
  if (mark >= 0) {
    for (const [key, value] of new URLSearchParams(withoutHash.slice(mark + 1))) {
      params.set(key, value);
    }
  }
  return params;
}

// ── The context the control and the provider share ─────────────────────────

/**
 * Held here rather than in `composition.tsx` because that module exports components and
 * `react-refresh/only-export-components` — which this workspace lints at
 * `--max-warnings 0` — refuses a component module that also exports a context or a hook.
 * The same split the shell already makes between `honesty.ts` and `HonestyProvider.tsx`.
 */
export interface SourceModeValue {
  readonly selection: SourceSelection;
  /** The source currently built, or `null` when the build carries none. */
  readonly active: ConfiguredSource | null;
  /** Switches. A no-op for a kind this build does not carry — never a broken transport. */
  readonly choose: (kind: SourceKind) => void;
}

export const SourceModeContext = createContext<SourceModeValue | null>(null);

/** `null` outside the composition root. Never a fabricated stand-in. */
export function useSourceMode(): SourceModeValue | null {
  return useContext(SourceModeContext);
}
