// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Proof of Exhausted Recall, rendered with its bound attached.
 *
 * The commitment: the candidate leaves are SCORE-SORTED, so disclosing `candidate_root`,
 * `theta`, `s`, `n` and the inclusion paths for leaves `s` and `s+1` establishes that
 * every leaf beyond position `s` scored below theta — nothing can be hand-excluded without
 * breaking sortedness — while revealing none of the suppressed content. That is a privilege
 * log that is cryptographically enforced rather than promised.
 *
 * ── THREE HONESTY RULES, IMPLEMENTED RATHER THAN INTENDED ────────────────────────
 *
 * 1. **The limit is rendered twice, and one of the two is verbatim from the payload.**
 *    `PER_LIMIT_SENTENCE` is the console's standing caveat and is grep-able in CI;
 *    `receipt.bound.statement` is the emitter's own sentence, rendered exactly as the
 *    column holds it. If the two ever disagree, a reader sees both.
 *
 * 2. **No seal.** The two Merkle paths are DISPLAYED here and are not verified here.
 *    Recomputing them against `candidate_root` is the in-browser verifier's job
 *    (`src/verify`, ui W8). A green tick over an unverified inclusion path would be the
 *    single most misleading pixel in this product, so where the seal would go there is a
 *    sentence saying the arithmetic has not been done on this screen.
 *
 * 3. **The bracket check is labelled as what it is.** Comparing `score(s) >= theta >
 *    score(s+1)` uses three numbers that are all on screen. It is a consistency check on
 *    the disclosed pair, chipped `recomputed` — it is emphatically NOT proof of inclusion,
 *    and it cannot be, because it never touches the root.
 */

import { type ReactNode } from 'react';

import { Digest, Mono, ProvenanceChip } from '../../design/primitives';

import { boundaryPairOf, boundarySane, PER_BOUND_GLOSS, PER_LIMIT_SENTENCE } from './model';
import { ProvenanceSlot } from './ProvenanceSlot';
import type { ProvenanceEntry } from './provenance';
import styles from './silence.module.css';
import type { BoundaryLeaf, SilenceReceipt } from '../../data/types.generated';

export interface PerPanelProps {
  readonly receipt: SilenceReceipt;
  readonly provenance: readonly ProvenanceEntry[] | undefined;
}

function Leaf({
  leaf,
  which,
  testId,
}: {
  readonly leaf: BoundaryLeaf;
  readonly which: string;
  readonly testId: string;
}): ReactNode {
  return (
    <div className={styles.boundaryCell} data-testid={testId} data-index={leaf.index}>
      <span className={styles.kicker}>{which}</span>
      <dl className={styles.facts}>
        <dt>index</dt>
        <dd>
          <Mono>{leaf.index}</Mono>
        </dd>
        <dt>score</dt>
        <dd>
          <Mono data-testid={`${testId}-score`}>{leaf.score}</Mono>
        </dd>
        <dt>leaf hash</dt>
        <dd>
          <Digest value={leaf.leaf_hash_hex} label="leaf_hash" />
        </dd>
        <dt>path length</dt>
        <dd>
          <Mono>{leaf.path_hex.length}</Mono> node(s)
        </dd>
      </dl>
    </div>
  );
}

export function PerPanel({ receipt, provenance }: PerPanelProps): ReactNode {
  const pair = boundaryPairOf(receipt);
  const sane = boundarySane(receipt);

  return (
    <section className={styles.panel} data-testid="per-panel" aria-label="Proof of Exhausted Recall">
      <span className={styles.kicker}>proof of exhausted recall</span>
      <h2 className={styles.sectionTitle}>the commitment, and what it does not cover</h2>

      <dl className={styles.facts}>
        <dt>theta</dt>
        <dd>
          <Mono data-testid="per-theta">{receipt.theta}</Mono>{' '}
          <ProvenanceSlot
            provenance={provenance}
            pointer="/receipt/theta"
            data-testid="per-theta-provenance"
          />
        </dd>
        <dt>s</dt>
        <dd>
          <Mono data-testid="per-s">{receipt.s}</Mono>
        </dd>
        <dt>n</dt>
        <dd>
          <Mono data-testid="per-n">{receipt.n}</Mono>
        </dd>
        <dt>candidate_root</dt>
        <dd>
          <Digest
            value={receipt.candidate_root}
            label="candidate_root"
            data-testid="per-candidate-root"
          />
          <p className={styles.note}>
            A Merkle root over the SCORE-SORTED candidate multiset. Sortedness is what makes
            the disclosure below a proof rather than a sample: an item removed by hand would
            break the ordering the root commits to.
          </p>
        </dd>
        <dt>corpus_root</dt>
        <dd>
          <Digest value={receipt.corpus_root} label="corpus_root" data-testid="per-corpus-root" />
        </dd>
        <dt>policy_version</dt>
        <dd>
          <Mono data-testid="per-policy-version">{receipt.policy_version}</Mono>
        </dd>
        <dt>issued_at</dt>
        <dd>
          <Mono>{receipt.issued_at}</Mono>
        </dd>
      </dl>

      {sane ? null : (
        <p className={styles.imbalance} data-testid="per-boundary-insane">
          <Mono>s</Mono> is outside <Mono>0 ≤ s ≤ n</Mono>. The database enforces{' '}
          <Mono>boundary_sane</Mono>, so this receipt did not come from a cluster carrying that
          constraint.
        </p>
      )}

      <h3 className={styles.sectionTitle}>the boundary pair</h3>
      <div className={styles.boundary}>
        <Leaf leaf={receipt.boundary_proof.leaf_s} which="leaf s" testId="per-leaf-s" />
        {receipt.boundary_proof.leaf_s_plus_1 === null ? (
          <div className={styles.boundaryCell} data-testid="per-leaf-s-plus-1-absent">
            <span className={styles.kicker}>leaf s+1</span>
            <p className={styles.prose}>
              None. The boundary sits at the end of the multiset: <Mono>s = n</Mono>, so there
              is no first leaf below theta to disclose. That is a stronger statement than a
              missing one, and it is displayed as such.
            </p>
          </div>
        ) : (
          <Leaf
            leaf={receipt.boundary_proof.leaf_s_plus_1}
            which="leaf s+1"
            testId="per-leaf-s-plus-1"
          />
        )}
      </div>

      <p
        className={styles.prose}
        data-testid="per-bracket"
        data-brackets={pair.bracketsTheta ? 'true' : 'false'}
      >
        {pair.boundaryAtEnd ? (
          <>
            Consistency check on the disclosed pair: <Mono>{pair.atS.score}</Mono> ≥ theta{' '}
            <Mono>{pair.theta}</Mono>, and there is no <Mono>s+1</Mono>.
          </>
        ) : (
          <>
            Consistency check on the disclosed pair: <Mono>{pair.atS.score}</Mono> ≥ theta{' '}
            <Mono>{pair.theta}</Mono> &gt; <Mono>{pair.atSPlusOne?.score}</Mono>.{' '}
            {pair.bracketsTheta
              ? 'The pair brackets theta, as a score-sorted multiset requires.'
              : 'THE PAIR DOES NOT BRACKET THETA. Either the multiset was not sorted or the disclosed indices are not the boundary.'}
          </>
        )}{' '}
        <ProvenanceChip kind="recomputed" detail="comparison of the two disclosed scores against theta" />
      </p>

      <p className={styles.prose} data-testid="per-not-recomputed">
        The two inclusion paths above are DISPLAYED, not verified. Recomputing them against{' '}
        <Mono>candidate_root</Mono> — RFC 6962 leaf and node hashing, in a Worker, against the
        same vectors the offline verifier consumes — belongs to the console&apos;s verifier
        module and has not run on this screen. There is deliberately no seal here: a green tick
        over an unverified Merkle path would be worse than no tick at all.
      </p>

      <h3 className={styles.sectionTitle}>the bound</h3>
      <p className={styles.limit} data-testid="per-limit-sentence">
        {PER_LIMIT_SENTENCE}
      </p>
      <p className={styles.prose}>
        Approximate nearest-neighbour search is approximate. An event the index never
        surfaced was never in the candidate multiset, so no Merkle argument over that
        multiset can say anything about it. What is proved is that nothing scoring at or above
        theta was withheld from the set that was returned.
      </p>

      <p className={styles.kicker}>the emitter&apos;s own bounding sentence, verbatim</p>
      <pre className={styles.verbatim} data-testid="per-bound-statement">
        {receipt.bound.statement}
      </pre>
      {/*
        THE GLOSS SITS BESIDE THE SENTENCE, NEVER INSIDE IT (R8).
        The `<pre>` above is the payload's own string in the mono face and this console does
        not touch it. This paragraph is ours, in the prose face, one element down — so a
        reader can see which words are whose, and a reader copying the well gets the
        emitter's sentence and nothing of ours mixed into it.
      */}
      <p className={styles.prose} data-testid="per-bound-gloss">
        {PER_BOUND_GLOSS}
      </p>

      <dl className={styles.facts}>
        <dt>bound.index_generation</dt>
        <dd>
          <Mono data-testid="per-bound-index-generation">{receipt.bound.index_generation}</Mono>
        </dd>
        <dt>bound.index_plan_digest</dt>
        <dd>
          <Digest
            value={receipt.bound.index_plan_digest}
            label="index_plan_digest"
            data-testid="per-bound-plan-digest"
          />
          <p className={styles.note}>
            The retrieval this receipt is about ran under that index generation and that
            observed plan. Both travel with the bound so an exhibit cannot be produced without
            them.
          </p>
        </dd>
      </dl>
    </section>
  );
}
