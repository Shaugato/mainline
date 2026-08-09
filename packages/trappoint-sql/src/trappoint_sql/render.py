# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""The render engine: templates + one binding -> byte-deterministic SQL.

**Byte-deterministic is a requirement, not an aspiration.** ``trappoint render --check``
is a zero-diff assertion in CI, and the Authority Source Contract is only binding while
the committed SQL is what the declaration produced. So:

* ``StrictUndefined`` — a typo in a template name is a refusal, never an empty string
  silently rendered into a ``GRANT``;
* ``trim_blocks`` / ``lstrip_blocks`` / ``keep_trailing_newline`` — block tags do not
  leak whitespace, so a reformatted template is a reviewable diff;
* every iteration the engine feeds a template is over a **sorted or explicitly ordered**
  sequence, and templates are loaded in sorted filename order;
* files are written with ``newline="\n"`` and compared as **bytes**. On Windows the
  default text mode would translate ``\n`` to ``\r\n`` and ``--check`` would fail on
  every file for a reason that has nothing to do with the SQL.

**One template renders many files.** One DDL statement per file is not negotiable
(CockroachDB DDL is not transactional across statements, so a multi-statement file is
not atomic and ``dirty`` becomes undiagnosable), and a template that could only emit one
file would put the migration numbering in Python instead of where a reviewer reads it.
So a template emits a stream split on a ``-- @file <name>`` sentinel line. The sentinel
is a SQL comment on purpose: a stream that somehow reached a database unsplit would
still parse.
"""

from __future__ import annotations

import re
import textwrap
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from jinja2 import TemplateError as JinjaTemplateError

from .attestation import Attestation, load_attestation
from .binding import AuthorityReport, check_authority_contract, spec_version_of_tree
from .errors import RenderRefused, TemplateRefused
from .model import Binding
from .pragma import capabilities_of, projected_columns_of

__all__ = [
    "MIGRATION_SUFFIXES",
    "RENDERED_BANNER",
    "CheckFinding",
    "RenderResult",
    "Unit",
    "build_environment",
    "check_units",
    "collision_findings",
    "render_binding",
    "split_units",
    "stem_collisions",
    "version_stem",
    "write_units",
]

RENDERED_BANNER = "-- @rendered-by  trappoint render"
MIGRATION_SUFFIXES: tuple[str, ...] = (".up.sql", ".sql")

_FILE_SENTINEL = re.compile(r"^--\s*@file\s+(?P<name>\S+)\s*$")
_CITATION = re.compile(r"\b(?:MI\d{2}|I\d{2})\b")
_HEADER_WIDTH = 92
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_]\w*)?\$")
_ONE_STATEMENT = 1

# Rule `R-1`, matched on word boundaries. See `_guard_recaller_covenant` for why a
# substring test is not merely imprecise here but actively unshippable.
_GRANT = re.compile(r"\bGRANT\b", re.I)
_WRITE_PRIVILEGE = re.compile(r"\b(?:INSERT|UPDATE|DELETE|TRUNCATE|ALL(?:\s+PRIVILEGES)?)\b", re.I)


def _word(token: str) -> re.Pattern[str]:
    """Build a pattern matching *token* as a whole SQL identifier, dots included."""
    return re.compile(rf"(?<![\w.]){re.escape(token)}(?![\w.])")


# Ruling D10, duplicated here rather than imported from `trappoint-migrate`: that
# distribution's CLI dispatches `trappoint render` into this one, so depending on it
# would be a genuine import cycle. Nine lines is a cheaper price than a cycle, and the
# guard has to fire at render time or the linter finds it one commit too late.
_BANNED: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "CREATE SEQUENCE",
        re.compile(r"\bCREATE\s+(?:TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)*SEQUENCE\b", re.I),
    ),
    ("nextval(", re.compile(r"\bnextval\s*\(", re.I)),
    ("SERIAL", re.compile(r"\b(?:BIG|SMALL)?SERIAL[248]?\b", re.I)),
    ("unique_rowid()", re.compile(r"\bunique_rowid\s*\(", re.I)),
)


@dataclass(frozen=True, slots=True)
class Unit:
    """One rendered migration: one statement, one file."""

    name: str
    template: str
    text: str

    @property
    def data(self) -> bytes:
        """The exact bytes that belong on disk."""
        return self.text.encode("utf-8")


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Everything one ``render`` produced, plus what it concluded on the way."""

    binding: Binding
    units: tuple[Unit, ...]
    authority: AuthorityReport
    attestation: Attestation
    capability_uses: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def by_name(self) -> dict[str, Unit]:
        """Units keyed by output filename."""
        return {unit.name: unit for unit in self.units}


def version_stem(name: str) -> str:
    """Strip a migration suffix chain, yielding the version the runner orders on.

    ``0010_type_control_delta.up.sql`` and ``0010_type_control_delta.sql`` both yield
    ``0010_type_control_delta`` — which is why two such files in one directory are a
    tree the migration runner refuses to discover.
    """
    for suffix in MIGRATION_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _mask_quoted(sql: str) -> str:
    """Blank the interior of quoted and dollar-quoted regions, preserving length."""
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "$":
            match = _DOLLAR_TAG.match(sql, i)
            if match is not None:
                tag = match.group(0)
                close = sql.find(tag, match.end())
                end = n if close == -1 else close + len(tag)
                out.append(" " * (end - i))
                i = end
                continue
        if ch in "'\"":
            j = i + 1
            while j < n:
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(" " * (j - i))
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_line_comments(sql: str) -> str:
    out: list[str] = []
    for line in sql.splitlines():
        masked = _mask_quoted(line)
        cut = masked.find("--")
        out.append(line if cut == -1 else line[:cut])
    return "\n".join(out)


def _statement_count(sql: str) -> int:
    body = _mask_quoted(_strip_line_comments(sql))
    return len([part for part in body.split(";") if part.strip()])


def _header(
    *,
    file: str,
    vertical: str,
    license_id: str,
    title: str,
    mi: Sequence[str],
    invariants: Sequence[str],
    rationale: str,
    counsel_gated: bool,
    template: str,
    binding_path: str,
) -> str:
    """Build the header comment block every rendered migration carries.

    Implemented in Python rather than as a Jinja macro so that every vertical's
    migrations carry a byte-identical shape: the migration linter searches this block
    for an ``MI``/``I`` citation, and a per-template macro is a per-template opportunity
    to drift out of that shape.
    """
    if not mi and not invariants:
        raise TemplateRefused(
            f"{file}: header() was called with no MI and no I citation. ARCHITECTURE.md "
            "§18 requires every migration to declare which invariant it realises, at the "
            "top, where a reviewer reads it."
        )
    wrapped = textwrap.wrap(" ".join(rationale.split()), width=_HEADER_WIDTH - 14) or [""]
    lines = [
        "-- SPDX-FileCopyrightText: 2026 MAINLINE contributors",
        f"-- SPDX-License-Identifier: {license_id}",
        "--",
        f"-- {vertical} · {file}",
        f"-- {title}",
        "--",
        f"-- MI: {', '.join(mi) if mi else '(none)'}",
        f"-- I: {', '.join(invariants) if invariants else '(none)'}",
        f"-- COUNSEL-GATED: {'yes' if counsel_gated else 'no'}",
        f"-- RATIONALE: {wrapped[0]}",
        *[f"--            {line}" for line in wrapped[1:]],
        "--",
        RENDERED_BANNER,
        f"-- @template     {template}",
        f"-- @binding      {binding_path}",
        "-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a",
        "-- hand edit here is a red build, not a silent divergence.",
    ]
    return "\n".join(lines)


def build_environment(templates_dir: Path) -> Environment:
    """Construct the one Jinja environment this package ever uses.

    Every setting here exists to make the output byte-stable; see the module docstring.
    ``autoescape`` is off because the output is SQL, and HTML-escaping SQL would corrupt
    every string literal in the schema.
    """
    return Environment(
        loader=FileSystemLoader(str(templates_dir), encoding="utf-8"),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        newline_sequence="\n",
        # S701 warns about XSS from an unescaped template. The output here is SQL written
        # to a file and applied by `trappoint migrate`; HTML-escaping it would corrupt
        # every string literal in the schema — `'don''t'` and every `>` in a CHECK. The
        # suppression sits on this line rather than the call because that is where ruff
        # anchors the diagnostic, and a `noqa` on the wrong line is reported as unused.
        autoescape=False,  # noqa: S701
        auto_reload=False,
        optimized=True,
    )


def split_units(stream: str, template: str) -> list[tuple[str, str]]:
    """Split a rendered template stream into ``(filename, body)`` pairs.

    Bodies are stripped of surrounding blank lines and given exactly one trailing
    newline, so a template's own whitespace cannot make the output unstable.

    Raises:
        TemplateRefused: text appears before the first sentinel, no sentinel is present,
            or a sentinel names a file twice.
    """
    units: list[tuple[str, str]] = []
    current: str | None = None
    body: list[str] = []
    seen: set[str] = set()

    def flush() -> None:
        if current is None:
            return
        text = "\n".join(body).strip("\n")
        units.append((current, text + "\n"))

    for number, line in enumerate(stream.splitlines(), start=1):
        match = _FILE_SENTINEL.match(line)
        if match is None:
            if current is None and line.strip():
                raise TemplateRefused(
                    f"{template}:{number}: text before the first `-- @file` sentinel. "
                    "Every byte a template emits belongs to a named output file."
                )
            body.append(line)
            continue
        flush()
        current = match.group("name")
        if current in seen:
            raise TemplateRefused(f"{template}: emits {current!r} twice")
        seen.add(current)
        body = []
    flush()

    if not units:
        raise TemplateRefused(
            f"{template}: emitted no `-- @file` sentinel, so it produced no migration. "
            "A template that renders nothing is a template that silently stopped working."
        )
    return units


def _guard_unit(unit: Unit, binding: Binding) -> None:
    for token, pattern in _BANNED:
        stripped = _strip_line_comments(unit.text)
        match = pattern.search(stripped)
        if match is not None:
            raise RenderRefused(
                f"{unit.name}: banned token {match.group(0)!r} (ruling D10). "
                f"{token} makes a gap in the ledger ambiguous, and the whole evidentiary "
                "value of the ledger is that a gap MEANS tampering."
            )
    if not _CITATION.search(_header_block(unit.text)):
        raise RenderRefused(
            f"{unit.name}: the header comment cites no MInn or Inn identifier (ARCHITECTURE.md §18)"
        )
    count = _statement_count(unit.text)
    if count != _ONE_STATEMENT:
        raise RenderRefused(
            f"{unit.name}: {count} statements in one file. CockroachDB DDL is not "
            "transactional across statements, so a failure leaves a half-applied file "
            "and an undiagnosable dirty marker. Split it with a lowercase letter suffix "
            "(ruling D7)."
        )
    _guard_recaller_covenant(unit, binding)


def _header_block(sql: str) -> str:
    lines: list[str] = []
    for raw in sql.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("--"):
            lines.append(raw)
            continue
        break
    return "\n".join(lines)


def _guard_recaller_covenant(unit: Unit, binding: Binding) -> None:
    """`R-1`: the role that detects a precursor may never be granted a WRITE on one.

    Finding `S1` in one line of enforcement. ``agent_recaller`` proposes candidates over
    HTTP; the kernel writes the obligation row inside the serializable transaction that
    issues the exposure receipt. A ``GRANT INSERT`` that quietly reunited those two
    would leave every constraint in place and every test green while the flagship claim
    became false, so the renderer refuses to emit one.

    **The privilege and the relation are matched on WORD BOUNDARIES, and that is not a
    tidiness point.** A plain substring test for ``ALL`` finds one inside
    ``agent_recALLer`` — so every ``GRANT SELECT ... TO agent_recaller`` was refused as a
    write, and the covenant became "the recaller may not read the obligation table
    either". That is a rule nobody can ship a grant band under, and a guard that refuses
    correct SQL gets relaxed rather than fixed, which is how the real rule dies. Same
    reasoning for the relation: ``blocking_check`` is a prefix of a plausible
    ``blocking_check_history``, and refusing a grant on the second in the name of the
    first is a refusal with no argument behind it.

    The covenant is about WRITES only. The recaller must be able to READ what it is
    proposing against; forbidding that would be a different rule with a different
    justification, and this one has neither.
    """
    body = _strip_line_comments(unit.text)
    if not _GRANT.search(body):
        return
    recaller = binding.role("recaller")
    if not _word(recaller).search(body):
        return
    if not _WRITE_PRIVILEGE.search(body):
        return
    targets = {relation.split(".", 1)[-1] for relation in binding.obligation_relations}
    targets |= binding.obligation_relations
    for target in sorted(targets):
        if target and _word(target).search(body):
            raise RenderRefused(
                f"R-1: {unit.name} grants {recaller!r} a write privilege on {target!r}. "
                "The role that detects a precursor may not be the role that writes one "
                "(finding S1). Only the gate role materialises an obligation."
            )


def render_binding(
    binding: Binding,
    templates_dir: Path,
    *,
    extra_globals: Mapping[str, Any] | None = None,
) -> RenderResult:
    """Render every template for *binding*, enforcing every contract on the way.

    Order of enforcement matters and is fixed: the attestation is resolved **before**
    a template is rendered (an undecided capability must not produce SQL that then gets
    thrown away), the Authority Source Contract is checked **before** any file is
    written, and the per-unit guards run on the rendered text.

    Raises:
        AttestationRefused, AuthoritySourceRefused, TemplateRefused, RenderRefused.
    """
    if not templates_dir.is_dir():
        raise TemplateRefused(f"no template directory at {templates_dir}")

    sources: dict[str, str] = {}
    for path in sorted(templates_dir.glob("*.sql.j2")):
        sources[path.name] = path.read_text(encoding="utf-8")
    if not sources:
        raise TemplateRefused(f"{templates_dir} holds no *.sql.j2 templates")

    projections = {name: projected_columns_of(text) for name, text in sources.items()}
    capability_uses = {
        name: capabilities_of(text) for name, text in sources.items() if capabilities_of(text)
    }

    attestation = load_attestation(binding.attestation_path)
    for _template, names in sorted(capability_uses.items()):
        for name in names:
            attestation.require(name)
    attestation.agree("stored_digest", binding.capabilities.stored_digest)
    attestation.agree("triggerdef", binding.capabilities.triggerdef)

    report = check_authority_contract(
        binding,
        projections,
        tree_spec_version=spec_version_of_tree(binding.repo_root),
    )

    env = build_environment(templates_dir)
    if extra_globals:
        env.globals.update(dict(extra_globals))

    units: list[Unit] = []
    owner_of: dict[str, str] = {}
    for name in sorted(sources):
        context = _context(binding, attestation, template=name)
        env.globals["header"] = _header_factory(binding, template_name=name)
        try:
            stream = env.get_template(name).render(**context)
        except (JinjaTemplateError, TypeError, ValueError, AttributeError, LookupError) as exc:
            # Jinja raises its own errors for syntax and undefined names, but a template
            # calling `len()` on a dict *method* (say, `t.values`) surfaces as a plain
            # TypeError from Python. Both are the same class of defect from where the
            # operator is standing, and both must name the template.
            raise TemplateRefused(f"{name}: {type(exc).__name__}: {exc}") from exc
        for filename, body in split_units(stream, name):
            previous = owner_of.get(filename)
            if previous is not None:
                raise RenderRefused(
                    f"two templates emit {filename!r}: {previous} and {name}. Output "
                    "filenames are the migration version, and two files claiming one "
                    "version is a tree the runner refuses to discover."
                )
            owner_of[filename] = name
            unit = Unit(name=filename, template=name, text=body)
            _guard_unit(unit, binding)
            units.append(unit)

    units.sort(key=lambda unit: unit.name)
    return RenderResult(
        binding=binding,
        units=tuple(units),
        authority=report,
        attestation=attestation,
        capability_uses=capability_uses,
    )


def _header_factory(binding: Binding, *, template_name: str) -> Any:
    """Bind ``header()`` to this binding and template, so templates cannot get it wrong."""
    template_rel = f"packages/trappoint-sql/templates/{template_name}"
    binding_rel = _relative(binding.source, binding.repo_root)

    def header(
        file: str,
        title: str,
        rationale: str,
        mi: Sequence[str] = (),
        i: Sequence[str] = (),
        counsel_gated: bool = False,
    ) -> str:
        return _header(
            file=file,
            vertical=binding.vertical.name,
            license_id=binding.vertical.license,
            title=title,
            mi=list(mi),
            invariants=list(i),
            rationale=rationale,
            counsel_gated=counsel_gated,
            template=template_rel,
            binding_path=binding_rel,
        )

    return header


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _context(binding: Binding, attestation: Attestation, *, template: str) -> dict[str, Any]:
    """Build the template context. Every sequence here is explicitly ordered."""
    zones = binding.zones
    roles = binding.roles
    return {
        "template": template,
        "binding": {
            "name": binding.vertical.name,
            "schema": binding.vertical.schema,
            "spec_version": binding.vertical.spec_version,
            "license": binding.vertical.license,
            "description": binding.vertical.description,
            "emit_outbox": binding.emit_outbox,
            "source": _relative(binding.source, binding.repo_root),
            "output_dir": binding.vertical.output_dir,
            "profile": binding.conformance_profile,
        },
        "zones": [{"zone": z.zone, "name": z.name, "purpose": z.purpose} for z in zones],
        "zone": {z.zone: z.name for z in zones},
        "roles": [
            {
                "slot": r.slot,
                "name": r.name,
                "nologin": r.nologin,
                "purpose": r.purpose,
                "overridable": r.overridable,
            }
            for r in roles
        ],
        "role": {r.slot: r.name for r in roles},
        "capabilities": {
            "stored_digest": binding.capabilities.stored_digest,
            "triggerdef": binding.capabilities.triggerdef,
            "isolation": binding.capabilities.isolation,
        },
        "cluster": attestation.cluster,
        "subjects": [
            {
                "kind": s.kind,
                "table": s.table,
                "id_column": s.id_column,
                "epoch_column": s.epoch_column,
                "state_column": s.state_column,
                "completing_state": s.completing_state,
                "transition_table": s.transition_table,
                "counters": [
                    {"column": c.column, "constraint": c.constraint, "polarity": c.polarity}
                    for c in s.counters
                ],
            }
            for s in binding.subjects
        ],
        "authority_sources": [
            {
                "projects": list(a.projects),
                "relation": a.relation,
                "key": list(a.key),
                "key_columns": list(a.key_columns),
                "columns": list(a.columns),
                "raise_via": a.raise_via,
            }
            for a in binding.authority_sources
        ],
    }


@dataclass(frozen=True, slots=True)
class CheckFinding:
    """One difference between what the templates say and what is committed."""

    name: str
    kind: str
    detail: str

    def render(self) -> str:
        """One line, path first."""
        return f"{self.name}: {self.kind} — {self.detail}"


def check_units(result: RenderResult) -> list[CheckFinding]:
    """Compare the rendered units with what is committed. Zero findings is the assertion.

    Four kinds of finding, and the last two are the ones people forget:

    * ``missing`` — the template renders a file that is not committed;
    * ``diff`` — the committed bytes are not the rendered bytes;
    * ``stale`` — a file carrying the rendered-by banner that no template produces any
      more. Without this, deleting a template leaves its output applied forever.
    * ``collision`` — two committed files claim one migration version. Promoted from
      advisory by MR-6: zero diff over a tree the runner refuses to discover is a green
      assertion about a dead deploy.
    """
    findings: list[CheckFinding] = []
    out = result.binding.output_dir
    for unit in result.units:
        target = out / unit.name
        if not target.is_file():
            findings.append(CheckFinding(unit.name, "missing", f"not committed under {out}"))
            continue
        committed = target.read_bytes()
        if committed != unit.data:
            findings.append(
                CheckFinding(
                    unit.name,
                    "diff",
                    f"committed {len(committed)} byte(s), rendered {len(unit.data)} byte(s); "
                    f"run `trappoint render --binding {result.binding.source}`",
                )
            )
    known = {unit.name for unit in result.units}
    if out.is_dir():
        for path in sorted(out.iterdir()):
            if not path.is_file() or path.name in known:
                continue
            if not path.name.endswith(".sql"):
                continue
            head = path.read_text(encoding="utf-8", errors="replace")[:4096]
            if RENDERED_BANNER in head:
                findings.append(
                    CheckFinding(
                        path.name,
                        "stale",
                        "carries the rendered-by banner but no template produces it",
                    )
                )
    findings.extend(collision_findings(out))
    return findings


def collision_findings(directory: Path) -> list[CheckFinding]:
    """``stem_collisions()`` as ``--check`` findings — the promotion, in one function."""
    return [
        CheckFinding(
            names[0],
            "collision",
            f"{', '.join(names)} all claim migration version {stem!r}. "
            "`trappoint migrate` refuses to discover this tree, so nothing here applies "
            "at all; the owner of the non-rendered twin removes it (deleting the "
            "rendered one only lasts until the next render).",
        )
        for stem, names in stem_collisions(directory)
    ]


def stem_collisions(directory: Path) -> list[tuple[str, tuple[str, ...]]]:
    """Report files that would claim the same migration version.

    **A ``--check`` FAILURE (MR-6, 2026-08-08), no longer advisory.** The old argument
    was that a foreign file in the output directory is not a *diff*, and ``--check``'s
    contract is zero-diff — every clause of which is true, and the conclusion drawn from
    it was still wrong: ``--check``'s contract is that the committed tree is the one the
    templates produced, and a tree the migration runner refuses to discover is not that
    tree, so a green ``--check`` over it asserts something false.

    This is the function that would have caught the incident of 2026-08-08 on day one —
    seven duplicate stems, ``0010`` to ``0016``, each a rendered ``.sql`` beside a
    hand-authored ``.up.sql`` — and it was returning its finding to nobody.
    """
    buckets: dict[str, list[str]] = {}
    if not directory.is_dir():
        return []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or not path.name.endswith(MIGRATION_SUFFIXES):
            continue
        buckets.setdefault(version_stem(path.name), []).append(path.name)
    return [(stem, tuple(names)) for stem, names in sorted(buckets.items()) if len(names) > 1]


def write_units(result: RenderResult) -> list[str]:
    """Write every unit to the binding's output directory. Returns the names that changed.

    Unchanged files are not rewritten. That keeps ``git status`` honest and keeps mtimes
    stable for anything watching the tree.
    """
    out = result.binding.output_dir
    out.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []
    for unit in result.units:
        target = out / unit.name
        if target.is_file() and target.read_bytes() == unit.data:
            continue
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(unit.text)
        changed.append(unit.name)
    return changed


def iter_template_names(templates_dir: Path) -> Iterable[str]:
    """Yield template filenames in the exact order the engine renders them."""
    return (path.name for path in sorted(templates_dir.glob("*.sql.j2")))
