// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The clause diff, as a published interface.
 *
 * The gate surface (`ui/gate-refusal-screen`) embeds `ClauseDiff` beside its refusal bar:
 * the gate says a merge was refused because a clause was weakened, and this panel is what
 * "weakened" meant. Two imports and nothing else:
 *
 * ```tsx
 * import { ClauseDiff, buildClauseDiff } from '../diff';
 *
 * <ClauseDiff model={buildClauseDiff({ clauseUuid, version, parent, delta })} />
 * ```
 *
 * `ClauseDiff` takes no transport, no context and no callback. It is a pure function of
 * one model, which is what lets the gate screen render it from a payload it already
 * fetched, and lets a test render it from a literal.
 *
 * `buildClauseDiff` is exported because the model is worth having on its own: it is the
 * thing the browser spec asserts against, and it carries the findings — including the
 * `witness_guard_expectation` discrepancy — that a caller may want to surface elsewhere.
 *
 * NOT exported: the tokeniser, the LCS, the CAT walker. They are implementation of the
 * model and a second caller would freeze them.
 */

export { ClauseDiff, type ClauseDiffProps } from './ClauseDiff';
export { ClauseDiffScreen, type ClauseDiffScreenProps } from './ClauseDiffScreen';
export { surface } from './surface';
export { buildClauseDiff, comparabilityOf, type BuildOptions } from './engine/build';
export { resolveWitnessField } from './engine/witness';
export { DiffTransportContext, useDiffTransport } from './transport-context';

export type {
  AnchorResidue,
  BoundWitness,
  CatChange,
  CatDiff,
  ClauseDiffInput,
  ClauseDiffModel,
  Comparability,
  Finding,
  FindingCode,
  FindingLevel,
  ScalarChange,
  TextDiff,
  TextSegment,
  UnwitnessedChange,
  WitnessAvailability,
  WitnessBindState,
  WitnessBinding,
  WitnessTarget,
} from './model';
