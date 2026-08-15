// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Resolves one registry entry into something rendered.
 *
 * Four outcomes, and every one of them paints:
 *
 *   1. `declared-missing` → NOT-BUILT-YET naming the milestone that owes it.
 *   2. the dynamic import rejects → NOT-BUILT-YET carrying the import error verbatim.
 *   3. the module loads but its descriptor is malformed → NOT-BUILT-YET carrying the
 *      validation reason, because a module that lies about itself is not a surface.
 *   4. the module is valid → the surface, inside its own error boundary.
 *
 * There is no fifth outcome. A blank pane is not an outcome this component can produce.
 *
 * ── THE ON-RAMP (2026-08-15) ─────────────────────────────────────────────────────
 *
 * All four outcomes are now introduced by a plain-language lede, mounted HERE and drawn
 * from `src/copy/onramp.ts`. `docs/leads/screens-work-plan.md` §2.10 rules that the
 * on-ramp is **chrome, not feature copy**, and this component is the reason that ruling is
 * enforceable rather than aspirational: it is the one place every surface passes through,
 * so seven screens gain an introduction without a single file under `src/features/` being
 * opened. Not one existing sentence moved, shortened or softened; what changed is only
 * what a reader meets FIRST.
 *
 * ── WHAT THE DISCLOSURE REVEALS, AND WHY IT IS THE PROMISE ───────────────────────
 *
 * Beneath the lede is a disclosure, closed on first visit, whose body is
 * `entry.promise` — the precise, specialist sentence the console's own promise list
 * (`src/app/surfaces.ts`) already carries for this screen, rendered verbatim from the
 * registry entry. It is not authored here, not paraphrased here and not summarised here;
 * this component cannot alter it, because it never holds a copy of it.
 *
 * The alternative that was considered and REJECTED, recorded so nobody re-proposes it:
 * collapsing the feature's OWN opening paragraph in place, by reaching from this chrome
 * into the mounted surface with a structural CSS selector. It would have hidden the
 * specialist paragraph until the click rather than merely demoting it — and it would have
 * meant chrome suppressing evidence it cannot identify, keyed on markup owned by five
 * other workers, on screens where hiding the wrong element means hiding a finding. A
 * console whose on-ramp can accidentally suppress a refusal is a worse console than one
 * whose precise sentence sits a screen-length lower. So the feature's paragraph stays
 * exactly where it is, visible and unedited, and the promise is what the click reveals.
 *
 * ── WHY THE DECK IS A LAZY IMPORT ────────────────────────────────────────────────
 *
 * Measured on the demo-mode build of 2026-08-15, gzipped at level 9 with the deploy's own
 * settings (`scripts/deploy/build_lambda.sh::gzip_bytes`): the entry chunk was 135,339 B
 * against `static_site.DEFAULT_MAX_RESPONSE_BYTES` of 139,264 — **3,925 B of headroom for
 * the whole console**, and a response over that ceiling is a **413**, not a slow page. Ten
 * screens' worth of prose does not go on that critical path: carried eagerly the deck cost
 * the entry 4,629 B (1,507 B gzipped), and this whole change now costs it 780 B gzipped,
 * leaving 3,145 B. It is imported in the same effect as the surface, so the lede and the
 * screen arrive together, and its failure is survivable: no deck, no lede, the surface
 * unchanged.
 */

import { useEffect, useState, type ReactNode } from 'react';

// `import type`, not an inline `{ type … }`. `tsconfig.json` sets `verbatimModuleSyntax`,
// under which the inline form leaves a bare `import '../copy/onramp'` behind — a static
// import of the module this file also imports dynamically, which put all ten ledes back in
// the entry chunk and cost 4,629 B on a budget with 3,925 B of headroom in it. Measured
// twice: `onramp-*.js` appears as its own chunk in the build output, or it does not.
import type { SurfaceLede } from '../copy/onramp';
import onramp from '../copy/onramp.module.css';

import { ErrorBoundary } from './ErrorBoundary';
import { NotBuiltYet } from './NotBuiltYet';
import styles from './shell.module.css';
import { validateSurfaceModule, type SurfaceDescriptor, type SurfaceEntry } from './surfaces';

type Resolution =
  | { readonly kind: 'loading' }
  | { readonly kind: 'ready'; readonly descriptor: SurfaceDescriptor }
  | { readonly kind: 'absent'; readonly reason: string };

function describeImportFailure(entry: SurfaceEntry, error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const stack = error instanceof Error && error.stack !== undefined ? `\n\n${error.stack}` : '';
  return (
    `Importing src/features/${entry.id}/surface.tsx failed.\n\n${message}${stack}\n\n` +
    `The module exists but did not evaluate. This is a build-time or module-graph fault in the ` +
    `${entry.owner} surface, not a refusal by the database — nothing here is a claim about any record.`
  );
}

// ── The disclosure's own chrome ────────────────────────────────────────────

/*
 * These three live HERE and not in the copy deck, and the reason is 4,629 bytes.
 *
 * The first build of this change imported them statically from `src/copy/onramp.ts` while
 * importing the deck lazily from the same path. Rollup, correctly, put the whole module in
 * the entry chunk — a lazy import of a module you also import eagerly is not lazy — and the
 * entry carried ten screens' worth of prose that nothing needs before the first paint:
 * 488,581 B against 483,952 B once the eager edge was cut, which is 1,507 B of gzip off a
 * budget that had 3,925 B in it. Only the TYPE crosses that boundary now, and a type is
 * erased at build.
 */

/**
 * The disclosure's label, in both states.
 *
 * It says what is behind it rather than inviting a click: a reader who does not want the
 * precise version should be able to decide that from the label alone.
 */
export const DISCLOSURE_SUMMARY = 'The precise version of this screen, in one sentence';

/**
 * What the disclosure says about the sentence it reveals.
 *
 * The sentence itself is `SurfaceEntry.promise`, quoted from the console's promise list —
 * so the precise reading is not authored here, cannot drift from the list, and cannot be
 * "improved" by a copy change. This note is its provenance, and it is also the commitment
 * this wave made to the screens below.
 */
export const DISCLOSURE_NOTE =
  'Quoted from the console’s own promise list (src/app/surfaces.ts), unchanged. The screen ' +
  'below states the same subject in its own words and at its own precision: nothing on it ' +
  'was shortened, softened or rewritten to make room for the plain-language note above it.';

/** Where the reader's choice is remembered, for this tab, for this session. */
export const DISCLOSURE_STORAGE_KEY = 'mainline.onramp.precise';

// ── The reader's choice ────────────────────────────────────────────────────

/**
 * Remembered for the SESSION, not for ever.
 *
 * `sessionStorage`, so a technical reader opens the precise version once and keeps it open
 * across every screen they click, and a laptop handed to the next person opens plain
 * again. Both reads are wrapped: storage throws outright in a partitioned or
 * storage-disabled context, and an on-ramp that can take the console down is worse than an
 * on-ramp that forgets.
 */
function readDisclosurePreference(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.sessionStorage.getItem(DISCLOSURE_STORAGE_KEY) === 'open';
  } catch {
    return false;
  }
}

function writeDisclosurePreference(open: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(DISCLOSURE_STORAGE_KEY, open ? 'open' : 'closed');
  } catch {
    // A reader whose browser refuses storage still gets the disclosure; it just does not
    // travel with them. Nothing on screen is a claim about a record, so nothing is lost.
  }
}

/**
 * The lede, and the precise version one line under it.
 *
 * `entry.promise` is rendered verbatim. Every entry in `DECLARED_SURFACES` carries one and
 * `buildRegistry` supplies a truthful sentence for an undeclared stranger, so there is no
 * branch here for a promise that is missing — there is no such entry.
 */
function OnRamp({ entry, lede }: { readonly entry: SurfaceEntry; readonly lede: SurfaceLede }): ReactNode {
  const [open, setOpen] = useState<boolean>(readDisclosurePreference);

  return (
    <aside
      className={onramp.onramp}
      aria-label={`What this screen is for — ${entry.title}`}
      data-testid="onramp"
      data-onramp-surface={entry.id}
    >
      <p className={onramp.kicker} data-testid="onramp-kicker">
        {lede.kicker}
      </p>
      {lede.sentences.map((sentence) => (
        <p className={onramp.lede} key={sentence} data-testid="onramp-lede">
          {sentence}
        </p>
      ))}
      <details
        className={onramp.details}
        open={open}
        data-testid="onramp-disclosure"
        onToggle={(event) => {
          const next = event.currentTarget.open;
          setOpen(next);
          writeDisclosurePreference(next);
        }}
      >
        <summary className={onramp.summary} data-testid="onramp-disclosure-summary">
          {DISCLOSURE_SUMMARY}
        </summary>
        <div className={onramp.preciseBody}>
          <p className={onramp.promise} data-testid="onramp-promise">
            {entry.promise}
          </p>
          <p className={onramp.provenance}>{DISCLOSURE_NOTE}</p>
        </div>
      </details>
    </aside>
  );
}

export function SurfaceHost({ entry }: { readonly entry: SurfaceEntry }): ReactNode {
  const [resolution, setResolution] = useState<Resolution>(() =>
    entry.load === null
      ? {
          kind: 'absent',
          reason:
            `No module at src/features/${entry.id}/surface.tsx.\n\n` +
            `The surface is declared in the console's promise list but has not been built, or its ` +
            `directory has been removed by the scope-cut ladder (BUILD_PLAN §10.2).`,
        }
      : { kind: 'loading' },
  );

  /**
   * `null` until the deck lands, and `null` for ever if it does not.
   *
   * The lede is an introduction, not a claim about a record, so its absence costs a reader
   * an on-ramp and costs the screen below nothing at all.
   */
  const [lede, setLede] = useState<SurfaceLede | null>(null);

  useEffect(() => {
    let live = true;
    import('../copy/onramp').then(
      (deck) => {
        if (live) setLede(deck.ledeFor(entry.id));
      },
      () => {
        // Deliberately silent, and deliberately not a NOT-BUILT-YET card: a copy deck that
        // failed to load is not a surface that failed to load, and saying so on the screen
        // would put a console defect where a reader is looking for a database's answer.
      },
    );
    return () => {
      live = false;
    };
  }, [entry.id]);

  useEffect(() => {
    const load = entry.load;
    if (load === null) {
      setResolution({
        kind: 'absent',
        reason:
          `No module at src/features/${entry.id}/surface.tsx.\n\n` +
          `The surface is declared in the console's promise list but has not been built, or its ` +
          `directory has been removed by the scope-cut ladder (BUILD_PLAN §10.2).`,
      });
      return undefined;
    }

    let live = true;
    setResolution({ kind: 'loading' });

    load().then(
      (mod) => {
        if (!live) return;
        const validation = validateSurfaceModule(entry.id, mod);
        setResolution(
          validation.ok
            ? { kind: 'ready', descriptor: validation.descriptor }
            : { kind: 'absent', reason: validation.reason },
        );
      },
      (error: unknown) => {
        if (!live) return;
        setResolution({ kind: 'absent', reason: describeImportFailure(entry, error) });
      },
    );

    return () => {
      live = false;
    };
  }, [entry]);

  const introduction = lede === null ? null : <OnRamp entry={entry} lede={lede} />;

  if (resolution.kind === 'absent') {
    return (
      <>
        {introduction}
        <NotBuiltYet entry={entry} reason={resolution.reason} />
      </>
    );
  }

  if (resolution.kind === 'loading') {
    return (
      <>
        {introduction}
        <p className={styles.loading} data-testid="surface-loading" role="status">
          Loading {entry.title}…
        </p>
      </>
    );
  }

  const { Component } = resolution.descriptor;
  return (
    <>
      {introduction}
      <ErrorBoundary boundary={`surface:${entry.id}`}>
        <div className={styles.surface} data-surface={entry.id} data-register={entry.register}>
          <Component />
        </div>
      </ErrorBoundary>
    </>
  );
}
