# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""This domain's CI greps, and the planted violations that prove they work.

Four bans, none of them stylistic:

* **no ``tenacity`` / ``backoff`` / ``retrying``** — §16: ``40001`` is the only
  retryable SQLSTATE, and a blanket retry helper cannot tell a serialization
  restart from a gate refusal;
* **no ``temperature`` / ``top_p`` / ``top_k``** — A6: they 400 on this Claude
  generation, and the honest claim was always replayability, never
  reproducibility of model output;
* **no per-signer dimension in any metric label** — §12: ``signer_sub`` is a span
  attribute, never a metric label, and the legal rule and the cardinality rule
  are the same rule;
* **the §11.7 must-not-claim strings are absent from README / deck / VERIFY.md.**

Every grep in this module is run twice: once over the real repository (which must
be clean), and once over a temporary tree with the violation deliberately planted
(which must fail). A grep nobody has watched catch something is a grep that is
probably matching nothing at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from mainline_boundary.greps import (
    SAMPLING_EXEMPT_PREFIXES,
    SAMPLING_SCOPE_NOTE,
    ClaimRule,
    claim_documents,
    load_claim_rules,
    sampling_sites,
    scan_metric_labels,
    scan_must_not_claim,
    scan_retry_dependencies,
    scan_retry_imports,
    scan_sampling_params,
)
from mainline_boundary.testkit import assert_enforced, assert_violates

#: The one directory the sampling ban is exempt for, named once so the assertion
#: that it is the ONLY one reads as a single fact.
_CORPUS_RENDER_PREFIX = "verticals/mainline/packages/mainline-corpus/src/mainline_corpus/render"

# ---------------------------------------------------------------------------
# 1. Retry helpers
# ---------------------------------------------------------------------------


def test_repository_imports_no_retry_helper(repo_root: Path) -> None:
    assert_enforced(scan_retry_imports(repo_root, repo_root=repo_root))


def test_repository_declares_no_retry_dependency(repo_root: Path) -> None:
    assert_enforced(scan_retry_dependencies(repo_root, repo_root=repo_root))


@pytest.mark.parametrize(
    "source",
    [
        "import tenacity\n",
        "from tenacity import retry\n",
        "import backoff\n",
        "from retrying import retry\n",
    ],
)
def test_planted_retry_import_is_caught(tmp_path: Path, source: str) -> None:
    (tmp_path / "gate_client.py").write_text(source, encoding="utf-8")
    assert_violates(scan_retry_imports(tmp_path), "GREP-RETRY-IMPORT")


def test_planted_retry_dependency_is_caught(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\ndependencies = ["tenacity>=9.0"]\n',
        encoding="utf-8",
    )
    assert_violates(scan_retry_dependencies(tmp_path), "GREP-RETRY-DEPENDENCY")


def test_a_comment_mentioning_tenacity_is_not_a_violation(tmp_path: Path) -> None:
    """The ban is on the import, not on the word.

    ``verticals/mainline/packages/mainline-domain/pyproject.toml`` documents the
    absence of a retry helper in a comment, and a text grep would fail on it.
    That is how a check gets disabled: everybody learns to ignore it.
    """
    (tmp_path / "note.py").write_text(
        "# Deliberately absent: tenacity/backoff/retrying. 40001 is the only\n"
        "# retryable SQLSTATE.\nVALUE = 1\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n'
        "# Also absent: tenacity (see above)\ndependencies = []\n",
        encoding="utf-8",
    )
    report = scan_retry_imports(tmp_path)
    report.merge(scan_retry_dependencies(tmp_path))
    assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# 2. Sampling parameters
# ---------------------------------------------------------------------------


def test_no_request_builder_sets_a_sampling_parameter(repo_root: Path) -> None:
    assert_enforced(scan_sampling_params(repo_root, repo_root=repo_root))


def test_planted_temperature_kwarg_is_caught(tmp_path: Path) -> None:
    package = tmp_path / "packages" / "mainline-agentkit" / "src" / "mainline_agentkit"
    package.mkdir(parents=True)
    (package / "transport.py").write_text(
        "def build(client, body):\n"
        "    return client.invoke_model(modelId=body.model, temperature=0.0)\n",
        encoding="utf-8",
    )
    assert_violates(scan_sampling_params(tmp_path), "GREP-SAMPLING-PARAM")


def test_planted_sampling_dict_key_is_caught(tmp_path: Path) -> None:
    package = tmp_path / "packages" / "mainline-agentkit" / "src" / "mainline_agentkit"
    package.mkdir(parents=True)
    (package / "body.py").write_text(
        'BODY = {"anthropic_version": "bedrock-2023-05-31", "top_p": 1, "top_k": 5}\n',
        encoding="utf-8",
    )
    report = scan_sampling_params(tmp_path)
    assert_violates(report, "GREP-SAMPLING-PARAM")
    assert len(report.violations_for("GREP-SAMPLING-PARAM")) == 2


def test_planted_sampling_subscript_assignment_is_caught(tmp_path: Path) -> None:
    package = tmp_path / "packages" / "mainline-agentkit" / "src" / "mainline_agentkit"
    package.mkdir(parents=True)
    (package / "sneaky.py").write_text(
        "def build(body: dict) -> dict:\n    body['temperature'] = 0\n    return body\n",
        encoding="utf-8",
    )
    assert_violates(scan_sampling_params(tmp_path), "GREP-SAMPLING-PARAM")


def test_a_process_temperature_string_is_not_a_violation(tmp_path: Path) -> None:
    """Our corpus is seal-face high-temperature alarms. A text grep is useless here."""
    package = tmp_path / "packages" / "mainline-domain" / "src" / "mainline_domain"
    package.mkdir(parents=True)
    (package / "lexicon.py").write_text(
        'TERMS = ["temperature", "top_k"]\n'
        'ALARM = "seal-face high-temperature alarm set at 150 degrees C"\n',
        encoding="utf-8",
    )
    assert scan_sampling_params(tmp_path).ok


# --- the 2026-08-10 narrowing, and the proof it did not blind the rule ------
#
# Run 31427116607 reported `examined=3203 violations=2`, and both violations were
# physical-dimension tables: `DIMENSION_SYMBOL` in trappoint-recall's lexical
# units and `_LABEL_REPRESENTATIVES` in mainline-domain's quantity units. The
# three tests below are one argument in three parts: the tables are clean, a real
# request builder is still caught, and the two are caught/cleared IN THE SAME
# FILE — because a rule that only works when the two shapes live apart is a rule
# that has not been separated from the token, only moved away from it.

_DIMENSION_TABLE = (
    "from typing import Final\n\n"
    "DIMENSION_SYMBOL: Final[dict[str, str]] = {\n"
    '    "ratio": "frac",\n'
    '    "lel": "lel",\n'
    '    "uel": "uel",\n'
    '    "pressure": "pa",\n'
    '    "temperature": "k",\n'
    '    "velocity": "m_s",\n'
    "}\n\n"
    "_LABEL_REPRESENTATIVES: Final[dict[str, str]] = {\n"
    '    "pressure": "pascal",\n'
    '    "temperature": "kelvin",\n'
    '    "frequency": "hertz",\n'
    "}\n"
)

_REAL_REQUEST_BUILDER = (
    "\n\n"
    "def render(client, node, model_id):\n"
    "    return client.converse(\n"
    "        modelId=model_id,\n"
    '        messages=[{"role": "user", "content": [{"text": node.text}]}],\n'
    "        temperature=0.0,\n"
    '        inferenceConfig={"temperature": 0.0, "topP": 1.0, "maxTokens": 900},\n'
    "    )\n"
)


def _domain_module(tmp_path: Path, source: str) -> Path:
    package = tmp_path / "packages" / "trappoint-recall" / "src" / "trappoint_recall"
    package.mkdir(parents=True, exist_ok=True)
    module = package / "units.py"
    module.write_text(source, encoding="utf-8")
    return module


def test_a_physical_dimension_table_is_not_a_request_builder(tmp_path: Path) -> None:
    """The two measured false positives, reproduced verbatim in shape, must be clean.

    Both real files sit in an industrial-safety domain that also carries
    ``pressure``, ``lel`` and ``uel``. Neither may acquire an exemption to go
    green: the instrument was wrong, not the code it was pointed at.
    """
    _domain_module(tmp_path, _DIMENSION_TABLE)
    report = scan_sampling_params(tmp_path)
    assert report.ok, report.summary()
    assert report.examined == 1, report.summary()
    assert report.exemptions == [], report.summary()


def test_a_planted_temperature_on_a_real_request_builder_is_still_caught(
    tmp_path: Path,
) -> None:
    """PL-2 for the narrowing: the ban must still be able to say no.

    Three sites, three different reasons — a keyword argument on ``converse``
    (a model transport), a dict key inside the ``inferenceConfig`` block that
    stands beside ``maxTokens``, and ``topP`` beside it — and the dimension table
    sitting in the same module is still cleared.
    """
    source = _DIMENSION_TABLE + _REAL_REQUEST_BUILDER
    _domain_module(tmp_path, source)
    numbered = list(enumerate(source.splitlines(), start=1))
    builder_lines = {n for n, line in numbered if "temperature=0.0" in line or "topP" in line}
    table_lines = {n for n, line in numbered if '"temperature": "' in line}
    assert len(builder_lines) == 2 and len(table_lines) == 2, (builder_lines, table_lines)

    report = scan_sampling_params(tmp_path)
    assert_violates(report, "GREP-SAMPLING-PARAM")
    reported = {int(v.subject.rsplit(":", 1)[1]) for v in report.violations}
    assert reported == builder_lines, report.summary()
    assert reported.isdisjoint(table_lines), report.summary()
    keys = sorted(v.detail.split("'")[1] for v in report.violations)
    assert keys == ["temperature", "temperature", "topP"], report.summary()
    assert all("request builder" in v.detail for v in report.violations)
    reasons = " ".join(v.detail for v in report.violations)
    assert "model transport" in reasons and "standing beside 'maxTokens'" in reasons


#: The repository's own Bedrock body builder. A rule proved only against fixtures
#: its own author wrote is proved against that author's idea of a request; this
#: file is the shape the product actually sends.
_REAL_BUILDER = "packages/mainline-agentkit/src/mainline_agentkit/fallback_toolform.py"
_REAL_BUILDER_ANCHOR = '"anthropic_version": ANTHROPIC_VERSION,'


def test_the_rule_fires_on_this_repositorys_own_request_builder(
    repo_root: Path, tmp_path: Path
) -> None:
    """Plant a sampling parameter into a copy of the real agentkit body builder.

    Copied verbatim, mutated by one line, and the rule must report that line and
    no other — in a 224-line module that mentions ``tools``, ``schema`` and
    ``thinking``. This is the assertion that would catch a narrowing which had
    quietly stopped measuring the thing A6 is about.
    """
    source = (repo_root / _REAL_BUILDER).read_text(encoding="utf-8")
    assert _REAL_BUILDER_ANCHOR in source, (
        f"{_REAL_BUILDER} no longer contains {_REAL_BUILDER_ANCHOR!r}. Re-point this "
        "test at the current body builder; do not delete it — it is the only place "
        "the A6 ban is proved against production code rather than a fixture."
    )
    lines: list[str] = []
    planted = 0
    for line in source.splitlines():
        lines.append(line)
        if _REAL_BUILDER_ANCHOR in line and not planted:
            lines.append('        "temperature": 0.0,')
            planted = len(lines)

    target = tmp_path / _REAL_BUILDER
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = scan_sampling_params(tmp_path)
    reported = sorted(int(v.subject.rsplit(":", 1)[1]) for v in report.violations)
    assert reported == [planted], report.summary()
    assert "anthropic_version" in report.violations[0].detail, report.summary()


def test_the_two_measured_false_positives_are_clean_without_an_exemption(
    repo_root: Path,
) -> None:
    """The real files, at their real paths, and neither is exempt from anything."""
    measured = (
        "packages/trappoint-recall/src/trappoint_recall/lexical/units.py",
        "verticals/mainline/packages/mainline-domain/src/mainline_domain/quantity/units.py",
    )
    exempt_prefixes = [prefix for prefix, _ in SAMPLING_EXEMPT_PREFIXES]
    for relative in measured:
        path = repo_root / relative
        assert path.is_file(), f"{relative} moved; re-measure before editing this test"
        assert not any(relative.startswith(prefix) for prefix in exempt_prefixes), (
            f"{relative} acquired an exemption. The rule was narrowed so that it would "
            "not need one; an exemption here would put the false positive back, silently."
        )
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert sampling_sites(tree) == [], relative
        assert "temperature" in path.read_text(encoding="utf-8"), (
            f"{relative} no longer contains the word this test exists to clear"
        )


def test_the_corpus_renderer_exemption_is_declared_and_reported(repo_root: Path) -> None:
    """The one hole in the sampling ban, visible rather than silent — and sized."""
    prefixes = [p for p, _ in SAMPLING_EXEMPT_PREFIXES]
    assert prefixes == [_CORPUS_RENDER_PREFIX]
    for _, reason in SAMPLING_EXEMPT_PREFIXES:
        assert "A6" in reason and "merge path" in reason
    report = scan_sampling_params(repo_root, repo_root=repo_root)
    for exemption in report.exemptions:
        assert exemption.reason, exemption
        assert "Withheld here:" in exemption.reason, exemption
    withheld = [e for e in report.exemptions if "Withheld here: nothing" not in e.reason]
    assert [e.subject for e in withheld] == [f"{_CORPUS_RENDER_PREFIX}/bedrock.py"], "\n".join(
        str(e) for e in report.exemptions
    )
    assert "temperature:" in withheld[0].reason and "topP:" in withheld[0].reason


def test_the_report_states_the_scope_it_measured(repo_root: Path) -> None:
    """A narrowed rule that does not say what it narrowed to is a rule nobody can audit."""
    report = scan_sampling_params(repo_root, repo_root=repo_root)
    assert any("REQUEST-BUILDER CONTEXT" in note for note in report.notes), report.notes
    assert SAMPLING_SCOPE_NOTE in report.summary()


# ---------------------------------------------------------------------------
# 3. Metric labels
# ---------------------------------------------------------------------------


def test_no_metric_carries_a_per_signer_dimension(repo_root: Path) -> None:
    assert_enforced(scan_metric_labels(repo_root, repo_root=repo_root))


def test_planted_signer_metric_label_is_caught(tmp_path: Path) -> None:
    (tmp_path / "telemetry.py").write_text(
        "def emit(meter, value):\n"
        '    counter = meter.create_counter("gate.refusals")\n'
        '    counter.add(value, attributes={"site_code": "MRD", "signer_sub": "abc"})\n',
        encoding="utf-8",
    )
    assert_violates(scan_metric_labels(tmp_path), "GREP-METRIC-SIGNER-LABEL")


def test_planted_prometheus_labelnames_is_caught(tmp_path: Path) -> None:
    (tmp_path / "prom.py").write_text(
        "from prometheus_client import Counter\n\n"
        'REFUSALS = Counter("gate_refusals", "refusals", labelnames=["site_code", "signer"])\n',
        encoding="utf-8",
    )
    assert_violates(scan_metric_labels(tmp_path), "GREP-METRIC-SIGNER-LABEL")


def test_planted_cloudwatch_dimension_is_caught(tmp_path: Path) -> None:
    (tmp_path / "cw.py").write_text(
        "def put(client):\n"
        "    client.put_metric_data(\n"
        '        Namespace="mainline",\n'
        '        MetricData=[{"MetricName": "merges", "Dimensions": '
        '[{"Name": "permit_id", "Value": "P-1"}]}],\n'
        "    )\n",
        encoding="utf-8",
    )
    assert_violates(scan_metric_labels(tmp_path), "GREP-METRIC-HIGH-CARDINALITY-LABEL")


def test_a_span_attribute_is_not_a_metric_label(tmp_path: Path) -> None:
    """§12 explicitly PERMITS permit_id and signer_sub as span attributes.

    Flagging them there would be flatly wrong, and a check that is wrong in the
    sanctioned case is a check people route around.
    """
    (tmp_path / "tracing.py").write_text(
        "def emit(tracer):\n"
        '    with tracer.start_as_current_span("gate.merge", attributes={\n'
        '        "mainline.permit_id": "P-1", "signer_sub": "abc"}) as span:\n'
        "        return span\n",
        encoding="utf-8",
    )
    assert scan_metric_labels(tmp_path).ok


# ---------------------------------------------------------------------------
# 4. The must-not-claim list
# ---------------------------------------------------------------------------


def test_claim_rules_load_and_cover_the_architecture_list() -> None:
    rules = load_claim_rules()
    ids = {r.rule_id for r in rules}
    for expected in (
        "RLS-VS-ROGUE-ADMIN",
        "OPEN-SOURCE-AGENTIC-MEMORY-LAYER",
        "MATERIALISES-A-BLOCKING-CHECK",
        "NOT-APPLICABLE-CONSTRUCTOR",
        "MULTI-MONTH-AS-OF-SYSTEM-TIME",
        "BIT-IDENTICAL-ANN-REPLAY",
        "UPSTREAM-SKILLS-MERGE",
        "IDENTITY-PROOFING",
        "ENCLAVE-ATTESTED-SIGNING",
    ):
        assert expected in ids, f"§11.7 entry {expected} is not encoded"
    for rule in rules:
        assert rule.patterns, f"{rule.rule_id} encodes no pattern"
        assert rule.description, f"{rule.rule_id} has no description"


def test_outward_facing_documents_make_no_forbidden_claim(repo_root: Path) -> None:
    documents = claim_documents(repo_root)
    assert documents, "no outward-facing document was found to scan"
    assert_enforced(scan_must_not_claim(repo_root))


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        (
            "MAINLINE is an open-source agentic memory layer for industry.",
            "GREP-CLAIM-OPEN-SOURCE-AGENTIC-MEMORY-LAYER",
        ),
        (
            "The gate materialises a blocking check for each precursor.",
            "GREP-CLAIM-MATERIALISES-A-BLOCKING-CHECK",
        ),
        (
            "Sign it off as not_applicable and move on.",
            "GREP-CLAIM-NOT-APPLICABLE-CONSTRUCTOR",
        ),
        (
            "We replay any ANN result bit-identical, years later.",
            "GREP-CLAIM-BIT-IDENTICAL-ANN-REPLAY",
        ),
        (
            "Our skill was merged upstream by CockroachDB.",
            "GREP-CLAIM-UPSTREAM-SKILLS-MERGE",
        ),
        (
            "RLS stops a rogue admin reading another site's records.",
            "GREP-CLAIM-RLS-VS-ROGUE-ADMIN",
        ),
        (
            "Query AS OF SYSTEM TIME eighteen months back for the original clause.",
            "GREP-CLAIM-MULTI-MONTH-AS-OF-SYSTEM-TIME",
        ),
        (
            "Every signature is enclave-attested end to end.",
            "GREP-CLAIM-ENCLAVE-ATTESTED-SIGNING",
        ),
    ],
)
def test_planted_forbidden_claim_is_caught(tmp_path: Path, text: str, rule_id: str) -> None:
    (tmp_path / "README.md").write_text(f"# MAINLINE\n\n{text}\n", encoding="utf-8")
    assert_violates(scan_must_not_claim(tmp_path), rule_id)


def test_a_disclaimer_is_not_a_claim(tmp_path: Path) -> None:
    """§11.7's own sentences must be writable in the README they govern."""
    (tmp_path / "README.md").write_text(
        "# MAINLINE\n\n"
        "We do not claim RLS is a defence against a rogue admin.\n"
        "We never claim bit-identical replay of an ANN result.\n"
        "There is no judicial precedent for WebAuthn-signed safety records.\n",
        encoding="utf-8",
    )
    report = scan_must_not_claim(tmp_path)
    assert report.ok, report.summary()
    assert report.exemptions, (
        "the disclaimers matched patterns and were excused, so the excuses must appear "
        "in the report; an invisible exemption is a hole"
    )


def test_a_missing_target_file_is_a_skip_not_a_pass(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# MAINLINE\n", encoding="utf-8")
    report = scan_must_not_claim(tmp_path)
    assert any(s.subject == "VERIFY.md" for s in report.skips), report.summary()


def test_a_missing_readme_is_a_violation(tmp_path: Path) -> None:
    assert_violates(scan_must_not_claim(tmp_path), "GREP-CLAIM-NO-README")


def test_custom_rule_shape_is_honoured(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# MAINLINE\n\nWe ship telepathy.\n", encoding="utf-8")
    import re

    rule = ClaimRule(
        rule_id="TELEPATHY",
        description="we do not ship telepathy",
        source="test",
        patterns=(re.compile("telepathy", re.IGNORECASE),),
        allow_if=(),
    )
    assert_violates(scan_must_not_claim(tmp_path, rules=[rule]), "GREP-CLAIM-TELEPATHY")
