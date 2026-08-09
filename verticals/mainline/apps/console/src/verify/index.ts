// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The verifier, as a barrel.
 *
 * Nothing new is defined here — a barrel that adds behaviour is a barrel that has to be
 * read. `src/verify/worker.ts` is deliberately NOT re-exported: it is a worker entry point
 * whose module side effect installs a message handler, and importing it through a barrel
 * would drag that side effect into every consumer. Callers reach the worker through
 * `createVerifier()`.
 */

export {
  ByteFormatError,
  concat,
  digestFromHex,
  equalBytes,
  fromBase64,
  fromHex,
  fromUtf8,
  toBase64,
  toHex,
  utf8,
} from './bytes';

export {
  CanonicalisationError,
  CANON_VERSION,
  MAX_DEPTH,
  canonicalise,
  canonicaliseJson,
  canonicaliseToString,
  compareMemberNames,
  es6Number,
  parseJsonStrict,
} from './jcs';

export {
  SOFTWARE_ORACLE,
  resolveSha256,
  sha256HexOf,
  sha256HexOfText,
  sha256Sync,
  webCryptoOracle,
  type DigestBackend,
  type ResolvedOracle,
  type Sha256Oracle,
} from './sha256';

export {
  GENESIS_LINK,
  LEAF_PREFIX,
  NODE_PREFIX,
  consistencyPath,
  inclusionPath,
  largestPowerOfTwoBelow,
  leafHash,
  merkleTreeHash,
  nodeHash,
  verifyConsistency,
  verifyInclusion,
  verifyLinkChain,
  type LinkChainOutcome,
  type ProofOutcome,
  type ProofStep,
} from './rfc6962';

export {
  DRAND_QUICKNET_GENESIS,
  DRAND_QUICKNET_PERIOD,
  EM_DASH,
  NoteFormatError,
  SIGNATURE_TYPE_ECDSA_P256,
  compareCanonSource,
  derToRaw,
  drandRoundTime,
  parseCanonExtension,
  parseDrandExtension,
  parseNote,
  parseVerificationKey,
  rootBytesFromHex,
  verificationKeyFromSpki,
  verifyNote,
  type CanonExtension,
  type CheckpointResult,
  type CheckpointVerdict,
  type DrandExtension,
  type KeyTrust,
  type NoteSignature,
  type ParsedNote,
  type VerificationKey,
} from './checkpoint';

export {
  NO_ANCHOR,
  operatorConfig,
  resolveVerifierConfig,
  type AnchorSource,
  type VerifierConfig,
} from './config';

export {
  PER_BOUND,
  SPLIT_VIEW_LIMIT,
  recomputeRoot,
  verifyLedger,
  type CheckReport,
  type CheckResult,
  type CheckStatus,
  type LedgerCheckpoint,
  type LedgerCosignature,
  type LedgerDebt,
  type LedgerInclusionProof,
  type LedgerLeaf,
  type LedgerPayload,
  type Overall,
  type Recomputed,
} from './ledger';

export {
  compareDecimal,
  verifyBoundary,
  type BoundaryFinding,
  type BoundaryLeaf,
  type BoundaryOutcome,
  type BoundaryStatus,
  type SilenceBoundaryInput,
} from './silenceroot';

export {
  InlineVerifier,
  WorkerVerifier,
  createVerifier,
  type Verifier,
  type VerifierInfo,
  type VerifierTransport,
  type WorkerLike,
} from './client';

export {
  InBrowserBundleVerifier,
  VERIFIER_NAME,
  inBrowserVerifier,
  type InBrowserBundleVerifierOptions,
} from './bundle-verifier';

export { useVerification, type UseVerificationInput, type VerificationState } from './useVerification';
