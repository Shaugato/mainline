// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE APP BAR — `CONTROL OF WORK`, and the module you are in.
 *
 * "Control of work" is the industry's own generic name for this software category, so the
 * product imitates nobody: no logo, no employer name, no form number, no vendor mark
 * (operator-systems-plan.md R13). MAINLINE is not named here and must not be. You see MAINLINE
 * by seeing what it stops.
 *
 * The two module links are REAL navigation — plain `<a href="#/...">`, which is what makes the
 * back button work and what makes the URL of a captured frame reproducible. They are the only
 * interactive elements in the chrome; the left rail is deliberately not (see Rail.ts).
 */

import { MODULES, moduleFor, type OperatorRoute } from '../route';

/** The product name, in the bar, verbatim. */
export const PRODUCT_NAME = 'CONTROL OF WORK';

export interface AppBarHandle {
  readonly element: HTMLElement;
  /** Repoints the module name and the `aria-current` link after a hash change. */
  setRoute(route: OperatorRoute): void;
}

export function createAppBar(route: OperatorRoute, doc: Document = document): AppBarHandle {
  const bar = doc.createElement('header');
  bar.className = 'cw-appbar';
  bar.setAttribute('data-cw', 'appbar');

  const product = doc.createElement('span');
  product.className = 'cw-appbar__product';
  product.setAttribute('data-cw', 'product-name');
  product.textContent = PRODUCT_NAME;

  const divider = doc.createElement('span');
  divider.className = 'cw-appbar__divider';
  // Decoration with no text: name it as such rather than leaving a screen reader to
  // announce an empty element it cannot explain.
  divider.setAttribute('aria-hidden', 'true');

  const moduleName = doc.createElement('span');
  moduleName.className = 'cw-appbar__module';
  moduleName.setAttribute('data-cw', 'module-name');

  const nav = doc.createElement('nav');
  nav.className = 'cw-appbar__nav';
  nav.setAttribute('aria-label', 'Modules');

  const links = new Map<OperatorRoute, HTMLAnchorElement>();
  for (const descriptor of MODULES) {
    const link = doc.createElement('a');
    link.className = 'cw-appbar__link';
    link.href = descriptor.hash;
    link.textContent = descriptor.name;
    link.setAttribute('data-cw-route', descriptor.route);
    nav.append(link);
    links.set(descriptor.route, link);
  }

  bar.append(product, divider, moduleName, nav);

  const setRoute = (next: OperatorRoute): void => {
    moduleName.textContent = moduleFor(next).name;
    for (const [candidate, link] of links) {
      if (candidate === next) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  };

  setRoute(route);

  return { element: bar, setRoute };
}
