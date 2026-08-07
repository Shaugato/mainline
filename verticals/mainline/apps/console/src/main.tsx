// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The entry point. Its whole job is to mount the shell and to make a failure to mount
 * legible, because the failure mode of a single-page application is a white rectangle.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './app/App';
import './app/tokens-fallback.css';

/*
 * The register token set is owned by the visual-language worker (`src/design/`). It is
 * imported here through a glob rather than a direct import so that:
 *
 *   • the shell builds before that worker has landed anything, and
 *   • the cut ladder can delete `src/design/` without breaking the entry point.
 *
 * A glob that matches nothing evaluates to `{}`. `*.module.css` is excluded because
 * those are scoped stylesheets belonging to components, not global tokens.
 */
import.meta.glob(['/src/design/**/*.css', '!/src/design/**/*.module.css'], { eager: true });

function fail(reason: string): never {
  const notice = document.createElement('pre');
  notice.setAttribute('data-testid', 'mount-failure');
  notice.style.padding = '2rem 1.5rem';
  notice.style.whiteSpace = 'pre-wrap';
  notice.textContent = `MAINLINE console failed to mount.\n\n${reason}`;
  document.body.append(notice);
  throw new Error(reason);
}

const container = document.getElementById('root');
if (container === null) {
  fail('index.html has no #root element. The document shell and the bundle disagree.');
}

// Remove the pre-boot notice only once we are certain React is about to render. If any
// line above threw, the reader keeps the sentence in index.html instead of a void.
document.getElementById('boot-notice')?.remove();

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
