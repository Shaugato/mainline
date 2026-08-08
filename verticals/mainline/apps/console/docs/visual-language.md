<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The visual language

**A spec the build consumes.** Every table below is rendered from `src/design/registers.ts`
by `src/design/registers.doc.ts`, and `tests/unit/design/doc-generated.test.ts` fails if this
file and that code have drifted by one character. Every threshold below is asserted by a test
that reads the literal text of `src/design/tokens.css`. Nothing here is a preference, and
nothing here is a description of what somebody intends to do.

That constraint is the point. `docs/leads/ui.md` §0 makes one claim about this console —
*it re-derives, in the browser, from signed bytes, every claim it displays* — and a design
system that could not be checked would be the one part of the product asserting something on
its own authority.

Authority: `docs/leads/ui.md` §1.1, §1.2, D9, D14, D15, D18; `ARCHITECTURE.md` §5.0 (the
`virulence_class` enum), §11.5 (the Attribution Rule); `spec/errors.md` §1 (the closed
SQLSTATE set).

---

## 0. How each claim in this document is enforced

A design law nobody can violate is worth more than a design law everybody agrees with. Each
row names the file that would go red.

| Claim | Enforced by |
|---|---|
| The register table and token map here match the code | `tests/unit/design/doc-generated.test.ts` |
| Every token is mapped to the registers allowed to use it, with no token missing from either side | `tests/unit/design/tokens.test.ts` |
| Every colour is inside the sRGB gamut in both registers of light | `tests/unit/design/tokens.test.ts` |
| Landing this token set cannot regress the shell's fallback sheet | `tests/unit/design/tokens.test.ts` |
| Every foreground is legible on every surface, in both registers, by WCAG 2.2 and APCA | `tests/unit/design/contrast.test.ts` |
| The severity ramp is monotone, single-hue, and still ordered under protanopia and deuteranopia | `tests/unit/design/severity.test.ts` |
| No EVIDENCE surface reaches `motion` or `@react-three/*`, directly or transitively | `tests/unit/design/register-boundary.test.ts` |
| The design package itself reaches neither — the hole that would be invisible everywhere else | `tests/unit/design/register-boundary.test.ts` |
| The **shipped directory law** refuses a planted import in a real evidence directory, with nothing overridden | `tests/unit/design/register-boundary.test.ts` |
| `eslint.config.js` — the fast half of the boundary — covers every directory the law names | `tests/unit/design/lint-config-agreement.test.ts` |
| No stylesheet declares a duration over its register's ceiling, or an easing outside the set | `tests/unit/design/motion.test.ts` |
| No stylesheet uses a colour the contrast gate has never measured | `tests/unit/design/primitives-css.test.ts` |
| `--tp-ok` — the only green — appears in exactly one declaration block | `tests/unit/design/primitives-css.test.ts` |
| A verified seal cannot be rendered without a recomputation record | the `SealProps` union; `tsc --noEmit` |
| Each primitive refuses what it is supposed to refuse | `tests/unit/design/primitives.test.tsx` |

**PL-2.** Three of those suites carry a committed red case, because a gate that has never
refused anything asserts nothing:

- `tests/unit/design/fixtures/planted/` holds four real modules that import `motion/react`,
  `motion` and `three`. `register-boundary.test.ts` declares that directory an EVIDENCE
  register and requires exactly those four violations — including the transitive one, which
  is the case ESLint structurally cannot catch. Delete one of those imports and the suite
  goes red. (Verified: removing the `motion/react` import fails the named assertion.)
- Those fixtures prove the *walker* works; they do not prove the *shipped directory law* is
  right, because they name their own directory. So `register-boundary.test.ts` also injects a
  module at a path inside a real EVIDENCE directory and passes no options at all —
  `registerOf()` alone decides — and requires the refusal. Verified red by deleting
  `src/features/gate` from `EVIDENCE_DIRECTORIES`: four assertions fail, naming the directory.
  The injection is in memory because those directories belong to other workers and this suite
  may not write into their trees; the walker reads text out of a `Map` and cannot tell the
  difference. The same block requires the identical `three` import to be **permitted** inside
  `render3d/`, so the boundary is a rule rather than a ban.
- `contrast.test.ts` runs its own machinery over a deliberately illegal pair and requires it
  to fail, and checks the arithmetic against published reference values so that a
  self-consistent-but-wrong implementation cannot pass.
- `severity.test.ts` proves the dichromacy simulation is not a no-op by requiring a red and a
  green at matched lightness to collapse under it.

---

## 1. The three registers

Design with gravity is not a mood; it is a partition with a lint. Every module belongs to
exactly one register, the register is decided by the module's **directory**, and the boundary
is a dependency rule enforced in two places that fail independently.

<!-- GENERATED:registers — rendered from src/design/registers.ts. Do not edit by hand. -->

| Register | Gloss | Surfaces | Directories | May not import | Motion ceiling |
|---|---|---|---|---|---|
| **EVIDENCE** | severe — a screen that could be tendered as an exhibit | gate refusal · clause diff · disposition · custody · audit · silence · ancestry ribbon + print exhibit | `src/app/**`<br>`src/data/**`<br>`src/verify/**`<br>`src/features/gate/**`<br>`src/features/diff/**`<br>`src/features/disposition/**`<br>`src/features/custody/**`<br>`src/features/audit/**`<br>`src/features/silence/**`<br>`src/features/ancestry/layout/**`<br>`src/features/ancestry/ribbon/**`<br>`src/features/ancestry/exhibit/**`<br>`src/features/ancestry/*` | `three`<br>`three/**`<br>`@react-three/*`<br>`@react-three/*/**`<br>`motion`<br>`motion/**`<br>`motion-dom`<br>`motion-dom/**`<br>`motion-utils`<br>`motion-utils/**`<br>`framer-motion`<br>`framer-motion/**` | 160 ms |
| **INSTRUMENT** | mechanical — motion is permitted only where the transition IS the fact | the six gate counters · the weld diagram · the reading-floor meter · propagation states | `src/features/propagation/**` | `three`<br>`three/**`<br>`@react-three/*`<br>`@react-three/*/**` | 220 ms |
| **MEMORY** | dimensional — the ancestry walk, and nothing else, ever | the ancestry walk | `src/features/ancestry/render3d/**` | — (nothing; this is the only register that may draw with a GPU) | 220 ms |

<!-- /GENERATED:registers -->

`src/design/**` appears in no register. That is deliberate and it is the most important
structural decision in this package: **the design system is register-neutral**. Every
register imports these primitives, so if `Counter.tsx` imported `motion`, every EVIDENCE
surface in the console would transitively import `motion` while every ESLint rule stayed
green — the boundary would be dead and nothing would say so. So the design package imports
neither restricted group, the two INSTRUMENT components animate with CSS transitions under
`motion.ts`'s policy and no library, and `register-boundary.test.ts` asserts it directly.

`src/features/ancestry` is split rather than assigned. The layout engine, the ribbon and the
print exhibit are EVIDENCE; only `render3d/` is MEMORY. That split is what makes
`BUILD_PLAN.md` §10.2's first cut — `rm -r render3d/` — leave a working console rather than a
hole.

---

## 2. The law of each register

Each sentence is written so that some test can fail on it. A law that cannot fail a test does
not belong in this list, and `register-boundary.test.ts` refuses a register whose law is
shorter than four sentences.

<!-- GENERATED:register-laws — rendered from src/design/registers.ts. Do not edit by hand. -->

### EVIDENCE — severe — a screen that could be tendered as an exhibit

1. Anything the database emitted verbatim is rendered in the mono face, as selectable text, never as an image.
2. No easing over 160 ms, and nothing moves that a screenshot could not reproduce.
3. No depth, no parallax, no gradient, no bloom, no particle, no shadow that implies a light source.
4. One severity accent over one neutral ramp; the accent is banded to mainline.virulence_class and to nothing else.
5. Every number carries a provenance chip naming how the console came to believe it.
6. Fully operable with a keyboard alone and with a screen reader alone, and printable to a court-legible page.
7. May not import a GPU package or a DOM-animation package, transitively or directly.

### INSTRUMENT — mechanical — motion is permitted only where the transition IS the fact

1. A transition is permitted only when the transition itself is the fact being reported — a counter going 1 → 0 is the product working.
2. Linear or a single cubic easing, never a spring, never a bounce, never an overshoot.
3. No transition exceeds 220 ms, and every transition is interruptible.
4. Every transition is skipped entirely under prefers-reduced-motion or a low-power capability signal, and the end state is identical either way.
5. Colour is the EVIDENCE token set unchanged; an instrument does not get its own palette.
6. May not import a GPU package.

### MEMORY — dimensional — the ancestry walk, and nothing else, ever

1. THE STILLNESS RULE — the severity-5 node is the only object in the scene that never moves, never scales, never emits and never responds to hover. Everything else moves past it.
2. The camera runs on rails at constant velocity; no easing into a fatality, no dolly zoom, no orbit.
3. No emissive vocabulary: no bloom, no lens flare, no god rays, no particles, no depth of field.
4. The scene uses FEWER colours than the tables — the neutral ramp plus the single severity accent, and nothing else.
5. No name of any person is ever rendered here (D15 / I15 / the Attribution Rule).
6. Optional by construction: every node and edge in the scene is also in the ribbon DOM, so deleting this register costs texture and no fact.

<!-- /GENERATED:register-laws -->

---

## 3. The token map

Forty-five tokens. `·` is a **refusal**, not an omission: `--tp-ok` is EVIDENCE-only because
the only green in this console is a verification seal a recomputation produced, and a green
reachable from a 3D scene is a green reachable without arithmetic.

`tokens.test.ts` asserts this table and `tokens.css` are in exact bijection in both
directions — a token declared but unmapped fails, and a token mapped but undeclared fails.
A token map that is allowed to be incomplete is a token map that stops being read.

<!-- GENERATED:tokens — rendered from src/design/registers.ts. Do not edit by hand. -->

#### Surfaces

| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |
|---|---|---|---|---|
| `--tp-bg` | the page ground | ✓ | ✓ | ✓ |
| `--tp-bg-sunken` | chrome and footers — beneath the page | ✓ | ✓ | ✓ |
| `--tp-bg-raised` | a panel or card standing on the page | ✓ | ✓ | ✓ |
| `--tp-bg-inset` | a verbatim well: a payload, a plan fragment, a diff hunk | ✓ | ✓ | ✓ |

#### Boundaries

| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |
|---|---|---|---|---|
| `--tp-rule` | a decorative row separator; carries no meaning and is exempt from the 3:1 floor | ✓ | ✓ | ✓ |
| `--tp-rule-strong` | a meaningful boundary: a panel edge, a table head, a section break | ✓ | ✓ | ✓ |

#### Ink

| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |
|---|---|---|---|---|
| `--tp-ink` | primary text | ✓ | ✓ | ✓ |
| `--tp-ink-dim` | secondary text and supporting prose | ✓ | ✓ | ✓ |
| `--tp-ink-faint` | labels, units and captions — never a fact on its own | ✓ | ✓ | ✓ |

#### Severity — banded to `mainline.virulence_class`

| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |
|---|---|---|---|---|
| `--tp-sev-routine` | virulence_class 'routine' — near-neutral, because a routine clause is not an alarm | ✓ | ✓ | ✓ |
| `--tp-sev-serious` | virulence_class 'serious' | ✓ | ✓ | ✓ |
| `--tp-sev-blood-major` | virulence_class 'blood_major' | ✓ | ✓ | ✓ |
| `--tp-sev-blood-fatal` | virulence_class 'blood_fatal' — emphasis weight only, never small body text | ✓ | ✓ | ✓ |

#### States

| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |
|---|---|---|---|---|
| `--tp-refuse` | a refusal: the constraint name, the SQLSTATE, a failed seal — emphasis weight only | ✓ | ✓ | ✓ |
| `--tp-refuse-ink` | prose inside a refusal panel, where the accent would be unreadable at body size | ✓ | ✓ | ✓ |
| `--tp-warn` | unverified, staged, unset — a slot nobody filled must look like one | ✓ | ✓ | ✓ |
| `--tp-ok` | THE ONLY GREEN: the VerificationSeal verified state, and nothing else, ever | ✓ | · | · |
| `--tp-focus` | the keyboard focus ring | ✓ | ✓ | ✓ |

#### Geometry

| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |
|---|---|---|---|---|
| `--tp-focus-width` | focus ring width | ✓ | ✓ | ✓ |
| `--tp-focus-offset` | focus ring offset | ✓ | ✓ | ✓ |
| `--tp-hairline` | the one border width | ✓ | ✓ | ✓ |
| `--tp-radius` | the one corner radius | ✓ | ✓ | ✓ |

#### Type

| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |
|---|---|---|---|---|
| `--tp-sans` | prose — everything the console wrote | ✓ | ✓ | ✓ |
| `--tp-mono` | verbatim — everything the database emitted | ✓ | ✓ | ✓ |
| `--tp-step--1` | caption and label size | ✓ | ✓ | ✓ |
| `--tp-step-0` | body size | ✓ | ✓ | ✓ |
| `--tp-step-1` | emphasis size — the floor for an accent foreground | ✓ | ✓ | ✓ |
| `--tp-step-2` | panel heading | ✓ | ✓ | ✓ |
| `--tp-step-3` | the refusal headline; one per screen at most | ✓ | ✓ | ✓ |
| `--tp-leading-tight` | headings and verbatim blocks | ✓ | ✓ | ✓ |
| `--tp-leading-body` | prose | ✓ | ✓ | ✓ |
| `--tp-weight-regular` | body weight | ✓ | ✓ | ✓ |
| `--tp-weight-medium` | label weight | ✓ | ✓ | ✓ |
| `--tp-weight-strong` | emphasis weight — required wherever an accent is the foreground | ✓ | ✓ | ✓ |
| `--tp-tracking-caps` | tracking for the uppercase label style | ✓ | ✓ | ✓ |

#### Space

| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |
|---|---|---|---|---|
| `--tp-space-1` | 4px | ✓ | ✓ | ✓ |
| `--tp-space-2` | 8px | ✓ | ✓ | ✓ |
| `--tp-space-3` | 12px | ✓ | ✓ | ✓ |
| `--tp-space-4` | 20px | ✓ | ✓ | ✓ |
| `--tp-space-5` | 32px | ✓ | ✓ | ✓ |
| `--tp-space-6` | 52px | ✓ | ✓ | ✓ |

#### Motion

| Token | Purpose | EVIDENCE | INSTRUMENT | MEMORY |
|---|---|---|---|---|
| `--tp-duration-evidence` | 120 ms — under the EVIDENCE 160 ms ceiling | ✓ | ✓ | ✓ |
| `--tp-duration-instrument` | 200 ms — under the INSTRUMENT 220 ms ceiling | · | ✓ | ✓ |
| `--tp-ease-linear` | the default: a measurement does not accelerate | · | ✓ | ✓ |
| `--tp-ease-mechanical` | the ONE permitted cubic; no spring, no bounce, no overshoot | · | ✓ | ✓ |

<!-- /GENERATED:tokens -->

---

## 4. Colour

### 4.1 OKLCH, and what it buys that hex does not

Every colour is authored as `oklch(L C H)`. The severity ramp's defining property is that it
is monotone in lightness and monotone in chroma; in hex that is an opinion, and in OKLCH the
first coordinate *is* perceptual lightness, so the property is visible in the source text and
checkable by parsing it.

Every colour is inside the sRGB gamut, and that is enforced. An out-of-gamut `oklch()` is
gamut-mapped by the browser under a rule that is neither plain clipping nor consistent across
engines — so a contrast number computed from the authored coordinates would be a claim about
a colour nobody is looking at.

### 4.2 Two registers of light, both fully specified

The **dark register is the default** and is stated unconditionally, so a stylesheet load
failure cannot leave the console unstyled. This is control-room software; it is read at 03:00
on a mine site next to a screen showing plant telemetry.

The **light register** exists for one purpose: the printed exhibit. `docs/leads/ui.md` §1.3 —
a court exhibit is a page, not a canvas. It is fully specified rather than derived, because
"invert the dark theme" produces unreadable paper and an unusable photocopy.

It is selected by `@media print`, or explicitly by `<html data-register-theme="light">`. It is
deliberately **not** selected by `prefers-color-scheme: light`: a reader whose operating
system is in light mode has expressed a preference about their operating system, not a request
to be handed the print exhibit. The two light blocks are asserted identical, so reviewing the
print register on screen reviews the print register.

### 4.3 The severity ramp

Banded to `mainline.virulence_class`, which `ARCHITECTURE.md` §5.0 declares as exactly four
values:

```sql
CREATE TYPE mainline.virulence_class AS ENUM
  ('routine','serious','blood_major','blood_fatal');
```

Four bands, one hue, both coordinates monotone:

| Band | Dark register | Light register (print) |
|---|---|---|
| `routine` | `oklch(0.845 0.016 30)` | `oklch(0.535 0.016 30)` |
| `serious` | `oklch(0.775 0.085 30)` | `oklch(0.46 0.088 30)` |
| `blood_major` | `oklch(0.705 0.15 30)` | `oklch(0.385 0.112 30)` |
| `blood_fatal` | `oklch(0.635 0.2 30)` | `oklch(0.31 0.122 30)` |

Severity rises by **deepening and saturating**. The hue never moves: a hue change across a
severity scale encodes rank in the one channel a dichromat cannot read, and it is the single
most common way an otherwise careful palette becomes inaccessible. `routine` is nearly
neutral on purpose — a routine clause is not an alarm, and a palette that shouts at every band
has no way left to shout at the fatal one.

**The redundancy rule.** Colour never carries the band alone. `SeverityBand` always renders
the band's name as text and has no prop that removes it, because a printed exhibit gets
photocopied, a dichromat reads a compressed ramp, and a screenshot outlives the stylesheet
that gave its colours meaning. The dichromacy floors below are a *support* for that rule, not
a substitute for it.

**Measured, both registers, Viénot–Brettel–Mollon (1999):**

| Simulation | Adjacent separation (dark) | Adjacent separation (print) |
|---|---|---|
| none | 9.0 · 9.0 · 8.9 L\* | 9.6 · 9.1 · 8.9 L\* |
| protanopia | 11.7 · 12.2 · 12.2 L\* | 12.8 · 10.7 · 10.3 L\* |
| deuteranopia | 7.7 · 7.6 · 7.6 L\* | 8.2 · 8.5 · 8.5 L\* |

The asserted floor is 4.0 L\* adjacent and 18 L\* across the ramp.

**Stated limit.** That simulation is a model of a *median dichromat*, not a measurement of any
person. It does not cover anomalous trichromacy — which is far more common than dichromacy —
and it does not cover tritanopia, which the 1999 single-matrix form does not model at all.
Nobody with a colour vision deficiency has looked at this palette. That is an unmeasured risk,
recorded here rather than in a commit message.

### 4.4 The severity band is never derived in the browser

The console renders `virulence` as it was given and renders `max_severity` as a separate fact
beside it. It never derives one from the other in either direction.

`clause_blame_closure` bands `max_severity` into `virulence` exactly once, in the database,
and `blocking_check.virulence` is a projection of that (`ARCHITECTURE.md` finding S1, MI25).
A console that re-banded a severity integer would be computing a gate-relevant value in
TypeScript — `docs/leads/ui.md` D5, one hop downstream, and precisely the laundering the
schema was shaped to prevent.

---

## 5. Type

Two faces, and the distinction between them is load-bearing rather than stylistic.

**`--tp-sans` is prose — everything the console wrote.** **`--tp-mono` is verbatim —
everything the database emitted.** A constraint name, a SQLSTATE, a commit id, a digest, a
plan fragment and a payload are always mono. That is the console's only signal for *this
string is not ours*, and it is the reason a reader can look at a refusal screen and know which
words to grep the schema for.

Three rules follow, and all three are asserted by `primitives.test.tsx`:

1. A verbatim value is **real selectable text**. Never an image, never a canvas, never a
   pseudo-element `content:` string. A value a reader cannot copy into a bug report has been
   paraphrased by the medium.
2. A verbatim value is **complete in the DOM**. `Digest` truncates by CSS clip with an
   ellipsis, so a select-all copies all sixty-four characters while twelve are showing. The
   obvious implementation — `display: none` on the tail — removes the value from the
   accessibility tree and from the selection, which turns a verbatim digest into a decorative
   prefix.
3. A verbatim value is **rendered exactly as given**. No case change, no
   underscore-to-space, no friendly rewriting. `docs/leads/ui.md` D18: a prettified refusal is
   a different refusal.

No webfont is shipped and none is fetched. A remote font is a network dependency on a console
whose whole claim is that it works from a static directory with no credentials (D7), and a
bundled font is a licence artefact in a tree where `reuse lint` green is a `G6` checklist
item. `system-ui` resolves to a variable face on every platform this ships to.

---

## 6. Contrast

### 6.1 The floors

| Use | WCAG 2.2 | APCA \|Lc\| | What it covers |
|---|---|---|---|
| `body` | ≥ 4.5 | ≥ 45 | all prose, labels, captions, verbatim values |
| `emphasis` | ≥ 4.5 | ≥ 32 | the severity ramp and `--tp-refuse`, rendered at ≥ `--tp-step-1` and ≥ `--tp-weight-strong` |
| `nontext` | ≥ 3.0 | — | a boundary that carries meaning: a panel edge, a focus ring, a meter track |
| `decorative` | ≥ 1.2 | — | `--tp-rule` only, with its exemption written down in `pairs.ts` |

`contrast.test.ts` takes the **cross product** — every foreground against every surface, in
both registers of light — rather than a list of pairs observed today. A list is correct
exactly until a feature worker drops a `ProvenanceChip` onto a surface nobody anticipated,
which is the entire point of a primitive. The stronger contract is simpler: every text
foreground is legible on every surface, so composition cannot produce an illegal pair.

The other half is closed by `primitives-css.test.ts`: every token used as a `color` in this
package must be in `FOREGROUNDS`, every token used as a `background` must be in `SURFACES`,
and no stylesheet outside `tokens.css` may contain a hex, an `rgb()`, or a named colour. The
gate is therefore total over the package rather than over a list somebody maintains by hand.

Measured worst case: **4.65:1** dark (`--tp-sev-blood-fatal` on `--tp-bg-inset`) and
**4.57:1** light (`--tp-sev-routine` on `--tp-bg-inset`).

### 6.2 WCAG 2.2 is the gate; APCA is a ratchet

WCAG 2.2 is normative here: it is what the axe-core run in `tests/browser/a11y.spec.ts`
enforces and what a procurement questionnaire asks about.

APCA-W3 (0.1.9, the `0.98G-4g` constant set) is a WCAG 3 working draft. It models dark-mode
legibility considerably better than the 2.x luminance ratio, and it is noticeably harsher on a
saturated accent over near-black — which is a real property of this palette and worth knowing
about. `--tp-sev-blood-fatal` measures Lc 36.4 on `--tp-bg-inset` while measuring 4.65:1 under
WCAG 2.2, and the two are both right about different things.

So the APCA floors are **ratchets**: set at what the palette measures today with a margin, so
that it cannot get worse without somebody noticing. They certify nothing. This palette does
not claim APCA-W3 Bronze, and lowering the WCAG floor to make an APCA number look better would
be gaming the gate rather than improving the palette.

### 6.3 Focus

One focus treatment for the whole console, declared once in `tokens.css` as
`:focus-visible { outline: … }`. Keyboard operability is a gate (D14), and a focus ring a
feature worker can accidentally style away is not a gate. No primitive overrides it.

---

## 7. Motion

### 7.1 The rule

Motion is permitted in exactly one circumstance: **the transition is the fact**. A counter of
open blocking checks going 1 → 0 is the product working, and marking that instant reports
something true. A panel sliding in, a card fading up, a number counting for flavour: these
report nothing, cost a frame budget, and make a screenshot an incomplete rendering of the
screen.

### 7.2 The easing set — two entries, and no spring

| Name | Value | When |
|---|---|---|
| `linear` | `linear` | the default |
| `mechanical` | `cubic-bezier(0.2, 0, 0.38, 1)` | the motion of a relay closing |

`linear` is the default and that is a statement rather than laziness: a measurement does not
accelerate, and a counter that eases out is performing a confidence it has not earned.

There is no spring, and `motion.test.ts` refuses one. A spring is parameterised by mass and
stiffness, so its peak depends on the interruption history — an interrupted spring is
non-deterministic under the cinema-mode capture `docs/leads/ui.md` D12 requires. There is no
overshoot either: an overshoot shows a value the data never held, which on an evidentiary
surface is a small lie told sixty times a second.

### 7.3 The ceilings, and how they are enforced

EVIDENCE 160 ms; INSTRUMENT and MEMORY 220 ms. `transition()` **throws** above the ceiling
rather than clamping, because a clamped duration is a policy violation that ships and a thrown
one is a policy violation that fails a unit test the first time it is written.

`motion.test.ts` also parses every stylesheet in this package and refuses:

- any declared duration above 220 ms;
- any literal duration in a `transition` — durations come from `--tp-duration-*` and nowhere
  else, or the value survives a change to the policy; and
- any easing that is not `var(--tp-ease-linear)` or `var(--tp-ease-mechanical)`.

### 7.4 `useMotionAllowed()`

Answers `false` when any of the following holds:

1. `prefers-reduced-motion: reduce` — subscribed **live**, not snapshotted, because a reader
   who turns reduced motion on has usually just been made unwell by something moving and
   telling them to reload is not an answer;
2. the low-power capability probe reports `save-data`, or a `deviceMemory` below 4 GB. An
   *unreported* `deviceMemory` is not low: a browser that does not implement it has told us
   nothing, and inventing a number would be a fabricated claim about the reader's machine;
3. the surrounding register is EVIDENCE.

Its default argument is `'evidence'`. A component that forgot to declare its register gets the
answer that cannot be wrong rather than the answer that is convenient — the same default
`src/app/surfaces.ts` applies to an undeclared surface.

`tokens.css` carries the CSS half of the same rule: a `@media (prefers-reduced-motion: reduce)`
block that kills every transition and animation in the document, including ones added by a
worker who never read this file.

### 7.5 The register is a runtime fact as well as a directory fact

The import boundary decides what a **directory** may depend on. `RegisterFrame` decides what a
component **instance** may do, and those are different questions: `Counter` is one file that is
an INSTRUMENT inside the propagation surface and EVIDENCE inside the refusal bar. The frame
writes `data-register` onto the DOM, so a Playwright spec can assert the law a subtree was
operating under and a captured DOM in an evidence bundle carries the same fact.

---

## 8. The primitives, and what each one refuses

| Primitive | What it refuses |
|---|---|
| `Mono` | rendering a verbatim value as anything but selectable text |
| `ConstraintName` | any prop that could carry a sentence the console composed (D18) |
| `Sqlstate` | showing a code outside `spec/errors.md`'s closed set without saying it is outside it |
| `Digest` | truncating the value in the DOM; going silent when a copy fails |
| `ProvenanceChip` | a fifth kind — there is no `computed`, no `derived`, no `estimated` |
| `VerificationSeal` | `state="verified"` without a `recomputation` record — a **compile** error |
| `StagedBadge` | any prop that makes it quieter |
| `SeverityBand` | removing the band name; deriving the band from a severity integer |
| `Counter` | moving outside an INSTRUMENT frame; tweening the value |
| `Meter` | any colour that means "you failed" — there is no such selector to add a class to |
| `Rule` | a third variant that means "make it look nicer" |
| `RegisterFrame` | nothing; it is how everything above learns which law applies |

Two of those are worth spelling out.

**`VerificationSeal` is a discriminated union, not a component with a boolean.**

```tsx
<VerificationSeal state="verified" />                        // does not compile
<VerificationSeal state="verified" recomputation={{ … }} />   // compiles
```

`docs/leads/ui.md` D6 is the whole design: the console re-derives every claim it displays from
signed bytes. A seal that a caller can turn green by passing `ok={true}` certifies a boolean,
and a boolean is exactly what a React component cannot authenticate. There is no default for
`recomputation`, no optional marker and no overload that omits it. And `unverified` is **not**
`failed`: amber means nobody has run the arithmetic yet, red means somebody ran it and it
disagreed. Collapsing the two would make an unchecked bundle look like a tampered one and —
far worse — would teach people to ignore red.

**`Meter` is the one component that measures a person,** and its neutrality is structural. It
is built for the reading-floor meter on the disposition screen. There is no `data-failing`
selector, no red fill and no amber track, because none exist in `instrument.module.css` and
adding one would be a design regression rather than a feature. The floor is drawn as a
hairline at its position so the reader sees the **distance** to it; the consequence of an
unmet floor is stated in words by the surface that owns the meter — *this permit now requires
a countersignature from a differently-credentialed signer* — because a consequence is a fact
and a colour is an accusation.

---

## 9. Two things this language will never render

**No name of any person appears in the MEMORY register, and `signer_sub` is never a visual
dimension anywhere in the console** — never a colour, an axis, a facet or a sort key. That is
`docs/leads/ui.md` D15 carrying `ARCHITECTURE.md` §11.5's Attribution Rule and I15 into pixels,
where a screenshot lives longer than a schema. This package provides no token, no scale and no
primitive that would make such an encoding easy, which is the only enforcement a design system
can offer for a rule about what is *absent*.

**No green without arithmetic.** `--tp-ok` appears in exactly one declaration block in this
package and `primitives-css.test.ts` fails if it appears in a second.

---

## 10. Known limits, recorded rather than omitted

1. **No person with a colour vision deficiency has seen this palette.** The dichromacy check
   is a published model applied to authored coordinates. It covers two dichromacies and not
   anomalous trichromacy or tritanopia.
2. **APCA is a working draft** and its floors here are ratchets against regression, not a
   conformance claim of any kind.
3. **The contrast gate measures authored token values, not rendered pixels.** It assumes the
   browser renders an in-gamut `oklch()` faithfully; the gamut assertion is what makes that
   assumption safe, and the axe-core run in `tests/browser/a11y.spec.ts` is what checks the
   composed result.
4. **`system-ui` is not one face.** Metrics differ across platforms, so line lengths and
   optical sizes differ. This is accepted in exchange for zero font bytes and zero font
   licences; the mono stack is what carries meaning and it is monospaced everywhere.
5. **The module-graph walk reads source text, not Rollup's built graph.** It follows every
   static import, every re-export, and every dynamic import with a literal specifier, and it
   asserts separately that no register-owned file contains a dynamic import with a *computed*
   specifier — so the limit is a failing assertion the day somebody needs one, rather than a
   silent gap.
6. **`--tp-rule` is exempt from the 3:1 non-text floor.** The exemption is data in `pairs.ts`
   with its reason attached rather than a token left out of the gate.
7. **The dichromacy matrices are easy to get wrong, and this repository got them wrong
   first.** The numbers usually quoted for "Viénot 1999" are the **LMS**-space matrices;
   applied to RGB they send a neutral grey negative. The grey-invariance assertion in
   `severity.test.ts` caught it, which is the argument for a property test over a
   plausible-looking constant — every ramp number would otherwise have been wrong and
   self-consistent.
8. **`eslint.config.js` hand-writes the boundary instead of spreading it.**
   `src/design/registers.ts` exports `registerBoundaryConfigs()` so the lint config can be
   generated from the law, and the console-foundation worker's config currently maintains an
   equivalent copy. `lint-config-agreement.test.ts` refuses the drift that matters — a
   directory under a register law with no lint rule — and accepts either form, so the copy can
   be replaced by the spread with no test change. Its one live divergence is recorded rather
   than asserted away: the copy lists `motion-utils` but not `motion-utils/**`, so a deep
   subpath import of that package is refused by the module-graph walk in CI rather than by the
   lint in the editor. One string in a file this package does not own.
9. **The register law is a *directory* law, so a file in no listed directory is in no
   register.** That is why `src/design/**` is checked by its own assertion and why
   `registerOf()` returning `null` is tested explicitly: a mistyped directory name would
   silently exempt a surface, and an exemption that reads as a clean result is the one failure
   this whole package is built to make impossible.

---

*The visual language of MAINLINE's console. Three registers enforced by the import graph, one
severity accent banded to a database enum, two faces where the difference between them is the
difference between a quotation and a sentence, and every threshold in this document asserted
by a test that reads the stylesheet rather than a copy of it.*
