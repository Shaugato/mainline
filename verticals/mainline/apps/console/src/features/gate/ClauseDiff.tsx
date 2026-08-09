// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * (5) THE CLAUSE DIFF — the edit that armed the check.
 *
 * Two canonical texts side by side, the `control_delta` verdict the database recorded,
 * the basis it was reached on, and the witness rows behind it.
 *
 * ── THE THREE WITNESS STATES ─────────────────────────────────────────────────────
 *
 *   rows           the payload carries witnesses; each is rendered verbatim.
 *   asserted-none  the payload carries `[]`. The emitter is claiming there are none.
 *   unavailable    the payload carries `null`. WITNESS UNAVAILABLE — and the panel
 *                  infers NOTHING. ui.md §4 is explicit: the diff renders
 *                  `control_delta` with an explicit witness-unavailable state, never an
 *                  inferred explanation.
 *
 * `null` and `[]` are different claims and are rendered differently. The algorithms
 * domain's `fn_delta_witness_guard` refuses a weaken/remove verdict on
 * `delta_basis='lattice'` whose witnesses were not written in the same transaction
 * (P0001) — so a `null` on a weaken is itself a finding. That judgement belongs to the
 * database; this panel reports the absence and stops.
 *
 * ── EVIDENTIARY WEIGHT OF THE BASIS ──────────────────────────────────────────────
 *
 * M11 (ARCHITECTURE.md §3.3): gist may accuse, only verbatim may acquit. In this payload
 * the place that distinction is carriable is `delta_basis`:
 *
 *   `lattice`            structural — re-derivable from the two CAT tuples by anyone.
 *   `lattice+model`      model-assisted. The model id and prompt version are named.
 *   `abstain_to_weaken`  the model ABSTAINED and the verdict defaulted to the unsafe
 *                        direction on purpose. That is a default, not a finding.
 *   `human`              asserted by a person.
 *
 * Only `lattice` gets the verbatim treatment. The rest are marked as gist, and the panel
 * says what that means for what they can be used to do.
 *
 * ── WHAT THIS PANEL COMPUTES ─────────────────────────────────────────────────────
 *
 * Exactly two things, both labelled on screen as computed in this browser: the anchor-set
 * difference and the flat-path CAT difference. Both are string comparisons over payload
 * fields, both are reading aids, and neither gates anything. Every verdict — the delta,
 * the basis, minimality — is read from the payload.
 */

import { type ReactNode } from 'react';

import { Digest, Mono } from '../../design/primitives';

import styles from './gate.module.css';
import { anchorDelta, catDelta, witnessState, type ClauseData, type DiffSelection } from './model';
import { ProvenanceSlot } from './ProvenanceSlot';
import type { ProvenanceEntry } from './provenance';
import type { DeltaBasis } from '../../data/types.generated';

const BASIS_IS_STRUCTURAL: Readonly<Record<DeltaBasis, boolean>> = Object.freeze({
  lattice: true,
  'lattice+model': false,
  abstain_to_weaken: false,
  human: false,
});

const BASIS_NOTE: Readonly<Record<DeltaBasis, string>> = Object.freeze({
  lattice:
    'Structural. The verdict follows from the two Control Assertion Tuples by the lattice alone, so anyone holding both versions can re-derive it without trusting us.',
  'lattice+model':
    'Model-assisted. The lattice did not settle it alone; a model contributed, and the model id and prompt version are named beside the verdict.',
  abstain_to_weaken:
    'The model ABSTAINED and the verdict defaulted to weaken. That is a deliberate default in the unsafe direction, not a finding about this edit — it exists so an unreadable change cannot pass as neutral.',
  human: 'Asserted by a person. It carries no structural derivation and cannot be re-derived from the tuples.',
});

const SELECTION_NOTE: Readonly<Record<DiffSelection, string>> = Object.freeze({
  'named-by-reason-set':
    'This clause was selected because the refusal’s minimal unsatisfiable subset names the obligation attached to it.',
  'first-open-check':
    'No refusal is on screen, so this clause was selected as the one behind the first still-open blocking check. It is not a claim that this clause is the reason for anything.',
  none: 'No clause was selected.',
});

export interface ClauseDiffProps {
  readonly clause: ClauseData | null;
  readonly selection: DiffSelection;
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

export function ClauseDiff({ clause, selection, provenance }: ClauseDiffProps): ReactNode {
  if (clause === null) {
    return (
      <section className={styles.panel} aria-labelledby="gate-diff-title" data-testid="clause-diff">
        <h2 className={styles.panelTitle} id="gate-diff-title">
          The clause edit
        </h2>
        <div className={styles.absent} data-testid="clause-diff-absent">
          <span className={styles.absentTitle}>no clause version carried</span>
          <p className={styles.prose}>
            {SELECTION_NOTE[selection]} No <Mono>clause_version</Mono> payload reached this screen,
            so there is no canonical text, no control delta and no witness set to render.
          </p>
        </div>
      </section>
    );
  }

  const { version, parent, delta } = clause;
  const resolvedParent = parent ?? null;
  const anchors = anchorDelta(resolvedParent?.anchor_set ?? null, version.anchor_set);
  const cat = catDelta(resolvedParent?.cat_json, version.cat_json);
  const witnesses = witnessState(delta.witnesses);
  const structural = BASIS_IS_STRUCTURAL[delta.basis];

  return (
    <section className={styles.panel} aria-labelledby="gate-diff-title" data-testid="clause-diff">
      <h2 className={styles.panelTitle} id="gate-diff-title">
        The clause edit — <Mono>{version.printed_label ?? version.clause_uuid}</Mono>
      </h2>
      <p className={styles.panelNote}>{SELECTION_NOTE[selection]}</p>

      <div className={styles.facts}>
        <Kv k="control_delta">
          <Mono data-testid="control-delta">{delta.delta}</Mono>
        </Kv>
        <ProvenanceSlot provenance={provenance} pointer="/version/control_delta" />
        <Kv k="delta_basis">
          <Mono data-testid="delta-basis">{delta.basis}</Mono>
        </Kv>
        <ProvenanceSlot provenance={provenance} pointer="/version/delta_basis" />
        <span className={styles.fact}>
          <span
            className={styles.anchorStrength}
            data-anchor={structural ? 'verbatim' : 'gist'}
            data-testid="basis-strength"
          >
            {structural ? 'structural — re-derivable' : 'not structurally re-derivable'}
          </span>
        </span>
        <Kv k="minimal">
          {delta.minimal === null ? (
            <span data-testid="minimality-unestablished">
              not established by the emitter — an unproven claim of minimality is worse than none
            </span>
          ) : (
            <Mono data-testid="minimality">{delta.minimal}</Mono>
          )}
        </Kv>
        {version.delta_model === null || version.delta_model === undefined ? null : (
          <Kv k="delta_model">{version.delta_model}</Kv>
        )}
        {version.delta_prompt_version === null || version.delta_prompt_version === undefined ? null : (
          <Kv k="delta_prompt_version">{version.delta_prompt_version}</Kv>
        )}
        <Kv k="sev_max">{version.sev_max}</Kv>
        <Kv k="cat_confidence">{version.cat_confidence ?? 'not stated'}</Kv>
      </div>

      <p className={styles.panelNote} data-testid="basis-note">
        {BASIS_NOTE[delta.basis]}
      </p>

      {/* ── The two texts ── */}
      <div className={styles.columns}>
        <div>
          <span className={styles.label}>
            {resolvedParent === null ? 'ancestor — not carried' : `ancestor · gen ${resolvedParent.gen}`}
          </span>
          {resolvedParent === null ? (
            <div className={styles.absent} data-testid="parent-absent">
              <span className={styles.absentTitle}>ancestor version not carried</span>
              <p className={styles.prose}>
                The read API did not resolve the version this one edits, so there is nothing to
                place beside the current text. The console does not reconstruct an ancestor from a
                digest.
              </p>
            </div>
          ) : (
            <>
              <pre className={styles.canon} data-testid="canon-parent">
                {resolvedParent.canon_text}
              </pre>
              <div className={styles.facts}>
                <Digest value={resolvedParent.canon_sha256} label="canon sha256" />
                <Kv k="commit">{resolvedParent.commit_id}</Kv>
              </div>
            </>
          )}
        </div>
        <div>
          <span className={styles.label}>current · gen {version.gen}</span>
          <pre className={styles.canon} data-testid="canon-current">
            {version.canon_text}
          </pre>
          <div className={styles.facts}>
            <Digest value={version.canon_sha256} label="canon sha256" />
            <ProvenanceSlot provenance={provenance} pointer="/version/canon_sha256" />
            <Kv k="commit">{version.commit_id}</Kv>
            <Kv k="activity_root">{version.activity_root}</Kv>
          </div>
        </div>
      </div>

      {/* ── Witnesses ── */}
      <div data-testid="witnesses" data-witness-state={witnesses}>
        <span className={styles.label}>delta witnesses</span>
        {witnesses === 'unavailable' ? (
          <div className={styles.absent} data-testid="witness-unavailable">
            <span className={styles.absentTitle}>witness unavailable</span>
            <p className={styles.prose}>
              The payload carries <Mono>witnesses: null</Mono> — no witness rows reached this
              screen. The verdict <Mono>{delta.delta}</Mono> is rendered as the database recorded
              it, with no explanation attached: this console does not infer or paraphrase a reason
              for a delta it cannot see the witnesses for.
            </p>
          </div>
        ) : witnesses === 'asserted-none' ? (
          <div className={styles.absent} data-testid="witness-asserted-none">
            <span className={styles.absentTitle}>emitter asserts there are none</span>
            <p className={styles.prose}>
              The payload carries an empty witness array. That is a positive claim by the emitter,
              and a different claim from <Mono>null</Mono>, which would mean none reached this
              screen.
            </p>
          </div>
        ) : (
          <table className={styles.deltaTable} data-testid="witness-table">
            <thead>
              <tr>
                <th scope="col">rule_id</th>
                <th scope="col">field</th>
                <th scope="col">from</th>
                <th scope="col">to</th>
                <th scope="col">note</th>
              </tr>
            </thead>
            <tbody>
              {(delta.witnesses ?? []).map((witness) => (
                <tr key={`${witness.rule_id}:${witness.field}`} data-testid="witness-row">
                  <td>
                    <code>{witness.rule_id}</code>
                  </td>
                  <td>
                    <code>{witness.field}</code>
                  </td>
                  <td>
                    <code>{witness.from_repr === '' ? '(empty)' : witness.from_repr}</code>
                  </td>
                  <td>
                    <code>{witness.to_repr === '' ? '(empty)' : witness.to_repr}</code>
                  </td>
                  <td>{witness.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <ProvenanceSlot provenance={provenance} pointer="/delta/witnesses" />
      </div>

      {/* ── Anchors ── */}
      <div data-testid="anchor-delta">
        <span className={styles.label}>anchor_set — tags, setpoints, citations, CAS numbers</span>
        <p className={styles.panelNote}>
          Computed in this browser as a set difference over the two <Mono>anchor_set</Mono> arrays.
          It is a reading aid: an anchor dropped between versions is one of the residue reasons, but
          the decision is the database&rsquo;s.
        </p>
        <div className={styles.anchorRow}>
          {anchors.removed.map((anchor) => (
            <span className={styles.anchorTag} data-change="removed" key={`r:${anchor}`}>
              {anchor}
            </span>
          ))}
          {anchors.added.map((anchor) => (
            <span className={styles.anchorTag} data-change="added" key={`a:${anchor}`}>
              {anchor}
            </span>
          ))}
          {anchors.kept.map((anchor) => (
            <span className={styles.anchorTag} data-change="kept" key={`k:${anchor}`}>
              {anchor}
            </span>
          ))}
        </div>
        {anchors.removed.length === 0 ? null : (
          <p className={styles.panelNote} data-testid="anchors-dropped">
            {anchors.removed.length} anchor(s) present in the ancestor are absent from the
            descendant.
          </p>
        )}
      </div>

      {/* ── CAT tuple ── */}
      <div data-testid="cat-delta">
        <span className={styles.label}>Control Assertion Tuple</span>
        <p className={styles.panelNote}>
          Flat-path comparison, computed in this browser. The tuple&rsquo;s shape is owned by the
          algorithms domain; no key is special-cased here, because a console that knew which CAT
          fields mattered would be a console with an opinion about the lattice.
        </p>
        {cat.length === 0 ? (
          <p className={styles.panelNote} data-testid="cat-unchanged">
            No leaf path differs between the two tuples.
          </p>
        ) : (
          <table className={styles.deltaTable} data-testid="cat-table">
            <thead>
              <tr>
                <th scope="col">path</th>
                <th scope="col">change</th>
                <th scope="col">from</th>
                <th scope="col">to</th>
              </tr>
            </thead>
            <tbody>
              {cat.map((change) => (
                <tr key={change.path} data-testid="cat-row" data-change={change.kind}>
                  <td>
                    <code>{change.path}</code>
                  </td>
                  <td>{change.kind}</td>
                  <td>
                    <code>{change.from ?? '—'}</code>
                  </td>
                  <td>
                    <code>{change.to ?? '—'}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
