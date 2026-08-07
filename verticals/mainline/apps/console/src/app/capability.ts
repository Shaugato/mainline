// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The capability probe — synchronous, injectable, frozen.
 *
 * ui.md §1.3: the 2D ribbon is the same truth minus one axis, NEVER a fallback. This
 * module decides which renderer the ancestry surface gets, and it does so by reading
 * the machine rather than by guessing about it.
 *
 * Two rules that a careless probe gets wrong:
 *
 *   • An unreported signal is `null`, and `null` is not "low". A browser that does not
 *     implement `navigator.deviceMemory` has told us nothing; inventing a number and
 *     then gating on it is a fabricated claim about the reader's machine, which is the
 *     precise failure mode this whole console exists to refuse.
 *   • `?render=3d` is a REQUEST, not an override. It can defeat a soft signal (a small
 *     `deviceMemory`, a save-data hint) because those are policy. It cannot defeat the
 *     absence of a WebGL2 context, because that is physics. Every such refusal is
 *     recorded in `reasons`, which the honesty chrome can render verbatim.
 */

/** The two renderers over the one `AncestryLayout` (ui.md §1.3). */
export type RenderMode = '2d' | '3d';

/**
 * Below this the MEMORY register is not attempted. Four gigabytes is the threshold
 * ui.md §1.3 names; `navigator.deviceMemory` is quantised to powers of two and capped
 * at 8, so this is a coarse instrument and is treated as one.
 */
export const MEMORY_REGISTER_MIN_DEVICE_MEMORY_GB = 4;

/**
 * Everything the probe is allowed to look at. Injected rather than read from globals
 * so that the decision is testable without a browser, and so that no part of the
 * decision can be reached by a module that did not ask for it.
 */
export interface CapabilityHost {
  /** `location.search`, including the leading `?`. */
  readonly search: string;
  /** `location.hash`, including the leading `#`. The router is hash-based. */
  readonly hash: string;
  /** `navigator.deviceMemory` in GiB, or `null` when the browser does not report it. */
  readonly deviceMemoryGb: number | null;
  /** `navigator.hardwareConcurrency`, or `null` when unreported. */
  readonly hardwareConcurrency: number | null;
  /** `matchMedia('(prefers-reduced-motion: reduce)').matches`. */
  readonly prefersReducedMotion: boolean;
  /** `navigator.connection.saveData` — the battery-saver / metered-link signal. */
  readonly saveData: boolean;
  /** Must not throw. `probeCapability` catches anyway, and records the catch. */
  readonly probeWebgl2: () => boolean;
}

export interface Capability {
  readonly webgl2: boolean;
  readonly deviceMemoryGb: number | null;
  readonly hardwareConcurrency: number | null;
  readonly prefersReducedMotion: boolean;
  readonly saveData: boolean;
  /** What the URL asked for, or `null` if it asked for nothing legible. */
  readonly renderOverride: RenderMode | null;
  /** What the ancestry surface will actually render. */
  readonly renderMode: RenderMode;
  /** The arithmetic, in order. Never empty. Safe to render verbatim. */
  readonly reasons: readonly string[];
}

const RENDER_PARAM = 'render';

/**
 * Reads `render=` from either query position. The console is hash-routed (so it can be
 * served from `file://` and from any static sub-path), which means a deep link can
 * legitimately look like `?render=2d#/ancestry` or `#/ancestry?render=2d`. Both work;
 * the hash query wins because it is the more specific of the two.
 */
export function readRenderOverride(search: string, hash: string): RenderMode | null {
  const hashQueryStart = hash.indexOf('?');
  const sources = [
    hashQueryStart >= 0 ? hash.slice(hashQueryStart + 1) : '',
    search.startsWith('?') ? search.slice(1) : search,
  ];
  for (const source of sources) {
    if (source === '') continue;
    const value = new URLSearchParams(source).get(RENDER_PARAM);
    if (value === '2d' || value === '3d') return value;
  }
  return null;
}

export function probeCapability(host: CapabilityHost): Capability {
  const reasons: string[] = [];

  let webgl2 = false;
  try {
    webgl2 = host.probeWebgl2();
  } catch (error) {
    // A probe that throws is a probe that failed. Record it; never let it escape and
    // take the whole shell down on a machine whose only sin is having no GPU.
    webgl2 = false;
    reasons.push(
      `WebGL2 probe threw (${error instanceof Error ? error.message : String(error)}) — treated as absent.`,
    );
  }

  reasons.push(`WebGL2: ${webgl2 ? 'available' : 'absent'}.`);
  reasons.push(
    host.deviceMemoryGb === null
      ? 'deviceMemory: not reported by this browser — unreported is not low, so it is not a reason on its own.'
      : `deviceMemory: ${host.deviceMemoryGb} GB (floor for the walk is ${MEMORY_REGISTER_MIN_DEVICE_MEMORY_GB} GB).`,
  );
  reasons.push(
    host.hardwareConcurrency === null
      ? 'hardwareConcurrency: not reported.'
      : `hardwareConcurrency: ${host.hardwareConcurrency}.`,
  );
  reasons.push(`prefers-reduced-motion: ${host.prefersReducedMotion ? 'yes' : 'no'}.`);
  reasons.push(`save-data: ${host.saveData ? 'yes' : 'no'}.`);

  const renderOverride = readRenderOverride(host.search, host.hash);

  // Soft signals: policy, not physics. A user who types render=3d may defeat them.
  const soft: string[] = [];
  if (host.prefersReducedMotion) soft.push('prefers-reduced-motion is set');
  if (host.saveData) soft.push('save-data is set');
  if (host.deviceMemoryGb !== null && host.deviceMemoryGb < MEMORY_REGISTER_MIN_DEVICE_MEMORY_GB) {
    soft.push(`deviceMemory ${host.deviceMemoryGb} GB is below the ${MEMORY_REGISTER_MIN_DEVICE_MEMORY_GB} GB floor`);
  }

  let renderMode: RenderMode;

  if (renderOverride === '2d') {
    renderMode = '2d';
    reasons.push('?render=2d — the ribbon was requested explicitly; nothing else was consulted.');
  } else if (!webgl2) {
    renderMode = '2d';
    reasons.push(
      renderOverride === '3d'
        ? '?render=3d was requested and is refused: no WebGL2 context exists, so the walk cannot be drawn. The ribbon carries every fact the walk does.'
        : 'No WebGL2 context — the ribbon renders the same layout projected on (x, y).',
    );
  } else if (renderOverride === '3d') {
    renderMode = '3d';
    reasons.push(
      soft.length === 0
        ? '?render=3d — requested, and nothing objected.'
        : `?render=3d — requested, overriding: ${soft.join('; ')}.`,
    );
  } else if (soft.length > 0) {
    renderMode = '2d';
    reasons.push(`Ribbon selected: ${soft.join('; ')}.`);
  } else {
    renderMode = '3d';
    reasons.push('Nothing objected: the dimensional walk is available on this machine.');
  }

  return Object.freeze({
    webgl2,
    deviceMemoryGb: host.deviceMemoryGb,
    hardwareConcurrency: host.hardwareConcurrency,
    prefersReducedMotion: host.prefersReducedMotion,
    saveData: host.saveData,
    renderOverride,
    renderMode,
    reasons: Object.freeze(reasons),
  });
}

interface NonStandardNavigator {
  readonly deviceMemory?: number;
  readonly hardwareConcurrency?: number;
  readonly connection?: { readonly saveData?: boolean };
}

function finiteOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Builds a host from a real browser window.
 *
 * `failIfMajorPerformanceCaveat` is left at its default (`false`) deliberately: D12
 * runs the ancestry-walk screenshots under ANGLE/SwiftShader, a software rasteriser
 * that reports exactly that caveat. Refusing it would make the one WebGL surface in
 * the product untestable, which is a worse outcome than a slow frame on a laptop that
 * asked for the walk anyway.
 */
export function browserCapabilityHost(win: Window & typeof globalThis): CapabilityHost {
  const nav = win.navigator as Navigator & NonStandardNavigator;
  return {
    search: win.location.search,
    hash: win.location.hash,
    deviceMemoryGb: finiteOrNull(nav.deviceMemory),
    hardwareConcurrency: finiteOrNull(nav.hardwareConcurrency),
    prefersReducedMotion:
      typeof win.matchMedia === 'function'
        ? win.matchMedia('(prefers-reduced-motion: reduce)').matches
        : false,
    saveData: nav.connection?.saveData === true,
    probeWebgl2: () => {
      const canvas = win.document.createElement('canvas');
      const gl = canvas.getContext('webgl2');
      if (gl === null) return false;
      // Release the context immediately. The probe answers a question; it does not
      // hold a GPU resource for the lifetime of the page.
      const lose = (gl).getExtension('WEBGL_lose_context') as {
        loseContext?: () => void;
      } | null;
      lose?.loseContext?.();
      return true;
    },
  };
}

/**
 * The host used when there is no browser at all (a Node import, a server render). It
 * claims nothing: no GPU, no reported memory, no media query. The ribbon is the
 * answer, which is the correct answer for a machine with no window.
 */
const HEADLESS_HOST: CapabilityHost = {
  search: '',
  hash: '',
  deviceMemoryGb: null,
  hardwareConcurrency: null,
  prefersReducedMotion: false,
  saveData: false,
  probeWebgl2: () => false,
};

/**
 * The probe result for this document, computed once at module load and frozen.
 *
 * It is a snapshot on purpose. A capability that changes under the reader mid-session
 * would change what a screenshot means, and screenshots of this console are exhibits.
 */
export const CAPABILITY: Capability = probeCapability(
  typeof window === 'undefined' ? HEADLESS_HOST : browserCapabilityHost(window),
);
