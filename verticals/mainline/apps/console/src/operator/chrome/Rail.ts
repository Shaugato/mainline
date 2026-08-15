// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE LEFT RAIL — the registers a control-of-work system keeps, and which of them this
 * deployment actually has.
 *
 * It is VISIBLY NON-INTERACTIVE, and that is a claim this file has to make good on rather than
 * imply. Every item is a `<span>` inside an `<li>`: no anchor, no button, no `tabindex`, no
 * pointer cursor, no hover affordance, nothing a keyboard can land on. A rail of dead links is
 * the oldest tell of a fake screenshot, and a judge who tabs into one and finds it does nothing
 * has learnt something true about the demo and nothing true about the product.
 *
 * The three registers this deployment does not carry SAY SO, in the item, in words. An empty
 * section and an unbuilt section must not look the same — the same rule the module frame
 * applies to a route with no screen registered.
 *
 * `tests/unit/operator/shell/chrome.test.ts` asserts the rail contains no focusable element,
 * so this stays true when somebody adds an item later.
 */

import { moduleFor, type OperatorRoute } from '../route';

export interface RailSection {
  readonly name: string;
  /** Whether this deployment has a screen behind the register at all. */
  readonly carried: boolean;
}

/**
 * The four registers, in the order these systems conventionally list them. Only Permits has a
 * screen in this deployment; the other three are named because naming a capability and leaving
 * it visibly unpopulated is honest, and quietly omitting it is a curated screenshot.
 */
export const RAIL_SECTIONS: readonly RailSection[] = [
  { name: 'Permits', carried: true },
  { name: 'Isolations', carried: false },
  { name: 'Certificates', carried: false },
  { name: 'Register', carried: false },
];

/** What an item that has no screen behind it says about itself. */
export const NOT_CARRIED_NOTE = 'not carried by this deployment';

export interface RailHandle {
  readonly element: HTMLElement;
  /** Moves the `current` marker after a hash change. */
  setRoute(route: OperatorRoute): void;
}

export function createRail(route: OperatorRoute, doc: Document = document): RailHandle {
  const rail = doc.createElement('nav');
  rail.className = 'cw-rail';
  rail.setAttribute('data-cw', 'rail');
  rail.setAttribute('aria-label', 'Registers');

  const heading = doc.createElement('p');
  heading.className = 'cw-rail__heading';
  heading.textContent = 'Registers';
  heading.id = 'cw-rail-heading';

  const list = doc.createElement('ul');
  list.className = 'cw-rail__list';

  const items = new Map<string, HTMLLIElement>();
  for (const section of RAIL_SECTIONS) {
    const item = doc.createElement('li');
    item.className = 'cw-rail__item';
    item.setAttribute('data-cw-section', section.name);

    const name = doc.createElement('span');
    name.className = 'cw-rail__name';
    name.textContent = section.name;
    item.append(name);

    if (!section.carried) {
      const note = doc.createElement('span');
      note.className = 'cw-rail__note';
      note.textContent = NOT_CARRIED_NOTE;
      item.append(note);
      item.setAttribute('data-state', 'absent');
    } else {
      item.setAttribute('data-state', 'available');
    }

    list.append(item);
    items.set(section.name, item);
  }

  const caption = doc.createElement('p');
  caption.className = 'cw-rail__caption';
  caption.textContent =
    'This rail is a list, not a menu. The two modules this deployment carries are switched in ' +
    'the bar above.';

  rail.append(heading, list, caption);

  const setRoute = (next: OperatorRoute): void => {
    const currentSection = moduleFor(next).railSection;
    for (const [name, item] of items) {
      const section = RAIL_SECTIONS.find((entry) => entry.name === name);
      const available = section?.carried === true;
      item.setAttribute(
        'data-state',
        name === currentSection ? 'current' : available ? 'available' : 'absent',
      );
    }
  };

  setRoute(route);

  return { element: rail, setRoute };
}
