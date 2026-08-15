// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ON-RAMP INSIDE THE PANEL — three pieces, and none of them removes anything.
 *
 * `docs/leads/two-audience-ux-plan.md` R6 rules that every screen opens with sentences a
 * site supervisor can read and that every exact thing already on it is one deliberate,
 * permanent click away. The shell mounts the first half of that (`src/app/SurfaceHost.tsx`
 * renders the lede from `src/copy/onramp.ts` above every surface). This module is the
 * second half, for the one panel that is ALSO embedded in the gate screen and therefore
 * cannot rely on chrome it does not control.
 *
 * Three components, and the constraints on each are the ruling, not a preference:
 *
 *   `PlainBand`  — two or three sentences at the top of the panel. No SQLSTATE, no RFC, no
 *                  term the reader has not been given. It introduces; it never summarises a
 *                  value below it, because a summary of a digest is a worse digest.
 *   `Disclosure` — a `<details>` that COLLAPSES and never removes. Its summary says what is
 *                  behind it in the reader's own words ("Show the exact wording…"), never
 *                  "Details". R6 permits collapsing digests, hash tables, witness tables,
 *                  canonicalisation detail and JSON pointers; it forbids collapsing a
 *                  refusal, a provenance chip, a STAGED badge or a stated absence, and this
 *                  panel keeps every one of those in the open flow.
 *   `Gloss`      — one sentence BESIDE a verbatim value, never inside it (R8). It is its own
 *                  element in the sans face so that no reader and no `sha256sum` can mistake
 *                  console prose for a string the database emitted.
 *
 * ── WHY THIS FILE IS NOT SHARED WITH `features/evidence/` ────────────────────────
 *
 * The evidence screen carries a near-identical trio. They are deliberately not one module.
 * Each is styled entirely by its own feature's CSS Module — a shared component would have
 * to take class names as props, which is the coupling without the reuse — and a feature
 * importing another feature's scoped stylesheet couples it to a class name nobody promised
 * to keep. The same reasoning `diff.module.css` already records for `.visuallyHidden`.
 *
 * ── WHERE THE GLOSS SENTENCES COME FROM ──────────────────────────────────────────
 *
 * They are quoted from the lead's R7 vocabulary table where R7 defines the term, and
 * written against a field of the payload where it does not. R7 places the eventual single
 * source at `src/design/glossary.ts`, which is another worker's file and does not exist
 * yet; when it lands these become imports, and the sentences already match so that the
 * change is an import and not a rewrite.
 */

import { type ReactNode } from 'react';

import styles from '../diff.module.css';

/**
 * The plain opening. Rendered inside the panel, above everything the panel computed.
 *
 * `aside`, not `section`: it is an introduction to the evidence, not evidence, and a
 * screen reader that lands on it should be told which of the two it is.
 */
export function PlainBand({
  children,
  label,
}: {
  readonly children: ReactNode;
  readonly label: string;
}): ReactNode {
  return (
    <aside className={styles.plainBand} aria-label={label} data-testid="diff-plain-band">
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
 * Closed on arrival and opened by one click or one keypress; the contents are in the DOM in
 * both states, so `Ctrl-F`, a screen reader's element list and a `document.body.innerText`
 * dump all still find them. That property is what makes "one click away" a true statement
 * about the bytes rather than about the pixels.
 *
 * There is no `open` prop and no persistence: the reader's choice is per-disclosure and
 * per-visit. `src/app/SurfaceHost.tsx` remembers the CHROME disclosure for the session; a
 * panel that also remembered eight of its own would produce a screen nobody can reproduce
 * from a link, and D7 says a screenshot must be reproducible from its URL.
 */
export function Disclosure({ summary, children, testId }: DisclosureProps): ReactNode {
  return (
    <details className={styles.disclosure} data-testid={testId}>
      <summary className={styles.disclosureSummary}>{summary}</summary>
      <div className={styles.disclosureBody}>{children}</div>
    </details>
  );
}

/**
 * One plain sentence beside a term the screen uses exactly (R8).
 *
 * Beside, never inside: the verbatim value stays in its own element in the mono face and
 * this sits next to it in the sans face at a smaller step. A gloss that shared an element
 * with the value would be text a reader could copy out of the console believing the
 * database wrote it.
 */
export function Gloss({ children }: { readonly children: ReactNode }): ReactNode {
  return (
    <span className={styles.gloss} data-testid="diff-gloss">
      {children}
    </span>
  );
}
