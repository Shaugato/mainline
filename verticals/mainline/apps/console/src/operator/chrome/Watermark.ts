// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PERMANENT SYNTHETIC WATERMARK — operator-systems-plan.md R13.
 *
 * This surface is deliberately indistinguishable, in shape and in vocabulary, from the
 * software a site supervisor already has open. That is what makes the demonstration land, and
 * it is exactly why it must say what it is, permanently, on every screen and in every frame of
 * any capture — including a screenshot somebody crops.
 *
 * The wording matches the seed's own `SYNTHETIC —` prefixes, which stay visible in the data
 * rather than being stripped for the camera. The same sentence is already in `operator.html`'s
 * boot notice and noscript block, so it is true before any script runs.
 *
 * It is a `<p>` inside a landmark-free strip and not an `aria-hidden` decoration: a caption a
 * screen reader cannot reach is a caption that is not on the page for everybody.
 */

/** The exact sentence. Asserted verbatim by tests/unit/operator/shell/chrome.test.ts. */
export const WATERMARK_TEXT =
  'SYNTHETIC DEMONSTRATION — no real site, no real permit, no real person';

export function createWatermark(doc: Document = document): HTMLElement {
  const strip = doc.createElement('div');
  strip.className = 'cw-watermark';
  strip.setAttribute('role', 'note');
  strip.setAttribute('data-cw', 'watermark');

  const line = doc.createElement('p');
  line.style.margin = '0';
  line.textContent = WATERMARK_TEXT;
  strip.append(line);

  return strip;
}
