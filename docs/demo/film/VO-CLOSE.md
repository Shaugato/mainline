<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
This file quotes forbidden sentences beside true ones so a founder reading it at 02:00 can see
which is which. It therefore carries the `prose-hygiene: register` marker, in the same form
docs/demo/story-and-script-plan.md, docs/submission/MUST-NOT-CLAIM.md and
docs/demo/research/r6-honesty.md use. Every quoted offence sits on a line that also carries an
explicit negation (`MUST NOT SAY:`), which the scanner's documented negation exemption reads as
stating the rule rather than committing it. If this path is ever added to a prose scanner's
sweep list, the scanner must PRINT that it skipped this file, so "not scanned" is never read as
"passed".
-->

# VO-CLOSE — the naming block, 22 s, and the 2 s end card

**Worker W3 · close compression** · 2026-08-16 · master at HEAD · live origin
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

*(No commit id is written here. `claim_hygiene.py`'s `HYG-sha-literal` rule fired on the tree
hash this header carried in its first draft, and the rule is right: a commit id cannot be
chosen, so none is ever written or spoken. §9 records that firing rather than hiding it.)*

Binding: `docs/demo/film-recut-plan.md` §2 and §3 (rulings **R-3** and **R-6**),
`docs/demo/story-and-script-plan.md` §3 and §4 (R-O, R-M, R-K, R-L, R-N),
`docs/demo/research/r6-honesty.md` A6 and A7, and `docs/demo/film/BEATS.yaml` for timing.

**THE ONE-LINE SUMMARY OF THIS REVISION.** The naming block was **50 s in four cards**. It is
now **22 s in three cards**. **Not one service, feature, label, caveat, concession, evidence
path or URL left the screen.** The 28 s came out of *dwell*, out of *speech* (82 spoken words →
34), and out of *running two sequential cards in parallel*. Every overlay block in §2, §3, §4
and §5 below carries the same content it carried at 50 s; where a line moved, it moved because
the line **wrapped differently**, never because it was cut. §0.4 states the four things that
were genuinely lost, in numbers, because a compression that claims to have cost nothing is a
compression nobody should believe.

**`claim_hygiene.py --check` verdict — recorded per R-B: §9.**

---

## 0 · WHAT THIS BLOCK IS, AND THE ONE RULE THAT SHAPES EVERY FRAME

**RULING R-O, restated because it decides the layout:** the naming block is **on-screen text
over live picture, never a stock slide.** The operator app, the gate transcript and the memory
panel stay behind the overlay for all 22 s. A judge who pauses inside `k2` sees the AWS list
*and* the refusal that the AWS list carried, in the same frame. Devpost's tip says "text overlay
or slide"; overlay-over-live satisfies it and a slide does not survive the question *"is that a
picture of your product, or a picture of a list?"*

Two consequences that bind W4 and W5:

1. **Nothing is cut to black inside the close.** The picture underneath keeps whatever it was
   showing when the close in-points (the last demo beat's frame). Overlays fade in over it; the
   picture does not change to suit them.
2. **The overlay is text a judge can `Ctrl-F` in this repository.** Every line in §2–§5 carries
   an evidence path in the same table. **If a line has no path, it does not go on screen** —
   and the compression did not retire one single row of those tables.

### 0.1 · THE ARITHMETIC — the new shape, and the two in-point tables

The lead's re-cut plan `docs/demo/film-recut-plan.md` §3.1 rules the close to **three cards
totalling 22 s**, replacing `c1`..`c4`. The card ids are `k1`, `k2`, `k3`.

| new | title | dur | replaces | spoken |
|---|---|---:|---|---:|
| `k1` | THE LOOP | **6 s** | `c1` (12 s) | **10 w** |
| `k2` | THE STACK — AWS ∥ CockroachDB | **10 s** | `c2` + `c3` (30 s) | **14 w** |
| `k3` | THE LIMIT, THE RAIL, THE URLS | **6 s** | `c4` (8 s) | **10 w** |
| **naming block** | | **22 s** | **50 s** | **34 w** |
| `end` | end card | 2 s | unchanged | 0 |

**The `spoken` column is what is DELIVERED, and it is not the budget.** `k2` delivers 14 against a
budget of 16 because `D35`'s cleared replacement is 14 words (§3.4.0). Under-running a budget is
free; `BEATS.yaml` says so in its own words, and neither `vo_word_budget` nor `close_words` moves
because of it.

**THE MEASUREMENT THIS FILE IS OBLIGED TO STATE FIRST.** `BEATS.yaml` is the timing authority
and W1 owns it. **As of this writing the committed `BEATS.yaml` still carries the pre-re-cut
close** — `c1 t:120 dur:12`, `c2 t:132 dur:16`, `c3 t:148 dur:14`, `c4 t:162 dur:8`,
`close_s: 50`, `total_s: 172`, and no `k*` beat at all. This file is therefore written against
**`film-recut-plan.md` §2.1 and §3.1, which bind W1 as well as me**, and not against a spine
that has not yet moved. **If W1's landed spine disagrees with any duration below, the spine wins
and this file is wrong** — the disagreement is a reconciliation, not a negotiation.

**What this file requires of `BEATS.yaml`**, stated so W1 can check it in one pass:

```
k1  dur: 6   vo_word_budget: 10
k2  dur: 10  vo_word_budget: 16
k3  dur: 6   vo_word_budget: 10
close_s: 22        close_words: 36
```

**In-points depend on the GO/NO-GO gate at `film-recut-plan.md` §6, which is not mine to
decide.** Both tables are given in full so nobody improvises one at 02:00. The close is
contiguous with the last demo beat in both.

**Table A — GO (use case two ships; demo runs `b0`..`b10` = 148 s):**

| block | in | dur | out |
|---|---|---:|---|
| `k1` · the loop | `2:28` | 6 s | `2:34` |
| `k2` · the stack | `2:34` | 10 s | `2:44` |
| `k3` · the limit, the rail, the URLs | `2:44` | 6 s | `2:50` |
| **naming block** | | **22 s** | |
| end card | `2:50` | 2 s | `2:52` |

`148 + 22 + 2 = 172 s · 2:52`, which is `film-recut-plan.md` §2.1's total to the second.

**Table B — NO-GO (`b9`/`b10` never added, `b8` restored to 10 s; demo = 128 s):**

| block | in | dur | out |
|---|---|---:|---|
| `k1` · the loop | `2:08` | 6 s | `2:14` |
| `k2` · the stack | `2:14` | 10 s | `2:24` |
| `k3` · the limit, the rail, the URLs | `2:24` | 6 s | `2:30` |
| **naming block** | | **22 s** | |
| end card | `2:30` | 2 s | `2:32` |

`128 + 22 + 2 = 152 s · 2:32`, which is §6's figure. **Nothing else in this file changes between
Table A and Table B.** The three cards, their overlays, their spoken lines, their sweep and
their evidence are identical; only the in-points move. That is deliberate: the close is the one
part of the film that must not depend on the gate.

#### 0.1.1 · THE 12 s VARIANT OF `k2`, AND THE ONE NUMBER THE PLAN DOES NOT PRINT

`film-recut-plan.md` §3.3 rules that if the two halves of `k2` will not fit legibly with their
labels, **`k2` takes 12 s and the 8 s banked in §2.1 pays for it — it does not get flattened.**
That ruling is inherited whole and §3.3.1 below is written to it.

**The cost of taking it is not zero, and the plan does not print the consequence, so this file
does.** Under Table A, spending 2 s of the bank gives:

```
148 + 24 + 2 = 174 s
```

`BEATS.yaml`'s `hard_stop_s` is **174**, and its own wording is *"if the assembled cut exceeds
this, the ladder below is executed."* **174 does not exceed 174**, so the variant is legal by
the spine's own text — but it lands the film **exactly on the hard stop with zero margin**,
against the 2 s the plan's §2.1 counts as margin, and `BEATS.yaml`'s budget block warns in its
own words that *"editing lands long, never short."*

**Handed to W1 and the lead, not acted on here.** If `k2` takes 12 s, the honest pairing is
cut-ladder **rank 1** (`b9` 12 → 8, saves 4), which lands the film at **170 s** with 4 s of
margin restored. Under Table B the variant is free — `128 + 24 + 2 = 154 s`, 26 s under the
ceiling — so the question only arises on a GO. **I have not changed a duration to avoid this;
I have printed it.**

### 0.2 · WORD RATE — THE PROOF THAT THIS IS DELIVERY AND NOT CONTENT

**This is the single most important table in the revision.** The founder's instruction was 50 s
→ 22 s. The obvious way to hit it is to delete lines. The way taken here is to let the eye keep
its pace and take the seconds out of the mouth and out of the sequence.

| | old close | new close, first draft | **new close, after `D35`** |
|---|---:|---:|---:|
| cards | 4 | 3 | **3** |
| duration | 50 s | 22 s | **22 s** |
| spoken words | 82 | 36 | **34** |
| **words per second** | **1.64** | 1.64 | **1.55** |

```
old:         82 w ÷ 50 s = 1.640 w/s
first draft: 36 w ÷ 22 s = 1.636 w/s      →  1.64 w/s to two decimals
after D35:   34 w ÷ 22 s = 1.545 w/s      →  1.55 w/s to two decimals
```

**The reading pace a judge's eye needs moves DOWN, and the direction is the whole argument.** The
block still runs far below the demo's 1.88 w/s and below `BEATS.yaml`'s 1.9 w/s assumption, for
the same reason it always did: the on-screen text is doing the naming, and a voice reading a list
*over* a list gives a judge two things to parse and lets him finish neither. **A close that had
been compressed in content would show up here as a rising w/s. It does not, and after `D35` it is
0.09 w/s further from doing so.**

**The third decimal is stated rather than rounded away, in both steps**: `1.640 → 1.636` was a
change of **−0.004 w/s**; `1.636 → 1.545` is a further **−0.091 w/s**. The close is *slower* than
the 50 s version at every stage, never faster. A compression of content would have moved that
number the other way, and `D35` — which put twelve spoken words back into the Bedrock claim and
took eleven out of a sentence that was false about the card — moved it further in the safe
direction while making the block **more** true, not less.

Per card, against `BEATS.yaml`'s 1.9 w/s assumption:

| card | spoken words | at 1.9 w/s | block dur | air at tail |
|---|---:|---:|---:|---:|
| `k1` | 10 | 5.3 s | 6 s | 0.7 s |
| `k2` | **14** | **7.4 s** | 10 s | **2.6 s** |
| `k3` | 10 | 5.3 s | 6 s | 0.7 s |
| **total** | **34** | **17.9 s** | **22 s** | **4.1 s** |

Two things this table says that the old one could not:

* **The block no longer contains a budget overrun.** The 50 s close carried `C4` at 16 words in
  a 15-word budget and 8.4 s of speech in an 8 s block — a declared **−0.4 s**. Every card here
  is under its block. **The compression removed the file's only arithmetic defect.**
* **The proportion of silence is preserved, and `D35` widened it.** Old: 6.9 s of air in 50 s =
  **0.138 s of air per block-second**. First draft: 3.1 s in 22 s = **0.139**. After `D35`: 4.1 s
  in 22 s = **0.186**. What is lost is *absolute* dwell — 6.9 s of silence becomes 4.1 s —
  **not** the ratio of voice to silence, and the absolute loss is stated as a cost in §0.4 rather
  than smuggled past this table. The extra second lands in `k2`, which is the card a judge is
  most likely to pause on, and it is not spent: it is air.

**RE-AFFIRMED BY THE 2026-08-16 TOOLS-PANEL WAVE, AND NOT ONE CELL OF EITHER TABLE MOVED.** That
wave put the four contest CockroachDB tools onto the closing card as **overlay text only**
(§5.6), per `docs/demo/close-card-plan.md` R-C3. **No spoken word was added anywhere in the
close, and none was removed.** The block still delivers **34 words in 22 s = 1.545 w/s → 1.55
w/s**; `k1` 10 · `k2` 14 · `k3` 10; `close_words: 36`, `close_s: 22`, `demo_s: 148`,
`total_s: 172` and every `vo_word_budget` are exactly what they were. **The panel is read, never
spoken** — §5.6's *What is NOT on this panel* forbids saying it aloud — so the air column above
is unspent, and **§0.4.1 prices what that air was asked to buy, and refuses it in writing.**

**The single cleanest trade in the revision**, and it is worth naming on its own: the sentence
*"We measure deliberation and never threshold it"* moves **from the mouth to the screen, where
it already is**, verbatim, in §5.2's overlay. **Six spoken words saved, zero content lost.** The
scope word **`here`** stays in the spoken line — §5.3 rules that dropping it is the difference
between a limit and a slander, and that ruling is untouched.

### 0.3 · THE CRITERION RAIL — R-3, AND THE COST OF IT, IN CLAUSE-SECONDS

`r1-judging` §1.1 prints the five criteria in full and T6 names the finding: the **second**
sentence of each criterion is unanswered surface, and four of them are scoring hooks nothing in
`docs/submission/` addresses. The rail is this film's answer to all four.

**RULING R-3 (`film-recut-plan.md` §2.3, authority: this file's own §0.3 as it stood, which
already designed the rail to lift into the final block complete).** Across 22 s and three
cards, four staggered fade-ins are unreadable. **The rail no longer builds one line per block.
It arrives WHOLE, in `k3`, under the limit.**

| appears at | criterion, in the organiser's own words | the clause, on the rail |
|---|---|---|
| `k3` in-point | *"Does it demonstrate insight into what makes agentic systems different from traditional apps?"* | **the database is in the reasoning loop, as the thing that constrains the agent** |
| `k3` in-point | *"Does the agent use the tools correctly and safely?"* | **`persisted: false` — this call is non-mutating by construction** |
| `k3` in-point | *"Is it used for more than toy queries — state, embeddings, context, or transactional data at real scale?"* | **transactional state, read inside the same `SERIALIZABLE` transaction as the decision — and no scale is claimed** |
| `k3` in-point | *"Has the team thought about resilience, access control, and what happens when things go wrong?"* | **the refusal itself; `42501` on 256/256 ungranted pairs in privilege conformance; a ledger that publishes what did not run** |

**Rail typography, unchanged.** Criterion words in quotation marks, small, italic; the clause
after an arrow, same size, not italic. It reads as *an answer to a question the judge
recognises*, which is the whole value of putting it there.

**THE COST, RECORDED PLAINLY AS THE BRIEF REQUIRES.** Under the old schedule the four lines
faded in at `2:00 / 2:12 / 2:28 / 2:42` and each sat **beside the block that had just proved
it**. That adjacency is gone. Measured in clause-seconds on screen:

```
old:  50 + 38 + 22 + 8  = 118 clause-seconds
new:   6 +  6 +  6 + 6  =  24 clause-seconds
```

**A judge no longer sees each criterion answered beside the block answering it.** All four
answers are still on screen, unabbreviated, with their evidence in §5.4 — but they arrive as an
index at the end rather than as four annotations along the way, and they hold for a fifth of the
time. **That is a real loss and this file does not dress it up.** Two things are true beside it,
and neither cancels it:

* **The rail was never the evidence; it was the index.** Each clause names a thing a block
  already proved on camera — `persisted: false` was on screen in `b8`, `SERIALIZABLE` in `b8`,
  the refusal in `b2` and `b5`. A judge reading the rail at `k3` is being pointed back at
  footage he has watched, not asked to accept a new claim.
* **`k3` is the frame a judge pauses on.** It is the last card before a silent 2 s end card and
  it carries both URLs, so it is where a pausing judge stops by construction. Six seconds of
  four-line rail on the freeze frame is not six seconds of rail in motion.

### 0.4 · WHAT THE COMPRESSION ACTUALLY COST — four items, in numbers

The brief's instruction was that nothing leaves the screen. Nothing did. **But four things were
genuinely lost and a reader who cannot find them in this file has been misled.**

| # | what was lost | measured | where it is recorded |
|---|---|---|---|
| 1 | **Dwell on `k1`, the block whose primary axis is `agentic_memory_design`.** | 12 s → **6 s**. The time a judge has to sit with STORE / RETRIEVE / ACT halves. | `film-recut-plan.md` §2.3 COST 1 calls this "the sharpest thing in this plan" and it is |
| 2 | **Rail adjacency.** | 118 → **24** clause-seconds; four annotations become one index | §0.3 above |
| 3 | **The spoken scale concession.** `C3` said *"One cluster, one region, and no scale claim"* **out loud**. `k2`'s 14 words do not. | 22 spoken words → 14, and the concession is one of the six | §3.4.1 — and the concession is **still on screen, verbatim, full width, in `k2`'s strap**, and **still on the rail in `k3`** |
| 4 | **`k2`'s type is smaller than either card it replaces.** Parallelism halves the sequence; it does not halve the glyphs. | `k2` ≈ **83 %** of `C3`'s type size, ≈ **66 %** of `C2`'s — arithmetic measured in §4.1.1 | §0.5, with the binding consequence: **no line may be added to `k2`** |

Item 3 is the one I would argue about if there were room to. The 50 s cut's §4.2 — `C3`'s
spoken line — said of the concession: *"conceding it out loud costs one second and buys the only
thing that makes the other twenty-one words believable."* I still think that is true. The brief fixes
`k2` at ~16 spoken words whose job is to state the grouping rule and to say the Bedrock line,
and there is no honest 16-word sentence that does all three. **The mitigation is that the
concession is the card's closing strap in full width, and the rail repeats it six seconds
later** — it is read twice and heard never, where it used to be read twice and heard once.

**`D35` did not reopen this, and the two seconds it freed are not spendable on it.** The
replacement line runs 14 words, which leaves 2.6 s of air in `k2` rather than 1.6 s — but the
concession is 10 words and the card's air is not a word budget: adding a third clause to a
sentence whose job is already two things is how the Bedrock claim gets compressed again. **The
air stays air.** If the film lead wants the concession heard, the seconds come from the 8 s bank
and from a ruling by W1, not from this card's silence.

#### 0.4.1 · THE 4.1 s WAS OFFERED AGAIN ON 2026-08-16, PRICED, AND REFUSED — with the arithmetic, so nobody re-opens it at 02:00

The tools-panel wave asked whether the four contest CockroachDB tools could be **said** rather
than shown. The 4.1 s in §0.2's air column is the only budget that could have paid for it. **It
cannot, and the reason is arithmetic rather than taste.** At this file's own 1.9 w/s:

```
k3:  0.7 s of air  x  1.9 w/s  =  1.3 words.   There is no sentence there.
k2:  2.6 s of air  x  1.9 w/s  =  4.9 words.

     "Four CockroachDB tools, three evidenced"       =   5 words
     14 + 5                                          =  19 words
     19 w / 1.9 w/s                                  =  10.0 s   in a 10 s block
     air left                                        =   0.0 s
```

**Zero air, on the card a judge is most likely to pause on** — and §0.2's whole argument is that
this close is *slower* than the 50 s cut at every stage. **It also breaks §3.5's landing-4
alignment, which is the editorial reason `k2` exists as one card.** Five words in front of the
line push everything right by `5 / 1.9 = 2.6 s`: the spoken denial *"— not in this path"* would
start at about `8.4 s` instead of `5.8 s` and would not clear until about `10.5 s`, **past the
card's own out-point**, while the sweep's fourth landing stays at `6.8 s` and would therefore
fall **in front of** the denial rather than inside it. §3.5 calls that alignment *"the one moment
the parallelism buys something the sequence could not."* **REFUSED** — `close-card-plan.md`
R-C3, adopted here without amendment.

**The air stays air, a second time.** The tools reach the screen through the only channel that
costs layout instead of seconds: **text a judge pauses on**, §5.6.

### 0.5 · THE CARD GEOMETRY OF `k2` — measured, because "will it fit" is an arithmetic question

`film-recut-plan.md` §3.3 makes fit the trigger for the 12 s variant, so fit must be a number
somebody can check, not an impression on the day.

**Measured from the committed text**, with `wc -L` semantics (longest line, characters):

| block | widest line | lines |
|---|---:|---:|
| old `C2` — AWS, §3.1 as committed at 50 s | 98 ch | 22 |
| old `C3` — CockroachDB, §4.1 as committed at 50 s | 92 ch | 33 |
| new `k2` — AWS half, §3.1 below | **67 ch** | **33** |
| new `k2` — CockroachDB half, §4.1 below | **77 ch** | **37** |
| **new `k2` composed**, 4 ch gutter + blank + strap | **148 ch** | **39** |

Laid side by side at their **committed** widths the composed card would be `98 + 92 + gutter ≈
194` characters across. **That is why both halves are re-wrapped.** Re-wrapping moves line
breaks; it does not move words. Every word, label, path, caveat and number is where it was.

**The arithmetic, with its assumptions named as assumptions** (rule 8: a budget is labelled a
budget). For a monospace face, advance ≈ `0.6 em`, line pitch ≈ `1.25 em`; a 1920 × 1080 frame
with 5 % title-safe margins gives `1824 × 1026` usable pixels.

```
width-bound:   em <= 1824 / (0.6 * total_characters_across)
height-bound:  em <= 1026 / (1.25 * lines_tall)
the card runs at the SMALLER of the two.
```

`C3` alone: `92` ch → em ≤ 33.0; `33` lines → em ≤ 24.9. **Height-bound at ≈ 25 px.**
`C2` alone: `98` ch → em ≤ 31.0; `22` lines → em ≤ 37.3. **Width-bound at ≈ 31 px.**
Composed `k2` at the measure written below: see §3.1.1 and §4.1.1 for the two halves' figures
and the composed result.

**Two consequences, and W4 must treat both as binding:**

1. **The 12 s bank buys dwell. It does not buy glyph size.** A card that is too small at 10 s is
   the same size at 12 s. **Legibility is bought only by balancing the two halves' line counts
   against their measure**, which is why both halves below are re-wrapped to the *same* measure
   rather than left at the widths they were cleared at. If `k2` is illegible, the remedy is the
   re-wrap, not the seconds — and **never the flattening**, which R-6 forbids outright.
2. **No line may be added to `k2`.** The composed card sits close to both bounds at once. One
   more line, or one line wider than the measure, costs glyph size on *every* other line in both
   halves. This is the constraint that keeps a well-meaning addition from silently shrinking the
   Bedrock exception.

#### 0.5.1 · CONSEQUENCE 2 WAS TESTED AGAINST A REAL REQUEST ON 2026-08-16, AND IT HELD

A rule nobody has ever been asked to break is not a rule; it is a preference. **This one was
asked.** The tools-panel wave needed the four contest CockroachDB tools on the closing card, and
`k2`'s CockroachDB half is where a CockroachDB list belongs by subject. **The rule was not
waived, the geometry was not re-opened, and the 12 s variant was not reached for.**

**`k2`'s two overlay strings are byte-identical.** §3.1's AWS half and §4.1's CockroachDB half
were not re-wrapped, not re-measured and not re-emitted by that wave; neither was the full-width
strap. `148 ch × 39 lines`, `20.5 px`, the four sweep landings in §3.5 at `1.2 / 3.0 / 4.8 /
6.8 s`, the 14 spoken words and `vo_word_budget: 16` are all exactly what §3 and §4 already
carried. **A stranger can check this in two commands, and should:**
`git diff --stat docs/demo/film/VO-CLOSE.md` reports **insertions only — zero deletions**, so no
committed line of this file was altered or removed by the wave at all; and
`git diff -U0 docs/demo/film/VO-CLOSE.md | grep "^@@"` puts every hunk in **§0.2, §0.4, §0.5, §1,
§5.2, §5.6, §8 and §9.2**, with **no hunk anywhere inside §3.1, §4.1 or §3.5**. A claim that two
overlay strings are byte-identical is worth exactly as much as the command that shows it.

**And the deciding reason is label truth, not geometry** — `close-card-plan.md` R-C1, adopted
here as this file's own finding, because the geometric argument is the weaker one and this file
does not rest on the weaker one. `k2`'s CockroachDB half has exactly **two** group headings,
`IN THIS REQUEST` and `IN THIS DATABASE, EARLIER`, and **three of the four tools are neither**:

* the **Managed MCP** transcripts were driven against the managed Cloud endpoint — never against
  the cluster this film's request reads, and never during it;
* **C-SPANN is excluded from this card by name**, by §4.2, whose first prohibition is that this
  demo world holds no seeded embedding and issues no vector query;
* **`ccloud`** is a committed CLI transcript, not a statement this database executed.

Filing any of the three under either heading is precisely the swap **§7.1** exists to prevent —
the finding this file calls *"the most important thing in this file."* They need the **third**
label, the one the AWS half already gives Bedrock: *exercised in this repository, not in this
request path.* **The tools panel is the CockroachDB mirror of the Bedrock box.** `k2` has no
third group and, by consequence 2 above, no room for one — and **even if it had the room, §7.1
would still forbid the filing.** The panel therefore lives on `k3`, and §5.6 is it.

**Composition, for W4:**

```
+---------------------------- k2 ----------------------------+
|                            |                               |
|   AWS half  (§3.1)         |   CockroachDB half  (§4.1)    |
|   - IN THIS REQUEST        |   - IN THIS REQUEST           |
|   - IN THE APPLY ...       |   - IN THIS DATABASE, EARLIER |
|   - Bedrock, boxed         |                               |
|                            |                               |
+------------------------------------------------------------+
|  One cluster.  One region.  ... and we do not claim scale.  |
+------------------------------------------------------------+
```

* **A visible vertical rule separates the halves.** It is the grouping made physical: R-6 says
  the grouping *is* the honesty, and a rule is what stops two adjacent stacks reading as one.
* **Both halves fade in together.** Never one and then the other — sequencing is precisely the
  thing that was removed, and re-introducing it inside the card spends the saving twice.
* **The strap is full width** and it is the only element that is. **A caveat may borrow width; a
  credit may not.** R-6's rule exists to stop `S3` borrowing the credibility of `Lambda`; a
  concession cannot be inflated by adjacency, so *"we do not claim scale"* spanning both halves
  makes it wider, not stronger.

---

## 1 · EVIDENCE DISCIPLINE — the three labels, and why the second one exists

Every service and every feature named in §3 and §4 carries one of three labels, printed on
screen in the group heading, not hidden in a footnote. **All three survive the compression
intact; the labels are the first thing a shorter card would have dropped and they are the last
thing that may go.**

| label | means | example |
|---|---|---|
| **IN THIS REQUEST** | it executed while the `POST /v1/demo/gate-run` a judge just watched was in flight | `CHECK gate_closed_when_issued` |
| **IN THE APPLY / IN THIS DATABASE, EARLIER** | it was applied into the account, or it ran against this database before the shoot and its output is what the request read | `fn_check_project` |
| **NOT IN THIS PATH** | it is exercised in this repository and had nothing to do with the refusal | Amazon Bedrock |

The second label is the one that makes the block honest. Three named things fall into it and a
looser film would quietly file them under the first: `fn_check_project`, the recursive-CTE blame
closure, and `42501`. **§7.1 is the finding that produced that discipline and it is the most
important thing in this file.**

**This table is scoped to §3 and §4 — the two halves of `k2` — and `k3` carries no group heading
at all.** The tools panel added to `k3` on 2026-08-16 (§5.6) therefore speaks a **second
vocabulary**, the census's `EXERCISED` / `DESIGNED`, and it is **not** a fourth entry in the table
above. The two vocabularies must not be blended: on the panel, `EXERCISED` carries the *third*
row's meaning — **exercised in this repository, and not in this request path** — which is why
§0.5.1 rules that the panel could not be filed under either of `k2`'s two headings, and why
§5.6.1 states the scope in terms before W2 renders a character of it.

---

## 2 · `k1` · THE LOOP — 6 s

*(Table A `2:28` → `2:34` · Table B `2:08` → `2:14`. Was `C1`, 12 s.)*

### 2.1 · What stays behind the overlay

The last demo beat's frame: `persisted false · single_transaction true · isolation
SERIALIZABLE`, and the memory panel's three columns still filled. The overlay lands *on top of*
the panel it is naming.

### 2.2 · Overlay text — exact, and unchanged from the 50 s cut

```
S T O R E                      R E T R I E V E                 A C T

mainline.event                 mainline_meas.recall_run        mainline.permit
mainline.blame_edge            mainline.clause_blame_current   CHECK gate_closed_when_issued
mainline.clause_blame_closure    (view · DISTINCT ON, gen DESC)  -> 23514
  append-only, generation-                                     mainline.fn_permit_merge_gate
  versioned; superseded,                                         -> P0001
  never deleted

occurred_at                    started_at                      refused at
2019-03-14T06:20:00Z           2026-08-02T03:00:00Z            <THIS RUN>

                               obligation materialised
                               2026-08-02T03:00:10Z
                               ten seconds
```

Strap, small, full width, under the three columns:

```
every date above is a column value · no AS OF SYSTEM TIME produced any frame of this film
```

**Rail line 1 no longer fades in here.** Per R-3 it arrives with the other three in `k3`. That
is the only change to this card's screen, and it is a removal of a rail line's *arrival*, not of
its content.

### 2.3 · Spoken — 10 words

> **"The incident. The retrieval. Ten seconds later, the obligation. Refused."**

**10 words · 5.3 s at 1.9 w/s · 0.7 s of air.** The three words STORE · RETRIEVE · ACT are on
screen in large type and are **not spoken** — saying them while they are that size is the kind
of narration that makes a judge stop reading.

Delivery is unchanged: **four fragments landing on three columns.** *"The incident"* on STORE.
*"The retrieval. Ten seconds later, the obligation"* on RETRIEVE — both timestamps are in that
column, ten seconds apart, so the gap is cashed out on screen while it is spoken.
*"Refused."* lands on ACT and then stops. Do not add "…and that's the loop."

**What the 50 s line said, and what changed** — recorded because a spoken line that changes
without a record is how a film drifts:

| | words | line |
|---|---:|---|
| 50 s | 20 | *"An incident from 2019. A retrieval, and ten seconds later, the obligation. And the refusal you just watched, re-deriving it."* |
| 22 s | **10** | *"The incident. The retrieval. Ten seconds later, the obligation. Refused."* |

Three deliberate decisions inside that halving:

1. **The year is no longer spoken. It is still on screen, in full, as `occurred_at
   2019-03-14T06:20:00Z`.** This is compression that happens also to remove the only place this
   file could be read as colliding with `film-recut-plan.md` §8 rule 7 (*"the seeded incident
   describes nobody. No date…"*), whose §4.3 statement is scoped to `b9`/`b10` and whose §8
   restatement is not. **I have not resolved that ambiguity; I have stepped out of it**, and the
   column value stays on screen where R-K and rule 8 both permit it. **Flagged to W6.**
2. **`"and ten seconds later"` became `"Ten seconds later"` as its own fragment, immediately
   after `"The retrieval"`.** This is not style. *"The incident. Ten seconds later, the
   obligation"* would attach the ten seconds to the **incident**, which would read as a
   ten-second response to a years-old event. That is a fake by grammar and it would be a fake
   this file exists to prevent. **The retrieval must be named between them.**
3. **`"re-deriving it"` is gone.** That is a real content loss from the *spoken* line — the
   re-derivation is the strongest thing `k1` could have said. It is not lost from the film: the
   re-derivation sentence is `b5`'s, verbatim from the payload, and it is `BEATS.yaml`'s own
   `b5.on_screen`. `k1` names the loop; `b5` proves the re-derivation.

### 2.4 · Tense — the one line in this block that can go wrong

**MUST NOT SAY:** *"Watch it remember."* · *"The system just retrieved the incident and blocked
the permit."* · anything present-tense about the retrieval. The recall is a record, not an event
happening now; it is `mainline_meas.recall_run`, every field a column, `started_at` two weeks
before the shoot. What runs **now** is the third column.

**The compressed line is safer here than the line it replaces, and that is worth saying.** All
four fragments are now nouns or a past participle — *"The incident. The retrieval. Ten seconds
later, the obligation. Refused."* — so there is no present participle left to mis-deliver. The
50 s line's `re-deriving` was defensible only because it described the request in flight; the
new line does not need the defence.

**Do not compute a "days before" figure out loud.** R-K: nothing spoken is unseen. If a
day-count appears it is computed in the browser from two columns both on screen and labelled
`derived` — never spoken from memory.

### 2.5 · Evidence — every line above

**Unchanged, complete, not one row retired.** These are the lines `film-recut-plan.md` §3.2
means by *"exactly the lines already cleared in `VO-CLOSE.md` §2.5."*

| on-screen line | what proves it |
|---|---|
| `mainline.event` · `occurred_at 2019-03-14T06:20:00Z` | `GET /v1/permits/{permit_id}/blocking-checks` → `/data/checks/0/precursor/occurred_at`, live, 200, 2,408 B (`docs/demo/research/r2-memory.md` §3.1); seeded `verticals/mainline/db/seeds/demo/demo_world.sql:264-284`; table `verticals/mainline/db/migrations/0033_event.sql` |
| `mainline.blame_edge` | `GET /v1/clauses/{clause_uuid}/ancestry` → `/data/blame_edges/0` (`basis asserted_document`, `state active`); table `verticals/mainline/db/migrations/0037_blame_edge.sql`; seeded `demo_world.sql:299-314` |
| `mainline.clause_blame_closure` · append-only, generation-versioned | `verticals/mainline/db/migrations/0038_clause_blame_closure.sql`; the append-only weld is `0128j_trg_refuse_mutation_clause_blame_closure.sql`; rationale for "superseded, never deleted" is `0039_clause_blame_current.sql`'s rationale block |
| `mainline.clause_blame_current` · view · `DISTINCT ON`, gen DESC | `verticals/mainline/db/migrations/0039_clause_blame_current.sql:118-135`; sole legal read path, enforced by `scripts/grep_closure_readpath.py` |
| `mainline_meas.recall_run` · `started_at 2026-08-02T03:00:00Z` | `verticals/mainline/db/seeds/demo/demo_permit.sql:239-252` — the literal is `TIMESTAMPTZ '2026-08-02 03:00:00+00'` at `:250`; served live by `GET /v1/recall-runs/{run_id}`, 200, 2,223 B |
| obligation `materialised 2026-08-02T03:00:10Z` | `demo_permit.sql:306-323` — the literal is `TIMESTAMPTZ '2026-08-02 03:00:10+00'` at `:321`; column `materialised_at` on `mainline.blocking_check` (`0058_blocking_check.sql`) |
| `CHECK gate_closed_when_issued -> 23514` | `evidence/deploy/live-gate-run.json` → `/data/beats/1/{sqlstate,constraint,constraint_source}`; constraint declared `verticals/mainline/db/migrations/0050_permit.sql:114` |
| `mainline.fn_permit_merge_gate -> P0001` | `evidence/deploy/live-gate-run.json` → `/data/beats/2/{sqlstate,constraint}`; function `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql` |
| `refused at <THIS RUN>` | **live slot.** Filled from the shoot's own response: `/data/beats/1/refusal/observed_at`. Reference value on the recorded run is `2026-08-14T22:10:33Z` — **re-derive from your own run, per R-K; do not caption the reference value.** |
| `no AS OF SYSTEM TIME produced any frame of this film` | `verticals/mainline/db/seeds/demo/demo_world.sql:149-151` (measured GC window 4500 s); `DEMO-HONESTY.md:147-152`; scanner rule `MNC-09-time-travel` |

---

## 3 · `k2` · THE STACK — THE AWS HALF — 10 s

*(Table A `2:34` → `2:44` · Table B `2:14` → `2:24`. Was `C2`, 16 s, sequential with `C3`.
`k2` runs this half and §4's half **side by side in one card**; §0.5 composes them.)*

### 3.1 · Overlay text — exact

Two labelled groups and one labelled exception. **The grouping is the honesty**: a flat list
would let "S3" borrow the credibility of "Lambda", and S3 was never in the request.

**Every word below is the committed 50 s text. Only the line breaks moved**, and they moved for
the geometry in §0.5, not to make room.

```
AWS  ·  IN THIS REQUEST

  AWS Lambda                arm64 · mainline-demo-api
  Lambda Function URL       authorization_type = NONE
                            (the founder's explicit choice)
  SSM Parameter Store       /mainline/demo/cockroach_dsn
  AWS IAM                   one execution role; one inline policy,
                            GetParameter on that one name


AWS  ·  IN THE APPLY THAT CREATED IT
        24 created · 0 changed · 0 destroyed

  Amazon S3                 Terraform state · versioned · SSE-S3 ·
                            public access blocked
  CloudWatch alarms + SNS   the cost guard: three alarms on three
  + AWS Budgets             timescales into one topic, a responder
                            that sets reserved concurrency to zero,
                            and the budget


  +--------------------------------------------------------------+
  |  Amazon Bedrock  —  EXERCISED IN THIS REPOSITORY.            |
  |  IT IS NOT IN THIS REQUEST PATH.                             |
  |                                                              |
  |  Claude on au.* inference profiles and Titan v2 embeddings,  |
  |  ap-southeast-2 (Sydney).                                    |
  |  The database is aws-ap-southeast-1 (Singapore).             |
  |  There is no end-to-end Australian residency and we do not   |
  |  claim one.                                                  |
  |  The refusal you just watched involved no model at all,      |
  |  and that is the point.                                      |
  +--------------------------------------------------------------+
```

**The box is not decoration.** `film-recut-plan.md` §3.2 requires the Bedrock exception *"in its
own boxed position"*. It is the third label and it is the only one of the three whose group has
a single member, so it cannot be carried by a heading the way the other two are: a rule around
it is what makes the label visible. W4 renders the `+`/`-`/`|` above as a drawn panel; the
characters are the specification, not the artwork.

#### 3.1.1 · Measured geometry of this half

| | value |
|---|---:|
| widest line | **67 ch** |
| lines | **33** |
| was, at 50 s (§3.1 committed) | 98 ch × 22 lines |

The half is **31 characters narrower and 11 lines taller** than the card it came from. That
trade is the whole re-wrap: width is what the composed card is short of, height is what it has
spare (§0.5). The Bedrock panel is 66 characters on every one of its twelve lines, measured, so
the box rules are straight without a renderer having to justify them.

### 3.2 · What is NOT on this half, and why — read this before adding anything

**Retained in full from the 50 s cut. Every prohibition below still binds.**

* **Never a CDN and never a distribution.** None exists on this account.
  `infra/modules/demo-api/main.tf` contains a conditional grant that is **not taken** —
  `create_cloudfront_invoke_grant = var.url_authorization_type == "AWS_IAM"`, and the applied
  value is `NONE`. The word is banned on screen and in speech by `CAMERA-STRINGS.yaml:127-131`.
* **No console window.** The cost guard exists and is applied; a metrics console on camera is
  forbidden by the same authority. Say "a cost guard that sets reserved concurrency to zero",
  film the overlay, and film nothing else.
* **Never CMEK and never PrivateLink**, not even as "we would add" — `MNC-03`.
* **No latency figure of any kind.** One of the applied alarms is named for a duration
  percentile. **That alarm's name does not go on screen and is not spoken.** An alarm threshold
  is not a performance claim, and a judge cannot be expected to make that distinction in the
  half-second the overlay gives him. This repository contains no load profile.
* **No CloudTrail, KMS, EventBridge or S3 Object Lock.** All four are real code and none is
  applied — `evidence/tool-usage/aws-services.json` marks them `DESIGNED` and
  `docs/HONESTY.md` says the object-lock check is one of the seven cryptographic checks that
  **did not run**. They belong in the written submission, not on a card that says "in this
  request".

### 3.3 · Evidence — every service named

**Unchanged, complete, not one row retired.**

| on-screen line | label | what proves it |
|---|---|---|
| **AWS Lambda** · arm64 · `mainline-demo-api` | in this request | `evidence/deploy/APPLIED.md:14-21` (24 created, `demo_url` on line 16); the serving artefact is `out/lambda/mainline-demo-api-arm64.zip`, named at `APPLIED.md:168-170` and measured as the deployed bytes at `evidence/deploy/console-mode.json:18`; the resource is `infra/modules/demo-api/main.tf:327-335` (`architectures = [var.architecture]`), name composed at `infra/envs/demo/main.tf:250` (`local.api_function_name = "${var.name_prefix}-api"`) with `name_prefix` defaulting to `mainline-demo` at `infra/envs/demo/variables.tf:68` |
| **Lambda Function URL** · `authorization_type = NONE` | in this request | `infra/modules/demo-api/main.tf:425-432`; the choice and its reason are recorded in the founder's own terms at `evidence/deploy/APPLIED.md:200-203` and `evidence/deploy/LIVE.md:74-76`; the URL itself is the origin every frame of this film is shot against |
| **SSM Parameter Store** · `/mainline/demo/cockroach_dsn` | in this request | `evidence/deploy/APPLIED.md:42-43` — the pre-parameter answers named the exact key verbatim in their own error — and `APPLIED.md:189-210` for why the value is placed by hand; the resource grant is `infra/modules/demo-api/main.tf:318-320` (`aws_iam_role_policy.dsn_access`) |
| **AWS IAM** · one execution role, one inline policy | in this request | `infra/modules/demo-api/main.tf:260-272` (`aws_iam_role.this`, `basic_execution` attachment) and `:318-325` (`dsn_access`); the role's narrowness is the point and it is measured at `evidence/deploy/APPLIED.md:191-203` — `mainline_api` holds CONNECT 1 · USAGE 37 · SELECT 66 · UPDATE 3 · INSERT 8 · EXECUTE 29 (`evidence/deploy/LIVE.md:73`), against `ALL on 417 objects` for the admin role |
| **Amazon S3** · Terraform state, versioned, SSE-S3, public access blocked | in the apply | `evidence/deploy/APPLIED.md:23-25` — the state bucket was the first mutating action of the whole deploy, versioned, all four public-access settings blocked, SSE-S3, noncurrent versions expiring at 30 days |
| **CloudWatch alarms + SNS + AWS Budgets** · the cost guard | in the apply | `evidence/deploy/APPLIED.md:18-21` — thirteen of the twenty-four applied resources: three alarms on three timescales into one SNS topic, a responder calling `PutFunctionConcurrency(ReservedConcurrentExecutions=0)`, plus the budget; module `infra/modules/cost-guard/main.tf`; corroborated by `docs/demo/research/r6-honesty.md` A6 |
| **Amazon Bedrock** · not in this request path | not in this path | `evidence/aws/probe/bedrock-probe.json`, `evidence/aws/probe/raw-haiku-converse.json` (a live `bedrock-runtime:Converse` against `au.anthropic.claude-haiku-4-5-20251001-v1:0` in `ap-southeast-2`), `evidence/aws/embeddings/manifest.json` (Titan v2, 2,060 vectors of width 1,024), `evidence/deploy/aws-live.json`; census row `evidence/tool-usage/aws-services.json` → `rows.aws_bedrock_runtime` / `rows.aws_bedrock_embeddings`, both `EXERCISED` |
| residency, stated as the split | — | `docs/demo/research/r6-honesty.md` A1 and the scanner rule `MNC-02-residency`: the cluster is `aws-ap-southeast-1` (Singapore); only Bedrock inference is `ap-southeast-2` (Sydney) |

### 3.4 · Spoken — 14 words, for the whole card, against a 16-word budget

**This is the only spoken line in `k2`.** It covers both halves, because the card is one card.

> **"Every line says which. Bedrock is exercised in this repository — not in this path."**

**14 words · 7.4 s at 1.9 w/s in a 10 s block · 2.6 s of air.** The dash is a real pause, not a
comma: the last four words are the half a judge does not expect, and they need the silence in
front of them. **The four words in front of the dash are the half that makes them credible**, and
that is the whole of `D35` — see §3.4.0.

#### 3.4.0 · `D35` — WHY THIS LINE CHANGED, AND WHAT THE OLD ONE LOST

**`CLAIMS-CLEARANCE.md` row `N22` was filed before this line existed and fired on it exactly, and
`D35` in §12.9 is the REFUSE.** The first draft of this section read:

> ~~"Everything here is either in that request or in the apply. Bedrock — not in this path."~~

**The compression took the Bedrock claim down to a bare denial.** *"is exercised in this
repository"* went out of the mouth while staying on the card in capitals, and the two halves are
not separable: **Bedrock IS exercised in this repository, and it IS not in this request path.**
A denial with its positive half removed under-states what was built, and a card that only denies
reads as a card hiding something — `N22`'s own words. The qualifier cannot simply be dropped
either: without *"not in this path"* the sentence over-states what the film shows. `r6-honesty.md`
A6's `TRUE INSTEAD` carries both halves in one clause and so does the line above.

**And the first sentence was carrying a second, separate defect.** *"Everything here is either in
that request or in the apply"* is `CLAIMS-CLEARANCE.md` §7.6's open **REWORD**: the overlay carries a **third** group
(`IN THIS DATABASE, EARLIER`), and §7.7/§7.8 move two more rows out of the first two — so
*"either… or…"* was false about three of the card's rows rather than one. **`"Every line says
which"`** is row `N20`, cleared, four words, and it is true of a card with any number of groups
because it is a claim about the **labels** rather than about the count.

**Both halves of the replacement were already cleared, separately, before the replacement
existed:** `N20` (*"Every line says which."*, 4 w) and `N21` (*"Bedrock is exercised in this
repository — not in this path."*, 10 w, carried forward from `K5` to the character). **No new
claim is made here; two cleared ones are put back together.** `D35`'s own supplied replacement is
this sentence verbatim and this file adopts it without amendment — inventing a third wording to
hit a word count is how a cleared line becomes an uncleared one.

**The cost, stated: the card's spoken line is now 14 words against a 16-word budget**, so the
close delivers **34** rather than 36 and reads at **1.55 w/s** rather than 1.64. §0.2 carries the
corrected arithmetic and the direction it moves in. **A budget is a ceiling** — `BEATS.yaml` says
so in its own words — so `k2`'s `vo_word_budget: 16` and `close_words: 36` are unchanged and
correct; what changed is what is delivered against them.

**The service names and the feature names are not read aloud** — they are on screen, larger than
they would be in speech, and a judge reads a list faster than anyone can say it. The VO's whole
job is **to tell him the list has a rule, and to say the Bedrock line out loud.**

**What changed from the two lines it replaces:**

| | words | line |
|---|---:|---|
| 50 s `C2` | 24 | *"Everything here is either in that request or in the apply that created it. Bedrock is exercised in this repository — not in this path."* |
| 50 s `C3` | 22 | *"Two refusals, two SQLSTATEs, one SERIALIZABLE transaction. The enum in that predicate is ours. One cluster, one region, and no scale claim."* |
| 22 s `k2`, first draft — **refused at `D35`** | 16 | ~~*"Everything here is either in that request or in the apply. Bedrock — not in this path."*~~ |
| 22 s `k2`, **as it stands** | **14** | *"Every line says which. Bedrock is exercised in this repository — not in this path."* |

* **`"that created it"` came out of the mouth and is still on the screen**, verbatim, as the
  group heading `AWS · IN THE APPLY THAT CREATED IT`, with `24 created · 0 changed · 0
  destroyed` under it. **The screen cashes out the jargon.** This is the pattern of the whole
  revision: a phrase that is already printed larger than it can be spoken is not spoken.
* **`"is exercised in this repository"` is back in the mouth, and it never left the screen** —
  it is in the box, in capitals: `EXERCISED IN THIS REPOSITORY.` **The first draft of this
  revision took it out of the mouth and that was the one place the compression cost content**
  rather than delivery; §3.4.0 is the finding and `D35` is the row. The spoken form now carries
  the half a judge will not predict *and* the half that makes it credible.
* **`"Everything here is either in that request or in the apply"` came out**, and what replaced
  it is shorter and truer of the card as built: the overlay has three labelled groups, not two.
* **`C3`'s sentence is not spoken at all.** Its three assertions are on screen and none is lost:
  two SQLSTATEs are in §4.1's left group beside their constraint and function; `SERIALIZABLE`
  is in the same group; the enum-inside-the-predicate is the third sweep landing (§3.5); and the
  scale concession is §4.1's full-width strap. **§0.4 item 3 records the loss of the spoken
  concession as a cost. It is the one I would argue about.**

#### 3.4.1 · The concession, and why it is safe to leave unspoken here

The 50 s cut's §4.2 argued the scale concession must be **heard**. The mitigation, stated so it
can be checked rather than trusted:

* it is on `k2`'s **full-width strap**, the widest single line on the card, and the eye ends
  there;
* it is on the **rail in `k3`**, six seconds later — *"and no scale is claimed"*;
* it is in `docs/submission/JUDGING-AXES.md:69`, which a judge can open.

**MUST NOT SAY**, at any point in the close, in any card: *"at scale"* · *"production scale"* ·
*"proven at scale"*. The concession being unspoken does not make its opposite speakable. **W6
files a REFUSE row against any take in which the scale concession is absent from `k2`'s strap.**

### 3.5 · The highlight sweep — four landings, and where they land

`film-recut-plan.md` §3.3 caps the sweep at **four landings in `k2`**, in the order this file
already fixed in §4.1: `23514` → `P0001` → the enum inside the predicate → the `It did not run
in this request.` column. **That cap and that order are inherited unchanged.**

| t | landing | half |
|---:|---|---|
| 0.0 – 1.2 s | both halves fade in **together**; nothing swept | — |
| 1.2 s | `23514`, beside `gate_closed_when_issued` | CockroachDB |
| 3.0 s | `P0001`, beside `mainline.fn_permit_merge_gate` | CockroachDB |
| 4.8 s | the enum **inside the predicate** — `'merged':::mainline.subject_state` | CockroachDB |
| 6.8 s | the three `It did not run in this request.` lines, held to the out-point | CockroachDB |
| 7.4 – 10.0 s | no sweep; card whole; **2.6 s of air** (was 1.6 s before `D35` shortened the line) | — |

**Everything else on the card is pause material by design**, which is what "confirm them
quickly" means for a list this long.

**Two things about this schedule that must be said rather than discovered on the day:**

1. **The AWS half receives no sweep landing at all.** Four landings is the cap and all four are
   CockroachDB features. The compensation is deliberate and already in the design: **the one AWS
   sentence a judge must *hear* is the Bedrock line, and it is the only thing spoken.** The AWS
   half is read, not swept; the CockroachDB half is swept, not spoken. Each half gets exactly
   one channel and they do not fight.
2. **Landing 4 is timed to sit under the spoken Bedrock line, and that is the point of the whole
   card.** At `6.8 s` the voice is on *"— not in this path"* over the left half while the
   sweep lands on *"It did not run in this request."* three times down the right half. **Those
   are the same sentence, in two vocabularies, about two vendors, at the same instant.** It is
   the one moment the parallelism buys something the sequence could not, and it is the editorial
   reason to run the halves together rather than merely the budgetary one.

   **The alignment survived `D35` and it is checkable rather than asserted**, at the file's own
   1.9 w/s: *"Every line says which."* is 4 w ≈ **2.1 s**, so it clears by `2.1 s`; *"Bedrock is
   exercised in this repository"* is 6 w ≈ **3.2 s**, landing the em-dash pause at about `5.4 s`;
   *"not in this path"* is 4 w ≈ **2.1 s**, running from roughly `5.8 s` to `7.9 s` once the dash
   is paid for. **Landing 4 at `6.8 s` falls inside the denial rather than in front of it**, which
   is a tighter fit than the refused line gave — that one only reached *"not in this path"* at
   about `5.8 s` after eleven words of preamble. **If the take drifts, the sweep moves to the
   voice; the voice never moves to the sweep.**

---

## 4 · `k2` · THE STACK — THE COCKROACHDB HALF — same 10 s

*(Was `C3`, 14 s, sequential after `C2`. It now runs beside §3 in one card; §0.5 composes them.)*

### 4.1 · Overlay text — exact

Two labelled groups. The first is what fired inside the request a judge just watched; the second
is what ran against this database earlier and what the client has read back elsewhere.

**Every word below is the committed 50 s text.** At 50 s the two groups were two *geometric*
columns; here they are two *stacked labelled groups*, which is the shape the AWS half has always
used. **The grouping is by heading, not by geometry**, and R-6 is satisfied by the heading — a
stack of two labelled groups is not a flat list, and each group keeps its own label word for
word.

```
CockroachDB  ·  IN THIS REQUEST

  CockroachDB Cloud (Basic)     aws-ap-southeast-1 (Singapore)
                                CCL v26.2.5
                                read live from GET /v1/health, not typed
  SERIALIZABLE                  one transaction, three savepoints,
                                rolled back
  CHECK constraint              gate_closed_when_issued       -> 23514
  PL/pgSQL trigger function     mainline.fn_permit_merge_gate -> P0001
  user-defined enum             mainline.subject_state
                                ((state != 'merged':::mainline.subject_state)
                                 OR (open_blocking = 0:::INT8))
                                the enum is inside the refusal message
  composite foreign keys        blocking_check -> clause_version
                                  (clause_uuid, commit_id)
                                permit_event -> subject_transition
                                  (subject_kind, from_state, to_state)


CockroachDB  ·  IN THIS DATABASE, EARLIER

  mainline.fn_check_project     a PL/pgSQL trigger function. It overwrote
                                this obligation's severity and virulence
                                from the blame closure when the row was
                                written. The gate reads its output.
                                It did not run in this request.
  recursive CTE                 the blame-closure writer,
    (WITH RECURSIVE)            db/queries/closure_write.sql:152.
                                THIS world's closure row carries
                                computed_by = demo_world.sql
                                projector_ver = demo-1.
                                It did not run in this request.
  42501                         read back by this same client during the
                                deploy, one HTTP request at a time; and
                                256/256 ungranted pairs refused in
                                privilege conformance.
                                It did not run in this request.
```

**The strap, full width beneath BOTH halves** (§0.5): it is the card's last line and the only
element that spans the vertical rule.

```
One cluster.  One region.  This repository holds no load profile, and we do not claim scale.
```

#### 4.1.1 · Measured geometry of this half

| | value |
|---|---:|
| widest line | **77 ch** |
| lines | **37** |
| was, at 50 s (§4.1 committed) | 92 ch × 33 lines |

The widest line is `((state != 'merged':::mainline.subject_state)` at its indent. **It is the
predicate, verbatim from the refusal message, and it is the third sweep landing** — it is the
last line on this card that may be re-wrapped to buy width.

**Composed `k2`**, with a 4-character gutter and rule, plus a blank line and the 92-character
strap:

```
characters across  =  67 + 4 + 77      =  148
lines tall         =  max(33, 37) + 2  =   39

width-bound   em <= 1824 / (0.6 * 148)  =  20.5 px
height-bound  em <= 1026 / (1.25 * 39)  =  21.0 px
k2 runs at the smaller:                 ~= 20.5 px

C3 alone ran at ~24.9 px (§0.5).   20.5 / 24.9  =  ~83 %
C2 alone ran at ~31.0 px (§0.5).   20.5 / 31.0  =  ~66 %
```

**`k2`'s type is roughly 83 % of `C3`'s and 66 % of `C2`'s.** That is the price of parallelism
and it is the number W4 needs. It is also the number that makes §0.5's rule enforceable: **the
two bounds land within 0.5 px of each other**, so the card is simultaneously width- and
height-limited and one added line — or one line wider than 77 characters — costs glyph size on
every other line in both halves. The re-wrap was tuned to that balance; it is not incidental.

*(The 0.6 advance ratio, the 1.25 line pitch and the 5 % title-safe margin are **assumptions
this file is budgeting with**, per rule 8, not measurements of a rendered frame. W4 must
re-measure against the actual face and the actual frame before the shoot, and if the result is
below a legible floor the remedy is §0.5's re-wrap — and, only if that fails, §0.1.1's 12 s with
its stated cost. **Never the flattening.**)*

### 4.2 · What is NOT on this half

**Retained in full from the 50 s cut. Every prohibition below still binds.**

* **No vector search, no `EXPLAIN` plan.** The C-SPANN work is real
  (`0031_clause_embedding.sql:149`, `evidence/aws/ann/ann-proof.json`) and **the demo world
  seeds no embeddings and runs no vector query.** `MUST NOT SAY:` *"vector search found the
  precursor."* The retrieval channel is `blame_ancestry` and `tau_applied = 0` —
  `demo_permit.sql:181-185` says in its own words that no threshold was consulted, so none may
  be claimed.
* **No changefeed and no CDC.** There is no `CREATE CHANGEFEED` in any of the 271 migrations;
  `v_changefeed_health` returns 0 rows; the census marks `rows.crdb_changefeed` **`DESIGNED`**.
  What the trigger writes is an **outbox row**, `mainline_ops.outbox`, `check_opened`.
  `MUST NOT SAY:` *"changefeeds propagate the lesson."*
* **No time travel.** `MNC-09`. Every date on screen is a column value and `k1`'s strap says so.
* **No row-level security claim.** `MNC-01` is this project's own headline caveat: RLS is
  evaluated by the same server a cluster admin owns, so it stops a confused query and never the
  administrator.
* **Never "multi-region", never "survives a region failure", never "tamper-proof", and never "split-view resistant" in any form, on any screen, in any caption.**
  Basic tier, one region; one witness, `q = 1`; tamper-**evident**, never tamper-proof.
* **No `merged_commit`, no `clearance_digest`, no `schema_fingerprint` on this card.** R-K
  permits `merged_commit` in the demo; there is no room for it here, and
  `clearance_digest` may never be captioned as a constant — four runs on 2026-08-15 produced
  four different digests, and if it were ever stable the rollback proof would be broken.

### 4.3 · Evidence — every feature named

**Unchanged, complete, not one row retired.**

| on-screen line | label | what proves it |
|---|---|---|
| **CockroachDB Cloud (Basic)** · `aws-ap-southeast-1` · `CCL v26.2.5` | in this request | `evidence/deploy/LIVE.md:14-22` — `cluster_version` read back from the deployed `GET /v1/health`, alongside `deploy_chain_applied 271 of 271`; tier and single region are stated at `docs/demo/research/r6-honesty.md` A7; the `ccloud` transcript is `evidence/ccloud/cluster-list.txt` (census row `evidence/tool-usage/crdb-features.json` → `rows.crdb_cloud_ccloud`, `EXERCISED`) |
| **`SERIALIZABLE`** · one transaction, three savepoints, rolled back | in this request | `evidence/deploy/live-gate-run.json` → `/data/transaction/{isolation,single_transaction,savepoints,disposition}` — the payload declares it; the read-only witness is `cluster_logical_timestamp()`, opened and closed timestamps identical; census row `rows.crdb_serializable`, `EXERCISED`, anchor `packages/trappoint-model/src/trappoint_model/cluster.py:222` (a write-skew pair REFUSED on the pinned node) |
| **`CHECK` constraint `gate_closed_when_issued`** → `23514` | in this request | declared `verticals/mainline/db/migrations/0050_permit.sql:114`; fired at `evidence/deploy/live-gate-run.json` → `/data/beats/1`, `constraint_source: reported`; census row `rows.crdb_check_constraints`, `EXERCISED` |
| **`mainline.fn_permit_merge_gate`** → `P0001` | in this request | `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql` (re-derivation at `:62-69`); fired at `live-gate-run.json` → `/data/beats/2`, `constraint_source: parsed`, message *"re-derived open obligation count is 1 while the projected counter reads zero"*; census row `rows.crdb_triggers`, `EXERCISED`, anchor `0115_fn_permit_merge_gate.sql:77` |
| **user-defined enum `mainline.subject_state`** | in this request | `verticals/mainline/db/migrations/0011_type_subject_state.sql:27`; and it is **inside the refusal the client read back** — `live-gate-run.json` → `/data/beats/1/message` contains `'merged':::mainline.subject_state` verbatim. This is the cheapest feature to prove in the whole block: the type name is in the error string, not in a caption |
| **composite foreign keys** | in this request | `verticals/mainline/db/migrations/0058_blocking_check.sql:109` — the obligation row's own two-column FK onto `mainline.clause_version (clause_uuid, commit_id)`; and `0059_permit_event.sql:66` — a **three-column** FK onto `mainline.subject_transition (subject_kind, from_state, to_state)`, enforced when beat 4's merge writes a permit event |
| **`mainline.fn_check_project`** | earlier, in this database | `verticals/mainline/db/migrations/0100_fn_check_project.sql:59-83`, welded by `0120_trg_check_project.sql`. The seed supplied `0, 'routine', 0` (`demo_permit.sql:318`, its own comment: *"projected over by fn_check_project"*) and the live row reads `severity 4, virulence blood_major` — `GET /v1/permits/{permit_id}/blocking-checks` → `/data/checks/0/{severity,virulence}`. **The proof that it ran is the delta, and the delta is live.** It fired when the row was written, not while the film's request was in flight |
| **recursive CTE (`WITH RECURSIVE`)** | earlier / elsewhere | `verticals/mainline/db/queries/closure_write.sql:152` — `WITH RECURSIVE anc (event_id, depth)`, the sanctioned writer of `0038_clause_blame_closure`; it walks `mainline.event_edge` (`0034_event_edge.sql:42` quotes the shape in its own header, and its rationale records that the only cycle guard is `depth < 64`). **See §7.1 — this world's closure row was written by the seed, and the overlay says so in the same breath as the feature name** |
| **`42501`** | earlier / elsewhere | `docs/STATE-OF-THE-BUILD.md:179-193` §12.6 — `scripts/qa/privilege_conformance.py`, **256/256 ungranted pairs refused with `42501`, 0 differences**, and that negative direction is falsifiable and was falsified; and `evidence/deploy/LIVE.md:58-71`, where five privilege gaps were found *"one HTTP request at a time"* against the deployment. See §7.2 for the half of §12.6 that is **not** claimed |
| `no load profile` · `no scale claim` | — | `docs/submission/JUDGING-AXES.md:69` already concedes it; `docs/demo/research/r1-judging.md` T6 names the concession as correct and asks only that the *positive* answer be given beside it, which the rail does |

---

## 5 · `k3` · THE LIMIT, THE RAIL, AND THE TWO URLS — 6 s

*(Table A `2:44` → `2:50` · Table B `2:24` → `2:30`. Was `C4`, 8 s.)*

### 5.1 · Why the limit closes the film and not the product

The last thing a judge hears should be the sentence a competitor could not say. Every other
project's closing seconds are a claim. This one's is a **concession stated more precisely than
anyone asked for**, and it is the single most credible six seconds available to us, because a
film that has spent two and a half minutes saying *"the database refuses"* has spent them
earning the right to say what it cannot do.

### 5.2 · Overlay text — exact, and unchanged from the 50 s cut

```
                        THE LIMIT WE WILL NOT DRESS UP

Nothing in this data model separates a considered disposition from a rubber stamp.
It makes the question unavoidable, the record precise, the worst stamp non-representable.
We measure deliberation and never threshold it.


"what makes agentic systems different from traditional apps?"
   -> the database is in the reasoning loop, as the thing that constrains the agent

"Does the agent use the tools correctly and safely?"
   -> persisted: false — this call is non-mutating by construction

"Is it used for more than toy queries ... at real scale?"
   -> transactional state, read inside the same SERIALIZABLE transaction as the decision
      — and no scale is claimed

"resilience, access control, and what happens when things go wrong?"
   -> the refusal itself; 42501 on 256/256 ungranted pairs in privilege
      conformance; a ledger that publishes
      what did not run


github.com/Shaugato/mainline
https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

**What changed here is not the text; it is when the rail arrives.** At 50 s the first three rail
lines were already on screen when `C4` began — they had arrived at `2:00`, `2:12` and `2:28` —
and `C4` added only the fourth. **Under R-3 all four arrive together, with the card.** The
practical consequence for W4 and W5: the four rail entries fade in **as one element**, with the
limit, not in sequence. §0.3 records what that costs.

**The tools panel in §5.6 arrives the same way — with the card, as one element, together with the
limit, the rail and both URLs, and never sequenced after them.** Sequencing inside a 6 s card is
exactly what R-3 took out of the rail; re-introducing it for a seven-line panel would spend that
saving twice and leave a judge reading a card that is still assembling itself. **One fade,
everything at once, held to the out-point** — and the panel is bound by the same two rules as the
rest of this card: §0.5's line limit in its `k3` form (§5.6.1, **≤ 119 characters across and
≤ 32 lines tall**) and R-C7's ban on a fifth sweep landing (§5.6.3).

**Nothing on this card is abbreviated.** All three lines of the limit, all four rail entries
with both halves of the third one's clause, and both URLs.

### 5.3 · Spoken — 10 words, one sentence

> **"Nothing here separates a considered disposition from a rubber stamp."**

**10 words · 5.3 s at 1.9 w/s in a 6 s block · 0.7 s of air.**

**The second sentence — *"We measure deliberation and never threshold it"* — is no longer
spoken. It is on screen, in §5.2's overlay, in its exact sanctioned form, unchanged.** That is
six spoken words saved and zero content lost, and §0.2 names it as the cleanest trade in the
revision.

**The scope word `here` stays, and the sentence cannot go below ten words with it intact.**
`MNC-06`'s own text is *"Nothing in this data model distinguishes a considered disposition from
a rubber stamp"*; `here` is the shortest honest stand-in for *in this data model*.

| candidate | words | what it costs |
|---|---:|---|
| *"Nothing here separates a considered disposition from a rubber stamp."* | **10** | nothing. **Chosen.** Exactly the block's budget |
| *"Nothing here separates … rubber stamp. We measure deliberation, never threshold it."* | 16 | the 50 s line. 8.4 s of speech in a 6 s block — **unexecutable**, and its second sentence is already on screen |
| *"Nothing separates a considered disposition from a rubber stamp."* alone | 9 | drops the scope word **here**, which is the whole difference between a limit and a slander |
| *"Deliberation is measured, never thresholded."* | 5 | drops sentence one, which is the film's last line and the only one a competitor cannot say |

**MUST NOT SAY:** *"Nothing separates a considered disposition from a rubber stamp"* — without
`here` that is a statement about safety records in general, which is not ours to make. **W6
files a REFUSE row against any take that drops the scope word.**

The second and third sentences of the on-screen limit are **not spoken**: *"the worst stamp
non-representable"* and *"it makes the question unavoidable, the record precise"* are the precise
form, and a judge who pauses gets them exactly. Paraphrasing them at speed is how a concession
turns back into a boast.

**The two URLs are not read aloud.** A judge reads a URL faster than anyone can say one, and
four seconds of spoken hostname is the worst trade in the film.

#### 5.3.1 · The 15-word frame-exact variant — RETIRED

At 50 s this section carried *"Nothing here separates a considered disposition from a rubber
stamp. Deliberation is measured, never thresholded."* — 15 words, passive voice, offered only
if the cut had to be frame-exact inside 8 s. **It is retired: the 22 s close's spoken line is
10 words in a 6 s block with 0.7 s of air, so there is no overrun for it to fix, and its passive
voice was its only cost.** Nothing replaces it; the primary line above fits.

### 5.4 · Evidence

**Unchanged, complete, not one row retired.**

| on-screen line | what proves it |
|---|---|
| the limit, all three sentences | `docs/submission/MUST-NOT-CLAIM.md` and scanner rule **`MNC-06-rubber-stamp`**, whose own text reads *"Nothing in this data model distinguishes a considered disposition from a rubber stamp… Claiming otherwise is the project's single worst available overclaim."* The wording on screen is the plan §5's TRUE INSTEAD column, unparaphrased |
| *"the database is in the reasoning loop"* | Cockroach Labs' own architecture framing, quoted at `docs/demo/research/r1-judging.md` §4(b); and it is literal here — the decision is a `CHECK` constraint and a PL/pgSQL trigger, `live-gate-run.json` → `/data/beats/1` and `/data/beats/2` |
| `persisted: false` — this call is non-mutating by construction | `evidence/deploy/live-gate-run.json` → `/data/persisted` (`false`), `/data/transaction/disposition` (`rolled_back`), and `/data/persistence_check/self_evidence/minted_disposition_rows_after_rollback` (`0`), keyed on a `uuid4` no other writer holds |
| transactional state in the same `SERIALIZABLE` transaction | `live-gate-run.json` → `/data/transaction/{isolation,single_transaction}`; the memory read at gate time is `0115_fn_permit_merge_gate.sql:62-69` and `:91-97`, inside that transaction |
| `42501` on 256/256 ungranted pairs in privilege conformance | `docs/STATE-OF-THE-BUILD.md:179-193`; the caveat that must travel with it is §7.2 below |
| *"a ledger that publishes what did not run"* | `docs/HONESTY.md`; `docs/CI-STATE.md`; `evidence/tool-usage/README.md`'s three-verdict table, where `NOT-AVAILABLE` exists *"so Bedrock Rerank appears… as a row with a reason, rather than as a silence"* |
| `github.com/Shaugato/mainline` | `README.md:25` — public since 2026-08-11, root `LICENSE` Apache-2.0; `docs/submission/SUBMISSION.json:21` `repo_url` |
| the live URL | `evidence/deploy/LIVE.md:8`; `evidence/deploy/APPLIED.md:16` |

**R-M holds.** No camera is pointed at `docs/submission/SUBMISSION.json` while its `demo_url`
reads `UNRESOLVED`. The live URL on screen is the origin this film was shot against, read from
the deploy record and confirmed by the request in devtools — not read off that file.

### 5.6 · THE FOUR CONTEST COCKROACHDB TOOLS — the panel on `k3`, read and never spoken

*(Numbered **5.6** and placed **here**, immediately after §5.4's evidence table, because §5.1–§5.4
and this section describe **what is on the screen** and are written in screen order, while §5.5 is
retired history. §5.5 keeps its number so that nothing pointing at it has to be re-aimed. If a
renumbering is ever done it is done to §5.5, never to this section.)*

**WHY THIS SECTION EXISTS.** `docs/submission/AUDIT.md` §5 counted the committed overlay text of
this file and found that `k2`'s AWS half names **seven services** while the whole 172 s film names
**zero of the four contest CockroachDB tools** — the string `MCP` appeared nowhere in any overlay
block here. On a CockroachDB hackathon that is backwards: the eligibility rule is about **tools**,
and a judge asking *"did they use at least two?"* could not see the answer anywhere in the film.
**This section is the answer, and it costs no second, no card and no spoken word.** §0.4.1 prices
the spoken alternative and refuses it; §0.5.1 records why the panel could not go on `k2`.

**AUTHORITY.** `docs/demo/close-card-plan.md` §2, rulings **R-C1**–**R-C7** and **R-C10**. The
text in §5.6.1 is R-C4's string of record, copied to the character; `ONSCREEN-TEXT.yaml` (W2's
file, not this one) reproduces it and invents no variant. **Where any other document prescribes
different content for these 22 seconds, this file wins** — R-C8, and
`docs/submission/census/close-block.md` §7.1 defers here explicitly rather than prescribing a
card of its own.

#### 5.6.1 · Panel text — exact, and the measured geometry

The panel sits **between the criterion rail and the two URLs** (R-C2). A judge answering an
eligibility question is doing verification, not watching a story, and §5.4 already makes the
bottom of this card the verification block. `k1` is refused as a home — §0.4 item 1 records that
it already paid the compression's sharpest cost, 12 s → 6 s of dwell on the axis-1 card, and
loading it further spends the same second twice. The end card is refused — two seconds is a held
frame whose value is that there is nothing on it to read but the name.

```
------------------------------------------------------------------------------------------------
COCKROACHDB  ·  THE FOUR CONTEST TOOLS.  THE RULES REQUIRE TWO.   three EXERCISED, one DESIGNED

Distributed Vector Indexing (C-SPANN)  EXERCISED  3 cspann, 4 VECTOR, 42809    evidence/aws/ann/
Managed MCP Server                     EXERCISED  15 of 16, DIVERGED, published   evidence/mcp/
CockroachDB Cloud + ccloud CLI         EXERCISED  cluster list -o json, parsed   evidence/ccloud/
CockroachDB Agent Skills               DESIGNED   shipped, validated;  NO RUN IS COMMITTED  skills/
```

**WHAT `EXERCISED` MEANS ON THIS PANEL, AND WHAT IT DOES NOT — read this before rendering it.**
The panel speaks the **census's verdict vocabulary** (`EXERCISED` / `DESIGNED`, from
`evidence/tool-usage/crdb-features.json`), which is **not** §1's three request-scope labels. On
this panel **`EXERCISED` means *exercised in this repository, with a committed transcript* — it
does NOT mean *in this request*.** None of the four tools ran inside the
`POST /v1/demo/gate-run` a judge just watched, and §0.5.1 is the ruling that says so. **This is
the same scope the AWS half gives Bedrock in capitals inside its box, and the panel must read as
its CockroachDB mirror.** Two consequences that bind W2 and W6:

* **The panel never sits under, beside, or visually inside anything reading `IN THIS REQUEST`.**
  It is on `k3`, which carries no such heading; it must not acquire one, and no rendering may
  place it adjacent to `k2`'s headings in a still, a thumbnail or a press-kit crop.
* **W6 files a REFUSE against any caption, subtitle, alt text or Devpost paste that expands
  `EXERCISED` to *"ran in this request"*, *"live"*, or *"in the demo"*.** The panel's own rows
  already resist it — `15 of 16, DIVERGED` is a transcript's verdict and `42809` is a refusal —
  but a caption written later by somebody who did not read this section is the failure mode, and
  it is cheap to forbid now and expensive to discover in a submitted film.

**Order is the criterion's own order**, per `docs/submission/DEVPOST.md:191`: the Technological
Implementation criterion enumerates *"distributed vector index, MCP Server, ccloud CLI"* in that
sequence, and the submission requirement names Agent Skills separately — so Agent Skills is fourth
**as the extra it is**. A judge holding `DEVPOST.md` beside the paused frame sees one list in one
order, which is the same principle that put the criterion rail in the organiser's own words on
this same card.

**`DESIGNED` is rendered equal to `EXERCISED`** (R-C5): same size, same weight, same column, no
grey, no footnote marker, no parenthesis. The heading says the ratio out loud —
`three EXERCISED, one DESIGNED` — so a judge has the count before he reads a row, and
`NO RUN IS COMMITTED` is set in the same capitals as `EXERCISED` so **the missing thing is as
legible as the present ones.** That is not decoration; it is the reason the other three rows are
believable.

**MEASURED GEOMETRY.** Same `wc -L` semantics as §0.5 (longest line, characters) and the same
budgeting assumptions, named as assumptions per rule 8: monospace advance ≈ `0.6 em`, line pitch
≈ `1.25 em`, and a 1920 × 1080 frame with 5 % title-safe margins giving `1824 × 1026` usable
pixels.

```
the panel alone   =  99 ch  x   7 lines      (measured from the block above)
k3 as committed   =  89 ch  x  24 lines      (§5.2's overlay, measured)

composed, with one blank separator line between the rail and the panel:

characters across  =  max(89, 99)  =   99
lines tall         =  24 + 1 + 7   =   32

width-bound   em <= 1824 / (0.6 * 99)   =  30.7 px
height-bound  em <= 1026 / (1.25 * 32)  =  25.6 px
k3 runs at the smaller:                 =  25.6 px

25.6 / 20.5  =  1.25 x  k2's composed glyph size   (§4.1.1)
25.6 / 24.9  =  1.03 x  the 24.9 px old C3 ran at  (§0.5)
```

**THE BINDING BUDGET, and it binds W2 as well as this file: `k3` composed must stay ≤ 119
characters across and ≤ 32 lines tall.** The card is **height-bound**, so it has **20 characters
of width headroom and none of height**: at 119 ch the width-bound falls to
`1824 / (0.6 × 119) = 25.5 px` and width takes over, which is where the 119 comes from. A
thirty-third line, by contrast, costs glyph size on every line of the limit, the rail, the panel
and both URLs at once. **This is §0.5 consequence 2 in its `k3` form**, and it is stated here so
that the card that absorbed this wave's addition is not the one card in the close without a
written line limit.

**If W2's re-measurement against the real face and the real frame lands below a legible floor,
the remedy ladder is, in order — and no step on it touches a word, a row, or the `DESIGNED`
state:**

1. **Drop the blank separator line** between the rail and the panel. `32 → 31` lines;
   height-bound `1026 / (1.25 × 31) = 26.5 px`. **Measured gain: +0.83 px.** *(The plan's ladder
   prints this as `+0.9 px`, which is what you get by differencing the two rounded figures
   `26.5 − 25.6`. The unrounded `+0.83` is the one to budget with; the discrepancy is arithmetic
   rounding, not a disagreement, and it is printed rather than reconciled silently.)*
2. **Shorten the horizontal rule.** It is decoration and carries no claim.
3. **Re-wrap the Agent Skills row onto two lines and drop the rule entirely.** This trades a line
   for width, so on a height-bound card it is the **last** step and never the first.

**Never a word. Never a row. Never the `DESIGNED` state.** Four moves are refused in advance
because each is a way of making the panel fit by making it less true: **never** drop the Agent
Skills row; **never** abbreviate or shrink `NO RUN IS COMMITTED`; **never** set `DESIGNED` smaller,
lighter or greyer than `EXERCISED`; **never** truncate an evidence path to buy characters, because
the path is what makes the row checkable.

#### 5.6.2 · What this costs `k3`, in numbers, because a change that claims to cost nothing is a change nobody should believe

**`k3` goes from 34.2 px to 25.6 px — a 25 % reduction in glyph size** on the card that carries
the film's only concession, the organiser's four criteria in their own words, and both URLs.
`ONSCREEN-TEXT.yaml` already records that `k3` is *"doing more reading work than `c4` did, in less
time"*, and this wave adds seven lines and one blank to it. **That is a real cost and this file
does not dress it up** — §0.3 and §0.4 exist for exactly this reason and this entry belongs beside
them.

Three things are true beside it and **none of them cancels it**:

* **25.6 px is still above the largest glyph size any card in this close actually runs at.** It is
  `1.25 ×` `k2`'s composed `20.5 px` — the densest card in the cut, already cleared — and `1.03 ×`
  the `24.9 px` old `C3` was cleared at. **It is below old `C2`'s `31.0 px`, and that is stated
  rather than rounded away:** `C2` was width-bound at 22 lines, and a card with 22 lines is not
  the card this one is. **Anyone repeating a claim that `k3` still runs larger than *either* card
  `k2` replaced is repeating something this file has measured to be false for `C2`.**
* **The panel is four rows a judge scans, not prose he reads.** Each row is name · verdict · three
  facts · path. The reading work is a scan down a verdict column, and the heading gives the ratio
  before the scan starts.
* **The alternative was leaving the closing card of a CockroachDB hackathon film naming seven AWS
  services and zero CockroachDB tools** — `AUDIT.md` §5's *"the largest unforced loss in the
  submission."* **A 25.6 px `k3` that answers the eligibility question beats a 34.2 px `k3` that
  does not.**

**One consequence for the cut ladder, handed to W3 rather than acted on here.** The ladder's
**rank 4** — `k3` 6 s → 4 s — is a **worse** step than it was, because the card it shortens is now
denser. It is still the last thing before `b10` and this file does not move it; but §10's record
of what rank 4 costs now has a second item, and the `why` field should carry it rather than the
old cost alone.

#### 5.6.3 · No sweep. The panel is read, never swept.

**No fifth highlight landing.** §3.5 caps the sweep at **four landings and spends all four inside
`k2`**, and that cap is inherited here unchanged. A 6 s card already carrying a ten-word spoken
line, a three-line limit, a four-stanza rail, a seven-line panel and two URLs cannot also carry a
pointer; a fifth landing would be the roving highlight `ONSCREEN-TEXT.yaml` calls *"a card nobody
reads"*. **The panel is pause material by design** — the same rule that leaves `k2`'s AWS half
unswept, for the same reason: each element gets exactly one channel and they do not fight.

#### 5.6.4 · Evidence — one row per tool, and the verdict column has a source of its own

**The panel prints a directory where the table prints a file**, because 99 characters is the
budget: the panel's `evidence/ccloud/` is the folder holding `cluster-list.txt`, named in full
below. Every command in the right-hand column was **run by this worker against this tree** and the
output pasted is the output it printed.

| on-panel row | verdict | path, as printed on the panel | what proves it — and the one command that prints it |
|---|---|---|---|
| **Distributed Vector Indexing (C-SPANN)** | **EXERCISED** | `evidence/aws/ann/` | `evidence/aws/ann/explain-unhinted.txt` — the server's own refusal, twice: `grep -c "REFUSED BY THE SERVER" evidence/aws/ann/explain-unhinted.txt` → **`2`** (lines `205` and `220`, both `SQLSTATE 42809`). The index is `ce_ann` on `mainline.clause_embedding`, declared at `verticals/mainline/db/migrations/0031_clause_embedding.sql:149`, and `evidence/aws/ann/ann-proof.json` carries the run. **`4 VECTOR` was re-measured live by this worker** on `mainline_demo`: `SELECT table_name, column_name, data_type FROM information_schema.columns WHERE data_type ILIKE '%vector%'` returns **five** rows — `clause_embedding.embedding`, `event_cue_coarse.emb_coarse`, `event_cue_embedding.emb`, `event_cue_stage.emb` (`vector`) **and `event_cue.tsv` (`tsvector`)** — so **four `VECTOR`, one `tsvector`**, matching `AUDIT.md` §4.1 exactly. **Anyone re-running this check must exclude `tsvector` or he will publish 5.** The `3 cspann` index count is `AUDIT.md` §4.1's and `close-card-plan.md` §1.3's — **this worker did not re-run it, and says so rather than inheriting it silently.** Two routes were tried and neither is a check a stranger should be handed: `crdb_internal.table_indexes` is privilege-restricted on this node (`InsufficientPrivilege`, with a hint against `allow_unsafe_internals`), and the `pg_am` compat shim reports vector indexes under no `cspann` access-method name — it returns the **five `inverted`** entries `cbc_anc`, `cue_tsv`, `cv_anchors`, `cv_trgm`, `predicate_watch_set`, which corroborate `AUDIT.md`'s *"5 gin"* and not the cspann count. **W5 should publish `SHOW INDEXES` or the census row as the one-command check for this number, never a `crdb_internal` query** |
| **Managed MCP Server** | **EXERCISED** | `evidence/mcp/` | `evidence/mcp/pack-run.json`, printed by `python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print(d['passed'],'/',d['total'],d['verdict'],d['exit_code'])"` → **`15 / 16 DIVERGED — KNOWN GAP 1`**. A second, independent transcript is `evidence/deploy/judge-run.json` (2026-08-11): 16 questions, channels `mcp` + `sql`, same verdict, five days apart. **The panel's `published` word means the transcript is published, never that an endpoint is** — see §5.6.5 |
| **CockroachDB Cloud + `ccloud` CLI** | **EXERCISED** | `evidence/ccloud/` → the file is **`evidence/ccloud/cluster-list.txt`** | a captured `ccloud auth whoami` line followed by `ccloud cluster list -o json`, **parsed rather than screen-scraped**: `tail -n +2 evidence/ccloud/cluster-list.txt \| python -c "import json,sys;print([(c['cockroach_version'],c['cloud_provider']) for c in json.load(sys.stdin)])"` → **`[('v26.2.5', 'AWS')]`**. Census anchor `evidence/ccloud/README.md:37` |
| **CockroachDB Agent Skills** | **DESIGNED** | `skills/` | `skills/` holds `designing-diachronic-gates`, `designing-vector-recall-prefixes`, a de-branded `upstream/cockroachdb-resilience-and-disaster-recovery`, and `validate-spec.py`. **`ls evidence/ \| grep -i skill` returns nothing, exit 1** — that is the whole of `NO RUN IS COMMITTED`, and it is why the row reads `DESIGNED`. The census says it in its own words: *"neither script's run is captured under `evidence/`, so they are shipped and not evidenced"* |
| **the verdict column itself** | — | not printed on the panel | `evidence/tool-usage/crdb-features.json`, which is a pure function of the source tree. `python -c "import json;d=json.load(open('evidence/tool-usage/crdb-features.json'));print([(k,d['rows'][k]['verdict']) for k in ['crdb_vector_index','crdb_managed_mcp','crdb_cloud_ccloud','crdb_agent_skills']])"` → **`crdb_vector_index EXERCISED · crdb_managed_mcp EXERCISED · crdb_cloud_ccloud EXERCISED · crdb_agent_skills DESIGNED`**. **The panel does not invent a verdict; it prints the census's.** `RULES-MATRIX.md` R6 clears eligibility on the three EXERCISED alone and explicitly does not count Agent Skills |

**The fourth command prints `DESIGNED`, and the frame already said so.** That is the entire point
of putting the state on the card: nothing a judge checks can be worse than what he was shown.

#### 5.6.5 · What is NOT on this panel — read this before adding anything

Written as a never-list for the same reason §8 is: a prohibition that does not begin with the word
`never` is a sentence the scanner and the reader both have to guess at (§9.1).

* **Never *"all four exercised"*, and never *"four tools exercised"*, in any casing, on any card,
  in any caption, in any cut-down of this panel.** Three are EXERCISED. One is DESIGNED. The
  heading states the ratio precisely so that no downstream summariser has to.
* **Never a panel with the Agent Skills row removed.** Dropping the DESIGNED row is exactly how
  *"three exercised, one designed"* silently becomes *"four tools"*, and it is a **REFUSE**. Four
  rows or the honest three-row count; never four rows' worth of credit from three rows of text.
* **Never a run of the skills assertion scripts captured to promote that row.** The tool is stated
  in the state it is in, or it is not stated at all. `assert_gate_refuses.py` and
  `assert_prefix_index_used.py` are real and they are not run for the film; **generating a
  transcript to change a word on a card is the one move this repository exists to refuse.**
* **Never an MCP route claim.** The panel cites a **committed transcript** and never an endpoint a
  judge can point a client at. `MUST NOT SAY:` *"judges can query our ledger over MCP"* — the
  credential is an account-level Cloud service-account key and
  `evidence/deploy/judge-access.json` records `credential_publishable: false`. `15 of 16,
  DIVERGED, published` reads as *"we drove it, and here is what came back"*, which is the true
  sentence. **A judge reads our ledger over pgwire as `mainline_judge`, or not at all.**
* **Never a spoken naming of any of the four tools, on any card in the close.** §0.4.1 has the
  arithmetic and R-C3 is the ruling. The panel is text a judge pauses on; the moment it is also
  something the founder says, the close is 19 words in a 10 s block with zero air and §3.5's
  landing-4 alignment is broken.
* **Never a promotion of any row by adjacency.** The verdicts come from
  `evidence/tool-usage/crdb-features.json` and change only when that file changes. **Never re-word
  `DESIGNED` to *"ready"*, *"complete"*, *"validated and ready to run"* or any phrase that reads
  as a run.** `shipped, validated` is the cleared wording and `NO RUN IS COMMITTED` travels with
  it on the same line.
* **Never a scale, latency or throughput figure on this panel.** `ann-proof.json` contains timing
  distributions; **none of them goes on screen**, per §3.2 and §8 — this repository holds no load
  profile, and a vector-index proof is not a performance claim.
* **Never a claim that a vector query ran in this film.** §4.2 stands unchanged: this demo world
  seeds no embedding and issues no vector query. The panel's C-SPANN row carries **the third
  label's meaning — exercised in this repository, not in this request path** — the same scope
  Bedrock carries, though not §1's literal heading, which `k3` does not print (§1, final
  paragraph; §5.6.1). The panel is the CockroachDB mirror of the Bedrock box and must read as one.

### 5.5 · THE 48 s / 170 s VARIANT — RETIRED, BECAUSE IT WAS EXECUTED

At 50 s this section preserved an alternate: the naming block at **48 s**, taken entirely out of
`C4` (8 s → 6 s), with `C4`'s spoken line reduced to its **first sentence alone, 10 words**, and
*"We measure deliberation and never threshold it"* left **on screen, unspoken**, where it was
already printed in its exact sanctioned form.

**Every element of that variant is now the primary.** `k3` is **6 s**. Its spoken line is
**exactly that 10-word first sentence** (§5.3). The moved sentence is **exactly where the
variant put it** — §5.2's overlay, unchanged. **The alternate was not discarded; it was taken,
and the compression went a further 26 s past it.**

| | 50 s primary | 48 s variant (was alternate) | **22 s primary (this file)** |
|---|---|---|---|
| close | 50 s | 48 s | **22 s** |
| the limit card | `C4`, 8 s | `C4`, 6 s | **`k3`, 6 s** |
| its spoken line | 16 w, two sentences | 10 w, one sentence | **10 w, one sentence** |
| *"We measure deliberation…"* | spoken **and** on screen | **on screen only** | **on screen only** |
| the overlay in §5.2 | unchanged | unchanged | **unchanged** |
| the rail | four blocks, staggered | four blocks, staggered | **whole, in `k3`** (R-3) |

**The variant's stated cost is now the primary's cost and is carried forward verbatim:** the
film's last spoken clause is a statement of the limit without the statement of what is done
instead, so a judge who is listening rather than reading hears only the concession. **At 50 s
that was the reason it was the alternate. At 22 s it is unavoidable arithmetic** — 16 words do
not fit in 6 s at any honest rate — **and the mitigation is that the missing sentence is on
screen at the moment it would have been said, in larger type than speech, in a card the film
freezes on.**

**There is no alternate variant of this file any more.** Anyone looking for the 48 s or 50 s
shape should read git history, not a preserved section: keeping a retired timing alive in a
document is how a film ends up carrying two timings, which §0.1 exists to prevent.

---

## 6 · THE END CARD — 2 s · silent

*(Table A `2:50` → `2:52` · Table B `2:30` → `2:32`. **Unchanged in content by the
compression.**)*

```
                              M A I N L I N E

        the lesson a past incident taught, as a constraint the database enforces

    github.com/Shaugato/mainline
    https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws

    SYNTHETIC CORPUS · EVERY SITE, PERMIT, INCIDENT AND PERSON HERE IS AUTHORED
```

* **No voice-over.** Two seconds is a held frame, not a sentence.
* **First and only appearance of the product name.** There is no title card before the demo; the
  name appears in the closing block, where it has been earned.
* **The watermark line is the R-L string**, unchanged, because this film's site seeds as
  `demo_site` and not as a Kestrel site (`demo_world.sql:72-76`). If the operator UI does render
  Kestrel Resources, `DEMO-HONESTY.md:35-36`'s committed string is used verbatim instead, and
  the deviation is recorded in `ONSCREEN-TEXT.yaml` (W4's file, not this one).
* **The URLs are the same two strings as `k3`**, in the same order, so a judge who paused on
  `k3` and is now typing does not have to re-find them.

---

## 7 · FINDINGS HANDED ON — three, and the first one changed this file

### 7.1 · THE RECURSIVE-CTE BLAME CLOSURE DID NOT RUN IN THIS WORLD, AND THE PLAN'S C3 LIST WOULD HAVE SAID IT DID

**This is the finding, and the compression did not touch it.** The plan's C3 list and my
original brief both name `recursive CTE blame closure` in a flat CockroachDB list, beside
`SERIALIZABLE` and the `CHECK` constraint. Those two fired in the filmed request. **The
recursive CTE did not fire in this world at all.**

`verticals/mainline/db/seeds/demo/demo_world.sql:333-341` says so in its own words, as a
recorded amendment rather than an oversight: the sanctioned writer
`verticals/mainline/db/queries/closure_write.sql` is *"a parameterised top-level statement into
which the projector binds ten positional values — a seed file that `scripts/deploy/seed_demo.py`
applies as ONE text cannot call it."* So the seed writes the closure row directly, and the row
it writes carries its own confession in two columns a judge can read live:

```
computed_by   = verticals/mainline/db/seeds/demo/demo_world.sql
projector_ver = demo-1
```

— `demo_world.sql:342-359`, served by `GET /v1/clauses/{clause_uuid}/ancestry` →
`/data/closure/{computed_by,projector_ver}` (`docs/demo/research/r2-memory.md` §3.2). I also
checked the request path directly: **there is no `RECURSIVE` anywhere under
`verticals/mainline/apps/demo-api/src/`**, so nothing in the filmed request runs one either.

Naming it in the "IN THIS REQUEST" group would have been a fake of exactly the class this
project reverted a worker for. §4.1 therefore names it in the **`IN THIS DATABASE, EARLIER`
group**, with `computed_by` in the same entry and `It did not run in this request.` beneath it —
the same treatment Bedrock gets, for the same reason, and the qualifier costs nothing because
the disclosure is already a live column value.

**Still handed to W1, W4 and W6, and the compression makes it more urgent, not less.**
`BEATS.yaml`'s `c3.on_screen` inherited the flat list verbatim: *"the CHECK constraint; the two
trigger functions; the recursive CTE blame closure; and the SQLSTATEs the client read back —
23514, P0001 and the ungranted-pair 42501."* Three of those items — one trigger function
(`fn_check_project`), the recursive CTE, and `42501` — did **not** run in the filmed request,
and `c3.on_screen` reads as though all of them did. **W1 is rewriting that block into `k2` this
wave.** If the flat list is carried across into `k2.on_screen`, the film ships a false line **on
a card that is already the densest in the cut**, where a reader is least able to catch it.
`BEATS.yaml` is W1's file and I have not touched it; **the two-group split in §4.1 is what `k2`
must render, and it is not a style choice.**

### 7.2 · `42501` — CITE THE FALSIFIABLE HALF, NEVER THE OTHER ONE

`docs/STATE-OF-THE-BUILD.md` §12.6 records **two** baselines: `120/120` granted pairs reachable
and `256/256` ungranted pairs refused with `42501`.

**Only the second may go on screen.** The positive direction is **not falsifiable as run** —
`main()` calls `apply_matrix()` unconditionally before probing, in borrowed-database mode too,
so the probe repairs the defect it is meant to detect and a missing grant cannot make it red
(`:189-193`). The negative direction *is* falsifiable and *was* falsified, with a precise red.

**MUST NOT SAY:** *"120 out of 120 granted pairs verified."* That number is real and its
verification is not, and for an `authorization_type = NONE` endpoint it is not the direction
that matters anyway. The overlay carries `256/256` alone, in §4.1 and again on the `k3` rail.
Handed to W6 for the clearance sheet.

### 7.3 · `evidence/tool-usage/aws-services.json` IS STALE WITH RESPECT TO THE APPLY — REPO HYGIENE, NOT AN ON-SCREEN PROBLEM

The census is a **pure function of the source tree** by design (`evidence/tool-usage/README.md`
§"Why there is no timestamp"), and it was generated before 2026-08-14. It therefore still reads:

| row | census verdict | census basis, verbatim in part | what `evidence/deploy/APPLIED.md` records |
|---|---|---|---|
| `aws_lambda` | `DESIGNED` | *"NOTHING IS DEPLOYED. A plan exists and a plan is not an apply"* | 24 created, `demo_url` live |
| `aws_ssm_parameter_store` | `DESIGNED` | *"NOTHING DEPLOYED — no parameter has been written and no role exists"* | the parameter is placed and `/v1/health` reads `ok=true` |
| `aws_iam` | `DESIGNED` | *"eleven `aws_iam_policy_document` data sources exist… offline"* | the execution role and `dsn_access` are applied |
| `aws_cloudwatch` | `EXERCISED` | *"METRICS READ, NOTHING PROVISIONED"* | thirteen of twenty-four applied resources are the guard |

**Nothing on screen is affected** — §3.3 cites `APPLIED.md` and `LIVE.md`, which are the later
and authoritative measurements, and the live request in devtools is itself the proof. But a
judge who opens the census reads *"NOTHING IS DEPLOYED"* beside our overlay saying `IN THIS
REQUEST`, and that is a bad thirty seconds we can avoid.

**The fix is one command** — `python scripts/submission/capture_tool_evidence.py` — and it
belongs to the owner of `scripts/**` and `evidence/**`, not to this worker: the plan forbids me
touching either. **Handed to the orchestrator, before the shoot. Still open at the time of this
revision.** I did not run it and I did not edit those files.

---

## 8 · THE BANNED LIST, AS A CHECKLIST TO READ ALOUD BEFORE THE TAKE

Every one of these is banned **on screen and in speech** for the whole 22 s. **Not one row was
retired by the compression** — a shorter block is a block with less room to notice an offence,
so the list gets stricter treatment, not looser.

Every row of the left column begins with **never**, because that is what the column is: the
never-list, not a list of things anyone is tempted to say.

| the never-list — on screen and in speech | authority |
|---|---|
| never CloudFront, never a CDN, never "edge", never a metrics console window | `CAMERA-STRINGS.yaml:127-131`; r6-honesty A6 |
| never CMEK, never PrivateLink, not even as "we would add" | `MNC-03` |
| never "multi-region", never "survives a region failure" | r6-honesty A7 — Basic tier, one region |
| never "vector search found the precursor" | r6-honesty A7 — this world seeds no embeddings |
| never "changefeeds propagate", never "CDC stream" — say **outbox row** | no `CREATE CHANGEFEED` in 271 migrations |
| never "Australian residency" — state the split instead | `MNC-02` — database Singapore, inference Sydney |
| never a p50, never a p99, never a production latency, and never **the duration-percentile alarm's name** | this repository holds no load profile |
| never "at scale", never "production scale", never "proven at scale" | §3.4.1 — the concession is unspoken in `k2`, which makes its opposite **more** dangerous, not less |
| never "our CI is green", never "we proved it in CI" | nothing in CI has ever asserted this URL |
| never "tamper-proof", and never "split-view resistant" in any form | r6-honesty A10 — tamper-**evident**; one witness, `q = 1` |
| never "120/120 granted pairs verified" | §7.2 — that direction is not falsifiable as run |
| never "the recursive CTE computed this closure" | §7.1 — `computed_by` says the seed did |
| never "`fn_check_project` runs when you press ISSUE" | §4.3 — it ran when the row was written |
| never the year 2024, in any sentence | R-E |
| never a camera on `docs/submission/SUBMISSION.json` | R-M |
| never **"all four exercised"**, never **"four tools exercised"**, never **"four tools"** as a credit — say **three EXERCISED, one DESIGNED** | §5.6.5; `AUDIT.md` **S5** — Agent Skills has no committed transcript, and the census says so in its own words |
| never speak the name of **any** of the four contest CockroachDB tools, on any card in the close | §0.4.1 — five words in front of `k2`'s line is 19 w = **10.0 s in a 10 s block, zero air**, and it breaks §3.5's landing-4 alignment. R-C3. **The panel is read, never said** |
| never **"judges can query our ledger over MCP"**, and never any wording that offers an MCP endpoint as a route into our ledger | §5.6.5; `evidence/deploy/judge-access.json` → `credential_publishable: false`. The panel cites a **transcript**; a judge reads the ledger over pgwire as `mainline_judge`, or not at all |
| never a tools panel with the **Agent Skills row removed**, and never `DESIGNED` re-worded as *"ready"*, *"complete"* or *"validated and ready to run"* | §5.6.5; `close-card-plan.md` R-C5 — dropping the DESIGNED row is how *"three exercised, one designed"* silently becomes *"four tools"* |

**Four rows were ADDED to this list on 2026-08-16 and none was retired**, which is the direction
a never-list is allowed to move. All four guard the same seam: the tools panel §5.6 puts four
CockroachDB tool names on screen for the first time, and **the moment a state on that panel is
softened, or one of those names is spoken, the panel stops being the thing that makes the rest of
the card believable.**

**The one to say out loud in the room before rolling:** *no number in these twenty-two seconds
is rounded, and no number is spoken that is not on screen.* R-K.

### 8.1 · Two clearance notes for W6, so a true string is not mistaken for a banned one

* **`mainline.blame_edge` is a table, and it stays on screen.** The banned word is *edge* in the
  content-delivery sense, forbidden by `CAMERA-STRINGS.yaml:127-131` alongside a CDN. It is not
  a ban on a substring: `mainline.blame_edge` is a real relation
  (`verticals/mainline/db/migrations/0037_blame_edge.sql`) and it is the middle hop of the STORE
  column in `k1`. Renaming it on screen to dodge a scanner would be a falsification of a schema.
  Likewise `mainline.event_edge`, cited in §4.3.
* **`create_cloudfront_invoke_grant` is quoted in §3.2 as evidence of a branch that is NOT
  taken.** It never goes on screen and is never spoken; it appears in this document only to
  prove the applied value is `NONE` and that no distribution was ever created.

### 8.2 · One new clearance note, produced by the compression itself

**The spoken year is gone from `k1` and it must not come back on the day.** §2.3 records why.
The line is *"The incident. The retrieval. Ten seconds later, the obligation. Refused."* — if a
take drifts back to *"An incident from 2019"* it is not an honesty failure (the value is on
screen) but it **is** a two-word overrun on a 10-word budget in a 6 s block, and it re-opens the
`film-recut-plan.md` §8 rule 7 question this file deliberately stepped out of. **W6: REFUSE any
take whose `k1` line exceeds 10 words.**

---

## 9 · `claim_hygiene.py --check` — THE VERDICT, AND THE RED THAT PRECEDED IT (R-B)

`docs/demo/film/` is outside every `TARGET_GLOBS` entry, so scanner coverage is not lost — it is
invoked by hand.

### 9.1 · The first draft of this file went RED, and that is recorded rather than quietly repaired

**A verbatim paste of a hygiene failure re-commits the offence** — the transcript quotes the
banned line back, so the record of the red becomes a red. That was measured, not reasoned: a
first attempt to paste the failing output turned 5 findings into 12, the seven new ones being
the paste itself. So the record below names **the rule and the line** and never the sentence,
which is lossless for anybody holding the file.

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/VO-CLOSE.md
  scanned 1 file(s) against 21 rules
  ... 5 claim-hygiene violation(s)
$ echo $?
1
```

| line, first draft | rule that fired | what was wrong |
|---|---|---|
| 19 | `HYG-sha-literal` | my own header carried a seven-hex tree literal |
| 283 | `MNC-03` | a prohibition written with "No …" — and plain *no* is **not** one of the scanner's negation markers |
| 392 | `MNC-14` | the same, split across a wrapped line so the marker and the phrase were not on one line |
| 593 | `MNC-03` | a never-list table row whose cell named the control without a marker |
| 600 | `MNC-14` | the same, one row down |

Four of the five are §8's own never-list. The scanner cannot tell a banned phrase in a
*prohibition* from one in a *claim* unless the line itself carries a negation marker, and those
four lines carried none. **The fix was to write the prohibitions as prohibitions** — every
never-list row begins with the word `never`, which is both the marker the scanner reads and the
honest way to write that column. Nothing was exempted, no rule was edited, no marker was bolted
onto a sentence that was not already a denial, and no phrase was deleted to dodge a rule.
**Every one of those repairs survives the compression unchanged.**

### 9.2 · The verdict on the 22 s revision, pasted verbatim

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/VO-CLOSE.md
  scanned 1 file(s) against 21 rules
  claim hygiene OK
$ echo $?
0
```

**Nothing in this file was softened to reach that line, and the compression did not reach it by
deleting a rule.** The two rules it comes closest to are `MNC-06-rubber-stamp` (§5.2 states the
limit) and `MNC-02-residency` (§3.1 states the split); both clear the scanner through the
documented negation exemption, because both sentences are denials — which is what they are
supposed to be. **Both sentences are on screen in the 22 s cut exactly as they were in the
50 s cut.**

#### 9.2.1 · Re-run after the 2026-08-16 tools-panel wave — still green, and re-run for a reason

The wave that added §0.4.1, §0.5.1, §5.6 and four rows to §8 put **four new tool names, two new
verdict words and a quoted MCP prohibition** into this file. §9.1's lesson is that a *prohibition*
without a negation marker fires exactly like a *claim*, so a wave that adds prohibitions is
precisely the wave most likely to go red. It was re-scanned rather than assumed:

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/VO-CLOSE.md
  scanned 1 file(s) against 21 rules
  claim hygiene OK
$ echo $?
0
```

**Nothing was softened and no rule was edited to reach it.** Every new prohibition in §5.6.5 and
§8 begins with `never` or carries `MUST NOT SAY:`, which is the marker §9.1 established and the
honest way to write that column in the first place.

### 9.3 · Falsification, because a hygiene check that has never fired is decoration

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --self-test
  planted 4 violation families, scanner fired on 4
    RED   [MNC-01-rls-vs-rogue-admin] ...
    RED   [MNC-15-upstream-merge] ...
    RED   [HYG-bare-invariant] ...
    RED   [HYG-sha-literal] ...
  self-test OK · the scanner goes red on every planted family
$ echo $?
0
```

The four planted sentences are elided here for the reason §9.1 measured: quoting them would
re-plant them in this file. **`HYG-sha-literal`'s own RED line carries a seven-hex literal in
its evidence**, so eliding is not politeness — pasting that line verbatim would make this file
go red on the very rule it is reporting, which is §9.1's lesson arriving a second time. They are in `SELF_TEST_FIXTURE` in `scripts/demo/claim_hygiene.py`,
where anybody can read them, and in `scripts/demo/fixtures/claim-hygiene-red.md`, which is
committed, deliberately non-compliant, and asserted non-zero by `.github/workflows/claims.yml`.

Two independent demonstrations that the check can go red **on this exact file**: the planted
fixture above, and §9.1, which is this file failing on its own first draft.

---

## 10 · DISSENT — the old one is withdrawn; here is what replaced it

**At 50 s this section dissented from cut-ladder rank 5** (`C4` 8 s → 4 s — *"the spoken limit;
the end card carries the URLs alone"*), on the grounds that it removed the film's spoken answer
to two of `r1-judging` T6's four unanswered scoring hooks and removed the concession that makes
the preceding two minutes credible. **That dissent is withdrawn, for two reasons, and both are
concessions to the lead rather than to the clock.**

1. **The ladder step it objected to no longer exists.** `film-recut-plan.md` §5's new ladder
   ranks `k3` **6 s → 4 s** at rank 4, and its `what_goes` is *"the spoken limit; **the screen
   keeps all three lines**."* The old rank 5 took the URLs off `k3` and left them to the end
   card. **The new step is strictly kinder than the one I objected to** — it is exactly the
   mitigation the old dissent asked for, granted before it was asked again.
2. **The alternative I proposed no longer exists either.** The old dissent said: take the four
   seconds from `C2` (16 s → 12 s) instead, *"a list a judge pauses on rather than listens to,
   and whose spoken line is already 3.4 s shorter than its block."* `C2` is gone. It is half of
   `k2`, `k2` is 10 s, and §0.1.1 shows `k2` is more likely to need **two seconds more** than to
   have four to give. **A dissent whose remedy has been deleted is not a dissent; it is a
   complaint, and this file does not file complaints.**

**What replaces it is a plain record of what rank 4 costs, so nobody executes it thinking it is
free.** If `k3` goes 6 s → 4 s:

* **the film loses its last spoken line entirely.** The close drops to 24 spoken words over
  20 s = **1.20 w/s**, and the last thing a judge *hears* becomes the tail of `k2`'s Bedrock
  line — *"— not in this path."* That is a good sentence, and it is not the sentence the film was
  built to end on. **After `D35` it is a slightly better sentence to end on than it was**, because
  the clause in front of it now says what Bedrock *is*, so the film's last spoken second is no
  longer a denial standing on its own;
* **`k3`'s screen is unchanged** — all three limit lines, all four rail entries, both URLs —
  but a four-line rail arriving whole with three lines of limit and two URLs now has **four
  seconds** and no voice under it. §0.3's clause-seconds fall from 24 to **16**;
* **the mitigation that costs nothing** is the one the old dissent already identified and W4 and
  W6 should hold ready rather than discover on the day: **the fourth rail clause reads naturally
  on the AWS half of `k2`** — access control is an AWS-block subject, and
  `authorization_type = NONE` and a narrow role are already on that overlay. It is a two-line
  edit to `ONSCREEN-TEXT.yaml` and it costs **zero seconds**. **But §0.5 forbids adding a line
  to `k2` without re-measuring the geometry**, so W4 must re-run §4.1.1's arithmetic before
  taking it, not after.

**The ladder is the lead's ruling and W1's spine, and it binds. Nothing in §0–§9 acts on this
section.**
