# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The DENY class: refusals that happen *before* the gate.

``42501`` is excluded from the refusal taxonomy by **definition**, not by exception. The
writer was stopped by the grant graph or by a row-level-security policy, and no gate
condition was ever evaluated — so classifying it with ``23514`` would say the gate refused
something the gate never saw.

It still needs an exhibit, and the driver supplies none: there is no constraint. The
specification therefore *defines* one (``spec/errors.md`` §3.1):

    ``grant:<verb>:<object>:<role>``, or the RLS policy name

That token is **synthesised from what the case did**, not parsed out of a message, and this
module is the only place in the corpus that synthesises an exhibit. Three guards keep it
honest and they are the reason this is a module rather than an f-string at each call site:

* it is applied **only** when the observed SQLSTATE is exactly ``42501``, so a case that
  was refused for some other reason cannot acquire a grant-shaped exhibit;
* the object is re-homed into the manifest's namespace exactly as ``P0001`` exhibits are,
  because the schema is a property of the binding and the manifest is one document;
* the verb, object and role are the case's own declaration of what it attempted, so a case
  that attempted the wrong thing produces a token that does not match the manifest.
"""

from __future__ import annotations

from ._exhibit import MANIFEST_NAMESPACE

__all__ = ["grant_exhibit", "normalise_deny"]


def grant_exhibit(verb: str, obj: str, role: str) -> str:
    """Return the specified token for a privilege refusal."""
    return f"grant:{verb}:{MANIFEST_NAMESPACE}.{obj}:{role}"


def normalise_deny(outcome: object, *, verb: str, obj: str, role: str) -> None:
    """Attach the synthesised exhibit to a ``42501`` outcome, in place.

    Any other SQLSTATE is left exactly as the driver reported it. In particular a history
    that **completed** keeps ``completed = True`` and no exhibit, so a role that turned out
    to hold the privilege fails the case rather than acquiring the name of the grant that
    was supposed to stop it.
    """
    if getattr(outcome, "sqlstate", "") != "42501":
        return
    outcome.constraint = grant_exhibit(verb, obj, role)  # type: ignore[attr-defined]
    # Synthesised from the case's declaration rather than reported by the driver. The
    # weakening flag is what keeps that visible in the report and in --json.
    outcome.exhibit_weakened = True  # type: ignore[attr-defined]
