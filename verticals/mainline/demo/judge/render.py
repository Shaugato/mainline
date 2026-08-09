# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Render ``QUESTIONS.yaml`` into ``PACK.md`` — the page a judge actually reads.

Two properties, and both are load-bearing rather than tidy.

**It is generated, and the generated file is committed.** ``judge/cli.py render --check``
fails when the committed page disagrees with the data, so a prompt cannot be edited in the
prose without the validator seeing it. The alternative — a hand-written page beside a
machine-checked pack — is two sources of truth, and the one a judge reads would be the
unchecked one.

**It is byte-reproducible.** No timestamp, no host, no run id, no ordering that depends on
a dictionary's insertion history. Every number on the page is read out of a committed file
at render time. A page whose bytes changed on every run could not be diffed, and a diff is
the only thing that makes "the prompts have not silently changed" checkable.

Prose items are emitted **one item per line, unwrapped**. That is deliberate: the
repository's claim-hygiene scanner is line-oriented and exempts a sentence that states its
own limit ("Nothing here separates…", "Not split-view resistance…"). Re-wrapping the
sentence would move the negation onto a different line from the claim and turn an honest
statement into a reported violation.
"""

from __future__ import annotations

from pathlib import Path

from . import envelope as env
from .drift import bind_and_measure, required_plan_substrings
from .pack import Pack, Question

_HEADER = """<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2

GENERATED FILE — do not edit by hand.

    python verticals/mainline/demo/judge/cli.py render          # rewrite this page
    python verticals/mainline/demo/judge/cli.py render --check  # fail if it has drifted

The source is QUESTIONS.yaml in this directory. Editing this page instead of that one
puts the prompt a judge reads outside the reach of the validator, which is the exact
failure this pack exists to prevent.
-->

# The judge pack — Tier 3, over CockroachDB's own managed endpoint

Every question below runs against the `mainline-verify` cluster over
`https://cockroachlabs.cloud/mcp`, with **none of our code between the prompt and the
row**. Point your own MCP client at it:

```bash
claude mcp add mainline-verify https://cockroachlabs.cloud/mcp --transport http \\
  --header "mcp-cluster-id: <cluster-id>" \\
  --header "Authorization: Bearer <service-account-api-key>"
```

The cluster id and key are published beside the submission for the duration of judging,
on a throwaway cluster holding synthetic data only. If publishing a key to anonymous
verifiers turns out to be outside Cockroach Labs' terms, this tier degrades exactly as
[`FALLBACK.md`](FALLBACK.md) describes, and it says so on the day rather than quietly
dropping the tier.

**Lead with Tier 2, not with this.** Reproducing the merge refusal on your own laptop
needs no credential of ours at all, and it is the stronger claim. See
[`../VERIFY.md`](../VERIFY.md).
"""


def _fence(sql: str) -> str:
    return f"```sql\n{sql.rstrip()}\n```"


def _envelope_section(pack: Pack) -> list[str]:
    out = [
        "## The envelope these prompts are shaped around",
        "",
        "These are documented limits of the Managed MCP Server, not preferences of ours. The",
        "binding one is the response cap: at the cap the server **truncates rather than",
        "raising**, so a partial answer about how much is currently blocked arrives looking",
        "exactly like a complete one. Every prompt below is aggregate-first because of it.",
        "",
        "| Limit | Value |",
        "|---|---|",
    ]
    labels = {
        "endpoint": "Endpoint",
        "cluster_header": "Cluster pin header",
        "max_statements_per_call": "Statements per call",
        "max_statement_chars": "Characters per statement",
        "request_timeout_seconds": "Statement timeout (s)",
        "max_response_bytes": "Response cap (bytes)",
        "our_response_budget_bytes": "Our budget (bytes) — 80 % of the cap",
        "select_page_rows": "SELECT page (rows)",
        "unreachable_schemas": "Unreachable schemas",
        "never_mcp_schemas": "Never issued to any MCP account",
        "write_surface": "The entire write surface",
    }
    for key, label in labels.items():
        value = pack.declared_envelope.get(key, env.DECLARED_ENVELOPE.get(key))
        rendered = ", ".join(f"`{v}`" for v in value) if isinstance(value, list) else f"`{value}`"
        out.append(f"| {label} | {rendered} |")
    out.append("")
    titles = {
        "outer_order_by": "The `ORDER BY` in these prompts does not reach past the view's own page",
        "truncation_guard": "Why every prompt carries an explicit `LIMIT 25`",
    }
    for key in sorted(pack.reading_notes):
        out.append(f"**{titles.get(key, key.replace('_', ' '))}.** {pack.reading_notes[key]}")
        out.append("")
    return out


def _question_section(question: Question, *, repo_root: Path) -> list[str]:
    title = f"### {question.qid} · {question.ask}"
    out = [title, ""]
    facts = [f"**verb** `{question.verb}`"]
    if question.qualified_view:
        facts.append(f"**view** `{question.qualified_view}`")
    if question.beat is not None:
        facts.append(f"**on camera** beat {question.beat} (`{question.shot_id}`)")
    if question.transcribed_from is not None:
        facts.append(f"**transcribed from** `{question.transcribed_from}`")
    if question.defined_in is not None:
        facts.append(f"**defined in** `{question.defined_in}`")
    out.append(" · ".join(facts))
    out.append("")
    out.append(_fence(question.sql))
    out.append("")
    if question.proves:
        out.append(f"**What a green answer proves.** {question.proves}")
        out.append("")
    if question.does_not_prove:
        out.append("**What it does not prove.**")
        out.append("")
        out.extend(f"- {item}" for item in question.does_not_prove)
        out.append("")
    out.extend(_plan_section(question, repo_root=repo_root))
    out.extend(_completeness_section(question))
    for note in question.honest_notes:
        out.append(f"> {note}")
        out.append("")
    return out


def _plan_section(question: Question, *, repo_root: Path) -> list[str]:
    if question.plan is None:
        return []
    plan = question.plan
    out = [
        (
            f"**Read the plan for** a `vector search` node on `{plan.index}` with a non-empty "
            "`prefix spans:` line."
        ),
        "",
    ]
    substrings = required_plan_substrings(repo_root)
    if substrings:
        out.append(
            "The substrings the film requires, read from `demo/REFUSAL-STRINGS.yaml`: "
            + ", ".join(f"`{s}`" for s in substrings)
            + "."
        )
        out.append("")
    if plan.note:
        out.append(f"**Before you send it.** {plan.note}")
        out.append("")
    if plan.substitutions:
        out.extend(f"- {item}" for item in plan.substitutions)
        out.append("")
    bound, _ = bind_and_measure(question, repo_root=repo_root)
    if bound is not None:
        verdict = "fits" if bound.fits else "DOES NOT FIT"
        out.append(
            f"**Measured, not assumed.** Bound to a worst-case {bound.dimension}-dimension "
            f"literal at six significant figures this statement is **{bound.statement_chars} "
            f"characters** against a {env.MAX_STATEMENT_CHARS} cap — {verdict}, with "
            f"{bound.headroom_chars} characters of headroom. The width is read from "
            f"`{question.defined_in}` at render time, so widening the embedding column "
            "turns this page red instead of turning the take red."
        )
        out.append("")
    return out


def _completeness_section(question: Question) -> list[str]:
    completeness = question.completeness
    if completeness is None:
        return []
    out: list[str] = []
    if completeness.columns:
        columns = ", ".join(f"`{c}`" for c in completeness.columns)
        out.append(
            f"**Truncation guard.** {columns}, plus `{completeness.guard}` — the runner flags a "
            "result of exactly 25 rows as possibly truncated whatever the view says about itself."
        )
    else:
        out.append(f"**Truncation guard.** `{completeness.guard}`.")
    if completeness.why_no_columns:
        out.append("")
        out.append(f"> {completeness.why_no_columns}")
    out.append("")
    return out


def _negatives_section(pack: Pack) -> list[str]:
    negatives = pack.negatives()
    if not negatives:
        return []
    out = [
        "---",
        "",
        "## Now try to break it — the negatives matter more than the positives",
        "",
        "Every statement in this section **must fail**. A negative suite that has quietly gone",
        "green is the worst artefact in a repository, because it reads as the strongest. Our own",
        "client refuses each of these before transmission and names the limit it broke; the",
        "server-side half is asserted by `tests/integration/mcp/test_negative_reachability.py`,",
        "which deliberately bypasses that screen — a control that lives only in our client is a",
        "control an attacker skips by not using our client.",
        "",
        "**Run these over MCP only.** On a pgwire connection as cluster admin they succeed, and",
        "reporting that as a pass would invert their meaning.",
        "",
    ]
    for question in negatives:
        out.append(f"### {question.qid} · {question.ask}")
        out.append("")
        out.append(_fence(question.sql))
        out.append("")
        out.append(f"**Must fail because.** {question.must_fail_because}")
        out.append("")
        if question.proves:
            out.append(f"**What the failure proves.** {question.proves}")
            out.append("")
        if question.does_not_prove:
            out.append("**What it does not prove.**")
            out.append("")
            out.extend(f"- {item}" for item in question.does_not_prove)
            out.append("")
    return out


def _related_section(pack: Pack) -> list[str]:
    if not pack.related_assertions:
        return []
    out = [
        "---",
        "",
        "## Asserted elsewhere, because it cannot be pasted",
        "",
    ]
    for entry in pack.related_assertions:
        out.append(f"**{entry.get('id')} — {entry.get('claim')}**")
        out.append("")
        out.append(f"{entry.get('how')}")
        out.append("")
        out.append(f"*Why it is not a question here:* {entry.get('why_not_a_question')}")
        out.append("")
    return out


def _footer(pack: Pack) -> list[str]:
    out = [
        "---",
        "",
        "## What this page is checked against",
        "",
        "| Authority | What it settles |",
        "|---|---|",
        (
            "| `verticals/mainline/db/migrations/*_v_*.sql` | every column a prompt selects "
            "exists in the shipped view |"
        ),
        (
            "| `verticals/mainline/db/migrations/0041, 0042` | the vector width, so the bound "
            "`EXPLAIN` is measured against the character cap |"
        ),
        (
            "| `verticals/mainline/demo/VERIFY.md` | every judge-facing statement is a question "
            "here or a stated exemption |"
        ),
        (
            "| `verticals/mainline/demo/REFUSAL-STRINGS.yaml` | the index name, the prefix "
            "columns and the plan substrings |"
        ),
        (
            "| `scripts/demo/claim_hygiene.py` | this page's own prose, under the same rules as "
            "the rest of the published surface |"
        ),
        "",
        "```bash",
        "python verticals/mainline/demo/judge/cli.py validate   # envelope, negatives, drift",
        "python verticals/mainline/demo/judge/cli.py render --check",
        "python verticals/mainline/demo/judge/cli.py run --via sql    # needs TRAPPOINT_DSN",
        "python verticals/mainline/demo/judge/cli.py run --via mcp    # needs a published key",
        "```",
        "",
        "Both `run` modes **exit non-zero when they had nothing to talk to**. A green run with no",
        "cluster behind it would assert nothing, and a green *negative* run with no cluster behind",
        "it would assert the opposite of what it claims.",
        "",
    ]
    if pack.authority:
        out.append("Authorities this pack implements rather than re-derives:")
        out.append("")
        out.extend(f"- {item}" for item in pack.authority)
        out.append("")
    return out


def render_pack(pack: Pack, *, repo_root: Path) -> str:
    """Render the whole pack as a Markdown page, deterministically."""
    lines: list[str] = [_HEADER, "---", ""]
    lines.extend(_envelope_section(pack))
    lines.append("---")
    lines.append("")
    lines.append("## The questions")
    lines.append("")
    for question in pack.positives():
        lines.extend(_question_section(question, repo_root=repo_root))
    lines.extend(_negatives_section(pack))
    lines.extend(_related_section(pack))
    lines.extend(_footer(pack))
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.rstrip() + "\n"
