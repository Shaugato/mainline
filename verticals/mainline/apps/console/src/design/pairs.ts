// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CONTRAST CONTRACT — which token may sit on which, and at what floor.
 *
 * `docs/leads/ui.md` D14 makes accessibility a gate. This file is the machine-readable
 * half of that gate: `contrast.test.ts` takes the CROSS PRODUCT of every foreground and
 * every surface declared here, computes WCAG 2.2 and APCA from the literal text of
 * `tokens.css`, and fails below the floor for the foreground's use class.
 *
 * ── WHY THE CROSS PRODUCT, RATHER THAN A LIST OF OBSERVED PAIRS ──────────────────
 *
 * A list of pairs "the primitives actually use today" is correct exactly until a
 * feature worker drops a `ProvenanceChip` onto a surface nobody anticipated — which is
 * the entire point of a primitive. So the contract is stronger and simpler: EVERY text
 * foreground is legible on EVERY surface. Composition then cannot produce an illegal
 * pair, and no future worker has to consult a table before placing a component.
 *
 * `primitives-css.test.ts` closes the other half: every token used as a `color` in the
 * design package's stylesheets must appear in `FOREGROUNDS`, and every token used as a
 * `background` must appear in `SURFACES`. A colour used but not declared fails; a
 * colour declared but unused is reported. Together the two tests mean the contrast gate
 * is total over the package rather than over a list somebody maintained by hand.
 *
 * ── WCAG 2.2 IS THE GATE; APCA IS A RATCHET ──────────────────────────────────────
 *
 * WCAG 2.2 is normative here because it is what D14's axe-core run enforces and what a
 * procurement questionnaire asks about. APCA-W3 is a WCAG 3 working draft; it models
 * dark-mode legibility considerably better than the 2.x luminance ratio and it is
 * noticeably harsher on saturated accents over near-black — which is a real property of
 * this palette and worth knowing about.
 *
 * So APCA floors here are RATCHETS, set at what the palette measures today with a small
 * margin. They cannot certify anything; they can only stop the palette getting worse
 * without somebody noticing. The console does not claim APCA Bronze conformance
 * anywhere, and `docs/visual-language.md` says so in the same words.
 */

/** How a foreground is rendered, which decides its floor. */
export type ContrastUse = 'body' | 'emphasis' | 'nontext' | 'decorative';

export interface ContrastFloor {
  /** WCAG 2.2 contrast ratio floor. Normative. */
  readonly wcag: number;
  /** APCA |Lc| floor, or `null` where APCA does not model the case. Advisory ratchet. */
  readonly apca: number | null;
  readonly rationale: string;
}

export const FLOORS: Readonly<Record<ContrastUse, ContrastFloor>> = Object.freeze({
  body: {
    wcag: 4.5,
    apca: 45,
    rationale:
      'WCAG 2.2 SC 1.4.3 (AA) for text below 18.66px/700 or 24px/400 — which is all prose in this console.',
  },
  emphasis: {
    wcag: 4.5,
    apca: 32,
    rationale:
      'Held to the same 4.5:1 as body even though these tokens are only ever rendered at >= --tp-step-1 and >= --tp-weight-strong, because a severity band is the one label nobody may squint at. The APCA floor is lower because APCA penalises a saturated accent on near-black far harder than the 2.x ratio does, and lowering the WCAG floor to compensate would be gaming the gate.',
  },
  nontext: {
    wcag: 3,
    apca: null,
    rationale:
      'WCAG 2.2 SC 1.4.11 for a boundary that carries meaning — a panel edge, a focus ring, a meter track. APCA does not model non-text contrast and is not asserted.',
  },
  decorative: {
    wcag: 1.2,
    apca: null,
    rationale:
      'A separator that carries no information. SC 1.4.11 does not apply; the floor exists only so the token cannot become invisible and stop separating anything.',
  },
});

export interface ForegroundToken {
  readonly token: string;
  readonly use: ContrastUse;
  /** Where it appears, so a failure names the component rather than the hex value. */
  readonly where: string;
  /**
   * Required only for `decorative`. Naming the exemption in data means an exemption
   * cannot be created by leaving something out — it has to be written down and read.
   */
  readonly exemptionReason?: string;
}

/** Every token the design package uses as a foreground. */
export const FOREGROUNDS: readonly ForegroundToken[] = [
  { token: '--tp-ink', use: 'body', where: 'Mono, ConstraintName, Sqlstate, Digest, Counter value' },
  { token: '--tp-ink-dim', use: 'body', where: 'supporting prose, Digest ellipsis, Meter caption' },
  { token: '--tp-ink-faint', use: 'body', where: 'ProvenanceChip label, Counter label, Meter units' },
  { token: '--tp-sev-routine', use: 'emphasis', where: 'SeverityBand — virulence_class routine' },
  { token: '--tp-sev-serious', use: 'emphasis', where: 'SeverityBand — virulence_class serious' },
  { token: '--tp-sev-blood-major', use: 'emphasis', where: 'SeverityBand — virulence_class blood_major' },
  { token: '--tp-sev-blood-fatal', use: 'emphasis', where: 'SeverityBand — virulence_class blood_fatal' },
  { token: '--tp-refuse', use: 'emphasis', where: 'ConstraintName + Sqlstate in a refusal, VerificationSeal failed' },
  { token: '--tp-refuse-ink', use: 'body', where: 'prose inside a refusal panel' },
  { token: '--tp-warn', use: 'body', where: 'VerificationSeal unverified, StagedBadge, ProvenanceChip staged' },
  { token: '--tp-ok', use: 'body', where: 'VerificationSeal verified — the only green in the console' },
];

/** Every token the design package uses as a background behind text. */
export const SURFACES: readonly string[] = [
  '--tp-bg',
  '--tp-bg-sunken',
  '--tp-bg-raised',
  '--tp-bg-inset',
];

/** Boundary tokens, checked against every surface at the non-text floor. */
export const BOUNDARIES: readonly ForegroundToken[] = [
  { token: '--tp-rule-strong', use: 'nontext', where: 'panel edge, table head, RegisterFrame border' },
  { token: '--tp-focus', use: 'nontext', where: 'the keyboard focus ring' },
  {
    token: '--tp-rule',
    use: 'decorative',
    where: 'row separator inside a table or list',
    exemptionReason:
      'It separates rows that are already separated by position and by content; removing it loses no information, so SC 1.4.11 does not apply. It is floored at 1.2:1 only so it cannot vanish.',
  },
];

export interface DeclaredPair {
  readonly foreground: ForegroundToken;
  readonly background: string;
  readonly floor: ContrastFloor;
}

/**
 * The full cross product — every foreground and boundary against every surface.
 * This is what `contrast.test.ts` iterates; there is no second list anywhere.
 */
export function declaredPairs(): readonly DeclaredPair[] {
  const out: DeclaredPair[] = [];
  for (const foreground of [...FOREGROUNDS, ...BOUNDARIES]) {
    for (const background of SURFACES) {
      out.push({ foreground, background, floor: FLOORS[foreground.use] });
    }
  }
  return out;
}

/**
 * Foregrounds that may only be rendered at emphasis size and weight.
 *
 * `primitives-css.test.ts` asserts that every declaration block using one of these as a
 * `color` also sets `font-weight` to at least `--tp-weight-strong`. That is the half of
 * the emphasis rule a stylesheet can be held to; the size half is carried by the
 * primitives themselves, which have no prop that can shrink them.
 */
export const EMPHASIS_ONLY: readonly string[] = FOREGROUNDS.filter(
  (foreground) => foreground.use === 'emphasis',
).map((foreground) => foreground.token);

/** The minimum numeric font weight that satisfies `--tp-weight-strong`. */
export const EMPHASIS_MIN_WEIGHT = 600;
