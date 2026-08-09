# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Exceptions raised by the client-side CBM projector.

Each one mirrors a ``P0001`` the database raises, and the docstring names the
SQL that is the authority.  The Python raising early is a convenience for the
projector process; it is never the control.  If these classes were deleted the
refusals would be unchanged, which is the correct relationship between an
application and a gate.
"""

from __future__ import annotations


class CBMError(Exception):
    """Base for every fault the blame-mass projector can report."""


class CommitUnknown(CBMError):
    """The commit an account is being computed for does not exist.

    Mirrors ``0140a``'s::

        MAINLINE: cbm account refused — the commit it accounts for does not exist
    """


class ClosureNotMaterialised(CBMError):
    """A clause version in the first-parent commit has no blame closure row.

    Mirrors ``0140a``'s::

        MAINLINE: cbm account refused — blame closure not materialised for the
        first-parent commit

    P3, fail closed: a severity nobody has projected yet is not a severity of
    zero.  A zero here would shrink ``inherited``, and a smaller ``inherited``
    is a gate that opens.
    """

    def __init__(self, first_parent: bytes, missing: int) -> None:
        self.first_parent = first_parent
        self.missing = missing
        super().__init__(
            f"blame closure not materialised for {missing} clause version(s) in "
            f"first-parent commit {first_parent.hex()[:16]}"
        )


class GenerationNotDense(CBMError):
    """``account_gen`` is not ``previous + 1`` (or not ``0`` for the first).

    Mirrors ``0140a``'s::

        MAINLINE: cbm account generations must be dense and monotone

    MI26.  Without it a projector could re-file an old, favourable generation
    on top of a newer, damning one — and the newest generation is what
    ``z_cbm_gate`` and ``mainline_audit.v_cbm_ledger`` read.
    """

    def __init__(self, supplied: int, expected: int) -> None:
        self.supplied = supplied
        self.expected = expected
        super().__init__(f"account_gen {supplied} supplied where {expected} was required")
