// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * ACCESSIBLE NAME — a documented subset of the accname 1.2 algorithm.
 *
 * `audit.ts` needs to answer one question about hundreds of elements: *would a screen
 * reader have anything to say about this control?* The full accname algorithm is a
 * recursive traversal with role-dependent name-from-content rules, CSS pseudo-element
 * participation, and a text-alternative computation that depends on layout. jsdom has
 * no layout and no cascade, so a faithful implementation is not available here at any
 * price.
 *
 * ── WHAT THIS IMPLEMENTS, EXACTLY ────────────────────────────────────────────────
 *
 * In precedence order, stopping at the first non-empty result:
 *
 *   1. `aria-labelledby` — concatenated text of the referenced elements, in the order
 *      written, with one level of recursion and a visited set (accname allows exactly
 *      one level of `aria-labelledby` indirection; deeper cycles are the classic way an
 *      implementation hangs on a page that references itself).
 *   2. `aria-label`.
 *   3. The native host-language label:
 *        • `<label for>` or an ancestor `<label>`, for labelable elements
 *        • `alt` for `<img>`, `<area>`, `<input type=image>`
 *        • `value`, or the type-specific default, for `<input type=button|submit|reset>`
 *        • `<legend>` for `<fieldset>`, `<caption>` for `<table>`, `<title>` for `<svg>`
 *        • text content for the roles that take their name from content
 *   4. `placeholder` on a text field — accname's last-resort host-language fallback.
 *   5. `title`.
 *
 * ── WHAT IT DOES NOT IMPLEMENT, AND WHY THAT IS SAFE HERE ────────────────────────
 *
 *   • CSS `::before` / `::after` content does not participate. It cannot be read
 *     without a cascade, and `docs/visual-language.md` forbids a pseudo-element from
 *     carrying a verbatim value in the first place — `check-a11y.ts` refuses that form
 *     statically, so the two gaps close each other.
 *   • Elements hidden by CSS are not excluded from name-from-content, because "hidden by
 *     CSS" is not knowable here. `aria-hidden` subtrees ARE excluded, which is the case
 *     that matters: a visually-hidden span is how this console gives a screen reader the
 *     word "staged", and excluding it would break the very pattern the design package
 *     uses.
 *
 * The consequence of both gaps points the same way: this function is more likely to find
 * a name than a browser is, never less. An auditor that under-reports names would produce
 * false failures, which is how a gate gets deleted; one that over-reports produces the
 * occasional missed finding, which the browser tier's real axe run catches.
 */

const NAME_FROM_CONTENT_TAGS: ReadonlySet<string> = new Set([
  'a', 'button', 'summary', 'th', 'td', 'legend', 'caption', 'option', 'label', 'output',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'figcaption', 'dt',
]);

const NAME_FROM_CONTENT_ROLES: ReadonlySet<string> = new Set([
  'button', 'cell', 'checkbox', 'columnheader', 'gridcell', 'heading', 'link', 'menuitem',
  'menuitemcheckbox', 'menuitemradio', 'option', 'radio', 'row', 'rowheader', 'switch',
  'tab', 'tooltip', 'treeitem',
]);

const INPUT_DEFAULT_LABELS: Readonly<Record<string, string>> = {
  submit: 'Submit',
  reset: 'Reset',
};

function normalise(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

function tagOf(element: Element): string {
  return element.tagName.toLowerCase();
}

function attr(element: Element, name: string): string | null {
  return element.getAttribute(name);
}

/** Whether this element or an ancestor has `aria-hidden="true"`. */
export function isAriaHidden(element: Element): boolean {
  let current: Element | null = element;
  while (current !== null) {
    if (current.getAttribute('aria-hidden') === 'true') return true;
    current = current.parentElement;
  }
  return false;
}

/**
 * Raw concatenated text, `aria-hidden` subtrees removed, whitespace NOT collapsed.
 *
 * The whitespace matters more than it looks. `Mono.tsx` renders
 * `<span class="visually-hidden">staged value: </span>` followed by the value, and a
 * recursive implementation that trimmed each child before joining would produce
 * `staged value:0.62` — the separator this console deliberately put in the accessibility
 * tree, deleted by the function whose job was to read it.
 */
function rawVisibleText(element: Element): string {
  if (element.getAttribute('aria-hidden') === 'true') return '';

  let out = '';
  for (const node of element.childNodes) {
    if (node.nodeType === 3 /* TEXT_NODE */) {
      out += node.nodeValue ?? '';
    } else if (node.nodeType === 1 /* ELEMENT_NODE */) {
      const child = node as Element;
      const tag = tagOf(child);
      if (tag === 'script' || tag === 'style' || tag === 'template') continue;
      out += rawVisibleText(child);
    }
  }
  return out;
}

/**
 * Text content with `aria-hidden` subtrees removed.
 *
 * The removal is the part that matters. `<button aria-hidden="true"><span>×</span></button>`
 * inside a labelled wrapper is a common decorative-glyph pattern, and counting the glyph
 * as the name would report a button called "×" as adequately named.
 */
export function visibleTextContent(element: Element): string {
  return normalise(rawVisibleText(element));
}

/**
 * The text of the elements an `aria-labelledby` points at.
 *
 * A referenced element takes its name FROM CONTENT regardless of its role — that is
 * accname 1.2 step 2B, and it is the step a naive implementation skips. Skipping it makes
 * `<span id="ref">Dispose</span>` contribute nothing, so `aria-labelledby="ref"` resolves
 * to the empty string and the control is reported as unnamed while a browser announces it
 * perfectly.
 */
function referencedText(
  element: Element,
  ids: readonly string[],
  visited: ReadonlySet<Element>,
): string {
  const root = element.ownerDocument;
  const parts: string[] = [];
  for (const id of ids) {
    if (id === '') continue;
    const target = root.getElementById(id);
    if (target === null) continue;
    if (visited.has(target)) continue;
    const name = computeName(target, new Set([...visited, target]), true);
    if (name !== '') parts.push(name);
  }
  return normalise(parts.join(' '));
}

function idList(value: string | null): readonly string[] {
  return value === null ? [] : value.split(/\s+/).filter((id) => id !== '');
}

/** The `<label>` text bound to a labelable element, by `for=` or by containment. */
export function labelTextFor(element: Element): string {
  const id = attr(element, 'id');
  const parts: string[] = [];

  if (id !== null && id !== '') {
    // CSS.escape is not available in every jsdom build; the id is matched by iteration
    // rather than by a selector so that an id containing a colon or a dot — both legal
    // in HTML and both selector metacharacters — cannot silently miss its label.
    for (const label of element.ownerDocument.querySelectorAll('label[for]')) {
      if (label.getAttribute('for') === id) parts.push(visibleTextContent(label));
    }
  }

  const ancestorLabel = element.closest('label');
  if (ancestorLabel !== null) {
    // The control's own text must not become its own label; remove it by cloning.
    const clone = ancestorLabel.cloneNode(true) as Element;
    for (const control of clone.querySelectorAll('input, select, textarea, button')) {
      control.remove();
    }
    parts.push(visibleTextContent(clone));
  }

  return normalise(parts.join(' '));
}

function nativeName(element: Element, fromContent: boolean): string {
  const tag = tagOf(element);

  if (tag === 'img' || tag === 'area') {
    return normalise(attr(element, 'alt') ?? '');
  }

  if (tag === 'input') {
    const type = (attr(element, 'type') ?? 'text').toLowerCase();
    if (type === 'image') return normalise(attr(element, 'alt') ?? '');
    if (type === 'button' || type === 'submit' || type === 'reset') {
      const value = normalise(attr(element, 'value') ?? '');
      if (value !== '') return value;
      return INPUT_DEFAULT_LABELS[type] ?? '';
    }
    if (type === 'hidden') return '';
    return labelTextFor(element);
  }

  if (tag === 'select' || tag === 'textarea' || tag === 'meter' || tag === 'progress') {
    return labelTextFor(element);
  }

  if (tag === 'fieldset') {
    const legend = element.querySelector('legend');
    return legend === null ? '' : visibleTextContent(legend);
  }

  if (tag === 'table') {
    const caption = element.querySelector('caption');
    return caption === null ? '' : visibleTextContent(caption);
  }

  if (tag === 'svg') {
    const title = element.querySelector('title');
    return title === null ? '' : normalise(title.textContent ?? '');
  }

  const role = attr(element, 'role');
  const nameFromContent =
    fromContent ||
    NAME_FROM_CONTENT_TAGS.has(tag) ||
    role?.split(/\s+/).some((token) => NAME_FROM_CONTENT_ROLES.has(token)) === true;

  if (nameFromContent) {
    // `<a>` without `href` is not a link and takes no name from content; treating it as
    // one would silently excuse an unnamed anchor used as a click target. A referenced
    // element (`fromContent`) is exempt — it is being read, not operated.
    if (!fromContent && tag === 'a' && attr(element, 'href') === null && role === null) return '';
    return visibleTextContent(element);
  }

  return '';
}

function computeName(
  element: Element,
  visited: ReadonlySet<Element>,
  fromContent = false,
): string {
  const labelledBy = referencedText(element, idList(attr(element, 'aria-labelledby')), visited);
  if (labelledBy !== '') return labelledBy;

  const label = normalise(attr(element, 'aria-label') ?? '');
  if (label !== '') return label;

  const native = nativeName(element, fromContent);
  if (native !== '') return native;

  const placeholder = normalise(attr(element, 'placeholder') ?? '');
  if (placeholder !== '') return placeholder;

  return normalise(attr(element, 'title') ?? '');
}

/**
 * The accessible name of an element, or `''` when it has none.
 *
 * `''` is a deliberate return value rather than `null`: every caller in `audit.ts` asks
 * "is there a name", and an implementation that could return `null`, `undefined` or `''`
 * for the same condition invites a truthiness check that treats `'0'` as unnamed.
 */
export function accessibleName(element: Element): string {
  return computeName(element, new Set([element]));
}

/**
 * The accessible DESCRIPTION — `aria-describedby`, then `aria-description`, then `title`
 * when `title` was not already consumed as the name.
 */
export function accessibleDescription(element: Element): string {
  const describedBy = referencedText(
    element,
    idList(attr(element, 'aria-describedby')),
    new Set([element]),
  );
  if (describedBy !== '') return describedBy;

  const description = normalise(attr(element, 'aria-description') ?? '');
  if (description !== '') return description;

  const title = normalise(attr(element, 'title') ?? '');
  return title === accessibleName(element) ? '' : title;
}
