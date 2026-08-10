<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Licensing

**Measured 2026-08-10 against the working tree at `D:/CoackroachDBxAWS/mainline`.** Every
number on this page is followed by the command that produced it. Run the commands. If a
number here disagrees with what your terminal says, the terminal is right and this page is
stale — re-run §6 and correct it.

The census counts **tracked** files, so it is a snapshot of one commit, not a constant. It
moves every time a file lands: the `docs/` row below reads `26` because this document was
itself untracked when the census ran, and it becomes `27` the moment this document is
committed. The commands are the durable part; the integers are the reading they gave on
2026-08-10.

---

## 1 · The short answer

| you want to | licence | can you fork it |
|---|---|---|
| reuse the **substrate** — `packages/`, `spec/`, `skills/` | **Apache-2.0** | **yes, unconditionally** |
| reuse the **product** — `verticals/`, `infra/` | **FSL-1.1-ALv2** (source-available; becomes Apache-2.0 two years after each release) | read, audit, modify, self-host; no competing commercial offering until the grant matures |
| quote the **documents and the evidence** — `docs/`, `qa/`, `evidence/` | **CC-BY-4.0** | yes, with attribution |

**The substrate under `packages/` and `spec/` is Apache-2.0 and it is genuinely forkable.**
That is not a marketing sentence, it is an architectural invariant with a guard: `.importlinter`
contract 1 forbids any `trappoint_*` distribution from importing any `mainline_*` module, so
the Apache-2.0 layer does not secretly depend on the source-available layer. A stranger can
lift `packages/` — the migration runner, the JCS canonicaliser, the recall engine, the
conformance harness — and owe this project nothing but the Apache notice.

```
$ git grep -h -o -E "SPDX-License-Identifier: [A-Za-z0-9.+-]+" -- packages | sed 's/.*: //' | sort | uniq -c | sort -rn
    593 Apache-2.0
      2 FSL-1.1-ALv2

$ git grep -h -o -E "SPDX-License-Identifier: [A-Za-z0-9.+-]+" -- spec | sed 's/.*: //' | sort | uniq -c | sort -rn
     38 Apache-2.0
```

The two `FSL-1.1-ALv2` hits under `packages/` are string literals inside checkers that
assert on the header text, not headers. They are counted here rather than hidden because
`git grep -o` counts occurrences, not files, and this page does not adjust numbers to look
tidier.

---

## 2 · Where the licence texts live

Four files, three licences, and the reason there are four rather than three is in §4.

| file | bytes | sha256 |
|---|---|---|
| `LICENSE` | 11 357 | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |
| `LICENSES/Apache-2.0.txt` | 11 357 | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |
| `LICENSES/LicenseRef-FSL-1.1-ALv2.txt` | 3 789 | `c9e20e8b23587d49a7afa6a6b35b980183f64b1daebc7a7312d3e7d5d51eb6aa` |
| `LICENSES/FSL-1.1-ALv2.txt` | 3 789 | `c9e20e8b23587d49a7afa6a6b35b980183f64b1daebc7a7312d3e7d5d51eb6aa` |
| `LICENSES/CC-BY-4.0.txt` | 17 023 | `d557539df68e771cc1eedcc91d13f70fca930e508d11eedcafa4b15db49e3744` |

```
$ sha256sum LICENSE LICENSES/*.txt
```

Two identities matter and both are checkable in one line each.

**The root `LICENSE` is a byte-identical copy of `LICENSES/Apache-2.0.txt`.** Not a
paraphrase, not a copy with a project header bolted on top. GitHub's licence detector reads
`LICENSE` at the repository root, compares it against a corpus of known texts, and
classifies nothing that has been edited. One added title line is enough to make
`licenseInfo` come back `null`, and `licenseInfo: null` is a Stage One disqualification
before a judge reads a word of the README.

```
$ sha256sum LICENSE LICENSES/Apache-2.0.txt
c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4 *LICENSE
c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4 *LICENSES/Apache-2.0.txt
```

**`LICENSES/FSL-1.1-ALv2.txt` is a byte-identical copy of
`LICENSES/LicenseRef-FSL-1.1-ALv2.txt`.** That is ruling L-1, and §4 explains why it exists.

```
$ sha256sum LICENSES/FSL-1.1-ALv2.txt LICENSES/LicenseRef-FSL-1.1-ALv2.txt
c9e20e8b23587d49a7afa6a6b35b980183f64b1daebc7a7312d3e7d5d51eb6aa *LICENSES/FSL-1.1-ALv2.txt
c9e20e8b23587d49a7afa6a6b35b980183f64b1daebc7a7312d3e7d5d51eb6aa *LICENSES/LicenseRef-FSL-1.1-ALv2.txt
```

`LICENSES/CC-BY-4.0.txt` is the SPDX licence-list canonical text, fetched verbatim, not
retyped:

```
$ curl -fsSL -o LICENSES/CC-BY-4.0.txt \
    https://raw.githubusercontent.com/spdx/license-list-data/main/text/CC-BY-4.0.txt
$ wc -l -c LICENSES/CC-BY-4.0.txt
  156 17023 LICENSES/CC-BY-4.0.txt
```

---

## 3 · Directory to licence

The licence assigned to each tree was not chosen here. It is the licence that tree's own
files already declare, counted. The command is the same for every row; only the pathspec
changes.

```
$ git grep -h -o -E "SPDX-License-Identifier: [A-Za-z0-9.+-]+" -- <DIR> | sed 's/.*: //' | sort | uniq -c | sort -rn
```

| tree | licence | what its own headers say (occurrences) |
|---|---|---|
| `packages/` | Apache-2.0 | `593 Apache-2.0`, `2 FSL-1.1-ALv2` (both string literals in checkers) |
| `spec/` | Apache-2.0 | `38 Apache-2.0` |
| `skills/` | Apache-2.0 | `13 Apache-2.0` |
| `scripts/` | Apache-2.0 | `19 Apache-2.0`, `3 CC-BY-4.0`, `2 FSL-1.1-ALv2`, `1 LicenseRef-FSL-1.1-ALv2` |
| `.github/` | Apache-2.0 | `17 Apache-2.0`, `1 FSL-1.1-ALv2` |
| repository root | Apache-2.0 for build files, CC-BY-4.0 for prose | `9 Apache-2.0`, `2 CC-BY-4.0` |
| `verticals/` | LicenseRef-FSL-1.1-ALv2 | `979 FSL-1.1-ALv2`, `238 LicenseRef-FSL-1.1-ALv2`, `2 Apache-2.0` |
| `infra/` | LicenseRef-FSL-1.1-ALv2 | `11 LicenseRef-FSL-1.1-ALv2` |
| `docs/` | CC-BY-4.0 | `26 CC-BY-4.0` |
| `evidence/` | CC-BY-4.0 | `16 CC-BY-4.0`, `1 Apache-2.0` |
| `qa/` | CC-BY-4.0 for prose, Apache-2.0 for the ratchets | `1 CC-BY-4.0` — see below |
| `tests/` | **split** — Apache-2.0 for substrate tests, LicenseRef-FSL-1.1-ALv2 for vertical tests | `256 FSL-1.1-ALv2`, `125 LicenseRef-FSL-1.1-ALv2`, `92 Apache-2.0`, `11 CC-BY-4.0` |

Two rows need a sentence.

**`qa/` shows one hit and has three more.** `qa/mypy-ratchet.json` and `qa/test-state.json`
carry their licence as an ordinary JSON key, `"SPDX-License-Identifier": "Apache-2.0"`, with
a quote after the colon rather than a space, so the census regex above does not see them.
REUSE reads comment headers, not JSON keys, so a checker does not see them either. They and
their sibling `qa/ruff-ratchet.json` are annotated Apache-2.0 in `REUSE.toml` to match what
two of the three already say in band.

```
$ head -c 120 qa/test-state.json
{
  "schema": "mainline.qa.test-state/1",
  "SPDX-FileCopyrightText": "2026 MAINLINE contributors",
  "SPDX-License-Identifier": "Apache-2.0",
```

**`tests/` is the one tree with no single answer**, and `REUSE.toml` reproduces the split by
subtree instead of flattening it to whichever number is larger. `tests/unit/recall_cue/` is
`11 of 11` LicenseRef-FSL-1.1-ALv2 and `tests/integration/recall_index/` is `20 of 20` FSL,
so their fixtures follow them; `tests/fixtures/`, `tests/unit/recall_fusion/`,
`tests/unit/recall_lexical/` and `tests/eval/recall/` are Apache-dominant and their fixtures
follow those.

---

## 4 · Ruling L-1 — the alias, and why it exists

**The same licence is spelled two ways in this repository, and both spellings ship a text.**

```
$ git grep -h -o -E "SPDX-License-Identifier: [A-Za-z0-9.+-]+" | sed 's/.*: //' | sort | uniq -c | sort -rn
   1242 FSL-1.1-ALv2
    790 Apache-2.0
    375 LicenseRef-FSL-1.1-ALv2
     59 CC-BY-4.0
```

That is occurrences. Per file — first header only, sidecars excluded — it is:

```
   1143 FSL-1.1-ALv2
    725 Apache-2.0
    338 LicenseRef-FSL-1.1-ALv2
     44 CC-BY-4.0
```

`LicenseRef-FSL-1.1-ALv2` is the correct spelling and `FSL-1.1-ALv2` is not. The Functional
Source License is not on the SPDX licence list, and REUSE Specification 3.3 is explicit:
"If a license does not exist in the SPDX License List, its SPDX License Identifier MUST be
`LicenseRef-[idstring]`". By the same rule, a licence file "MUST be the SPDX License
Identifier of the license followed by an appropriate file extension" — which means
`LICENSES/FSL-1.1-ALv2.txt` is itself a non-conforming filename. It ships anyway, and this
section is the disclosure.

**The ruling: ship both filenames holding byte-identical text; do not mass-edit 1 143 headers.**

The alternative was a single commit rewriting `FSL-1.1-ALv2` to `LicenseRef-FSL-1.1-ALv2`
across 1 143 files owned by all eight build domains. Three reasons that is the worse move,
in ascending order of importance.

1. It is a 1 143-file diff eight days before a deadline, touching migrations, rendered SQL
   templates and fixture bundles that are byte-addressed by the fixity checker. The blast
   radius is larger than the defect.
2. It violates the ownership rule that keeps parallel work from corrupting itself. No
   worker in the submission domain owns files under `verticals/`, `packages/`, `spec/`,
   `infra/` or `skills/`.
3. **It would hide the defect instead of recording it.** A repository whose central claim is
   that it publishes what is broken does not get to launder an inconsistency with
   `sed -i`. The divergence is real, it is now countable in one command, and S02 publishes
   it as a ratchet in `qa/reuse-ratchet.json` that may fall and may not rise. When the count
   reaches zero, `LICENSES/FSL-1.1-ALv2.txt` gets deleted and this section gets shorter.

Nothing legal turns on the spelling: both identifiers resolve to the same 3 789 bytes, and
the digests in §2 prove it.

---

## 5 · `REUSE.toml`, and the 4 518 files that cannot carry a header

7 120 files are tracked. 2 424 of them resolve a licence on their own. 4 518 cannot.

```
$ git ls-files | wc -l
7120
$ git grep -l -E "SPDX-License-Identifier" | grep -v '\.license$' | wc -l
2252
$ git ls-files '*.license' | wc -l
178
```

Of the 4 518 uncovered files, **4 461 are `.json`** and JSON has no comment syntax. A
further 19 are `py.typed`, which PEP 561 requires to be empty. The rest are captured
`EXPLAIN` output, ledger checkpoint notes and SQL transcripts that are compared byte for
byte by the fixity checker and by the console replay loader — a licence header inside one
of those is not a licence header, it is a corrupted fixture.

```
UNCOVERED : 4518
  .json        4461        verticals   4369
  .txt           21        tests          83
  .typed         19        packages       31
  .md             8        infra          15
```

Writing 4 518 `.license` sidecars would be 4 518 new files to say three sentences each.
`REUSE.toml` says the same thing once, in a file a human can read, and REUSE Specification
3.3 exists precisely for this case. Two of its semantics are load-bearing and both are
quoted in the file's own header comment:

* **`precedence = "closest"`**, stated explicitly on every block, means a file that carries
  its own header keeps it. `REUSE.toml` fills gaps; it never relicenses, rewrites or
  contradicts any of the 2 252 headers on disk. The single exception is the root `LICENSE`,
  which uses `override` because it is a licence text rather than a file licensed under one,
  and because the Apache text contains the string `SPDX-License-Identifier: Apache-2.0`
  inside its own appendix boilerplate.
* **"exclusively the LAST matching table in the file is used"** — so the blocks run
  general to specific, and reordering the file changes its meaning. Two blocks say so in a
  comment directly above themselves.

### What it covers, counted

`REUSE.toml` holds 12 `[[annotations]]` tables carrying 66 path patterns. Against the 4 518
uncovered files they match **4 516**:

```
[[annotations]] tables  : 12
path patterns           : 66
UNCOVERED before        : 4518
MATCHED by REUSE.toml   : 4516
still UNMATCHED         : 2
resolved licence of the newly-covered files:
  LicenseRef-FSL-1.1-ALv2      4399
  Apache-2.0                    103
  CC-BY-4.0                      14
unmatched files:
  LICENSES/Apache-2.0.txt
  LICENSES/LicenseRef-FSL-1.1-ALv2.txt
```

**The two unmatched files are the licence texts themselves, and they are unmatched on
purpose.** REUSE 3.3 exempts them — "The License Files stored in the `LICENSES/`
directory" are not Covered Files — and assigning this project's copyright notice to the
Apache Software Foundation's text or to Creative Commons' text would be a false statement
in a file whose entire job is to make true ones.

### Re-derived a second time, in SQL

The count above is one Python loop. A number that is only ever produced by the program that
wants it to be right is not a measurement, so the same map was loaded into CockroachDB
v26.2.5 on the local node and re-derived with SQL, from `git ls-files` and the parsed
`REUSE.toml` rather than from the Python result:

```sql
CREATE TABLE file_licence (path STRING PRIMARY KEY, resolved_by STRING NOT NULL, licence STRING NOT NULL);
SELECT resolved_by, count(*) FROM file_licence GROUP BY resolved_by ORDER BY 2 DESC;
SELECT licence, count(*) FROM file_licence WHERE licence <> 'n/a' GROUP BY licence ORDER BY 2 DESC;
```

```
rows loaded : 7120

-- how each tracked file resolves a licence
  reuse_toml             4518
  header                 2250
  sidecar_itself          178
  sidecar                 172
  licence_text              2

-- the licence every non-exempt tracked file ends up under
  LicenseRef-FSL-1.1-ALv2      4773
  FSL-1.1-ALv2                 1213
  Apache-2.0                    886
  CC-BY-4.0                      68

UNRESOLVED tracked files: 0
VERDICT: COMPLETE
```

`header` is 2 250 here and 2 252 above. The difference is exactly the two `qa/` ratchets
whose tag is a JSON key rather than a comment, so a header parser skips them and
`REUSE.toml` picks them up instead. Both numbers are correct measurements of two different
questions, and neither was adjusted to match the other.

`reuse_toml 4518` versus `MATCHED 4516` is the same two files seen from the other side: the
SQL derivation buckets `LICENSES/` separately as `licence_text`, so the two ratchets move
into `reuse_toml` and the totals meet.

---

## 6 · Re-derive everything on this page

One block, no repository scripts required, run from the repository root.

```bash
sha256sum LICENSE LICENSES/*.txt
git ls-files | wc -l
git ls-files '*.license' | wc -l
git grep -l -E "SPDX-License-Identifier" | grep -v '\.license$' | wc -l
git grep -h -o -E "SPDX-License-Identifier: [A-Za-z0-9.+-]+" | sed 's/.*: //' | sort | uniq -c | sort -rn

python3 - <<'PY'
import re, subprocess, tomllib
from collections import Counter
from pathlib import Path

def glob_re(p):
    o, i = [], 0
    while i < len(p):
        if p.startswith("**", i): o.append(".*"); i += 2
        elif p[i] == "*":         o.append("[^/]*"); i += 1
        else:                     o.append(re.escape(p[i])); i += 1
    return re.compile("^" + "".join(o) + "$")

doc = tomllib.loads(Path("REUSE.toml").read_text(encoding="utf-8"))
tables = []
for a in doc["annotations"]:
    paths = a["path"]
    paths = [paths] if isinstance(paths, str) else paths
    tables.append(([glob_re(x) for x in paths], a["SPDX-License-Identifier"]))

files = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                       check=True).stdout.split("\n")
files = [f for f in files if f]
sidecars = {f[:-8] for f in files if f.endswith(".license")}

uncovered = []
for rel in files:
    if rel.endswith(".license") or rel in sidecars:
        continue
    try:
        head = open(rel, "rb").read(8192)
    except OSError:
        head = b""
    if b"SPDX-License-Identifier" not in head:
        uncovered.append(rel)

got = Counter()
miss = []
for rel in uncovered:
    win = None
    for pats, lic in tables:
        if any(p.match(rel) for p in pats):
            win = lic
    if win is None: miss.append(rel)
    else:           got[win] += 1

print("tracked           :", len(files))
print("uncovered         :", len(uncovered))
print("matched REUSE.toml:", sum(got.values()))
for lic, n in got.most_common():
    print(f"  {lic:<28} {n}")
print("unmatched         :", len(miss))
for m in miss:
    print("   ", m)
PY
```

Expected, on the tree measured 2026-08-10:

```
tracked           : 7120
uncovered         : 4518
matched REUSE.toml: 4516
  LicenseRef-FSL-1.1-ALv2      4399
  Apache-2.0                   103
  CC-BY-4.0                    14
unmatched         : 2
    LICENSES/Apache-2.0.txt
    LICENSES/LicenseRef-FSL-1.1-ALv2.txt
```

`scripts/qa/check_reuse.py` is the checker CI runs — `.github/workflows/ci.yml` names that
exact path in its `checkers` registry and in the `reuse` lane — and `qa/reuse-ratchet.json`
is where the two-spelling divergence is published as a number that may fall and may not
rise. Both are S02's, not this file's.

---

## 7 · What is still open

Recorded here rather than in a commit message, in the manner of `docs/HONESTY.md`.

| open | detail |
|---|---|
| the two-spelling divergence | 1 143 files declare the non-SPDX `FSL-1.1-ALv2`. Mitigated by the alias text in §4, not repaired. |
| `LICENSES/FSL-1.1-ALv2.txt` is a non-conforming filename | Required by the alias; REUSE 3.3 wants the identifier to be the filename, and `FSL-1.1-ALv2` is not an identifier. Disclosed in §4. |
| SPDX headers are absent from ~4 500 files | Covered by `REUSE.toml` rather than by headers. This is the supported mechanism, not a workaround, but it means a per-file `grep` will not find a licence in a fixture. |
| the FSL future grant date is per release, and no release is tagged | Until a release is tagged the two-year Apache-2.0 conversion clock has no start. Nothing under `packages/` or `spec/` is affected; that layer is Apache-2.0 today. |
