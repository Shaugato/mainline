// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The primitive surface, as a barrel.
 *
 * Nothing new is defined here — a barrel that adds behaviour is a barrel that has to be
 * read. Feature workers import from `src/design` (the package barrel) or from this file;
 * either way they get exactly these components and nothing else.
 *
 * ── THE PLAIN-LANGUAGE KIT ───────────────────────────────────────────────────────
 *
 * `PlainBand`, `Disclosure` and `Gloss` are rulings R6 and R8 of
 * `docs/leads/two-audience-ux-plan.md` as components, and the vocabulary they render is
 * re-exported here beside them so a feature worker writes one import rather than three.
 *
 * The one thing NOT re-exported is the detail mode. `?detail=full` is an ADDRESS
 * concern — it is parsed from the location, published by the shell and propagated by every
 * nav link — so `DetailModeContext`, `useDetailMode()` and `hrefWithDetail()` come from
 * `src/app/detail-mode.ts`. Re-exporting them from the design package would put the
 * router's state behind a design import and give it two names.
 */

export { ConstraintName, type ConstraintNameProps } from './ConstraintName';
export { Counter, type CounterDirection, type CounterProps } from './Counter';
export { Digest, type CopyStatus, type DigestProps } from './Digest';
export { Disclosure, type DisclosureProps } from './Disclosure';
export { Gloss, type GlossProps } from './Gloss';
export { Meter, type MeterProps } from './Meter';
export { Mono, type MonoProps } from './Mono';
export { MAX_SENTENCES, PlainBand, type PlainBandProps } from './PlainBand';
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

// ── The vocabulary (R7), beside the components that render it ────────────────────

export {
  FORBIDDEN_WORDS,
  GLOSSED_TERMS,
  GLOSSED_TERM_KEYS,
  PRODUCT_WORDS,
  PRODUCT_WORD_KEYS,
  REFUSED_SUMMARIES,
  SQLSTATE_GLOSSES,
  everySentence,
  forbiddenWordsIn,
  glossFor,
  glossedTerm,
  labelFor,
  productWord,
  sqlstateGloss,
  summaryNamesItsContents,
  type GlossaryKey,
  type GlossedTerm,
  type GlossedTermKey,
  type ProductWord,
  type ProductWordKey,
  type SqlstateGloss,
} from '../glossary';
