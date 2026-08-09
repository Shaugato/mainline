// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CINEMA BRIDGE.
 *
 * `docs/leads/ui.md` §1.6 / D12: `?cinema=1&seed=<int>&t=<iso>&frame=<int>` freezes the
 * clock, seeds the one permitted PRNG, kills every transition, and puts r3f in
 * `frameloop="never"` with manual `advance()`. That contract is owned by the
 * cinema-conformance-harness worker and lives in `src/cinema/`.
 *
 * ── WHY THIS IS A BRIDGE AND NOT AN IMPORT ───────────────────────────────────────
 *
 * Same reason as `contract.ts`: `src/cinema/` is another worker's directory, and a hard
 * import of a module that may not exist yet would break `tsc --noEmit` for the entire
 * workspace rather than for this surface. The MEMORY register is cut-ladder item 1; it
 * is not allowed to be the reason anybody else's build is red.
 *
 * So the bridge reads the provider's state through the interface the provider publishes
 * to the window, and falls back to parsing the SAME URL GRAMMAR itself. Both paths
 * produce the identical `CinemaState`, and `readCinema()` records which one answered in
 * `source`, so a capture can be told apart from a guess.
 *
 * When `src/cinema/` lands, the only change needed here is to prefer its hook over the
 * window object — the grammar, the defaults and the semantics do not move. That is the
 * point of writing the grammar down twice: the second copy is not a fork, it is a
 * fallback with a test.
 *
 * ── WHAT THIS SURFACE ACTUALLY NEEDS FROM CINEMA MODE ────────────────────────────
 *
 * Two facts and nothing else:
 *
 *   enabled  → `frameloop="never"`, pointer events off, the quality ladder inert.
 *   frame    → advance exactly this many times from a cold mount, then stop.
 *
 * `seed` and `t` are carried through because the provider owns them and a reader of this
 * file should see the whole grammar, but the walk consumes neither: there is no
 * non-deterministic value in this scene, which is the strongest form of D4's rule.
 */

export interface CinemaState {
  readonly enabled: boolean;
  /** The frame index to advance to. `0` when cinema mode is on and no frame was named. */
  readonly frame: number;
  /** The PRNG seed. Carried, never consumed here. */
  readonly seed: number | null;
  /** The frozen instant, ISO-8601. Carried, never consumed here. */
  readonly tIso: string | null;
  /** Which of the two paths answered. Rendered into `data-walk-cinema-source`. */
  readonly source: 'provider' | 'url' | 'absent';
}

export const CINEMA_ABSENT: CinemaState = Object.freeze({
  enabled: false,
  frame: 0,
  seed: null,
  tIso: null,
  source: 'absent',
});

/**
 * What the provider is expected to publish. Structural, optional, and never trusted:
 * every field is validated before it is believed.
 */
interface PublishedCinema {
  readonly enabled?: unknown;
  readonly frame?: unknown;
  readonly seed?: unknown;
  readonly t?: unknown;
}

interface CinemaHost {
  /** `location.search`, including the leading `?`. */
  readonly search: string;
  /** `location.hash`, including the leading `#`. The console is hash-routed. */
  readonly hash: string;
  /** Whatever the provider published, or `undefined`. */
  readonly published: unknown;
}

function nonNegativeInt(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) {
    return Math.trunc(value);
  }
  if (typeof value === 'string' && /^\d+$/.test(value.trim())) {
    const parsed = Number.parseInt(value.trim(), 10);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/**
 * Reads a parameter from either query position.
 *
 * The console is hash-routed so it can be served from `file://` and from any static
 * sub-path (W1's router), which means a deep link can legitimately be
 * `?cinema=1#/ancestry` or `#/ancestry?cinema=1`. The hash query wins, because it is the
 * more specific of the two. This mirrors `src/app/capability.ts`'s `readRenderOverride`
 * exactly; the two grammars must not drift.
 */
function readParam(search: string, hash: string, key: string): string | null {
  const hashQueryStart = hash.indexOf('?');
  const sources = [
    hashQueryStart >= 0 ? hash.slice(hashQueryStart + 1) : '',
    search.startsWith('?') ? search.slice(1) : search,
  ];
  for (const source of sources) {
    if (source === '') continue;
    const value = new URLSearchParams(source).get(key);
    if (value !== null) return value;
  }
  return null;
}

/** The pure decision, so `cinema.test.ts` needs no window. */
export function decideCinema(host: CinemaHost): CinemaState {
  const published = host.published;
  if (typeof published === 'object' && published !== null) {
    const record = published as PublishedCinema;
    const enabled = record.enabled === true;
    if (enabled) {
      return Object.freeze({
        enabled: true,
        frame: nonNegativeInt(record.frame) ?? 0,
        seed: nonNegativeInt(record.seed),
        tIso: typeof record.t === 'string' && record.t !== '' ? record.t : null,
        source: 'provider' as const,
      });
    }
  }

  const flag = readParam(host.search, host.hash, 'cinema');
  if (flag !== '1' && flag !== 'true') return CINEMA_ABSENT;

  return Object.freeze({
    enabled: true,
    frame: nonNegativeInt(readParam(host.search, host.hash, 'frame')) ?? 0,
    seed: nonNegativeInt(readParam(host.search, host.hash, 'seed')),
    tIso: readParam(host.search, host.hash, 't'),
    source: 'url' as const,
  });
}

/** The window key the harness publishes on. Named once, here, so a rename is one edit. */
export const CINEMA_WINDOW_KEY = '__MAINLINE_CINEMA__';

interface CinemaWindow {
  readonly [CINEMA_WINDOW_KEY]?: unknown;
}

/**
 * The live read. No window ⇒ no cinema, which is correct: a machine with no document is
 * not taking a screenshot.
 */
export function readCinema(win?: Window & CinemaWindow): CinemaState {
  const target: (Window & CinemaWindow) | undefined =
    win ?? (typeof window === 'undefined' ? undefined : window);
  if (target === undefined) return CINEMA_ABSENT;
  return decideCinema({
    search: target.location.search,
    hash: target.location.hash,
    published: target[CINEMA_WINDOW_KEY],
  });
}
