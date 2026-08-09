# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The two real bindings, and the foundation SQL they produce (migrations 0001-0023).

Two claims are under test and they are different claims.

**The substrate claim.** One template set renders two bindings that share no schema, no
output directory, no outbox decision, and no role name in any slot a binding is allowed
to name. A template engine with an audience of one proves nothing about whether the
templates read the binding or hard-code the vertical, which is why the reference
vertical is a first-class deliverable and is tested here beside MAINLINE rather than as
a fixture underneath it.

The qualifier on "role name" is measured, not hedged: exactly two of the nine names DO
coincide (``agent_recaller``, ``quality_assurance``), because
``vertical.schema.json`` 1.0 closes ``[roles]`` with ``additionalProperties: false`` and
has no key for the slots that carry them, and §11.2's default for both is a
cluster-global constant. ``test_the_two_bindings_share_no_schema_role_or_output_directory``
pins that set, so narrowing it (the spec grows the keys) or widening it (someone drops
an override) is a red test rather than a quiet change of meaning.

**The foundation claim.** The rendered band 0001-0023 says specific things about the
world, and the specific things are the product:

* the clearance lattice is 21 rows out of a 24-cell product, and the three missing cells
  are the mechanism — a missing row in a foreign-key target refuses, and the refusal
  names ``clearance_legal`` rather than an application rule;
* the transition edge set is 9 edges per subject kind, identical across kinds, with
  nothing transitioning INTO ``draft`` and nothing leaving ``merged`` back into the gate;
* ``agent_recaller`` receives no write privilege anywhere in the band (finding `S1`).

These are read out of the COMMITTED files, not out of the render. A test that only read
the render would stay green while the committed tree said something else, and the
committed tree is what ``trappoint migrate up`` applies.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from trappoint_sql.binding import load_binding
from trappoint_sql.model import Binding
from trappoint_sql.render import check_units, render_binding, stem_collisions

BINDINGS = ("verticals/mainline/vertical.toml", "packages/trappoint-sql/refvertical/vertical.toml")

# ARCHITECTURE.md §5.0: the clearance lattice is the 4x6 product MINUS three cells.
VIRULENCE = ("routine", "serious", "blood_major", "blood_fatal")
DISPOSITION_KIND = (
    "applied",
    "mitigated",
    "mechanism_absent",
    "escalated",
    "accept_residual",
    "emergency_override",
)
DELIBERATELY_ABSENT = frozenset(
    {
        ("blood_fatal", "mechanism_absent"),
        ("blood_fatal", "accept_residual"),
        ("blood_major", "accept_residual"),
    }
)

# ARCHITECTURE.md §5.0: the same nine edges for every subject kind.
EDGES = frozenset(
    {
        ("draft", "checks_materialised"),
        ("draft", "abandoned"),
        ("checks_materialised", "checks_materialised"),
        ("checks_materialised", "dispositioned"),
        ("dispositioned", "checks_materialised"),
        ("dispositioned", "merged"),
        ("merged", "suspended"),
        ("merged", "closed"),
        ("suspended", "closed"),
    }
)

_CITATION = re.compile(r"\b(?:MI\d{2}|I\d{2})\b")
_CLEARANCE_ROW = re.compile(r"^\s*\('(?P<virulence>\w+)',\s*'(?P<kind>\w+)',", re.M)
_EDGE_ROW = re.compile(r"^\s*\('(?P<kind>\w+)',\s*'(?P<frm>\w+)',\s*'(?P<to>\w+)'\)", re.M)
_LITERAL = re.compile(r"'(?:[^']|'')*'")


def executable(sql: str) -> str:
    """Strip comments and blank the interior of string literals.

    Both halves are load-bearing when a test asks "does this file GRANT anything?".
    Migration ``0009x`` is a ``COMMENT ON SCHEMA`` whose literal spells out the whole
    separation covenant — including the sentence "``agent_recaller`` holds no INSERT on
    any obligation relation". A scan that read the literal would find the words ``GRANT``
    and ``INSERT`` in a file that grants nothing, and the covenant's own text would fail
    the test asserting the covenant. Likewise a header comment that names the statement
    it introduces (``CREATE TYPE …``) is prose, not a statement.
    """
    body = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return _LITERAL.sub("''", body)


@pytest.fixture(params=BINDINGS, ids=("mainline", "trappoint-ref"))
def binding(request: pytest.FixtureRequest, repo_root_path: Path) -> Binding:
    """Each real binding in turn."""
    return load_binding(repo_root_path / request.param)


def committed(binding_obj: Binding, name: str) -> str:
    """Read one committed migration out of the binding's output directory."""
    return (binding_obj.output_dir / name).read_text(encoding="utf-8")


# ── the zero-diff assertion, which is the worker's completion test ──────────────────


def test_render_check_is_a_zero_diff_no_op(binding: Binding, templates_dir: Path) -> None:
    result = render_binding(binding, templates_dir)
    findings = check_units(result)
    assert findings == [], "\n".join(f.render() for f in findings)


def test_the_output_directory_holds_no_colliding_migration_versions(binding: Binding) -> None:
    # A zero-diff tree the migration runner refuses to discover is a green assertion
    # about a dead deploy (MR-6).
    collisions = stem_collisions(binding.output_dir)
    assert collisions == [], f"{collisions}"


# ── the substrate claim: two bindings that agree on nothing but the templates ───────


def test_the_two_bindings_share_no_schema_role_or_output_directory(repo_root_path: Path) -> None:
    mainline = load_binding(repo_root_path / BINDINGS[0])
    reference = load_binding(repo_root_path / BINDINGS[1])
    assert mainline.vertical.schema != reference.vertical.schema
    assert mainline.output_dir != reference.output_dir
    assert mainline.emit_outbox is True
    # Ruling D9: the substrate must not hard-depend on a changefeed table it does not own.
    assert reference.emit_outbox is False

    # Every slot a binding is ALLOWED to name must differ, or the reference vertical
    # would prove nothing about whether the templates read the binding.
    overridable = {r.slot for r in mainline.roles if r.overridable}
    for slot in sorted(overridable):
        assert mainline.role(slot) != reference.role(slot), f"{slot!r} renders identically"

    # The three that COINCIDE are exactly the three `vertical.schema.json` 1.0 has no key
    # for, and two of those three are cluster-global constants in ARCHITECTURE.md §11.2
    # rather than schema-scoped names — so coinciding is correct for them, and the third
    # (`auditor`) is schema-scoped and therefore differs anyway. Pinned here because the
    # moment the spec grows the missing keys, this set must shrink deliberately rather
    # than by accident.
    shared = {r.name for r in mainline.roles} & {r.name for r in reference.roles}
    assert shared == {"agent_recaller", "quality_assurance"}
    assert mainline.role("auditor") != reference.role("auditor")


def test_mainline_renders_the_nine_role_names_of_the_architecture_matrix(
    repo_root_path: Path,
) -> None:
    # ARCHITECTURE.md §11.2, reproduced exactly — by DERIVATION, with no table of
    # vertical knowledge in the substrate. Three of the nine (`agent_recaller`,
    # `mainline_auditor`, `quality_assurance`) cannot be named by a binding at all,
    # because vertical.schema.json 1.0 has no key for them.
    binding_obj = load_binding(repo_root_path / BINDINGS[0])
    assert [r.name for r in binding_obj.roles] == [
        "mainline_migrator",
        "mainline_owner",
        "agent_gate",
        "agent_projector",
        "agent_recaller",
        "svc_disposition",
        "mainline_auditor",
        "auditor_ro",
        "quality_assurance",
    ]
    assert binding_obj.role("owner") == "mainline_owner"
    (owner,) = [r for r in binding_obj.roles if r.slot == "owner"]
    assert owner.nologin, "the schema owner must be unassumable"


def test_every_authority_relation_of_the_reference_vertical_has_ddl(
    repo_root_path: Path,
) -> None:
    # THE REGRESSION TEST FOR THE GAP THIS WORKER FOUND. The reference binding named
    # `trappoint_ref.clause_blame_current` as an authority relation while no file created
    # it: the Authority Source Contract passed at render time on a relation no projection
    # trigger could ever read, which is the exact failure the contract exists to prevent.
    # The contract cannot see this — it validates a declaration, not a schema — so the
    # reference vertical's own SQL has to be checked against its own binding.
    binding_obj = load_binding(repo_root_path / BINDINGS[1])
    sql = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(binding_obj.output_dir.glob("*.sql"))
    )
    created = set(re.findall(r"CREATE (?:TABLE|VIEW|MATERIALIZED VIEW)\s+([a-z_]+\.[a-z_]+)", sql))
    for entry in binding_obj.authority_sources:
        assert entry.relation in created, (
            f"{entry.relation} is declared as an authority source but no file under "
            f"{binding_obj.output_dir.name}/ creates it. The reference vertical exists so "
            "that K1 does not depend on K3; a binding whose authority relation does not "
            "exist cannot be conformance-tested at all."
        )


# ── the foundation band, read out of the committed files ────────────────────────────


def test_the_clearance_lattice_is_twenty_one_rows(binding: Binding) -> None:
    seed = committed(binding, "0018b_clearance_legal_seed.sql")
    rows = [(m["virulence"], m["kind"]) for m in _CLEARANCE_ROW.finditer(seed)]
    assert len(rows) == 21
    assert len(set(rows)) == 21, "a duplicated cell would fail the primary key at apply time"


def test_exactly_three_cells_are_absent_and_they_are_the_named_three(binding: Binding) -> None:
    seed = committed(binding, "0018b_clearance_legal_seed.sql")
    present = {(m["virulence"], m["kind"]) for m in _CLEARANCE_ROW.finditer(seed)}
    product = {(v, k) for v in VIRULENCE for k in DISPOSITION_KIND}
    assert product - present == DELIBERATELY_ABSENT
    assert present - product == set(), "a seeded cell outside the 4x6 product"


def test_each_absent_cell_is_named_in_the_migration_that_omits_it(binding: Binding) -> None:
    # Absence is the mechanism, and an unexplained absence is indistinguishable from an
    # oversight. The reader of this file must be told which three and why.
    seed = committed(binding, "0018b_clearance_legal_seed.sql")
    for virulence, kind in sorted(DELIBERATELY_ABSENT):
        assert f"({virulence}, {kind})" in seed, f"({virulence}, {kind}) is absent but unexplained"
    assert "DELIBERATELY ABSENT" in seed


def test_the_fatality_cells_are_absent_for_the_reason_the_product_is_named_after(
    binding: Binding,
) -> None:
    seed = committed(binding, "0018b_clearance_legal_seed.sql")
    fatal = {kind for virulence, kind in _iter_rows(seed) if virulence == "blood_fatal"}
    assert "accept_residual" not in fatal, (
        "accepting residual risk on a control a death wrote is the exhibit that ends the "
        "argument; there is no rank and no expiry that makes this cell legal"
    )
    assert "mechanism_absent" not in fatal


def _iter_rows(seed: str) -> list[tuple[str, str]]:
    return [(m["virulence"], m["kind"]) for m in _CLEARANCE_ROW.finditer(seed)]


def test_the_transition_edge_set_is_identical_for_every_subject_kind(binding: Binding) -> None:
    seed = committed(binding, "0017b_subject_transition_seed.sql")
    by_kind: dict[str, set[tuple[str, str]]] = {}
    for match in _EDGE_ROW.finditer(seed):
        by_kind.setdefault(match["kind"], set()).add((match["frm"], match["to"]))
    assert set(by_kind) == {"permit", "change_request"}
    for kind, edges in sorted(by_kind.items()):
        assert edges == EDGES, f"{kind} has a different edge set"


def test_nothing_transitions_into_draft_and_merged_never_re_enters_the_gate() -> None:
    # The absent edges carry the state-machine half of the epoch pin: a merged subject
    # cannot re-enter the gate, so no obligation can be attached to a completed
    # transition. Asserted over the edge set this module declares, so a future edit to
    # EDGES that broke the property fails here rather than silently in the seed.
    assert not [edge for edge in EDGES if edge[1] == "draft"]
    assert {to for frm, to in EDGES if frm == "merged"} == {"suspended", "closed"}
    assert not [edge for edge in EDGES if edge[0] in {"closed", "abandoned"}]


def test_the_seven_types_are_each_their_own_migration(binding: Binding) -> None:
    expected = (
        "0010_type_control_delta.sql",
        "0011_type_subject_state.sql",
        "0012_type_disposition_kind.sql",
        "0013_type_virulence_class.sql",
        "0014_type_blame_basis.sql",
        "0015_type_blame_state.sql",
        "0016_type_prop_state.sql",
    )
    schema = binding.vertical.schema
    for name in expected:
        body = executable(committed(binding, name))
        assert body.count("CREATE TYPE") == 1, f"{name} is not exactly one CREATE TYPE"
        assert f"{schema}." in body, "every type must be schema-qualified into the binding's schema"


def test_the_five_schema_zones_are_derived_from_the_one_declared_name(binding: Binding) -> None:
    schema = binding.vertical.schema
    assert [z.name for z in binding.zones] == [
        schema,
        f"{schema}_meas",
        f"{schema}_audit",
        f"{schema}_qa",
        f"{schema}_ops",
    ]


# ── properties every rendered file in the band must carry ──────────────────────────


def test_every_rendered_file_cites_an_invariant(binding: Binding, templates_dir: Path) -> None:
    # ARCHITECTURE.md §18, enforced by the renderer and re-asserted over the committed
    # bytes: the enforcement and the artefact are different things, and only one of them
    # is what `trappoint migrate up` reads.
    for unit in render_binding(binding, templates_dir).units:
        text = committed(binding, unit.name)
        header = text.split("\n\n", 1)[0]
        assert _CITATION.search(header), f"{unit.name} cites no MI or I identifier"


def test_no_committed_file_in_the_band_reintroduces_a_sequence(binding: Binding) -> None:
    # Ruling D10. The gap-free-by-CAS claim is worthless if one future migration
    # reintroduces a sequence, and the claim is what makes a gap MEAN tampering.
    banned = re.compile(
        r"\bCREATE\s+SEQUENCE\b|\bnextval\s*\(|\b(?:BIG|SMALL)?SERIAL[248]?\b|\bunique_rowid\s*\(",
        re.I,
    )
    for path in sorted(binding.output_dir.glob("*.sql")):
        body = executable(path.read_text(encoding="utf-8"))
        assert not banned.search(body), f"{path.name} reintroduces a banned token"


def test_the_recaller_receives_no_write_privilege_anywhere_in_the_band(binding: Binding) -> None:
    # Finding `S1` asserted over the artefact rather than over the guard that produced it.
    # The role that detects a precursor may never write one.
    recaller = binding.role("recaller")
    write = re.compile(r"\b(?:INSERT|UPDATE|DELETE|TRUNCATE|ALL(?:\s+PRIVILEGES)?)\b", re.I)
    grant = re.compile(r"\bGRANT\b", re.I)
    seen = 0
    for path in sorted(binding.output_dir.glob("*.sql")):
        body = executable(path.read_text(encoding="utf-8"))
        if not grant.search(body) or recaller not in body:
            continue
        seen += 1
        assert not write.search(body), f"{path.name} grants {recaller} a write privilege"
    assert seen, (
        f"no committed file in the band names {recaller} in a GRANT at all. That is not a "
        "pass: this test would then be green over a band whose grants had been deleted, "
        "and 0009b is supposed to give the recaller USAGE."
    )


def test_the_binding_declares_its_conformance_profile(binding: Binding) -> None:
    # `ANOMALY_COVERAGE.md` and the suite's `--profile` flag both read this. A binding
    # with no profile is a binding no conformance case can select on, which is a vertical
    # nobody can prove anything about.
    assert binding.conformance_profile in {"mainline", "trappoint-ref"}


def test_the_committed_binding_is_valid_toml_with_an_spdx_header(
    binding: Binding, repo_root_path: Path
) -> None:
    text = binding.source.read_text(encoding="utf-8")
    assert "SPDX-License-Identifier:" in text.split("\n\n", 1)[0]
    with binding.source.open("rb") as handle:
        document = tomllib.load(handle)
    assert document["vertical"]["output_dir"]
    assert (repo_root_path / document["capabilities"]["attestation"]).is_file()
