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
 */

import { useEffect, useState, type ReactNode } from 'react';

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

  if (resolution.kind === 'absent') {
    return <NotBuiltYet entry={entry} reason={resolution.reason} />;
  }

  if (resolution.kind === 'loading') {
    return (
      <p className={styles.loading} data-testid="surface-loading" role="status">
        Loading {entry.title}…
      </p>
    );
  }

  const { Component } = resolution.descriptor;
  return (
    <ErrorBoundary boundary={`surface:${entry.id}`}>
      <div className={styles.surface} data-surface={entry.id} data-register={entry.register}>
        <Component />
      </div>
    </ErrorBoundary>
  );
}
