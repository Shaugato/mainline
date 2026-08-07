// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The error boundary that never swallows a message.
 *
 * "Something went wrong. Please try again." is the standard React boundary, and in this
 * product it is a lie of exactly the kind the whole console exists to refuse: it
 * replaces a specific claim the system made with a generic one the UI composed.
 *
 * Two paths, and no third:
 *
 *   • The thrown value carries a REFUSAL payload → render the constraint name, the
 *     SQLSTATE and the database's message VERBATIM (D18, I14). The console does not
 *     rephrase a refusal; a prettified refusal is a different refusal.
 *   • Anything else → render the error's own `name`, `message` and stack, verbatim,
 *     plus the component stack React gives us. An engineer reading a screenshot must
 *     be able to act on it without asking for the console log.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react';

import { isModelledSqlstate, refusalFrom } from './refusal';
import styles from './shell.module.css';

/**
 * Something was thrown that is not an Error. Show it as faithfully as JSON allows and
 * say what it was, rather than printing `[object Object]` and losing the only evidence
 * of what actually happened.
 */
function stringifyUnknown(value: unknown): string {
  if (typeof value === 'string') return value;
  try {
    return `${typeof value}: ${JSON.stringify(value, null, 2)}`;
  } catch {
    return `${typeof value}: (not serialisable)`;
  }
}

interface Props {
  /** Named so the reader knows WHICH part of the console failed. */
  readonly boundary: string;
  readonly children: ReactNode;
}

interface State {
  readonly error: unknown;
  readonly componentStack: string | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null, componentStack: null };

  static getDerivedStateFromError(error: unknown): Partial<State> {
    return { error };
  }

  override componentDidCatch(error: unknown, info: ErrorInfo): void {
    this.setState({ componentStack: info.componentStack ?? null });
    // Re-emit to the browser console as well. The screen is one audience; the person
    // running the browser spec with a devtools protocol attached is another, and a
    // boundary that only paints is invisible to them.
    console.error(`[MAINLINE console] boundary "${this.props.boundary}" caught:`, error);
  }

  override render(): ReactNode {
    const { error, componentStack } = this.state;
    if (error === null) return this.props.children;

    const refusal = refusalFrom(error);

    if (refusal !== null) {
      const modelled = isModelledSqlstate(refusal.sqlstate);
      return (
        <section className={styles.failure} role="alert" data-failure="refusal">
          <h2 className={styles.failureTitle}>
            <span className={styles.sqlstate} data-sqlstate={refusal.sqlstate}>
              {refusal.sqlstate}
            </span>{' '}
            <span className={styles.constraint}>{refusal.constraint}</span>
          </h2>
          <pre className={styles.verbatim}>{refusal.message}</pre>
          <dl className={styles.failureMeta}>
            <dt>constraint source</dt>
            <dd>
              {refusal.constraint_source ?? 'reported'}
              {refusal.constraint_source === 'parsed'
                ? ' — recovered from the message text, which is a WEAKENED diagnosis'
                : ''}
            </dd>
            {refusal.subject_kind !== undefined && (
              <>
                <dt>subject</dt>
                <dd>
                  {refusal.subject_kind} {refusal.subject_id ?? ''}
                </dd>
              </>
            )}
            {refusal.gate_epoch !== undefined && (
              <>
                <dt>gate epoch</dt>
                <dd>{refusal.gate_epoch}</dd>
              </>
            )}
            {!modelled && (
              <>
                <dt>taxonomy</dt>
                <dd>
                  SQLSTATE {refusal.sqlstate} is outside the closed REFUSE set of
                  spec/errors.md §1. That is a defect, not an edge case: the database refused for a
                  reason nobody modelled.
                </dd>
              </>
            )}
          </dl>
        </section>
      );
    }

    const name = error instanceof Error ? error.name : typeof error;
    const message = error instanceof Error ? error.message : stringifyUnknown(error);
    const stack = error instanceof Error ? (error.stack ?? null) : null;

    return (
      <section className={styles.failure} role="alert" data-failure="exception">
        <h2 className={styles.failureTitle}>
          <span className={styles.constraint}>{name}</span> in boundary “{this.props.boundary}”
        </h2>
        <pre className={styles.verbatim}>{message}</pre>
        {stack !== null && (
          <details className={styles.details}>
            <summary>stack</summary>
            <pre className={styles.verbatim}>{stack}</pre>
          </details>
        )}
        {componentStack !== null && (
          <details className={styles.details}>
            <summary>component stack</summary>
            <pre className={styles.verbatim}>{componentStack}</pre>
          </details>
        )}
        <p className={styles.failureNote}>
          This is the console failing, not the database refusing. Nothing above is a claim about
          any record.
        </p>
      </section>
    );
  }
}
