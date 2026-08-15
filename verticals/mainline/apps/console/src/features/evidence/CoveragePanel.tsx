// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Coverage — the arithmetic of the audit, with the conservation law written out.
 *
 * Every counter here carries a `recomputed` provenance chip, and the chip is not
 * decoration: `docs/leads/ui.md` D5 says a number on an evidentiary surface must say
 * how the console came to believe it, and these are the only numbers in the console
 * this browser genuinely produced rather than read.
 *
 * The equation at the bottom is the part a reviewer should look at. A screen made of
 * counters has one invisible failure mode — the parts stop summing to the whole and
 * every individual number still looks plausible — so the sum is displayed, and it is
 * marked when it does not balance.
 *
 * `unlisted` renders as **not established** rather than as zero when the source cannot
 * enumerate itself. "No smuggled files were found" and "we cannot look" are different
 * sentences and only one of them is true of a static host.
 *
 * ── THE ONE DISTINCTION A LAY READER WILL NOT MAKE UNAIDED (2026-08-15) ──────────
 *
 * That distinction was already correct on this screen and already rendered in bold. What it
 * was missing was a sentence saying what the difference IS, in ordinary words, for a reader
 * who has never had to make it. `docs/leads/two-audience-ux-plan.md` R6 requires it and
 * `src/features/evidence/source.ts` states the reason it exists at all: the difference
 * between "none found" and "not established" is the whole difference between honesty and
 * reassurance, and a reader who cannot tell them apart reads the second as the first — the
 * exact misreading this console exists to refuse.
 *
 * The sentence explains; it does not soften and it does not fill. `unlisted === null` still
 * renders as **not established**, and no count on this screen moved by one.
 */

import { type ReactNode } from 'react';

import { Counter, ProvenanceChip } from '../../design/primitives';

import styles from './evidence.module.css';
import type { Coverage } from './model';
import { Gloss } from './Plain';

function Cell({
  value,
  label,
  detail,
  testId,
}: {
  readonly value: number;
  readonly label: string;
  readonly detail: string;
  readonly testId: string;
}): ReactNode {
  return (
    <li className={styles.counterCell}>
      <Counter value={value} label={label} data-testid={testId}>
        <ProvenanceChip kind="recomputed" detail={detail} />
      </Counter>
    </li>
  );
}

export function CoveragePanel({ coverage }: { readonly coverage: Coverage }): ReactNode {
  const unlisted = coverage.unlisted;
  return (
    <div data-testid="evidence-coverage">
      <Gloss>
        <em>Coverage</em> is how much of the capture was actually checked here, and how much was
        not. The numbers below are the ones this browser produced; the line under them is the
        same numbers added up, so that the parts and the whole cannot quietly stop agreeing.
      </Gloss>

      <ul className={styles.counters}>
        <Cell
          value={coverage.filesDeclared}
          label="files the manifest lists"
          detail="manifest.files.length"
          testId="coverage-files-declared"
        />
        <Cell
          value={coverage.digestsMatched}
          label="digests that matched"
          detail="SHA-256 over the bytes, compared to manifest.files[].sha256"
          testId="coverage-matched"
        />
        <Cell
          value={coverage.digestsMismatched}
          label="digests that disagreed"
          detail="SHA-256 over the bytes, compared to manifest.files[].sha256"
          testId="coverage-mismatched"
        />
        <Cell
          value={coverage.filesUnreadable}
          label="files that could not be read"
          detail="the source rejected the read"
          testId="coverage-unreadable"
        />
        <Cell
          value={coverage.bytesDeclared}
          label="bytes the manifest declares"
          detail="Σ manifest.files[].bytes"
          testId="coverage-bytes-declared"
        />
        <Cell
          value={coverage.bytesRead}
          label="bytes actually read"
          detail="Σ byteLength of what arrived"
          testId="coverage-bytes-read"
        />
        <Cell
          value={coverage.framesDeclared}
          label="captured exchanges"
          detail="files under frames/"
          testId="coverage-frames"
        />
        <Cell
          value={coverage.resourcesWithFrame}
          label={`of ${coverage.resourcesDeclared} declared resources have a frame`}
          detail="frame names decoded and matched against src/data/resources.ts"
          testId="coverage-resources-covered"
        />
      </ul>

      <p className={styles.equation} data-conserved={String(coverage.conserved)} data-testid="evidence-conservation">
        {coverage.filesDeclared} declared = {coverage.digestsMatched} matched +{' '}
        {coverage.digestsMismatched} disagreed + {coverage.filesUnreadable} unreadable +{' '}
        {coverage.filesUnchecked} not checked
        {coverage.conserved
          ? ' — balanced.'
          : ' — DOES NOT BALANCE. No count on this screen may be relied on.'}
      </p>

      <p className={styles.note} data-testid="evidence-unlisted">
        Files present in the directory but absent from the manifest:{' '}
        {unlisted === null ? (
          <strong>not established — this source cannot enumerate itself.</strong>
        ) : unlisted.length === 0 ? (
          <>none. The source listed its own contents and every file in it is in the manifest.</>
        ) : (
          <strong>{unlisted.length}, named in the findings below.</strong>
        )}{' '}
        An unlisted file is never served by the transport; it is reported because a file nobody
        checked should not be in an evidence directory at all.
      </p>

      <p className={styles.establishedNote} data-testid="evidence-not-established-note">
        <strong>&ldquo;None&rdquo; and &ldquo;not established&rdquo; are different answers, and
        only one of them is reassuring.</strong> <em>None</em> means the check ran and came back
        empty. <em>Not established</em> means the check could not be run at all, so nobody knows
        — here, because the place these files are served from answers for a file you name and
        will not hand over a list of what it holds. Where you see <em>not established</em> on
        this screen, read it as <em>nobody looked</em>, never as <em>nothing was found</em>.
      </p>
    </div>
  );
}
