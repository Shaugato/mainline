<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# EVERY-SCREEN WAVE — work plan

Lead: every-screen lead. Written 2026-08-15 against the live URL
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`,
build `b822fdc`, dist `assets/index-BH5dfAvF.js`.

**Everything below was measured, not read.** Every claim in §1 and §2 is a
transcript of what the deployed artefact served me today. Where I quote a
number, I fetched it.

---

## 0 · What a judge actually sees today — measured, and worse than the brief

The brief describes seven screens and five defects. The navigation the live
console renders has **NINE rows**, and **seven of the nine show a judge nothing
on arrival**. This is the sidebar, top to bottom, as served:

| # | nav row | href | what arrives with no query string |
|---|---|---|---|
| 1 | Gate — the refusal | `#/gate` | demo driver renders; evidence panels say **NO SUBJECT ADDRESSED** |
| 2 | Ancestry — the blame walk | `#/ancestry` | **NOT BUILT YET** card (K3, `ui/ancestry-layout-ribbon`) |
| 3 | Disposition — the signature | `#/disposition` | **NOT BUILT YET** card (K5, `ui/disposition-lattice-modal`) |
| 4 | Custody — the chain | `#/custody` | **HTTP 404** — `site_code 'BLK-07'` |
| 5 | Audit — the MCP surface | `#/audit` | renders; 14 views, **6 carry rows**, 8 empty; carries one FALSE sentence |
| 6 | Propagation | `#/propagation` | **no subject addressed** |
| 7 | Silence | `#/silence` | **no subject addressed** |
| 8 | `diff` | `#/diff` | **HTTP 404** — clause `018f3a30-…` at commit `5f916282…`; nav title is the bare word `diff`, milestone badge `unknown` |
| 9 | `evidence` | `#/evidence` | **Could not read manifest.json — Failed to construct 'URL': Invalid base URL**; nav title bare word `evidence` |

Honesty strip on arrival: `TRANSPORT LIVE (staged)`, `BUNDLE unknown (unset)`,
`SEAL NOT VERIFIED (unset)`, `CORPUS ROOT unknown (unset)`,
`CLOCK SKEW unknown (unset)`, `SIGNATURE PATH unknown (unset)`,
`RENDER walk (3D) (build)`, `BUILD b822fdc (build)`.

Two corrections to the brief's table, both load-bearing:

* **Audit is not "every aggregate: No rows".** Six of fourteen views carry rows
  (`v_blame_coverage`, `v_cbm_ledger`, `v_disposition_coverage`,
  `v_ledger_health`, `v_open_gate_summary`, `v_recall_conservation`). The
  *first* view rendered, `v_agent_actions`, is empty and long, and a reader who
  scrolls it generalises. The real Audit defect is elsewhere — see §2.5.
* **The brief did not know about rows 2, 3, 8 and 9.** `ancestry` and
  `disposition` are promised in `DECLARED_SURFACES` and have no module.
  `diff` and `evidence` are *built and shipping* and are missing from the
  promise list, so the registry renders them as self-registered strangers at
  order 1000/1001 with the bare directory name as their title.

**I also checked whether in-app navigation works.** It does. My first
cross-screen probe appeared to leave the old surface mounted; that was an
artefact of driving the address bar rather than the link. Clicking the real
sidebar anchors switches surfaces correctly. **There is no router defect. Do
not let a worker invent one.**

---

## 1 · The subjects the seed actually carries — proven against the live URL

Every id below returned **HTTP 200** from the live Function URL today. These
are the only subjects that exist. I obtained them from `POST /v1/demo/gate-run`
and `GET /v1/ledger`, never by guessing.

| subject | value | proven by |
|---|---|---|
| site | `dec0de00-0001-4000-8000-000000000001` | `GET /v1/ledger?site_code=…` → 200, 10 751 B |
| permit | `dec0de00-0006-4000-8000-000000000001` | `GET /v1/permits/…` → 200, 5 691 B |
| blocking check | `dec0de00-0007-4000-8000-000000000001` | `GET /v1/checks/…/disposition` → 200, 3 805 B |
| clause | `dec0de00-0004-4000-8000-000000000001` | `GET /v1/clauses/…/ancestry` → 200, 3 744 B |
| head commit | `9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39` | `GET /v1/clauses/…/versions/…` → 200, 3 230 B |
| lesson (event) | `dec0de00-0005-4000-8000-000000000001` | `GET /v1/lessons/…/propagation` → 200, 4 041 B |

And the three ids the console currently addresses, none of which the seed has
ever carried:

* `BLK-07` → `404 no mainline.ledger_checkpoint rows for site_code 'BLK-07'`
* clause `018f3a30-2200-7d10-9f31-0c9a4e77bb02` → `404`
* commit `5f916282a2a3e576…` → `404`

**I drove every broken screen by hand with the real ids and every one of them
came to life.** Gate renders the full weld diagram, six projected counters,
the precursor with its verbatim anchor and the clause edit. Custody renders
four layers and fifteen offline checks. Diff renders the control-delta panels.
Propagation and Silence render with their STAGED banners intact. **The kernel
owes these screens nothing but an address.**

---

## 2 · Rulings — console wrong, or seed owes a row?

The ratified tiebreaker: the console and the committed JSON schemas are
authoritative for what the demo must carry, so a screen the console
legitimately offers usually means the seed owes its subject — *except* where
the console addresses an id nobody ever seeded, which is the console being
wrong. Each ruling below names its authority.

### 2.1 Gate opens on nothing — **BOTH, and the kernel owes the seam**

`GateSurfaceRoot.tsx` refuses to choose a permit, and its docstring defends
that: *"The console does not guess which permit you meant."* That principle is
right and stays. But the console has no way to **ask** which permit exists —
`/v1/audit` is aggregate-first and carries `site_id` and a commit prefix, never
a `permit_id`; I checked all fourteen views.

So the console is not wrong to refuse to guess, and the seed is not wrong to
carry one permit. **What is missing is a route.** I rule that the demo API owes
a read-only subject index, `GET /v1/demo/subjects`, whose body is `SELECT`ed
from the demo tables and never typed as a Python constant, and the console
resolves every screen's default from that one call. *Authority:* the tiebreaker
makes the console authoritative for what the demo must carry; the console
carries seven screens that each need one subject; the kernel is the only
component that can name a subject without inventing it.

**This forbids the obvious shortcut.** A worker who pastes
`dec0de00-0006-…` into a `.tsx` constant has rebuilt `BLK-07` with a luckier
value. It fails the moment the seed changes and it is the same class of defect
as the one we are fixing. **No UUID literal may appear in any console source
file in this wave.**

### 2.2 Custody addresses `BLK-07` — **CONSOLE WRONG**

`CustodyScreen.tsx:48` — `export const DEFAULT_SITE_CODE = 'BLK-07'`. No seed
in this repository has ever written that site code; `demo_world.sql:72` seeds
`site_code` as the literal text of the `site_id` UUID and says so in a comment.
`BLK-07` is a fixture string that leaked out of `tests/vectors/checkpoint.json`
into a shipped default. Delete it. *Authority:* console addressing an id nobody
seeded — the brief's own named exception.

### 2.3 Diff addresses an invented clause and commit — **CONSOLE WRONG**

`ClauseDiffScreen.tsx:55-56`. The docstring calls them *"the address the
capture bundle carries"* — but the capture bundle does not carry them either;
the live kernel 404s on both. Same ruling, same fix. *Authority:* as 2.2.

### 2.4 Evidence — `Invalid base URL` — **CONSOLE WRONG, and it is a one-line bug**

`src/data/bundle.ts:161` does `new URL(path, this.baseUrl)` with
`this.baseUrl = './bundle/'`. A relative string is not a valid `URL` base, so
the constructor throws before any fetch happens. This never fired in REPLAY
because the replay builds carried an absolute bundle URL.

**The bundle is on the wire and I fetched it:**
`GET /bundle/manifest.json` → **HTTP 200, 8 435 B**. The screen is one
resolution away from working. *Authority:* the brief's explicit instruction —
fix the resolution, do not remove the screen.

### 2.5 Audit — **CONSOLE WRONG, and it is stating a falsehood on the live demo**

`AuditScreen.tsx:106` renders, verbatim, on the LIVE transport:

> "The bytes reached it through a bundle whose every file digest and whose
> checkpoint were recomputed in this browser"

**No bundle was consulted.** `VITE_MAINLINE_API_BASE:"/"` is compiled in, the
transport reports `mode: 'live'` and `bundleDigestPrefix: null`, and the
honesty strip two inches above says `BUNDLE unknown`. This is the most serious
copy defect I found: a must-not-claim violation on the screen whose subject is
auditability. It is not a rendering bug and it is not cosmetic.

The eight empty views are **honest and stay**. The console already says the
right thing about them — *"An empty aggregate is a statement about what was
reachable under the caps above, not a statement that nothing exists."* Nobody
may seed fake MCP calls to fill `v_agent_actions`.

### 2.6 The custody seal is RED, and that is the finding of this wave

Addressed with the correct site, Custody does not 404 — it renders
**"verification FAILED. 4 check(s) FAILED in this browser; 6 were not run."**
Red seals on the headline evidence surface are worse than a 404, because a 404
reads as unfinished and a red seal reads as caught.

**The four reds split two and two, and they need opposite fixes.**

**(a) `inclusion_proof` and `consistency_proof_every_pair` — SEED WRONG. One
stale row in the cloud database, and I proved it arithmetically.**

The live payload carries three checkpoints, at `tree_size` 1, 2 and 4. The
`tree_size = 1` checkpoint declares
`root_hash = 74f0845f11c5992bb6e69ba250d899975fc73d551b1eeab96a8502eaca508c8f`.

```
SHA-256("mainline-demo/ledger/root/1")
  = 74f0845f11c5992bb6e69ba250d899975fc73d551b1eeab96a8502eaca508c8f
SHA-256("mainline-demo/ledger/logsig/1")
  = 3a9818c7…  →  base64 OpgYx+c8Cn7anRDjskMK0nMbrmUdgfCbZ0xIJr7zWbs=
  = exactly the log_sig_b64 the live URL serves for that checkpoint
```

That row is **the hash of a string naming itself**, over a tree with nothing
behind it. `demo_world.sql` §8's own preamble documents it as the defect that
was removed on 2026-08-14:

> "Until 2026-08-14 this section seeded ONE checkpoint, `tree_size = 1`, with a
> `root_hash` of `digest('mainline-demo/ledger/root/1', 'sha256')` — a hash of
> a STRING NAMING ITSELF — over a `mainline.ledger_leaf` that held zero rows."

The current seed only inserts at `tree_size` 2 and 4. **The fix landed in the
file and never reached the cloud**, because every insert in §8 is guarded by
`NOT EXISTS` and nothing in the chain ever `DELETE`s a superseded checkpoint.
The stale row is still in `mainline_demo` and it is the single root cause of
both proof failures: the browser correctly reports that seq 0 reconstructs
`032980be…` (the true leaf-0 hash) against a recorded root of `74f0845f…`, and
the `1→2` consistency failure is downstream of the same bogus anchor. `2→4`
passes. *Authority:* the seed's own committed ruling, plus the hash preimage
above.

**(b) `log_signature` and `canonicaliser_identity` — CONSOLE WRONG about the
verdict, not about the arithmetic.**

The seeded note is three lines with no empty line, so it has no C2SP signature
section; `log_sig` is `digest('mainline-demo/ledger/logsig/N')`, a 32-byte
SHA-256 that no one has ever claimed is an ECDSA signature; there is no `canon:`
extension line. §8's preamble declares all three as deliberate placeholders:
*"`log_sig`, `tsa_token` and `beacon` remain synthetic and are marked so."*

The console's own `src/verify/config.ts` already states the correct semantics
in its docstring:

> "`source: 'none'` is a first-class outcome. With no anchor the signature
> check reports SKIP with a named reason and the seal is amber — never green,
> and never red, because a checkpoint nobody could check has not been accused
> of anything."

That contract is not being honoured. The note fails to *parse* before the
anchor question is ever reached, so `checkpoint.ts` reports FAILED. **A check
that was never attemptable is not a check that failed.** Reclassifying it is
not a weakening — it is the console finally saying what its own design says.
The bar is narrow and I set it explicitly in W4's brief: *a note carrying no
signature section at all* skips with a named reason; *a note carrying a
signature that does not verify* stays red, forever.

### 2.7 Ancestry and Disposition — **CONSOLE WRONG about ORDER, right about the card**

Deleting them from `DECLARED_SURFACES` is the tempting fix and it is the
dishonest one. `surfaces.ts` says so itself: the promise list exists so that a
cut surface renders *"a NOT-BUILT-YET card naming the milestone that owes it,
rather than vanishing from the navigation as though it had never been
promised."* The cards stay. What changes is that two dead ends currently sit at
positions 2 and 3, above every working screen. Reorder, and mark them in the
nav list. *Authority:* `surfaces.ts`'s own contract.

### 2.8 `diff` and `evidence` untitled at the bottom — **CONSOLE WRONG**

Both ship real `surface.tsx` modules with real titles
(*"Diff — what 'weakened' meant"*, order 15; *"Evidence — the bundle"*,
order 45) and neither appears in `DECLARED_SURFACES`, so `buildRegistry` files
them as undeclared strangers at order 1000/1001 with `title: id` and
`milestone: 'unknown'`. The promise list is simply stale. Add them.

### 2.9 The honesty strip — three chips have no LIVE meaning, two already work

Measured after addressing Gate with the real permit, the strip becomes:
`CORPUS ROOT 49b22526…023f4932c8dbd8cd2df1bc22e612cf8ddf40768d84b9e07d09498983
(db:column)` and `CLOCK SKEW −1 ms (recomputed)`.

**Two of the five "unset" chips are not defects at all — they are the Gate
defect wearing a different hat, and W2 fixes them for free.** Nobody may write
new code for those two.

The other three need words, not values:

* **BUNDLE** — in LIVE no bundle byte is on screen. `unknown` implies a value
  we failed to obtain. The truth is that none was consulted. Say that.
* **SEAL** — `NOT VERIFIED` reads as a failure and is not one; the bundle
  verifier does not run in LIVE. Say that, and point at Custody, which does run
  real arithmetic on live bytes and reports its own verdict.
* **SIGNATURE PATH** — `env.d.ts` and `ui.md` D17 make this a build-time
  selection from the GT-15 attestation. `vite.config.ts:50-52` looks for the
  attestation at `evidence/attestations/g1-attestation.json`; the only
  attestation in the repo is `packages/trappoint-sql/g1-attestation.json` and
  it declares **GT-13 and GT-05 only — there is no GT-15 capability in it**.
  Further, the Disposition surface is NOT BUILT, so this artefact compiles
  *neither* capture path. Printing `webauthn` or `oidc_envelope` would be a
  fabrication; printing `unknown` is unhelpful. The truthful chip is a sentence
  naming the fact: no signing surface ships in this build.

*Authority for all three:* the brief's instruction that a chip with no meaning
in LIVE must say **that**, in words, instead of `unknown`.

### 2.10 The on-ramp — the founder's second request

Read the current copy before judging it: it is precise and every sentence is
defensible. Custody opens on *"RFC 8785 canonicalisation, RFC 6962 leaf, node,
inclusion and consistency hashing, and the ECDSA P-256 signature over the
checkpoint note"* — correct, and unreadable to a first-time reader who has not
yet been told what the product refuses.

**The fix is an on-ramp, never a dumbing-down.** Not one existing sentence may
become vaguer. What changes is what a reader meets FIRST. I rule that the
on-ramp is **chrome, not feature copy**: it is mounted by `SurfaceHost` from a
copy deck keyed by surface id, so no feature file is edited and no precise
sentence is touched. Plus one new screen — the founder's *"present a couple of
exceptional use cases that we are solving"* — as an Overview surface that opens
the console, tells the story in plain language, and deep-links into Gate,
Custody and Diff **with the real subjects**.

---

## 3 · How a fix is proved in this wave

The last defect of this exact kind shipped because every test read source and
none read what was served. So:

1. **Nobody deploys.** No `terraform apply`, no Lambda update, no AWS call, no
   SSM write. Build and verify locally; the orchestrator deploys.
2. **Every subject a fix addresses must be proved against the LIVE URL by
   direct `curl` today**, recorded as method, path, status and byte count.
   Every id in §1 already has such a proof; a worker adding another must
   produce it the same way.
3. **Every rendering fix must be proved against a SERVED artefact** — build
   `dist/`, serve it through the same `static_site` handler against a locally
   seeded `mainline_demo`, and read the bytes back out of the response. Reading
   `src/` proves nothing.
4. **W1's new route cannot return 200 on the live URL until the orchestrator
   deploys.** That is expected and it is the only step this wave hands off.
   W1 discharges its obligation in two parts: (P1) every id the route will
   return is proved 200 against the *existing* live routes today; (P2) the new
   route is proved end-to-end against the locally served deployable artefact.
5. **No commits.** Leave the tree for the orchestrator.

### The prohibitions, restated because they are the ones that get broken

* **Never invent a row, fake a seal, or hard-code a green tick.** A worker was
  reverted for reshaping `demo_world.sql` to match a code constant. If a screen
  has no data, the honest fixes are exactly two: seed the subject the console
  addresses, or address the subject the seed carries.
* **Never weaken a claim to make a screen render.** If a rewrite makes a claim
  vaguer, it is wrong.
* **Never lower a floor, raise a ceiling, or add a known-red exemption.**
  `DEFAULT_MAX_RESPONSE_BYTES` stays `136 * 1024`.
* `continue-on-error` and `|| true` are banned. Do not weaken `HONESTY.md` or
  `CI-STATE.md`.

---

## 4 · The seven workers

Paths are literal and disjoint. A worker touching a path it does not own is a
defect regardless of the outcome.

| id | title | owns |
|---|---|---|
| **W1** | The demo subject index (kernel) | demo-api: `subjects.py` (new), `app.py`, `reads.py`, `contracts/subjects.schema.json` (new), its tests |
| **W2** | Console addressing — five screens, no invented ids | `src/data/demo-subjects.ts` (new), `src/data/resources.ts`, the five surface roots |
| **W3** | The Evidence screen and the bundle base URL | `src/data/bundle.ts`, `src/features/evidence/**` |
| **W4** | The custody seal: two seed reds, two console reds | `demo_world.sql` §8, the chain cleanup, `src/verify/{checkpoint,ledger,config}.ts`, `src/features/custody/**` except `CustodyRoot.tsx` |
| **W5** | The honesty strip, and the Audit screen's false sentence | `src/app/{honesty.ts,HonestyChrome.tsx,HonestyProvider.tsx}`, `src/data/transport.ts`, `src/features/audit/**` |
| **W6** | Navigation truth | `src/app/{surfaces.ts,App.tsx,NotBuiltYet.tsx}` |
| **W7** | The on-ramp and the two use cases | `src/app/SurfaceHost.tsx`, `src/copy/**` (new), `src/features/overview/**` (new) |

### Declared seams between workers

* **W2 ↔ W4 on Custody.** W2 owns `CustodyRoot.tsx` only. W4 owns everything
  else under `src/features/custody/` and is *required* to delete
  `DEFAULT_SITE_CODE` from `CustodyScreen.tsx`, making `siteCode: string` a
  required prop. W2 passes the resolved value through. Typed seam, no overlap.
* **W6 ↔ W7 on the Overview surface.** W7 writes `src/features/overview/**`;
  W6 adds its entry to `DECLARED_SURFACES`. The registry glob self-registers
  W7's surface even if W6 lands later — it would merely sort last in the
  interim. Neither blocks the other.
* **W1 ↔ W2 on the contract.** W2 codes against
  `contracts/subjects.schema.json`. If W1 has not landed, W2's resolver must
  degrade to the truthful panel described in its brief, never to a literal.
* **W5 may not touch `App.tsx`.** The `signaturePath` value is already
  `'unknown'`; W5 changes only how the chip *renders* that fact.

## 5 · Done, for the wave

A judge loads the bare URL, clicks every sidebar row top to bottom, and:

* every row that promises data shows data, from the live kernel;
* the two rows that promise a screen nobody built still say so, and sit below
  the working screens rather than above them;
* the Custody seal is green where the arithmetic holds, and names — in words,
  amber — the two checks that this synthetic log makes unattemptable;
* no chip in the honesty strip says `unknown` unless `unknown` is the true and
  complete answer;
* the Audit screen no longer claims a bundle it never read;
* the first thing a non-specialist reads is what the product refuses and why,
  and every precise sentence is still one click away, unchanged.
