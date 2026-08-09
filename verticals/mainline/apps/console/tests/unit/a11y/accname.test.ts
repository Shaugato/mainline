// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The accessible-name subset, against the cases that actually decide findings.
 *
 * Every assertion here corresponds to a way `control-name` could be wrong. The two that
 * matter most are the precedence order (a wrong order silently prefers a `title` over a
 * `<label>`, which is what a browser does NOT do) and the aria-hidden exclusion (without
 * it, a decorative glyph counts as a button's name and the rule reports clean).
 */

import { afterEach, describe, expect, it } from 'vitest';

import {
  accessibleDescription,
  accessibleName,
  isAriaHidden,
  labelTextFor,
  visibleTextContent,
} from '../../../src/a11y/accname';
import { mount, unmountAll } from './_fixtures';

afterEach(unmountAll);

/**
 * Mounts one fixture and returns the element `selector` names inside it.
 *
 * `unmountAll()` runs BEFORE each mount, not only after each test. Several assertions in
 * one `it` would otherwise leave two containers in the document carrying the same id —
 * and `labelTextFor()` searches the whole document for `label[for]`, exactly as a browser
 * does, so the second fixture would inherit the first one's label and pass or fail for
 * reasons that have nothing to do with the code.
 */
function only(html: string, selector: string): Element {
  unmountAll();
  const found = mount(html).querySelector(selector);
  if (found === null) throw new Error(`fixture has no ${selector}`);
  return found;
}

describe('precedence', () => {
  it('aria-labelledby beats aria-label beats native beats title', () => {
    expect(
      accessibleName(
        only(
          '<span id="ref">From the reference</span>' +
            '<button id="b" aria-labelledby="ref" aria-label="From the label" title="From the title">From content</button>',
          '#b',
        ),
      ),
    ).toBe('From the reference');

    expect(
      accessibleName(
        only('<button id="b" aria-label="From the label" title="t">From content</button>', '#b'),
      ),
    ).toBe('From the label');

    expect(accessibleName(only('<button id="b" title="t">From content</button>', '#b'))).toBe(
      'From content',
    );

    expect(accessibleName(only('<button id="b" title="From the title"></button>', '#b'))).toBe(
      'From the title',
    );
  });

  it('concatenates several aria-labelledby targets in the order written', () => {
    const element = only(
      '<span id="a">Dispose</span><span id="b">precursor 7</span><button id="x" aria-labelledby="b a"></button>',
      '#x',
    );
    expect(accessibleName(element)).toBe('precursor 7 Dispose');
  });

  it('does not hang on a self-referential aria-labelledby', () => {
    const element = only('<button id="loop" aria-labelledby="loop">text</button>', '#loop');
    // One level of indirection, a visited set, and a real answer rather than a stack overflow.
    expect(accessibleName(element)).toBe('text');
  });
});

describe('native names', () => {
  it('reads a label by for=, by containment, and both', () => {
    expect(labelTextFor(only('<label for="i">Threshold</label><input id="i">', '#i'))).toBe('Threshold');
    expect(labelTextFor(only('<label>Threshold <input id="i"></label>', '#i'))).toBe('Threshold');
  });

  it('does not let the control’s own text become its own label', () => {
    const element = only('<label>Threshold <input id="i" value="0.62"></label>', '#i');
    expect(labelTextFor(element)).toBe('Threshold');
  });

  it('finds a label whose for= contains selector metacharacters', () => {
    // `id="a.b:c"` is legal HTML and would break a naive `querySelector('#' + id)`.
    const element = only('<label for="a.b:c">Threshold</label><input id="a.b:c">', 'input');
    expect(accessibleName(element)).toBe('Threshold');
  });

  it('uses alt for images, value for button inputs, and the type default for submit', () => {
    expect(accessibleName(only('<img id="i" alt="seal">', '#i'))).toBe('seal');
    expect(accessibleName(only('<input id="i" type="button" value="Sign">', '#i'))).toBe('Sign');
    expect(accessibleName(only('<input id="i" type="submit">', '#i'))).toBe('Submit');
  });

  it('uses legend for a fieldset, caption for a table, title for an svg', () => {
    expect(accessibleName(only('<fieldset id="f"><legend>Clearance</legend></fieldset>', '#f'))).toBe('Clearance');
    expect(accessibleName(only('<table id="t"><caption>Precursors</caption></table>', '#t'))).toBe('Precursors');
    expect(accessibleName(only('<svg id="s"><title>Ribbon</title></svg>', '#s'))).toBe('Ribbon');
  });

  it('gives an anchor without href no name from content — it is not a link', () => {
    expect(accessibleName(only('<a id="a">not a link</a>', '#a'))).toBe('');
    expect(accessibleName(only('<a id="a" href="#/gate">a link</a>', '#a'))).toBe('a link');
  });

  it('does not take a name from the content of a plain div', () => {
    expect(accessibleName(only('<div id="d">some prose</div>', '#d'))).toBe('');
  });
});

describe('aria-hidden', () => {
  it('excludes a hidden subtree from name-from-content', () => {
    expect(
      accessibleName(only('<button id="b"><span aria-hidden="true">×</span></button>', '#b')),
    ).toBe('');
  });

  it('keeps a visually-hidden span, because that is how this console speaks', () => {
    // src/design/primitives/Mono.tsx renders "staged value: " into a visually-hidden
    // span. Excluding it would break the pattern the design package depends on.
    expect(
      visibleTextContent(only('<code id="c"><span class="visually-hidden">staged value: </span>0.62</code>', '#c')),
    ).toBe('staged value: 0.62');
  });

  it('detects an aria-hidden ancestor, not only the element itself', () => {
    const element = only('<div aria-hidden="true"><span><button id="b">x</button></span></div>', '#b');
    expect(isAriaHidden(element)).toBe(true);
  });
});

describe('description', () => {
  it('prefers aria-describedby, then aria-description, then an unconsumed title', () => {
    expect(
      accessibleDescription(
        only('<p id="n">Six checks are open.</p><button id="b" aria-describedby="n">Dispose</button>', '#b'),
      ),
    ).toBe('Six checks are open.');

    expect(
      accessibleDescription(only('<button id="b" aria-description="Six open">Dispose</button>', '#b')),
    ).toBe('Six open');

    // A title that was consumed as the NAME is not also the description.
    expect(accessibleDescription(only('<button id="b" title="Dispose"></button>', '#b'))).toBe('');
    expect(accessibleDescription(only('<button id="b" title="Six open">Dispose</button>', '#b'))).toBe('Six open');
  });
});
