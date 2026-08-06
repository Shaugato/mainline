# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""CAS Registry Number recognition, with the check digit actually checked.

A CAS number is ``NNNNNNN-NN-C``.  The final digit is a checksum: take every
digit of the first two groups, weight them 1, 2, 3, ... from the right, sum, and
take the result modulo 10.

Validating it is not pedantry — it is what stops the extractor from claiming
``2019-05-1`` (a date) or ``1910-146-2`` (a mangled regulation reference) as a
chemical identity anchor.  A false CAS anchor is an identity-class anchor, and
identity-class anchors *veto matches*, so a false one manufactures residue for a
clause nobody touched.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = ["CAS_PATTERN", "cas_check_digit", "is_valid_cas"]

CAS_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<![\d-])(\d{2,7})-(\d{2})-(\d)(?![\d-])")


def cas_check_digit(body: str) -> int:
    """The expected check digit for the digits of the first two groups."""
    if not body.isdigit():
        raise ValueError(f"CAS body must be digits, got {body!r}")
    return sum(int(digit) * weight for weight, digit in enumerate(reversed(body), start=1)) % 10


def is_valid_cas(first: str, second: str, check: str) -> bool:
    """``True`` iff the three groups form a checksum-valid CAS number."""
    if first.startswith("0"):
        # CAS numbers are not zero-padded; a leading zero means this is a date
        # or a part number that happens to share the shape.
        return False
    return cas_check_digit(first + second) == int(check)
