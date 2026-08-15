// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The custody surface's view model — pure functions over a `ledger` payload and a
 * `CheckReport`, with no React and no formatting opinions.
 *
 * The one rule this file exists to enforce: **a seal is derived from a recomputation or it
 * is not green.** `sealFor` cannot produce a `verified` seal without an algorithm name, an
 * instant and a digest prefix, because `VerificationSeal`'s own type will not compile one
 * — and the algorithm name and digest here come out of the check's `recomputations`, not
 * out of a string this file made up. A check that passed without recomputing anything (the
 * structural ones — no sandbox leaf, witness set shape) says so in its algorithm slot
 * rather than borrowing a digest from a neighbour.
 */

import type { Recomputation, SealProps } from '../../design/primitives';
import type { VerifierConfig } from '../../verify/config';
import {
  noteTextInput,
  type CheckReport,
  type CheckResult,
  type CheckStatus,
  type LedgerCheckpoint,
  type LedgerPayload,
  type Recomputed,
} from '../../verify/ledger';

// ── Which site, when the subject index could not say ───────────────────────

/**
 * The site code a `ledger` payload NAMES ABOUT ITSELF.
 *
 * This is the second of the two legitimate ways this surface can learn its subject, and
 * the distinction between it and the defect it replaces is the whole point:
 *
 *   • The `DEFAULT_SITE_CODE` this surface used to carry was the CONSOLE asserting a fact
 *     about rows it did not write. It answered 404 against the live kernel because no seed
 *     in this repository has ever written that code, and correcting it to a luckier value
 *     would rebuild the same defect against the next deployment. The value itself is
 *     recorded in `docs/leads/screens-work-plan.md` §2.2 and appears in no source file.
 *   • `GET /v1/ledger` with **no** `site_code` is the KERNEL naming its own subject.
 *     `contracts/ledger.schema.json` makes `site_code` a REQUIRED member of `data`, so any
 *     payload that satisfied the contract on the way in carries one, and it is whatever
 *     this deployment actually holds.
 *
 * The first is a guess. The second is an answer, and it is re-SELECTable by anyone holding
 * the DSN. This function does no repair: a payload naming an empty site yields `null` and
 * the surface says which nothing it is.
 */
export function siteNamedByLedger(payload: LedgerPayload | null): string | null {
  const code = payload?.site_code ?? '';
  return code === '' ? null : code;
}

// ── The signature check, named rather than coloured ────────────────────────

/** What the checkpoint-signature check did. Never a colour; the seal decides that. */
export type SignatureState = 'not-run' | 'skipped' | 'checked' | 'failed';

export interface SignatureReading {
  readonly state: SignatureState;
  /** Short, for a fact slot. Uppercase words are states, not emphasis. */
  readonly headline: string;
  /** The verifier's or the config's own sentence, verbatim. Never paraphrased. */
  readonly detail: string;
}

/**
 * WHY THE ONE SKIP ON THIS SCREEN GETS ITS OWN SENTENCE.
 *
 * `.env.demo` ships `VITE_MAINLINE_LOG_VKEY` EMPTY, so on the demo build the ECDSA P-256
 * check over the checkpoint note cannot be attempted at all. Two/R4 rules what that must
 * read: **`SKIPPED — this build carries no log key`** — amber, never green, and never red,
 * because a checkpoint nobody could check has not been accused of anything.
 *
 * It is DERIVED, not asserted. The state comes from the report's own `log_signature` check
 * when the verifier has answered, and from `VerifierConfig.source` before it has. A branch
 * that printed the SKIP sentence unconditionally would print it on a build that DOES carry
 * a key, which is the same class of defect as printing a tick on one that does not.
 */
export function signatureReading(
  report: CheckReport | null,
  config: VerifierConfig,
): SignatureReading {
  const anchored = config.logVkeys.length > 0;
  const check = report?.checks.find((entry) => entry.name === 'log_signature') ?? null;

  if (check === null) {
    return {
      state: 'not-run',
      headline: anchored ? 'not yet run' : 'SKIPPED — this build carries no log key',
      detail: config.sourceNote,
    };
  }
  if (check.status === 'fail') {
    return { state: 'failed', headline: 'FAILED', detail: check.detail };
  }
  if (check.status === 'skip') {
    return {
      state: 'skipped',
      headline: anchored ? 'SKIPPED' : 'SKIPPED — this build carries no log key',
      detail: check.detail,
    };
  }
  return { state: 'checked', headline: 'checked in this browser', detail: check.detail };
}

// ── The chain, as four layers ──────────────────────────────────────────────

export interface ChainLayer {
  /** `L0`…`L3`, from ARCHITECTURE.md §7.2. */
  readonly level: string;
  readonly title: string;
  /** What this layer holds in THIS payload. Null when the payload carries none of it. */
  readonly count: number | null;
  /** One line: what the layer is for. */
  readonly purpose: string;
  /** The digest that identifies this layer's state here, or null. */
  readonly digest: string | null;
  readonly digestLabel: string;
}

/**
 * L0 intake is deliberately shown as absent rather than omitted.
 *
 * `ledger_intake` has a random primary key so there is no hot row, and it is not part of
 * the `ledger` read contract: the console never sees it. Drawing the chain without it
 * would let a reader think the sequencer's input stage does not exist. Drawing it with a
 * null count says what is true — this surface cannot see it from here.
 */
export function chainLayers(payload: LedgerPayload, recomputedRootHex: string | null): ChainLayer[] {
  const head = [...payload.checkpoints].sort((a, b) => a.tree_size - b.tree_size).at(-1) ?? null;
  return [
    {
      level: 'L0',
      title: 'intake',
      count: null,
      purpose:
        'mainline.ledger_intake — random primary key, no hot row. Not part of the ledger read ' +
        'contract, so this surface cannot see it and does not pretend to.',
      digest: null,
      digestLabel: 'not exposed',
    },
    {
      level: 'L1',
      title: 'sequenced leaves',
      count: payload.leaves.length,
      purpose:
        'mainline.ledger_leaf — dense PRIMARY KEY (site_code, seq). Sequenced-ness is derived, ' +
        'never an UPDATE: the whole ledger path is INSERT plus SELECT.',
      digest: payload.leaves.at(-1)?.link_hash_hex ?? null,
      digestLabel: 'head link_hash',
    },
    {
      level: 'L2',
      title: 'RFC 6962 tree',
      count: payload.nodes?.length ?? 0,
      purpose:
        'mainline.ledger_node — tile-addressable interior hashes. Their absence downgrades ' +
        'nothing: this browser recomputes the tree from the leaves.',
      digest: recomputedRootHex,
      digestLabel: 'root recomputed here',
    },
    {
      level: 'L3',
      title: 'signed checkpoint',
      count: payload.checkpoints.length,
      purpose:
        'mainline.ledger_checkpoint — a C2SP tlog-checkpoint note. The ONLY object in this ' +
        'design that leaves our trust boundary, and therefore the only one that is evidence ' +
        'rather than a checksum.',
      digest: head?.root_hex ?? null,
      digestLabel: 'root, signed',
    },
  ];
}

// ── Seals ──────────────────────────────────────────────────────────────────

/** The recomputation a check's seal names, or null when the check hashed nothing. */
export function primaryRecomputation(check: CheckResult): Recomputed | null {
  return check.recomputations.find((entry) => entry.agrees) ?? check.recomputations[0] ?? null;
}

/**
 * A check plus the instant it ran, as seal props.
 *
 * The four states are not cosmetic. `failed` means somebody ran the arithmetic and it
 * disagreed; `unverified` means nobody ran it. Collapsing them would make an unchecked
 * bundle look like a tampered one and — far worse — would teach people to ignore red.
 */
export function sealFor(check: CheckResult, at: string): SealProps {
  const subject = `check ${check.id === 0 ? '—' : check.id}: ${check.name}`;
  if (check.status === 'skip') {
    return { state: 'unverified', subject, reason: firstLine(check.detail) };
  }
  if (check.status === 'fail') {
    return { state: 'failed', subject, reason: firstLine(check.detail) };
  }
  const recomputed = primaryRecomputation(check);
  const recomputation: Recomputation =
    recomputed === null
      ? {
          algorithm: 'structural assertion over the payload — no digest was recomputed',
          at,
          digestPrefix: '(no digest)',
        }
      : {
          algorithm: recomputed.algorithm,
          at,
          digestPrefix: recomputed.computed.slice(0, 16),
        };
  return { state: 'verified', subject, recomputation };
}

/** The report as one seal, for the header. */
export function overallSeal(report: CheckReport | null, at: string): SealProps {
  if (report === null) {
    return {
      state: 'unverified',
      subject: 'the custody ledger',
      reason: 'no ledger payload has reached this browser, so nothing has been recomputed.',
    };
  }
  if (report.overall === 'fail') {
    return { state: 'failed', subject: 'the custody ledger', reason: report.summary };
  }
  if (report.overall === 'bounded') {
    return { state: 'unverified', subject: 'the custody ledger', reason: report.summary };
  }
  return {
    state: 'verified',
    subject: 'the custody ledger',
    recomputation: {
      algorithm: `every implemented check, via ${report.oracleName}`,
      // The report's own instant wins; the caller's is a fallback for a report that was
      // built without a clock, which must still not be able to render an empty slot.
      at: report.at === '' ? at : report.at,
      digestPrefix: primaryRecomputation(report.checks[0] ?? emptyCheck())?.computed.slice(0, 16) ?? '(none)',
    },
  };
}

function emptyCheck(): CheckResult {
  return {
    id: 0,
    name: 'none',
    status: 'skip',
    detail: 'no checks ran',
    bounded: null,
    recomputations: [],
    offline: true,
  };
}

function firstLine(detail: string): string {
  return detail.split('\n')[0] ?? detail;
}

// ── Counters ───────────────────────────────────────────────────────────────

export interface CheckTally {
  readonly pass: number;
  readonly fail: number;
  readonly skip: number;
  readonly bounded: number;
  /** Checks that need no access to our database and no cooperation from us. */
  readonly offline: number;
}

export function tally(report: CheckReport | null): CheckTally {
  if (report === null) return { pass: 0, fail: 0, skip: 0, bounded: 0, offline: 0 };
  return {
    pass: report.checks.filter((check) => check.status === 'pass').length,
    fail: report.checks.filter((check) => check.status === 'fail').length,
    skip: report.checks.filter((check) => check.status === 'skip').length,
    bounded: report.checks.filter((check) => check.bounded !== null).length,
    offline: report.checks.filter((check) => check.offline).length,
  };
}

// ── WHICH checks disagreed, and against WHICH checkpoint ───────────────────

/**
 * THE BARE RED IS THE DEFECT THIS SECTION EXISTS TO END.
 *
 * `CheckReport.summary` is written for the honesty chrome and reads, verbatim,
 * *"4 check(s) FAILED in this browser; 6 were not run."* That sentence is TRUE and it stays
 * on screen exactly as the verifier wrote it — but a judge who reads it has been told a
 * count and nothing else: not which claims disagreed, and not which of the three checkpoints
 * this payload carries they disagreed about. A red with no subject reads as "this product is
 * broken"; a red that names `check 2 inclusion_proof` and `the checkpoint at tree_size 1`
 * reads as a finding somebody can act on, and it is the SAME red.
 *
 * So nothing here weakens, hides, skips or exempts a single check. Every function below is a
 * pure reading of the report the worker produced:
 *
 *   • the checks named are the ones whose `status` the verifier set to `fail` or `skip`;
 *   • the sentence quoted per finding is the verifier's own `detail`, first line, verbatim;
 *   • the checkpoint attribution is a JOIN, not a parse — see {@link checkpointsNamedBy}.
 *
 * The count and the seal are untouched: `tally` still counts every check, `overallSeal` still
 * carries the verifier's summary word for word, and a screen showing this band still shows
 * `verification FAILED` above it.
 */

/** One checkpoint a finding names, identified the way the ledger identifies it. */
export interface CheckpointRef {
  readonly treeSize: number;
  /** First 16 hex characters of the root the checkpoint records. Enough to tell two apart. */
  readonly rootPrefix: string;
  /** The database's own projection. Shown because a finding against an admissible row is worse. */
  readonly admissible: boolean;
}

/** One check that did not pass, with everything a reader needs to chase it. */
export interface CustodyFinding {
  readonly id: number;
  readonly name: string;
  /** `fail` — re-done here and disagreed. `skip` — never attempted. Never collapsed. */
  readonly status: CheckStatus;
  /** The checkpoints this check's own rows name, ascending by tree size. May be empty. */
  readonly checkpoints: readonly CheckpointRef[];
  /** The verifier's own `input` labels for the rows that disagreed, verbatim. */
  readonly rows: readonly string[];
  readonly disagreed: number;
  /** How many rows of this check had something to compare at all. */
  readonly compared: number;
  /** The verifier's `detail`, first line, verbatim. Never paraphrased. */
  readonly firstLine: string;
}

export interface CustodyVerdict {
  /** One sentence naming the checks and the checkpoints. Empty before the report lands. */
  readonly headline: string;
  readonly failures: readonly CustodyFinding[];
  readonly notRun: readonly CustodyFinding[];
  /** Every checkpoint named by a FAILING check, ascending. The subject of the red. */
  readonly implicated: readonly CheckpointRef[];
}

function checkpointRef(checkpoint: LedgerCheckpoint): CheckpointRef {
  return {
    treeSize: checkpoint.tree_size,
    rootPrefix: checkpoint.root_hex.slice(0, 16),
    admissible: checkpoint.admissible,
  };
}

/**
 * The checkpoints one check's rows name — **joined on a digest, never parsed out of prose.**
 *
 * A `Recomputed.claimed` on this screen is the value the payload carried for that row, and
 * for checks 2, 3 and 4 that value IS a checkpoint's `root_hex`: check 2 compares a
 * reconstructed root against the root of the checkpoint at the proof's tree size, check 3
 * against the root of the later checkpoint of the pair, and check 4's root-line row against
 * the root the row records. So the attribution is `claimed === checkpoint.root_hex` — an
 * equality between two 64-character digests, which is either true or false and cannot drift
 * the way `input.endsWith(String(treeSize))` drifted (`noteTextInput`'s docstring records
 * that exact bug: `tree_size 2` matching a row about tree size 12).
 *
 * A FAILING check names only the checkpoints its DISAGREEING rows name — otherwise a check
 * with one bad path would accuse every checkpoint it had ever touched. A SKIPPED check names
 * every checkpoint it filed a row for, because "not attempted" is a statement about all of
 * them; check 4 files one `noteTextInput` row per checkpoint and nothing else, and that row
 * carries an empty `claimed` by design, so it is matched by its own exported label rather
 * than by a digest.
 *
 * Rows that name nothing this payload carries produce NO checkpoint. That is the honest
 * answer — the finding is still rendered, with the verifier's words beside it.
 */
export function checkpointsNamedBy(
  check: CheckResult,
  payload: LedgerPayload | null,
): readonly CheckpointRef[] {
  const checkpoints = payload?.checkpoints ?? [];
  if (checkpoints.length === 0) return [];

  const named = new Map<number, LedgerCheckpoint>();
  for (const checkpoint of checkpoints) {
    const byNoteLabel = noteTextInput(checkpoint.tree_size);
    for (const row of check.recomputations) {
      const disagreed = row.claimed !== '' && !row.agrees;
      const matchesDigest = row.claimed === checkpoint.root_hex;
      const matchesLabel = row.input === byNoteLabel;
      if (check.status === 'fail' ? disagreed && matchesDigest : matchesDigest || matchesLabel) {
        named.set(checkpoint.tree_size, checkpoint);
      }
    }
  }
  return [...named.values()]
    .sort((a, b) => a.tree_size - b.tree_size)
    .map((checkpoint) => checkpointRef(checkpoint));
}

function findingFor(check: CheckResult, payload: LedgerPayload | null): CustodyFinding {
  const compared = check.recomputations.filter((row) => row.claimed !== '');
  const disagreeing = compared.filter((row) => !row.agrees);
  return {
    id: check.id,
    name: check.name,
    status: check.status,
    checkpoints: checkpointsNamedBy(check, payload),
    rows: disagreeing.map((row) => row.input),
    disagreed: disagreeing.length,
    compared: compared.length,
    firstLine: firstLine(check.detail),
  };
}

function nameList(findings: readonly CustodyFinding[]): string {
  return findings.map((finding) => `check ${finding.id} ${finding.name}`).join(', ');
}

function checkpointPhrase(refs: readonly CheckpointRef[]): string {
  if (refs.length === 0) {
    return (
      'The rows that disagreed name no checkpoint this payload carries, so this band cannot ' +
      'attribute them to one; each finding below carries the verifier’s own words instead.'
    );
  }
  const [only] = refs;
  if (refs.length === 1 && only !== undefined) {
    return (
      `Every row that disagreed was measured against ONE checkpoint: the one at tree_size ` +
      `${only.treeSize}, root ${only.rootPrefix}… . Every other checkpoint in this payload ` +
      'agreed with the arithmetic run here.'
    );
  }
  const sizes = refs.map((ref) => ref.treeSize).join(', ');
  return `The rows that disagreed were measured against the checkpoints at tree_size ${sizes}.`;
}

/**
 * The report as ONE named sentence, plus the findings behind it.
 *
 * Composed rather than quoted, and that is the one place on this screen where a sentence is
 * this console's rather than the verifier's — so it is composed only out of values the report
 * and the payload carry: check ids, check names, counts, and tree sizes joined on a root
 * digest. It states nothing the two objects do not already state, and it states nothing
 * softer: `DISAGREED` is the word, and a skip is called *never attempted* rather than
 * folded into the same number as a pass.
 */
export function custodyVerdict(
  report: CheckReport | null,
  payload: LedgerPayload | null,
): CustodyVerdict {
  if (report === null) {
    return { headline: '', failures: [], notRun: [], implicated: [] };
  }

  const failures = report.checks
    .filter((check) => check.status === 'fail')
    .map((check) => findingFor(check, payload));
  const notRun = report.checks
    .filter((check) => check.status === 'skip')
    .map((check) => findingFor(check, payload));

  const implicated = new Map<number, CheckpointRef>();
  for (const finding of failures) {
    for (const ref of finding.checkpoints) implicated.set(ref.treeSize, ref);
  }
  const implicatedRefs = [...implicated.values()].sort((a, b) => a.treeSize - b.treeSize);

  const notRunSentence =
    notRun.length === 0
      ? ''
      : ` ${notRun.length} check(s) were never attempted at all — ${nameList(notRun)} — and a ` +
        'check nobody could run is shown here as loudly as one that disagreed.';

  if (failures.length === 0) {
    const headline =
      notRun.length === 0
        ? 'Every implemented check was re-done in this browser and agreed.'
        : `Every check that ran was re-done in this browser and agreed.${notRunSentence}`;
    return { headline, failures, notRun, implicated: implicatedRefs };
  }

  const headline =
    `${failures.length} check(s) were re-done in this browser and DISAGREED: ` +
    `${nameList(failures)}. ${checkpointPhrase(implicatedRefs)}${notRunSentence}`;
  return { headline, failures, notRun, implicated: implicatedRefs };
}

// ── Cosignatures ───────────────────────────────────────────────────────────

export interface QuorumShape {
  readonly treeSize: number;
  readonly cosignatures: number;
  readonly distinctDomains: readonly string[];
  readonly adverse: number;
  readonly openDebt: number;
  /**
   * True exactly when at least one cosignature over the head is declared adverse. It is
   * the ONLY condition under which any surface may discuss split view, and even then only
   * to say that the precondition is now met.
   */
  readonly adversePresent: boolean;
}

export function quorumShape(payload: LedgerPayload): QuorumShape {
  const treeSize = payload.checkpoints.reduce((max, entry) => Math.max(max, entry.tree_size), 0);
  const overHead = (payload.cosignatures ?? []).filter((entry) => entry.tree_size === treeSize);
  const adverse = overHead.filter((entry) => entry.adverse).length;
  return {
    treeSize,
    cosignatures: overHead.length,
    distinctDomains: [...new Set(overHead.map((entry) => entry.trust_domain))].sort(),
    adverse,
    openDebt: (payload.unwitnessed_debt ?? []).filter((debt) => debt.discharged_tree_size === null)
      .length,
    adversePresent: adverse > 0,
  };
}
