<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# Accessibility — the console's contract, and what is actually measured

**`docs/leads/ui.md` D14.**

> *A safety product that a supervisor with a cracked screen and gloves cannot operate has
> an availability of zero regardless of uptime.*

This document is generated from `src/a11y/contract.ts` and `src/a11y/audit.ts`.
`tests/unit/a11y/doc-generated.test.ts` asserts that every table below is byte-identical
to what those files render, so the document cannot drift from the code. Editing a table by
hand fails CI and prints the exact text to paste.

---

## 0. The one thing to read if you read nothing else

Every law in §1 carries a **coverage** state, and `NOT YET MEASURED` is one of the legal
values. It is printed in bold, in the same column as the ones that are enforced.

That is deliberate, and it is the only thing about this document that is unusual. An
accessibility page on which every row reads as satisfied is a page nobody has measured;
the useful artefact is the one that says which claims have a red test behind them today
and which do not. The gate is **not** "every row is green". The gate is:

1. nothing claims to be enforced that is not — `contract.test.ts` resolves every claim
   against the rule, check or file it names, and fails if that thing does not exist; and
2. nothing that IS enforced has a `serious` or `critical` finding.

This is the same rule the gate screen applies to `unmodelled_asset_count`: an unknown is
reported as an unknown and never folded into a zero.

---

## 1. The law

<!-- GENERATED:laws — rendered from src/a11y/contract.ts + src/a11y/audit.ts. Do not edit by hand. -->

| Law | Statement | WCAG 2.2 | Registers | Coverage | Held up by |
|---|---|---|---|---|---|
| `every-control-is-named` | Every control a reader can reach — button, link, field, tab, checkbox — exposes a non-empty accessible name, so that an operator using speech output is told what the control does before activating it. | `1.1.1`, `2.4.4`, `4.1.2` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `control-name`<br>`img-alt`<br>`check-a11y:img-without-alt` |
| `controls-are-real-controls` | Interactive behaviour is attached to a native interactive element, never to a div with a click handler — because a div is not reachable by keyboard, is announced as nothing, and reimplementing it with a role and a key handler reimplements an element that already exists. | `2.1.1`, `4.1.2` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `check-a11y:click-handler-on-non-interactive` |
| `keyboard-order-is-dom-order` | No element carries a positive tabindex and none claims a single-character access key, so the order a screen reader reads a refusal in is the order a keyboard walks it in and no control silently captures a key an operator needs. | `1.3.2`, `2.4.3`, `2.1.4` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `tabindex-positive`<br>`check-a11y:positive-tabindex`<br>`check-a11y:access-key` |
| `nothing-focusable-is-hidden` | No element inside an aria-hidden subtree is reachable by keyboard, so a keyboard user never lands on a control a screen reader has been told does not exist. | `1.3.1`, `4.1.2` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `focusable-inside-aria-hidden`<br>`check-a11y:aria-hidden-interactive` |
| `a-refusal-is-announced` | Every panel carrying a data-failure marker is inside a live region, so that a refusal reaches an operator who cannot see the screen at the moment it is refused. | `4.1.3` | EVIDENCE | enforced here | `refusal-in-live-region` |
| `a-refusal-is-never-paraphrased` | What assistive technology is given for a constraint name, a SQLSTATE or a digest is the same string the eye is given — never a friendlier restatement and never a summary. | `1.1.1`, `4.1.2` | EVIDENCE | enforced here | `verbatim-is-text`<br>`src/a11y/announce.ts` |
| `verbatim-is-selectable-text` | Anything the database emitted is real, selectable text — never an image, never a canvas, never a CSS pseudo-element string — so it can be copied into a bug report or a court filing unchanged. | `1.1.1`, `1.4.5` | EVIDENCE | enforced here | `verbatim-is-text`<br>`check-a11y:no-canvas-outside-memory`<br>`check-a11y:verbatim-in-pseudo-element`<br>`check-a11y:inner-html` |
| `severity-is-never-colour-alone` | Severity, virulence and verification state are carried by text as well as by colour, so the meaning survives a monochrome print, a cracked screen and every form of colour vision. | `1.4.1` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `severity-not-colour-alone` |
| `contrast-floors-hold` | Every foreground/background token pair the primitives actually use meets 4.5:1 for body text and 3:1 for large text and meaningful boundaries. | `1.4.3`, `1.4.11` | EVIDENCE · INSTRUMENT · MEMORY | enforced (other suite) | `tests/unit/design/contrast.test.ts` |
| `motion-is-refusable` | Every transition is skipped under prefers-reduced-motion or a low-power signal, and the end state is identical either way. | `2.3.3` | EVIDENCE · INSTRUMENT · MEMORY | enforced (other suite) | `tests/unit/design/motion.test.ts`<br>`src/design/motion.ts` |
| `structure-is-real` | Headings descend without skipping a level, lists contain only list items, ids are unique, and every aria reference resolves — so the structure a screen reader announces is the structure the screen has. | `1.3.1`, `2.4.6`, `4.1.2` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `heading-order`<br>`heading-empty`<br>`list-structure`<br>`duplicate-id`<br>`aria-ref-resolves`<br>`label-for-resolves` |
| `aria-is-valid` | Every role and every aria-* attribute in the console is one that exists in ARIA 1.2; an invented one is a silent no-op that reads as a feature. | `4.1.2` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `role-known`<br>`aria-attr-known`<br>`aria-attr-value` |
| `nothing-moves-on-its-own` | No element animates itself outside the motion policy — there is no marquee, no blink, and nothing that moves text a reader cannot stop. | `2.2.2` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `no-marquee-or-blink` |
| `landmarks-are-navigable` | Each document has exactly one main landmark, and repeated landmarks of the same kind carry distinct accessible names, so a screen-reader user can jump between regions rather than reading through them. | `1.3.1`, `2.4.1` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `main-landmark`<br>`landmark-unique-name`<br>`region-name` |
| `no-name-in-the-memory-register` | No person is identified anywhere in the MEMORY register, and signer_sub is never a colour, an axis, a facet or a sort key in any register (D15 / I15 / the Attribution Rule). | — | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `no-person-in-memory`<br>`signer-sub-is-not-a-dimension`<br>`check-a11y:signer-sub` |
| `the-gate-to-signature-path-is-keyboard-only` | The complete path from the refusal to the signature — refusal, precursor list, disposition, defeater, reading floor, signature — is operable with a keyboard alone, in that order, with no pointer-only step. | `2.1.1`, `2.1.2`, `2.4.3` | EVIDENCE | **NOT YET MEASURED** (browser tier) | `tests/browser/a11y.spec.ts`<br>`KEYBOARD_TRAVERSAL` |
| `a-focus-ring-is-always-visible` | Every element that can receive keyboard focus shows a focus indicator that meets the 3:1 non-text contrast floor and is never removed by a stylesheet. | `2.4.7`, `2.4.11`, `1.4.11` | EVIDENCE · INSTRUMENT · MEMORY | enforced here | `check-a11y:focus-visible-outline` |
| `the-exhibit-prints` | Every EVIDENCE surface prints to a court-legible page with its caption block, and the ancestry ribbon prints to A3. | — | EVIDENCE | **NOT YET MEASURED** (browser tier) | `tests/browser/a11y.spec.ts` |
| `no-fact-is-three-dimensional-only` | Every node and edge drawn in the MEMORY register also exists in the ribbon DOM, so the dimensional walk is optional and the accessible path loses no fact. | `1.1.1`, `1.3.1` | EVIDENCE · INSTRUMENT · MEMORY | enforced (other suite) | `tests/unit/ancestry-3d/projection.test.ts` |

<!-- /GENERATED:laws -->

---

## 2. What runs, and where

| Tier | What it covers | Command | Landed? |
|---|---|---|---|
| **DOM audit** — `src/a11y/audit.ts` | The rendered shell, the navigation, the honesty chrome, the failure states and every design primitive, in jsdom | `pnpm test` | yes |
| **Source checks** — `src/a11y/source-checks.ts` | Patterns a rendered audit cannot see: CSS, unmounted branches, and anything wrong because of *where* it is | `node scripts/check-a11y.ts` | yes |
| **Contrast** — `tests/unit/design/contrast.test.ts` | WCAG 2.2 and APCA over every token pair the primitives use | `pnpm test` | yes (another worker) |
| **Motion** — `tests/unit/design/motion.test.ts` | `prefers-reduced-motion`, the easing set and the duration ceilings | `pnpm test` | yes (another worker) |
| **axe-core, six surfaces, real browser** — `tests/browser/a11y.spec.ts` | Everything a real accessibility tree, a real layout and a real keyboard can see | `pnpm run test:browser` | **no — owned by the `cinema-conformance-harness` worker** |

`@axe-core/playwright` is a devDependency of this workspace, so axe runs in the browser
tier. It is deliberately **not** used in the unit tier: pnpm's strict `node_modules` does
not expose `axe-core` itself, `package.json` belongs to another worker, and adding a
dependency to somebody else's manifest is not a thing this worker may do. So the unit-tier
auditor is dependency-free, implements a documented subset, and reports the gap.

### The DOM rules

<!-- GENERATED:rules — rendered from src/a11y/contract.ts + src/a11y/audit.ts. Do not edit by hand. -->

| Rule | Impact | WCAG 2.2 | What to do about it |
|---|---|---|---|
| `aria-attr-known` | critical | `4.1.2` | Fix the spelling, or delete the attribute. An unknown `aria-*` attribute is not an error in any browser — it is silently ignored, and the control ships with no name at all. |
| `control-name` | critical | `4.1.2`, `2.4.4` | Give the control an accessible name: visible text, `aria-label`, `aria-labelledby`, or a `<label for>`. A control with no name is announced as "button" and nothing else. |
| `focusable-inside-aria-hidden` | critical | `1.3.1`, `4.1.2` | Either remove `aria-hidden` or make the element unreachable (`tabindex="-1"`, `disabled`, or `inert`). A keyboard user can land on a control that speech output insists is not there. |
| `img-alt` | critical | `1.1.1` | Give the image an `alt`. If it carries no information, `alt=""` is the correct answer and says so explicitly; a MISSING alt makes a screen reader read the file name. |
| `no-person-in-memory` | critical | — | Remove the person. `docs/leads/ui.md` D15 and ARCHITECTURE §11.5: events carry titles and severities; people do not appear in the MEMORY register. A screenshot outlives a schema. |
| `signer-sub-is-not-a-dimension` | critical | — | Choose another dimension. `signer_sub` may never be a colour, an axis, a facet or a sort key anywhere in this console (D15 / I15 / the Attribution Rule) — a chart of people is the one thing this domain will not build. |
| `verbatim-is-text` | critical | `1.1.1`, `1.4.5` | Render the value as text in a `<code>` element (src/design/primitives/Mono.tsx). A verbatim value a reader cannot select is a verbatim value the medium paraphrased — and it cannot be pasted into a bug report, a filing or a grep of the schema. |
| `aria-attr-value` | serious | `4.1.2` | Use one of the values ARIA defines for this attribute; anything else is ignored. |
| `aria-ref-resolves` | serious | `1.3.1`, `4.1.2` | Point the reference at an element that exists. A dangling `aria-labelledby` is the same as no label, and it LOOKS like a label in review. |
| `duplicate-id` | serious | `4.1.1`, `1.3.1` | Make the id unique. `aria-labelledby`, `aria-describedby` and `<label for>` all resolve to the FIRST match, so a duplicate silently gives two controls the same label. |
| `heading-empty` | serious | `1.3.1`, `2.4.6` | Remove the heading or give it text. An empty heading is a landmark that leads nowhere. |
| `label-for-resolves` | serious | `1.3.1`, `3.3.2` | Point `for=` at the id of a form control that exists. A label bound to nothing is a label that reviews as present and announces as absent. |
| `list-structure` | serious | `1.3.1` | Put only `<li>` inside `<ul>`/`<ol>`. A stray element breaks the "list of 7 items" announcement that is the only reason the list markup is there. |
| `no-marquee-or-blink` | serious | `2.2.2` | Delete it. Moving text that cannot be paused fails 2.2.2 and has no place on an exhibit. |
| `refusal-in-live-region` | serious | `4.1.3` | Put the refusal inside `role="alert"` (or an `aria-live` region). A refusal an operator cannot hear is a refusal that did not happen for that operator, and this product is a refusal. |
| `role-known` | serious | `4.1.2` | Use a role from ARIA 1.2, or remove the attribute and let the native semantics stand. |
| `severity-not-colour-alone` | serious | `1.4.1` | Add the severity as text — visible, or in a visually-hidden span if the layout is already carrying it. Colour is not available to every reader, to a monochrome print, or to a court exhibit photocopied twice. |
| `tabindex-positive` | serious | `2.4.3` | Use `tabindex="0"` and put the element where it belongs in the DOM. A positive tabindex jumps the whole document queue, so the order a screen reader reads in stops matching the order a keyboard walks in. |
| `heading-order` | moderate | `1.3.1` | Descend one level at a time. A jump from h2 to h4 tells a screen-reader user a section is missing, and they will go looking for it. |
| `landmark-unique-name` | moderate | `1.3.1`, `2.4.1` | Give each repeated landmark an `aria-label` naming what it contains. Two navigations both announced as "navigation" cannot be told apart from the landmark list. |
| `main-landmark` | moderate | `1.3.1`, `2.4.1` | Give the document exactly one main landmark. Two is ambiguous and zero removes the single most-used screen-reader shortcut on the page. |
| `region-name` | moderate | `1.3.1` | Name the region with `aria-label` or `aria-labelledby`, or drop `role="region"`. An unnamed region is announced as "region" and adds a stop to the landmark list for no information. |

<!-- /GENERATED:rules -->

### What NO tier in this repository checks today

Copied from `NOT_CHECKED_HERE` in `src/a11y/audit.ts`, which is a field of every report the
auditor returns — not a footnote:

- **Colour contrast** — needs a cascade and computed colours. Covered over the *token set*
  by `tests/unit/design/contrast.test.ts`; the rendered pixels are not checked.
- **Focus indicator visibility** — the source form is refused by
  `check-a11y:focus-visible-outline`; whether the ring is actually visible against the
  painted background is browser-tier.
- **Reflow, zoom and text spacing** (WCAG 1.4.10, 1.4.12) — need layout. **Nothing covers
  these.**
- **Target size** (WCAG 2.5.8) — needs layout. **Nothing covers this.**
- **Reading order versus visual order** — the DOM order is asserted; the painted order is
  not.
- **Whether a screen reader actually announces a live region** — no automated tier here
  runs one.
- **Elements hidden by a CSS class** — jsdom has no cascade, so such an element is audited
  as though it were visible.

No conformance claim is made anywhere in this repository. WCAG success criteria are cited
because they are the vocabulary; citing a criterion is not a claim to have met it.

---

## 3. The keyboard-only path

D14 requires a complete keyboard path from the refusal to the signature. It is declared as
data in `KEYBOARD_TRAVERSAL` so that the browser spec, when it lands, asserts against the
same list this table is generated from rather than against a copy of it.
`verifyTraversal(observed)` grades an observed tab order against it and fails on a missing
step, on an out-of-order step, and reports any step it has never heard of.

**This path is NOT YET MEASURED.** Observing a real tab order needs a real browser.

<!-- GENERATED:traversal — rendered from src/a11y/contract.ts + src/a11y/audit.ts. Do not edit by hand. -->

| # | Step | Surface | The operator... |
|---|---|---|---|
| 1 | `refusal` | `gate` | read the constraint name and the SQLSTATE the database reported |
| 2 | `minimal-unsatisfiable-subset` | `gate` | walk the minimal unsatisfiable subset, one clause at a time |
| 3 | `precursors` | `gate` | open a blocking precursor and read its origin and evidence summary |
| 4 | `disposition-open` | `disposition` | open the disposition for that precursor |
| 5 | `defeater` | `disposition` | choose a defeater from the per-check vocabulary |
| 6 | `reading-floor` | `disposition` | read the reading-floor meter and its consequence |
| 7 | `signature` | `disposition` | reach the signature control and submit |

<!-- /GENERATED:traversal -->

---

## 4. What operating each surface actually means

One entry per surface in `src/app/surfaces.ts`. `contract.test.ts` asserts the two lists
are in exact bijection, so a surface cannot be promised without somebody writing down what
it means to operate it without a mouse or a screen.

<!-- GENERATED:operations — rendered from src/a11y/contract.ts + src/a11y/audit.ts. Do not edit by hand. -->

#### `gate`

- Hear the constraint name and the SQLSTATE, character by character on demand, as the database emitted them.
- Walk the minimal unsatisfiable subset item by item and hear each provenance chip.
- Reach every non-zero counter and follow it to its witness rows.
- Distinguish a counter that is zero from a counter that was never computed, by text.
- Open the clause diff and read both sides in the mono face.

#### `ancestry`

- Walk from the current clause to the terminal event using arrow keys alone.
- Hear each node as a list item with its date, kind and severity in text.
- Hear that a closure is truncated, and by which generation, without seeing the graphic.
- Hear that an edge is inferred rather than declared.
- Print the ribbon exhibit with its caption block.

#### `disposition`

- Reach every required field in DOM order, with each field announcing the projected column that required it.
- Choose a defeater from the per-check vocabulary without a pointer.
- Hear the reading-floor meter as a measurement, never as a judgement about the person.
- Hear the consequence of an unmet floor as a fact, in text.
- Reach and operate the signature control.

#### `custody`

- Hear each verification seal as verified, failed or unverified, in words, never as a colour.
- Read the bytes hashed and the digest produced for any recomputed claim.
- Hear the split-view honest limit sentence in full.

#### `audit`

- Read every audit view as a real table with header cells.
- Hear the truncation flag on any row whose ancestry is incomplete.
- Read the row and byte caps each query ran under.

#### `propagation`

- Reach a declined lesson with the same number of keystrokes as an adopted one.
- Hear the declination kind and its predicate in text.
- Hear an open merge conflict and its base, ours and theirs digests.

#### `silence`

- Read the conservation identity as an arithmetic line that balances.
- Hear every score together with its threshold and its policy version.
- Hear the PER honest-limit sentence in full.

#### `overview`

- Read what the system refuses, and why that refusal is the deliverable, before meeting a single identifier.
- Follow either worked case from its first sentence to the screen carrying its evidence, by keyboard alone.
- Reach every deep link as a link whose text names the surface it opens, rather than as an icon or a colour.
- Hear that a plain-language sentence is a summary, and reach the precise sentence it summarises.

#### `diff`

- Read both texts of the clause, at both commits, as selectable text in the mono face.
- Hear which side is the earlier commit and which is the later, in words, before reading either.
- Reach every control-bearing change by keyboard and hear it announced as added, removed or unchanged.

#### `evidence`

- Read every declared file with its expected digest and its recomputed digest, as selectable text.
- Hear each file verdict as verified, failed or not checked, in words, never as a colour or a tick.
- Hear that no bundle was consulted at all, when that is the case, rather than meeting an empty table.

<!-- /GENERATED:operations -->

---

## 5. Using the package

```ts
import { assertAccessible, audit, formatReport } from '../../src/a11y';

// In a unit test: throws on any serious or critical finding, and the message carries the
// whole report INCLUDING what the auditor cannot see.
assertAccessible(container, { label: 'the gate surface' });

// Or grade it yourself.
const report = audit(container);
report.blocking;    // D14's gate: this must be empty
report.notChecked;  // print this next to any pass you quote
```

```ts
import { createAnnouncer } from '../../src/a11y';

const announcer = createAnnouncer(document);
announcer.announce('Merge refused by constraint:');   // prose the console composed
announcer.announceVerbatim('gate_closed_when_issued'); // exactly what the database emitted
```

`announceVerbatim` **refuses** a value it would have to alter — leading or trailing
whitespace, an embedded newline, the empty string. Trimming a constraint name on its way to
speech output would make the ear and the eye disagree about what the database said: a
paraphrase performed by the accessibility layer, which is the one place nobody would look
for it (D18).

```ts
import { createFocusTrap, tabOrder, applyRovingTabindex } from '../../src/a11y';

const trap = createFocusTrap(dialog, { onEscape: close });
trap.activate();  // Tab is held inside; release() restores the previous focus
```

---

## 6. Register-specific obligations

From `docs/leads/ui.md` §1.1 — the register is also the accessibility contract:

- **EVIDENCE** must be fully operable with a screen reader alone and with a keyboard
  alone, and must print to a court-legible page.
- **INSTRUMENT** may move only where the transition is the fact, and every transition is
  skipped under `prefers-reduced-motion` with an identical end state.
- **MEMORY** must be entirely optional. Every node and edge in the 3D scene also exists in
  the ribbon DOM (`tests/unit/ancestry-3d/projection.test.ts`), so the accessible path
  loses no fact — and no person is ever identified there.

---

## 7. Reporting a defect this document does not cover

The honest answer to "is the console accessible?" is: *these named checks pass, these named
things are unchecked, and here is the list of both.* If you find something in the unchecked
column that is wrong in practice, it is not a gap in this document — it is the reason the
column exists. Add a law to `src/a11y/contract.ts` with the coverage state it truthfully
has, and a rule to `src/a11y/audit.ts` or `src/a11y/source-checks.ts` if it is checkable
from a DOM or from source.

A law added with `coverage: 'enforced'` and nothing behind it fails `contract.test.ts`.
