#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Validate skill directories against the Agent Skills Specification.

    python skills/validate-spec.py skills/            # a tree of skills
    python skills/validate-spec.py skills/my-skill    # one skill
    python skills/validate-spec.py skills/ --strict   # warnings become errors
    python skills/validate-spec.py skills/ --github   # GitHub Actions annotations

Exit status: 0 every skill validates · 1 at least one error (or, under ``--strict``, at
least one warning) · 2 the path was unusable.

HONESTY ABOUT WHAT THIS FILE IS. The CockroachDB Agent Skills repository ships its own
``scripts/validate-spec.py`` and runs it on contributions. This file is an INDEPENDENT
implementation of the rules that validator enforces — permitted subdirectories, frontmatter
field set and limits, naming, description shape, link resolution, body size — written so
this repository can validate its own skills offline and without vendoring a file it cannot
reproduce byte for byte. It is deliberately at least as strict as the published rules, so a
skill that passes here is not thereby guaranteed to pass upstream.

**Before opening an upstream pull request, replace this file with upstream's copy at HEAD
and re-run it.** A local validator agreeing with itself is not evidence about somebody
else's CI. `.github/workflows/skills.yml` also runs `npx skills-ref validate`, which is the
specification's own reference implementation and is the check that matters most.

Standard library only: no PyYAML. The frontmatter parser handles the flat scalar/mapping
subset the specification uses, and REFUSES anything it does not understand rather than
guessing — a validator that silently skips a field it cannot parse is worse than no
validator.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PERMITTED_DIRECTORIES = frozenset({"scripts", "references", "assets"})
REQUIRED_FIELDS = ("name", "description")
KNOWN_FIELDS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools", "version"}
)
RESERVED_NAMES = frozenset({"skill", "skills", "anthropic", "claude", "agent", "agents"})
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_BODY_LINES = 500
MIN_QUOTE_LENGTH = 2
MIN_SENTENCES = 2
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
XML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9_-]*\s*/?>")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
BACKTICK_PATH = re.compile(r"`((?:scripts|references|assets)/[^`]+)`")
GERUNDS = ("ing ",)


def _say(text: str = "") -> None:
    """Write one line to stdout through a single funnel."""
    sys.stdout.write(text + "\n")


@dataclass
class Finding:
    """One problem with one skill."""

    path: Path
    level: str
    message: str

    def render(self, *, github: bool) -> str:
        """Render as a GitHub Actions annotation or as a terminal line."""
        if github:
            kind = "error" if self.level == "error" else "warning"
            return f"::{kind} file={self.path.as_posix()}::{self.message}"
        return f"  [{self.level.upper():<7}] {self.path.as_posix()}: {self.message}"


@dataclass
class Frontmatter:
    """A parsed YAML frontmatter block, restricted to the subset the spec uses."""

    fields: dict[str, str] = field(default_factory=dict)
    nested: dict[str, dict[str, str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def parse_frontmatter(text: str) -> Frontmatter:
    """Parse the leading ``---`` block. Refuses shapes it does not understand."""
    result = Frontmatter()
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        result.errors.append("the file does not begin with a `---` frontmatter block")
        return result
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        result.errors.append("the frontmatter block is never closed with `---`")
        return result

    current: str | None = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indented = raw.startswith((" ", "\t"))
        if ":" not in raw:
            if current is not None and indented:
                joined = (result.fields.get(current, "") + " " + raw.strip()).strip()
                result.fields[current] = joined
                continue
            result.errors.append(f"frontmatter line is not `key: value`: {raw.strip()!r}")
            continue
        key, _, value = raw.partition(":")
        cleaned = _unquote(value.strip())
        if indented:
            if current is None:
                result.errors.append(f"indented frontmatter key with no parent: {raw.strip()!r}")
                continue
            result.nested.setdefault(current, {})[key.strip()] = cleaned
            continue
        current = key.strip()
        if cleaned:
            result.fields[current] = cleaned
        else:
            result.fields.setdefault(current, "")
    return result


def _unquote(value: str) -> str:
    if len(value) >= MIN_QUOTE_LENGTH and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def validate_skill(directory: Path) -> list[Finding]:
    """Validate one skill directory and return every finding."""
    skill_md = directory / "SKILL.md"
    findings: list[Finding] = []
    if not skill_md.is_file():
        return [Finding(directory, "error", "no SKILL.md in this directory")]

    text = skill_md.read_text(encoding="utf-8")
    matter = parse_frontmatter(text)
    findings.extend(Finding(skill_md, "error", message) for message in matter.errors)

    findings.extend(_check_fields(skill_md, directory, matter))
    findings.extend(_check_body(skill_md, text))
    findings.extend(_check_layout(directory))
    findings.extend(_check_links(skill_md, directory, text))
    return findings


def _check_fields(skill_md: Path, directory: Path, matter: Frontmatter) -> list[Finding]:
    findings: list[Finding] = []
    for required in REQUIRED_FIELDS:
        if not matter.fields.get(required):
            findings.append(Finding(skill_md, "error", f"frontmatter is missing `{required}`"))

    for key in matter.fields:
        if key not in KNOWN_FIELDS:
            findings.append(
                Finding(skill_md, "warning", f"frontmatter field `{key}` is not in the spec")
            )

    name = matter.fields.get("name", "")
    if name:
        findings.extend(_check_name(skill_md, directory, name))

    description = matter.fields.get("description", "")
    if description:
        findings.extend(_check_description(skill_md, description))

    compatibility = matter.fields.get("compatibility", "")
    if len(compatibility) > MAX_COMPATIBILITY:
        findings.append(
            Finding(
                skill_md,
                "error",
                f"`compatibility` is {len(compatibility)} characters (max {MAX_COMPATIBILITY})",
            )
        )
    return findings


def _check_name(skill_md: Path, directory: Path, name: str) -> list[Finding]:
    findings: list[Finding] = []
    if len(name) > MAX_NAME:
        findings.append(
            Finding(skill_md, "error", f"`name` is {len(name)} characters (max {MAX_NAME})")
        )
    if not NAME_PATTERN.match(name):
        findings.append(
            Finding(
                skill_md,
                "error",
                f"`name` {name!r} must be lowercase words joined by single hyphens",
            )
        )
    if name in RESERVED_NAMES:
        findings.append(Finding(skill_md, "error", f"`name` {name!r} is reserved"))
    if name != directory.name:
        findings.append(
            Finding(
                skill_md,
                "error",
                f"`name` is {name!r} but the directory is {directory.name!r}; they must match",
            )
        )
    if "-" not in name:
        findings.append(
            Finding(skill_md, "warning", "`name` is a single word; prefer `verb-ing-a-noun`")
        )
    elif not name.split("-", 1)[0].endswith("ing"):
        findings.append(
            Finding(
                skill_md,
                "warning",
                "`name` does not start with a gerund; upstream house style prefers "
                "`designing-…`, `verifying-…`, `configuring-…`",
            )
        )
    return findings


def _check_description(skill_md: Path, description: str) -> list[Finding]:
    findings: list[Finding] = []
    if len(description) > MAX_DESCRIPTION:
        findings.append(
            Finding(
                skill_md,
                "error",
                f"`description` is {len(description)} characters (max {MAX_DESCRIPTION})",
            )
        )
    if description.count(".") < MIN_SENTENCES:
        findings.append(
            Finding(
                skill_md,
                "error",
                "`description` must be more than one sentence: say what the skill does AND "
                "when to use it, or no agent will ever select it",
            )
        )
    if "use when" not in description.lower() and "use this" not in description.lower():
        findings.append(
            Finding(
                skill_md,
                "warning",
                "`description` names no usage trigger; a phrase beginning `Use when …` is what "
                "makes the skill discoverable",
            )
        )
    lowered = description.lower()
    if lowered.startswith(("i ", "we ", "you ")) or " we " in lowered[:80]:
        findings.append(
            Finding(
                skill_md,
                "warning",
                "`description` should be third person, not first or second",
            )
        )
    return findings


def _check_body(skill_md: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    body = text.split("---", 2)[-1]
    if not body.strip():
        findings.append(Finding(skill_md, "error", "the body after the frontmatter is empty"))
    lines = text.splitlines()
    if len(lines) > MAX_BODY_LINES:
        findings.append(
            Finding(
                skill_md,
                "warning",
                f"SKILL.md is {len(lines)} lines (guidance: under {MAX_BODY_LINES}); move detail "
                "into `references/` and let progressive disclosure do its job",
            )
        )
    stripped = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    stripped = re.sub(r"`[^`]*`", "", stripped)
    stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.DOTALL)
    tags = {match.group(0) for match in XML_TAG.finditer(stripped)}
    if tags:
        findings.append(
            Finding(
                skill_md,
                "warning",
                "XML-style tags outside code fences: " + ", ".join(sorted(tags)),
            )
        )
    return findings


def _check_layout(directory: Path) -> list[Finding]:
    findings: list[Finding] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_dir() and entry.name not in PERMITTED_DIRECTORIES:
            findings.append(
                Finding(
                    entry,
                    "error",
                    f"`{entry.name}/` is not a permitted subdirectory; only "
                    + ", ".join(sorted(PERMITTED_DIRECTORIES))
                    + " are allowed",
                )
            )
    return findings


def _check_links(skill_md: Path, directory: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    targets = {match.group(1) for match in LINK.finditer(text)}
    targets |= {match.group(1) for match in BACKTICK_PATH.finditer(text)}
    for target in sorted(targets):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        candidate = (directory / target.split("#", 1)[0]).resolve()
        if not candidate.exists():
            findings.append(Finding(skill_md, "error", f"link target does not exist: {target}"))
    return findings


def discover(root: Path) -> list[Path]:
    """Find every skill directory under a path, or return the path itself if it is one."""
    if (root / "SKILL.md").is_file():
        return [root]
    return sorted({found.parent for found in root.rglob("SKILL.md")})


def main(argv: list[str] | None = None) -> int:
    """Validate every skill under the given path and report."""
    parser = argparse.ArgumentParser(description="Validate Agent Skills against the spec.")
    parser.add_argument("path", help="a skills tree or one skill directory")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument("--github", action="store_true", help="emit GitHub Actions annotations")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.exists():
        _say(f"no such path: {root}")
        return 2

    skills = discover(root)
    if not skills:
        _say(f"no SKILL.md found under {root}. Refusing to report success on an empty tree.")
        return 2

    errors = 0
    warnings = 0
    for skill in skills:
        findings = validate_skill(skill)
        if not findings:
            level = "OK"
        elif any(finding.level == "error" for finding in findings):
            level = "FAIL"
        else:
            level = "WARN"
        _say(f"[{level}] {skill.as_posix()}")
        for finding in findings:
            _say(finding.render(github=args.github))
            if finding.level == "error":
                errors += 1
            else:
                warnings += 1

    _say("")
    _say(f"{len(skills)} skill(s), {errors} error(s), {warnings} warning(s)")
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
