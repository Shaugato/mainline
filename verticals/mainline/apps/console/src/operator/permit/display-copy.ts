// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE DISPLAY COPY AFFORDANCE — HSG250 ¶18 and ¶51 bullet four.
 *
 * ¶18 makes display at the worksite a requirement of the system, not a nicety, and ¶51's
 * fourth bullet requires of any ELECTRONIC permit system that *the facility exists for paper
 * permits to be produced for display at the job site*. So a control-of-work product without
 * a print control is not a control-of-work product. r3-operator §9 lists it among the five
 * cheapest fidelity wins available: *"None costs more than a few lines and each is a thing a
 * fake screen normally gets wrong."*
 *
 * This is a REAL affordance. It calls the browser's own print, which renders the real DOM
 * through `print.css`. Nothing is generated, staged or substituted for printing: what comes
 * out of the printer is the screen a judge is looking at, including its provenance chips,
 * its unsigned rows and its `not carried by this deployment` labels. A print view that
 * quietly tidied those away would be a second, prettier document making claims the first one
 * does not — which is the whole class of act this repository exists to refuse.
 *
 * HSG250 is quoted by PARAGRAPH NUMBER and never reproduced. R13: no verbatim standard text
 * is presented as this product's own.
 */

import './print.css';

import { el } from './typed-fields';

export interface DisplayCopyOptions {
  /**
   * The window whose `print()` is called. Defaults to the document's own view.
   * Injectable so a test can assert the control calls print without opening a dialog.
   */
  readonly view?: Pick<Window, 'print'> | null;
}

export interface DisplayCopyControl {
  readonly root: HTMLElement;
  readonly button: HTMLButtonElement;
}

/**
 * The display-copy control: a button, its citation, and nothing else.
 */
export function renderDisplayCopy(options: DisplayCopyOptions = {}): DisplayCopyControl {
  const root = el('div', 'cow-display-copy');

  const button = el('button', 'cow-button cow-button-quiet');
  button.type = 'button';
  button.textContent = 'Display copy ⎙';
  button.title = 'Produce a paper copy for display at the work site (HSE HSG250 ¶18, ¶51)';
  button.setAttribute('data-action', 'display-copy');
  button.addEventListener('click', () => {
    const view = options.view === undefined ? root.ownerDocument.defaultView : options.view;
    view?.print();
  });
  root.appendChild(button);

  root.appendChild(
    el('span', 'cow-hint', 'HSE HSG250 ¶18 · ¶51 — display at the work site'),
  );
  return { root, button };
}
