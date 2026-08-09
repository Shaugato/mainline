// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The ARIA 1.2 vocabulary, as data.
 *
 * `audit.ts` refuses a `role` or an `aria-*` attribute that is not in these sets, and
 * that refusal is the whole point of the file: a misspelled ARIA attribute is not an
 * error in any browser. `aria-lable="Close"` is silently ignored, the control ships with
 * no accessible name, every screenshot looks correct, and the only person who finds out
 * is the operator using speech output.
 *
 * ── HOW THIS LIST IS ALLOWED TO BE WRONG ─────────────────────────────────────────
 *
 * It is a transcription of the ARIA 1.2 recommendation, which means it can be STALE (a
 * role added in a later revision reads as invalid here) but not PERMISSIVE. That is the
 * direction an error in a safety gate should point: a false refusal is a five-minute
 * conversation and a line added below, while a false clearance is a control nobody can
 * operate. `roles.test.ts` asserts the sets are non-empty and disjoint from obvious
 * typos, so the file cannot rot into a rubber stamp by being emptied.
 *
 * Deprecated-but-valid roles (`directory`) are included: they are still valid ARIA, and
 * refusing them here would be this file inventing policy rather than reporting the spec.
 */

/** Every role name in ARIA 1.2, including abstract-adjacent document structure roles. */
export const ARIA_ROLES: ReadonlySet<string> = new Set([
  // Widget roles
  'button', 'checkbox', 'gridcell', 'link', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
  'option', 'progressbar', 'radio', 'scrollbar', 'searchbox', 'separator', 'slider',
  'spinbutton', 'switch', 'tab', 'tabpanel', 'textbox', 'treeitem',
  // Composite widget roles
  'combobox', 'grid', 'listbox', 'menu', 'menubar', 'radiogroup', 'tablist', 'tree',
  'treegrid',
  // Document structure roles
  'application', 'article', 'associationlist', 'associationlistitemkey',
  'associationlistitemvalue', 'blockquote', 'caption', 'cell', 'code', 'columnheader',
  'comment', 'definition', 'deletion', 'directory', 'document', 'emphasis', 'feed',
  'figure', 'generic', 'group', 'heading', 'image', 'img', 'insertion', 'list', 'listitem',
  'math', 'meter', 'none', 'note', 'paragraph', 'presentation', 'row', 'rowgroup',
  'rowheader', 'strong', 'subscript', 'superscript', 'suggestion', 'table',
  'term', 'time', 'toolbar', 'tooltip',
  // Landmark roles
  'banner', 'complementary', 'contentinfo', 'form', 'main', 'navigation', 'region',
  'search',
  // Live region roles
  'alert', 'log', 'marquee', 'status', 'timer',
  // Window roles
  'alertdialog', 'dialog',
]);

/** Roles that name a landmark. Repeated landmarks of one kind must be named apart. */
export const LANDMARK_ROLES: ReadonlySet<string> = new Set([
  'banner', 'complementary', 'contentinfo', 'form', 'main', 'navigation', 'region', 'search',
]);

/** Native elements that map to a landmark role without an explicit `role` attribute. */
export const IMPLICIT_LANDMARKS: Readonly<Record<string, string>> = {
  header: 'banner',
  footer: 'contentinfo',
  main: 'main',
  nav: 'navigation',
  aside: 'complementary',
  form: 'form',
};

/** Roles that announce their contents when they change. */
export const LIVE_REGION_ROLES: ReadonlySet<string> = new Set([
  'alert', 'log', 'marquee', 'status', 'timer', 'alertdialog',
]);

/** Every `aria-*` attribute defined by ARIA 1.2. */
export const ARIA_ATTRIBUTES: ReadonlySet<string> = new Set([
  // Global states and properties
  'aria-atomic', 'aria-braillelabel', 'aria-brailleroledescription', 'aria-busy',
  'aria-controls', 'aria-current', 'aria-describedby', 'aria-description', 'aria-details',
  'aria-disabled', 'aria-dropeffect', 'aria-errormessage', 'aria-flowto', 'aria-grabbed',
  'aria-haspopup', 'aria-hidden', 'aria-invalid', 'aria-keyshortcuts', 'aria-label',
  'aria-labelledby', 'aria-live', 'aria-owns', 'aria-relevant', 'aria-roledescription',
  // Widget states and properties
  'aria-activedescendant', 'aria-autocomplete', 'aria-checked', 'aria-colcount',
  'aria-colindex', 'aria-colindextext', 'aria-colspan', 'aria-expanded', 'aria-level',
  'aria-modal', 'aria-multiline', 'aria-multiselectable', 'aria-orientation',
  'aria-placeholder', 'aria-posinset', 'aria-pressed', 'aria-readonly', 'aria-required',
  'aria-rowcount', 'aria-rowindex', 'aria-rowindextext', 'aria-rowspan', 'aria-selected',
  'aria-setsize', 'aria-sort', 'aria-valuemax', 'aria-valuemin', 'aria-valuenow',
  'aria-valuetext',
]);

/** `aria-*` attributes whose value is a space-separated list of element ids. */
export const ARIA_ID_REFERENCE_LISTS: readonly string[] = [
  'aria-controls',
  'aria-describedby',
  'aria-flowto',
  'aria-labelledby',
  'aria-owns',
];

/** `aria-*` attributes whose value is a single element id. */
export const ARIA_ID_REFERENCES: readonly string[] = [
  'aria-activedescendant',
  'aria-details',
  'aria-errormessage',
];

/** `aria-*` attributes that accept only `true` or `false`. */
export const ARIA_BOOLEAN_ATTRIBUTES: readonly string[] = [
  'aria-atomic',
  'aria-busy',
  'aria-disabled',
  'aria-modal',
  'aria-multiline',
  'aria-multiselectable',
  'aria-readonly',
  'aria-required',
];

/** The permitted values of the tristate and enumerated attributes this console uses. */
export const ARIA_ENUMERATED_VALUES: Readonly<Record<string, readonly string[]>> = {
  'aria-checked': ['true', 'false', 'mixed', 'undefined'],
  'aria-current': ['page', 'step', 'location', 'date', 'time', 'true', 'false'],
  'aria-expanded': ['true', 'false', 'undefined'],
  'aria-hidden': ['true', 'false', 'undefined'],
  'aria-invalid': ['true', 'false', 'grammar', 'spelling'],
  'aria-live': ['off', 'polite', 'assertive'],
  'aria-orientation': ['horizontal', 'vertical', 'undefined'],
  'aria-pressed': ['true', 'false', 'mixed', 'undefined'],
  'aria-selected': ['true', 'false', 'undefined'],
  'aria-sort': ['ascending', 'descending', 'none', 'other'],
};

/** Element names that can be the target of a `<label for>`. */
export const LABELABLE_ELEMENTS: ReadonlySet<string> = new Set([
  'button', 'input', 'meter', 'output', 'progress', 'select', 'textarea',
]);

/**
 * Elements and roles that must have an accessible name to be operable.
 *
 * `role="generic"` and `role="presentation"` are deliberately absent: a named generic is
 * pointless but harmless, and demanding a name from every div would produce a report
 * nobody reads.
 */
export const NAME_REQUIRED_ROLES: ReadonlySet<string> = new Set([
  'button', 'checkbox', 'combobox', 'link', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
  'option', 'radio', 'searchbox', 'slider', 'spinbutton', 'switch', 'tab', 'textbox',
  'treeitem', 'progressbar', 'meter',
]);
