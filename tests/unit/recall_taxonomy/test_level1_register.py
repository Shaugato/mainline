# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Level 1 is frozen, on the register, and re-inducting it is a re-partition.

Three refusals, and one message.  The message matters as much as the refusal: an engineer
who tries to change a level-1 code needs to be told, at the point of the attempt, that the
codes are prefix values baked into the physical vector index and that the supported
operation is a re-partition — because the failure mode of getting this wrong is silent
(orphaned vectors in a tree no arm binds) and the correction is expensive.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mainline_recall_agent.taxonomy import (
    LEVEL_FONDS,
    MAX_LEVEL1_CODES,
    MIN_LEVEL1_CODES,
    ActivityNode,
    LabelRejected,
    Level1OffRegister,
    Level1Register,
    Level1Repartition,
    Level1Unfrozen,
    RegisterMalformed,
    assert_level1_node,
    derive_scope_id,
    load_level1_register,
    refuse_level1_reinduction,
)

SITE = "11111111-1111-4111-8111-111111111111"


def test_register_loads_inside_the_fonds_cardinality_band(register: Level1Register) -> None:
    assert MIN_LEVEL1_CODES <= len(register.codes) <= MAX_LEVEL1_CODES
    assert len(set(register.roots)) == len(register.codes)
    assert len(register.sha256) == 64


def test_register_digest_is_over_content_not_bytes(
    register: Level1Register, tmp_path: Path, fixtures_dir: Path
) -> None:
    """Reformatting the file must not change the register's identity; editing it must."""
    payload = json.loads((fixtures_dir / "icmm_mue_l1.json").read_text(encoding="utf-8"))
    reformatted = tmp_path / "reformatted.json"
    reformatted.write_text(json.dumps(payload, indent=8), encoding="utf-8")
    assert load_level1_register(reformatted).sha256 == register.sha256

    payload["codes"][0]["notes"] = "an added note"
    edited = tmp_path / "edited.json"
    edited.write_text(json.dumps(payload), encoding="utf-8")
    assert load_level1_register(edited).sha256 != register.sha256


def test_loader_refuses_an_unfrozen_register_entry(fixtures_dir: Path) -> None:
    with pytest.raises(Level1Unfrozen) as excinfo:
        load_level1_register(fixtures_dir / "icmm_mue_l1_unfrozen.json")
    assert excinfo.value.context["activity_root"] == "MUE-07"


def test_loader_refuses_a_register_that_declares_itself_unfrozen(tmp_path: Path) -> None:
    payload = {
        "register_id": "unfrozen",
        "frozen": False,
        "codes": [
            {
                "activity_root": f"MUE-{index:02d}",
                "mue_title": "title",
                "label": "isolating stored energy before intrusive work",
            }
            for index in range(MIN_LEVEL1_CODES)
        ],
    }
    path = tmp_path / "register.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Level1Unfrozen):
        load_level1_register(path)


def test_loader_refuses_a_thing_label_at_the_root_of_the_index(fixtures_dir: Path) -> None:
    with pytest.raises(LabelRejected) as excinfo:
        load_level1_register(fixtures_dir / "icmm_mue_l1_thing_label.json")
    assert excinfo.value.context["reason"] == "equipment_or_place_term"


def _register_payload(count: int, *, duplicate: bool = False) -> dict[str, object]:
    codes = [
        {
            "activity_root": "MUE-01" if duplicate else f"MUE-{index:02d}",
            "mue_title": "title",
            "label": f"isolating stored energy before intrusive work {'a' * index}",
        }
        for index in range(count)
    ]
    return {"register_id": "generated", "frozen": True, "codes": codes}


@pytest.mark.parametrize("count", [MIN_LEVEL1_CODES - 1, MAX_LEVEL1_CODES + 1])
def test_loader_refuses_a_register_outside_the_cardinality_band(
    tmp_path: Path, count: int
) -> None:
    path = tmp_path / "register.json"
    path.write_text(json.dumps(_register_payload(count)), encoding="utf-8")
    with pytest.raises(RegisterMalformed) as excinfo:
        load_level1_register(path)
    assert excinfo.value.context["count"] == count


def test_loader_refuses_a_duplicate_code_because_the_code_is_the_index_prefix(
    tmp_path: Path,
) -> None:
    path = tmp_path / "register.json"
    path.write_text(
        json.dumps(_register_payload(MIN_LEVEL1_CODES, duplicate=True)), encoding="utf-8"
    )
    with pytest.raises(RegisterMalformed) as excinfo:
        load_level1_register(path)
    assert excinfo.value.context["activity_root"] == "MUE-01"


def test_register_nodes_are_frozen_icmm_and_deterministically_identified(
    register: Level1Register,
) -> None:
    nodes = register.nodes(site_id=SITE, taxonomy_ver=1)
    assert len(nodes) == len(register.codes)
    for node in nodes:
        assert node.level == LEVEL_FONDS
        assert node.frozen is True
        assert node.induced_by == "icmm_mue"
        assert node.parent_scope is None
        assert node.scope_id == derive_scope_id(
            site_id=SITE, taxonomy_ver=1, level=LEVEL_FONDS, label_path=[node.label]
        )
    # Two calls, same identities: a re-run of the induction must not re-identify the fonds.
    assert [n.scope_id for n in register.nodes(site_id=SITE, taxonomy_ver=1)] == [
        n.scope_id for n in nodes
    ]


def test_a_fonds_cannot_be_constructed_unfrozen(register: Level1Register) -> None:
    code = register.codes[0]
    with pytest.raises(Level1Unfrozen):
        ActivityNode(
            scope_id="00000000-0000-4000-8000-000000000001",
            site_id=SITE,
            level=LEVEL_FONDS,
            parent_scope=None,
            label=code.label,
            activity_root=code.activity_root,
            taxonomy_ver=1,
            induced_by="icmm_mue",
            frozen=False,
        )


def test_assert_level1_node_refuses_an_off_register_code(register: Level1Register) -> None:
    invented = ActivityNode(
        scope_id="00000000-0000-4000-8000-000000000009",
        site_id=SITE,
        level=LEVEL_FONDS,
        parent_scope=None,
        label="managing fatigue across rostered shifts",
        activity_root="MUE-99",
        taxonomy_ver=1,
        induced_by="icmm_mue",
        frozen=True,
    )
    with pytest.raises(Level1OffRegister) as excinfo:
        assert_level1_node(invented, register)
    assert excinfo.value.context["activity_root"] == "MUE-99"
    # The refusal must come from the membership check itself, not incidentally from the
    # label lookup further down: only the membership branch reports the node's own label,
    # and asserting on it is what makes removing that branch turn this test red.
    assert excinfo.value.context["label"] == invented.label
    assert excinfo.value.context["register_id"] == register.register_id


def test_assert_level1_node_refuses_a_local_rewording(register: Level1Register) -> None:
    code = register.codes[0]
    reworded = ActivityNode(
        scope_id="00000000-0000-4000-8000-00000000000a",
        site_id=SITE,
        level=LEVEL_FONDS,
        parent_scope=None,
        label="supporting excavated ground before entry",
        activity_root=code.activity_root,
        taxonomy_ver=1,
        induced_by="icmm_mue",
        frozen=True,
    )
    with pytest.raises(Level1OffRegister) as excinfo:
        assert_level1_node(reworded, register)
    assert excinfo.value.context["on_register"] == code.label


def test_assert_level1_node_refuses_an_induced_fonds(register: Level1Register) -> None:
    code = register.codes[1]
    induced = ActivityNode(
        scope_id="00000000-0000-4000-8000-00000000000b",
        site_id=SITE,
        level=LEVEL_FONDS,
        parent_scope=None,
        label=code.label,
        activity_root=code.activity_root,
        taxonomy_ver=1,
        induced_by="llm_induced",
        frozen=True,
    )
    with pytest.raises(Level1OffRegister):
        assert_level1_node(induced, register)


def test_assert_level1_node_accepts_the_register_itself(register: Level1Register) -> None:
    for node in register.nodes(site_id=SITE, taxonomy_ver=1):
        assert assert_level1_node(node, register) is node


def test_reinduction_is_refused_as_a_repartition(register: Level1Register) -> None:
    existing = [*register.roots[:-1], "MUE-90"]
    with pytest.raises(Level1Repartition) as excinfo:
        refuse_level1_reinduction(register, existing)
    message = str(excinfo.value)
    assert "RE-PARTITION, not an update" in message
    assert "K-means tree per distinct prefix value" in message
    assert excinfo.value.context["removed"] == ["MUE-90"]
    assert excinfo.value.context["added"] == [register.roots[-1]]


def test_first_install_and_no_change_are_both_allowed(register: Level1Register) -> None:
    refuse_level1_reinduction(register, [])
    refuse_level1_reinduction(register, list(register.roots))
