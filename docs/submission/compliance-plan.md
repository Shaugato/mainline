<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# COMPLIANCE PLAN — the Official Rules, verbatim, against what this repository can prove

**Authored 2026-08-16 by the rules-compliance lead. Primary source:
[`cockroachdb-ai.devpost.com/rules`](https://cockroachdb-ai.devpost.com/rules) and
[`cockroachdb-ai.devpost.com`](https://cockroachdb-ai.devpost.com/), fetched today.
Every row about our own system was measured today, not remembered.**

Submission closes **2026-08-18 17:00 EDT** — the gate measured `2d 14h` remaining when
this file was written.

---

## 0 · The three findings that change what we do

**Finding 1 — the demo is live and the submission record still says it is not.**
`scripts/submission/check_submission_ready.py` prints `FAIL  demo URL  demo_url is
UNRESOLVED`, while `curl` against
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws` returns `200`
on `/`, `/judge` and `/console`, and `POST /v1/demo/gate-run` returns a beat array with
`sqlstate` values. **Ten documents read `demo_url` out of `SUBMISSION.json` rather than
from their own prose** (the file's own `read_by` list), so every one of them currently
tells a judge the origin does not exist. This is the highest-cost technicality on the
board and it is a one-line edit plus a verification command. It is W1.

**Finding 2 — the brief's MCP premise is false, and the truth is better.** The brief says
there is "no recorded end-to-end call — no `evidence/mcp/`". There is no `evidence/mcp/`
directory, and that much is true. But `evidence/deploy/judge-run.json` **does** record a
live Managed MCP session: endpoint `https://cockroachlabs.cloud/mcp`, cluster
`7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`, database `mainline_demo`, protocol `2025-06-18`,
`tools/list` returning 12 tools, driving 16 judge-pack questions with **15 PASS**. The
run's own verdict is `DIVERGED — KNOWN GAP`. So **all four CockroachDB tools are
EXERCISED against a floor of two** — the actionable gap is that the proof is buried under
a filename nobody would guess, not that it is missing. It is W4.

**Finding 3 — "free to access" is not the clause; the real clause runs four weeks past
the deadline.** The rules say the Entrant *"must make the Project available free of
charge and without any restriction, for testing, evaluation and use by the Sponsor,
Administrator and Judges **until the Judging Period ends**."* The Judging Period ends
**2026-09-15**. Nothing in this repository states that the origin, and the budget guard
that could tear it down, must survive to that date. It is W5.

---

## 1 · The rules, verbatim, one row each

Quoted text is character-for-character from the Official Rules page. Status is measured.

### 1.1 Stage One (pass/fail — a miss here ends the entry)

> "The first stage will determine via pass/fail whether the ideas meet a baseline level of
> viability, in that the Project reasonably fits the theme and reasonably applies the
> required APIs/SDKs featured in the Hackathon."

| # | requirement | status | evidence measured today |
|---|---|---|---|
| S1 | agentic app, CockroachDB as persistent memory, deployed on AWS | **MET** | live origin answers; `POST /v1/demo/gate-run` returns real `sqlstate` refusals |
| S2 | ≥ 2 CockroachDB tools of {Managed MCP Server, Distributed Vector Indexing, ccloud CLI, Agent Skills Repo} | **MET — all 4** | `evidence/tool-usage/crdb-features.json` 12 EXERCISED / 2 DESIGNED; MCP at `evidence/deploy/judge-run.json` |
| S3 | ≥ 1 AWS service | **MET — 5 marked as having run** | gate: "Amazon Bedrock, Amazon CloudWatch, AWS Lambda, AWS IAM, AWS SSM Parameter Store" |
| S4 | "Projects must be newly created by the Entrant during the Submission Period" | **MET** | gate: "101 commits, all inside the window" |

### 1.2 Submission Requirements

> "Provide a URL to your code repository for judging and testing. The repository must
> contain all necessary source code, clear README documentation, any required
> dependencies, example configurations or datasets if applicable, and setup and run
> instructions required for the project to be functional. The repository must be public
> and open source by including an open source license file (we recommend MIT or Apache
> 2.0). **This license should be detectable and visible at the top of the repository page
> (in the About section).**"

| # | requirement | status | evidence measured today |
|---|---|---|---|
| R1 | public repo, source, README, deps, setup/run | **MET** | `gh repo view` → `PUBLIC`; gate PASS "remote is in sync" |
| R1b | **licence detectable in the About section** | **MET — measured, not assumed** | `api.github.com/repos/Shaugato/mainline` → `license.spdx_id = "Apache-2.0"`. The multi-licence REUSE tree did **not** break GitHub's detector. |
| R2 | "Provide a URL to your functional demo app." | **LIVE BUT UNRECORDED** | origin `200`; `SUBMISSION.json.demo_url == "UNRESOLVED"` → **W1** |
| R3 | "Include a text description that should explain the features and functionality" | **MET** | `docs/submission/DEVPOST.md`, 58 910 bytes / 225 non-blank lines |
| R4 | demonstration video | **NOT DONE** | `video_url == "UNRESOLVED"`; script cut to 2:52 → **W5** |
| R5 | "Identify which CockroachDB tools you used … and how — **what did the agent actually do with them?**" | **MET, discoverability weak** | `docs/TOOL-USAGE.md`; the "what did the agent actually do" phrasing is an *agentic* question → **W4** |
| R6 | "Identify which AWS Services tools you used … and how." | **MET** | `evidence/tool-usage/aws-services.json`, 28/28 cited artefacts present |
| R7 | *Optional:* architecture diagram | present | keep |
| R8 | *Optional:* feedback on CockroachDB AI tools | **worth doing** | the `N01` divergence and the `10 KiB` truncation finding are exactly this → **W4** |

### 1.3 The video sub-rules, verbatim

> * "should be less than three (3) minutes. Judges are not required to watch beyond three minutes"
> * "must include footage that shows the Project functioning on the device for which it was built"
> * "must include footage showing the CockroachDB memory layer at work"
> * "must be uploaded to and made publicly visible on YouTube or Vimeo and a link to the video must be provided on the submission form"
> * "must not include third party trademarks, or copyrighted music or other material unless the Entrant has permission to use such material."

**Two of these are quiet traps.** *"made publicly visible"* — YouTube **Unlisted** satisfies
"publicly visible" in the sense the rule means (no login required) and is the conventional
hackathon choice, but **Private does not**, and an unlisted video whose link is mistyped is
indistinguishable from a private one to a judge. *"must not include third party
trademarks"* — the film shows a console; any AWS or CockroachDB logo, any browser chrome
carrying a third-party mark, any background music at all, is a rule the judges can check
frame by frame. W5 owns both.

### 1.4 Functionality

> "The Project must be capable of being successfully installed and running consistently on
> the platform for which it is intended and **must function as depicted in the video
> and/or expressed in the text description**."

This is the clause that makes `DEVPOST.md` a liability as well as an asset: **every
sentence in the text description is a functionality promise.** W3 audits it against the
live origin.

### 1.5 Access and availability

> "Access must be provided to an Entrant's working Project for judging and testing by
> providing a link to a website, functioning demo, or a test build."
> "If Entrant's website is private, Entrant must include login credentials in its testing
> instructions."
> "The Entrant must make the Project available free of charge and without any restriction,
> for testing, evaluation and use by the Sponsor, Administrator and Judges **until the
> Judging Period ends**."

Our Function URL is `authorization_type = NONE`, so the *demo* is not private and needs no
credential. But `SUBMISSION.json.judge_access.required` is `true` and offers **two** deeper
paths, one of which contradicts our own documentation — see Ruling 8.

### 1.6 Judging criteria — verbatim, with the tie-break

> **Tie Breaking.** "For each Prize listed below, if two or more Submissions are tied, the
> tied Submission with the highest score in the **first applicable criterion listed above**
> will be considered the higher scoring Submission. In the event any ties remain, this
> process will be repeated, as needed, by comparing the tied Submissions' scores on the
> next applicable criterion."

**The brief's central strategic claim is confirmed verbatim.** The criteria are "equally
weighted" for scoring *and* lexicographic for ties, and **Agentic Memory Design is listed
first**. Product Readiness is fourth. Depth on axis one outranks breadth everywhere else.

| criterion (official name) | sentence 1 | **sentence 2 — the unanswered hook** | in `docs/submission/`? |
|---|---|---|---|
| **Agentic Memory Design** | "Does CockroachDB play a meaningful, production-grade role as the agent's memory layer?" | *"Is it used for more than toy queries — state, embeddings, context, or transactional data at real scale?"* | ✅ `JUDGING-AXES.md:73` |
| **Technological Implementation** | "Is the integration with CockroachDB tools (distributed vector index, MCP Server, ccloud CLI) quality software engineering?" | *"Does the agent use the tools correctly and safely?"* | ✅ `JUDGING-AXES.md:130` |
| **Real-World  Impact** | "How big of an impact could the project have on real users or workflows?" | *"Is the use case meaningful, not just technically impressive?"* | ❌ **ABSENT — the one real gap** |
| **Product Readiness** | "Is the design secure, observable, and scalable?" | *"Has the team thought about resilience, access control, and what happens when things go wrong?"* | ✅ `JUDGING-AXES.md:292` |
| **Creativity & Originality** | "Is this a genuinely new idea or a novel application of the technology?" | *"Does it demonstrate insight into what makes agentic systems different from traditional apps?"* | ✅ `JUDGING-AXES.md:452` |

---

## 2 · RULINGS — where the brief left something open, or was wrong

I was told to rule in writing and name my authority. I do, including where the ruling
contradicts the brief that commissioned it.

**Ruling 1 — the MCP gap as briefed does not exist. Do not manufacture evidence for it.**
*Authority:* `evidence/deploy/judge-run.json`, read today; `docs/TOOL-USAGE.md:580`.
A live Managed MCP session is recorded, 15/16 PASS. Creating an `evidence/mcp/` directory
that re-stages a call we already made would be theatre. **W4 makes the existing proof
findable and quotes its honest `DIVERGED — KNOWN GAP` verdict.** Nobody re-runs anything
against the Cloud cluster to satisfy a premise that measurement retired.

**Ruling 2 — four of the five second sentences are already answered; only one is not.**
*Authority:* `grep` over `docs/submission/`, run today. The brief asserted all five were
absent. That is false for Agentic Memory Design, Technological Implementation, Product
Readiness and Creativity & Originality. **The single genuine hole is Real-World Impact's
"Is the use case meaningful, not just technically impressive?"** — and it is the sharpest
of the five, because it is the one sentence that invites a judge to hold our engineering
against us. W2 answers exactly that one and does not pad the other four.

**Ruling 3 — the criterion is "Product Readiness", not "Production Readiness".**
*Authority:* verbatim rules text. `DEVPOST.md` and `JUDGING-AXES.md` already use the
official name; `grep` finds zero occurrences of "Production Readiness" in
`docs/submission/`. **No change. Recorded so nobody "fixes" it into being wrong.**

**Ruling 4 — the tie-break is lexicographic and confirmed.** *Authority:* the "Tie
Breaking" paragraph quoted at §1.6. Effort ordering stands: Agentic Memory Design first.

**Ruling 5 — the availability obligation runs to 2026-09-15, not 2026-08-18.**
*Authority:* "until the Judging Period ends", plus the Judging Period dates
"August 19 – September 15, 2026". **This is a new obligation no file in the repository
states.** W5 records it. Note the tension with the cost guard: a budget action that
disables the Function URL in September is a *rules breach*, not a saving.

**Ruling 6 — Agent Skills is not named in the Technological Implementation criterion.**
*Authority:* the criterion reads "(distributed vector index, MCP Server, ccloud CLI)" —
three tools. The *submission requirement* separately names "Agent Skills". **So Agent
Skills earns the ≥2-tools floor but scores nothing on the axis's own enumeration.** On
axis two, lead with vector indexing, MCP and ccloud in that order; mention Agent Skills
after. W4 owns the ordering.

**Ruling 7 — the licence requirement is fully met, including the About-section clause.**
*Authority:* `api.github.com/repos/Shaugato/mainline` → `"spdx_id": "Apache-2.0"`. The
FSL-1.1-ALv2 and CC-BY-4.0 files under REUSE did not confuse GitHub's detector. This was
the most plausible silent technicality and it is measured clear. **No change.**

**Ruling 8 — `SUBMISSION.json` contradicts `TOOL-USAGE.md` about MCP as a judge path, and
`TOOL-USAGE.md` wins.** *Authority:* `SUBMISSION.json.judge_access.how` tells a judge to
"point any MCP client at the CockroachDB Managed MCP Server"; `docs/TOOL-USAGE.md:604`
states the MCP credential is **"not publishable to anonymous judges, so this channel
cannot be the judge access path."** Both cannot be true. The honest reading is
TOOL-USAGE's, because it was written against the run that discovered it. **W1 resolves
`judge_access.how` to the psql `mainline_judge` path as the operative one and demotes MCP
to a description of what *we* exercised.** Shipping a form field that sends a judge down a
path we know they cannot walk is exactly the self-discrediting error the prohibitions name.

**Ruling 9 — the GitHub About section has no homepage URL.** *Authority:* the API returns
`"homepage": null`. The rules require only the *licence* to be visible there, so this is
**not** a breach. It is free polish and it is explicitly **out of scope** for all five
workers, because setting it is a GitHub-side action, not a repository edit.

**Ruling 10 — scope discipline.** No worker commits, deploys, touches AWS, writes SSM,
widens a grant, or edits `HONESTY.md` / `CI-STATE.md`. `/v1/openapi.json` returns `404`;
**no file in `README.md` links to it** (the only URLs in README are the repo, the clone
URL and the demo origin), so this is not a dead link and no worker chases it.

---

## 3 · The five workers — disjoint, enumerated paths

Every brief repeats the three standing prohibitions. No two workers may touch the same file.

| id | title | files owned (exclusive) |
|---|---|---|
| W1 | Resolve the submission record | `docs/submission/SUBMISSION.json`, `docs/submission/RULES-MATRIX.md` |
| W2 | The Real-World Impact hook | `docs/submission/JUDGING-AXES.md` |
| W3 | The text description as a functionality promise | `docs/submission/DEVPOST.md` |
| W4 | Tool identification and the buried MCP proof | `docs/TOOL-USAGE.md`, `evidence/mcp/README.md` |
| W5 | Video rules and the availability obligation | `docs/submission/VIDEO-KIT.md`, `docs/submission/JUDGE-START.md` |

**Ordering.** W1 is the only one whose omission is fatal on its own — a submission whose
own record says the demo does not exist. Run it first. W2 is the highest-value hour on the
lexicographic first-tie axis chain. W3 is the largest surface and the largest risk. W4 and
W5 are parallel.

**The one thing none of the five can do:** record the film. `video_url` stays UNRESOLVED
until the founder uploads it. W5 makes that step unmissable; it cannot take it.
