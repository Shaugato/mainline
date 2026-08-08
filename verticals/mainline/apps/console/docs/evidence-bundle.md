<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The console EvidenceBundle

**The prose contract for the console's replay transport.** The machine-checkable half is
[`contracts/bundle.schema.json`](../contracts/bundle.schema.json); the player is
[`src/data/bundle.ts`](../src/data/bundle.ts); the producer is
[`scripts/capture-bundle.ts`](../scripts/capture-bundle.ts). Where this document and the schema
disagree, **the schema wins** and this document is the defect.

The key words MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT and MAY are to be interpreted as in
BCP 14 (RFC 2119, RFC 8174).

Version `1.0` — `manifest_version: 1`, `frame_version: 1`.

---

## 0. Two different artefacts are called "evidence bundle". Do not confuse them.

| | **custody bundle** | **console EvidenceBundle** (this document) |
|---|---|---|
| Defined in | [`spec/wire/evidence-bundle.md`](../../../../../spec/wire/evidence-bundle.md) | here |
| Shape | ONE self-describing JSON file, emailable | a content-addressed **directory** |
| Contains | checkpoints, leaves, inclusion/consistency proofs, cosignatures, receipts | captured HTTP request/response pairs, plus a custody bundle, plus verbatim SQL |
| Consumed by | `uvx trappoint-verify verify --bundle bundle.json`, by a stranger, offline | the console's `BundleTransport`, in a browser |
| Owner | custody domain | UI domain (`data-contracts-replay`) |
| Claim it supports | "this ledger is internally consistent and signed" | "this screen was produced from these bytes and nothing else" |

The console bundle **carries** a custody bundle, verbatim, at `ledger/bundle.json`. It does not
reimplement it, does not summarise it, and does not verify it — `trappoint-verify` and the
in-browser verifier do that. A console bundle is a transport artefact. A custody bundle is
evidence. Keeping the two words apart matters, because only one of them is something a stranger
can check without us.

---

## 1. Why this exists

Two constraints meet in one artefact.

`BUILD_PLAN` §3/K5 states the problem the console has: *nobody can authenticate a React
component*. `docs/leads/ui.md` D6 removes the premise — the console re-derives in-browser what it
displays — but re-derivation needs bytes with a provenance, and a `fetch` against a live kernel
gives the viewer no way to know what came back.

Separately, AWS credentials are not valid on the founder's machine and G6 requires a functional,
free demo URL. A bundle is a demo that needs no cloud account.

So: **replay is the default transport and live is a transport swap** (D7). `LIVE` and `REPLAY`
differ in one line of composition and in one permanently-rendered badge (D16), never in a code
path — `HttpTransport` and `BundleTransport` implement the same `MainlineTransport` interface and
share `finishExchange()`, which holds every post-condition both must satisfy.

What makes this not a mock is one mechanism, stated as a mechanism rather than a promise:

> **`BundleTransport` cannot serve a single frame before manifest verification has RESOLVED, and
> it has no verifier of its own.** There is no default verifier and no skip-verification option,
> because a default that passes is a lie with a configuration flag in front of it. A tampered
> fixture renders a failure state, never a screen.

---

## 2. Layout

```
<bundle>/
├── manifest.json              REQUIRED — the only file whose digest is not inside itself
├── manifest.seed.json         producer input; NOT part of the bundle, NOT listed, never served
├── frames/                    REQUIRED — one file per captured exchange
│   ├── GET~20~2Fv1~2Fpermits~2F018f3a2f-….json
│   └── POST~20~2Fv1~2Fpermits~2F018f3a2f-…~2Fmerge.json
├── ledger/                    OPTIONAL
│   ├── bundle.json            a spec/wire/evidence-bundle.md v1.0 artefact, verbatim
│   └── checkpoint-000005.note a C2SP signed note, verbatim
└── sql/                       OPTIONAL
    └── merge-refused-23514.txt   one verbatim round trip per file
```

Rules that hold for the whole directory:

1. Paths in `manifest.files` are bundle-relative, forward-slashed, and MUST NOT contain `..` or a
   leading `/`. Windows separators MUST NOT appear; `capture-bundle.ts` normalises them.
2. `manifest.json` MUST NOT list itself. A file cannot carry its own digest, and a manifest that
   claims to is asserting something no reader can check. `BundleTransport` refuses such a manifest
   by name.
3. A file present on disk but absent from `manifest.files` is **outside the verified set** and is
   never served — not as a fallback, not with a warning. Smuggling a file into the directory
   therefore achieves nothing.
4. `.license` sidecars, `REUSE.toml` and `.gitattributes` are REUSE/VCS metadata, not evidence.
   The producer excludes them; they are neither listed nor served.

---

## 3. `manifest.json`

Normative shape: [`bundle.schema.json`](../contracts/bundle.schema.json) (root object).
`BundleTransport` validates the manifest against that schema **before** handing it to the
verifier, so a malformed manifest fails as `contract`, not as a digest mismatch.

| member | required | meaning |
|---|---|---|
| `manifest_version` | yes | MUST be `1`. A player that does not recognise the version refuses to serve rather than guessing which fields still mean what they used to. |
| `bundle_id` | yes | Stable identity, `^[a-z0-9][a-z0-9._-]*$`. Two bundles with the same id and different digests are a contradiction the player reports rather than resolves. |
| `captured_at` | yes | RFC 3339 UTC. |
| `generator` | no | Provenance, not evidence. **No check reads it.** |
| `cluster_fingerprint` | yes | §3.1. |
| `schema_version` | yes | The database schema digest, or a named migration head. A bundle that cannot say which schema produced it cannot be replayed against a claim about that schema. |
| `staged` | yes | §3.2. |
| `staged_note` | iff staged | Non-null string exactly when `staged` is `true`; `null` otherwise. Enforced by an `if/then/else` in the schema. |
| `checkpoint` | yes | §3.3, or explicit `null`. |
| `files` | yes | ≥ 1 entry: `{path, sha256, bytes, media_type?}`. |

`files[].bytes` is a byte length, and it exists so that a truncated transfer produces
`manifest declares N bytes, received M` rather than a digest mismatch that reads like an attack.
It is the **only** integrity assertion `src/data/bundle.ts` makes itself — a length comparison,
not a hash.

### 3.1 `cluster_fingerprint`

```jsonc
{
  "source": "observed" | "declared",   // load-bearing
  "product": "CockroachDB CCL",
  "version": "v26.2.5",
  "cluster_version": "26.2",
  "tier": "basic",
  "region": "aws-ap-southeast-1",
  "evidence_ref": "where the measurement behind a `declared` fingerprint is recorded"
}
```

`source` is the load-bearing member. `observed` means these values were read from a live cluster
*during this capture*. `declared` means a human wrote them from a recorded measurement — a
strictly weaker claim, and the console displays it as one. A `declared` fingerprint SHOULD carry
`evidence_ref` naming where the measurement lives.

`region` MUST be stated precisely. In this deployment residency is **split** — Bedrock inference
in `ap-southeast-2` (Sydney), the database in `aws-ap-southeast-1` (Singapore). Any end-to-end
Australian data-residency claim is therefore **false** and MUST NOT appear in a bundle or on any
screen fed by one. A unit test greps every fixture payload for that claim and fails on it.

### 3.2 `staged`

`staged: true` means **at least one frame in this bundle was hand-authored rather than captured
from a running system.** It is not a debug flag and it is not advisory:

- `capture-bundle.ts stage` REFUSES to build a bundle whose plan does not declare `staged: true`.
  Hand-authored material that does not announce itself is the one thing this console must never
  render.
- `seal` REFUSES a seed with `staged: true` and no `staged_note`. An unexplained flag is a flag
  nobody has to justify.
- `TransportDescription.staged` propagates it, and the honesty chrome renders it permanently and
  non-dismissibly (D16). Before a bundle has been opened, `describe()` reports `staged: true` with
  the note *"The bundle has not been opened, so nothing about it is established yet."* — the
  pessimistic default is deliberate.
- Every envelope inside a staged bundle ALSO carries `staged` + `staged_note`, and a unit test
  requires each note to be longer than 40 characters. The chrome reads the per-payload flag rather
  than trusting the manifest, so a bundle cannot launder a payload by claiming to be live.

The committed fixture bundle is staged, and its note says exactly what is real about it: the
SQLSTATEs, constraint names and column names are taken from `ARCHITECTURE.md` §5 and
`spec/wire/refusal.md` and are real claims about the design; **the values are not observations,
and no number on such a screen may be quoted as a measurement.**

### 3.3 `checkpoint`

```jsonc
{
  "site_code": "BLK-07",
  "tree_size": 5,
  "root_hex": "<64 lowercase hex>",
  "note_path": "ledger/checkpoint-000005.note",   // MUST also appear in files[]
  "custody_bundle_path": "ledger/bundle.json"     // optional
}
```

`null` is a legitimate value and means the bundle carries no custody anchor at all. The console
renders that as an **absence**, not as an unverified state — "there is no checkpoint here" and
"there is a checkpoint I could not check" are different sentences and only one of them is true.

---

## 4. `frames/` — one captured exchange per file

### 4.1 The canonical request key

Everything about addressing follows from one derivation, in
[`src/data/resources.ts`](../src/data/resources.ts):

```
key = "<METHOD> <interpolated path>"                       when there is no query
key = "<METHOD> <interpolated path>?<sorted query>"        otherwise
```

The query pairs are sorted by name then value and percent-encoded. The key is computed from the
resource declaration alone — never from a transport detail — which is what makes a frame captured
against a live kernel addressable by a player that has never seen one.

Path parameters are checked against `^[A-Za-z0-9._~-]{1,128}$` before interpolation. This is not
sanitisation theatre: admitting a `/` would let a caller reshape the request into a different
resource, which in replay would silently address a different frame.

### 4.2 Key → file name

`framePathForKey()` maps the key to `frames/<encoded>.json`. Unreserved characters
(`A–Z a–z 0–9 . _ -`) pass through; every other byte becomes `~XX` with its uppercase hex. `~` is
itself escaped, so the mapping stays **injective** — two different requests can never name the
same frame.

```
key   GET /v1/ledger?site_code=BLK-07
file  frames/GET~20~2Fv1~2Fledger~3Fsite_code~3DBLK-07.json
```

A bundle therefore needs **no index**. An index would be a second place for the truth to live.

### 4.3 Frame format

Normative shape: `bundle.schema.json#/$defs/frame`.

```jsonc
{
  "frame_version": 1,
  "key": "GET /v1/permits/018f3a2f-1104-7c88-b3aa-77c1de40e2b1",
  "request": {
    "method": "GET",
    "path": "/v1/permits/018f3a2f-1104-7c88-b3aa-77c1de40e2b1",
    "query": [ { "name": "as_of", "value": "5f91…" } ],   // ordered pairs, not an object
    "body_b64": null                                       // non-null only for POST
  },
  "response": {
    "status": 200,
    "headers": [ { "name": "content-type", "value": "application/json" } ],
    "body_b64": "<the response body, byte for byte>"
  },
  "captured_at": "2026-08-07T02:15:00.000Z",
  "duration_ms": 12
}
```

Four choices worth defending:

**Bodies are base64.** A frame that stored a re-serialised JSON object would be testing our JSON
writer rather than the server's output, and a whitespace difference would silently change every
digest computed over it. `stage` copies payload bytes into the frame; it never parses and
re-emits them.

**`query` is a list of `{name, value}`, not an object.** The canonical key sorts them itself, and
an object here would put an index signature into the generated read model. `gen-types.ts` confines
index signatures to exactly three named aliases (`JsonValue`, `JsonObject`, `StringMap<T>`) and a
test counts them, so an open-ended map cannot be introduced by writing a schema.

**`headers` is an allowlist** (`content-type`, `date`), enforced by the capture script. A capture
that stored every header would carry credentials, and an evidence bundle is a thing we hand to
strangers.

**`key` is inside the file as well as in its name.** The player compares them. A frame filed under
the wrong name is exactly how a swapped fixture presents, so it is a hard failure (`mismatch`).

### 4.4 Replay answers the exchange that was captured

For a `POST`, the player compares the caller's body against `request.body_b64` and refuses on any
difference. There is no loose-matching option.

The reason is specific: serving a captured response to a *different* request body would let the
console appear to transact — a signature over different text, a merge of a different subject — and
then report the old outcome. That is precisely the fabricated screen this whole design exists to
make impossible.

---

## 5. `ledger/` and `sql/`

`ledger/` carries custody artefacts **verbatim**: a `spec/wire/evidence-bundle.md` v1.0 bundle and
the C2SP signed checkpoint notes it references. The console does not interpret these; it hands the
bytes to the in-browser verifier and to whoever downloads them. Because they are listed in
`manifest.files`, they are covered by the same digest check as everything else.

`sql/` carries verbatim round trips, one per file, in a fixed layout:

```
$ cockroach sql --url <redacted> --format csv --set errexit=true -e <statement below>
--- statement ---
CALL trappoint.merge_permit('018f3a2f-…'::UUID, 7::INT8);
--- exit code ---
1
--- stdout ---

--- stderr ---
ERROR: failed to satisfy CHECK constraint (state != 'merged' OR open_blocking = 0)
SQLSTATE: 23514
CONSTRAINT: gate_closed_when_issued
DETAIL: …
HINT: MAINLINE: …
```

The URL is redacted because it carries a password. Nothing else is. The SQLSTATE and the
constraint name appear because they are the product: the deliverable is a refusal, and a refusal
whose constraint name is paraphrased is a different refusal (D18).

`sql/` also exists for a structural reason recorded in `docs/leads/ui.md` §4: the ancestry read
endpoint `GET /v1/clauses/{uuid}/ancestry` has **no owner in any domain**. `capture` sources that
payload directly from SQL and writes a frame for it, and the console never learns the difference —
`RESOURCES` records the gap as `owner: null` where a reader will see it.

---

## 6. The verification hook

`BundleTransport` takes a REQUIRED `verifier`. There is no default and no null case.

```ts
interface BundleVerifier {
  readonly name: string;
  verify(input: {
    manifestBytes: Uint8Array;
    manifest: BundleManifest;
    read: (path: string) => Promise<Uint8Array>;   // through the transport's cache
    signal?: AbortSignal;
  }): Promise<{
    verdict: 'verified' | 'failed';
    manifestDigest: string;      // lowercase hex, computed by the verifier
    filesChecked: number;
    summary: string;             // rendered verbatim
    findings: { subject: string; check: string; detail: string }[];
  }>;
}
```

**There are deliberately two verdicts and no third.** "Unverified" is not a value this hook may
return: a verifier that cannot check something reports it as a finding with a named SKIP reason
and decides, itself, whether the bundle is still servable. The transport must never be in a
position to interpret an ambiguous verdict optimistically.

**`read` goes through the transport's cache, not the source.** That is what makes *the bytes I
checked are the bytes you serve* true rather than hopeful: a hostile source cannot return
different content on a second read after the check has passed. The cache is populated on first
read and never invalidated.

**`src/data/**` computes no digest and verifies no signature.** The three things `bundle.ts` does
that a verifier cannot do for it are: hold the byte cache (above); compare declared against
received byte lengths; and refuse a path that `manifest.files` does not list. Everything
cryptographic belongs to the in-browser verifier — vendored RFC 8785 JCS, WebCrypto SHA-256,
RFC 6962 leaf/node/inclusion/consistency, C2SP note parse and ECDSA-P256 — owned by the
`verifier-custody-room` worker and cross-vectored against `packages/trappoint-verify`.

Ordering inside `open()`, which is load-bearing:

1. read `manifest.json` through the cache;
2. decode UTF-8 (fatal), parse JSON;
3. validate against `bundle.schema.json`;
4. index `files` by path — refusing a duplicate path, and refusing a self-listing manifest;
5. **call the verifier and await it**;
6. if the verdict is not `verified`, throw — the failure is remembered, not retried, because a
   bundle that failed verification does not become verified by asking again.

`exchange()` awaits `open()` before it touches a frame. Concurrent callers share one promise.

**`describe().bundleDigestPrefix` is `null` until the verifier has reported one.** The chrome shows
"unknown" rather than a digest nobody has computed. The manifest digest is what is displayed
because the manifest is the only file whose digest is not listed inside itself.

---

## 7. What the player refuses, and what each refusal means

Every refusal is a `TransportError` carrying `failure`, `requestKey` and a verbatim `detail`.

| `failure` | Raised when |
|---|---|
| `tampered` | The injected verifier returned `failed` (detail = its verbatim summary and findings), **or** a file's byte length disagrees with `manifest.files[].bytes`. |
| `missing_frame` | The manifest does not list the frame for this request, or the source cannot produce a listed file. The message says the bundle *captured a different set of exchanges* — it is not incomplete for this one. |
| `malformed` | A bundle file is not valid UTF-8, is not JSON, or a `body_b64` is not base64. |
| `contract` | The manifest, a frame, or a response envelope fails its JSON Schema. Carries the pointer-level validation errors. |
| `mismatch` | A frame's internal `key` disagrees with its file name; a replayed POST body differs from the captured one; or an envelope declares a `resource`/`schema_id` other than the one requested. |
| `aborted` | The caller's `AbortSignal` was already aborted, or fired. Replay honours cancellation exactly as live does. |
| `network` | `HttpTransport` only: `fetch` rejected. |
| `status` | `HttpTransport` only: a non-2xx response whose body carries no envelope. A refusal, by contrast, arrives *with* an envelope and is a normal response. |
| `unverified` | Declared in the union and **produced by no code path in `src/data/**` today.** It is reserved for the injected verifier surface, which is another worker's; it is named here so nobody adds a second spelling for the same idea. |

Two behaviours that are easy to get wrong and are pinned by tests:

- A tampered manifest makes **every** frame unservable, including frames whose own bytes are
  untouched. The manifest is the thing that says this is the bundle it claims to be.
- A smuggled file (present on disk, absent from the manifest) does **not** invalidate the bundle —
  everything the manifest lists still verifies — but it can never be addressed. Both halves of
  that are asserted, so neither can silently flip.

There is **no retry helper, of any kind**, in either transport, and there will not be one. A
blanket retry is banned repo-wide; here the reason is specific. The kernel's POST endpoints are
state transitions, SQLSTATE `40001` is an UNDECIDED transaction rather than a failure, and a helper
that re-sends a merge because a socket closed is a helper that can issue a permit twice. A `retry`
outcome is surfaced to the caller. `useResource().reload` exists so that a human pressing a button
is the only retry this console has — a decision with an author.

---

## 8. Producing a bundle

```console
$ node scripts/capture-bundle.ts stage   --sources fixtures/sources/blk-07 --out fixtures/bundles/blk-07
$ node scripts/capture-bundle.ts seal    --dir fixtures/bundles/blk-07
$ node scripts/capture-bundle.ts check   --dir fixtures/bundles/blk-07
$ node scripts/capture-bundle.ts capture --plan capture-plan.json --out out/blk-07
```

**`stage`** assembles a bundle from hand-authored, human-readable sources
(`fixtures/sources/<id>/plan.json` + `payloads/*.json` + directories named in `plan.copy`). It is
deliberately not a shortcut around capture: payload **bytes** are copied into the frame rather than
re-serialised, so what a reviewer reads in `fixtures/sources/**` is exactly what the console
receives, to the byte, digest included. It refuses a plan that does not declare `staged: true`.

**`seal`** is offline and complete: it walks the directory, records every content file's length and
SHA-256, merges `manifest.seed.json` over the result, and writes `manifest.json`. This is the mode
CI exercises. Sealing is where SHA-256 is computed — that is **production**, not verification, and
it happens in `scripts/`, never in `src/data/**`.

**`check`** re-derives every digest and reports disagreement in both directions (on disk but
unlisted; listed but missing; wrong length; wrong digest). It is a producer-side self-check, not
the console's verifier.

**`capture`** performs a real run. Each plan step is either an HTTP exchange against a live read
API or a `cockroach sql` invocation, and both are recorded byte-for-byte, including the SQLSTATE
and constraint name the driver reported on a refusal. A step declares `expect_error`, and a run
whose outcome disagrees with the plan **fails the capture** — a capture that records the wrong
outcome is worse than no capture.

### 8.1 Determinism

`seal` sorts `files` by path and writes two-space-indented JSON with a trailing newline, so two
seals of the same directory are byte-identical and a `git diff` after a re-seal shows the digests
that moved and nothing else.

Two parts of that are checked rather than assumed, and one is not:

- **Asserted in CI.** For every step in the staging plan, the frame's decoded
  `response.body_b64` equals the source payload file *character for character* — compared as
  strings, not as JSON, because JSON equality would pass through a re-serialisation and that is
  the exact defect the test exists to catch (`fixtures.test.ts`, one case per step).
- **Asserted in CI.** `capture-bundle check --dir` re-derives all 21 digests, and the transport's
  own tamper test hashes the sealed bytes with WebCrypto and compares them to `manifest.files`.
- **Verified by hand, not in CI.** Re-running `stage` over `fixtures/sources/blk-07` into a scratch
  directory reproduces `fixtures/bundles/blk-07` byte for byte, `manifest.json` included. That was
  run during authoring; it is not yet a CI step, because it needs a scratch directory and a
  recursive diff and belongs in the repo-level `just` target rather than in `vitest`.

The reason to care is narrower than "reproducible builds are nice". Evidence Act 1995 (Cth)
ss. 146–147 turn on a process that *ordinarily* produces a particular outcome. A generator whose
output varies run to run has no "ordinarily" to appeal to.

### 8.2 What is NOT part of the bundle

`manifest.seed.json` is the input to sealing — the claims a human makes about identity, capture
time, cluster and staging — not captured evidence. It is excluded from `files`, and because
unlisted files are never served, it is unreachable through the transport.

---

## 9. Honesty rules for anyone producing a bundle

1. A staged bundle MUST say so, in the manifest and in every envelope it carries.
2. `cluster_fingerprint.source` MUST be `declared` unless the values were read from a live cluster
   during this capture.
3. No bundle may claim end-to-end Australian data residency. Inference is in `ap-southeast-2`; the
   database is in `aws-ap-southeast-1`.
4. The custody vocabulary banned by `spec/wire/evidence-bundle.md` §14 — "defence exhibit",
   "for litigation", "court-ready" — MUST NOT appear. A ledger built to be evidence is not a
   business record, and saying so out loud costs the record its ordinariness.
5. A staged custody bundle MUST NOT pretend to verify. The committed one carries real *shape* and
   fake arithmetic, and says: running `trappoint-verify` against it MUST fail, and that failure is
   the correct outcome.
6. No person's name goes into a bundle that the MEMORY register will render (D15).

---

## 10. The committed fixture bundle

`fixtures/sources/blk-07` → `fixtures/bundles/blk-07`, `bundle_id: blk-07-staged-2026-08-07`,
21 content files. It exists so the six situations the demo must be able to show can each be
rendered, and `tests/unit/data/fixtures.test.ts` names all six and fails if one goes missing:

| # | situation | evidence in the bundle |
|---|---|---|
| 1 | a refused merge | `23514` on `gate_closed_when_issued`, plus the verbatim SQL round trip |
| 2 | a refused disposition | `23503` on `fk_clearance`, whose MUS names the **missing lattice row** — "not permitted" and "not representable" are different sentences |
| 3 | a precursor arriving after issue | `P0001` from `trappoint.*`, whose NAA is `fork_subject` — suspend and fork, never rewrite |
| 4 | blame across a working life | a 22-year ancestry ending at a severity-5 event, `ancestry_complete: true` |
| 5 | what recall did not say | a silence ledger whose per-channel contributions sum to the fused score it publishes |
| 6 | custody | a checkpoint with an inclusion proof against a tree size it declares, leaves dense from `seq = 0`, genesis link = 64 zeroes |

The bundle also declines to overclaim on its own behalf: the checkpoint note names a `.invalid/`
origin that cannot be mistaken for a real log, and the projected `admissible` column is `false`,
because one operator cosignature satisfies neither quorum nor diversity.

---

## 11. Conformance

This document is held by `tests/unit/data/` — 111 tests across 8 files, run by `pnpm test`:

| file | what it pins |
|---|---|
| `bundle-transport.test.ts` | one flipped hex digit in one declared digest ⇒ **no frame is servable**; the intact bundle serves one, so the refusal is not vacuous; the gate is the injected verifier's verdict, not an internal opinion; a self-listing manifest is refused; a POST with a different body is refused; an uncaptured request is `missing_frame`, never an empty result |
| `transport-parity.test.ts` | the same assertions run against `HttpTransport` and `BundleTransport` — the D7 claim that live and replay differ in one line of composition |
| `fixtures.test.ts` | every fixture payload validates against its contract; every one declares itself staged with a note; **every sealed frame decodes to its source payload character for character**; the six situations above; the overclaim greps |
| `contracts.test.ts` | every contract compiles with no unimplemented keyword and no dangling `$ref`; `contracts/refusal.schema.json` is structurally identical to `spec/wire/refusal.schema.json`, compared JSON-pointer by JSON-pointer in both directions |
| `schema-validator.test.ts` | the validator itself — including that an unimplemented keyword raises rather than passing vacuously |
| `types.test.ts` | `types.generated.ts` contains no `any`; its index signatures are confined to three named aliases; the generated shapes and the hand-written structural types in `transport.ts`/`bundle.ts` agree, asserted at compile time |
| `resources.test.ts` | key derivation, the injective frame-name encoding, path-parameter refusal, and that every derived frame name satisfies the path pattern in `bundle.schema.json` |
| `use-resource.test.tsx` | no state carries stale data alongside a failure; an abort is supersession, not failure; a refusal is its own terminal state, carrying the constraint name |

Producer-side, `node scripts/capture-bundle.ts check --dir <bundle>` re-derives every digest and
exits non-zero on any disagreement.

---

## 12. Limits — what is not established

Stated plainly, because a document about authenticity that overstates itself is self-refuting.

- **`capture` has never been run against a live kernel or a live cluster.** No AWS credential and
  no CockroachDB Cloud connection were available on the machine this was written on. The code is
  complete and its failure paths are real, but "capture works" should be treated as untested until
  an `evidence/demo-run-<ts>/` directory produced by it exists. `stage`, `seal` and `check` are
  exercised in CI and are the modes the committed fixtures depend on.
- **The verifier that gates the transport is injected and is another worker's.** The tests here
  use a real WebCrypto SHA-256 manifest-integrity verifier written in the test tree — real hashing,
  so the tamper test proves something — but it checks manifest integrity only. It says nothing
  about whether the carried ledger verifies; that is a claim about contents, it belongs to the
  custody surface, and for a staged fixture it is expected to fail.
- **A verified bundle establishes provenance, not truth.** It says: these bytes are the bytes that
  were sealed, and this screen was produced from them and nothing else. Whether the numbers inside
  describe a real cluster is what `staged` and `cluster_fingerprint.source` are for, and on the
  committed fixture both say no.
