// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * (2) THE IRREDUCIBLE REASON SET, and beside it the nearest admissible alternative.
 *
 * `mus` is the minimal unsatisfiable subset: *remove any one element and the transition
 * would have been admissible; remove none and it would not*
 * (`spec/wire/refusal.md` §3). That sentence is the product — a gate that only says
 * "no" gets routed around, and an invariant that is routed around is not an invariant
 * (ARCHITECTURE.md §3.1) — so the list renders every atom, in payload order, with its
 * kind, its identifiers and whatever detail the emitter attached, verbatim.
 *
 * `naa` is the MINIMUM-CARDINALITY change that restores admissibility. It is advice, not
 * authority: acting on it still goes through the gate, and this panel says so.
 *
 * The honest not-computable state is the half that is easy to get wrong. When `naa` is
 * `null` the payload MUST carry an `naa_reason` from a closed set, and one of those
 * reasons — `no_legal_verdict_exists` — is not a failure of the diagnoser at all. §4:
 * *"A consumer MUST render it as a statement about the rule, never as a defect."* So the
 * absent alternative is presented as an answer, with the specification's own gloss
 * attributed to the specification, and never as an error.
 *
 * MUS atom kinds are the four fact families plus the obligation family that carries
 * them: `obligation`, `clause`, `event`, `authority_gap`, `capability_gap`. There is no
 * default branch — a kind outside the union is a contract change, and TypeScript's
 * exhaustiveness is what will notice it.
 */

import { type ReactNode } from 'react';

import { Mono, SeverityBand } from '../../design/primitives';
import { isVirulenceClass } from '../../design/severity';

import styles from './gate.module.css';
import { NAA_REASON_GLOSS, naaCardinality } from './model';
import { ProvenanceSlot } from './ProvenanceSlot';
import { pointer, type ProvenanceEntry } from './provenance';
import type { MusAtom, Naa, RefusalPayload } from '../../data/types.generated';

export interface ReasonSetProps {
  readonly refusal: RefusalPayload;
  readonly provenance: readonly ProvenanceEntry[] | undefined;
}

function Kv({ k, children }: { readonly k: string; readonly children: ReactNode }): ReactNode {
  return (
    <span className={styles.fact}>
      <span className={styles.label}>{k}</span>
      <span className={styles.factValue}>{children}</span>
    </span>
  );
}

function AtomBody({ atom }: { readonly atom: MusAtom }): ReactNode {
  switch (atom.kind) {
    case 'obligation':
      return (
        <div className={styles.facts}>
          <Kv k="obligation_id">{atom.obligation_id}</Kv>
          {atom.origin === undefined ? null : <Kv k="origin">{atom.origin}</Kv>}
          {atom.clause_id === undefined ? null : <Kv k="clause_id">{atom.clause_id}</Kv>}
          {atom.event_id === undefined ? null : <Kv k="event_id">{atom.event_id}</Kv>}
          {atom.severity === undefined ? null : <Kv k="severity">{atom.severity}</Kv>}
          {atom.virulence === undefined ? null : (
            <span className={styles.fact}>
              {isVirulenceClass(atom.virulence) ? (
                <SeverityBand
                  virulence={atom.virulence}
                  {...(atom.severity === undefined ? {} : { severity: atom.severity })}
                />
              ) : (
                <Kv k="virulence">{atom.virulence}</Kv>
              )}
            </span>
          )}
        </div>
      );
    case 'clause':
      return (
        <div className={styles.facts}>
          <Kv k="clause_id">{atom.clause_id}</Kv>
          {atom.commit_id === undefined ? null : <Kv k="commit_id">{atom.commit_id}</Kv>}
          {atom.relation === undefined ? null : <Kv k="relation">{atom.relation}</Kv>}
        </div>
      );
    case 'event':
      return (
        <div className={styles.facts}>
          <Kv k="event_id">{atom.event_id}</Kv>
          {atom.severity === undefined ? null : <Kv k="severity">{atom.severity}</Kv>}
        </div>
      );
    case 'authority_gap':
      return (
        <div className={styles.facts}>
          <Kv k="relation">{atom.relation}</Kv>
          {Object.entries(atom.key).map(([name, value]) => (
            <Kv key={name} k={`key.${name}`}>
              {value === null ? 'null' : String(value)}
            </Kv>
          ))}
        </div>
      );
    case 'capability_gap':
      return (
        <div className={styles.facts}>
          <Kv k="capability">{atom.capability}</Kv>
          {atom.required_value === undefined ? null : (
            <Kv k="required">{JSON.stringify(atom.required_value)}</Kv>
          )}
          {atom.observed_value === undefined ? null : (
            <Kv k="observed">{JSON.stringify(atom.observed_value)}</Kv>
          )}
        </div>
      );
  }
}

function NearestAdmissible({ naa }: { readonly naa: Naa }): ReactNode {
  const cardinality = naaCardinality(naa);
  return (
    <div data-testid="naa" data-naa-kind={naa.kind} className={styles.item}>
      <div className={styles.itemHead}>
        <span className={styles.label}>kind</span>
        <Mono data-testid="naa-kind">{naa.kind}</Mono>
        <span className={styles.label}>minimum cardinality</span>
        {cardinality === null ? (
          <span className={styles.chipUndeclared} data-testid="naa-cardinality-absent">
            not stated by the emitter
          </span>
        ) : (
          <Mono data-testid="naa-cardinality">{cardinality}</Mono>
        )}
      </div>

      <p className={styles.canon} data-testid="naa-description">
        {naa.description}
      </p>

      {naa.kind === 'dispose_obligations' ? (
        <div className={styles.facts}>
          {naa.obligation_ids.map((id) => (
            <Kv key={id} k="dispose">
              {id}
            </Kv>
          ))}
          {(naa.legal_kinds ?? []).map((kind) => (
            <Kv key={kind} k="legal kind">
              {kind}
            </Kv>
          ))}
        </div>
      ) : null}

      {naa.kind === 'substitute_kind' ? (
        <div className={styles.facts}>
          {naa.legal_kinds.map((kind) => (
            <Kv key={kind} k="legal kind">
              {kind}
            </Kv>
          ))}
        </div>
      ) : null}

      {naa.kind === 'supply_evidence' ? (
        <div className={styles.facts}>
          {naa.required.map((item) => (
            <Kv key={item} k="required">
              {item}
            </Kv>
          ))}
        </div>
      ) : null}

      {naa.kind === 'materialise_authority' ? (
        <div className={styles.facts}>
          <Kv k="relation">{naa.relation}</Kv>
          {Object.entries(naa.key).map(([name, value]) => (
            <Kv key={name} k={`key.${name}`}>
              {value === null ? 'null' : String(value)}
            </Kv>
          ))}
        </div>
      ) : null}

      {naa.kind === 'fork_subject' ? (
        <div className={styles.facts}>
          <Kv k="parent_subject_id">{naa.parent_subject_id}</Kv>
        </div>
      ) : null}

      <p className={styles.panelNote}>
        Advice, not authority. Acting on it still goes through the gate
        (<Mono>spec/wire/refusal.md</Mono> §4).
      </p>
    </div>
  );
}

function NotComputable({ reason }: { readonly reason: string | null }): ReactNode {
  const gloss = reason === null ? null : (NAA_REASON_GLOSS[reason] ?? null);
  const byDesign = reason === 'no_legal_verdict_exists';
  return (
    <div className={styles.absent} data-testid="naa-absent" data-naa-reason={reason ?? 'unstated'}>
      <span className={styles.absentTitle}>
        {byDesign ? 'there is no way to sign this away' : 'nearest admissible alternative — not computable'}
      </span>
      {reason === null ? (
        <p className={styles.prose}>
          The payload carries <Mono>naa: null</Mono> and states no <Mono>naa_reason</Mono>.
          <Mono> spec/wire/refusal.md</Mono> §2 requires one, so this is a defect in the emitter,
          not a property of the refusal — and the console will not guess which reason was meant.
        </p>
      ) : (
        <>
          <p className={styles.facts}>
            <Kv k="naa_reason">{reason}</Kv>
          </p>
          {gloss === null ? (
            <p className={styles.prose}>
              That reason is outside the closed set <Mono>spec/wire/refusal.md</Mono> §4 declares.
              It is rendered verbatim and interpreted no further.
            </p>
          ) : (
            <p className={styles.prose} data-testid="naa-gloss">
              <Mono>spec/wire/refusal.md</Mono> §4: {gloss}.
              {byDesign
                ? ' This is the product working, and it is a statement about the rule — not a defect and not a diagnoser failure.'
                : ''}
            </p>
          )}
        </>
      )}
    </div>
  );
}

export function ReasonSet({ refusal, provenance }: ReasonSetProps): ReactNode {
  const { mus, naa } = refusal;

  return (
    <div className={styles.columns}>
      <section className={styles.panel} aria-labelledby="gate-mus-title" data-testid="mus-panel">
        <h2 className={styles.panelTitle} id="gate-mus-title">
          Minimal unsatisfiable subset
        </h2>
        <p className={styles.panelNote}>
          Remove any one element below and the transition would have been admissible; remove none
          and it would not. Obtained by <Mono>{refusal.diagnosis}</Mono> diagnosis in{' '}
          <Mono>{refusal.probe_calls}</Mono> probe call(s).
        </p>

        {mus.length === 0 ? (
          <div className={styles.absent} data-testid="mus-empty">
            <span className={styles.absentTitle}>empty reason set</span>
            <p className={styles.prose}>
              The payload carries no atoms. <Mono>spec/wire/refusal.md</Mono> M-1 forbids an empty{' '}
              <Mono>mus</Mono> for every SQLSTATE the gate path is closed over, so this payload is
              non-conformant and nothing about the refusal can be read from it.
            </p>
          </div>
        ) : (
          <ol className={styles.list} data-testid="mus-list">
            {mus.map((atom, index) => (
              <li
                className={styles.item}
                key={`${atom.kind}:${index}`}
                data-testid="mus-atom"
                data-atom-kind={atom.kind}
              >
                <div className={styles.itemHead}>
                  <Mono data-testid="mus-atom-kind">{atom.kind}</Mono>
                  <ProvenanceSlot
                    provenance={provenance}
                    pointer={pointer('refusal', 'mus', index)}
                  />
                </div>
                <AtomBody atom={atom} />
                {atom.detail === undefined ? null : (
                  <p className={styles.canon} data-testid="mus-atom-detail">
                    {atom.detail}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className={styles.panel} aria-labelledby="gate-naa-title" data-testid="naa-panel">
        <h2 className={styles.panelTitle} id="gate-naa-title">
          Nearest admissible alternative
        </h2>
        <p className={styles.panelNote}>
          The minimum-cardinality change to the attempted history that restores admissibility.
        </p>
        {naa === null ? (
          <NotComputable reason={refusal.naa_reason ?? null} />
        ) : (
          <NearestAdmissible naa={naa} />
        )}
      </section>
    </div>
  );
}
