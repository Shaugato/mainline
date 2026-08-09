# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CAPABILITY SWITCHES — ruling `D5`, and `PL-3` as an exit code.

A capability under a dated `GT-*` check is a **render-time switch, never a runtime
branch**. The claim that buys is specific: both branches of every switch are committed,
readable SQL, so the fallback is something a reviewer reads rather than something a
reviewer trusts, and no cluster ever discovers at runtime which branch it got.

Holding that requires four refusals, and the third is the one that looks like
over-engineering until it fires:

* no attestation at all → refuse. A missing measurement is not a permissive one.
* ``UNKNOWN`` → refuse. `PL-3` forbids a dated path on an unproven capability, and a
  default is exactly how an unproven capability reaches production.
* a template declares ``{# @capability X #}`` that the attestation does not answer →
  refuse. An undeclared-in-the-ground-truth branch is a branch nobody audited.
* the binding selects a branch the measurement did not authorise → refuse. The binding
  does not overrule the measurement; that is what "ground truth" means.

And one acceptance, which is the half that proves the switch is a switch:
``FALLBACK-SELECTED`` renders the *other* branch, in full, into a committed file.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from trappoint_sql.attestation import load_attestation
from trappoint_sql.binding import load_binding
from trappoint_sql.errors import AttestationRefused
from trappoint_sql.render import render_binding

# A template whose two branches are BOTH committed SQL. The `@capability` pragma is what
# makes the renderer demand an answer before either branch exists.
SWITCHED = """\
{# @capability stored_digest #}
-- @file 9100_dedupe.sql
{{ header(file='9100_dedupe.sql', title='the dedupe key, both branches committed',
          rationale='GT-13 decides which branch is emitted; both are readable SQL.',
          mi=['MI09'], i=['I01']) }}
{% if capabilities.stored_digest == 'stored' %}
--
-- GT-13 PASS: the server computes the key, so the inserter cannot choose its identity.

CREATE TABLE {{ binding.schema }}.dedupe (
  a STRING NOT NULL,
  b BYTES AS (digest(a, 'sha256')) STORED,
  CONSTRAINT pk_dedupe PRIMARY KEY (a)
);
{% else %}
--
-- GT-13 FALLBACK-SELECTED: a plain BYTES column with a length CHECK. The sentence "the
-- server computes the key" is withdrawn in the commit that selects this branch.

CREATE TABLE {{ binding.schema }}.dedupe (
  a STRING NOT NULL,
  b BYTES NOT NULL,
  CONSTRAINT dedupe_sized CHECK (length(b) = 32),
  CONSTRAINT pk_dedupe PRIMARY KEY (a)
);
{% endif %}
"""

UNDECLARED = """\
{# @capability vector_prefix_in #}
-- @file 9101_unknown.sql
{{ header(file='9101_unknown.sql', title='branches on a capability nobody measured',
          rationale='Exists to be refused.', mi=['MI20'], i=['I06']) }}

CREATE TABLE {{ binding.schema }}.probe (x INT8 NOT NULL PRIMARY KEY);
"""

INERT = """\
-- @file 9102_inert.sql
{{ header(file='9102_inert.sql', title='no capability at all',
          rationale='Renders whatever the attestation says.', mi=['MI01'], i=['I01']) }}

CREATE TABLE {{ binding.schema }}.inert (x INT8 NOT NULL PRIMARY KEY);
"""


def attestation_path(root: Path) -> Path:
    """Where ``fake_root`` puts the ground truth."""
    return root / "attest" / "g1-attestation.json"


def retune(root: Path, name: str, **changes: object) -> None:
    """Rewrite one capability answer in the throwaway attestation."""
    path = attestation_path(root)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["capabilities"][name].update(changes)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


# ── the four refusals ───────────────────────────────────────────────────────────────


def test_render_refuses_without_any_attestation(
    fake_root: Path,
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    binding = load_binding(write_binding())
    attestation_path(fake_root).unlink()
    templates = write_templates([("9102_inert.sql.j2", INERT)])
    with pytest.raises(AttestationRefused) as excinfo:
        render_binding(binding, templates)
    message = str(excinfo.value)
    assert "g1-attestation.json" in message
    assert "not a permissive one" in message, "the message must say why absence is not a default"


def test_render_refuses_an_unknown_capability(
    fake_root: Path,
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    retune(fake_root, "stored_digest", status="UNKNOWN")
    binding = load_binding(write_binding())
    templates = write_templates([("9100_dedupe.sql.j2", SWITCHED)])
    with pytest.raises(AttestationRefused) as excinfo:
        render_binding(binding, templates)
    message = str(excinfo.value)
    assert "stored_digest" in message
    assert "GT-13" in message, "the operator must be told WHICH ground-truth check to run"
    assert "There is no default" in message


def test_render_refuses_a_capability_the_ground_truth_does_not_answer(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # A template may not branch on something nobody measured. This is the refusal that
    # keeps `unmeasured.known_open` in the attestation from quietly becoming a switch.
    binding = load_binding(write_binding())
    templates = write_templates([("9101_unknown.sql.j2", UNDECLARED)])
    with pytest.raises(AttestationRefused) as excinfo:
        render_binding(binding, templates)
    assert "vector_prefix_in" in str(excinfo.value)
    assert "ruling D5" in str(excinfo.value)


def test_render_refuses_when_the_binding_overrules_the_measurement(
    fake_root: Path,
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # The measurement says the fallback; the binding asks for the primary branch. Emitting
    # it would produce SQL the measurement says will not run.
    retune(fake_root, "stored_digest", status="FALLBACK-SELECTED", selects="client_computed")
    binding = load_binding(write_binding())
    templates = write_templates([("9102_inert.sql.j2", INERT)])
    with pytest.raises(AttestationRefused) as excinfo:
        render_binding(binding, templates)
    message = str(excinfo.value)
    assert "does not overrule the measurement" in message
    assert "client_computed" in message


# ── the acceptance that proves it is a switch ───────────────────────────────────────


def test_fallback_selected_renders_the_other_branch_in_full(
    fake_root: Path,
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    retune(fake_root, "stored_digest", status="FALLBACK-SELECTED", selects="client_computed")
    swap = ('stored_digest = "stored"', 'stored_digest = "client_computed"')
    binding = load_binding(write_binding(swap))
    templates = write_templates([("9100_dedupe.sql.j2", SWITCHED)])
    sql = render_binding(binding, templates).by_name["9100_dedupe.sql"].text
    assert "CHECK (length(b) = 32)" in sql, "the fallback branch must be COMMITTED SQL, not a stub"
    assert "STORED" not in sql
    assert "FALLBACK-SELECTED" in sql, "a rendered fallback must say which measurement selected it"


def test_pass_renders_the_primary_branch(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    binding = load_binding(write_binding())
    templates = write_templates([("9100_dedupe.sql.j2", SWITCHED)])
    sql = render_binding(binding, templates).by_name["9100_dedupe.sql"].text
    assert "digest(a, 'sha256')) STORED" in sql
    assert "length(b) = 32" not in sql


def test_the_switch_is_resolved_before_any_sql_exists(
    fake_root: Path,
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # Order of enforcement is fixed and load-bearing: an undecided capability must not
    # produce SQL that is then thrown away, because a half-written output directory is a
    # tree `trappoint migrate` would apply without complaint.
    retune(fake_root, "triggerdef", status="UNKNOWN")
    binding = load_binding(write_binding())
    templates = write_templates([("9102_inert.sql.j2", INERT)])
    with pytest.raises(AttestationRefused):
        render_binding(binding, templates)
    assert list(binding.output_dir.iterdir()) == []


# ── the attestation document itself ─────────────────────────────────────────────────


def test_an_answer_without_a_cluster_is_not_evidence(fake_root: Path) -> None:
    # "It worked on my laptop" and "it worked on Cloud Basic" are different claims, and
    # the local node is known to diverge from Cloud on gc.ttlseconds.
    path = attestation_path(fake_root)
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["cluster"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AttestationRefused) as excinfo:
        load_attestation(path)
    assert "which cluster" in str(excinfo.value)


def test_an_answer_must_name_its_ground_truth_gate(fake_root: Path) -> None:
    path = attestation_path(fake_root)
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["capabilities"]["stored_digest"]["gate"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AttestationRefused) as excinfo:
        load_attestation(path)
    assert "GT-13" in str(excinfo.value), "the message should show the shape it wanted"


@pytest.mark.parametrize("status", ["pass", "Pass", "OK", "", "TRUE"])
def test_only_the_three_documented_statuses_are_legal(fake_root: Path, status: str) -> None:
    # No case-insensitive match, no truthiness. A status this module does not recognise
    # is refused rather than treated as an answer.
    retune(fake_root, "stored_digest", status=status)
    with pytest.raises(AttestationRefused) as excinfo:
        load_attestation(attestation_path(fake_root))
    assert "legal values are" in str(excinfo.value)


def test_the_committed_attestation_answers_both_switches(repo_root_path: Path) -> None:
    # The real one. Both capabilities the bindings declare must be answered, or no
    # vertical in this repository can render at all.
    attestation = load_attestation(repo_root_path / "packages/trappoint-sql/g1-attestation.json")
    for name in ("stored_digest", "triggerdef"):
        answer = attestation.require(name)
        assert answer.answered
        assert answer.measured_on, f"{name} claims no substrate it was measured on"
        assert answer.gate.startswith("GT-")
