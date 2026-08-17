<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DIAGRAMS — the two pictures, and the words that carry them when the picture does not load

**Two files, both new on 2026-08-17, both under
[`docs/submission/diagrams/`](diagrams/).**

| file | what it is | who it is for |
|---|---|---|
| [`diagrams/story.svg`](diagrams/story.svg) | four panels: a fire, a rule written down, the person who wrote it leaving, and a database refusing a change thirteen years later | somebody meeting this project for the first time, in about twenty seconds |
| [`diagrams/architecture.svg`](diagrams/architecture.svg) | who calls what: the caller, the AWS services, CockroachDB, the three steps the refusal is made of, and — drawn deliberately outside the live path — the parts that are real here but are not called while a judge is looking | a reviewer who wants to know what actually runs |

**Every diagram in this repository has to survive not being seen.** A judge may open
the submission on a phone, may be using a screen reader, may be reading a printed
copy, or may hit a gallery that failed to load an image. So each diagram below gets a
**caption that says everything the picture says**, written to be read on its own. If
the caption and the picture ever disagree, the caption is the one to fix, because it
is the one more people will read.

**One term, before it is used anywhere below.** A **SQLSTATE** is the five-character
code a database returns when it accepts or refuses a write. `00000` means the write
went through. `23514` means a `CHECK` constraint — a rule the database enforces on
every write — refused it. `P0001` means a piece of code running inside the database
raised the error itself.

---

## 0 · Where each file is used

| destination | which file | note |
|---|---|---|
| Devpost, the optional **architectural diagram** field — *"Include an architectural diagram showing how CockroachDB, AWS services, and your agent interact"* | `architecture.svg` | this is the field the optional requirement names, and it is the reason this file exists |
| Devpost **image gallery** | `story.svg` **first**, then `architecture.svg` | gallery order matters: the first image is the one a judge sees beside the title. The story panel is the one a non-technical reader can act on |
| Devpost **thumbnail** (*field name unverified without logging in*) | `story.svg` | if the form takes only one image, it takes this one |
| This repository | both, linked from wherever a reader is being told what the shape of the thing is | neither file is embedded in `README.md` by this document; that file belongs to another worker (see §5) |

**Why the story picture goes first and not the architecture.** With no film recorded,
the gallery is the only picture of this submission a judge meets before the prose. The
architecture diagram answers *what did you build*, which is a question somebody has to
already care about. The story panel answers *why would anybody want this*, which is the
question that comes first.

---

## 1 · `architecture.svg` — the diagram the optional requirement asks for

### 1.1 · The caption, sixty-second version

> A judge opens a web address in an ordinary browser. There is no account, no login
> and no credential of ours — the address is deliberately open. The request lands on
> a small program AWS runs for us, which asks a second AWS service for the connection
> details it needs, and then talks to a CockroachDB database in Singapore.
>
> Inside that database, the interesting part happens. Somebody is trying to sign off a
> permit to open a live machine. The database holds, attached to that permit, a count
> of questions raised by past incidents that nobody has answered yet. While that count
> is above zero, a rule inside the database refuses to let the permit be signed off.
> Not a warning, not a red box: the write does not land, and it does not land for the
> application, for an administrator at a command line, or for a correction script.
>
> The demo then attacks its own gate: it forces that count to zero behind the
> database's back and tries the merge again. It is refused again, because the rule
> works the number out for itself rather than believing the one it is handed.
>
> Two things in the picture are drawn **outside** that path on purpose. Amazon Bedrock
> — the AWS service that runs the language and embedding models — is genuinely used in
> this repository, and it is **not** called during the demo a judge presses. Those
> steps are database queries and reach no model at all. The CockroachDB Managed MCP
> Server, a second way of asking this database questions, has genuinely been exercised
> too, and it needs a key of ours that we cannot publish, so it can never be how a
> judge gets in.

**One word the version below uses freely.** This product handles a permit the way a
codebase handles a change, so the moment of signing one off is called a **merge**, and
`merged` is the state the database refuses to let the permit reach.

### 1.2 · The caption, mechanism version

> **On the request path.** An anonymous caller reaches an **AWS Lambda Function URL** —
> a web address AWS attaches directly to a function — in region `ap-southeast-1`
> (Singapore), configured `authorization_type = NONE`, which means it accepts callers
> who present no AWS credential. That setting is deliberate and its reason is
> published: no CloudFront distribution exists in this account to sign requests for a
> credentialed URL, and a credentialed URL nothing is authorised to sign for is a demo
> nobody can reach.[^furl]
>
> Behind it, an **AWS Lambda** function runs the demo API: Python 3.13 on `arm64`,
> `256 MB`, a 14-second timeout.[^lambda] It carries no AWS SDK. Its single AWS call —
> to **AWS Systems Manager Parameter Store**, for the encrypted database connection
> string — is signed by hand, once per cold start, and cached for the life of the
> container, so a warm request makes no AWS call at all.[^ssm] The connection string is
> never a function environment variable, so it is absent from the configuration anyone
> holding read access to the function can list.
>
> The function then speaks **pgwire** — PostgreSQL's own wire protocol, which
> CockroachDB serves — over TLS, in the same region, to **CockroachDB Cloud** on the
> Basic tier: cluster `mainline-dev`, database `mainline_demo`, CockroachDB CCL
> `v26.2.5`, `aws-ap-southeast-1`, with the migration chain applied `271` of `271`
> files.[^health]
>
> **The refusal is three steps, and all three are inside the database.**
> **1 · PROJECT** — two triggers (rules the database runs itself on every write). One
> fills in an obligation's severity from the record of what caused the rule, over-
> writing whatever the writer supplied.[^project] The other adds one to a plain integer
> column on the permit row.[^materialise] Neither takes the writer's word for anything.
> **2 · PIN** — the same trigger also ticks an **epoch**, a counter that rises whenever
> a new obligation appears. A completed merge takes a composite foreign key onto
> `(permit_id, gate_epoch)`, so attaching a new obligation to an already-finished merge
> is not refused by policy; it cannot be expressed.[^pin]
> **3 · REFUSE** — a named `CHECK` constraint, `gate_closed_when_issued`, holds that a
> permit may not be `merged` while that count is above zero.[^check] Violating it
> returns SQLSTATE `23514` carrying the constraint's own name. Forge the projected
> count and a second mechanism catches it: `mainline.fn_permit_merge_gate` re-derives
> the count and raises `P0001` instead.[^gatefn]
>
> All four steps of the demo run inside one `SERIALIZABLE` transaction ending in
> `ROLLBACK`. The response reports `persisted: false`, so asking the question leaves
> nothing behind for the next reader.[^beats] The second use case, a change to a written
> procedure, refuses the same way — constraint `cr_gate_closed_when_merged`, then
> `P0001` from `mainline.fn_cr_merge_gate` — and it has **no admission step**; the run
> declares that rather than omitting it.[^cr]
>
> **Amazon CloudWatch** appears twice and the two are different. The function's log
> group and its four metric alarms exist in the account; **no artefact in this
> repository records any alarm ever moving into an alarm state**, so what is evidenced
> is the alarm, not the threshold. Separately, and off the request path, read-only
> calls read the `AWS/Bedrock` counters — invocation and token counts AWS publishes for
> free — which are the one witness in this project that AWS wrote and we did not.[^cw]
>
> **Off the request path, and labelled so on the diagram.** MAINLINE's recall agent —
> the program that reads a site's memory — runs in this repository, not in the Lambda.
> It calls **Amazon Bedrock** in `ap-southeast-2` (Sydney): Claude for reasoning, Titan
> Text Embeddings v2 for the numbers that stand for a clause. Every such call carries
> an AWS-minted request id in the evidence.[^bedrock] It then searches CockroachDB's
> vector index, `ce@ce_ann`, naming the index explicitly in the statement, because the
> unhinted plan at this scale is a declared full scan.[^ann] The **CockroachDB Cloud
> Managed MCP Server** is a separate channel that has been exercised: `15` of `16` pack
> questions answered, with the run's own verdict left at `DIVERGED — KNOWN GAP` and its
> one failure preserved. It opens with an account-level CockroachDB Cloud key that is
> not publishable, so it cannot be the judge access path.[^mcp] **CockroachDB Agent
> Skills** is drawn as a note rather than as a path: the skills are written and on
> disk, each shipping a script a reader can run, and no run of either is recorded under
> `evidence/`.[^skills]

### 1.3 · Every element, and whether a judge's request touches it

| element on the diagram | on the demo's request path? | what it is doing |
|---|---|---|
| a judge's browser, or `curl` | **yes** — it is the caller | holds no credential of ours |
| AWS Lambda Function URL, `ap-southeast-1` | **yes** | `authorization_type = NONE`; the front door |
| AWS Lambda, the demo API | **yes** | runs the four steps as SQL |
| AWS Systems Manager Parameter Store | **yes, on a cold start only** | hands over the encrypted connection string; a warm container does not call it |
| CockroachDB Cloud Basic, `mainline_demo` | **yes** | where the refusal happens |
| PROJECT — `check_project`, `check_materialised` | **yes** | fills in severity; adds one to the count |
| PIN — `epoch_pin_permit` | **yes** | ties a finished merge to the epoch it finished under |
| REFUSE — `gate_closed_when_issued`, `mainline.fn_permit_merge_gate` | **yes** | returns `23514`; returns `P0001` when the count is forged |
| Amazon CloudWatch — the function's log group and alarms | **yes, as a side effect** | the function writes logs; no alarm is recorded as having fired |
| Amazon CloudWatch — reading `AWS/Bedrock` counters | **no** | a separate read-only programme, run by us, off the wire a judge touches |
| Amazon Bedrock, `ap-southeast-2` | **no** | real in this repository; the four demo steps call no model |
| MAINLINE's recall agent | **no** | runs in this repository, not in the Lambda |
| CockroachDB vector index `ce@ce_ann` | **no** | the recall agent's read path, not the demo API's |
| CockroachDB Cloud Managed MCP Server | **no** | exercised, and needs a key we cannot publish |
| CockroachDB Agent Skills | **no — and not a path at all** | written and on disk; no recorded run |

**Nine elements are on the path and six are not, and the diagram draws the boundary as
a dashed panel with the words on it.** That is the single most important line in the
picture. A diagram that put Amazon Bedrock inside the live request path would be the
largest overclaim available to this submission, because it would suggest a judge's
click causes a model call. It does not. The four steps are SQL.

### 1.4 · What the diagram deliberately does not draw

* **No logo, wordmark or brand colour of any third party**, and no browser chrome.
  Service and product names appear as plain text only. The contest rules permit judges
  to inspect submitted media frame by frame for exactly this, and the same discipline
  should hold for a still image as for a film.
* **No CloudFront.** It is written into the infrastructure and cannot be applied: this
  account is refused new distributions pending a verification only AWS Support can
  lift. Drawing a box that does not exist would be the same offence in the other
  direction.[^cf]
* **No arrow into Agent Skills.** It is named as a note. An arrow is a claim about a
  path, and no run of either skill is recorded.
* **No timings.** Nothing in this repository has measured the cross-region hop under
  load, so the diagram states geography and says nothing about speed.

### 1.5 · Where each label's wording comes from

Every element above is transcribed from one of the following. Nothing on the diagram
was written from memory.

[^furl]: `infra/modules/demo-api/variables.tf:103` is the `default = "NONE"` line;
    `infra/modules/demo-api/main.tf:432` passes it to the URL; the committed plan carries
    `authorization_type = "NONE"` at `evidence/deploy/terraform-plan-furl.txt:351`. The
    CloudFront reason is `docs/TOOL-USAGE.md` Part 2, *AWS Lambda, IAM, SSM Parameter
    Store*.
[^lambda]: `infra/modules/demo-api/main.tf:326` opens the function; the plan gives
    `memory_size = 256` and `timeout = 14` at
    `evidence/deploy/terraform-plan-furl.txt:290` and `:315`.
[^ssm]: The signed call is
    `verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:214`; the single grant is
    `infra/modules/demo-api/main.tf:280`, scoped to one parameter ARN at `:285`.
[^health]: `evidence/deploy/live-health.json` — `ok true`, `deploy_chain 271/271`, and the
    cluster version string. Re-derive it with one unauthenticated `GET /v1/health` against
    the demo address in `docs/submission/SUBMISSION.json`.
[^project]: `verticals/mainline/db/migrations/0100_fn_check_project.sql` is the function and
    `0120_trg_check_project.sql:28` is the `BEFORE INSERT` trigger that attaches it. Its own
    header states the overwrite is unconditional: a supplied value is replaced whether or not
    it agrees.
[^materialise]: `verticals/mainline/db/migrations/0101_fn_check_materialised.sql:62` is the
    `UPDATE mainline.permit SET open_blocking = open_blocking + 1, gate_epoch = gate_epoch + 1`;
    `0121_trg_check_materialised.sql:30` is the `AFTER INSERT` trigger that attaches it.
[^pin]: `verticals/mainline/db/migrations/0071a_epoch_pin_permit.sql:36` — the composite
    foreign key on `(permit_id, gate_epoch)`.
[^check]: `verticals/mainline/db/migrations/0050_permit.sql:114` —
    `CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0)`.
[^gatefn]: `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:77` — the
    `RAISE EXCEPTION USING ERRCODE = 'P0001'`.
[^beats]: `evidence/deploy/live-gate-run.json` — the four steps answered over HTTP by the
    deployed address, verdict `PROVEN`, `persisted false`; and
    `evidence/demo/live-beats.json`.
[^cr]: `qa/live2.json` — verdict `PROVEN`, with the admission step recorded as absent rather
    than omitted. `README.md`'s two-use-case table states the same thing in one line.
[^cw]: `scripts/aws/cloudwatch_evidence.py:299` is the read-only guard that refuses any
    operation outside a six-item allow-list before the request is signed;
    `evidence/aws/cloudwatch/bedrock-metrics.json` and `reconciliation.json` hold what it
    read. The log group is `infra/modules/demo-api/main.tf:239` and the four alarms are at
    `:581`, `:615`, `:648` and `:757`.
[^bedrock]: `evidence/deploy/aws-live.json` — a `Converse` call and a Titan v2 `InvokeModel`
    call, each `200`, each carrying the request id AWS returned;
    `packages/mainline-agentkit/src/mainline_agentkit/transport.py:273` is the residency
    check that refuses any model identifier without the `au.` prefix.
[^ann]: `verticals/mainline/db/migrations/0031_clause_embedding.sql:149` declares the index
    inline at `CREATE TABLE`;
    `skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py` is the
    committed assertion that goes red when the plan stops choosing it.
    `docs/TOOL-USAGE.md` Part 1 records the measurement: unhinted, the plan is a declared
    `FULL SCAN`.
[^mcp]: `evidence/mcp/pack-run.json` — `15` passed of `16`, verdict `DIVERGED — KNOWN GAP`;
    `evidence/deploy/judge-access.json` records `mcp_channel.credential_publishable: false`.
[^skills]: `docs/TOOL-USAGE.md` Part 1, Tool 4, whose verdict is `DESIGNED` and whose own
    words are that they are shipped and not yet evidenced.
[^cf]: `infra/modules/demo-api/main.tf:22` and `docs/deploy/RUNBOOK.md` §1 record the
    verbatim `403 AccessDenied` and the fact that the calling identity holds administrator
    access, so it is an account-level hold rather than a permissions defect.

---

## 2 · `story.svg` — the picture for somebody who has never met this project

### 2.1 · The caption

> **A made-up story, in four steps.** In June 2013 a seal on a big machine catches
> fire. Two contractors working nearby are burned. The alarm that should have warned
> them was set too high.
>
> In August 2013 an engineer lowers that alarm from 150 °C to 135 °C, so it trips
> sooner and gives people time to get out — and he writes down why. The record keeps
> one line: lowered after the seal fire, two contractors burned.
>
> In 2021 he leaves. Everyone who was in the room leaves. The rule stays behind as a
> bare number on a form, and nothing on the screen says why it is 135 °C. Normally,
> this is where the reason is lost for good.
>
> In 2026 another engineer proposes putting the alarm back to 150 °C. He is not
> careless — the manufacturer's manual says 150 °C, and the alarm nuisance-trips on hot
> afternoons. But the record still knows about the fire, and nobody has ever answered
> for it. So the change will not save. Somebody has to answer for the fire first, by
> name and in writing.
>
> That last step is the whole point. It is not a reminder placed next to the button. It
> is a condition of the button working.
>
> **The people, the plant and the incident number are invented. The refusal is not:** it
> happens on a real database, and the record of it is in this repository.

### 2.2 · Panel by panel, for a reader who cannot see the picture

| panel | date on it | picture | words |
|---|---|---|---|
| 1 | June 2013 | a flame, with two small figures either side of it | *A fire, and two people hurt.* A seal on a big machine catches fire. Two contractors working nearby are burned. The alarm that should have warned them was set too high. |
| 2 | August 2013 | a vertical scale, an arrow pointing down it, `150 °C` at the top and `135 °C` in bold at the bottom | *It is fixed — and the reason written down.* An engineer lowers the alarm from 150 °C to 135 °C so it trips sooner and gives people time to get out. He writes down why. The record keeps one line: lowered after the seal fire, two contractors burned. |
| 3 | 2021 | a page with writing on it stays; a faded figure walks away from it | *The one who knew it leaves.* He moves on. Everyone who was in the room moves on. The rule stays behind as a bare number on a form. Nothing on the screen says why it is 135 °C. Normally this is where the reason is lost for good. |
| 4 | 2026, in a red-bordered panel | a form with a heavy red bar straight across it, and an unsigned signature line beneath | *The database says no.* An engineer proposes putting the alarm back to 150 °C. He is not careless — the maker's manual says 150 °C. The record still knows about the fire, and nobody has answered for it. So the change will not save. Someone has to answer for the fire first — by name, in writing. |

### 2.3 · Where the dates and the two numbers come from

Every date and number in the story is transcribed from this repository's own corpus,
not written for the picture:
`verticals/mainline/packages/mainline-corpus/src/mainline_corpus/gazetteer/anchors.yaml`
gives `2013-06-12` for the fire, `2013-08-04` for the change that followed it,
`2021-07-16` for the author's departure, and `150` and `135` as the manufacturer's and
post-incident settings. `verticals/mainline/demo/script/CAMERA-STRINGS.yaml` carries
the revision-history line itself, asserted byte-identical across four files by
`tests/unit/corpus`, with a header noting that its arrow and dash are load-bearing and
must not be tidied.

**Nobody dies in this story, and the picture does not say anybody does.** The corpus
records the two contractors as suffering partial-thickness burns and rates the incident
at severity `4`, deliberately not `5`; its own comment says so, and a fatality is on the
list of things that may never appear on camera. A sentence about a death would be an
overclaim inside a fiction, which is a strange thing to be caught doing and an easy one
to avoid.

### 2.4 · The words that are not in that file, on purpose

`story.svg` contains no technical term at all. It does not say *projection*, *epoch*,
*obligation*, *disposition*, *blame ancestry*, *SQLSTATE*, *constraint*, *trigger*,
*merge* or *transaction*. It says *fire*, *alarm*, *record*, *form*, *save* and *sign*.
The one arguably technical word is *database*, and it is in the title on purpose,
because the surprise the picture is built around is that the refusal comes from there
rather than from a person or a policy.

Check it in one line, no network and no credential:

```bash
python -c "import re;t=open('docs/submission/diagrams/story.svg',encoding='utf-8').read();b=re.findall(r'>([^<>]+)</text>',t);j=[w for w in ('projection','epoch','obligation','disposition','ancestry','SQLSTATE','constraint','trigger','merge','transaction','permit','clause','vector','schema') if any(w in s.lower() for s in b)];print('jargon in visible text:',j or 'none')"
#  ->  jargon in visible text: none
```

That command reads only the text a viewer sees. The file's own comment header and its
accessibility description do use ordinary words like *corpus* and *refusal*, because
they are addressed to a developer and a screen reader rather than to the panel.

---

## 3 · Using these files

### 3.1 · They are self-contained, and here is how to check

Both files load nothing from anywhere. No external font, no remote image, no script,
no network reference of any kind. The only `http://` string in either is the SVG
namespace declaration, which is an identifier rather than a fetch, and the only `url(`
references point at arrowhead definitions inside the same file.

```bash
python - <<'EOF'
import re, pathlib
for p in sorted(pathlib.Path("docs/submission/diagrams").glob("*.svg")):
    s = p.read_text(encoding="utf-8")
    ext = re.findall(r'https?://(?!www\.w3\.org/2000/svg)[^\s"\')<]+', s)
    print(f"{p.name:18} script={'<script' in s}  image={'<image' in s}  "
          f"xlink={'xlink:href' in s}  external={ext or 'none'}")
EOF
```

### 3.2 · They are readable on a light page and on a dark one

Neither file relies on the host page's colours. Each paints an opaque background
panel of its own and sets every text and stroke colour explicitly, so dark text is
never left standing on a transparent background. That is a deliberate choice over the
alternative — a `prefers-color-scheme` rule inside the SVG — because a media query
inside an SVG is honoured inconsistently once the file is embedded in a gallery, or
converted to an image, or pasted into a document, and all three of those are going to
happen to these files. A picture that is beautiful in one theme and unreadable in the
other is worse than one that looks the same everywhere.

### 3.3 · If a destination will not take SVG

Devpost's gallery historically prefers raster formats. **Neither file has been
converted, and this document does not claim a conversion that has not happened.** The
route that needs no new dependency is the Playwright already vendored under
`verticals/mainline/apps/console/node_modules`, driven headlessly against a
`file://` URL of the SVG with the viewport set to the file's own `width` and `height`
attributes — `1240 × 1104` for `architecture.svg`, `1240 × 606` for `story.svg` — and
`deviceScaleFactor: 2` for a legible result. Whoever runs it should re-read the output
at full size before uploading it: the failure mode of an automated rasteriser is a
correct image with one clipped line, and a clipped line in the panel that says what is
*not* on the request path is the one clipped line this submission cannot afford.

---

## 4 · The five rules these files were drawn under

1. **Nothing is drawn that the tree cannot prove.** Every box in `architecture.svg`
   resolves to a file, a line or a committed artefact in §1.5.
2. **Nothing is promoted.** Agent Skills stays `DESIGNED` and appears as a note, not a
   path. Amazon Bedrock stays *real in this repository and not in the demo's request
   path* — both halves, in the picture and in the caption. The change to a written
   procedure stays *no admission step*. The Managed MCP run keeps its own
   `DIVERGED — KNOWN GAP` verdict and its single failure.
3. **No third-party logo, wordmark or brand colour, and no browser chrome.** Service
   names are plain text.
4. **No marketing voice.** There is no adjective in either file that a reader could
   not check.
5. **The caption is the deliverable, not the decoration.** If somebody has to see the
   picture to understand the submission, the diagram has failed, and §1.1 and §2.1 are
   written to make that impossible.

---

## 5 · Two corrections owed to files this document may not edit

**Both are reported here and applied nowhere.** `docs/submission/RULES-MATRIX.md` and
`README.md` belong to other owners in this wave, and a diagram worker editing a
compliance matrix is how two documents come to disagree about which one is
authoritative.

### 5.1 · The optional diagram requirement is absent from the rules matrix, not merely wrong in it

The plan that commissioned this work states that `RULES-MATRIX.md` §1.2 marks the
architecture-diagram row *"present"*. **Measured today, that row does not exist.** The
strings `diagram` and `architectural` appear nowhere in
`docs/submission/RULES-MATRIX.md`, in any case:

```bash
grep -ci "diagram\|architectural" docs/submission/RULES-MATRIX.md   # -> 0
```

Its §1 table is the eight numbered rules `R1`–`R8`, and neither optional requirement
has a row at all. The heading *"Requirement 6 of the gate"* at §3 is about free and
unrestricted judge access — a different numbering from the contest's own, and not this
requirement.

**Why the distinction changes the fix.** A row wrongly marked *present* needs its
verdict corrected. A requirement with no row needs a row added, and needs somebody to
ask the same question of the other optional requirement, which is also absent. The
recommendation to that file's owner is to add two rows — the architectural diagram and
the platform feedback — with whatever verdict is true when they look, and to say in the
cell that the optional requirements were tracked separately from `R1`–`R8` until this
wave. **That is a correction to a plan's description of a file, not a defect in the
file's own eight rows**, every one of which still resolves.

### 5.2 · The author's departure year is `2021` in the corpus and `2017` in four documents

The brief for this diagram gave the year the author leaves as `2017`. **Every corpus
artefact says `2021-07-16`** — `anchors.yaml:57`, `people.yaml:252` and
`CAMERA-STRINGS.yaml:58` — and `2017` matches no date in the corpus at all.
`story.svg` therefore says 2021, and `README.md` already says 2021, having been
corrected in an earlier wave that recorded the finding at
`docs/submission/readme-parts/01-opening.claims.md`.

**Four documents assert `2017` as fact, and none of them is this worker's to edit.**
Each line below resolves to the sentence today, and in three of them the replacement is
*2017* → *2021* and nothing else:

| file | line | note |
|---|---:|---|
| `docs/ARCHITECTURE.md` | 20 | *"an engineer who left the company in 2017"* |
| `docs/story/ORIGIN.md` | 20 | *"That person left the company in `2017`"* |
| `docs/submission/JUDGING-AXES.md` | 335 | **two problems, see below** |
| `docs/submission/DEVPOST.md` | — | already reported by that page's own owner; see the paragraph after this table |

**The `JUDGING-AXES.md` line needs a second pair of eyes, not just a year.** It reads
*"the person who knew why it existed left in 2017 — that is the ordinary way a
fatality's lesson is undone"*. The year is wrong the same way the others are. The word
**fatality** is the harder one: read as a general remark about industry it is
defensible, but it sits on the sentence describing this project's own use case, so a
reader will attach it to `INC-2013-044` — where **nobody dies**, the corpus records two
contractors with partial-thickness burns at severity `4`, and
`docs/submission/MUST-NOT-CLAIM.md` §3 forbids inventing a fatality. **This is reported
as a question for that file's owner rather than as a defect**, because only they can say
which reading was meant. That file is on the untouchable list for this wave and is not
edited here.

**`docs/submission/DEVPOST.md` carries it too, and needs no second report.** That page's
own owner has already found it, together with three further contradictions in the same
*Inspiration* block — the clause date, the punctuation of the quoted line, and a phrase
about a *"thirteen-year-old death"* when nobody in the corpus dies — and has published
the exact replacement text on the page itself, under the same report-rather-than-apply
discipline. **Two workers arriving independently at the same four defects, from
different directions, is the strongest thing that could be said for the method**, and
duplicating the report would only give the orchestrator two instructions for one
paragraph. It is named here so a reader of this page does not think it was missed.

---

## 6 · Related pages

* [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) — every CockroachDB tool and AWS service with
  a file, a line and a verdict saying whether it has actually run. It is the source
  behind most of §1.5.
* [`docs/story/ORIGIN.md`](../story/ORIGIN.md) — the same story as §2, at greater length,
  and the three-step mechanism stated normatively.
* [`docs/HONESTY.md`](../HONESTY.md) — what is proven, what is authored and what is not
  built. Neither diagram may claim anything that page denies.
* [`docs/submission/MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) — the flattering sentences
  this project is not entitled to say. Both captions were read against it.
