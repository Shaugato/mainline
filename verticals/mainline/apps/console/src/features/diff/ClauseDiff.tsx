// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CLAUSE DIFF — the panel that armed the check.
 *
 * `docs/leads/ui.md` §5 gives this to the gate screen as "the clause diff that armed the
 * check", and that phrase is the whole design brief. A permit is refused because a clause
 * was WEAKENED over a blame ancestry holding a fatality. This panel is where a reader
 * finds out what "weakened" meant, in words, against the two column values it was decided
 * from.
 *
 * One sentence governs every pixel of it:
 *
 *     THE CONSOLE COMPUTED WHAT CHANGED. ONLY THE DATABASE SAYS WHY.
 *
 * The panel is therefore in two halves that are never allowed to blend:
 *
 *   WHAT — the canonical text, the anchor set, the Control Assertion Tuple, the columns.
 *          Re-derived in this browser from two rows, deterministic, and badged
 *          `recomputed` wherever the console did the deriving, `db:column` wherever it is
 *          quoting. Every one of these is reassemblable from the DOM, so the derivation is
 *          checkable rather than merely asserted.
 *
 *   WHY  — `mainline.delta_witness`, verbatim, and nothing else. When the rows are absent
 *          the panel says WITNESS UNAVAILABLE and offers no account, because the only
 *          account it could offer would be one it made up. When they are present but do
 *          not cover an observed change, that change is LISTED as uncovered.
 *
 * EVIDENCE register (ui.md §1.1): no motion, no depth, no gradient. Every string the
 * database emitted is in the mono face and is real selectable text. The panel prints.
 *
 * D5: this component computes no gate condition. It never derives `control_delta`, never
 * decides whether an obligation should exist, and never colours a verdict it worked out
 * itself — `weaken` is rendered because the column says `weaken`.
 *
 * ── TWO READERS, ONE PANEL (2026-08-15) ──────────────────────────────────────────
 *
 * `docs/leads/two-audience-ux-plan.md` R6: the panel opens with sentences a site supervisor
 * can read, and every exact thing that was already on it is one deliberate, permanent click
 * away. **Nothing was deleted and no sentence got vaguer.** What changed is the order a
 * reader meets things in, and which of them start collapsed:
 *
 *   always open — the delta verdict and its provenance chips, every finding, every stated
 *                 absence (`NO DIFF — …`, `WITNESS UNAVAILABLE`, `NO WITNESSES`), the
 *                 changes no witness accounts for, and the STAGED badge. R6 forbids
 *                 collapsing any of these and this panel collapses none of them.
 *   one click   — the two commit fingerprints, the canonical text and its unified diff, the
 *                 anchor table, the Control Assertion Tuple pointers, the witness rows and
 *                 the column-by-column table. R6 names each of these as collapsible, they
 *                 are all still in the DOM in both states, and they all print open.
 *
 * The one thing that would have been easier and is forbidden: summarising a collapsed table
 * in the sentence above it. A summary of a digest is a worse digest, so the plain sentences
 * say what the reader is about to look AT and never what it says.
 */

import { type ReactNode } from 'react';

import { RegisterFrame, StagedBadge, Digest } from '../../design/primitives';
import styles from './diff.module.css';
import type { ClauseDiffModel } from './model';
import { Disclosure, Gloss, PlainBand } from './parts/Plain';
import {
  AnchorResidueView,
  CatDeltaView,
  ScalarTable,
  UnwitnessedPanel,
} from './parts/StructurePanels';
import { TextDiffView } from './parts/TextDiffView';
import { DeltaVerdictBar, FindingsPanel } from './parts/VerdictAndFindings';
import { WitnessTable } from './parts/WitnessTable';

export interface ClauseDiffProps {
  readonly model: ClauseDiffModel;
  /**
   * `envelope.staged_note`, verbatim, when the payload said it was staged.
   *
   * Passed in rather than read from a context so that the panel is a pure function of its
   * props: the gate screen embeds this component beside its own data and must be able to
   * hand it the same fact without a second provider (D7 / the honesty chrome).
   */
  readonly staged?: string;
}

/** Why there is no comparison, when there is none. Never a blank space. */
function ComparabilityNotice({ model }: { readonly model: ClauseDiffModel }): ReactNode {
  const { comparability } = model;
  if (comparability.kind === 'comparable') return null;

  const heading =
    comparability.kind === 'parent_mismatch'
      ? 'NO DIFF — WRONG ANCESTOR'
      : comparability.kind === 'parent_unresolved'
        ? 'NO DIFF — ANCESTOR NOT CARRIED'
        : 'NO DIFF — ORIGIN VERSION';

  const body =
    comparability.kind === 'parent_mismatch' ? (
      <>
        This version names <code className={styles.mono}>{comparability.named ?? '(none)'}</code>{' '}
        as its parent and the payload supplied{' '}
        <code className={styles.mono}>{comparability.supplied}</code>. Diffing them would
        depict an edit that never happened, and on screen it would be indistinguishable from
        one that did. The comparison is refused rather than annotated.
      </>
    ) : comparability.kind === 'parent_unresolved' ? (
      <>
        This version names <code className={styles.mono}>{comparability.named}</code> as its
        parent and the read API resolved no ancestor row for it. Everything the database said
        about the delta is below; nothing on this screen has been compared against anything.
      </>
    ) : (
      <>
        This version names no parent, so there is nothing in this payload to compare it with.
        A verdict other than <code className={styles.mono}>introduce</code> on an origin
        version is not by itself irregular: a re-scoped control is a new clause whose delta is
        measured against an ancestor reached through identity residue rather than through{' '}
        <code className={styles.mono}>parent_version</code>.
      </>
    );

  return (
    <div className={styles.absence} data-testid="diff-no-comparison">
      <p className={styles.absenceHead}>{heading}</p>
      <p className={styles.absenceBody}>{body}</p>
    </div>
  );
}

export function ClauseDiff({ model, staged }: ClauseDiffProps): ReactNode {
  const comparable = model.comparability.kind === 'comparable';

  return (
    <RegisterFrame
      register="evidence"
      as="section"
      label="Clause diff"
      bordered
      // `noUncheckedIndexedAccess` types a CSS Module member as `string | undefined`, and
      // `RegisterFrame.className` is `string | undefined`-hostile under
      // `exactOptionalPropertyTypes`. The coalesce is the honest fix: a missing class is a
      // styling defect, never an evidentiary one, and an empty string says so.
      className={styles.panel ?? ''}
      data-testid="clause-diff"
    >
      <header className={styles.head}>
        <h2 className={styles.title}>Clause diff</h2>
        <p className={styles.subtitle}>
          clause <code className={styles.mono}>{model.clauseUuid}</code>
        </p>
        {staged === undefined ? null : (
          <StagedBadge what={staged} data-testid="diff-staged" />
        )}
      </header>

      <PlainBand label="What a clause version is, in plain words">
        <p className={styles.plainLead}>
          A clause is the written rule a permit has to satisfy. Every time someone edits it, the
          database keeps the wording from before the edit and the wording from after it as two
          separate versions, and this panel opens one of them.
        </p>
        <p className={styles.plainLead}>
          What you can read below: the exact wording held against this version, what an edit
          changed if there is an earlier version to change from, and the word the database
          recorded for what that change did to the controls.
        </p>
        <p className={styles.plainLead}>
          The two are kept apart on purpose. Anything this browser worked out is marked as worked
          out here; anything the database said is quoted and never re-worded.
        </p>
      </PlainBand>

      <Disclosure
        summary="Show the exact fingerprint of each version"
        testId="diff-commits-disclosure"
      >
        <Gloss>
          A fingerprint is a short code worked out from the bytes of a version. Change one
          character of the wording and the code changes completely, which is how two people can
          establish they are looking at the same version without comparing the text word by word.
        </Gloss>
        <div className={styles.commits}>
          <Digest value={model.versionCommit} label="this version" />
          {model.parentCommit === null ? null : (
            <Digest value={model.parentCommit} label="ancestor" />
          )}
        </div>
      </Disclosure>

      <DeltaVerdictBar verdict={model.verdict} severity={model.severity} />

      <p className={styles.thesis}>
        This browser computed <strong>what</strong> changed, from the two column values below,
        and shows its arithmetic. Only the database says <strong>why</strong> — every reason on
        this screen is a <code className={styles.mono}>delta_witness</code> row, rendered
        verbatim. Where there is no row, there is no reason here either.
      </p>

      <FindingsPanel findings={model.findings} />

      <ComparabilityNotice model={model} />

      {comparable && model.text !== null && model.canonText.parent !== null ? (
        <TextDiffView
          diff={model.text}
          parentText={model.canonText.parent}
          versionText={model.canonText.version}
          parentCommit={model.parentCommit ?? ''}
          versionCommit={model.versionCommit}
        />
      ) : null}

      {model.anchors === null ? null : <AnchorResidueView anchors={model.anchors} />}
      {model.cat === null ? null : <CatDeltaView cat={model.cat} />}

      <WitnessTable binding={model.witnesses} />
      <UnwitnessedPanel unwitnessed={model.unwitnessed} comparable={comparable} />

      {model.scalars.length === 0 ? null : <ScalarTable scalars={model.scalars} />}
    </RegisterFrame>
  );
}
