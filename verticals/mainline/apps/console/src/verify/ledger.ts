// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The check suite, run over a `ledger` payload in the reader's own browser.
 *
 * `spec/custody/checks.yaml` is the normative registry of sixteen checks. This module
 * implements the subset that needs no access to our database and no cooperation from us —
 * 1, 2, 3, 4, 7 (bounded), 9, 10 and 13 — and reports the rest as SKIP with a named
 * reason. That subset is not an arbitrary cut: `offline: true` in the registry IS the
 * product claim, and a browser is the most hostile-to-us place it can be demonstrated.
 *
 * ── SKIP IS PRINTED AS LOUDLY AS FAIL ─────────────────────────────────────────────
 *
 * The registry's own words: *a verifier that quietly passes because it did not look is
 * the single worst artefact this domain could ship*. So there are three statuses and no
 * "n/a", every SKIP carries the reason it skipped, and a report containing one cannot
 * render a green summary. `CheckReport.overall` is `pass` only when every implemented
 * check passed AND nothing was skipped; otherwise it is `bounded` or `fail`.
 *
 * ── WHAT THE STAGED FIXTURE DOES TO THIS SCREEN, AND WHY THAT IS CORRECT ──────────
 *
 * `fixtures/bundles/blk-07/` is hand-authored. Its `ledger/bundle.json` says so in its own
 * `notes` member: *running trappoint-verify against it MUST fail, and that failure is the
 * correct outcome*. This module makes no exception for it. The custody surface fed the
 * staged bundle shows RED leaf-hash recomputations, and the screen says why. A verifier
 * with a fixture allowlist is not a verifier.
 */

import { fromBase64, toHex } from './bytes';
import { canonicalise } from './jcs';
import {
  compareCanonSource,
  parseNote,
  parseVerificationKey,
  verifyNote,
  type CheckpointResult,
  type VerificationKey,
} from './checkpoint';
import { NO_ANCHOR, type VerifierConfig } from './config';
import {
  leafHash,
  merkleTreeHash,
  verifyConsistency,
  verifyInclusion,
  verifyLinkChain,
  type ProofOutcome,
} from './rfc6962';
import type { Sha256Oracle } from './sha256';

// ── The payload, as this module reads it ───────────────────────────────────

export interface LedgerCheckpoint {
  readonly site_code: string;
  readonly tree_size: number;
  readonly root_hex: string;
  readonly note: string;
  readonly log_key?: string | null;
  readonly log_sig_b64?: string | null;
  readonly tsa_token_b64?: string | null;
  readonly s3_version?: string | null;
  readonly canon_src_sha256: string;
  readonly admissible: boolean;
  readonly observed_at?: string | null;
}

export interface LedgerLeaf {
  readonly seq: number;
  readonly entry_id: string;
  readonly entry_kind: string;
  readonly subject_id: string;
  readonly payload_ver: number;
  readonly canon_bytes_b64: string;
  readonly payload?: unknown;
  readonly leaf_hash_hex: string;
  readonly link_hash_hex: string;
  readonly prev_link_hash_hex: string;
  readonly is_sandbox: boolean;
  readonly actor: string;
  readonly actor_kind: string;
  readonly recorded_at: string;
  readonly batch_id?: string | null;
}

export interface LedgerInclusionProof {
  readonly seq: number;
  readonly tree_size: number;
  readonly path_hex: readonly string[];
}

export interface LedgerConsistencyProof {
  readonly from_size: number;
  readonly to_size: number;
  readonly path_hex: readonly string[];
}

export interface LedgerCosignature {
  readonly tree_size: number;
  readonly witness_id: string;
  readonly trust_domain: string;
  readonly adverse: boolean;
  readonly sig_b64: string;
  readonly witness_key?: string | null;
  readonly received_at: string;
}

export interface LedgerDebt {
  readonly debt_id: string;
  readonly site_code: string;
  readonly permit_id: string;
  readonly incurred_at: string;
  readonly discharged_tree_size: number | null;
}

export interface LedgerPayload {
  readonly site_code: string;
  readonly checkpoints: readonly LedgerCheckpoint[];
  readonly leaves: readonly LedgerLeaf[];
  readonly nodes?: readonly { readonly level: number; readonly idx: number; readonly hash_hex: string }[];
  readonly inclusion_proofs: readonly LedgerInclusionProof[];
  readonly consistency_proofs?: readonly LedgerConsistencyProof[];
  readonly cosignatures?: readonly LedgerCosignature[];
  readonly unwitnessed_debt?: readonly LedgerDebt[];
}

// ── The report ─────────────────────────────────────────────────────────────

export type CheckStatus = 'pass' | 'fail' | 'skip';

/**
 * One recomputation, in a form the surface can SHOW rather than summarise: what was
 * hashed, what came out, and what it was compared against.
 */
export interface Recomputed {
  /** e.g. `SHA-256(0x00 ‖ canon_bytes)`. */
  readonly algorithm: string;
  /** A short, printable description of the input bytes. */
  readonly input: string;
  readonly inputBytes: number;
  /** What this browser computed, lowercase hex. */
  readonly computed: string;
  /** What the payload claimed, lowercase hex. */
  readonly claimed: string;
  readonly agrees: boolean;
}

export interface CheckResult {
  /** The id in spec/custody/checks.yaml. */
  readonly id: number;
  readonly name: string;
  readonly status: CheckStatus;
  /** Verbatim. Rendered without paraphrase. */
  readonly detail: string;
  /**
   * A load-bearing precondition of the CLAIM that is not met, stated verbatim. Non-null
   * on a PASS means the pass is real and the claim it would support is not.
   */
  readonly bounded: string | null;
  readonly recomputations: readonly Recomputed[];
  /** True when the check needs no access to our database and no cooperation from us. */
  readonly offline: boolean;
}

export type Overall = 'pass' | 'bounded' | 'fail';

export interface CheckReport {
  readonly overall: Overall;
  readonly checks: readonly CheckResult[];
  /** ISO-8601 UTC instant this browser finished. */
  readonly at: string;
  /** Which primitive did the arithmetic — `WebCrypto SHA-256` or the software fallback. */
  readonly oracleName: string;
  /** One line, verbatim, for the honesty chrome. */
  readonly summary: string;
}

// ── The honest limit, verbatim ─────────────────────────────────────────────

/**
 * The split-view sentence, stated once and rendered literally on the custody surface.
 *
 * It is exported as a constant rather than written into JSX so that `custody.spec.ts` can
 * assert the rendered text against THIS string, and so that softening it is a diff in a
 * file whose whole subject is not overclaiming.
 */
export const SPLIT_VIEW_LIMIT =
  'Until an adverse witness runs the cosigning service the quorum is q=1 and split-view ' +
  'resistance is NOT claimed.';

export const PER_BOUND =
  'ANN retrieval is approximate: a Proof of Exhausted Recall proves exhaustion of the ' +
  'retrieval that ran, not of the corpus.';

// ── The suite ──────────────────────────────────────────────────────────────

export interface VerifyLedgerOptions {
  readonly oracle: Sha256Oracle;
  readonly config?: VerifierConfig;
  readonly subtle?: SubtleCrypto | undefined;
  /** Injected so the report is deterministic under cinema mode (D12). */
  readonly now?: () => Date;
}

export async function verifyLedger(
  payload: LedgerPayload,
  options: VerifyLedgerOptions,
): Promise<CheckReport> {
  const { oracle } = options;
  const config = options.config ?? NO_ANCHOR;
  const now = options.now ?? ((): Date => new Date());

  const keys: VerificationKey[] = [];
  const keyFailures: string[] = [];
  for (const vkey of config.logVkeys) {
    try {
      keys.push(await parseVerificationKey(oracle, vkey));
    } catch (error) {
      keyFailures.push(error instanceof Error ? error.message : String(error));
    }
  }

  const leafHashes = new Map<number, Uint8Array>();
  const checks: CheckResult[] = [
    await checkLeafHashes(oracle, payload, leafHashes),
    await checkLinkChain(oracle, payload, leafHashes),
    await checkInclusion(oracle, payload, leafHashes),
    await checkConsistency(oracle, payload),
    await checkLogSignature(oracle, payload, keys, keyFailures, config, options.subtle),
    checkCanonIdentity(payload, config),
    checkNoSandboxLeaf(payload),
    checkWitnessQuorum(payload),
    checkPayloadDiscrepancy(payload),
    ...deferredChecks(),
  ];

  const failed = checks.filter((check) => check.status === 'fail').length;
  const skipped = checks.filter((check) => check.status === 'skip').length;
  const bounded = checks.filter((check) => check.status === 'pass' && check.bounded !== null).length;

  const overall: Overall = failed > 0 ? 'fail' : skipped > 0 || bounded > 0 ? 'bounded' : 'pass';
  const summary =
    failed > 0
      ? `${failed} check(s) FAILED in this browser; ${skipped} were not run.`
      : skipped > 0 || bounded > 0
        ? `every check that ran passed, but ${skipped} were NOT RUN and ${bounded} carry a stated bound. ` +
          'A report containing a SKIP is not a clean report.'
        : 'every implemented check passed, recomputed in this browser.';

  return { overall, checks, at: now().toISOString(), oracleName: oracle.name, summary };
}

// ── Check 1 — leaf hash recomputation ──────────────────────────────────────

async function checkLeafHashes(
  oracle: Sha256Oracle,
  payload: LedgerPayload,
  out: Map<number, Uint8Array>,
): Promise<CheckResult> {
  const recomputations: Recomputed[] = [];
  const disagreements: string[] = [];

  if (payload.leaves.length === 0) {
    return skip(1, 'leaf_hash_recomputation', 'the payload carries no leaves, so nothing was hashed.');
  }

  for (const leaf of payload.leaves) {
    let canonBytes: Uint8Array;
    try {
      canonBytes = fromBase64(leaf.canon_bytes_b64, `leaf ${leaf.seq} canon_bytes_b64`);
    } catch (error) {
      disagreements.push(error instanceof Error ? error.message : String(error));
      continue;
    }
    const computed = await leafHash(oracle, canonBytes);
    out.set(leaf.seq, computed);
    const computedHex = toHex(computed);
    const agrees = computedHex === leaf.leaf_hash_hex;
    recomputations.push({
      algorithm: 'SHA-256(0x00 ‖ canon_bytes)',
      input: `leaf ${leaf.seq} (${leaf.entry_kind}) canon_bytes`,
      inputBytes: canonBytes.byteLength,
      computed: computedHex,
      claimed: leaf.leaf_hash_hex,
      agrees,
    });
    if (!agrees) {
      disagreements.push(
        `leaf ${leaf.seq}: SHA-256(0x00 ‖ canon_bytes) is ${computedHex}, but the row carries ` +
          `${leaf.leaf_hash_hex}.`,
      );
    }
  }

  if (disagreements.length > 0) {
    return {
      id: 1,
      name: 'leaf_hash_recomputation',
      status: 'fail',
      detail:
        `${disagreements.length} of ${payload.leaves.length} leaves do not hash to the value ` +
        `recorded against them.\n${disagreements.join('\n')}`,
      bounded: null,
      recomputations,
      offline: true,
    };
  }

  return {
    id: 1,
    name: 'leaf_hash_recomputation',
    status: 'pass',
    detail:
      `all ${payload.leaves.length} leaves hash to the value recorded against them. The bytes ` +
      'hashed are the carried canon_bytes, never a re-canonicalisation of the parsed payload — ' +
      're-canonicalising would test this console\'s own JSON writer rather than the ledger.',
    bounded: null,
    recomputations,
    offline: true,
  };
}

// ── Check 9 — link chain and density ───────────────────────────────────────

async function checkLinkChain(
  oracle: Sha256Oracle,
  payload: LedgerPayload,
  leafHashes: Map<number, Uint8Array>,
): Promise<CheckResult> {
  if (payload.leaves.length === 0) {
    return skip(9, 'link_chain_and_density', 'the payload carries no leaves.');
  }

  const ordered = [...payload.leaves].sort((a, b) => a.seq - b.seq);
  const rows: {
    seq: number;
    leafHash: Uint8Array;
    linkHash: Uint8Array;
    prevLinkHash: Uint8Array;
  }[] = [];
  for (const leaf of ordered) {
    const computed = leafHashes.get(leaf.seq);
    if (computed === undefined) {
      return {
        id: 9,
        name: 'link_chain_and_density',
        status: 'fail',
        detail: `leaf ${leaf.seq} could not be hashed, so the chain cannot be recomputed past it.`,
        bounded: null,
        recomputations: [],
        offline: true,
      };
    }
    try {
      rows.push({
        seq: leaf.seq,
        // The RECOMPUTED leaf hash, not the carried one. Chaining the carried values
        // would let a substituted leaf pass check 9 after failing check 1.
        leafHash: computed,
        linkHash: hexBytes(leaf.link_hash_hex),
        prevLinkHash: hexBytes(leaf.prev_link_hash_hex),
      });
    } catch (error) {
      return {
        id: 9,
        name: 'link_chain_and_density',
        status: 'fail',
        detail: error instanceof Error ? error.message : String(error),
        bounded: null,
        recomputations: [],
        offline: true,
      };
    }
  }

  const outcome = await verifyLinkChain(oracle, rows);
  const recomputations: Recomputed[] = outcome.computed.map((value, index) => ({
    algorithm: 'SHA-256(prev_link_hash ‖ leaf_hash)',
    input: `leaf ${index}`,
    inputBytes: 64,
    computed: value,
    claimed: rows[index]?.linkHash === undefined ? '' : toHex(rows[index]?.linkHash ?? new Uint8Array()),
    agrees: value === toHex(rows[index]?.linkHash ?? new Uint8Array()),
  }));

  if (!outcome.ok) {
    return {
      id: 9,
      name: 'link_chain_and_density',
      status: 'fail',
      detail: outcome.reason,
      bounded: null,
      recomputations,
      offline: true,
    };
  }
  return {
    id: 9,
    name: 'link_chain_and_density',
    status: 'pass',
    detail:
      `seq is dense from 0 to ${rows.length - 1} and every link hash recomputes. This is the ` +
      'jury-legible half of the argument — entry k names entry k−1 — and it is NOT the half ' +
      'that proves non-omission: a rogue DBA who deletes a leaf, renumbers and re-links ' +
      'produces a chain that recomputes perfectly. Check 3 is what that attack cannot survive.',
    bounded: null,
    recomputations,
    offline: true,
  };
}

// ── Check 2 — inclusion proofs ─────────────────────────────────────────────

async function checkInclusion(
  oracle: Sha256Oracle,
  payload: LedgerPayload,
  leafHashes: Map<number, Uint8Array>,
): Promise<CheckResult> {
  if (payload.inclusion_proofs.length === 0) {
    return skip(
      2,
      'inclusion_proof',
      'the payload carries no inclusion proofs, so no leaf has been shown to be in the tree a ' +
        'checkpoint committed to.',
    );
  }

  const rootsBySize = new Map<number, string>();
  for (const checkpoint of payload.checkpoints) rootsBySize.set(checkpoint.tree_size, checkpoint.root_hex);

  const recomputations: Recomputed[] = [];
  const failures: string[] = [];

  for (const proof of payload.inclusion_proofs) {
    const rootHex = rootsBySize.get(proof.tree_size);
    if (rootHex === undefined) {
      failures.push(
        `the proof for seq ${proof.seq} is against tree_size ${proof.tree_size}, and this payload ` +
          'carries no checkpoint at that size. A proof against a root nobody signed proves nothing.',
      );
      continue;
    }
    const leaf = leafHashes.get(proof.seq);
    if (leaf === undefined) {
      failures.push(`the proof for seq ${proof.seq} names a leaf this payload does not carry.`);
      continue;
    }
    let outcome: ProofOutcome;
    try {
      outcome = await verifyInclusion(oracle, {
        seq: proof.seq,
        treeSize: proof.tree_size,
        leafHash: leaf,
        path: proof.path_hex.map((value) => hexBytes(value)),
        expectedRoot: hexBytes(rootHex),
      });
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error));
      continue;
    }
    recomputations.push({
      algorithm: `RFC 6962 §2.1.1 inclusion path (${proof.path_hex.length} siblings)`,
      input: `leaf ${proof.seq} of ${proof.tree_size}`,
      inputBytes: 32 * (proof.path_hex.length + 1),
      computed: outcome.computedRootHex,
      claimed: rootHex,
      agrees: outcome.ok,
    });
    if (!outcome.ok) failures.push(`seq ${proof.seq} → size ${proof.tree_size}: ${outcome.reason}`);
  }

  if (failures.length > 0) {
    return {
      id: 2,
      name: 'inclusion_proof',
      status: 'fail',
      detail: failures.join('\n'),
      bounded: null,
      recomputations,
      offline: true,
    };
  }
  return {
    id: 2,
    name: 'inclusion_proof',
    status: 'pass',
    detail:
      `${payload.inclusion_proofs.length} inclusion proof(s) reconstruct the checkpoint root. ` +
      'This is the proof that answers "this was never in the log" — a proposition nobody can ' +
      'rebut with a chain, only with a tree.',
    bounded: null,
    recomputations,
    offline: true,
  };
}

// ── Check 3 — consistency, for EVERY consecutive pair ──────────────────────

async function checkConsistency(oracle: Sha256Oracle, payload: LedgerPayload): Promise<CheckResult> {
  const checkpoints = [...payload.checkpoints].sort((a, b) => a.tree_size - b.tree_size);
  if (checkpoints.length < 2) {
    return skip(
      3,
      'consistency_proof_every_pair',
      `this payload carries ${checkpoints.length} checkpoint(s), so there is no consecutive pair ` +
        'to prove consistency between. Nothing here rules out a deletion-and-rewrite between ' +
        'two checkpoints, because there are not two.',
    );
  }

  const proofs = new Map<string, LedgerConsistencyProof>();
  for (const proof of payload.consistency_proofs ?? []) {
    proofs.set(`${proof.from_size}→${proof.to_size}`, proof);
  }

  const recomputations: Recomputed[] = [];
  const failures: string[] = [];

  for (let i = 1; i < checkpoints.length; i += 1) {
    const previous = checkpoints[i - 1];
    const current = checkpoints[i];
    if (previous === undefined || current === undefined) continue;
    const key = `${previous.tree_size}→${current.tree_size}`;
    const proof = proofs.get(key);
    if (proof === undefined) {
      failures.push(
        `no consistency proof for ${key}. The registry requires one for EVERY consecutive pair; ` +
          'a missing pair is exactly where a deletion would be placed.',
      );
      continue;
    }
    let outcome: ProofOutcome;
    try {
      outcome = await verifyConsistency(oracle, {
        from: previous.tree_size,
        to: current.tree_size,
        fromRoot: hexBytes(previous.root_hex),
        toRoot: hexBytes(current.root_hex),
        path: proof.path_hex.map((value) => hexBytes(value)),
      });
    } catch (error) {
      failures.push(`${key}: ${error instanceof Error ? error.message : String(error)}`);
      continue;
    }
    recomputations.push({
      algorithm: `RFC 6962 §2.1.2 consistency proof (${proof.path_hex.length} nodes)`,
      input: `tree ${previous.tree_size} → ${current.tree_size}`,
      inputBytes: 32 * proof.path_hex.length,
      computed: outcome.computedRootHex,
      claimed: current.root_hex,
      agrees: outcome.ok,
    });
    if (!outcome.ok) failures.push(`${key}: ${outcome.reason}`);
  }

  if (failures.length > 0) {
    return {
      id: 3,
      name: 'consistency_proof_every_pair',
      status: 'fail',
      detail: failures.join('\n'),
      bounded: null,
      recomputations,
      offline: true,
    };
  }
  return {
    id: 3,
    name: 'consistency_proof_every_pair',
    status: 'pass',
    detail:
      `every consecutive checkpoint pair (${checkpoints.length - 1} of them) is proved consistent. ` +
      'This is the check that catches "delete leaf k, renumber, recompute every link_hash".',
    bounded: null,
    recomputations,
    offline: true,
  };
}

// ── Check 4 — the log signature ────────────────────────────────────────────

async function checkLogSignature(
  oracle: Sha256Oracle,
  payload: LedgerPayload,
  keys: readonly VerificationKey[],
  keyFailures: readonly string[],
  config: VerifierConfig,
  subtle: SubtleCrypto | undefined,
): Promise<CheckResult> {
  if (payload.checkpoints.length === 0) {
    return skip(4, 'log_signature', 'the payload carries no checkpoints.');
  }
  if (keyFailures.length > 0) {
    return {
      id: 4,
      name: 'log_signature',
      status: 'fail',
      detail: `the configured verification key could not be parsed: ${keyFailures.join('; ')}`,
      bounded: null,
      recomputations: [],
      offline: true,
    };
  }

  const recomputations: Recomputed[] = [];
  const results: CheckpointResult[] = [];
  for (const checkpoint of payload.checkpoints) {
    const result = await verifyNote({
      note: checkpoint.note,
      keys,
      oracle,
      subtle,
    });
    results.push(result);
    recomputations.push({
      algorithm: 'SHA-256(note text) — the bytes the ECDSA P-256 signature covers',
      input: `checkpoint at tree_size ${checkpoint.tree_size}`,
      inputBytes: new TextEncoder().encode(result.note?.signedText ?? checkpoint.note).byteLength,
      computed: result.signedTextSha256,
      claimed: result.note?.rootHex ?? checkpoint.root_hex,
      agrees: result.verdict === 'verified',
    });
    if (result.note !== null && result.note.rootHex !== checkpoint.root_hex) {
      return {
        id: 4,
        name: 'log_signature',
        status: 'fail',
        detail:
          `the checkpoint row records root ${checkpoint.root_hex}, but the SIGNED note text says ` +
          `${result.note.rootHex}. tree_size and root_hex are redundant with the note on purpose; ` +
          'a disagreement between them is a finding, not a formatting difference.',
        bounded: null,
        recomputations,
        offline: true,
      };
    }
    if (result.note !== null && result.note.treeSize !== checkpoint.tree_size) {
      return {
        id: 4,
        name: 'log_signature',
        status: 'fail',
        detail:
          `the checkpoint row records tree_size ${checkpoint.tree_size}, but the SIGNED note text ` +
          `says ${result.note.treeSize}.`,
        bounded: null,
        recomputations,
        offline: true,
      };
    }
  }

  const failed = results.find((result) => result.verdict === 'failed');
  if (failed !== undefined) {
    return {
      id: 4,
      name: 'log_signature',
      status: 'fail',
      detail: failed.reason,
      bounded: null,
      recomputations,
      offline: true,
    };
  }
  const malformed = results.find((result) => result.verdict === 'malformed');
  if (malformed !== undefined) {
    return {
      id: 4,
      name: 'log_signature',
      status: 'fail',
      detail: `a checkpoint note will not parse: ${malformed.reason}`,
      bounded: null,
      recomputations,
      offline: true,
    };
  }
  const skipped = results.find((result) => result.verdict === 'skipped');
  if (skipped !== undefined) {
    return skip(4, 'log_signature', `${skipped.reason}\n\n${config.sourceNote}`, recomputations);
  }

  const selfAsserted = results.some((result) => result.trust === 'self-asserted');
  return {
    id: 4,
    name: 'log_signature',
    status: 'pass',
    detail:
      `every checkpoint note verifies under ECDSA P-256 / SHA-256 against the configured key. ` +
      config.sourceNote,
    bounded: selfAsserted
      ? 'The key used came from the same payload as the checkpoint. A bundle that carries its ' +
        'own trust anchor proves nothing: this is PASS(self-asserted-key), not PASS.'
      : null,
    recomputations,
    offline: true,
  };
}

// ── Check 10 — the canonicaliser's own identity ────────────────────────────

function checkCanonIdentity(payload: LedgerPayload, config: VerifierConfig): CheckResult {
  if (payload.checkpoints.length === 0) {
    return skip(10, 'canonicaliser_identity', 'the payload carries no checkpoints.');
  }
  const findings: string[] = [];
  let unpinned = false;

  for (const checkpoint of payload.checkpoints) {
    // Declared without an initialiser, for the same reason as `capability.ts`'s webgl2
    // probe: both arms below assign, so an `= null` here is written and never read.
    // The `null` that matters is the one the catch chooses — "the note did not parse,
    // therefore this checkpoint names no canonicaliser" — and check 10's whole job is
    // to report that. A silent default in front of it made the two indistinguishable.
    let noteCanon: string | null;
    try {
      noteCanon = parseNote(checkpoint.note).extensions.get('canon') ?? null;
    } catch {
      noteCanon = null;
    }
    if (noteCanon === null) {
      findings.push(
        `the checkpoint at tree_size ${checkpoint.tree_size} carries no parseable canon: ` +
          'extension line, so the code that produced its leaves is not named in the signed bytes.',
      );
      continue;
    }
    const comparison = compareCanonSource(noteCanon, config.canonSrcSha256);
    if (comparison.status === 'mismatch') findings.push(comparison.detail);
    if (comparison.status === 'unpinned') unpinned = true;

    const parsedHex = noteCanon.split(' ')[1] ?? '';
    if (parsedHex !== checkpoint.canon_src_sha256) {
      findings.push(
        `the checkpoint ROW records canon_src_sha256 ${checkpoint.canon_src_sha256}, but the ` +
          `SIGNED note says ${parsedHex}. The signed value is the one that counts.`,
      );
    }
  }

  if (findings.length > 0) {
    return {
      id: 10,
      name: 'canonicaliser_identity',
      status: 'fail',
      detail: findings.join('\n'),
      bounded: null,
      recomputations: [],
      offline: true,
    };
  }
  if (unpinned) {
    return skip(
      10,
      'canonicaliser_identity',
      'the checkpoint names the canonicaliser that produced its leaves, but this console pins ' +
        'no value to compare it against. Comparing the payload\'s claim against itself would be ' +
        'the scheme\'s own code marking its own homework. Set VITE_MAINLINE_CANON_SHA256 from ' +
        'spec/custody/canon-registry.yaml to turn this into a comparison.',
    );
  }
  return {
    id: 10,
    name: 'canonicaliser_identity',
    status: 'pass',
    detail:
      'the canonicaliser named in every signed checkpoint is the one this reader pinned. ' +
      'Re-canonicalising an old leaf under a newer version changes this line, and this line is ' +
      'signed.',
    bounded: null,
    recomputations: [],
    offline: true,
  };
}

// ── Check 13 — no sandbox leaf in an evidentiary tree ──────────────────────

function checkNoSandboxLeaf(payload: LedgerPayload): CheckResult {
  const sandbox = payload.leaves.filter((leaf) => leaf.is_sandbox);
  if (sandbox.length > 0) {
    return {
      id: 13,
      name: 'no_sandbox_leaf',
      status: 'fail',
      detail:
        `${sandbox.length} leaf/leaves carry is_sandbox = true (seq ` +
        `${sandbox.map((leaf) => leaf.seq).join(', ')}). No leaf in an evidentiary bundle may be ` +
        'a sandbox write.',
      bounded: null,
      recomputations: [],
      offline: true,
    };
  }
  return {
    id: 13,
    name: 'no_sandbox_leaf',
    status: 'pass',
    detail: `no leaf in this bundle carries is_sandbox = true (${payload.leaves.length} checked).`,
    bounded: null,
    recomputations: [],
    offline: true,
  };
}

// ── Check 7 — witness quorum, bounded ──────────────────────────────────────

function checkWitnessQuorum(payload: LedgerPayload): CheckResult {
  const cosignatures = payload.cosignatures ?? [];
  const largest = payload.checkpoints.reduce((max, c) => Math.max(max, c.tree_size), 0);
  const forHead = cosignatures.filter((cosignature) => cosignature.tree_size === largest);
  const domains = new Set(forHead.map((cosignature) => cosignature.trust_domain));
  const adverse = forHead.filter((cosignature) => cosignature.adverse);
  const openDebt = (payload.unwitnessed_debt ?? []).filter((debt) => debt.discharged_tree_size === null);

  const parts = [
    `${forHead.length} cosignature(s) over tree_size ${largest}, across ${domains.size} trust ` +
      `domain(s) (${[...domains].join(', ') || 'none'}), ${adverse.length} of them declared adverse.`,
    `${openDebt.length} unwitnessed-debt row(s) are open. Going dark stays possible and ` +
      'self-reports: an unreachable witness produces a debt row, never a blocked merge.',
    'The cosignature BYTES have not been verified here: no witness verification key is ' +
      'configured, and cosignature verification is not implemented in this browser.',
  ];

  if (forHead.length === 0) {
    return skip(7, 'witness_quorum', `${parts[1]}\n${parts[0]}`);
  }

  return {
    id: 7,
    name: 'witness_quorum',
    status: 'pass',
    detail: parts.join('\n'),
    bounded:
      adverse.length === 0
        ? SPLIT_VIEW_LIMIT +
          ' Every cosignature above is over our own infrastructure, which is not adverse in the ' +
          'legal sense, so this PASS is about the SET of cosignatures and not about split view.'
        : SPLIT_VIEW_LIMIT,
    recomputations: [],
    offline: true,
  };
}

// ── A3 — payload versus its own canon_bytes ────────────────────────────────

/**
 * Not a numbered registry check: a DISCREPANCY report.
 *
 * `canon_bytes_b64` is what was hashed; `payload` is a convenience rendering for humans.
 * Nothing signs the latter. A substitution attack that rewrote only the readable member
 * would otherwise be invisible — the tree would verify perfectly and the screen would show
 * the attacker's text. Re-canonicalising `payload` and comparing is what turns that into a
 * legible discrepancy.
 *
 * A disagreement is NOT a failure of the ledger, and is deliberately not reported as one:
 * the hashed bytes still hash correctly. It is reported as what it is.
 */
function checkPayloadDiscrepancy(payload: LedgerPayload): CheckResult {
  const withPayload = payload.leaves.filter((leaf) => leaf.payload !== undefined);
  if (withPayload.length === 0) {
    return skip(
      0,
      'payload_vs_canon_bytes',
      'no leaf carries a human-readable payload alongside its canon_bytes, so there is nothing ' +
        'to compare. A leaf with no readable rendering cannot be silently rewritten, but it also ' +
        'cannot be read.',
    );
  }

  const recomputations: Recomputed[] = [];
  const discrepancies: string[] = [];
  const decoder = new TextDecoder('utf-8', { fatal: false });

  for (const leaf of withPayload) {
    let carried: string;
    let recanonicalised: string;
    try {
      carried = decoder.decode(fromBase64(leaf.canon_bytes_b64, `leaf ${leaf.seq}`));
      recanonicalised = decoder.decode(canonicalise(leaf.payload));
    } catch (error) {
      discrepancies.push(`leaf ${leaf.seq}: ${error instanceof Error ? error.message : String(error)}`);
      continue;
    }
    const agrees = carried === recanonicalised;
    recomputations.push({
      algorithm: 'RFC 8785 JCS over the readable payload',
      input: `leaf ${leaf.seq} payload`,
      inputBytes: recanonicalised.length,
      computed: recanonicalised,
      claimed: carried,
      agrees,
    });
    if (!agrees) {
      discrepancies.push(
        `leaf ${leaf.seq}: canonicalising the readable payload gives ${recanonicalised}, but the ` +
          `bytes that were hashed are ${carried}. The tree is unaffected; what you can READ and ` +
          'what was SIGNED are not the same thing.',
      );
    }
  }

  if (discrepancies.length > 0) {
    return {
      id: 0,
      name: 'payload_vs_canon_bytes',
      status: 'fail',
      detail: discrepancies.join('\n'),
      bounded: null,
      recomputations,
      offline: true,
    };
  }
  return {
    id: 0,
    name: 'payload_vs_canon_bytes',
    status: 'pass',
    detail:
      `the readable payload of all ${withPayload.length} leaf/leaves re-canonicalises to exactly ` +
      'the bytes that were hashed. What you can read is what was signed.',
    bounded: null,
    recomputations,
    offline: true,
  };
}

// ── Deferred checks — named, never silently absent ─────────────────────────

/**
 * The registry entries this browser does not implement.
 *
 * They are emitted as explicit SKIPs rather than omitted, because `spec/custody/checks.yaml`
 * rule 3 is that a deferred check must never be reachable as PASS and must never be
 * silently absent. A reader is entitled to see the shape of what was not done.
 */
function deferredChecks(): CheckResult[] {
  return [
    skip(
      5,
      'rfc3161_upper_bound',
      'RFC 3161 timestamp verification needs ASN.1 and X.509 chain building, neither of which ' +
        'this dependency-free browser verifier implements. Run `pipx run trappoint-verify` for ' +
        'the upper time bound.',
    ),
    skip(
      6,
      'beacon_lower_bound',
      'The NIST pulse signature is RSA over SHA-512 with an X.509 certificate, and the drand ' +
        'round is BLS12-381 over G1 — no browser primitive verifies either. The drand ROUND TIME ' +
        'is arithmetic and is shown on the checkpoint panel, but the round\'s own signature is ' +
        'not checked here, so the drand line alone is not a lower bound this page established.',
    ),
    skip(
      8,
      'archive_object_lock',
      'S3 Object Lock verification requires an AWS call. Offline, s3_version is a claim by us ' +
        'about our own archive, and this console labels it as one.',
    ),
    skip(
      11,
      'gate_self_attestation',
      'The pg_get_triggerdef snapshot lives in schema_attestation, which is not in the ledger ' +
        'payload this surface reads. The gate\'s self-attestation is checked by trappoint-verify.',
    ),
    skip(
      12,
      'webauthn_reverification',
      'Re-verifying a WebAuthn assertion needs the enrolled COSE key and the exposure receipt ' +
        'that produced the challenge. Neither is in this payload.',
    ),
    skip(
      14,
      'closure_generation_monotone',
      'Closure generations live in clause_blame_current, not in the custody ledger. The ancestry ' +
        'surface carries the flag; this one cannot check it.',
    ),
  ];
}

// ── Helpers ────────────────────────────────────────────────────────────────

function skip(
  id: number,
  name: string,
  detail: string,
  recomputations: readonly Recomputed[] = [],
): CheckResult {
  return { id, name, status: 'skip', detail, bounded: null, recomputations, offline: true };
}

function hexBytes(value: string): Uint8Array {
  if (!/^[0-9a-f]{64}$/.test(value)) {
    throw new Error(`${JSON.stringify(value)} is not a 64-character lowercase hex digest`);
  }
  const bytes = new Uint8Array(32);
  for (let i = 0; i < 32; i += 1) bytes[i] = Number.parseInt(value.slice(i * 2, i * 2 + 2), 16);
  return bytes;
}

/** Exported for the custody surface's tree diagram: MTH over the recomputed leaves. */
export async function recomputeRoot(
  oracle: Sha256Oracle,
  payload: LedgerPayload,
): Promise<{ readonly rootHex: string; readonly leafCount: number }> {
  const ordered = [...payload.leaves].sort((a, b) => a.seq - b.seq);
  const hashes: Uint8Array[] = [];
  for (const leaf of ordered) {
    hashes.push(await leafHash(oracle, fromBase64(leaf.canon_bytes_b64, `leaf ${leaf.seq}`)));
  }
  return { rootHex: toHex(await merkleTreeHash(oracle, hashes)), leafCount: hashes.length };
}
