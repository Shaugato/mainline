// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * (3) THE WELD — the projected counters, each under the CHECK that reads it.
 *
 * ARCHITECTURE.md §5.5 declares six independently-named refusals on `mainline.permit`
 * plus `merge_evidence`, and says why the six are not one: *the constraint name is the
 * courtroom exhibit, and "the merge was refused by `boundary_certified_when_issued`" is
 * a materially better sentence than "a counter was non-zero."* This panel is that
 * sentence, drawn.
 *
 * Each counter is a PROJECTION (P2 / I02): a trigger wrote it onto the permit row from
 * an authoritative table, never from the inserter, and the CHECK reads the column and
 * nothing else. The console renders the value verbatim with its provenance chip and
 * computes none of them (D5).
 *
 * ── THE THREE STATES, AND WHY THE THIRD EXISTS ───────────────────────────────────
 *
 * A zero counter and a counter that is zero because nothing was computed must not look
 * the same. `model.ts`'s `CounterState` splits them:
 *
 *   `blocking`         non-zero. This constraint is holding the gate shut.
 *   `clear`            zero, AND this screen carries the rows or the certificate that
 *                      say what was examined to arrive at zero.
 *   `unwitnessed-zero` zero, and nothing on this screen establishes what was examined.
 *
 * `unmodelled_asset_count` is the case with a body count behind it. ARCHITECTURE.md
 * §5.5, finding S11: an asset with no modelled energy edges is UNKNOWN, not SAFE — and
 * unknown blocks. With no boundary certificate in the payload, a zero there means nobody
 * counted the unmodelled tags, and the row says so in those words rather than showing a
 * reassuring nought.
 *
 * ── REGISTER ─────────────────────────────────────────────────────────────────────
 *
 * The counters are INSTRUMENT elements (ui.md §1.1): motion is permitted here because
 * the transition IS the fact — `open_blocking` going 1 → 0 is the product working. The
 * `RegisterFrame` declares that on the tree, `Counter` reads it, and the end state is
 * identical whether or not the mark ran. This DIRECTORY is still EVIDENCE and imports
 * no animation library; the register is a property of the instance, which is exactly
 * what a directory rule cannot express.
 */

import { type ReactNode } from 'react';

import { ConstraintName, Counter, Mono, RegisterFrame } from '../../design/primitives';

import styles from './gate.module.css';
import { ProvenanceSlot } from './ProvenanceSlot';
import { pointer, type ProvenanceEntry } from './provenance';
import type { CounterState, WeldCounter, WeldDiagramModel } from './model';
import type { BlockingCheck, Permit } from '../../data/types.generated';

const STATE_WORD: Readonly<Record<CounterState, string>> = Object.freeze({
  blocking: 'blocking',
  clear: 'clear — witnessed',
  'unwitnessed-zero': 'zero — unwitnessed',
});

export interface WeldDiagramProps {
  readonly weld: WeldDiagramModel;
  readonly permit: Permit;
  readonly provenance: readonly ProvenanceEntry[] | undefined;
  /** Open checks, for the witness links. `null` when that read has not landed. */
  readonly checks: readonly BlockingCheck[] | null;
}

function WitnessLinks({
  counter,
  checks,
}: {
  readonly counter: WeldCounter;
  readonly checks: readonly BlockingCheck[] | null;
}): ReactNode {
  if (counter.witnessSource === 'not_carried') {
    return (
      <span className={styles.chipUndeclared} data-testid="witness-not-carried">
        witness rows not carried by this payload
      </span>
    );
  }

  if (counter.witnessSource === 'boundary_certificate') {
    return (
      <a className={styles.witnessLink} href="#gate-boundary-certificate">
        boundary certificate ({counter.witnessCount ?? 0} unmodelled or under-declared tag(s))
      </a>
    );
  }

  const open = (checks ?? []).filter((check) => check.open);
  if (open.length === 0) {
    return <span className={styles.witnessLink}>no open blocking_check rows in this payload</span>;
  }
  return (
    <span className={styles.anchorRow}>
      {open.map((check) => (
        <a className={styles.witnessLink} key={check.check_id} href={`#gate-check-${check.check_id}`}>
          <Mono>{check.check_id}</Mono>
        </a>
      ))}
    </span>
  );
}

function CounterRow({
  counter,
  constraint,
  checks,
  provenance,
}: {
  readonly counter: WeldCounter;
  readonly constraint: string;
  readonly checks: readonly BlockingCheck[] | null;
  readonly provenance: readonly ProvenanceEntry[] | undefined;
}): ReactNode {
  return (
    <div
      className={styles.weldCounter}
      data-counter={counter.column}
      data-counter-state={counter.state}
      data-testid={`weld-counter-${counter.column}`}
    >
      <Counter
        value={counter.value}
        label={`${counter.column}, read by ${constraint}`}
        data-testid={`counter-${counter.column}`}
      />
      <span className={styles.weldState}>{STATE_WORD[counter.state]}</span>
      <ProvenanceSlot provenance={provenance} pointer={pointer('counters', counter.column)} />
      <WitnessLinks counter={counter} checks={checks} />
      {counter.unknownBlocks ? (
        <p className={styles.unknownBlocks} data-testid="unknown-blocks">
          <strong>UNKNOWN BLOCKS — NOT SAFE.</strong> This payload carries no boundary certificate,
          so nothing here establishes how many declared or adjacent asset tags have no modelled
          energy edges at all. ARCHITECTURE.md §5.5 (S11): an asset with no modelled energy edges is
          unknown, not safe, and unknown blocks. A zero shown without a certificate behind it is an
          absence of counting, not a clear result.
        </p>
      ) : null}
    </div>
  );
}

export function WeldDiagram({ weld, permit, provenance, checks }: WeldDiagramProps): ReactNode {
  const certificate = permit.boundary_certificate ?? null;

  return (
    <RegisterFrame
      register="instrument"
      as="section"
      label="The weld — projected counters and the CHECK that reads each"
      data-testid="weld"
    >
      <p className={styles.panelNote}>
        Every number below is a column a trigger wrote onto <Mono>mainline.permit</Mono> from an
        authoritative table — never from a writer, and never from this console (P2 / I02). The
        constraint beside it is the CHECK that reads that column and nothing else.
      </p>

      {weld.empty ? (
        <div className={styles.absent} data-testid="weld-empty">
          <span className={styles.absentTitle}>no constraints in this payload</span>
          <p className={styles.prose}>
            The permit payload declares no gate constraints. ARCHITECTURE.md §5.5 declares six named
            refusals plus <Mono>merge_evidence</Mono> on <Mono>mainline.permit</Mono>; a payload
            carrying none of them establishes nothing about the gate, and the console renders the
            absence rather than an empty diagram.
          </p>
        </div>
      ) : (
        <div className={styles.weld}>
          {weld.rows.map((row) => (
            <div
              className={styles.weldRow}
              key={row.constraint}
              data-constraint={row.constraint}
              data-blamed={row.blamedByRefusal ? 'true' : 'false'}
              data-testid={`weld-row-${row.constraint}`}
            >
              <div>
                <ConstraintName
                  name={row.constraint}
                  tone={row.blamedByRefusal ? 'refuse' : 'neutral'}
                />
                {row.blamedByRefusal ? (
                  <span className={styles.refusalKicker}> — named by the refusal</span>
                ) : null}
                {row.predicate === null ? (
                  <p className={styles.weldPredicate}>
                    predicate not captured by the read API — the constraint name stands alone rather
                    than being reconstructed
                  </p>
                ) : (
                  <pre className={styles.weldPredicate}>{row.predicate}</pre>
                )}
              </div>

              <div className={styles.weldCounters}>
                {row.counters.length === 0 ? (
                  <span className={styles.witnessLink} data-testid="weld-no-counter">
                    reads no projected counter — <Mono>merged_commit</Mono> is{' '}
                    <Mono>{permit.merged_commit ?? 'NULL'}</Mono>
                  </span>
                ) : (
                  row.counters.map((counter) => (
                    <CounterRow
                      key={counter.column}
                      counter={counter}
                      constraint={row.constraint}
                      checks={checks}
                      provenance={provenance}
                    />
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {weld.unreadColumns.length === 0 ? null : (
        <div className={styles.absent} data-testid="weld-unread">
          <span className={styles.absentTitle}>projected columns no constraint here reads</span>
          <p className={styles.prose}>
            {weld.unreadColumns.join(', ')} — present on the permit row and not named by any
            constraint in this payload. That may be correct (<Mono>countersigned_count</Mono> is
            read jointly with <Mono>unmet_floor_count</Mono>) or it may be a missing constraint; the
            console reports it either way rather than dropping the column.
          </p>
        </div>
      )}

      <div id="gate-boundary-certificate" data-testid="boundary-certificate">
        {certificate === null ? (
          <div className={styles.absent}>
            <span className={styles.absentTitle}>no boundary certificate</span>
            <p className={styles.prose}>
              <Mono>mainline.boundary_certificate</Mono> holds no row for this permit in this
              payload, so <Mono>unmodelled_asset_count</Mono> has nothing behind it on this screen.
            </p>
          </div>
        ) : (
          <div className={styles.facts}>
            <span className={styles.fact}>
              <span className={styles.label}>asset_graph_version</span>
              <Mono>{certificate.asset_graph_version}</Mono>
            </span>
            <span className={styles.fact}>
              <span className={styles.label}>tags_declared</span>
              <Mono>{certificate.tags_declared}</Mono>
            </span>
            <span className={styles.fact}>
              <span className={styles.label}>tags_resolved</span>
              <Mono>{certificate.tags_resolved}</Mono>
            </span>
            <span className={styles.fact}>
              <span className={styles.label}>tags_unmodelled</span>
              <Mono>{certificate.tags_unmodelled}</Mono>
            </span>
            <span className={styles.fact}>
              <span className={styles.label}>under_declared</span>
              <Mono>{certificate.under_declared}</Mono>
            </span>
            <span className={styles.fact}>
              <span className={styles.label}>computed_at</span>
              <Mono>{certificate.computed_at}</Mono>
            </span>
          </div>
        )}
      </div>
    </RegisterFrame>
  );
}
