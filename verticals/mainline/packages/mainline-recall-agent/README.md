<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-recall-agent` — model providers

The only code in MAINLINE that talks to Bedrock, and the reason the rest of the recall
domain runs with **no AWS account, no network and no model weights**.

Two contracts, both in `providers/types.py`:

| Protocol | Method | Implementations |
|---|---|---|
| `EmbeddingProvider` | `embed(texts, facet) -> list[Vector1024]`, `coarse(vecs) -> list[Vector256]`, plus stable `model_id` / `index_gen` | `BedrockTitanV2`, `LocalBGE`, `SurrogateEmbedder`, `ReplayEmbeddingProvider` |
| `JudgeProvider` | `judge(system_blocks, user_payload, schema) -> ValidatedModel` | `BedrockClaudeJudge` (live or cassette transport) |

Authority: `ARCHITECTURE.md` §6.4 (rerank is in-region Claude, **not** Bedrock Rerank —
that is absent from `ap-southeast-2`), §6.6 (the latency table this package's budget lives
in), §8.4 (structured-output contract, refusal handling, prompt-injection posture), §10.1
(residency); `docs/leads/recall.md` **D4–D7**.

---

## Run it

```bash
# The CI and demo default. No credentials, no network, no weights.
MAINLINE_RECALL_PROVIDER=cassette uv run pytest tests/unit/recall_providers
```

| Environment variable | Meaning |
|---|---|
| `MAINLINE_RECALL_PROVIDER` | `cassette` (default) · `bedrock` · `local` |
| `MAINLINE_RECALL_CASSETTE_DIR` | Override the cassette root (`tests/fixtures/cassettes/recall`) |
| `MAINLINE_RECALL_EMBED_MODEL` | In cassette mode, replay this recorded embedding space instead of the surrogate |
| `MAINLINE_RECALL_CASSETTE_MODE` | `replay` (default) · `record` |
| `MAINLINE_RECALL_ALLOW_NETWORK` | Second, independent opt-in required for recording |
| `MAINLINE_RECALL_REQUIRE_FITTED_PROJECTION` | Make loading the *provisional* coarse projection a hard failure. **Set this anywhere a recall number is published.** |
| `MAINLINE_BGE_REVISION` | The pinned bge-large weights revision. `LocalBGE` refuses to construct without one. |
| `AWS_REGION` | Must be `ap-southeast-2`; `BedrockTitanV2` refuses anything else. |

---

## The decisions this package implements

**D4 — two embedding spaces, and they may never be mixed.**
`BedrockTitanV2` is `amazon.titan-embed-text-v2:0` at 1024-d; its coarse 256-d vector is
Matryoshka truncation plus **client-side** renormalisation, which is legitimate because
Titan v2 is MRL-trained. `LocalBGE` is `BAAI/bge-large-en-v1.5` (MIT, natively 1024-d, so
the DDL is unchanged); its coarse vector comes from a **committed projection**, never
truncation, because bge is not MRL-trained and truncating it would be a false claim.
`assert_homogeneous(rows)` raises if one corpus carries more than one `embed_model`, and
optionally more than one `index_gen` — cosine across two spaces is a number with no meaning
and it is a number that reaches a supervisor as `p_relevant`.
The "never truncation" half of D4 is a test, not a comment:
`test_local_bge_corpus.py::test_local_bge_coarse_is_a_projection_and_provably_not_a_truncation`
computes what Matryoshka truncation *would* have returned for every cue in the fixture
corpus and requires the shipped coarse vector to disagree with it, so replacing
`LocalBGE.coarse` with a prefix goes red instead of quietly shipping a false claim.

**D5 — the judge's identity is resolved at runtime, never hard-coded.**
`resolve_inference_profile()` calls `bedrock:ListInferenceProfiles`, asserts the `au.`
prefix, walks a declared tier ladder if the requested tier has no Australian profile, and
returns a `ResolvedModel` the caller pins into `recall_policy`. `global.*` and `apac.*` are
refused, not preferred-against. A `recall_policy` row replayed through `pinned_model()` is
re-asserted for residency: a stored row is not a bypass.
`tests/unit/recall_providers/test_no_hardcoded_model_ids.py` greps the whole package for
Claude model ids, cross-region profile ids and Bedrock ARNs. Exactly one model-id literal is
permitted, in one file — the Titan **embedding** id, because ARCHITECTURE §10.1 records
that embedding models cannot use inference profiles at all, so there is no ARN to resolve.

**D6 — structured output, then one repair, then a dead letter.**
`output_config.format` carries a `json_schema` with `additionalProperties: false` and
`strict: true`, **and** the response is re-validated client-side with Pydantic. On a schema
violation the judge makes exactly **one** more call, carrying the validator's own error
verbatim, and then raises `DeadLetter` with both raw completions and both errors so the
caller can write `silence_ledger(reason='abstained')`. The loop is written out longhand;
a blanket-retry helper is banned (ARCHITECTURE §6.5) and a test asserts the transport was
called twice, never three times.

`stop_reason` is read **before** `content`. A refusal raises `ModelRefusal` so the caller
writes `silence_ledger(reason='model_refusal')` and falls back to channels A+B client-side —
*a precursor the model declined to summarise must still block the merge.* A test spies on
the validator and asserts it was never called on a refusal, so reordering the two lines
turns the suite red.

Every exception that must become silence carries its reason as a class attribute, and a
test asserts each one is inside the closed D10 vocabulary:

| Exception | `silence_reason` |
|---|---|
| `ModelRefusal` | `model_refusal` |
| `ModelTruncated` | `truncated` |
| `DeadLetter` | `abstained` |
| `ProviderUnavailable` | `unreachable` |
| everything else | `None` — a defect, and it must crash rather than be recorded as silence |

**D7 — prompt caching on the listwise judge.**
`build_system_blocks(rubric, facet_definitions, few_shots, prompt_version)` returns a
`SystemPrefix` whose `wire()` puts `cache_control: {"type": "ephemeral"}` on the **last**
block; volatile content goes in the user turn after the breakpoint. The prefix refuses to
contain a block declared unstable, and a conservative scan rejects UUIDs, ISO-8601 instants
and per-request markers. `last_usage` exposes `cache_read_input_tokens`.

The user turn additionally carries ARCHITECTURE §8.4 layer 2: the payload is wrapped in a
sentinel-tagged `<untrusted-data-…>` span. The sentinel is derived from the payload rather
than a CSPRNG so the run stays replayable and cassette-keyable; it is still per-request and
still unpredictable to any single injected span.

---

## Cassettes

Keyed by `sha256(JCS(request))` — RFC 8785 canonical JSON, implemented in `canonical.py`
(sorted by UTF-16 code unit, ECMAScript number formatting, NaN and Infinity refused). Each
cassette stores the canonical request beside the digest it claims, and loading recomputes
it, so a cassette edited to change what the model "said" **fails to load** rather than
quietly rewriting a fixture a gate test depends on.

Replay is the default. Recording requires two independent opt-ins
(`MAINLINE_RECALL_CASSETTE_MODE=record` **and** `MAINLINE_RECALL_ALLOW_NETWORK=1`), because
recording issues real, billable calls against real safety narratives.

```bash
# On a machine with credentials or weights:
MAINLINE_RECALL_CASSETTE_MODE=record MAINLINE_RECALL_ALLOW_NETWORK=1 \
  python -m mainline_recall_agent.providers.record --provider bedrock

# Regenerate the handwritten judge fixtures after a prompt change:
python tests/unit/recall_providers/make_fixture_cassettes.py
```

Regeneration is **idempotent**: a constructed cassette (`handwritten` / `surrogate`) whose
content is unchanged keeps the `recorded_at` it already had, so re-running the generator
produces an empty diff and a genuine fixture change is visible in review instead of hiding
inside 32 re-stamped files. A *live* cassette always re-stamps, because there its timestamp
says when the call was observed and is evidence.

The suite's offline claim is enforced rather than documented: an autouse fixture in
`tests/unit/recall_providers/conftest.py` refuses outbound socket connections, so a
provider that quietly acquired a session and reached the network would fail the suite
instead of passing it slowly.

---

## What is **not** proved here — read this before quoting anything

AWS credentials are not valid on the build machine and the bge-large weights are a network
fetch. Four consequences, each visible in the artefacts rather than only in this file:

1. **The committed coarse projection is provisional and is not PCA.** It is a sparse ternary
   (Achlioptas) random projection derived from a declared keystream, committed so the coarse
   sweep is runnable and bit-stable offline. Its sidecar says `fit_status: "provisional"`,
   `fit_method: "sparse_ternary_random_projection"`, and a test asserts the label matches
   the artefact. It preserves pairwise distance in expectation and preserves **nothing**
   about the corpus's variance structure. `fit_projection.py` is real, runnable code that
   produces the fitted PCA from real embeddings of a declared corpus; run it before any
   recall number is published, and set `MAINLINE_RECALL_REQUIRE_FITTED_PROJECTION=1` so the
   provisional artefact cannot be loaded by accident. The `projection_id` is folded into
   `index_gen`, so a corpus coarsened under one map can never be silently compared with a
   corpus coarsened under the other.

2. **The committed judge cassettes are handwritten, and declare it.** They are evidence
   about *our client* — that a refusal raises before content is touched, that the repair
   path fires exactly once, that the breakpoint sits on the last system block — and about
   nothing else. Every cassette carries a `provenance` field and a test asserts that no
   judge cassette currently claims live provenance. Recording real ones is `GT-RC-01`.

3. **The offline embedder is declared non-semantic.** `SurrogateEmbedder`
   (`model_id = "mainline-surrogate-hash-v1"`) is deterministic feature hashing. It has the
   right width and the right norm and carries no semantics. It is in `NON_SEMANTIC_MODEL_IDS`,
   `is_semantic` is `False`, and `assert_semantic()` raises on it, so a retrieval number
   measured over a surrogate corpus cannot be published by accident. It exists to make the
   shapes, the plumbing and the refusals testable, not to retrieve anything.

4. **The Bedrock wire shapes are designed, not observed.** `output_config.format`,
   `stop_reason: "refusal"`, the Titan `InvokeModel` body and the usage fields follow the
   published contracts and are exercised only through cassettes from this machine. The
   modules say so in their docstrings. Nothing in this package requires a live AWS call to
   be considered done, and nothing in it claims a live AWS call has been made.

Additionally: **`sentence-transformers` is an extra (`[local-embed]`), not a runtime
dependency.** It pulls torch, and the bge weights need a network fetch regardless — a hard
dependency would make the "runs offline" claim false on a fresh checkout. Install the extra
on machines that will actually encode.

---

## Layout

```
providers/
  types.py            Protocols, Vector1024/Vector256, ResolvedModel, Usage, FACETS
  errors.py           every exception, each carrying its silence_ledger reason
  canonical.py        RFC 8785 JCS + the request digest
  base.py             the D3 embedding template and input discipline
  vectors.py          normalisation, Matryoshka truncation, the float32 wire form
  homogeneity.py      assert_homogeneous / assert_semantic
  projection.py       the committed coarse projection, digest-verified on load
  fit_projection.py   CLI: fit the real PCA
  surrogate.py        offline, deterministic, declared non-semantic
  local_bge.py        bge-large, revision pinning mandatory
  bedrock_titan.py    Titan v2 (the one permitted model-id literal)
  resolve.py          runtime au.* inference-profile resolution
  system_blocks.py    the cached system prefix and the quarantined user turn
  schema.py           Pydantic -> strict JSON Schema, output_config
  judge.py            BedrockClaudeJudge: one repair, refusal first, injected transport
  cassette.py         record/replay, self-verifying, provenance-declaring
  record.py           CLI: record cassettes
  registry.py         MAINLINE_RECALL_PROVIDER and the explicit fallback ladder
  data/               committed projection sidecar
```
