# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The shapes the scan must NOT flag, so that its two exceptions are themselves tested.

Without this file the scanner's exceptions would be untested code paths, and an untested
exception in a security scan is where the next false negative lives. Every construct here
is one that appears in real code in this repository:

* ``"tools": []`` - ``CallProfile.describe`` (declared absence);
* ``tools=list(self.tools)`` - ``mainline_recall_fleet.legs`` raising a contract
  violation (same-name derivation);
* ``sorted(grant.tools)`` and ``spec.get("tools")`` -
  ``mainline_quarantine.capability`` comparing what a process holds with what the
  register grants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Leg:
    """A fleet leg that declares its own (empty) tool list."""

    leg_id: str
    tools: tuple[str, ...] = ()

    def describe(self) -> dict[str, Any]:
        """The register shape, which says out loud that this leg holds nothing."""
        return {"leg_id": self.leg_id, "tools": []}

    def refuse_if_armed(self) -> None:
        """Raise when a leg declares a tool, naming the tools in the diagnostic."""
        if self.tools:
            raise ValueError("a recall leg declares a tool", {"tools": list(self.tools)})


def grant_report(spec: dict[str, Any], granted: Leg) -> dict[str, Any]:
    """Read a tool list out of a register entry and compare it with what is granted."""
    return {
        "declared": sorted(granted.tools),
        "tools": spec.get("tools") or [],
        "mcp_servers": None,
    }
