# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``mainline-gate-svc`` — the deterministic merge-gate caller for the MAINLINE binding.

Three modules and one claim between them:

* :mod:`mainline_gate_svc.config` — where the DSN comes from, and the refusal that runs
  before anything else: a gate process holding an AWS or model-provider credential
  refuses to start.
* :mod:`mainline_gate_svc.service` — :func:`~mainline_gate_svc.service.merge_permit`:
  one explicit ``SERIALIZABLE`` transaction, one ``CALL mainline.merge_permit``, and a
  :class:`~trappoint_core.GateRefused` that leaves with its constraint name intact.
* :mod:`mainline_gate_svc.cli` — a thin entry point over the two above.

The claim, from ARCHITECTURE.md §8.2: **no model can reach the merge gate.** Until this
distribution existed, that claim's code-path enforcement (E3) scanned a path that was
not there and recorded ``E3-ROOT-ABSENT`` as a skip-with-reason — honest, and
unfalsifiable. The enforcement now has a subject: three runtime dependencies, a
``sys.modules`` walk after import, and a transitive walk over the declared distribution
metadata, in ``tests/test_no_model_in_closure.py``.
"""

from __future__ import annotations

from typing import Final

from .config import (
    DEFAULT_SCHEMA,
    DEFAULT_SUBJECT_KIND,
    DSN_VARIABLES,
    MODEL_ENVIRONMENT_NAMES,
    MODEL_ENVIRONMENT_PREFIXES,
    GateConfig,
    GateServiceError,
    MissingDsn,
    ModelEnvironmentPresent,
    load_config,
    model_environment,
    retry_policy,
)
from .service import (
    MERGE_CALL_FIELDS,
    ConnectionUnavailable,
    DirectConnection,
    MergeOutcome,
    WrongBinding,
    call_parameters,
    connection_source,
    merge_permit,
    merge_request_from_mapping,
)

__all__ = [
    "DEFAULT_SCHEMA",
    "DEFAULT_SUBJECT_KIND",
    "DSN_VARIABLES",
    "MERGE_CALL_FIELDS",
    "MODEL_ENVIRONMENT_NAMES",
    "MODEL_ENVIRONMENT_PREFIXES",
    "ConnectionUnavailable",
    "DirectConnection",
    "GateConfig",
    "GateServiceError",
    "MergeOutcome",
    "MissingDsn",
    "ModelEnvironmentPresent",
    "WrongBinding",
    "__version__",
    "call_parameters",
    "connection_source",
    "load_config",
    "merge_permit",
    "merge_request_from_mapping",
    "model_environment",
    "retry_policy",
]

__version__: Final[str] = "0.1.0"
