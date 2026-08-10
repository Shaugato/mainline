# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""This domain's CI greps — four bans, each with a reason that is not style.

* **No ``tenacity`` / ``backoff`` / ``retrying``.** MI-level rule from §16:
  ``40001`` is the only retryable SQLSTATE; ``23514``/``23503``/``23505``/``P0001``
  are gate refusals, attempted exactly once, ever. A blanket retry helper cannot
  tell those apart, so a decorator that retries "on exception" turns a refusal
  into a race. And on the model side (§8.4) a schema violation gets exactly one
  retry with the validator error appended, then dead-letters — never a free-text
  retry loop, because a retry loop against an ill-posed prompt is how a silent
  extraction failure becomes a silent memory gap.

* **No ``temperature`` / ``top_p`` / ``top_k``.** Decision A6. They return 400 on
  this Claude generation, and the honest claim was never reproducibility (§8.2) —
  it is *replayability* plus *arithmetic reproducibility*. A parameter that cannot
  exist cannot be blamed for drift.

* **No per-signer dimension in any metric label.** §12: ``permit_id``,
  ``clause_uuid`` and — critically — ``signer_sub`` are span attributes, never
  metric labels. The legal rule and the cardinality rule are the same rule.

* **The §11.7 must-not-claim strings are absent from README / deck / VERIFY.md.**

The greps are AST-based wherever a string would be ambiguous. That matters most
for the sampling ban: a repo-wide text grep for ``temperature`` matches a domain
lexicon entry about process temperature, and a check that everybody learns to
ignore is a check that is already dead.

**2026-08-10 — the sampling rule was narrowed, because it did exactly that.**
Run ``31427116607`` reported ``examined=3203 violations=2``, and both violations
were physical-dimension tables in an industrial-safety domain that also carries
``pressure``, ``lel`` and ``uel``:

* ``packages/trappoint-recall/src/trappoint_recall/lexical/units.py:67`` —
  ``DIMENSION_SYMBOL = {…, "temperature": "k", …}``;
* ``verticals/mainline/…/mainline_domain/quantity/units.py:262`` —
  ``_LABEL_REPRESENTATIVES = {…, "temperature": "kelvin", …}``.

Neither is a request builder; the paragraph above had predicted the failure mode
word for word. Being AST-based was not enough, because ``ast.walk`` sees the node
and not the *context*: ``{"temperature": "k"}`` and ``{"temperature": 0.0}``
beside ``"modelId"`` are the same node and opposite findings. The rule now walks
the tree carrying that context (:func:`sampling_sites`) and fires only inside a
**request-builder context**. Neither units.py acquired an exemption; the ban
still fires on a real ``temperature=`` on a real transport call, which
``tests/boundary/test_ci_greps.py`` proves by planting one next to a copy of the
very tables that used to trip it.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from .findings import Enforcement, Report
from .repo import iter_files, iter_python_files, rel

AUTHORITY_RETRY = "ARCHITECTURE.md §16 (40001 is the only retryable code) / §8.4"
AUTHORITY_SAMPLING = "docs/leads/agents-mcp.md A6 / ARCHITECTURE.md §8.2"
AUTHORITY_METRICS = "ARCHITECTURE.md §12 (label budget is the design constraint)"
AUTHORITY_CLAIMS = "ARCHITECTURE.md §11.7 (the must-not-claim list)"

# ---------------------------------------------------------------------------
# 1. Retry helpers
# ---------------------------------------------------------------------------

RETRY_MODULES: frozenset[str] = frozenset({"tenacity", "backoff", "retrying", "stamina"})


def scan_retry_imports(root: Path, *, repo_root: Path | None = None) -> Report:
    base = repo_root or root
    report = Report(enforcement=Enforcement.GREP)
    for path in iter_python_files(root):
        report.examine()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError):
            continue
        except SyntaxError as exc:
            report.violate(
                rule="GREP-UNPARSEABLE",
                subject=rel(path, base),
                detail=f"file could not be parsed, so it was not cleared: {exc}",
                authority=AUTHORITY_RETRY,
            )
            continue
        for node in ast.walk(tree):
            modules: list[tuple[str, int]] = []
            if isinstance(node, ast.Import):
                modules = [(a.name.split(".")[0], node.lineno) for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [(node.module.split(".")[0], node.lineno)]
            for module, lineno in modules:
                if module in RETRY_MODULES:
                    report.violate(
                        rule="GREP-RETRY-IMPORT",
                        subject=f"{rel(path, base)}:{lineno}",
                        detail=(
                            f"imports {module!r}. A blanket retry helper cannot tell a "
                            "serialization restart (40001, retryable) from a gate refusal "
                            "(23514/23503/23505/P0001, attempted exactly once, ever)"
                        ),
                        authority=AUTHORITY_RETRY,
                    )
    return report


def scan_retry_dependencies(root: Path, *, repo_root: Path | None = None) -> Report:
    """A declared dependency is a loaded gun even before anything imports it."""
    base = repo_root or root
    report = Report(enforcement=Enforcement.GREP)
    for path in iter_files(root, (".toml",)):
        if path.name != "pyproject.toml":
            continue
        report.examine()
        try:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        for requirement in _declared_requirements(document):
            name = re.split(r"[<>=!~\[\s;]", requirement, maxsplit=1)[0].strip().lower()
            if name.replace("-", "_") in RETRY_MODULES:
                report.violate(
                    rule="GREP-RETRY-DEPENDENCY",
                    subject=rel(path, base),
                    detail=f"declares a dependency on {name!r}",
                    authority=AUTHORITY_RETRY,
                )
    return report


def _declared_requirements(document: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    project = document.get("project")
    if isinstance(project, Mapping):
        deps = project.get("dependencies")
        if isinstance(deps, list):
            out.extend(str(d) for d in deps)
        optional = project.get("optional-dependencies")
        if isinstance(optional, Mapping):
            for group in optional.values():
                if isinstance(group, list):
                    out.extend(str(d) for d in group)
    groups = document.get("dependency-groups")
    if isinstance(groups, Mapping):
        for group in groups.values():
            if isinstance(group, list):
                out.extend(str(d) for d in group if isinstance(d, str))
    return out


# ---------------------------------------------------------------------------
# 2. Sampling parameters
# ---------------------------------------------------------------------------

SAMPLING_KEYS: frozenset[str] = frozenset(
    {"temperature", "top_p", "top_k", "topP", "topK", "topSequences"}
)

#: Where model requests are built. Scoped rather than repo-wide on purpose: a
#: repo-wide grep for ``temperature`` in a process-safety corpus is noise.
SAMPLING_SCAN_ROOTS: tuple[str, ...] = (
    "packages",
    "verticals/mainline/packages",
    "scripts",
)

#: Keys and keyword arguments that **only a model request carries**. This is the
#: evidence that turns a bare token into a request-builder context, and it is the
#: whole of the 2026-08-10 narrowing (see the section comment above). Every entry
#: is a wire-protocol name from the Bedrock ``Converse`` / ``InvokeModel``
#: contract or the Anthropic Messages contract.
#:
#: Deliberately ABSENT, and each absence is a decision: ``model`` (an equipment
#: model number is a first-class field in this domain), ``body``, ``system`` (a
#: plant system), ``tools`` (a permit's tool list) and ``config``. A marker whose
#: meaning changes with the domain is not a marker, it is the false positive we
#: are removing.
REQUEST_MARKER_KEYS: frozenset[str] = frozenset(
    {
        "additionalModelRequestFields",
        "anthropic_beta",
        "anthropic_version",
        "generationConfig",
        "guardrailConfig",
        "guardrailIdentifier",
        "inferenceConfig",
        "inference_config",
        "inputText",
        "max_completion_tokens",
        "max_tokens",
        "max_tokens_to_sample",
        "maxTokens",
        "messages",
        "modelArn",
        "modelId",
        "model_id",
        "prompt",
        "promptVariables",
        "stopSequences",
        "stop_sequences",
        "systemPrompt",
        "system_prompt",
        "textGenerationConfig",
        "toolChoice",
        "toolConfig",
        "tool_choice",
        "tool_config",
    }
)

#: Method names that ARE a model transport, whatever the receiver is called.
MODEL_TRANSPORT_METHODS: frozenset[str] = frozenset(
    {
        "converse",
        "converse_stream",
        "create_message",
        "generate_content",
        "invoke_agent",
        "invoke_endpoint",
        "invoke_flow",
        "invoke_model",
        "invoke_model_with_response_stream",
        "retrieve_and_generate",
    }
)

#: ``messages.create(...)`` / ``chat.completions.create(...)``: the tail method is
#: generic, the namespace it hangs off is not. Matched per dotted SEGMENT, never
#: as a substring — ``"llm" in "allmatches"`` is exactly how a grep starts lying.
MODEL_TRANSPORT_NAMESPACES: frozenset[str] = frozenset(
    {"chat", "completions", "messages", "responses"}
)
MODEL_TRANSPORT_TAIL_METHODS: frozenset[str] = frozenset(
    {"complete", "create", "generate", "stream", "submit"}
)

#: Receivers that can only be a model client.
MODEL_TRANSPORT_RECEIVERS: frozenset[str] = frozenset(
    {
        "anthropic",
        "bedrock",
        "bedrock_runtime",
        "bedrockruntime",
        "llm_client",
        "model_client",
        "openai",
    }
)

#: Names a request body is bound to. Exact, lower-cased, whole-name matches — the
#: point of the narrowing is that ``DIMENSION_SYMBOL`` and ``_LABEL_REPRESENTATIVES``
#: are not in here and never can be, whereas ``body`` and ``BODY`` are.
REQUEST_BODY_NAMES: frozenset[str] = frozenset(
    {
        "body",
        "converse_request",
        "inference_config",
        "inferenceconfig",
        "invoke_body",
        "kwargs",
        "model_kwargs",
        "model_params",
        "model_request",
        "payload",
        "req",
        "request",
        "request_body",
    }
)

_MUTATING_DICT_METHODS: frozenset[str] = frozenset({"setdefault", "update"})

#: Paths deliberately outside the ban, each with the reason. Exemptions are
#: reported, never silent — and since 2026-08-10 the report also names what the
#: narrowed rule WOULD have flagged there, so the exemption states its own size.
SAMPLING_EXEMPT_PREFIXES: tuple[tuple[str, str], ...] = (
    (
        "verticals/mainline/packages/mainline-corpus/src/mainline_corpus/render",
        "the demo-corpus renderer targets a different (Sonnet-4.5 Converse) generation "
        "that does accept sampling parameters, is offline-by-default, and is not on the "
        "merge path. A6 bans sampling parameters in the FLEET's request builders. This "
        "exemption is a cross-domain note, not a licence to widen the ban's hole.",
    ),
)

#: Printed in every report, so the scope of the rule is part of its output rather
#: than something a reader has to reconstruct from the source.
SAMPLING_SCOPE_NOTE = (
    "GREP-SAMPLING-PARAM fires on a sampling parameter in a REQUEST-BUILDER CONTEXT "
    "only: a keyword argument on a model transport call, a keyword or dict key "
    f"standing beside one of {len(REQUEST_MARKER_KEYS)} wire-protocol markers "
    "(modelId, messages, anthropic_version, inferenceConfig, maxTokens, …), or a "
    "write into a name bound to a request body. A bare token in a module-level "
    "lookup table is not a request builder and is not a finding."
)


@dataclass(frozen=True, slots=True)
class SamplingSite:
    """One sampling parameter, and the evidence that its context is a request."""

    key: str
    lineno: int
    context: str


def sampling_sites(tree: ast.AST) -> list[SamplingSite]:
    """Every sampling parameter in ``tree`` that sits in a request-builder context.

    A contextual walk rather than :func:`ast.walk`, because the context is the
    whole question: ``{"temperature": "k"}`` in a physical-dimension table and
    ``{"temperature": 0.0}`` beside ``"modelId"`` are the same node and opposite
    findings. Request context is entered by a transport call, by a marker key or
    keyword, or by a binding to a request-body name, and is inherited by every
    descendant so a nested ``inferenceConfig`` block is covered by its parent.
    """
    out: list[SamplingSite] = []
    _visit(tree, in_request=False, out=out)
    out.sort(key=lambda site: (site.lineno, site.key))
    return out


def scan_sampling_params(
    root: Path,
    *,
    repo_root: Path | None = None,
    scan_roots: Sequence[str] = SAMPLING_SCAN_ROOTS,
    exemptions: Sequence[tuple[str, str]] = SAMPLING_EXEMPT_PREFIXES,
) -> Report:
    base = repo_root or root
    report = Report(enforcement=Enforcement.GREP)
    report.note(SAMPLING_SCOPE_NOTE)
    for scan_root in _resolve_scan_roots(root, scan_roots):
        for path in iter_python_files(scan_root):
            where = rel(path, base)
            exempt = next((r for p, r in exemptions if where.startswith(p)), None)
            tree = _parse(path)
            if exempt is not None:
                report.exempt(
                    rule="GREP-SAMPLING-PARAM",
                    subject=where,
                    reason=exempt + _withheld(tree),
                )
                continue
            report.examine()
            if tree is None:
                continue
            for site in sampling_sites(tree):
                report.violate(
                    rule="GREP-SAMPLING-PARAM",
                    subject=f"{where}:{site.lineno}",
                    detail=(
                        f"a model request builder sets {site.key!r} — {site.context}. "
                        "A6: sampling parameters return 400 on this generation, and the "
                        "claim was always replayability plus arithmetic reproducibility, "
                        "never reproducibility of model output"
                    ),
                    authority=AUTHORITY_SAMPLING,
                )
    return report


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None


def _withheld(tree: ast.AST | None) -> str:
    """What the rule would have reported in an exempt file, appended to the reason.

    An exemption that hides an unknown quantity is weaker than one that states
    its size: this is what makes the corpus-renderer hole arguable rather than
    merely declared.
    """
    if tree is None:
        return " (unparseable, so nothing was withheld and nothing was cleared)"
    sites = sampling_sites(tree)
    if not sites:
        return " Withheld here: nothing — the narrowed rule finds no request builder."
    named = ", ".join(f"{site.key}:{site.lineno}" for site in sites)
    return f" Withheld here: {named}."


def _visit(node: ast.AST, *, in_request: bool, out: list[SamplingSite]) -> None:
    child_context = in_request
    if isinstance(node, ast.Call):
        child_context = _visit_call(node, in_request=in_request, out=out)
    elif isinstance(node, ast.Dict):
        child_context = _visit_dict(node, in_request=in_request, out=out)
    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
        child_context = _visit_assignment(node, out=out) or in_request
    for child in ast.iter_child_nodes(node):
        _visit(child, in_request=child_context, out=out)


def _visit_call(call: ast.Call, *, in_request: bool, out: list[SamplingSite]) -> bool:
    receiver = _receiver_text(call.func)
    method = receiver.rsplit(".", 1)[-1]
    markers = sorted({k.arg for k in call.keywords if k.arg in REQUEST_MARKER_KEYS})
    transport = _is_transport_call(receiver, method)
    bodies = sorted((_name_segments(call.func) - {method}) & REQUEST_BODY_NAMES)
    mutates_body = method in _MUTATING_DICT_METHODS and bool(bodies)
    is_request = in_request or transport or bool(markers) or mutates_body

    if not is_request:
        return False
    if transport:
        why = f"keyword argument on {receiver}(), which is a model transport"
    elif markers:
        why = f"keyword argument standing beside {markers[0]!r} on {receiver}()"
    elif mutates_body:
        why = f"{method}() writing into the request body {bodies[0]!r}"
    else:
        why = "keyword argument inside a model request under construction"
    for keyword in call.keywords:
        if keyword.arg in SAMPLING_KEYS:
            out.append(SamplingSite(keyword.arg, keyword.lineno, why))
    if mutates_body:
        for arg in call.args:
            if isinstance(arg, ast.Constant) and arg.value in SAMPLING_KEYS:
                out.append(SamplingSite(str(arg.value), arg.lineno, why))
    return True


def _visit_dict(node: ast.Dict, *, in_request: bool, out: list[SamplingSite]) -> bool:
    literal = {
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    markers = sorted(literal & REQUEST_MARKER_KEYS)
    is_request = in_request or bool(markers)
    if not is_request:
        return False
    why = (
        f"dict key standing beside {markers[0]!r}"
        if markers
        else "dict key inside a model request under construction"
    )
    for key in node.keys:
        if isinstance(key, ast.Constant) and key.value in SAMPLING_KEYS:
            out.append(SamplingSite(str(key.value), key.lineno, why))
    return True


def _visit_assignment(node: ast.Assign | ast.AnnAssign, *, out: list[SamplingSite]) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    binds_request_body = False
    for target in targets:
        bodies = sorted(_name_segments(target) & REQUEST_BODY_NAMES)
        if not bodies:
            continue
        binds_request_body = True
        if isinstance(target, ast.Subscript):
            index = target.slice
            if isinstance(index, ast.Constant) and index.value in SAMPLING_KEYS:
                out.append(
                    SamplingSite(
                        str(index.value),
                        target.lineno,
                        f"subscript assignment into the request body {bodies[0]!r}",
                    )
                )
    return binds_request_body


def _is_transport_call(receiver: str, method: str) -> bool:
    if method in MODEL_TRANSPORT_METHODS:
        return True
    segments = set(receiver.split("."))
    if method in MODEL_TRANSPORT_TAIL_METHODS and segments & MODEL_TRANSPORT_NAMESPACES:
        return True
    return bool(segments & MODEL_TRANSPORT_RECEIVERS)


def _name_segments(node: ast.AST | None) -> set[str]:
    """Every lower-cased name in a ``a.b["c"]`` chain, so ``self.body`` matches ``body``."""
    out: set[str] = set()
    current: ast.AST | None = node
    while True:
        if isinstance(current, ast.Attribute):
            out.add(current.attr.lower())
            current = current.value
        elif isinstance(current, ast.Subscript):
            current = current.value
        elif isinstance(current, ast.Call):
            current = current.func
        else:
            break
    if isinstance(current, ast.Name):
        out.add(current.id.lower())
    return out


def _resolve_scan_roots(root: Path, scan_roots: Sequence[str]) -> list[Path]:
    resolved: list[Path] = []
    for name in scan_roots:
        candidate = root / name
        if candidate.exists():
            resolved.append(candidate)
    return resolved or ([root] if root.exists() else [])


# ---------------------------------------------------------------------------
# 3. Metric labels
# ---------------------------------------------------------------------------

#: Per-signer dimensions. §11.5's Attribution Rule and §12's cardinality rule
#: land on the same list, which is the best kind of rule.
PER_SIGNER_LABELS: frozenset[str] = frozenset(
    {
        "signer",
        "signer_sub",
        "signer_id",
        "signer_email",
        "signer_name",
        "person_id",
        "person_sub",
        "subject_sub",
        "user_id",
        "username",
        "email",
    }
)

#: High-cardinality identifiers §12 names explicitly as span attributes only.
HIGH_CARDINALITY_LABELS: frozenset[str] = frozenset(
    {"permit_id", "clause_uuid", "disposition_id", "check_id", "commit_sha", "trace_id"}
)

METRIC_METHODS: frozenset[str] = frozenset(
    {"add", "record", "observe", "labels", "put_metric_data", "increment", "distribution"}
)


def scan_metric_labels(root: Path, *, repo_root: Path | None = None) -> Report:
    base = repo_root or root
    report = Report(enforcement=Enforcement.GREP)
    for path in iter_python_files(root):
        report.examine()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for name, lineno in _label_names(node):
                bare = name.split(":", 1)[0].strip().lower()
                if bare in PER_SIGNER_LABELS:
                    report.violate(
                        rule="GREP-METRIC-SIGNER-LABEL",
                        subject=f"{rel(path, base)}:{lineno}",
                        detail=(
                            f"metric label {name!r} carries a per-signer dimension. §12: "
                            "signer_sub is a span attribute, never a metric label — the "
                            "legal rule and the cardinality rule are the same rule"
                        ),
                        authority=AUTHORITY_METRICS,
                    )
                elif bare in HIGH_CARDINALITY_LABELS:
                    report.violate(
                        rule="GREP-METRIC-HIGH-CARDINALITY-LABEL",
                        subject=f"{rel(path, base)}:{lineno}",
                        detail=(
                            f"metric label {name!r} is named in §12 as a span attribute, "
                            "never a metric label"
                        ),
                        authority=AUTHORITY_METRICS,
                    )
    return report


#: Keywords that can only be metric dimensions, whatever the receiver is called.
UNAMBIGUOUS_LABEL_KEYWORDS: frozenset[str] = frozenset(
    {"labelnames", "label_names", "dimensions", "MetricData"}
)

#: Keywords that mean "metric label" on a metric instrument and "span attribute"
#: on a tracer. §12 explicitly *permits* permit_id and signer_sub as span
#: attributes, so flagging them there would be flatly wrong; the receiver name is
#: what disambiguates.
CONTEXTUAL_LABEL_KEYWORDS: frozenset[str] = frozenset({"attributes", "labels", "tags"})

_METRIC_RECEIVER_HINTS: tuple[str, ...] = (
    "metric",
    "counter",
    "histogram",
    "gauge",
    "meter",
    "statsd",
    "cloudwatch",
    "telemetry",
    "otel",
    "prom",
    "updowncounter",
)


def _receiver_text(func: ast.AST) -> str:
    parts: list[str] = []
    node: ast.AST | None = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append(_receiver_text(node.func))
    return ".".join(reversed(parts)).lower()


def _looks_like_metric(text: str) -> bool:
    return any(hint in text for hint in _METRIC_RECEIVER_HINTS)


def _label_names(call: ast.Call) -> list[tuple[str, int]]:
    """String constants that function as label *names* in a metric call."""
    out: list[tuple[str, int]] = []
    func = call.func
    method = (
        func.attr
        if isinstance(func, ast.Attribute)
        else (func.id if isinstance(func, ast.Name) else "")
    )
    receiver = _receiver_text(func)
    metric_context = _looks_like_metric(receiver) or method in {"put_metric_data", "labels"}

    for keyword in call.keywords:
        contextual = keyword.arg in CONTEXTUAL_LABEL_KEYWORDS and metric_context
        if keyword.arg in UNAMBIGUOUS_LABEL_KEYWORDS or contextual:
            out.extend(_names_in(keyword.value))
        elif method == "labels" and keyword.arg:
            out.append((keyword.arg, keyword.lineno))

    if metric_context and method in METRIC_METHODS:
        for arg in call.args:
            if isinstance(arg, (ast.Dict, ast.List, ast.Tuple)):
                out.extend(_names_in(arg))
    return out


def _names_in(node: ast.AST) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=False):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value == "Name" and isinstance(value, ast.Constant):
                    if isinstance(value.value, str):
                        out.append((value.value, value.lineno))
                else:
                    out.append((key.value, key.lineno))
            out.extend(_names_in(value))
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for element in node.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                out.append((element.value, element.lineno))
            else:
                out.extend(_names_in(element))
    return out


# ---------------------------------------------------------------------------
# 4. The must-not-claim list
# ---------------------------------------------------------------------------

CLAIM_TARGET_FILES: tuple[str, ...] = ("README.md", "VERIFY.md")
CLAIM_TARGET_DIRS: tuple[str, ...] = ("docs/deck", "docs/submission")

GLOBAL_NEGATION = re.compile(
    r"(?i)\b(never|not|no|cannot|can't|without|refus\w+|declin\w+|out of scope|"
    r"must[- ]not|do(es)? not|is not|are not|weaker|instead of|rather than)\b"
)


@dataclass(frozen=True, slots=True)
class ClaimRule:
    rule_id: str
    description: str
    source: str
    patterns: tuple[re.Pattern[str], ...]
    allow_if: tuple[re.Pattern[str], ...]


def load_claim_rules() -> tuple[ClaimRule, ...]:
    text = (
        resources.files("mainline_boundary")
        .joinpath("data", "must-not-claim.yaml")
        .read_text(encoding="utf-8")
    )
    document = yaml.safe_load(text)
    entries = document.get("claims") if isinstance(document, Mapping) else None
    if not isinstance(entries, list):
        raise ValueError("must-not-claim.yaml has no 'claims' list")
    out: list[ClaimRule] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        out.append(
            ClaimRule(
                rule_id=str(entry.get("id", "")),
                description=str(entry.get("description", "")),
                source=str(entry.get("source", AUTHORITY_CLAIMS)),
                patterns=tuple(
                    re.compile(str(p), re.IGNORECASE) for p in entry.get("patterns", [])
                ),
                allow_if=tuple(
                    re.compile(str(p), re.IGNORECASE) for p in entry.get("allow_if", [])
                ),
            )
        )
    return tuple(out)


def claim_documents(root: Path) -> tuple[Path, ...]:
    out: list[Path] = []
    for name in CLAIM_TARGET_FILES:
        candidate = root / name
        if candidate.is_file():
            out.append(candidate)
    for directory in CLAIM_TARGET_DIRS:
        base = root / directory
        if base.is_dir():
            out.extend(iter_files(base, (".md", ".txt", ".html")))
    return tuple(out)


def scan_must_not_claim(
    root: Path, *, rules: Iterable[ClaimRule] | None = None, require_readme: bool = True
) -> Report:
    report = Report(enforcement=Enforcement.GREP)
    claim_rules = tuple(rules) if rules is not None else load_claim_rules()
    documents = claim_documents(root)

    if require_readme and not (root / "README.md").is_file():
        report.violate(
            rule="GREP-CLAIM-NO-README",
            subject="README.md",
            detail=(
                "the must-not-claim grep has no README to read. §11.7 binds the list "
                "into README, deck, video and MSA; a missing README is an unchecked one"
            ),
            authority=AUTHORITY_CLAIMS,
        )
    for name in CLAIM_TARGET_FILES:
        if not (root / name).is_file():
            report.skip(
                rule="GREP-CLAIM-TARGET-ABSENT",
                subject=name,
                reason=(
                    f"{name} does not exist yet, so no claim in it has been checked. "
                    "This is not a pass; it becomes enforcing the moment the file lands"
                ),
            )

    for path in documents:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        report.examine()
        lines = text.splitlines()
        where = rel(path, root)
        for claim in claim_rules:
            for pattern in claim.patterns:
                for match in pattern.finditer(text):
                    lineno = text.count("\n", 0, match.start()) + 1
                    context = _context(lines, lineno)
                    if any(a.search(context) for a in claim.allow_if):
                        report.exempt(
                            rule=f"GREP-CLAIM-{claim.rule_id}",
                            subject=f"{where}:{lineno}",
                            reason="matched an allow_if context declared for this claim",
                        )
                        continue
                    if GLOBAL_NEGATION.search(context):
                        report.exempt(
                            rule=f"GREP-CLAIM-{claim.rule_id}",
                            subject=f"{where}:{lineno}",
                            reason=(
                                "the surrounding line disclaims rather than asserts; "
                                "recorded so the exemption is arguable rather than invisible"
                            ),
                        )
                        continue
                    report.violate(
                        rule=f"GREP-CLAIM-{claim.rule_id}",
                        subject=f"{where}:{lineno}",
                        detail=f"{claim.description} — matched {match.group(0).strip()!r}",
                        authority=claim.source,
                    )
    return report


def _context(lines: Sequence[str], lineno: int) -> str:
    index = lineno - 1
    start = max(0, index - 1)
    end = min(len(lines), index + 2)
    return " ".join(lines[start:end])


# ---------------------------------------------------------------------------
# All of them
# ---------------------------------------------------------------------------


def run_all_greps(repo_root: Path) -> Report:
    report = Report(enforcement=Enforcement.GREP)
    report.merge(scan_retry_imports(repo_root, repo_root=repo_root))
    report.merge(scan_retry_dependencies(repo_root, repo_root=repo_root))
    report.merge(scan_sampling_params(repo_root, repo_root=repo_root))
    report.merge(scan_metric_labels(repo_root, repo_root=repo_root))
    report.merge(scan_must_not_claim(repo_root))
    return report
