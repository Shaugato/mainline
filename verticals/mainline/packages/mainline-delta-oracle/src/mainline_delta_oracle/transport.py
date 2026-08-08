# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Where the recordings live, and the two locks on the live lane.

**Cassette-first is decision D12 and it is not a convenience.**  AWS credentials
are not valid on the build machine as of 2026-08, and PL-3 forbids putting an
unproven capability on a dated path.  So the default transport is a replay store
of committed interactions, CI never opens a socket, and a stranger can run the
whole of Path B on a laptop with no AWS account.

**The live lane exists and is off.**  Reaching Bedrock needs *both*
``MAINLINE_AGENT_PROVIDER=bedrock`` and ``MAINLINE_AGENT_ALLOW_LIVE=1``, and both
locks are agentkit's rather than this package's — there is one model surface in
this repository and this package is a caller of it, not a second one.  When it is
opened, agentkit refuses any model id that is not an ``au.*`` inference profile,
which is the residency control in the code path (§10.1).

**A replay miss is fatal.**  It never falls through to a live call.  A provider
that quietly reached the network on a miss would make every green run a claim
about a call that may never have been recorded.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Final

from mainline_agentkit import AgentkitSettings, CassetteStore, CassetteTransport, select_transport

from .errors import CassetteModelDrift, CassetteRootUnknown

if TYPE_CHECKING:
    from mainline_agentkit import Transport

__all__ = [
    "CASSETTE_DIR_ENV",
    "COMMITTED_CASSETTE_PARTS",
    "build_transport",
    "default_cassette_root",
    "verify_cassette_store",
]

#: Overrides the search below.  Used by the fixture generator and by any harness
#: that keeps its own recordings.
CASSETTE_DIR_ENV: Final[str] = "MAINLINE_ORACLE_CASSETTE_DIR"

#: Where the committed recordings live, relative to the repository root.
COMMITTED_CASSETTE_PARTS: Final[tuple[str, ...]] = (
    "tests",
    "fixtures",
    "domain",
    "oracle",
    "cassettes",
)


def default_cassette_root(start: Path | None = None) -> Path:
    """Locate the committed cassette store.

    Args:
        start: where to begin the upward search.  Defaults to this file.

    Returns:
        The directory holding ``<key>.json`` interactions.

    Raises:
        CassetteRootUnknown: when neither the environment variable nor the
            repository layout produces one.  There is no fallback to a temporary
            directory: an empty store presents as "every key missing", which reads
            as a code bug rather than the setup problem it is.
    """
    override = os.environ.get(CASSETTE_DIR_ENV)
    if override:
        candidate = Path(override)
        if not candidate.is_dir():
            raise CassetteRootUnknown(
                f"{CASSETTE_DIR_ENV}={override!r} is not a directory. Replay never falls "
                f"through to a live call, so a store that is not there is fatal."
            )
        return candidate
    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        candidate = parent.joinpath(*COMMITTED_CASSETTE_PARTS)
        if candidate.is_dir():
            return candidate
    raise CassetteRootUnknown(
        f"no cassette store found above {here}. Set {CASSETTE_DIR_ENV}, or run from a "
        f"checkout containing {'/'.join(COMMITTED_CASSETTE_PARTS)}."
    )


def verify_cassette_store(store: CassetteStore, *, model_id: str) -> int:
    """Refuse a store whose recordings came from a different model generation.

    A cassette recorded against one generation and replayed as another is a test
    that asserts something about a model nobody called.  Returns the number of
    interactions checked.

    Raises:
        CassetteModelDrift: naming the first divergent key.
    """
    checked = 0
    for key in store.keys():
        recorded = store.get(key).model_id
        if recorded != model_id:
            raise CassetteModelDrift(
                f"cassette {key} was recorded against model {recorded!r} and this oracle "
                f"is configured for {model_id!r}. Re-record the store, or configure the "
                f"generation it was recorded with; do not replay across generations."
            )
        checked += 1
    return checked


def build_transport(
    *,
    settings: AgentkitSettings | None = None,
    cassette_root: Path | None = None,
    model_id: str | None = None,
) -> Transport:
    """Build the configured provider, cassette by default.

    Args:
        settings: agentkit settings.  Read from the environment when omitted, so
            the provider is ``cassette`` unless someone opened both locks.
        cassette_root: an explicit store.  Falls back to
            ``MAINLINE_CASSETTE_DIR``, then to :func:`default_cassette_root`.
        model_id: when given, every recording in the store is checked against it
            before the first call.

    Returns:
        A transport satisfying agentkit's ``Transport`` protocol.
    """
    resolved = settings or AgentkitSettings.from_env()
    if resolved.provider != "cassette":
        return select_transport(resolved)
    root = cassette_root or resolved.cassette_dir or default_cassette_root()
    store = CassetteStore(root, mode=resolved.cassette_mode)
    if model_id is not None and resolved.cassette_mode == "replay":
        verify_cassette_store(store, model_id=model_id)
    return CassetteTransport(store)
