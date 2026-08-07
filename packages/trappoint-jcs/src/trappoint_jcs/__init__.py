# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-jcs`` — RFC 8785 JSON canonicalisation for evidentiary payloads.

Zero runtime dependencies, by contract. Not ``pydantic``, not ``cryptography``, not
anything: this package produces the bytes that every hash in the custody ledger is taken
over, and a dependency here is a dependency an opposing expert's re-implementation would
have to reproduce.

Version dispatch
----------------
``CANONICALISERS`` maps ``payload_ver`` to the entry point that produced those bytes.
``ledger_intake.payload_ver`` records which canonicaliser was used for each leaf, and the
verifier dispatches on it. **Every historical canonicaliser is retained forever.**
Removing ``canon_v1`` would make every leaf written under it unverifiable, which is a
breaking change to *evidence*, not to code; ``spec/custody/canon-registry.yaml`` pins the
SHA-256 of each one and ``scripts/custody/check_vendored_canon.py`` fails the build if a
pin stops matching.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from trappoint_jcs.canon_v1 import (
    CANON_VERSION,
    CanonicalisationError,
    DepthExceeded,
    DuplicateKey,
    InvalidString,
    NonEvidentiaryNumber,
    NonFiniteNumber,
    NonInteroperableNumber,
    NonStringKey,
    UnsupportedType,
    canon_src_sha256,
    canonicalise,
    canonicalise_json,
    canonicalise_payload,
    es6_number,
)

__version__: Final = "0.1.0"

#: ``payload_ver`` → the payload canonicaliser that produced those bytes. Append only.
CANONICALISERS: Final[dict[int, Callable[[Any], bytes]]] = {
    CANON_VERSION: canonicalise_payload,
}

#: ``payload_ver`` → ``canon_src_sha256`` of the module that implements it.
CANONICALISER_SOURCE_DIGESTS: Final[dict[int, Callable[[], bytes]]] = {
    CANON_VERSION: canon_src_sha256,
}

__all__ = [
    "CANONICALISERS",
    "CANONICALISER_SOURCE_DIGESTS",
    "CANON_VERSION",
    "CanonicalisationError",
    "DepthExceeded",
    "DuplicateKey",
    "InvalidString",
    "NonEvidentiaryNumber",
    "NonFiniteNumber",
    "NonInteroperableNumber",
    "NonStringKey",
    "UnsupportedType",
    "__version__",
    "canon_src_sha256",
    "canonicalise",
    "canonicalise_json",
    "canonicalise_payload",
    "es6_number",
]
