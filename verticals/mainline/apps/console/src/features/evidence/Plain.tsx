// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ON-RAMP INSIDE THE EVIDENCE SCREEN — three pieces, and none of them removes anything.
 *
 * `docs/leads/two-audience-ux-plan.md` R6: every screen opens with sentences a site
 * supervisor can read, and every exact thing already on it is one deliberate, permanent
 * click away. The shell mounts the lede above this surface (`src/app/SurfaceHost.tsx` from
 * `src/copy/onramp.ts`); this module is what the surface itself adds beneath it.
 *
 *   `PlainBand`  — what a bundle IS, in words a reader who has never met one can use.
 *   `Disclosure` — a `<details>` that COLLAPSES and never removes. Its summary names what is
 *                  inside it in the reader's words, never "Details". R6 permits collapsing
 *                  digests, hash tables and inventories; it forbids collapsing a seal, a
 *                  finding, a provenance chip, a STAGED badge or a stated absence, and this
 *                  screen collapses none of those.
 *   `Gloss`      — one sentence BESIDE a verbatim value, never inside it (R8), in its own
 *                  element in the sans face, so nothing a reader copies out of this screen
 *                  can be mistaken for something the manifest declared.
 *
 * ── WHY THIS IS NOT SHARED WITH `features/diff/` ─────────────────────────────────
 *
 * The clause-diff panel carries a near-identical trio and they are deliberately not one
 * module: each is styled entirely by its own feature's CSS Module, so a shared component
 * would have to take class names as props — the coupling without the reuse — and a feature
 * that imports another feature's scoped stylesheet is coupled to a class name nobody
 * promised to keep.
 *
 * ── A WORD ON WHAT THESE SENTENCES MAY CLAIM ─────────────────────────────────────
 *
 * Everything written through these components is console prose, and R7's test applies to
 * every sentence of it: *can I point at the field it came from?* The band below points at
 * `manifest.files[].sha256`, at the recomputation this browser performs in
 * `audit.ts`, and at nothing else. In particular it does not say the bundle is *signed*:
 * this build ships an empty `VITE_MAINLINE_LOG_VKEY`, no signature is checked on this
 * screen, and a plain-language sentence is not the place to acquire a claim the machinery
 * does not make.
 */

import { type ReactNode } from 'react';

import styles from './evidence.module.css';

/**
 * The plain opening, above the audit and below the shell's lede.
 *
 * `aside`, not `section`: it introduces the evidence and is not itself evidence, and a
 * reader arriving by screen reader should be told which of the two they have landed on.
 */
export function PlainBand({
  children,
  label,
}: {
  readonly children: ReactNode;
  readonly label: string;
}): ReactNode {
  return (
    <aside className={styles.plainBand} aria-label={label} data-testid="evidence-plain-band">
      {children}
    </aside>
  );
}

export interface DisclosureProps {
  /** What is behind it, in the reader's words. Never "Details". */
  readonly summary: string;
  readonly children: ReactNode;
  readonly testId: string;
}

/**
 * Collapsed, never removed.
 *
 * The contents are in the DOM in both states, so `Ctrl-F`, a screen reader's element list
 * and a text dump of the page all still find them; "one click away" is therefore a claim
 * about the bytes rather than about the pixels. No `open` prop and no persistence — D7 says
 * a screenshot must be reproducible from its URL, and eight remembered toggles would make
 * that false.
 */
export function Disclosure({ summary, children, testId }: DisclosureProps): ReactNode {
  return (
    <details className={styles.disclosure} data-testid={testId}>
      <summary className={styles.disclosureSummary}>{summary}</summary>
      <div className={styles.disclosureBody}>{children}</div>
    </details>
  );
}

/** One plain sentence beside a term this screen uses exactly (R8). Beside, never inside. */
export function Gloss({ children }: { readonly children: ReactNode }): ReactNode {
  return (
    <span className={styles.gloss} data-testid="evidence-gloss">
      {children}
    </span>
  );
}
