// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The accessibility package (`docs/leads/ui.md` D14).
 *
 * Register-NEUTRAL, like `src/design/`: every register may import it, so it imports
 * neither restricted group and depends on nothing but the DOM. React is not imported
 * here either — the announcer takes a `Document` and the focus trap takes an `Element`,
 * so the whole package is usable from a Playwright `page.evaluate()` body, from a unit
 * test, and from a component, with the same code.
 *
 * What lives where:
 *
 *   `contract.ts`     the law, as data, with an honest coverage state per line
 *   `contract.doc.ts` the law rendered into docs/accessibility.md
 *   `audit.ts`        the dependency-free DOM auditor and D14's `assertAccessible()` gate
 *   `accname.ts`      the documented subset of accname 1.2 the auditor needs
 *   `roles.ts`        the ARIA 1.2 vocabulary
 *   `focus.ts`        focusability, tab order, the modal trap, roving tabindex
 *   `announce.ts`     the live regions, and the rule that a verbatim value is never
 *                     paraphrased on its way to speech output
 */

export {
  A11Y_LAW,
  BLOCKING_IMPACTS,
  COVERAGE_STATES,
  IMPACTS,
  KEYBOARD_TRAVERSAL,
  MEASURED_COVERAGE,
  SURFACE_OPERATIONS,
  impactRank,
  isBlocking,
  lawById,
  enforcementTokens,
  operationsFor,
  verifyTraversal,
  type A11yLaw,
  type Coverage,
  type Impact,
  type SurfaceOperations,
  type TraversalResult,
  type TraversalStep,
} from './contract';

export {
  NOT_CHECKED_HERE,
  RULES,
  RULE_IDS,
  assertAccessible,
  audit,
  formatReport,
  ruleById,
  snippetOf,
  targetPath,
  type A11yFinding,
  type A11yReport,
  type AuditOptions,
} from './audit';

export { accessibleDescription, accessibleName, isAriaHidden, labelTextFor, visibleTextContent } from './accname';

export {
  applyRovingTabindex,
  createFocusTrap,
  focusableWithin,
  isDisabled,
  isFocusable,
  isHiddenByDom,
  isHiddenFromAssistiveTech,
  isTabbable,
  nextRovingIndex,
  tabOrder,
  tabindexOf,
  type FocusTrap,
  type FocusTrapOptions,
} from './focus';

export { createAnnouncer, verbatimRefusal, type Announcer, type Politeness } from './announce';
