# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Where the bytes come from, and the preamble that makes them evidence.

ARCHITECTURE.md §8.6 calls this the **custody preamble**: before a document is read for
content, its bytes are pinned — an object key, an immutable version id, and a SHA-256 —
and that triple is what every later claim about the document joins back to. ``event``
carries two of the three columns for exactly this reason (``source_object_key``,
``source_sha256``), and a ``document_intake_finding`` carries the digest so a refusal can
be tied to bytes a reviewer can re-read.

Two ports, both Protocols, both with a real offline implementation:

===================== =========================================== ==========================
Port                  Offline                                      Cloud
===================== =========================================== ==========================
:class:`ObjectStore`  :class:`LocalObjectStore` (a directory)      :class:`S3ObjectStore`
:class:`TextExtractor` :class:`Utf8TextExtractor`                  :class:`TextractExtractor`
===================== =========================================== ==========================

**Digest before content, always.** :meth:`ObjectStore.fetch` returns
:class:`FetchedObject`, whose ``sha256`` is computed here from the bytes that arrived —
never taken from the caller, never taken from an S3 header. If the caller declared an
expected digest and it differs, the fetch is a refusal. A digest the inserter supplied is
the failure mode principle P2 exists to prevent, and it is the same argument one layer
down from the projection triggers.

.. rubric:: Honesty note — the cloud legs have never run

Neither :class:`S3ObjectStore` nor :class:`TextractExtractor` has been executed against
AWS. **AWS credentials are not valid on the build machine** (PL-3, 2026-08-09), so no test
in this repository may require one; both classes skip cleanly and both are behind the
``aws`` extra with the ``boto3`` import inside the method. What is claimed for them is
that the call shapes match the published APIs — ``GetObject`` with a ``VersionId``,
``DetectDocumentText`` with an ``S3Object`` — not that they have been observed to work.

:class:`TextractExtractor` implements the **synchronous** ``DetectDocumentText`` path
only. The asynchronous multi-page flow (``StartDocumentTextDetection`` +
``GetDocumentTextDetection``, with its job polling) is **not implemented here** and is
recorded as deferred rather than stubbed: a polling loop nobody has run against the
service is a worse lie than an absence.
"""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from .errors import SourceUnavailable, TextExtractionUnavailable
from .verbatim import text_digest

__all__ = [
    "CUSTODY_PREAMBLE_VERSION",
    "ExtractedText",
    "FetchedObject",
    "LocalObjectStore",
    "ObjectRef",
    "ObjectStore",
    "S3ObjectStore",
    "TextExtractor",
    "TextractExtractor",
    "Utf8TextExtractor",
    "custody_preamble",
]

#: Bumped when the preamble's shape changes, so a stored preamble can be read by the
#: reader that was written for it rather than by inference from a missing key.
CUSTODY_PREAMBLE_VERSION: Final[str] = "1"

_TEXT_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {"text/plain", "text/markdown", "text/csv", "application/json"}
)


@dataclass(frozen=True, slots=True)
class ObjectRef:
    """What to fetch: a key, and the immutable version of it.

    ``version_id`` is not optional in spirit. S3 Object Lock in COMPLIANCE mode pins a
    *version*, and a reference without one names whatever is current — which is the one
    thing an evidentiary reference must never do. It is typed as a string with an empty
    default so a local directory (which has no versions) can be modelled honestly, and
    :class:`S3ObjectStore` refuses an empty one.
    """

    object_key: str
    version_id: str = ""
    expected_sha256: str = ""

    def __post_init__(self) -> None:
        """Refuse a reference that names nothing."""
        if not self.object_key.strip():
            raise SourceUnavailable("an object reference with no key names nothing")


@dataclass(frozen=True, slots=True)
class FetchedObject:
    """Bytes that arrived, with the digest computed from them.

    Attributes:
        ref: what was asked for.
        body: the bytes.
        sha256: hex digest **computed here**, never supplied.
        media_type: as reported by the store, or guessed from the key.
    """

    ref: ObjectRef
    body: bytes
    sha256: str
    media_type: str

    @property
    def sha256_bytes(self) -> bytes:
        """The 32 raw bytes ``event.source_sha256`` holds."""
        return bytes.fromhex(self.sha256)


@dataclass(frozen=True, slots=True)
class ExtractedText:
    """The text a document yielded, and which extractor produced it.

    ``extracted_sha256`` is the digest every :class:`~mainline_archivist.verbatim.VerbatimSpan`
    indexes. Two extractors over one PDF produce two texts and therefore two digests, and
    a span is only meaningful against the one it was read from — which is why the
    extractor's name and version travel with the text rather than being assumed.
    """

    text: str
    extractor: str
    media_type: str
    page_count: int = 0

    @property
    def extracted_sha256(self) -> str:
        """Digest of the extracted text."""
        return text_digest(self.text)

    def __post_init__(self) -> None:
        """Refuse an empty extraction rather than ingesting a document with no content."""
        if not self.text.strip():
            raise TextExtractionUnavailable(
                f"{self.extractor} produced no usable text. An event whose narrative "
                f"would be empty fails CHECK narrative_stated at the database; refusing "
                f"here names the extractor instead of the constraint."
            )


@runtime_checkable
class ObjectStore(Protocol):
    """Fetch the pinned bytes of one object."""

    name: str

    def fetch(self, ref: ObjectRef) -> FetchedObject:
        """Return the bytes for ``ref``, with a digest computed from them."""
        ...


@runtime_checkable
class TextExtractor(Protocol):
    """Turn fetched bytes into text a model and a span can both index."""

    name: str

    def extract(self, obj: FetchedObject) -> ExtractedText:
        """Return the document's text."""
        ...


@dataclass(frozen=True, slots=True)
class LocalObjectStore:
    """A directory of documents. The offline path, and the one CI uses.

    Not a test double: the demo corpus and every conformance run read through this class,
    so the code path that computes the digest and refuses a mismatch is the same one the
    cloud path uses.
    """

    root: Path
    name: str = "local"

    def fetch(self, ref: ObjectRef) -> FetchedObject:
        """Read ``root / object_key`` and digest it.

        Raises:
            SourceUnavailable: the key escapes ``root``, the file is missing or
                unreadable, or the bytes do not match ``expected_sha256``.
        """
        root = self.root.resolve()
        candidate = (root / ref.object_key).resolve()
        if not candidate.is_relative_to(root):
            raise SourceUnavailable(
                f"object key {ref.object_key!r} resolves outside the store root; a key "
                f"that can traverse upwards is a key an attacker can aim"
            )
        try:
            body = candidate.read_bytes()
        except OSError as exc:
            raise SourceUnavailable(f"cannot read {candidate}: {exc}") from exc
        return _finish(ref, body, _guess_media_type(ref.object_key))


@dataclass(frozen=True, slots=True)
class S3ObjectStore:
    """``GetObject`` on an Object-Locked version. **Never executed** — see the module note.

    Attributes:
        bucket: the evidence bucket.
        client: an injected ``boto3`` S3 client. Built on first use when omitted, which
            is the only place ``boto3`` is imported.
    """

    bucket: str
    client: Any = None
    name: str = "s3"

    def fetch(self, ref: ObjectRef) -> FetchedObject:
        """Fetch one pinned object version.

        Raises:
            SourceUnavailable: no version id, ``boto3`` missing, the call fails, or the
                bytes do not match ``expected_sha256``.
        """
        if not ref.version_id:
            raise SourceUnavailable(
                f"{ref.object_key!r} has no version id. Object Lock pins a version; a "
                f"reference without one names whatever is current, which is precisely "
                f"what an evidentiary reference must not do."
            )
        client = self.client if self.client is not None else _s3_client()
        try:
            response = client.get_object(
                Bucket=self.bucket, Key=ref.object_key, VersionId=ref.version_id
            )
            body = response["Body"].read()
            media_type = str(response.get("ContentType") or _guess_media_type(ref.object_key))
        except SourceUnavailable:
            raise
        except Exception as exc:
            raise SourceUnavailable(
                f"s3://{self.bucket}/{ref.object_key} version {ref.version_id}: {exc}"
            ) from exc
        return _finish(ref, body, media_type)


@dataclass(frozen=True, slots=True)
class Utf8TextExtractor:
    """Decode text documents. The offline extractor, and a real one.

    Decoding is strict: a byte sequence that is not valid UTF-8 is a refusal rather than a
    replacement character, because a replacement character inside a quoted span would make
    a verbatim span disagree with the document it came from.
    """

    name: str = "utf8"

    def extract(self, obj: FetchedObject) -> ExtractedText:
        """Decode ``obj`` as UTF-8 text.

        Raises:
            TextExtractionUnavailable: the media type is not textual, or the bytes are
                not valid UTF-8.
        """
        if obj.media_type not in _TEXT_MEDIA_TYPES:
            raise TextExtractionUnavailable(
                f"{self.name} handles {sorted(_TEXT_MEDIA_TYPES)}, not "
                f"{obj.media_type!r}. Choose an extractor for this media type rather "
                f"than letting one guess."
            )
        try:
            text = obj.body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TextExtractionUnavailable(
                f"{obj.ref.object_key} is not valid UTF-8 ({exc}); decoding with "
                f"replacement characters would put bytes in a quoted span that are not "
                f"in the document"
            ) from exc
        return ExtractedText(text=text, extractor=self.name, media_type=obj.media_type)


@dataclass(frozen=True, slots=True)
class TextractExtractor:
    r"""``DetectDocumentText`` over an S3 object. **Never executed** — see the module note.

    Synchronous single-request path only. Lines are joined with ``\\n`` in the order
    Textract returns them, which is the order a reader sees.
    """

    bucket: str
    client: Any = None
    name: str = "textract:detect_document_text"

    def extract(self, obj: FetchedObject) -> ExtractedText:
        """Extract text for ``obj`` by S3 reference.

        Raises:
            TextExtractionUnavailable: ``boto3`` is missing, the object has no version
                id, or the service call fails.
        """
        if not obj.ref.version_id:
            raise TextExtractionUnavailable(
                f"{obj.ref.object_key!r} has no version id; Textract would read whatever "
                f"is current rather than the bytes whose digest is on the finding"
            )
        client = self.client if self.client is not None else _textract_client()
        document: dict[str, Any] = {
            "S3Object": {
                "Bucket": self.bucket,
                "Name": obj.ref.object_key,
                "Version": obj.ref.version_id,
            }
        }
        try:
            response = client.detect_document_text(Document=document)
        except Exception as exc:
            raise TextExtractionUnavailable(
                f"textract detect_document_text on {obj.ref.object_key}: {exc}"
            ) from exc
        blocks = response.get("Blocks") or []
        lines = [str(block.get("Text", "")) for block in blocks if block.get("BlockType") == "LINE"]
        pages = sum(1 for block in blocks if block.get("BlockType") == "PAGE")
        return ExtractedText(
            text="\n".join(lines),
            extractor=self.name,
            media_type=obj.media_type,
            page_count=pages,
        )


def custody_preamble(obj: FetchedObject, extracted: ExtractedText) -> dict[str, Any]:
    """Build the §8.6 record that ties every later claim to bytes somebody can re-read.

    Carried into ``agent_action_provenance`` and quoted in a ``document_intake_finding``.
    Both digests are present because they answer different questions: ``source_sha256``
    identifies the object under Object Lock, ``extracted_sha256`` identifies the text the
    spans index.
    """
    return {
        "preamble_version": CUSTODY_PREAMBLE_VERSION,
        "object_key": obj.ref.object_key,
        "version_id": obj.ref.version_id,
        "source_sha256": obj.sha256,
        "source_bytes": len(obj.body),
        "media_type": obj.media_type,
        "extractor": extracted.extractor,
        "extracted_sha256": extracted.extracted_sha256,
        "extracted_chars": len(extracted.text),
        "page_count": extracted.page_count,
    }


def _finish(ref: ObjectRef, body: bytes, media_type: str) -> FetchedObject:
    """Digest the bytes that arrived and refuse a declared digest that disagrees."""
    digest = hashlib.sha256(body).hexdigest()
    if ref.expected_sha256 and ref.expected_sha256.lower() != digest:
        raise SourceUnavailable(
            f"{ref.object_key!r} digests to {digest} but the reference declared "
            f"{ref.expected_sha256}. The bytes are authoritative and the declaration is "
            f"not: a fetch that accepted the caller's digest would make every finding "
            f"downstream a claim about a document nobody checked."
        )
    return FetchedObject(ref=ref, body=body, sha256=digest, media_type=media_type)


def _guess_media_type(object_key: str) -> str:
    """Media type from the key's suffix, defaulting to plain text."""
    guessed, _ = mimetypes.guess_type(object_key)
    return guessed or "text/plain"


def _s3_client() -> Any:
    """Build an S3 client, or refuse with the import failure.

    The import is inside the function so that a process ingesting from local disk never
    loads a cloud SDK — the same shape ``mainline_quarantine`` uses for its live
    guardrail leg.
    """
    try:
        import boto3
    except ImportError as exc:
        raise SourceUnavailable(
            "boto3 is not installed; install the 'aws' extra, or pass an injected "
            "client. The S3 leg is optional by design: no dated path may require an "
            "AWS credential (PL-3)."
        ) from exc
    return boto3.client("s3")


def _textract_client() -> Any:
    """Build a Textract client, or refuse with the import failure."""
    try:
        import boto3
    except ImportError as exc:
        raise TextExtractionUnavailable(
            "boto3 is not installed; install the 'aws' extra, or pass an injected "
            "client. Utf8TextExtractor is the offline path and it is real code."
        ) from exc
    return boto3.client("textract")
