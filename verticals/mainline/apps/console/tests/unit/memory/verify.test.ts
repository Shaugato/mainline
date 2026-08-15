// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE FALSIFICATION MATTERS MORE THAN THE PASS.
 *
 * `public/memory-verify.js` exists so that the STORE column of `/memory.html` can say
 * `recomputed` — the one chip the read API is forbidden to emit, because an emitter cannot
 * vouch for a recomputation the reader has not performed. That chip is worth exactly as
 * much as this file's ability to turn red.
 *
 * So the battery below is symmetrical. For every ledger capture available it asserts that
 * every leaf verifies; and then it corrupts one byte of the bytes, and one character of the
 * claimed hash, and asserts that each corruption is CAUGHT — reported as a mismatch, and
 * rendered as an alert carrying both hex strings and NO chip. A verifier that cannot fail
 * is not a verifier, it is a green light with a hash-shaped decal on it.
 *
 * ── WHERE THE BYTES COME FROM ─────────────────────────────────────────────────────────
 *
 * Two sources, both real, each verified independently and never compared to each other:
 *
 * 1. `CAPTURED_LEDGER_LEAVES` below — the `seq`, `entry_kind`, `canon_bytes_b64`,
 *    `leaf_hash_hex`, `prev_link_hash_hex` and `link_hash_hex` of all four leaves of
 *    `GET /v1/ledger` against the deployed Function URL, read at
 *    `observed_at 2026-08-15T11:52:32.039704Z`, transcribed field for field. Six fields of
 *    each leaf and nothing else: the leaf's `payload` object is not an input to the hash,
 *    and a fixture should carry what the thing under test consumes.
 *
 *    **This transcript cannot be forged into a pass.** Every hash below is recomputed from
 *    the base64 beside it at run time. Mistype either one and this file goes red.
 *
 * 2. Every ledger capture `w1-contract` has landed under `fixtures/memory-loop/`, found by
 *    shape (`data.leaves` is a non-empty array) rather than by filename. When that
 *    directory exists it is replayed through the identical battery. The two sources are
 *    NOT asserted equal to each other: the deployed Function URL runs with
 *    `MAINLINE_DEMO_*` overrides, so a capture taken against a local node legitimately
 *    carries different identifiers inside its canonical bytes, and therefore different
 *    hashes. Each capture is internally consistent or it is not; that is the whole claim.
 */

import { beforeAll, describe, expect, it, vi } from 'vitest';

// @ts-expect-error -- `public/` is served verbatim and is deliberately outside the
// TypeScript project: it is a browser ES module with no build step, which is the property
// that keeps it out of the console's entry closure and out of the 136 KB response ceiling.
// The module's shape is re-declared below and every use is checked against that.
import * as memoryVerifyUntyped from '../../../public/memory-verify.js';

// ── The module's shape, declared here because the module itself is untyped ─────────────

interface LeafLike {
  readonly seq?: number;
  readonly entry_kind?: string;
  readonly canon_bytes_b64?: string;
  readonly leaf_hash_hex?: string;
  readonly prev_link_hash_hex?: string;
  readonly link_hash_hex?: string;
}

interface LeafResult {
  readonly seq: number | null;
  readonly entry_kind: string | null;
  readonly claimed_leaf_hash_hex: string | null;
  readonly recomputed_leaf_hash_hex: string | null;
  readonly canon_bytes_length: number | null;
  readonly matched: boolean;
  readonly status: 'match' | 'mismatch' | 'unverifiable';
  readonly reason: string | null;
  readonly rule: string;
}

interface LeavesResult {
  readonly results: readonly LeafResult[];
  readonly total: number;
  readonly matched: number;
  readonly all_matched: boolean;
  readonly rule: string;
}

interface ChainResult {
  readonly total: number;
  readonly failures: readonly { readonly seq: number | null; readonly code: string }[];
  readonly linked: boolean;
  readonly head_link_hash_hex: string | null;
  readonly rule: string;
}

interface MemoryVerifyModule {
  verifyLeaf(leaf: unknown): Promise<LeafResult>;
  verifyLeaves(leaves: unknown): Promise<LeavesResult>;
  verifyChain(leaves: unknown): Promise<ChainResult>;
  selectMemoryLeaves(
    leaves: unknown,
  ): readonly { readonly entry_kind: string; readonly leaf: LeafLike | null }[];
  renderLeafVerification(result: unknown, options?: { readonly pointer?: string }): Element;
  renderChip(kind: unknown, pointer?: unknown): Element | null;
  mountVerification(
    root: Element | null,
    sources: unknown,
  ): Promise<{ readonly results: readonly LeafResult[] }>;
  readonly VERIFY_CELLS: {
    readonly precursor_event_ingested: string;
    readonly blame_closure_computed: string;
  };
  readonly MEMORY_LEAF_KINDS: readonly string[];
  readonly CLASS_NAMES: { readonly chip: string; readonly verifyFailure: string };
  readonly GENESIS_LINK_HASH_HEX: string;
  readonly LEAF_HASH_RULE: string;
}

const mv = memoryVerifyUntyped as MemoryVerifyModule;

/**
 * SubtleCrypto must be the host's, and it must be real.
 *
 * Measured: the jsdom environment this suite runs in (`vitest.config.ts`, `environment:
 * 'jsdom'`) supplies a working `crypto.subtle.digest`, so no shim is installed and
 * `tests/setup.ts` is not touched. This guard exists so that a future environment which
 * withdraws SubtleCrypto turns the file RED rather than turning every `verifyLeaf` into an
 * `unverifiable` that some later assertion might learn to tolerate.
 */
beforeAll(() => {
  if (typeof globalThis.crypto?.subtle?.digest !== 'function') {
    throw new Error(
      'verify.test.ts: this environment has no SubtleCrypto, so nothing below would be ' +
        'computed. Install node:crypto webcrypto onto globalThis here (not in tests/setup.ts) ' +
        'before treating any result in this file as meaningful.',
    );
  }
});

// ── Source 1: the transcript ──────────────────────────────────────────────────────────

const CAPTURED_LEDGER_LEAVES: readonly LeafLike[] = [
  {
    seq: 0,
    entry_kind: 'doc_registered',
    canon_bytes_b64:
      'eyJkb2NfaWQiOiJkZWMwZGUwMC0wMDAzLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJlbnRyeV9raW5kIjoiZG9jX3JlZ2lzdGVyZWQiLCJzaXRlX2NvZGUiOiJkZWMwZGUwMC0wMDAxLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJzb3VyY2UiOiJ2ZXJ0aWNhbHMvbWFpbmxpbmUvZGIvc2VlZHMvZGVtby9kZW1vX3dvcmxkLnNxbCIsInN5bnRoZXRpYyI6dHJ1ZX0=',
    leaf_hash_hex: '032980be3a0d1fb7a62074e18f06b66ae45bb837151ab4bda2ad89948db7bdb2',
    prev_link_hash_hex: '0000000000000000000000000000000000000000000000000000000000000000',
    link_hash_hex: '86b8393ab37b96516e692dca2bbb2e4645e991d037b431c56399c2d94d1a1161',
  },
  {
    seq: 1,
    entry_kind: 'clause_version_committed',
    canon_bytes_b64:
      'eyJjbGF1c2VfdXVpZCI6ImRlYzBkZTAwLTAwMDQtNDAwMC04MDAwLTAwMDAwMDAwMDAwMSIsImVudHJ5X2tpbmQiOiJjbGF1c2VfdmVyc2lvbl9jb21taXR0ZWQiLCJnZW4iOjEsInNpdGVfY29kZSI6ImRlYzBkZTAwLTAwMDEtNDAwMC04MDAwLTAwMDAwMDAwMDAwMSIsInNvdXJjZSI6InZlcnRpY2Fscy9tYWlubGluZS9kYi9zZWVkcy9kZW1vL2RlbW9fd29ybGQuc3FsIiwic3ludGhldGljIjp0cnVlfQ==',
    leaf_hash_hex: '80300ea96180d714ffda6b0b7f40726543ebbae44cadbc3bf83858bf749bb6e6',
    prev_link_hash_hex: '86b8393ab37b96516e692dca2bbb2e4645e991d037b431c56399c2d94d1a1161',
    link_hash_hex: 'afe3289347af801fea3b87552b0d2bc06ecaa250c17144bbc3ff400a9afc8e71',
  },
  {
    seq: 2,
    entry_kind: 'precursor_event_ingested',
    canon_bytes_b64:
      'eyJlbnRyeV9raW5kIjoicHJlY3Vyc29yX2V2ZW50X2luZ2VzdGVkIiwiZXZlbnRfaWQiOiJkZWMwZGUwMC0wMDA1LTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJzaXRlX2NvZGUiOiJkZWMwZGUwMC0wMDAxLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJzb3VyY2UiOiJ2ZXJ0aWNhbHMvbWFpbmxpbmUvZGIvc2VlZHMvZGVtby9kZW1vX3dvcmxkLnNxbCIsInN5bnRoZXRpYyI6dHJ1ZX0=',
    leaf_hash_hex: '6ca2bb9afa88bc988277b51c3b3ce4e5dd02708b14d8af0a32546802e4b0e107',
    prev_link_hash_hex: 'afe3289347af801fea3b87552b0d2bc06ecaa250c17144bbc3ff400a9afc8e71',
    link_hash_hex: 'a19884a1493dc4cc7ebcc0dce175e12893a63fabc6db7f930afb3b722aaf8263',
  },
  {
    seq: 3,
    entry_kind: 'blame_closure_computed',
    canon_bytes_b64:
      'eyJjbGF1c2VfdXVpZCI6ImRlYzBkZTAwLTAwMDQtNDAwMC04MDAwLTAwMDAwMDAwMDAwMSIsImNsb3N1cmVfZ2VuIjowLCJlbnRyeV9raW5kIjoiYmxhbWVfY2xvc3VyZV9jb21wdXRlZCIsInNpdGVfY29kZSI6ImRlYzBkZTAwLTAwMDEtNDAwMC04MDAwLTAwMDAwMDAwMDAwMSIsInNvdXJjZSI6InZlcnRpY2Fscy9tYWlubGluZS9kYi9zZWVkcy9kZW1vL2RlbW9fd29ybGQuc3FsIiwic3ludGhldGljIjp0cnVlfQ==',
    leaf_hash_hex: '6e3fb05782687e1d924a5f192f3636301eb5f0f8f056f02d13237184658ded59',
    prev_link_hash_hex: 'a19884a1493dc4cc7ebcc0dce175e12893a63fabc6db7f930afb3b722aaf8263',
    link_hash_hex: '1fdaf40518c1e8cff296b897521c78c0cfe57ce32b6f7691fe15e06aa083f182',
  },
];

// ── Source 2: whatever w1-contract has captured ───────────────────────────────────────

interface LedgerSource {
  readonly label: string;
  readonly leaves: readonly LeafLike[];
}

/**
 * Read through Vite's own glob, root-absolute, exactly as `tests/unit/data/_support.ts`
 * reads the sealed bundles: the unit project's `types` list is `["vite/client",
 * "vitest/globals"]` on purpose — the application must not be able to reach a Node global
 * by accident — and that list is not this worker's to widen.
 *
 * A glob that matches nothing yields `{}`. So a fixture directory `w1-contract` has not
 * landed yet is an empty record rather than an exception, and the battery still runs
 * against the transcript.
 */
const FIXTURE_RAW = import.meta.glob<string>('/fixtures/memory-loop/**/*.json', {
  query: '?raw',
  import: 'default',
  eager: true,
});

/**
 * A ledger capture is recognised BY SHAPE — an envelope whose `data.leaves` is a non-empty
 * array — and never by filename. W1 owns that directory and its naming; a spec that
 * hard-coded `ledger.json` would go quietly green the day the file was called something
 * else, which is the failure mode with no symptom.
 */
function fixtureLedgers(): LedgerSource[] {
  const sources: LedgerSource[] = [];
  for (const [path, raw] of Object.entries(FIXTURE_RAW).sort(([a], [b]) => a.localeCompare(b))) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      continue;
    }
    const leaves = (parsed as { data?: { leaves?: unknown } } | null)?.data?.leaves;
    if (Array.isArray(leaves) && leaves.length > 0) {
      sources.push({ label: path, leaves: leaves as readonly LeafLike[] });
    }
  }
  return sources;
}

const FIXTURE_SOURCES = fixtureLedgers();

const LEDGER_SOURCES: readonly LedgerSource[] = [
  { label: 'GET /v1/ledger transcribed at 2026-08-15T11:52:32Z', leaves: CAPTURED_LEDGER_LEAVES },
  ...FIXTURE_SOURCES,
];

// ── Helpers that corrupt, because corruption is the point ─────────────────────────────

/** Flip one bit of the first canonical byte and re-encode. The bytes are now a lie. */
function corruptCanonBytes(b64: string): string {
  const raw = atob(b64);
  const flipped = String.fromCharCode(raw.charCodeAt(0) ^ 0x01) + raw.slice(1);
  return btoa(flipped);
}

/** Change one hex character of the claimed hash. The claim is now a lie. */
function corruptClaimedHash(hex: string): string {
  const first = hex.startsWith('0') ? '1' : '0';
  return first + hex.slice(1);
}

// ── The battery ───────────────────────────────────────────────────────────────────────

describe.each(LEDGER_SOURCES)('RFC 6962 leaf hashing — $label', ({ leaves }) => {
  it('recomputes every leaf hash from the bytes the server returned', async () => {
    const outcome = await mv.verifyLeaves(leaves);

    expect(outcome.total).toBe(leaves.length);
    expect(outcome.matched).toBe(leaves.length);
    expect(outcome.all_matched).toBe(true);

    // Named individually so a red run says WHICH leaf, not just "3 of 4".
    for (const result of outcome.results) {
      expect(`${String(result.entry_kind)}:${result.status}`).toBe(
        `${String(result.entry_kind)}:match`,
      );
      expect(result.recomputed_leaf_hash_hex).toBe(result.claimed_leaf_hash_hex);
      expect(result.canon_bytes_length).toBeGreaterThan(0);
    }
  });

  it('carries both memory leaves, found by entry_kind, and both verify', async () => {
    const selected = mv.selectMemoryLeaves(leaves);
    expect(selected.map((entry) => entry.entry_kind)).toStrictEqual([
      'precursor_event_ingested',
      'blame_closure_computed',
    ]);

    for (const { entry_kind: kind, leaf } of selected) {
      expect(leaf, `the ledger carries no ${kind} leaf`).not.toBeNull();
      const result = await mv.verifyLeaf(leaf);
      expect(result.entry_kind).toBe(kind);
      expect(result.matched).toBe(true);
    }
  });

  it('CATCHES a corrupted canonical byte — the whole reason this runs in the browser', async () => {
    for (const leaf of leaves) {
      const tampered: LeafLike = {
        ...leaf,
        canon_bytes_b64: corruptCanonBytes(leaf.canon_bytes_b64 ?? ''),
      };
      const result = await mv.verifyLeaf(tampered);

      expect(result.status).toBe('mismatch');
      expect(result.matched).toBe(false);
      expect(result.recomputed_leaf_hash_hex).not.toBe(result.claimed_leaf_hash_hex);
      expect(result.claimed_leaf_hash_hex).toBe(leaf.leaf_hash_hex);
      expect(result.reason).toContain('do not hash');
    }
  });

  it('CATCHES a corrupted claimed hash', async () => {
    for (const leaf of leaves) {
      const tampered: LeafLike = {
        ...leaf,
        leaf_hash_hex: corruptClaimedHash(leaf.leaf_hash_hex ?? ''),
      };
      const result = await mv.verifyLeaf(tampered);

      expect(result.status).toBe('mismatch');
      expect(result.matched).toBe(false);
      expect(result.recomputed_leaf_hash_hex).toBe(leaf.leaf_hash_hex);
    }
  });

  it('re-derives the link chain: SHA-256(prev_link_hash || leaf_hash), genesis included', async () => {
    const chain = await mv.verifyChain(leaves);
    expect(chain.failures).toStrictEqual([]);
    expect(chain.linked).toBe(true);
    expect(chain.total).toBe(leaves.length);
  });

  it('CATCHES a leaf lifted out of the chain', async () => {
    const withoutSecond = [...leaves.slice(0, 1), ...leaves.slice(2)];
    const chain = await mv.verifyChain(withoutSecond);
    expect(chain.linked).toBe(false);
    expect(chain.failures.map((failure) => failure.code)).toContain(
      'prev_link_hash_does_not_name_predecessor',
    );
  });
});

describe('the transcript itself', () => {
  it('is the four leaves the deployed ledger returned, two of them the memory writes', () => {
    expect(CAPTURED_LEDGER_LEAVES).toHaveLength(4);
    expect(CAPTURED_LEDGER_LEAVES.map((leaf) => leaf.entry_kind)).toStrictEqual([
      'doc_registered',
      'clause_version_committed',
      'precursor_event_ingested',
      'blame_closure_computed',
    ]);
    expect(CAPTURED_LEDGER_LEAVES[0]?.prev_link_hash_hex).toBe(mv.GENESIS_LINK_HASH_HEX);
  });

  it('names the two memory kinds the module addresses by kind', () => {
    expect(mv.MEMORY_LEAF_KINDS).toStrictEqual([
      'precursor_event_ingested',
      'blame_closure_computed',
    ]);
  });
});

describe('the fixture directory w1-contract owns', () => {
  it('holds at least one ledger capture as soon as it holds anything', () => {
    const captured = Object.keys(FIXTURE_RAW);
    if (captured.length === 0) {
      // Not landed yet. The battery above still ran, against the transcript, so nothing
      // in this file is green for want of having been checked.
      expect(FIXTURE_SOURCES).toHaveLength(0);
      return;
    }
    expect(
      FIXTURE_SOURCES.length,
      `fixtures/memory-loop/ carries ${String(captured.length)} JSON files ` +
        `(${captured.join(', ')}) and none of them is an envelope whose data.leaves is a ` +
        `non-empty array`,
    ).toBeGreaterThan(0);
  });
});

describe('the hash rule, pinned against an independent implementation', () => {
  /**
   * A known answer, computed by Python's `hashlib` — a different SHA-256 implementation in
   * a different runtime — so that this file does not check `crypto.subtle` against itself.
   */
  it('is SHA-256 of 0x00 concatenated with the entry bytes', async () => {
    const result = await mv.verifyLeaf({
      seq: 0,
      entry_kind: 'known_answer',
      canon_bytes_b64: btoa('abc'),
      leaf_hash_hex: '609f6e36d2405585188d5cfd761f407c7cc46a7d3f314c88270469dde315fcd1',
    });
    expect(result.status).toBe('match');
    expect(result.canon_bytes_length).toBe(3);
  });

  it('is NOT the bare SHA-256 of the entry bytes — the 0x00 prefix is load-bearing', async () => {
    const result = await mv.verifyLeaf({
      seq: 0,
      entry_kind: 'known_answer',
      canon_bytes_b64: btoa('abc'),
      // SHA-256("abc"), the textbook digest, without RFC 6962's leaf prefix.
      leaf_hash_hex: 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    });
    expect(result.status).toBe('mismatch');
  });
});

describe('a leaf that cannot be verified is never reported as one that was', () => {
  it.each([
    ['no leaf at all', null, 'leaf is not an object'],
    ['a leaf with no claimed hash', { seq: 1, canon_bytes_b64: 'YWJj' }, 'leaf_hash_hex'],
    [
      'a leaf with no canonical bytes',
      { seq: 1, leaf_hash_hex: '0'.repeat(64) },
      'canon_bytes_b64',
    ],
    [
      'a truncated hash',
      { seq: 1, canon_bytes_b64: 'YWJj', leaf_hash_hex: 'deadbeef' },
      'leaf_hash_hex',
    ],
  ])('reports %s as unverifiable, not as a match', async (_label, leaf, reasonFragment) => {
    const result = await mv.verifyLeaf(leaf);
    expect(result.status).toBe('unverifiable');
    expect(result.matched).toBe(false);
    expect(result.reason).toContain(reasonFragment);
  });

  it('does not call an empty ledger verified', async () => {
    const outcome = await mv.verifyLeaves([]);
    expect(outcome.total).toBe(0);
    expect(outcome.all_matched).toBe(false);
  });
});

describe('rendering — a failure is loud, and it never wears the chip', () => {
  const chipSelector = `.${mv.CLASS_NAMES.chip}`;

  it('renders a match with the recomputed chip and the FULL hash, not an ellipsis', async () => {
    const leaf = CAPTURED_LEDGER_LEAVES[2];
    const result = await mv.verifyLeaf(leaf);
    const element = mv.renderLeafVerification(result, { pointer: '/data/leaves/2/leaf_hash_hex' });

    expect(element.getAttribute('data-verify')).toBe('match');
    expect(element.getAttribute('role')).toBeNull();

    const chip = element.querySelector(chipSelector);
    expect(chip?.getAttribute('data-kind')).toBe('recomputed');
    expect(chip?.textContent).toContain('recomputed in this browser from signed bytes');
    expect(chip?.textContent).toContain('/data/leaves/2/leaf_hash_hex');

    const hash = element.querySelector('[data-hash="recomputed"]');
    expect(hash?.textContent).toBe(leaf?.leaf_hash_hex);
    expect(element.textContent).not.toContain('…');
  });

  it('renders a mismatch as an alert carrying BOTH hashes and NO chip', async () => {
    const leaf = CAPTURED_LEDGER_LEAVES[3];
    const result = await mv.verifyLeaf({
      ...leaf,
      canon_bytes_b64: corruptCanonBytes(leaf?.canon_bytes_b64 ?? ''),
    });
    const element = mv.renderLeafVerification(result, { pointer: '/data/leaves/3/leaf_hash_hex' });

    expect(element.getAttribute('data-verify')).toBe('mismatch');
    expect(element.getAttribute('role')).toBe('alert');
    expect(element.className).toContain(mv.CLASS_NAMES.verifyFailure);
    expect(element.textContent).toContain('LEAF HASH DOES NOT VERIFY');

    // The claim and the truth, side by side, both in full.
    expect(element.querySelector('[data-hash="claimed"]')?.textContent).toBe(leaf?.leaf_hash_hex);
    expect(element.querySelector('[data-hash="recomputed"]')?.textContent).toBe(
      result.recomputed_leaf_hash_hex,
    );

    // THE INVARIANT. `recomputed` asserts that a recomputation succeeded. One did not.
    expect(element.querySelector(chipSelector)).toBeNull();
    expect(element.textContent).not.toContain('recomputed in this browser from signed bytes');
  });

  it('renders an unverifiable leaf loudly too, and still without a chip', async () => {
    const result = await mv.verifyLeaf({ seq: 9, entry_kind: 'precursor_event_ingested' });
    const element = mv.renderLeafVerification(result);

    expect(element.getAttribute('data-verify')).toBe('unverifiable');
    expect(element.getAttribute('role')).toBe('alert');
    expect(element.textContent).toContain('LEAF HASH COULD NOT BE VERIFIED');
    expect(element.querySelector(chipSelector)).toBeNull();
  });

  it('refuses to render anything that is not a verifyLeaf result', () => {
    expect(() => mv.renderLeafVerification({ matched: true })).toThrow(TypeError);
    expect(() => mv.renderLeafVerification(null)).toThrow(TypeError);
  });
});

describe('the two `verify.` cells the shell reserves for this module', () => {
  function panel(): HTMLElement {
    const root = document.createElement('div');
    root.innerHTML =
      `<span data-cell="${mv.VERIFY_CELLS.precursor_event_ingested}"></span>` +
      `<span data-cell="${mv.VERIFY_CELLS.blame_closure_computed}"></span>`;
    return root;
  }

  function cell(root: HTMLElement, id: string): HTMLElement {
    const found = root.querySelector<HTMLElement>(`[data-cell="${id}"]`);
    if (found === null) {
      throw new Error(`the panel carries no cell ${id}`);
    }
    return found;
  }

  const ingestedCell = (root: HTMLElement): HTMLElement =>
    cell(root, mv.VERIFY_CELLS.precursor_event_ingested);
  const closureCell = (root: HTMLElement): HTMLElement =>
    cell(root, mv.VERIFY_CELLS.blame_closure_computed);

  const okLedger = (leaves: readonly LeafLike[]): unknown => ({
    ledger: { state: 'ok', envelope: { data: { leaves } } },
  });

  it('fills both cells from the ledger the loop client already fetched', async () => {
    const root = panel();
    const outcome = await mv.mountVerification(root, okLedger(CAPTURED_LEDGER_LEAVES));

    expect(outcome.results).toHaveLength(2);
    for (const filled of [ingestedCell(root), closureCell(root)]) {
      expect(filled.dataset.filled).toBe('true');
      expect(filled.dataset.error).toBeUndefined();
      expect(filled.querySelector('[data-verify="match"]')).not.toBeNull();
      expect(filled.querySelector(`.${mv.CLASS_NAMES.chip}`)?.getAttribute('data-kind')).toBe(
        'recomputed',
      );
    }

    // The pointer names the leaf's real position in the array it was found in.
    expect(ingestedCell(root).textContent).toContain('/data/leaves/2/leaf_hash_hex');
    expect(closureCell(root).textContent).toContain('/data/leaves/3/leaf_hash_hex');
  });

  it('ISSUES NO REQUEST — the panel owes four GETs and one POST, and this is neither', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    await mv.mountVerification(panel(), okLedger(CAPTURED_LEDGER_LEAVES));
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('paints the failed read into the cell that needed it, never a value', async () => {
    const root = panel();
    const outcome = await mv.mountVerification(root, {
      ledger: { state: 'failed', failure: 'HTTP 503 GET /v1/ledger' },
    });

    expect(outcome.results).toHaveLength(0);
    for (const failed of [ingestedCell(root), closureCell(root)]) {
      expect(failed.dataset.error).toBe('true');
      expect(failed.textContent).toContain('HTTP 503 GET /v1/ledger');
      expect(failed.querySelector(`.${mv.CLASS_NAMES.chip}`)).toBeNull();
    }
  });

  it('says so when the ledger carried no leaf of that kind', async () => {
    const root = panel();
    const withoutClosure = CAPTURED_LEDGER_LEAVES.filter(
      (leaf) => leaf.entry_kind !== 'blame_closure_computed',
    );
    await mv.mountVerification(root, okLedger(withoutClosure));

    expect(ingestedCell(root).querySelector('[data-verify="match"]')).not.toBeNull();
    expect(closureCell(root).dataset.error).toBe('true');
    expect(closureCell(root).textContent).toContain('no blame_closure_computed leaf');
  });

  it('paints the alert, not a value, when a leaf does not verify', async () => {
    const root = panel();
    const tampered = CAPTURED_LEDGER_LEAVES.map((leaf) =>
      leaf.entry_kind === 'precursor_event_ingested'
        ? { ...leaf, canon_bytes_b64: corruptCanonBytes(leaf.canon_bytes_b64 ?? '') }
        : leaf,
    );
    await mv.mountVerification(root, okLedger(tampered));

    const alerted = ingestedCell(root).querySelector('[data-verify="mismatch"]');
    expect(alerted?.getAttribute('role')).toBe('alert');
    expect(ingestedCell(root).querySelector(`.${mv.CLASS_NAMES.chip}`)).toBeNull();
    expect(closureCell(root).querySelector('[data-verify="match"]')).not.toBeNull();
  });
});
