# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The deterministic OPC container: a ``.docx`` is a zip, and a zip is where reproducibility dies.

Decision **D4** says ``.docx`` output is byte-reproducible.  Four mechanisms in an ordinary zip
writer defeat that, and this module removes all four rather than mitigating them.

1. **Wall-clock member timestamps.**  ``ZipInfo(name)`` defaults ``date_time`` to
   ``time.localtime()``; ``python-docx``'s ``_ZipPkgWriter`` calls ``writestr(name, blob)`` with a
   bare string and inherits exactly that.  Every member written here is stamped
   ``(1980, 1, 1, 0, 0, 0)`` — the DOS epoch, the earliest the format can express, chosen because
   it is a constant nobody will be tempted to "improve" into a document date.  The document's own
   date belongs in ``docProps/core.xml`` where a reader can see it, not in zip metadata where
   they cannot.
2. **Emission order.**  Members are written in ``sorted()`` order over their part names.  Python
   sorts ``str`` by code point with no locale involvement, so ``[Content_Types].xml`` (``0x5B``)
   sorts before ``_rels/.rels`` (``0x5F``) before ``docProps/`` before ``word/`` on every
   platform.  That the OPC-required part lands first is a consequence of sorting, not a special
   case — and it is asserted below rather than assumed.
3. **Compression.**  ``ZIP_STORED``, always.  DEFLATE output is a function of the *zlib build*,
   not only of the input and the level: several distributions now ship zlib-ng, and two
   conforming implementations may emit different byte streams for identical input at identical
   level.  Pinning a level does not pin an implementation.  Storing costs a few hundred kilobytes
   across the whole fixture tree and buys an equality that holds across operating systems, Python
   versions and zlib versions — which is precisely the equality the brief asks for.  OPC permits
   stored parts; Word opens them without complaint.
4. **Host metadata.**  ``create_system`` defaults to 3 (Unix) on POSIX and 0 (MS-DOS) on Windows,
   and the value lands in the central directory; ``external_attr`` then carries the umask.  Both
   are pinned to 0, along with ``create_version``/``extract_version``, the flag bits, the extra
   field and the archive comment.

**Verified how far.**  Two in-process renders, two subprocess renders and the committed bytes are
compared by :mod:`mainline_corpus.docx.verify` on demand.  Cross-OS equality is *engineered* here
and must be *asserted* by a CI matrix job this worker does not own; nothing in this module claims
that job exists or is green.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping
from typing import Final

__all__ = [
    "FIXED_DATE_TIME",
    "OPC_FIRST_PART",
    "PackageError",
    "read_package",
    "write_package",
]

#: The DOS epoch, on every member of every package this module writes.
FIXED_DATE_TIME: Final[tuple[int, int, int, int, int, int]] = (1980, 1, 1, 0, 0, 0)

#: The part an OPC reader looks for first.  Asserted in :func:`write_package`, not assumed.
OPC_FIRST_PART: Final[str] = "[Content_Types].xml"


class PackageError(ValueError):
    """A part set is not a well-formed OPC package, or a container is not readable as one."""


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=FIXED_DATE_TIME)
    info.compress_type = zipfile.ZIP_STORED
    # 0 == MS-DOS/OS-2.  With create_system 3, `external_attr` carries Unix permission bits,
    # which differ between a developer laptop and a CI runner with a different umask.
    info.create_system = 0
    info.create_version = 20
    info.extract_version = 20
    info.external_attr = 0
    info.internal_attr = 0
    info.flag_bits = 0
    info.extra = b""
    info.comment = b""
    return info


def write_package(parts: Mapping[str, bytes]) -> bytes:
    """Serialise ``parts`` into a byte-reproducible OPC (``.docx``) container.

    ``parts`` maps a part name — ``"word/document.xml"``, always forward-slashed and never built
    with ``os.path`` — to its exact bytes.  The same mapping always produces the same output, on
    any platform, in any process, at any time.
    """
    if not parts:
        raise PackageError("an OPC package with no parts is not a document")
    for name in parts:
        if "\\" in name:
            raise PackageError(
                f"part name {name!r} contains a backslash. OPC part names are forward-slashed "
                "URIs; a Windows path separator here would produce a package a Linux reader "
                "cannot open and a digest that differs per platform."
            )
        if name.startswith("/") or ".." in name.split("/"):
            raise PackageError(f"part name {name!r} is not a relative OPC part name")
    if OPC_FIRST_PART not in parts:
        raise PackageError(
            f"the package has no {OPC_FIRST_PART}; without it the container is not an OPC "
            "package and Word will report it as corrupt on a judge's laptop rather than in CI"
        )
    ordered = sorted(parts)
    if ordered[0] != OPC_FIRST_PART:
        # Cannot happen for the fixed part set, and is checked anyway: the day someone adds a
        # part whose name sorts before '[', the failure should be this sentence.
        raise PackageError(
            f"{OPC_FIRST_PART} must be the first member; sorted order put {ordered[0]!r} first"
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, mode="w", compression=zipfile.ZIP_STORED, allowZip64=False
    ) as archive:
        archive.comment = b""
        for name in ordered:
            archive.writestr(_zip_info(name), parts[name])
    return buffer.getvalue()


def read_package(payload: bytes) -> dict[str, bytes]:
    """Read an OPC container back into ``{part name: bytes}``, in sorted part order.

    Used by the renderer to open a committed template, and by ``probe`` to report what a produced
    document *says* rather than what the generator believed it had written.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return {
                info.filename: archive.read(info)
                for info in sorted(archive.infolist(), key=lambda item: item.filename)
            }
    except zipfile.BadZipFile as exc:
        raise PackageError(f"not a zip container: {exc}") from exc
