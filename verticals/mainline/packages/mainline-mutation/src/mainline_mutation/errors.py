# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The four conditions this harness refuses to paper over.

A measurement harness that degrades quietly is worse than no harness: it keeps
publishing a number after the thing it measured stopped being the thing under
test.  Each of these is raised rather than logged, and each names the property
that would otherwise have been silently lost.
"""

from __future__ import annotations

__all__ = [
    "CatalogueError",
    "FixtureError",
    "MutationError",
    "OperatorInapplicable",
    "UnpopulatedClass",
]


class MutationError(Exception):
    """Base class for everything this package refuses."""


class CatalogueError(MutationError):
    """The declared catalogue and the implemented operators disagree.

    A class declared in ``catalogue-v1.toml`` with no operator would be counted
    as a class with zero trials and would drag the published rate down for a
    reason that is a wiring bug rather than a finding.  An operator with no
    declaration would contribute trials that no catalogue entry describes, which
    is a number nobody can audit.  Both raise.
    """


class FixtureError(MutationError):
    """A fixture revision is missing, malformed, or unusable by an operator.

    Notably raised when an operator that *must* apply to a fixture cannot — for
    example the setpoint operators against a clause with no setpoint.  The
    catalogue declares which fixtures each class applies to, so a mismatch is a
    declaration error and not a run-time surprise to be skipped.
    """


class OperatorInapplicable(MutationError):
    """This operator has nothing to do to this revision, and says so.

    Distinct from :class:`FixtureError`: inapplicability is legal when the
    catalogue does not claim the pairing.  The runner records it as *no trial*
    rather than as a survived mutant, because a mutation that was never applied
    is not evidence about detection in either direction.
    """


class UnpopulatedClass(MutationError):
    """A catalogue class produced no trial at all across the whole fixture set.

    This is the failure the ``done_when`` names — "every KILL class and every
    SURVIVE class has at least one fixture and one recorded result" — and it is
    an exception rather than a warning because a class that silently contributes
    nothing makes the published aggregate a statement about a smaller catalogue
    than the one the artefact claims.
    """
