// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * FOCUS — who can be reached with a keyboard, in what order, and how a modal keeps it.
 *
 * `docs/leads/ui.md` D14 requires a complete keyboard-only path from the refusal to the
 * signature. That requirement decomposes into three mechanical questions, and this file
 * answers all three without a dependency:
 *
 *   1. Which elements can take focus at all? (`isFocusable`)
 *   2. Which of those does Tab actually visit, and in what order? (`tabOrder`)
 *   3. When the disposition modal is open, can Tab leave it? (`createFocusTrap`)
 *
 * ── THE ORDERING RULE, AND WHY THIS FILE REFUSES POSITIVE TABINDEX ───────────────
 *
 * The real sequential-focus-navigation order puts every positive `tabindex` first, in
 * ascending numeric order, ahead of the entire document. `tabOrder()` implements that
 * faithfully — but `audit.ts` fails any positive `tabindex` as a `serious` finding, and
 * `scripts/check-a11y.ts` refuses it in source, so the faithful branch should be dead
 * code in this console forever.
 *
 * It is implemented anyway, and tested, for one reason: an ordering function that
 * silently ignored positive tabindex would report the DOM order as the tab order on a
 * page where the two differ, which is precisely the page a keyboard audit exists to
 * catch. A checker must model the failure it refuses.
 *
 * ── WHAT jsdom CANNOT TELL US ────────────────────────────────────────────────────
 *
 * Visibility. `display: none` and `visibility: hidden` remove an element from the tab
 * order in a browser; in jsdom there is no cascade, so only the forms visible in the DOM
 * itself are honoured: the `hidden` attribute, `inert`, `aria-hidden`, `disabled`, and
 * an inline `style` that sets `display:none` or `visibility:hidden`. A class that hides
 * an element is invisible to this file, and `A11yReport.notChecked` says so in every
 * report `audit.ts` returns.
 */

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button',
  'input',
  'select',
  'textarea',
  'summary',
  'iframe',
  'object',
  'embed',
  'audio[controls]',
  'video[controls]',
  '[contenteditable]',
  '[tabindex]',
].join(',');

function tagOf(element: Element): string {
  return element.tagName.toLowerCase();
}

/** The inline-style half of hiddenness — the only half a DOM without a cascade has. */
function inlineHidden(element: Element): boolean {
  const style = element.getAttribute('style');
  if (style === null) return false;
  const flat = style.replace(/\s+/g, '').toLowerCase();
  return flat.includes('display:none') || flat.includes('visibility:hidden');
}

/**
 * Whether an element is removed from interaction by the DOM alone.
 *
 * `aria-hidden` is included deliberately. It does not remove an element from the tab
 * order in a browser — that is exactly the bug `focusable-inside-aria-hidden` reports —
 * so this predicate is NOT used by `isFocusable`. It is exported for the auditor, which
 * needs to ask the two questions separately.
 */
export function isHiddenFromAssistiveTech(element: Element): boolean {
  let current: Element | null = element;
  while (current !== null) {
    if (current.hasAttribute('hidden')) return true;
    if (current.getAttribute('aria-hidden') === 'true') return true;
    if (current.hasAttribute('inert')) return true;
    if (inlineHidden(current)) return true;
    current = current.parentElement;
  }
  return false;
}

/**
 * Hidden by the DOM in a way that removes the element from the tab order — the element
 * itself OR any ancestor.
 *
 * `aria-hidden` is deliberately NOT part of this. It hides an element from assistive
 * technology and leaves it fully tabbable, which is the exact defect
 * `focusable-inside-aria-hidden` reports; folding it in here would make that rule
 * unreachable and the report clean.
 *
 * The ancestor walk is the part a first draft leaves out: `<div hidden><button>` is a
 * hidden button, and checking only the element itself calls it reachable.
 */
export function isHiddenByDom(element: Element): boolean {
  let current: Element | null = element;
  while (current !== null) {
    if (current.hasAttribute('hidden')) return true;
    if (inlineHidden(current)) return true;
    current = current.parentElement;
  }
  return false;
}

/** Disabled by the DOM: the `disabled` attribute, a disabled `<fieldset>`, or `inert`. */
export function isDisabled(element: Element): boolean {
  if (element.hasAttribute('disabled')) return true;
  let current: Element | null = element;
  while (current !== null) {
    if (current.hasAttribute('inert')) return true;
    if (tagOf(current) === 'fieldset' && current.hasAttribute('disabled')) {
      const legend = current.querySelector('legend');
      // The first <legend>'s controls escape a disabled fieldset. Modelling that is not
      // pedantry: a disabled fieldset with a legend containing the "edit" button is a
      // real pattern, and calling that button unreachable would be a false finding.
      if (legend?.contains(element) !== true) return true;
    }
    current = current.parentElement;
  }
  return false;
}

/** The parsed `tabindex`, or `null` when the attribute is absent or not an integer. */
export function tabindexOf(element: Element): number | null {
  const raw = element.getAttribute('tabindex');
  if (raw === null) return null;
  const value = Number.parseInt(raw.trim(), 10);
  return Number.isNaN(value) ? null : value;
}

/**
 * Whether an element can hold focus at all (including programmatically, via `focus()`).
 *
 * `tabindex="-1"` is focusable and NOT tabbable — that is the whole point of it, and the
 * shell's `<main tabindex="-1">` depends on the distinction.
 */
export function isFocusable(element: Element): boolean {
  if (isDisabled(element)) return false;
  if (isHiddenByDom(element)) return false;

  const explicit = tabindexOf(element);
  if (explicit !== null) return true;

  const tag = tagOf(element);
  if (tag === 'input') return (element.getAttribute('type') ?? 'text').toLowerCase() !== 'hidden';
  if (tag === 'a' || tag === 'area') return element.hasAttribute('href');
  if (tag === 'audio' || tag === 'video') return element.hasAttribute('controls');
  if (element.hasAttribute('contenteditable')) {
    return element.getAttribute('contenteditable') !== 'false';
  }
  return ['button', 'select', 'textarea', 'summary', 'iframe', 'object', 'embed'].includes(tag);
}

/** Whether Tab visits this element. Focusable, and not `tabindex="-1"`. */
export function isTabbable(element: Element): boolean {
  if (!isFocusable(element)) return false;
  const explicit = tabindexOf(element);
  return explicit === null || explicit >= 0;
}

/** Every element within `root` (inclusive) that can hold focus, in DOM order. */
export function focusableWithin(root: ParentNode): readonly Element[] {
  const found: Element[] = [];
  if (root instanceof Element && isFocusable(root)) found.push(root);
  for (const element of root.querySelectorAll(FOCUSABLE_SELECTOR)) {
    if (isFocusable(element)) found.push(element);
  }
  return found;
}

/**
 * The sequence Tab produces, implementing the real ordering rule.
 *
 * Positive `tabindex` values come first in ascending order (ties broken by DOM order),
 * then everything with `tabindex="0"` or an implicit tab stop in DOM order.
 */
export function tabOrder(root: ParentNode): readonly Element[] {
  const tabbable = focusableWithin(root).filter(isTabbable);

  const positive: { element: Element; index: number; at: number }[] = [];
  const natural: Element[] = [];

  tabbable.forEach((element, at) => {
    const explicit = tabindexOf(element);
    if (explicit !== null && explicit > 0) positive.push({ element, index: explicit, at });
    else natural.push(element);
  });

  positive.sort((a, b) => a.index - b.index || a.at - b.at);
  return [...positive.map((entry) => entry.element), ...natural];
}

// ── The trap ─────────────────────────────────────────────────────────────────────

export interface FocusTrap {
  /** Moves focus into the container and starts holding Tab inside it. */
  readonly activate: () => void;
  /** Stops holding Tab and returns focus to wherever it was before `activate()`. */
  readonly release: () => void;
  /** The element focus will return to on `release()`, or `null` before `activate()`. */
  readonly returnTo: () => Element | null;
}

export interface FocusTrapOptions {
  /**
   * What to focus first. Defaults to the first tabbable element, falling back to the
   * container itself — which is why a trapped container should carry `tabindex="-1"`.
   */
  readonly initial?: Element | null;
  /** Called when Escape is pressed inside the trap. */
  readonly onEscape?: () => void;
}

/**
 * Holds Tab inside `container` until released.
 *
 * Used by the disposition surface, where a signature dialog that leaks Tab back to the
 * page behind it lets a keyboard operator sign a form they can no longer see.
 *
 * It listens on `keydown` in the CAPTURE phase on the container's document, so a child
 * that calls `stopPropagation()` — which any reasonable field-level key handler might —
 * cannot disable the trap. The listener is removed on `release()`; a trap that outlives
 * its dialog is worse than no trap.
 */
export function createFocusTrap(container: Element, options: FocusTrapOptions = {}): FocusTrap {
  const doc = container.ownerDocument;
  let previous: Element | null = null;
  let active = false;

  const onKeyDown = (event: KeyboardEvent): void => {
    if (!active) return;

    if (event.key === 'Escape') {
      options.onEscape?.();
      return;
    }
    if (event.key !== 'Tab') return;

    const stops = tabOrder(container);
    if (stops.length === 0) {
      // Nothing inside can take focus. Refuse to let Tab leave anyway: an empty dialog
      // that releases focus to the page behind it is the leak this trap exists to stop.
      event.preventDefault();
      return;
    }

    const first = stops[0];
    const last = stops[stops.length - 1];
    if (first === undefined || last === undefined) return;

    const current = doc.activeElement;
    const inside = current !== null && container.contains(current);

    if (!inside) {
      // Focus escaped the container (a browser extension, a programmatic focus() from a
      // stale handler). Pull it back to the edge Tab was heading for.
      event.preventDefault();
      const edge = event.shiftKey ? last : first;
      if (edge instanceof HTMLElement) edge.focus();
      return;
    }
    if (!event.shiftKey && current === last) {
      event.preventDefault();
      if (first instanceof HTMLElement) first.focus();
    } else if (event.shiftKey && current === first) {
      event.preventDefault();
      if (last instanceof HTMLElement) last.focus();
    }
  };

  return {
    activate: (): void => {
      if (active) return;
      previous = doc.activeElement;
      active = true;
      doc.addEventListener('keydown', onKeyDown, true);
      const target = options.initial ?? tabOrder(container)[0] ?? container;
      if (target instanceof HTMLElement) target.focus();
    },
    release: (): void => {
      if (!active) return;
      active = false;
      doc.removeEventListener('keydown', onKeyDown, true);
      if (previous instanceof HTMLElement) previous.focus();
      previous = null;
    },
    returnTo: (): Element | null => previous,
  };
}

// ── Roving tabindex ──────────────────────────────────────────────────────────────

/**
 * The roving-tabindex pattern: a composite widget is ONE tab stop, and the arrow keys
 * move within it.
 *
 * The ancestry ribbon uses it — `docs/leads/ui.md` §1.3 requires arrow keys to walk
 * ancestors — and so does any list long enough that tabbing through it would be a
 * punishment. The function is pure: it takes the items and the index that should be
 * active and writes the attributes. Nothing here listens to a key; the surface owns its
 * own key handling, because only the surface knows what "next" means in its geometry.
 */
export function applyRovingTabindex(items: readonly Element[], activeIndex: number): void {
  items.forEach((item, index) => {
    item.setAttribute('tabindex', index === activeIndex ? '0' : '-1');
  });
}

/**
 * The next index for an arrow key, or `null` when the key is not a movement key.
 *
 * `wrap` defaults to false. For the ancestry walk that matters: running off the end of
 * the ancestry is a fact — you have reached the origin event — and wrapping silently to
 * the other end would tell a keyboard user the walk is a circle when it is a line.
 */
export function nextRovingIndex(
  key: string,
  current: number,
  count: number,
  options: { readonly wrap?: boolean; readonly orientation?: 'horizontal' | 'vertical' | 'both' } = {},
): number | null {
  if (count <= 0) return null;
  const orientation = options.orientation ?? 'both';
  const wrap = options.wrap ?? false;

  const forwardKeys =
    orientation === 'horizontal'
      ? ['ArrowRight']
      : orientation === 'vertical'
        ? ['ArrowDown']
        : ['ArrowRight', 'ArrowDown'];
  const backKeys =
    orientation === 'horizontal'
      ? ['ArrowLeft']
      : orientation === 'vertical'
        ? ['ArrowUp']
        : ['ArrowLeft', 'ArrowUp'];

  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;

  const step = forwardKeys.includes(key) ? 1 : backKeys.includes(key) ? -1 : 0;
  if (step === 0) return null;

  const next = current + step;
  if (next < 0) return wrap ? count - 1 : 0;
  if (next >= count) return wrap ? 0 : count - 1;
  return next;
}
