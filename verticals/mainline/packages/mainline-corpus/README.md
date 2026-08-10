<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-corpus` — THE SYNTHETIC CORPUS

**Ninety-four modules that had no distribution.**

On 2026-08-10 this directory contained `src/mainline_corpus/` with nine stage
subpackages and no `pyproject.toml`, no top-level `__init__.py`, and no `py.typed`.
It was therefore not a uv workspace member, not installable, and not importable
except by whoever had put `…/mainline-corpus/src` on `PYTHONPATH` by hand. Four
consumers imported it regardless:

| consumer | what it imports |
|---|---|
| `tests/unit/moc_stream/{conftest,test_moc_stream}.py` | `mainline_corpus.moc_stream.build` |
| `tests/integration/schema/test_mi_event_severity.py` | `mainline_corpus.moc_stream.build` |
| `packages/mainline-boundary/.../greps.py` | the `render/` **path**, as a grep root |
| `tests/boundary/test_ci_greps.py` | the same path, asserted |

This file, `pyproject.toml`, `src/mainline_corpus/__init__.py` and `py.typed` are
the distribution those four were already assuming existed.

## The stages

Nine subpackages, six of them runnable. There are no console scripts: every stage
is invoked as a module, which is how the sources and `docs/leads/corpus-demo.md`
already spell it.

```
uv run --package mainline-corpus python -m mainline_corpus.skeleton    --out …
uv run --package mainline-corpus python -m mainline_corpus.moc_stream  --out verticals/mainline/fixtures/corpus/moc-stream
uv run --package mainline-corpus python -m mainline_corpus.blame       --out …
uv run --package mainline-corpus python -m mainline_corpus.render      --out …
uv run --package mainline-corpus python -m mainline_corpus.reflow      --out …
uv run --package mainline-corpus python -m mainline_corpus.docx        --out …
```

`gazetteer` and `prompts` are data-bearing libraries rather than stages; `rng` is
the one seeded generator, and nothing in the package calls `random` directly.

## What the wheel must carry, and why it is not only Python

`gazetteer/__init__.py` and `prompts/__init__.py` both resolve their data with
`Path(__file__).resolve().parent`, not `importlib.resources`. Eleven gazetteer YAML
files and four Markdown prompt texts therefore have to sit **beside** the modules
in the installed tree, or the package imports and then fails at first use.
`[tool.hatch.build.targets.wheel] packages = ["src/mainline_corpus"]` ships the
directory rather than the `*.py` in it, which is what makes that true.

"Hatchling includes data files by default" is a sentence about hatchling, not
about this build, so `tests/release/test_workspace_members.py` asserts it of this
build, at two strengths:

* **always** — it calls `gazetteer.checksum()` and `prompts.load_all()`, which
  read all eleven YAML files and parse all four prompt texts from wherever the
  package is installed, and raise by name when one is absent;
* **when `uv` is on the machine** — it runs `uv build --package mainline-corpus
  --wheel` and looks inside the artefact a stranger would install. Measured
  2026-08-10: 117 entries, of which 19 are not Python. This half *skips with a
  reason* when uv is absent, which on the morning this was written was this
  machine's actual state.

## Dependencies, each one measured

Derived by reading every `import` in all 94 modules, not by guessing:

* **`pyyaml`** — four unconditional top-level imports (`gazetteer`, `prompts`,
  `render.authored`, `skeleton.emit`). Floor `>=6.0`, matching `mainline-boundary`,
  `mainline-mcp` and `mainline-steward`.
* **`jinja2`** — one unconditional top-level import (`docx/template.py`, a
  `StrictUndefined` environment). Floor `>=3.1`, matching `trappoint-sql`.
* **`mainline-domain`** — `skeleton/build.py` re-checks every gazetteer citation
  against the *shipped* `REGULATORY_CITATION` extractor. It guards the import and
  records `skipped: mainline_domain not importable` in `index.json` when it fails.
  Declaring the dependency is what turns that skip into a check that runs.

**`boto3` is an extra, not a dependency** (`[bedrock]`), matching
`mainline-quarantine` and `mainline-archivist`. `render/bedrock.py` imports it
lazily, behind `--allow-live`, and its own header says the tier has never been
executed against the service from this repository.

**`python-docx` is absent on purpose.** `docx/verify.py` stage 3 uses it as a
*third-party* parse of our own output — "python-docx is not in `uv.lock` and this
build does not require it" — and returns a `skipped=True` finding when it is
missing. Adding it would put it in the lock and make that sentence false.

## Types

```
mypy --strict -p mainline_corpus   ->  95 source files, 1 error
```

The one error is `import docx` inside the optional stage-3 finding above:
`Cannot find implementation or library stub for module named "docx"`. That is the
absence being reported, so it is silenced by a module override on `docx` — and by
nothing else. There is no blanket `ignore_missing_imports` in this file.
