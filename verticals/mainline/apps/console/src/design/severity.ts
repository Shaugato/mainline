// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The severity ramp, banded to `mainline.virulence_class`.
 *
 * ── THE BAND NAMES ARE THE DATABASE'S, NOT OURS ──────────────────────────────────
 *
 * `ARCHITECTURE.md` §5.0 declares:
 *
 *     CREATE TYPE mainline.virulence_class AS ENUM
 *       ('routine','serious','blood_major','blood_fatal');
 *
 * Four values, in that order. The console renders the value it was given, spelled the
 * way the column spells it. It does not translate `blood_fatal` into "critical", and it
 * does not invent a fifth band: a reader who sees `blood_fatal` on screen and greps the
 * schema for it finds the same string, which is the whole point of a verbatim surface.
 *
 * ── WHAT THIS MODULE DELIBERATELY DOES NOT DO ────────────────────────────────────
 *
 * It does NOT band a severity integer into a virulence class. `clause_blame_closure`
 * bands `max_severity` (0–5) into `virulence` exactly once, in the database, and
 * `blocking_check.virulence` is a PROJECTION of that (ARCHITECTURE.md §5, finding S1,
 * MI25). If the console re-derived the band from a severity number it would be
 * computing a gate-relevant value in TypeScript — D5, one hop downstream, and precisely
 * the laundering the schema was shaped to prevent.
 *
 * So: pass the console `virulence` and it renders it. Pass it a severity integer and it
 * renders that too, as a separate fact, in mono, with its own provenance.
 */

/** `mainline.virulence_class`, in the enum's own order. */
export const VIRULENCE_CLASSES = ['routine', 'serious', 'blood_major', 'blood_fatal'] as const;

export type VirulenceClass = (typeof VIRULENCE_CLASSES)[number];

export function isVirulenceClass(value: unknown): value is VirulenceClass {
  return (VIRULENCE_CLASSES as readonly unknown[]).includes(value);
}

export interface SeverityBand {
  readonly virulence: VirulenceClass;
  /** The custom property carrying this band's colour, in both registers. */
  readonly token: string;
  /** Rank within the ramp, 0 = least severe. Used only for ordering assertions. */
  readonly rank: number;
  /**
   * How the band is spoken to a screen reader. The enum value is what is SHOWN — an
   * assistive-technology user gets the same string plus the expansion, never a
   * substitute for it.
   */
  readonly spoken: string;
}

export const SEVERITY_BANDS: readonly SeverityBand[] = [
  {
    virulence: 'routine',
    token: '--tp-sev-routine',
    rank: 0,
    spoken: 'routine — no blood in the ancestry',
  },
  {
    virulence: 'serious',
    token: '--tp-sev-serious',
    rank: 1,
    spoken: 'serious — injury in the ancestry',
  },
  {
    virulence: 'blood_major',
    token: '--tp-sev-blood-major',
    rank: 2,
    spoken: 'blood major — major injury in the ancestry',
  },
  {
    virulence: 'blood_fatal',
    token: '--tp-sev-blood-fatal',
    rank: 3,
    spoken: 'blood fatal — a fatality in the ancestry',
  },
];

export function bandFor(virulence: VirulenceClass): SeverityBand {
  const band = SEVERITY_BANDS.find((entry) => entry.virulence === virulence);
  if (band === undefined) {
    // Unreachable while VIRULENCE_CLASSES and SEVERITY_BANDS agree, which
    // `severity.test.ts` asserts by construction. Throwing beats a default band: a
    // silently-defaulted severity is a mis-stated severity, and this is the one number
    // on the screen that decides what a person is allowed to sign.
    throw new Error(`severity.ts: no band declared for virulence_class "${virulence}".`);
  }
  return band;
}

/** `var(--tp-sev-…)`, ready to drop into a `style` prop or a CSS custom property. */
export function severityVar(virulence: VirulenceClass): string {
  return `var(${bandFor(virulence).token})`;
}

/**
 * THE REDUNDANCY RULE.
 *
 * Colour never carries the band alone. Every surface that colours something by
 * virulence must also render the band's name as text, because:
 *
 *   • the printed exhibit may be photocopied in monochrome;
 *   • a dichromat reads the ramp by lightness, which is monotone but compressed; and
 *   • a screenshot outlives the stylesheet that gave it meaning.
 *
 * `severity.test.ts` measures the dichromatic lightness separation of the ramp and
 * asserts a floor, but that floor is a SUPPORT for this rule, not a substitute for it.
 * The `SeverityBand` primitive renders the name unconditionally and has no prop that
 * can turn it off.
 */
export const SEVERITY_IS_NEVER_COLOUR_ALONE = true as const;
