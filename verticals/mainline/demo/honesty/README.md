<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The honesty card — generated, traceable, and unable to omit its worst news

`gen_card.py` writes `card.html`: the four-column REAL / SYNTHETIC / STAGED / NOT-BUILT-YET card
that is on screen, full width, for eight seconds of the film.

## Where each value comes from, and which source wins

| Input | Supplies | Owner |
|---|---|---|
| `corpus.lock.json` | counts, severity histogram, **renderer census**, embedding provenance, the staged permit's expected state | `corpus-freeze-load` |
| the G1 attestation | cluster product, edition, version, tier, region, `gc.ttlseconds`, one entry per probed capability | the day-1 probe run |
| `../script/CAMERA-STRINGS.yaml` | exactly one string: the 2013 commit message | the demo script |
| `disclosures.yaml` | the fourth column and the limits — statements, not measurements | this directory |

**Precedence: a measurement outranks a statement about a measurement.** Where the attestation and
`disclosures.yaml` both speak to a fact — today, the residency split and the garbage-collection
window — the attestation wins, `disclosures.yaml` is the standing fallback on the authority of
ADR 0002, and the card's own provenance table names which one supplied each value.

## What the generator refuses to do

- **Render a number it cannot trace.** Every value goes through `fact()`, which raises and names
  the missing path rather than substituting a plausible zero. A blank cell is indistinguishable
  from a true zero, and on this card that difference is the whole product.
- **Render a card whose fourth column omits M14 SHEPARD.** BUILD_PLAN §5.1 puts it there
  explicitly and finding S3 exists because an earlier script filmed it. See ADR 0030.
- **Render a card with no rubber-stamp limit.** Naming the limit you cannot engineer away is the
  cheapest credibility available in three minutes.
- **Emit any run of seven or more hexadecimal characters.** A commit id is a `sha256` over the JCS
  envelope that nobody can choose in advance, so a digest on this card would be a promise the DAG
  has not made. Digests stay in the lock, where a reader can check them at their own pace.
- **Round the residency split off into something shorter.** The database is in Singapore and only
  model inference is in Sydney, so the shorter sentence a marketer would reach for is not true
  here. If an input ever asserted it, the generator stops rather than prints it.
- **Let a fixture reach camera quietly.** The NOT-FOR-CAMERA banner is driven by the `_fixture`
  marker *inside the data*, not by the command-line flag, and a fixture build exits 3.

## Running it

```bash
python gen_card.py                     # real inputs only; exits 2 if one is missing, naming it
python gen_card.py --allow-fixtures    # stand-ins for what is not frozen yet; exits 3
python gen_card.py --check             # fail if the committed card is stale
python gen_card.py --json              # the provenance ledger, for the test suite to walk
```

Exit 3 is the state today, because `corpus.lock.json` is not frozen. It is a **warning** in CI —
which should stay green while the corpus is being built — and a **refusal** in
`just demo:preflight`, which should not.

## The fixtures, and what they are asking for

`fixtures/g1-attestation.fixture.json` is transcribed from ADR 0002, so its numbers are true even
though the probe run was not. It differs from the shipped
`packages/trappoint-sql/g1-attestation.json` in exactly three ways, each of which the card needs
and each of which is therefore a concrete request rather than a paragraph of prose: it carries an
`inference` block, it carries `cluster.gc_ttlseconds`, and it carries a `not_built` list. Until
those land upstream the card reads them from `disclosures.yaml` and says so, in a note printed on
the card itself.
