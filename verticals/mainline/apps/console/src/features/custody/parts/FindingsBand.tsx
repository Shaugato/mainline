// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE RED, WITH A SUBJECT.
 *
 * Measured against the live URL on 2026-08-15, this surface reported `5 passed / 4 failed /
 * 6 not run` under the headline `verification FAILED`, and told a reader nothing else above
 * the fold. Every one of those numbers was true. The problem is what a stranger does with
 * them: a red with no subject reads as *"this product is broken"*, and the four reds here
 * are four specific, checkable findings — two of them about ONE checkpoint out of the three
 * this payload carries, and one of them a true statement about a synthetic corpus.
 *
 * So this band names them. It is the first thing under the seal, and it is composed entirely
 * out of {@link custodyVerdict}, which is composed entirely out of the report the Web Worker
 * produced and the payload the transport served.
 *
 * ── WHAT THIS BAND MAY NOT DO ────────────────────────────────────────────────────
 *
 * It does not weaken, skip, exempt, hide or explain away one check. The seal above it still
 * says FAILED, the tally beside it still counts every check, `CheckList` below it still
 * renders all fifteen with their arithmetic, and the verifier's own summary is still printed
 * verbatim in the checks section. This band ADDS a subject to a number; if it ever subtracts
 * one, it is wrong.
 *
 * It also does not diagnose. *Why* a particular checkpoint row is in a particular deployment
 * is a question about a database, and this console cannot see the answer from here — it can
 * see only that the arithmetic it ran disagreed with that row and agreed with the others.
 * Attributing a cause the screen cannot establish would be exactly the invention this whole
 * surface exists to refuse.
 *
 * ── THE TWO READERS (R9) ─────────────────────────────────────────────────────────
 *
 * The lead is plain: no acronym, no digest, one sentence per fact. Everything precise —
 * check ids, the verifier's verbatim first line, the rows that disagreed under the exact
 * labels the worker filed them under, the root prefix of every checkpoint named — is below
 * it and is never collapsed, because a finding is not working-out: it is the finding.
 */

import { type ReactNode } from 'react';

import { Mono } from '../../../design/primitives';
import styles from '../custody.module.css';
import type { CheckpointRef, CustodyFinding, CustodyVerdict } from '../model';

/** The plain sentence above the fold. Counts only — no digest, no check name, no acronym. */
function plainLead(verdict: CustodyVerdict): string {
  const failed = verdict.failures.length;
  const notRun = verdict.notRun.length;
  if (failed === 0 && notRun === 0) {
    return 'Every claim on this page was re-done in this browser, and every one of them agreed.';
  }
  if (failed === 0) {
    return (
      `Every claim that could be re-done in this browser agreed. ${notRun} of them could not be ` +
      'attempted at all, and those are listed here rather than left off the page — a claim ' +
      'nobody checked is not a claim that passed.'
    );
  }
  const one = failed === 1;
  const first = verdict.implicated[0];
  const where =
    verdict.implicated.length === 1 && first !== undefined
      ? ` Every disagreement is about ONE of this log’s snapshots — the statement it made when ` +
        `it held ${first.treeSize} ${first.treeSize === 1 ? 'entry' : 'entries'}. Every other ` +
        'snapshot here was re-done and reproduced exactly.'
      : verdict.implicated.length === 0
        ? ''
        : ` The snapshots involved — ${verdict.implicated.length} of them — are named below.`;
  return (
    `${failed} claim${one ? '' : 's'} on this page ${one ? 'was' : 'were'} re-done in this ` +
    `browser and did NOT agree.${where}` +
    (notRun === 0
      ? ''
      : ` A further ${notRun} could not be attempted at all, and they are named too — a claim ` +
        'nobody checked is not a claim that passed.')
  );
}

/**
 * WHY THERE IS NO CHECKPOINT HERE, IN THE RIGHT WORDS FOR THE RIGHT REASON.
 *
 * Three different silences reach this slot and only one of them is about a checkpoint:
 *
 *   • a check that was never attempted compared nothing, so there is nothing to attribute —
 *     and printing "no checkpoint carries the value this row was compared against" over a
 *     check that never ran would read as a second finding that does not exist;
 *   • a failing check whose rows compared nothing against a root (check 4 files the SHA-256
 *     of a note text, which no checkpoint publishes) is attributed by its own sentence,
 *     which names the tree size in the verifier's words rather than in this band's; and
 *   • a failing check that DID compare against a root no checkpoint here carries is the one
 *     case where the absence is itself worth stating.
 */
function noCheckpointReason(finding: CustodyFinding): string {
  if (finding.status !== 'fail') {
    return 'Nothing was compared here, because this check was never attempted — so no checkpoint is named against it.';
  }
  if (finding.compared === 0) {
    return 'Nothing in this check was compared against a checkpoint root, so this band names none. Where the sentence above names a checkpoint, that sentence is the verifier’s and not this band’s.';
  }
  return 'No checkpoint in this payload carries the value the disagreeing row was compared against, so this finding is attributed to none of them. The verifier’s own sentence is above.';
}

function CheckpointList({
  refs,
  finding,
}: {
  readonly refs: readonly CheckpointRef[];
  readonly finding: CustodyFinding;
}): ReactNode {
  if (refs.length === 0) {
    return <p className={styles.chainPurpose}>{noCheckpointReason(finding)}</p>;
  }
  return (
    <ul className={styles.plainList}>
      {refs.map((ref) => (
        <li key={ref.treeSize} data-testid={`custody-finding-checkpoint-${ref.treeSize}`}>
          measured against the checkpoint at <Mono>tree_size {ref.treeSize}</Mono>, root{' '}
          <Mono>{ref.rootPrefix}…</Mono>
          {ref.admissible
            ? ' — a row the database projects as admissible'
            : ' — a row the database does not project as admissible'}
        </li>
      ))}
    </ul>
  );
}

function Finding({ finding }: { readonly finding: CustodyFinding }): ReactNode {
  return (
    <li
      className={styles.check}
      data-status={finding.status}
      data-testid={`custody-finding-${finding.id}`}
    >
      <p className={styles.checkHead}>
        <span className={styles.checkId}>check {finding.id}</span>
        <span className={styles.checkName}>{finding.name}</span>
        <span className={styles.kicker}>
          {finding.status === 'fail' ? 'RE-DONE HERE AND DISAGREED' : 'NEVER ATTEMPTED'}
        </span>
      </p>

      {finding.status === 'fail' && finding.compared > 0 ? (
        <p className={styles.detail} data-testid={`custody-finding-rows-${finding.id}`}>
          {finding.disagreed} of {finding.compared} recomputation(s) in this check disagreed
          {finding.rows.length === 0 ? '.' : `: ${finding.rows.join('; ')}.`} Each one is in the
          table below this band, with the bytes hashed and both digits.
        </p>
      ) : null}

      <CheckpointList refs={finding.checkpoints} finding={finding} />

      {/*
        * THE VERIFIER'S OWN FIRST LINE, VERBATIM.
        *
        * `CheckList` renders the whole `detail` unparaphrased a little further down; this is
        * its first line, so the finding is legible without scrolling and is still the
        * verifier's sentence rather than a summary of it.
        */}
      <p className={styles.detail} data-testid={`custody-finding-detail-${finding.id}`}>
        {finding.firstLine}
      </p>
    </li>
  );
}

export function FindingsBand({ verdict }: { readonly verdict: CustodyVerdict }): ReactNode {
  if (verdict.headline === '') return null;

  /*
   * THREE FRAMES, NOT TWO — the same distinction `CheckList` draws and for its reason.
   *
   * Red is for arithmetic that ran and disagreed. Amber is for arithmetic nobody could run:
   * `spec/custody/checks.yaml` says a verifier that quietly passes because it did not look is
   * the worst artefact this domain could ship, so a skip is framed as loudly as a failure and
   * never as a pass. Neutral is for a report with neither — and a report with neither is the
   * only one this band is allowed to leave unframed.
   */
  const frame =
    verdict.failures.length > 0
      ? styles.failure
      : verdict.notRun.length > 0
        ? styles.limit
        : styles.section;
  return (
    <section
      className={frame}
      data-testid="custody-findings"
      data-failures={verdict.failures.length}
      data-not-run={verdict.notRun.length}
      aria-label="What disagreed, and about which checkpoint"
    >
      <span className={styles.limitTitle}>
        what disagreed here, and which checkpoint it was about
      </span>

      <p className={styles.prose} data-testid="custody-findings-plain">
        {plainLead(verdict)}
      </p>

      <p className={styles.limitText} data-testid="custody-verdict">
        {verdict.headline}
      </p>

      {verdict.failures.length === 0 ? null : (
        <ul className={styles.checks} data-testid="custody-findings-failed">
          {verdict.failures.map((finding) => (
            <Finding key={`fail-${finding.id}`} finding={finding} />
          ))}
        </ul>
      )}

      {verdict.notRun.length === 0 ? null : (
        <ul className={styles.checks} data-testid="custody-findings-not-run">
          {verdict.notRun.map((finding) => (
            <Finding key={`skip-${finding.id}`} finding={finding} />
          ))}
        </ul>
      )}

      <p className={styles.chainPurpose}>
        Nothing above is a check that was weakened, skipped by this screen, or hidden: the seal
        is still the verifier’s, the tally still counts every check, and every check — the ones
        that agreed included — is listed in full below with the arithmetic that produced it.
        This band only says WHICH ones and about WHAT. Why a particular checkpoint row exists in
        a particular deployment is a question about that database, and this screen does not
        answer questions it cannot see the answer to.
      </p>
    </section>
  );
}
