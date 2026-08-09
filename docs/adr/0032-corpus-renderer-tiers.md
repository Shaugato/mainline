<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0032 — Stage 2 renders in three tiers, offline by default, into a committed cache

**Status:** Accepted · **Date:** 2026-08-04 · **Decider:** corpus & demo lead · **Milestone:** K3
**Supersedes:** nothing · **Implements:** `docs/leads/corpus-demo.md` decisions **D2** and **D5**
**Depends on:** ADR 0002 (platform ground truth, findings F5 and the Bedrock inventory)
**Constrained by:** `ARCHITECTURE.md` §2.2 **S26**, §19 **GT-11**, §18 **I2**

## Context

Stage 1 authors causality and emits structure only. Stage 2 turns four thousand three hundred
and twenty-four structural nodes into prose: an ICAM narrative per event, a body per clause
revision, a justification per MOC, a revision-history "reason for change" cell per document
revision. `research/06-build/demo-engineering.md` §1 stage 2 specifies Claude Sonnet on the
Bedrock inference profile with temperature 0, strict JSON, and every response cached by
`sha256(prompt ‖ model_id ‖ prompt_version)` into a committed `fixtures/corpus/cache/`.

Three facts make the specification, as written, unshippable on the schedule.

**AWS credentials are not valid on the founder's machine.** Nothing that must exist by a date
may require a live AWS call. PL-3 is explicit and this is the exact case it names.

**The film's words cannot be model output.** `test_camera_strings_agree` asserts that the 2013
commit message is byte-identical in the authored fixture, `VO.md`, `SHOT-LIST.yaml` and the
generated honesty card. A string that a model produced is a string that can move. The camera
beats need verbatim text under version control, not a cached sample of a distribution.

**A cache that only holds model output would be empty.** It would make `--verify` pass
vacuously, give `corpus-freeze-load` nothing to fold into `MANIFEST.sha256`, and leave
`corpus.lock.json`'s renderer census with nothing to count — the census being the thing that
stops the honesty card from overstating how much of this prose a model wrote.

## Decision

### 1. Three tiers, assigned by node, chosen by a named policy

| tier | producer id (in the cache key) | what it renders |
|---|---|---|
| `authored` | `authored/verbatim-1` | the 21 camera-facing nodes, verbatim from `fixtures/corpus/authored/` |
| `template` | `template/deterministic-1` | everything else, composed from the skeleton, the gazetteer and the dated vocabulary-drift schedule |
| `bedrock` | `au.anthropic.claude-sonnet-4-5-20250929-v1:0` | the bulk, only under `--policy=model-rendered` |

The tier is a property of the node under a declared policy (`params.TIER_POLICY`), never a
runtime branch inside a renderer. `offline` is the default: camera-facing → `authored`,
bulk → `template`. That makes the census a consequence of a committed decision rather than of
whichever flag someone happened to pass on the day.

The producer id is what goes into the cache key beside the prompt. Two tiers therefore can
never collide on one entry, and changing how a deterministic tier composes prose is a bump of
its producer id, which re-keys exactly the entries it produced.

### 2. `--offline` is the default and is **enforced**

`render.netguard` patches `socket.socket.connect`, `connect_ex`, `create_connection`,
`getaddrinfo` and `gethostbyname` for the duration of the command and raises `OfflineViolation`
on any outbound attempt. Loopback is not exempt. `netguard.allow(reason=…)` is the single named
hole and has exactly one caller: the `bedrock` tier under `--allow-live`.

The claim "this corpus rebuilds with zero Bedrock calls" is then a property of the process
rather than a sentence in a README. A cache miss on a `bedrock`-tier node under `--offline` is
a hard error that prints the node id, the key and the path it looked for.

### 3. The cache holds **every** rendered node, whichever tier produced it

`fixtures/corpus/cache/<first2>/<key>.json`, plus an `INDEX.json` carrying every entry's
digest, the renderer census, the prompt versions and the prompt template digests.

The entry shape is closed (`cache.ENTRY_KEYS`) and contains **no timestamp, wall clock, random
value, hostname, path, duration, token count or request id**. `_refuse_volatile` re-checks the
serialised body against a list of such names, because `facts` and `response` are nested
free-form objects and that is where an ambient value would hide.

### 4. The cache key is `sha256(canonical_prompt ‖ model_id ‖ prompt_version)`, NUL-separated

The canonical prompt is a fixed six-field block: prompt kind, prompt version, **template
digest**, node id, system text, user text, canonical facts JSON. Two consequences are load-bearing:

* **The template digest is inside the key.** Editing a prompt therefore re-keys every entry it
  produced. The committed entries do not go stale — they go *absent*, and the rebuild is a
  visible diff. Bumping `prompt_version` in the same commit remains a procedural rule, but
  forgetting it can no longer leave a cache that silently describes text that no longer exists.
* **The node id is inside the key.** Two clause revisions can carry byte-identical facts (a
  `restate` of one clause in two documents). Without the node id they would share an entry and
  the census would under-count by however many collisions there were.

The separator is NUL because concatenating three UTF-8 strings is not injective: `("ab","c")`
and `("a","bc")` are the same bytes.

### 5. `--verify` reports three strengths and does not blur them

**STRUCTURAL** — reassemble the canonical prompt from the prompt file on disk plus the entry's
own facts; recompute `prompt_sha256` and the key; the key must equal the filename.
**INTEGRITY** — every entry's bytes match `INDEX.json`, and the file set matches the index.
**RECOMPUTED** — re-render the node and compare against the body actually on disk.

A `bedrock` entry can never reach RECOMPUTED offline. The report says `not_recomputable`, never
`ok`. The cache is tamper-**evident**, not tamper-proof, and `INDEX.json` is folded into
`MANIFEST.sha256` by `corpus-freeze-load` to make the evidence stick.

Measured on the committed tree: a tampered response with its digest and index entry updated to
match is caught at RECOMPUTED and names the key. A tampered response without them is caught
twice.

### 6. Spans are computed here, never reported by a renderer

ARCHITECTURE §18 I2: *we compute offsets; we never trust a model-reported offset.*
`render.spans.bind` is an exact-and-unique `find()`; zero matches or two matches is a build
failure naming the node and the quote. Convention: `[start, end)`, **0-based, half-open, in
Unicode code points**, so `end - start == len(quote)` is checkable by anyone holding the pair.
CockroachDB's `substring` is 1-based and length-taking, so the loader converts once:

```sql
substring(canon_text FROM span[1] + 1 FOR span[2] - span[1])
```

That snippet is emitted into the stage-2 `index.json` as `span_sql` so nobody has to rederive it.

### 7. A camera-facing node with no authored fixture is refused or deferred, **never** paraphrased

`--camera=require` (the default) refuses and names `corpus-spine-authored`.
`--camera=defer` records the node in `INDEX.json` with its owner and renders the rest. It does
**not** fall back to the `template` tier: a committed cache entry whose text is a machine
paraphrase of a camera beat would be wrong, would be committed, and would have to be *noticed*
rather than merely rebuilt. Absent is honest; wrong is not.

## Bedrock specifics, and what is not claimed about them

* **`au.*` only.** `check_profile_id` refuses `global.*` (GT-11: routes to every commercial
  region) and `apac.*` (S26: can take an Australian fatality narrative offshore) at call time.
* **boto3 `converse` directly, never the Claude Agent SDK**, which rejects `au.*` inference
  profile ids.
* **One tool, forced** (`toolChoice: {tool: …}`), schema `additionalProperties: false` with
  every property required — checked when the prompt file is parsed, recursively, including
  array items. Text output is not accepted and is not parsed as a fallback: a fallback parser
  is how malformed output becomes plausible output.
* **No Citations.** Anthropic's citations feature and schema-bound tool output are mutually
  exclusive and return 400 together. This tier binds quotes itself, which is stronger anyway.
* **No retry, no jitter.** A retry loop inside a hashed path is a machine for producing two
  different responses under one cache key.

**Not claimed:** that this profile id has been reached from this repository. It has not. ADR
0002 measured eight `au.*` Claude profiles ACTIVE in `ap-southeast-2` on 2026-08-07, so the
family exists on the account; **this specific profile id is unverified** and the request
assembly and response handling are covered by a stubbed client, not by a live call. The
renderer census in the committed `INDEX.json` reads `{"authored": 0, "bedrock": 0, "template":
4303}` and the honesty card is generated from it, so the card states this by construction.

**Residency, stated precisely (ADR 0002 F5):** inference would run in Sydney; the database is
in Singapore. No end-to-end Australian residency claim is available for this deployment and
none is made here.

## Consequences

**Good.** The corpus is complete with zero model calls and zero AWS. A judge rebuilds it from
the committed cache offline. `corpus.lock.json`'s renderer census is a fact about the cache, so
the honesty card cannot overstate the model's contribution. Regeneration is a genuine no-op:
4303 hits, no writes, unless a prompt or a producer id moved. The vocabulary drift the corpus
exists to measure is real, because the `template` tier looks its words up by date in the
schedule `corpus-blame-key` emitted rather than reaching for the current surface form.

**Costly.** The committed cache is **4304 files and ~10.6 MiB** of JSON. That is a real weight
in the repository and it is the price of the reproducibility claim; entries are written with
`indent=2` so that a corrupted one can be *read* in a diff, which is worth more than the bytes
it costs. Stage 2 also takes about two minutes on a cold cache (it rebuilds stage 1 in memory
first) and a few seconds warm.

**Accepted.** The bulk of the corpus is composed rather than model-written, so it reads with
less variety than a model would produce. Variety comes from the fact product — six event kinds
× five failure modes × four ICAM tiers × eight hazard energies × forty-seven control classes ×
four vocabulary eras — and not from sampling, which buys the property that matters: a reader
can point at any sentence and say which fact produced it. If credentials land before D-5,
`--policy=model-rendered --allow-live` re-renders the bulk under the Bedrock producer id, every
key changes by construction, and the census on the card changes with it. Nothing on camera
moves, because the camera nodes are `authored` under every policy.

## Alternatives rejected

**Cache only `bedrock` responses.** Today's cache would be empty, `--verify` would pass
vacuously, and the census would have nothing to count. Rejected: the cache is stage 2's output,
not a side effect of one tier.

**Fall back to `template` for a missing camera fixture.** Produces a committed, plausible, wrong
artefact for the one part of the corpus that appears on screen. Rejected in favour of a refusal
that names the owning worker.

**Ship a hash-of-prompt "cache" without the response.** Verifiable and useless: the judge needs
the text, offline.

**Use `apac.*` because it is broader.** Refused at call time, per S26.
