// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE RED HAS A SUBJECT — and gaining one costs no check.
 *
 * Measured against the live URL on 2026-08-15 the custody surface reported `5 passed / 4
 * failed / 6 not run` under a bare `verification FAILED`. Every number was true and none of
 * them told a reader WHICH claims disagreed or WHICH of the three checkpoints in the payload
 * they disagreed about. `custodyVerdict` answers both questions out of the report and the
 * payload; this file holds it to two things at once:
 *
 *   1. it NAMES — the check ids, the check names, and the tree size of every checkpoint a
 *      disagreeing row was measured against; and
 *   2. it SUBTRACTS NOTHING — every failing check appears, every skipped check appears, the
 *      verifier's own sentence is quoted verbatim, and no branch anywhere can turn a red
 *      into anything else.
 *
 * The attribution under test is a JOIN, not a parse: a row's `claimed` digest against a
 * checkpoint's `root_hex`. The last case here is the one that matters most — a disagreeing
 * row whose claimed value belongs to NO checkpoint in the payload must be attributed to
 * none, loudly, rather than to the nearest one.
 *
 * This file lives under `tests/unit/verify/` for the reason `custody-screen.test.tsx` gives
 * in its own header: `tests/unit/custody/` belongs to nobody, and creating it would be a
 * path outside this worker's allocation.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { custodyVerdict, checkpointsNamedBy, tally } from '../../../src/features/custody/model';
import { FindingsBand } from '../../../src/features/custody/parts/FindingsBand';
import {
  noteTextInput,
  type CheckReport,
  type CheckResult,
  type CheckStatus,
  type LedgerCheckpoint,
  type LedgerPayload,
  type Recomputed,
} from '../../../src/verify/ledger';

/** A 64-character lowercase hex string that is unmistakably this fixture's. */
function root(marker: string): string {
  return marker.repeat(64).slice(0, 64);
}

const ROOT_1 = root('a1');
const ROOT_2 = root('b2');
const ROOT_4 = root('c4');
/** A root no checkpoint in the payload carries. */
const ROOT_ELSEWHERE = root('d9');

function checkpoint(treeSize: number, rootHex: string, admissible = true): LedgerCheckpoint {
  return {
    site_code: 'fixture-site',
    tree_size: treeSize,
    root_hex: rootHex,
    note: `mainline/fixture-site\n${treeSize}\n${rootHex}\n`,
    canon_src_sha256: root('ee'),
    admissible,
  };
}

function payload(checkpoints: readonly LedgerCheckpoint[]): LedgerPayload {
  return {
    site_code: 'fixture-site',
    checkpoints,
    leaves: [],
    inclusion_proofs: [],
  };
}

function recomputed(over: Partial<Recomputed>): Recomputed {
  return {
    algorithm: 'RFC 6962 §2.1.1 inclusion path (1 sibling)',
    input: 'leaf 0 of 1',
    inputBytes: 64,
    computed: root('11'),
    claimed: ROOT_1,
    agrees: false,
    ...over,
  };
}

function check(
  id: number,
  name: string,
  status: CheckStatus,
  detail: string,
  recomputations: readonly Recomputed[],
): CheckResult {
  return { id, name, status, detail, bounded: null, recomputations, offline: true };
}

function report(checks: readonly CheckResult[]): CheckReport {
  const failed = checks.filter((entry) => entry.status === 'fail').length;
  const skipped = checks.filter((entry) => entry.status === 'skip').length;
  return {
    overall: failed > 0 ? 'fail' : skipped > 0 ? 'bounded' : 'pass',
    checks,
    at: '2026-08-15T00:00:00.000Z',
    oracleName: 'WebCrypto SHA-256',
    summary: `${failed} check(s) FAILED in this browser; ${skipped} were not run.`,
  };
}

/** The shape the live payload has: three checkpoints, one of which nothing reproduces. */
const THREE = payload([
  checkpoint(1, ROOT_1),
  checkpoint(2, ROOT_2),
  checkpoint(4, ROOT_4),
]);

const INCLUSION_FAIL = check(
  2,
  'inclusion_proof',
  'fail',
  'seq 0 → size 1: recomputed root does not match the checkpoint.\nsecond line, not the first.',
  [
    recomputed({ input: 'leaf 0 of 1', claimed: ROOT_1, agrees: false }),
    recomputed({ input: 'leaf 1 of 2', claimed: ROOT_2, agrees: true }),
    recomputed({ input: 'leaf 3 of 4', claimed: ROOT_4, agrees: true }),
  ],
);

const CONSISTENCY_FAIL = check(
  3,
  'consistency_proof_every_pair',
  'fail',
  '1→2: the proof does not carry the earlier root into the later one.',
  [
    recomputed({
      algorithm: 'RFC 6962 §2.1.2 consistency proof (1 node)',
      input: 'tree 1 → 2',
      claimed: ROOT_2,
      agrees: false,
    }),
    recomputed({
      algorithm: 'RFC 6962 §2.1.2 consistency proof (2 nodes)',
      input: 'tree 2 → 4',
      claimed: ROOT_4,
      agrees: true,
    }),
  ],
);

const SIGNATURE_SKIP = check(
  4,
  'log_signature',
  'skip',
  'a checkpoint note has no empty line, so it has no signature section.',
  [1, 2, 4].map((size) =>
    recomputed({
      algorithm: 'SHA-256(note text) — the exact bytes a checkpoint signature would cover',
      input: noteTextInput(size),
      claimed: '',
      agrees: false,
    }),
  ),
);

const LEAF_PASS = check(1, 'leaf_hash', 'pass', 'every leaf hash reproduces.', [
  recomputed({ input: 'leaf 0', claimed: root('11'), computed: root('11'), agrees: true }),
]);

describe('the verdict names the checks', () => {
  it('names every failing check by id and by name', () => {
    const verdict = custodyVerdict(report([LEAF_PASS, INCLUSION_FAIL, CONSISTENCY_FAIL]), THREE);

    expect(verdict.headline).toContain('check 2 inclusion_proof');
    expect(verdict.headline).toContain('check 3 consistency_proof_every_pair');
    expect(verdict.headline).toContain('DISAGREED');
    expect(verdict.failures.map((finding) => finding.id)).toEqual([2, 3]);
  });

  it('counts exactly what the tally counts — nothing is dropped on the way to the band', () => {
    const settled = report([LEAF_PASS, INCLUSION_FAIL, CONSISTENCY_FAIL, SIGNATURE_SKIP]);
    const verdict = custodyVerdict(settled, THREE);
    const counts = tally(settled);

    expect(verdict.failures).toHaveLength(counts.fail);
    expect(verdict.notRun).toHaveLength(counts.skip);
  });

  it('quotes the verifier’s own first line, verbatim, and does not paraphrase it', () => {
    const verdict = custodyVerdict(report([INCLUSION_FAIL]), THREE);
    expect(verdict.failures[0]?.firstLine).toBe(
      'seq 0 → size 1: recomputed root does not match the checkpoint.',
    );
  });

  it('says which rows disagreed, under the labels the worker filed them under', () => {
    const verdict = custodyVerdict(report([INCLUSION_FAIL, CONSISTENCY_FAIL]), THREE);
    expect(verdict.failures[0]?.rows).toEqual(['leaf 0 of 1']);
    expect(verdict.failures[0]?.compared).toBe(3);
    expect(verdict.failures[1]?.rows).toEqual(['tree 1 → 2']);
  });

  it('names a skipped check as never attempted rather than folding it into a pass', () => {
    const verdict = custodyVerdict(report([LEAF_PASS, SIGNATURE_SKIP]), THREE);
    expect(verdict.notRun.map((finding) => finding.name)).toEqual(['log_signature']);
    expect(verdict.headline).toContain('never attempted');
    expect(verdict.failures).toHaveLength(0);
  });

  it('reports a clean report as clean, with no red anywhere in the sentence', () => {
    const verdict = custodyVerdict(report([LEAF_PASS]), THREE);
    expect(verdict.headline).toBe('Every implemented check was re-done in this browser and agreed.');
    expect(verdict.headline).not.toContain('DISAGREED');
  });

  it('says nothing at all before the worker has answered', () => {
    expect(custodyVerdict(null, THREE).headline).toBe('');
  });
});

describe('the verdict names the checkpoint, by joining digests', () => {
  it('attributes a failing check to the checkpoint whose root the disagreeing row claimed', () => {
    expect(checkpointsNamedBy(INCLUSION_FAIL, THREE).map((ref) => ref.treeSize)).toEqual([1]);
    expect(checkpointsNamedBy(CONSISTENCY_FAIL, THREE).map((ref) => ref.treeSize)).toEqual([2]);
  });

  it('does NOT attribute the checkpoints whose rows agreed', () => {
    const named = checkpointsNamedBy(INCLUSION_FAIL, THREE).map((ref) => ref.treeSize);
    expect(named).not.toContain(2);
    expect(named).not.toContain(4);
  });

  it('attributes a skipped signature check to every checkpoint it filed a row for', () => {
    expect(checkpointsNamedBy(SIGNATURE_SKIP, THREE).map((ref) => ref.treeSize)).toEqual([1, 2, 4]);
  });

  it('attributes a row claiming a root NO checkpoint carries to no checkpoint at all', () => {
    const orphan = check(2, 'inclusion_proof', 'fail', 'the proof is against a root nobody signed.', [
      recomputed({ input: 'leaf 0 of 7', claimed: ROOT_ELSEWHERE, agrees: false }),
    ]);
    expect(checkpointsNamedBy(orphan, THREE)).toEqual([]);

    const verdict = custodyVerdict(report([orphan]), THREE);
    expect(verdict.implicated).toEqual([]);
    expect(verdict.headline).toContain('name no checkpoint this payload carries');
  });

  it('carries the root prefix and the database’s own admissibility projection', () => {
    const [named] = checkpointsNamedBy(INCLUSION_FAIL, payload([checkpoint(1, ROOT_1, false)]));
    expect(named?.rootPrefix).toBe(ROOT_1.slice(0, 16));
    expect(named?.admissible).toBe(false);
  });

  it('survives a payload with no checkpoints without inventing one', () => {
    expect(checkpointsNamedBy(INCLUSION_FAIL, payload([]))).toEqual([]);
    expect(checkpointsNamedBy(INCLUSION_FAIL, null)).toEqual([]);
  });
});

describe('the band a judge reads', () => {
  it('names the checks and the one checkpoint they were measured against', () => {
    render(
      <FindingsBand
        verdict={custodyVerdict(report([LEAF_PASS, INCLUSION_FAIL, SIGNATURE_SKIP]), THREE)}
      />,
    );

    const band = screen.getByTestId('custody-findings');
    expect(band).toHaveAttribute('data-failures', '1');
    expect(band).toHaveAttribute('data-not-run', '1');
    expect(screen.getByTestId('custody-verdict')).toHaveTextContent('check 2 inclusion_proof');
    expect(screen.getByTestId('custody-verdict')).toHaveTextContent('tree_size 1');
    expect(screen.getByTestId('custody-finding-2')).toHaveAttribute('data-status', 'fail');
    expect(screen.getByTestId('custody-finding-4')).toHaveAttribute('data-status', 'skip');
    expect(screen.getByTestId('custody-finding-detail-2')).toHaveTextContent(
      'recomputed root does not match the checkpoint.',
    );
  });

  it('opens in plain words, with no digest and no acronym above the fold', () => {
    render(<FindingsBand verdict={custodyVerdict(report([INCLUSION_FAIL]), THREE)} />);
    const plain = screen.getByTestId('custody-findings-plain').textContent ?? '';

    expect(plain).toContain('did NOT agree');
    expect(plain).not.toContain('RFC');
    expect(plain).not.toContain('inclusion_proof');
    expect(plain).not.toContain(ROOT_1.slice(0, 16));
  });

  it('says which silence a missing checkpoint is — never the same sentence for all three', () => {
    // A check that never ran compared nothing; a failing check that compared nothing against
    // a root is attributed by the verifier's own sentence; and a failing check that compared
    // against a root nobody here carries is the one case where the absence is the finding.
    const noteOnly = check(4, 'log_signature', 'fail', 'a checkpoint note will not parse.', [
      recomputed({ input: noteTextInput(1), claimed: '', agrees: false }),
    ]);
    const orphan = check(2, 'inclusion_proof', 'fail', 'the proof is against a root nobody signed.', [
      recomputed({ input: 'leaf 0 of 7', claimed: ROOT_ELSEWHERE, agrees: false }),
    ]);
    const neverRan = check(5, 'rfc3161_upper_bound', 'skip', 'this verifier implements no ASN.1.', []);

    render(<FindingsBand verdict={custodyVerdict(report([noteOnly, orphan, neverRan]), THREE)} />);

    expect(screen.getByTestId('custody-finding-5').textContent ?? '').toContain(
      'never attempted — so no checkpoint is named',
    );
    expect(screen.getByTestId('custody-finding-4').textContent ?? '').toContain(
      'Nothing in this check was compared against a checkpoint root',
    );
    expect(screen.getByTestId('custody-finding-4').textContent ?? '').toContain(
      'that sentence is the verifier’s and not this band’s',
    );
    expect(screen.getByTestId('custody-finding-2').textContent ?? '').toContain(
      'No checkpoint in this payload carries the value the disagreeing row was compared against',
    );
  });

  it('renders nothing before the worker answers, rather than an empty red box', () => {
    const { container } = render(<FindingsBand verdict={custodyVerdict(null, THREE)} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('never turns a red into anything else: the failing check is still listed as failing', () => {
    render(<FindingsBand verdict={custodyVerdict(report([INCLUSION_FAIL]), THREE)} />);
    const finding = screen.getByTestId('custody-finding-2');
    expect(finding.textContent ?? '').toContain('RE-DONE HERE AND DISAGREED');
    expect(finding.textContent ?? '').not.toContain('expected');
  });
});
