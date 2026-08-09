// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Focus: who Tab visits, in what order, and whether a dialog can be escaped by accident.
 *
 * The positive-tabindex block is the one that would be missing from a careless version of
 * this file. `tabOrder()` implements the REAL ordering rule — positive tabindex first, in
 * ascending order, ahead of the whole document — even though `audit.ts` refuses positive
 * tabindex outright, because an ordering function that ignored it would report the DOM
 * order as the tab order on exactly the page a keyboard audit exists to catch.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  applyRovingTabindex,
  createFocusTrap,
  focusableWithin,
  isDisabled,
  isFocusable,
  isHiddenFromAssistiveTech,
  isTabbable,
  nextRovingIndex,
  tabOrder,
  tabindexOf,
} from '../../../src/a11y/focus';
import { mount, unmountAll } from './_fixtures';

afterEach(unmountAll);

const ids = (elements: readonly Element[]): readonly string[] =>
  elements.map((element) => element.getAttribute('id') ?? element.tagName.toLowerCase());

describe('focusability', () => {
  it('separates focusable from tabbable — the distinction the shell’s <main> depends on', () => {
    const container = mount('<main id="m" tabindex="-1">surface</main><button id="b">Sign</button>');
    const main = container.querySelector('#m');
    const button = container.querySelector('#b');
    if (main === null || button === null) throw new Error('fixture');

    expect(isFocusable(main)).toBe(true);
    expect(isTabbable(main)).toBe(false);
    expect(isTabbable(button)).toBe(true);
  });

  it('refuses a disabled control, and a control inside a disabled fieldset', () => {
    const container = mount(
      '<button id="a" disabled>a</button>' +
        '<fieldset disabled><button id="b">b</button></fieldset>' +
        '<fieldset disabled><legend><button id="c">c</button></legend><button id="d">d</button></fieldset>',
    );
    const at = (selector: string): Element => {
      const found = container.querySelector(selector);
      if (found === null) throw new Error(selector);
      return found;
    };
    expect(isDisabled(at('#a'))).toBe(true);
    expect(isDisabled(at('#b'))).toBe(true);
    // The first <legend>'s controls escape a disabled fieldset. Calling them unreachable
    // would be a false finding on a real and common pattern.
    expect(isDisabled(at('#c'))).toBe(false);
    expect(isDisabled(at('#d'))).toBe(true);
  });

  it('honours the hiddenness the DOM can express, and only that', () => {
    const container = mount(
      '<div hidden><button id="a">a</button></div>' +
        '<div style="display:none"><button id="b">b</button></div>' +
        '<div aria-hidden="true"><button id="c">c</button></div>' +
        '<div class="hidden-by-a-class"><button id="d">d</button></div>',
    );
    const at = (selector: string): Element => {
      const found = container.querySelector(selector);
      if (found === null) throw new Error(selector);
      return found;
    };
    expect(isFocusable(at('#a'))).toBe(false);
    expect(isFocusable(at('#b'))).toBe(false);
    // aria-hidden does NOT remove an element from the tab order in a browser. That is the
    // bug `focusable-inside-aria-hidden` reports, so this predicate must not hide it.
    expect(isFocusable(at('#c'))).toBe(true);
    expect(isHiddenFromAssistiveTech(at('#c'))).toBe(true);
    // A class cannot be resolved without a cascade. Honestly reported as visible.
    expect(isFocusable(at('#d'))).toBe(true);
  });

  it('parses tabindex, and refuses a value that is not an integer', () => {
    const container = mount('<div id="a" tabindex="0"></div><div id="b" tabindex="nope"></div>');
    const at = (selector: string): Element => {
      const found = container.querySelector(selector);
      if (found === null) throw new Error(selector);
      return found;
    };
    expect(tabindexOf(at('#a'))).toBe(0);
    expect(tabindexOf(at('#b'))).toBeNull();
  });
});

describe('tab order', () => {
  it('is DOM order when nothing carries a positive tabindex', () => {
    const container = mount(
      '<a id="a" href="#/gate">a</a><button id="b">b</button><input id="c"><textarea id="d"></textarea>',
    );
    expect(ids(tabOrder(container))).toEqual(['a', 'b', 'c', 'd']);
  });

  it('models the real rule: positive tabindex jumps the whole queue', () => {
    const container = mount(
      '<button id="first">first in DOM</button>' +
        '<button id="two" tabindex="2">two</button>' +
        '<button id="one" tabindex="1">one</button>' +
        '<button id="last">last in DOM</button>',
    );
    expect(
      ids(tabOrder(container)),
      'an ordering function that ignored positive tabindex would report the DOM order here, ' +
        'which is precisely the page a keyboard audit exists to catch.',
    ).toEqual(['one', 'two', 'first', 'last']);
  });

  it('excludes tabindex="-1" and disabled controls', () => {
    const container = mount(
      '<button id="a">a</button><button id="b" tabindex="-1">b</button><button id="c" disabled>c</button>',
    );
    expect(ids(tabOrder(container))).toEqual(['a']);
    expect(ids(focusableWithin(container))).toEqual(['a', 'b']);
  });
});

describe('the focus trap', () => {
  it('wraps at both ends and restores focus on release', () => {
    const container = mount(
      '<button id="outside">outside</button>' +
        '<div id="dialog" tabindex="-1"><button id="first">first</button><button id="last">last</button></div>',
    );
    const dialog = container.querySelector('#dialog');
    const outside = container.querySelector<HTMLElement>('#outside');
    const first = container.querySelector<HTMLElement>('#first');
    const last = container.querySelector<HTMLElement>('#last');
    if (dialog === null || outside === null || first === null || last === null) throw new Error('fixture');

    outside.focus();
    const trap = createFocusTrap(dialog);
    trap.activate();
    expect(document.activeElement).toBe(first);
    expect(trap.returnTo()).toBe(outside);

    // Tab off the end wraps to the beginning.
    last.focus();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(first);

    // Shift+Tab off the beginning wraps to the end.
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }));
    expect(document.activeElement).toBe(last);

    trap.release();
    expect(document.activeElement).toBe(outside);
  });

  it('survives a child that stops propagation, because it listens in the capture phase', () => {
    const container = mount(
      '<div id="dialog" tabindex="-1"><button id="first">first</button><button id="last">last</button></div>',
    );
    const dialog = container.querySelector('#dialog');
    const first = container.querySelector<HTMLElement>('#first');
    const last = container.querySelector<HTMLElement>('#last');
    if (dialog === null || first === null || last === null) throw new Error('fixture');

    last.addEventListener('keydown', (event) => {
      event.stopPropagation();
    });

    const trap = createFocusTrap(dialog);
    trap.activate();
    last.focus();
    last.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(
      document.activeElement,
      'a field-level key handler calling stopPropagation() must not be able to switch the trap off',
    ).toBe(first);
    trap.release();
  });

  it('calls onEscape and stops listening after release', () => {
    const container = mount('<div id="dialog" tabindex="-1"><button id="only">only</button></div>');
    const dialog = container.querySelector('#dialog');
    if (dialog === null) throw new Error('fixture');

    const onEscape = vi.fn();
    const trap = createFocusTrap(dialog, { onEscape });
    trap.activate();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(onEscape).toHaveBeenCalledTimes(1);

    trap.release();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(onEscape, 'a trap that outlives its dialog is worse than no trap').toHaveBeenCalledTimes(1);
  });
});

describe('roving tabindex', () => {
  it('leaves exactly one tab stop', () => {
    const container = mount('<li id="a"></li><li id="b"></li><li id="c"></li>');
    const items = [...container.querySelectorAll('li')];
    applyRovingTabindex(items, 1);
    expect(items.map((item) => item.getAttribute('tabindex'))).toEqual(['-1', '0', '-1']);
    expect(ids(tabOrder(container))).toEqual(['b']);
  });

  it('does not wrap by default, because the ancestry is a line and not a circle', () => {
    expect(nextRovingIndex('ArrowDown', 2, 3)).toBe(2);
    expect(nextRovingIndex('ArrowUp', 0, 3)).toBe(0);
    expect(nextRovingIndex('ArrowDown', 2, 3, { wrap: true })).toBe(0);
    expect(nextRovingIndex('Home', 2, 3)).toBe(0);
    expect(nextRovingIndex('End', 0, 3)).toBe(2);
    expect(nextRovingIndex('Enter', 0, 3)).toBeNull();
  });

  it('respects orientation', () => {
    expect(nextRovingIndex('ArrowRight', 0, 3, { orientation: 'vertical' })).toBeNull();
    expect(nextRovingIndex('ArrowDown', 0, 3, { orientation: 'vertical' })).toBe(1);
  });
});
