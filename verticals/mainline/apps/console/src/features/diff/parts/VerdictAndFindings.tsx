// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The verdict, and the things about this payload that do not add up.
 *
 * ── The verdict bar ──────────────────────────────────────────────────────────────
 *
 * `control_delta` is the value the whole gate turns on: a `weaken` over a blame ancestry
 * holding a severity ≥ 4 event auto-materialises a blocking obligation (ARCHITECTURE.md
 * §3, §5.3). So it is rendered in the mono face, spelled exactly as the enum spells it,
 * beside the basis that produced it and the model that was consulted if one was. The
 * console does not translate `weaken` into "reduced" and does not colour it into an
 * alarm on its own — the accent is applied to `weaken` and `remove` because those are the
 * two the guard covers, and the WORD is always present regardless of colour.
 *
 * ── The findings ─────────────────────────────────────────────────────────────────
 *
 * A finding is a contradiction inside the payload, or between the payload and a rule some
 * named artefact in this repository states. Each carries its AUTHORITY, rendered mono,
 * because a finding without one is an opinion and this console does not render those.
 *
 * Discrepancies come first and are never behind a disclosure. The single most important
 * one is `witness_guard_expectation`: `fn_delta_witness_guard` refuses a lattice weaken
 * with no witness rows, so a payload carrying one should not exist. The console states
 * the contradiction and stops — it does not decide between "the guard is not installed",
 * "the read API dropped the rows" and "these bytes were never written by a kernel",
 * because deciding that from a rendering layer is precisely the composed claim D5 forbids.
 */

import { type ReactNode } from 'react';

import { ProvenanceChip } from '../../../design/primitives';
import styles from '../diff.module.css';
import type { ClauseDiffModel, Finding } from '../model';

export function DeltaVerdictBar({
  verdict,
  severity,
}: {
  readonly verdict: ClauseDiffModel['verdict'];
  readonly severity: ClauseDiffModel['severity'];
}): ReactNode {
  return (
    <div className={styles.verdict} data-testid="delta-verdict">
      <span className={styles.verdictLabel}>control_delta</span>
      <code className={styles.verdictValue} data-delta={verdict.delta}>
        {verdict.delta}
      </code>
      <ProvenanceChip kind="db:column" detail="clause_version.control_delta" />

      <span className={styles.verdictLabel}>basis</span>
      <code className={styles.mono}>{verdict.basis}</code>
      <ProvenanceChip kind="db:column" detail="clause_version.delta_basis" />

      {verdict.model === null ? null : (
        <>
          <span className={styles.verdictLabel}>model</span>
          <code className={styles.mono}>{verdict.model}</code>
          {verdict.promptVersion === null ? null : (
            <code className={styles.mono}>{verdict.promptVersion}</code>
          )}
        </>
      )}

      <span className={styles.verdictLabel}>sev_max</span>
      <code className={styles.mono}>
        {severity.parentSevMax === null
          ? String(severity.versionSevMax)
          : `${severity.parentSevMax} → ${severity.versionSevMax}`}
      </code>
      <ProvenanceChip kind="db:column" detail="clause_version.sev_max — projected, never chosen" />
    </div>
  );
}

export function FindingsPanel({ findings }: { readonly findings: readonly Finding[] }): ReactNode {
  if (findings.length === 0) return null;
  return (
    <section
      className={styles.section}
      data-testid="diff-findings"
      aria-labelledby="diff-findings-head"
    >
      <div className={styles.sectionHead}>
        <h3 className={styles.sectionTitle} id="diff-findings-head">
          What does not add up
        </h3>
        <span className={styles.verdictLabel}>
          {findings.filter((finding) => finding.level === 'discrepancy').length} discrepancy ·{' '}
          {findings.filter((finding) => finding.level === 'observation').length} observation
        </span>
      </div>
      <ul className={styles.findings}>
        {findings.map((finding, index) => (
          <li
            className={styles.finding}
            data-level={finding.level}
            data-code={finding.code}
            key={`${finding.code}-${index}`}
          >
            <p className={styles.findingTitle}>
              <span className={styles.findingLevel}>{finding.level}</span>{' '}
              {finding.title}
            </p>
            <p className={styles.findingDetail}>{finding.detail}</p>
            <code className={styles.findingAuthority}>
              <span className={styles.visuallyHidden}>authority: </span>
              {finding.authority}
            </code>
          </li>
        ))}
      </ul>
    </section>
  );
}
