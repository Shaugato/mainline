// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `src/design` — the console's visual language, as code.
 *
 * This package is REGISTER-NEUTRAL by construction, and that is the load-bearing fact
 * about it: every register imports these primitives, so if one of them imported
 * `motion` or `@react-three/*`, every EVIDENCE surface in the console would transitively
 * import it while every ESLint rule stayed green. `register-boundary.test.ts` asserts
 * the neutrality directly, because it is the one violation that would be invisible in
 * every feature directory.
 *
 * The spec is `docs/visual-language.md`, and its register and token tables are RENDERED
 * from `registers.ts` rather than written beside it.
 *
 * `tokens.css` is not exported here. It is a global stylesheet, loaded once by
 * `src/main.tsx` through a glob, and importing it from a module would put a second copy
 * of the cascade into whichever chunk did the importing.
 */

export {
  apcaContrast,
  cieLStar,
  fromLinear,
  linearToSrgb,
  oklchToSrgb,
  parseOklch,
  relativeLuminance,
  simulateDichromacy,
  srgbToLinear,
  toHex,
  toLinear,
  wcagContrast,
  type Dichromacy,
  type Oklch,
  type Srgb,
} from './color';

export {
  ABSOLUTE_CEILING_MS,
  DURATION_MS,
  EASING,
  EASING_NAMES,
  EVIDENCE_CEILING_MS,
  INSTRUMENT_CEILING_MS,
  ceilingFor,
  decideMotion,
  transition,
  useMotionAllowed,
  useMotionPolicy,
  type EasingName,
  type MotionRefusal,
} from './motion';

export {
  BOUNDARIES,
  EMPHASIS_MIN_WEIGHT,
  EMPHASIS_ONLY,
  FLOORS,
  FOREGROUNDS,
  SURFACES,
  declaredPairs,
  type ContrastFloor,
  type ContrastUse,
  type DeclaredPair,
  type ForegroundToken,
} from './pairs';

export {
  PROVENANCE_KINDS,
  PROVENANCE_SPOKEN,
  isProvenanceKind,
  type ProvenanceKind,
} from './provenance';

export { RegisterContext, useRegister } from './register-context';

export {
  EVIDENCE_DIRECTORIES,
  EVIDENCE_FLAT_DIRECTORIES,
  GPU_PACKAGES,
  INSTRUMENT_DIRECTORIES,
  MEMORY_DIRECTORIES,
  MOTION_PACKAGES,
  NEUTRAL_DIRECTORIES,
  REGISTERS,
  REGISTER_LAW,
  TOKEN_LAW,
  isRegister,
  lawFor,
  registerBoundaryConfigs,
  tokenAllowedIn,
  tokenRule,
  type Register,
  type RegisterEslintConfig,
  type RegisterLaw,
  type RestrictedPatternGroup,
  type TokenGroup,
  type TokenRule,
} from './registers';

export {
  SEVERITY_BANDS,
  SEVERITY_IS_NEVER_COLOUR_ALONE,
  VIRULENCE_CLASSES,
  bandFor,
  isVirulenceClass,
  severityVar,
  type SeverityBand as SeverityBandToken,
  type VirulenceClass,
} from './severity';

export {
  CLASS_LABEL,
  GATE_PATH_CODES,
  sqlstateClass,
  type SqlstateClass,
} from './sqlstate';

export * from './primitives';
