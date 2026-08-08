# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""theta, and the refusal to invent one.

theta is the confidence a Path-B answer must carry before a *disagreement inside
the zero-force class* is allowed to resolve as anything other than ``weaken``.
It is a **calibration artefact**, not a setting, and it lives in
``identity_policy`` — the same file whose content hash decision D11 stamps onto
every ``identity_assignment`` row — for one reason: retro-tuning theta to make a
merge that should have blocked look reasonable must leave the same trace that
retro-tuning the matcher leaves.

Consequences that are enforced here rather than intended:

* **There is no default.**  Not in a function signature, not in a module
  constant, not in a fallback branch.  A missing theta raises
  :class:`PolicyIncomplete`.  A default would be a threshold nobody signed, and
  the whole point of the ledger is that every threshold has an author.
* **The content hash travels with the value.**  :class:`PolicyTheta` carries the
  SHA-256 of the exact policy bytes theta was read from, and
  :mod:`mainline_domain.resolution.silence` writes it into the arithmetic of
  every silence record.  Two runs that disagree can be told apart by the hash
  rather than by argument.
* **theta is bounded to the same scale as ``OracleVerdict.confidence``.**  That
  scale is ``[0, 1]``.  See the honesty note in
  ``mainline_delta_oracle.mapping``: the oracle emits a *named band* mapped onto
  that interval, not a calibrated probability, and theta must be chosen with
  that in mind.

**Ownership.**  ``data/policy/identity-policy-v1.toml`` belongs to worker W8
(``margin-assignment``).  This module only reads it, and names the exact key it
needs so that the two workers cannot drift silently:

.. code-block:: toml

   [resolution]
   oracle_confidence_theta = 0.75
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from ..data import data_file

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from typing import Any

__all__ = [
    "IDENTITY_POLICY_PARTS",
    "THETA_KEY",
    "THETA_SECTION",
    "PolicyIncomplete",
    "PolicyTheta",
    "load_policy_theta",
    "theta_from_policy",
]

#: Where the committed policy lives inside the distribution.  Owned by W8.
IDENTITY_POLICY_PARTS: Final[tuple[str, ...]] = ("policy", "identity-policy-v1.toml")

THETA_SECTION: Final[str] = "resolution"
THETA_KEY: Final[str] = "oracle_confidence_theta"


class PolicyIncomplete(Exception):
    """The identity policy does not carry theta, so no resolution may proceed.

    Deliberately not a subclass of ``KeyError``: a caller writing
    ``except KeyError`` around a policy read is a caller who is about to supply a
    default, and this is the one value that must never have one.
    """


@dataclass(frozen=True, slots=True)
class PolicyTheta:
    """theta, plus the identity of the document it came from."""

    theta: float
    policy_version: str
    policy_sha256: str

    def __post_init__(self) -> None:
        """Refuse a theta outside the interval ``OracleVerdict.confidence`` lives in."""
        if not 0.0 <= self.theta <= 1.0:
            raise PolicyIncomplete(
                f"{THETA_SECTION}.{THETA_KEY} = {self.theta} is outside [0, 1]; "
                f"theta is compared against OracleVerdict.confidence, which is a "
                f"band midpoint on that interval"
            )
        if not self.policy_sha256:
            raise PolicyIncomplete("a policy theta without a content hash is untraceable")


def theta_from_policy(
    policy: Mapping[str, Any],
    *,
    policy_version: str,
    policy_sha256: str,
) -> PolicyTheta:
    """Read theta out of an already-parsed policy mapping.

    Args:
        policy: the parsed ``identity-policy-v1.toml`` document.
        policy_version: the version string recorded alongside the value.
        policy_sha256: hex SHA-256 of the exact bytes ``policy`` was parsed from.

    Raises:
        PolicyIncomplete: the section or the key is absent, or the value is not a
            real number.  Never returns a default.
    """
    section = policy.get(THETA_SECTION)
    if not isinstance(section, dict) or THETA_KEY not in section:
        raise PolicyIncomplete(
            f"identity policy {policy_version!r} carries no [{THETA_SECTION}] "
            f"{THETA_KEY}. The abstention ratchet compares OracleVerdict.confidence "
            f"against theta, and a resolution run under an unsigned threshold is a "
            f"resolution nobody authored. Add the key to the policy; do not add a "
            f"default to the code."
        )
    raw = section[THETA_KEY]
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise PolicyIncomplete(
            f"[{THETA_SECTION}] {THETA_KEY} is {raw!r} ({type(raw).__name__}); "
            f"theta must be a real number in [0, 1]"
        )
    return PolicyTheta(
        theta=float(raw),
        policy_version=policy_version,
        policy_sha256=policy_sha256,
    )


def load_policy_theta(path: Path | None = None) -> PolicyTheta:
    """Load theta from the committed identity policy.

    Args:
        path: an explicit policy file.  Defaults to the committed
            ``data/policy/identity-policy-v1.toml`` (worker W8), which raises
            ``FileNotFoundError`` while that file does not exist — loudly, rather
            than falling back to a value this module made up.

    Returns:
        theta with the content hash of the bytes it was read from.

    Raises:
        FileNotFoundError: the policy is not installed.
        PolicyIncomplete: the policy is installed but carries no theta.
        tomllib.TOMLDecodeError: the policy is not parseable.  Left to propagate:
            a policy that does not parse is not a policy.
    """
    resolved = path if path is not None else data_file(*IDENTITY_POLICY_PARTS)
    raw = resolved.read_bytes()
    document: Mapping[str, Any] = tomllib.loads(raw.decode("utf-8"))
    meta = document.get("policy")
    version = (
        str(meta["version"])
        if isinstance(meta, dict) and "version" in meta
        else resolved.stem  # truthful identifier; the hash below is the real identity
    )
    return theta_from_policy(
        document,
        policy_version=version,
        policy_sha256=hashlib.sha256(raw).hexdigest(),
    )
