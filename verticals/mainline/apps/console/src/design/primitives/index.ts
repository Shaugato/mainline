// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The primitive surface, as a barrel.
 *
 * Nothing new is defined here — a barrel that adds behaviour is a barrel that has to be
 * read. Feature workers import from `src/design` (the package barrel) or from this file;
 * either way they get exactly these components and nothing else.
 */

export { ConstraintName, type ConstraintNameProps } from './ConstraintName';
export { Counter, type CounterDirection, type CounterProps } from './Counter';
export { Digest, type CopyStatus, type DigestProps } from './Digest';
export { Meter, type MeterProps } from './Meter';
export { Mono, type MonoProps } from './Mono';
export { ProvenanceChip, type ProvenanceChipProps } from './ProvenanceChip';
export { RegisterFrame, type RegisterFrameProps } from './RegisterFrame';
export { Rule, type RuleProps } from './Rule';
export { SeverityBand, type SeverityBandProps } from './SeverityBand';
export { Sqlstate, type SqlstateProps } from './Sqlstate';
export { StagedBadge, type StagedBadgeProps } from './StagedBadge';
export {
  VerificationSeal,
  type Recomputation,
  type SealProps,
} from './VerificationSeal';
