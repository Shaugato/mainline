<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# TRAPPOINT skills

Agent Skills for building database-enforced **refusals** on CockroachDB. Apache-2.0.

Every skill here ships a script that **fails when the guarantee does not hold**. That is the
line between a skill and a blog post: an agent that scaffolds a gate can then prove the gate
refuses, on a throwaway node, in about a minute, with no cloud account.

## Install

```bash
npx skills add Shaugato/mainline
```

Or as a Claude Code plugin, which is the same content through a different channel:

```
/plugin marketplace add Shaugato/mainline
/plugin install trappoint-skills@trappoint
```

## What is here

| Skill | Answers | Proves it with |
|---|---|---|
| [`designing-diachronic-gates`](designing-diachronic-gates/) | How do I make the database refuse a transition because of the subject's *history*, and how do I know it really refuses? | `scripts/assert_gate_refuses.py` — spins a throwaway node, replays an illegal history, fails unless the expected SQLSTATE **and constraint name** are raised, and unwelds the schema six ways to prove each mechanism is load-bearing |
| [`designing-vector-recall-prefixes`](designing-vector-recall-prefixes/) | What should the prefix columns of a C-SPANN vector index be, and how do I prove from `EXPLAIN` that the index was used? | `scripts/assert_prefix_index_used.py` — asserts the plan fragment, including the full scan sitting beside a legitimate vector search |

Both are self-contained: standard library only, no driver required, no credential of ours,
and a `--self-test` that runs anywhere.

## Try the refusal

```bash
python skills/designing-diachronic-gates/scripts/assert_gate_refuses.py --self-test
```

It starts a single-node CockroachDB (a local `cockroach` binary if you have one, otherwise
`docker`), welds a reference gate, then removes one mechanism at a time and requires the
illegal history to become **ADMITTED**. Four of the nine rows are admissions. Those are the
rows that make the other five mean anything — a suite that has never been red asserts
nothing.

## `skills/upstream/` is a staging area, not an installable skill

[`skills/upstream/`](upstream/) holds a **de-branded** skill prepared as a contribution to
[`cockroachlabs/cockroachdb-skills`](https://github.com/cockroachlabs/cockroachdb-skills),
laid out in that repository's directory shape
(`<domain>/<skill-name>/SKILL.md`). It is not one of ours, carries none of our vocabulary,
and is deliberately **not** listed in `.claude-plugin/marketplace.json`: the marketplace
enumerates the two branded skill directories explicitly rather than globbing `./skills`, so
nothing under `upstream/` is ever loaded as a plugin skill.

Its `SKILL.md` and script carry no SPDX header comment. Licensing travels in `.license`
sidecar files beside them (REUSE 3.x), because a file destined for somebody else's
repository should not carry our project name inside it — and CI greps that tree to make sure
it does not.

The proposal issue body lives in [`docs/upstream/proposal-issue.md`](../docs/upstream/proposal-issue.md).

**We claim the filing, never the merge.** Nothing in this repository depends on an upstream
maintainer doing anything, and `.github/workflows/skills.yml` fails the build on any string
in our own documentation that claims otherwise.

## Validation

Two validators, run on every push by [`skills.yml`](../.github/workflows/skills.yml):

```bash
python skills/validate-spec.py skills/ --strict
npx --yes skills-ref validate skills/designing-diachronic-gates
```

The plugin manifest has its own validator, which CI checks structurally (every declared
skill path must contain a `SKILL.md`) and which you can run directly:

```bash
claude plugin validate .claude-plugin/marketplace.json
```

`skills-ref` is the Agent Skills Specification's own reference implementation and is the
check that matters. `skills/validate-spec.py` is **our** implementation of the same rules —
it exists so this repository can validate offline and so a rule can be tightened locally.
It is *not* a byte copy of upstream's `scripts/validate-spec.py`, which could not be
reproduced exactly from here; replace it with upstream's copy at HEAD before opening a pull
request there, and re-run. A local validator agreeing with itself is not evidence about
somebody else's CI.

## Before filing anything upstream

- [ ] Re-enumerate the target domain directory at `main`. It was `.gitkeep`-only when
      checked on **2026-08-10**; being the first skill in an empty domain is the whole
      reason for the target, and it stops being true the moment somebody else files.
- [ ] Confirm the domain still appears in the issue form's dropdown
      (`.github/ISSUE_TEMPLATE/new-skill.yml`). *Resilience and Disaster Recovery* was
      present on 2026-08-10.
- [ ] Re-resolve every URL in *Supporting Documentation*; links, never copied prose.
- [ ] `python scripts/verify_restore_merkle_root.py --self-test` exits 0 on a machine with
      no third-party packages installed.
- [ ] Nothing in the upstream tree mentions this project, its verticals, or its vocabulary.
      CI checks this, but read it once yourself — the check knows only the words it was told.
