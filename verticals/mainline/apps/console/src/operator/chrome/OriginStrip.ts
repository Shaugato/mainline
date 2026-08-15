// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ORIGIN STRIP — operator-systems-plan.md R3.
 *
 * Two facts, permanently on screen, and neither of them is compiled in.
 *
 *   • `location.origin` — the origin this page was actually served by. There is deliberately
 *     no CORS block on the deployed Function URL (M1), which means a page NOT served by that
 *     origin cannot read its answers at all. Rendering the origin is therefore not decoration:
 *     it is the evidence that the requests on this screen could only have gone one place.
 *   • `X-Mainline-Emulator` — stamped on every response by `scripts/deploy/local_furl.py`
 *     (M12) and by nothing else. It exists precisely so a rehearsal capture cannot be passed
 *     off as the deployed one. When it is present, this strip prints it.
 *
 * ── THE THREE STATES, AND WHY THERE ARE THREE ────────────────────────────────────────
 *
 * `unobserved` is not `absent`. Before any response has come back, this page knows NOTHING
 * about the header, and printing "absent" would be a claim about a response that has not
 * happened. After a response arrives with no such header, "absent" is a real finding: nothing
 * on the wire declared itself an emulator. Collapsing the two would be the same defect as a
 * gate counter reading zero because nothing computed it.
 *
 * ── HOW THE VALUE GETS HERE ──────────────────────────────────────────────────────────
 *
 * The kernel client (`src/operator/kernel/**`, another worker) owns the fetch. It hands the
 * header over by EITHER of two paths, and neither one makes the shell import the kernel or the
 * kernel import the shell:
 *
 *   1. `reportEmulator(exchange.emulator)` — a direct call, typed.
 *   2. `document.dispatchEvent(new CustomEvent('mainline-operator:exchange',
 *      { detail: { emulator: exchange.emulator } }))` — no import at all.
 *
 * Whichever arrives first wins, and every later response overwrites it: the strip always shows
 * what the LAST response said, never a remembered best case.
 */

/** The response header this strip reads, spelled once. */
export const EMULATOR_HEADER = 'X-Mainline-Emulator';

/** The DOM event the kernel may dispatch instead of importing this module. */
export const EXCHANGE_EVENT = 'mainline-operator:exchange';

export type EmulatorObservation =
  | { readonly kind: 'unobserved' }
  | { readonly kind: 'absent' }
  | { readonly kind: 'present'; readonly value: string };

/** What the strip prints before any response has been seen. Never "absent". */
export const UNOBSERVED_TEXT = 'no response observed yet in this page load';

/** What it prints once a response has arrived carrying no such header. */
export const ABSENT_TEXT = 'absent — the last response declared no emulator';

let observation: EmulatorObservation = { kind: 'unobserved' };

const mounted = new Set<(next: EmulatorObservation) => void>();

export function observedEmulator(): EmulatorObservation {
  return observation;
}

/**
 * Records what the last response said about {@link EMULATOR_HEADER}.
 *
 * `null` means the response arrived and carried no such header — which is a fact, and is
 * rendered as one. It does not mean "no response yet"; that state can only be left, never
 * re-entered, except by {@link resetEmulatorObservation}.
 */
export function reportEmulator(header: string | null): void {
  observation =
    header === null || header.trim() === '' ? { kind: 'absent' } : { kind: 'present', value: header };
  for (const paint of mounted) paint(observation);
}

/** Back to `unobserved`. For tests, and for a shell that is being re-booted in place. */
export function resetEmulatorObservation(): void {
  observation = { kind: 'unobserved' };
  for (const paint of mounted) paint(observation);
}

/**
 * Bridges the import-free path: a `CustomEvent` carrying `{ emulator: string | null }`.
 *
 * Anything else in the detail is ignored; a detail with no `emulator` key at all is ignored
 * rather than treated as `null`, because "the event did not mention the header" and "the
 * response did not carry the header" are different statements.
 */
export function installExchangeBridge(target: EventTarget = document): () => void {
  const handler = (event: Event): void => {
    if (!(event instanceof CustomEvent)) return;
    const detail: unknown = event.detail;
    if (typeof detail !== 'object' || detail === null || !('emulator' in detail)) return;
    const value: unknown = (detail as { emulator?: unknown }).emulator;
    if (value === null) reportEmulator(null);
    else if (typeof value === 'string') reportEmulator(value);
  };
  target.addEventListener(EXCHANGE_EVENT, handler);
  return () => {
    target.removeEventListener(EXCHANGE_EVENT, handler);
  };
}

export interface OriginStripHandle {
  readonly element: HTMLElement;
  /** Detaches this strip from the observation feed. */
  destroy(): void;
}

export function createOriginStrip(
  win: Pick<Window, 'location'> = window,
  doc: Document = document,
): OriginStripHandle {
  const strip = doc.createElement('footer');
  strip.className = 'cw-origin';
  strip.setAttribute('data-cw', 'origin-strip');
  strip.setAttribute('aria-label', 'Origin and emulator');

  const originValue = doc.createElement('code');
  originValue.className = 'cw-origin__value';
  originValue.setAttribute('data-cw-field', 'origin');
  // Verbatim, whatever it is — including the string "null" under file://, which is the
  // honest answer and is also the answer that explains why nothing loaded.
  originValue.textContent = win.location.origin;

  const emulatorValue = doc.createElement('code');
  emulatorValue.className = 'cw-origin__value';
  emulatorValue.setAttribute('data-cw-field', 'emulator');

  strip.append(
    pair(doc, 'served from', originValue),
    pair(doc, EMULATOR_HEADER, emulatorValue),
  );

  const paint = (next: EmulatorObservation): void => {
    emulatorValue.setAttribute('data-observed', next.kind);
    emulatorValue.textContent =
      next.kind === 'present'
        ? next.value
        : next.kind === 'absent'
          ? ABSENT_TEXT
          : UNOBSERVED_TEXT;
  };

  paint(observation);
  mounted.add(paint);

  return {
    element: strip,
    destroy: () => {
      mounted.delete(paint);
    },
  };
}

function pair(doc: Document, label: string, value: HTMLElement): HTMLElement {
  const wrapper = doc.createElement('span');
  wrapper.className = 'cw-origin__pair';

  const labelNode = doc.createElement('span');
  labelNode.className = 'cw-origin__label';
  labelNode.textContent = label;

  wrapper.append(labelNode, value);
  return wrapper;
}
