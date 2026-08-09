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
import type { CheckReport, CheckResult, LedgerPayload, Recomputed } from '../../verify/ledger';

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
