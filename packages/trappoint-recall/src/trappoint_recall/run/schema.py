# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""JSON Schema generation for the frozen candidate-set contract.

The schema is **generated from the models and committed to the repository**, and a test
asserts the two agree (``tests/integration/recall_run/test_contract_schema.py``). That
arrangement is deliberate rather than redundant:

* the models are the implementation the recall agent validates against, in Python;
* the committed schema is what the kernel lead, the console and any future non-Python
  consumer validate against, and it is a file they can read in a pull request;
* the test is what stops the two from drifting, which is the failure mode a hand-written
  schema always eventually reaches.

The generated document is *not* a substitute for the model's validators. Conservation, the
probabilistic cap and the deterministic-origin rules are cross-field laws that JSON Schema
cannot express, and pretending otherwise would leave a consumer believing a schema-valid
payload is a legal one. The schema says so, in its own ``description``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from trappoint_recall.run.contract import CONTRACT_SCHEMA_VERSION, CandidateSet

__all__ = [
    "SCHEMA_FILENAME",
    "SCHEMA_ID",
    "candidate_set_json_schema",
    "committed_schema_path",
    "render_schema",
    "write_schema",
]

SCHEMA_ID: Final = "https://mainline.trappoint.dev/schema/candidate-set-v1.schema.json"
SCHEMA_FILENAME: Final = "candidate-set-v1.schema.json"

_CROSS_FIELD_NOTE: Final = (
    "JSON Schema validity is necessary and NOT sufficient. Three laws are cross-field and "
    "are enforced by trappoint_recall.run.contract, by mainline_recall_agent.run, and by the "
    "database: (1) MI17 candidates_conserved, n_candidates = blocking + advisory + silenced + "
    "deduped exactly; (2) at most 3 blocking checks of probabilistic origin, with channels A "
    "and B uncapped; (3) MI16, every bonded severity-5 event is blocking. A payload that "
    "validates here and violates one of those is refused downstream."
)


def candidate_set_json_schema() -> dict[str, Any]:
    """The JSON Schema for :class:`~trappoint_recall.run.contract.CandidateSet`."""
    schema = CandidateSet.model_json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = SCHEMA_ID
    schema["title"] = "MAINLINE recall candidate set"
    schema["description"] = (
        "The payload of POST /v1/permits/{id}/checks:materialise. The recall agent never "
        "writes blocking_check; it hands the kernel this set and the kernel decides what "
        f"becomes an obligation. Contract version {CONTRACT_SCHEMA_VERSION}. "
        + _CROSS_FIELD_NOTE
    )
    return schema


def render_schema() -> str:
    """The committed text: two-space indent, sorted keys, one trailing newline."""
    return json.dumps(candidate_set_json_schema(), indent=2, sort_keys=True) + "\n"


def committed_schema_path() -> Path:
    """Where the generated schema lives in the source tree."""
    return Path(__file__).resolve().parent / "schema" / SCHEMA_FILENAME


def write_schema(destination: Path | None = None) -> Path:
    """Regenerate the committed schema. Returns the path written."""
    target = committed_schema_path() if destination is None else destination
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_schema(), encoding="utf-8")
    return target


if __name__ == "__main__":  # pragma: no cover - a maintenance entry point
    print(write_schema())  # noqa: T201
