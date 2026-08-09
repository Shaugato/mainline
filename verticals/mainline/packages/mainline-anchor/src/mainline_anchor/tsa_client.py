# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""RFC 3161: build the request, post it, and read back only what this package checks.

The upper time bound in ARCHITECTURE.md §7.3 step 1 is a timestamp token from at least
two independent authorities. Getting one is three things: encode a ``TimeStampReq`` in
DER, POST it as ``application/timestamp-query``, and decode enough of the
``TimeStampResp`` to know whether it is a token over **our** digest.

**What this module does NOT do is verify the token**, and the boundary is ruling CU-8's.
Verifying a CMS ``SignedData`` — the signer's certificate, the chain to a trusted root,
the signature over ``TSTInfo`` — is verifier check 5, hand-rolled inside
``trappoint-verify`` over its own minimal DER reader, because ``cryptography`` has no CMS
verification API and adding ``asn1crypto`` would cost the one-dependency floor that makes
a stranger willing to run the verifier at all. Duplicating that here would put a second
implementation of the most security-sensitive parser in the repository into a package
nobody audits.

What *is* done here is the check that belongs at the boundary and nowhere else:

* the response's ``PKIStatus`` is ``granted`` (0) or ``grantedWithMods`` (1);
* ``TSTInfo.messageImprint.hashedMessage`` equals the digest we asked about — otherwise
  we have a valid timestamp over somebody else's bytes, which reads as evidence and is
  not;
* ``TSTInfo.messageImprint.hashAlgorithm`` is SHA-256, not something weaker the authority
  substituted;
* the nonce we sent is echoed, because RFC 3161 §2.4.2 requires it when the request
  carried one and its absence is how a replayed token gets in.

Every failure raises. A TSA that returns something unusable produces an
:class:`~mainline_anchor.ports.AnchorDebt` one frame up, in the fanout, where the
checkpoint is already indelible and the honest record is a debt row.

Dependency floor for this module: ``hashlib``, ``secrets``, ``urllib.request``,
``datetime``, ``re``. No ASN.1 library, no HTTP library.
"""

from __future__ import annotations

import re
import secrets
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final

from mainline_anchor.ports import AnchorError, HttpResponse, TimestampToken

__all__ = [
    "OID_SHA256",
    "TSA_CONTENT_TYPE",
    "TSA_RESPONSE_CONTENT_TYPE",
    "HttpTsaAuthority",
    "TsaRejected",
    "TsaResponseInvalid",
    "UrllibTransport",
    "build_timestamp_request",
    "parse_timestamp_response",
]

#: What an RFC 3161 request is posted as. Some authorities reject any other value.
TSA_CONTENT_TYPE: Final = "application/timestamp-query"
TSA_RESPONSE_CONTENT_TYPE: Final = "application/timestamp-reply"

OID_SHA256: Final = "2.16.840.1.101.3.4.2.1"
_OID_SIGNED_DATA: Final = "1.2.840.113549.1.7.2"
_OID_CT_TST_INFO: Final = "1.2.840.113549.1.9.16.1.4"

#: PKIStatus values RFC 3161 §2.4.2 defines as success.
_PKI_STATUS_GRANTED: Final = 0
_PKI_STATUS_GRANTED_WITH_MODS: Final = 1

_TAG_BOOLEAN: Final = 0x01
_TAG_INTEGER: Final = 0x02
_TAG_OCTET_STRING: Final = 0x04
_TAG_NULL: Final = 0x05
_TAG_OID: Final = 0x06
_TAG_GENERALIZED_TIME: Final = 0x18
_TAG_SEQUENCE: Final = 0x30
_TAG_SET: Final = 0x31
_TAG_CONTEXT_0: Final = 0xA0

_SHA256_BYTES: Final = 32
_INDEFINITE_LENGTH: Final = 0x80
_LONG_FORM_MASK: Final = 0x80
_BASE128_MASK: Final = 0x7F
_BASE128_CONTINUE: Final = 0x80
_OID_FIRST_ARC_MULTIPLIER: Final = 40
_HTTP_OK: Final = 200

_GENERALIZED_TIME = re.compile(
    r"\A(?P<y>\d{4})(?P<mo>\d{2})(?P<d>\d{2})(?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})"
    r"(?:\.(?P<frac>\d{1,6})\d*)?Z\Z"
)


class TsaRejected(AnchorError):
    """The authority answered, and the answer was a refusal.

    Attributes:
        status: The ``PKIStatus`` integer.
    """

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"the timestamp authority returned PKIStatus={status}: {detail}")
        self.status = status


class TsaResponseInvalid(AnchorError):
    """The authority answered with something this profile cannot accept."""


# ── DER encoding ──────────────────────────────────────────────────────────────────────


def _der_length(length: int) -> bytes:
    if length < _INDEFINITE_LENGTH:
        return bytes([length])
    body = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([_LONG_FORM_MASK | len(body)]) + body


def _der_tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _der_length(len(content)) + content


def _der_integer(value: int) -> bytes:
    """Encode a non-negative integer, with the leading zero DER requires when needed."""
    if value < 0:
        raise ValueError("this profile encodes no negative integers")
    if value == 0:
        return _der_tlv(_TAG_INTEGER, b"\x00")
    # (bit_length + 8) // 8 adds one byte exactly when the high bit of the first content
    # byte would otherwise be set, which is what keeps the value positive in two's
    # complement.
    width = (value.bit_length() + 8) // 8
    return _der_tlv(_TAG_INTEGER, value.to_bytes(width, "big"))


def _der_base128(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    chunks: list[int] = []
    while value:
        chunks.append(value & _BASE128_MASK)
        value >>= 7
    chunks.reverse()
    return bytes(chunk | _BASE128_CONTINUE for chunk in chunks[:-1]) + bytes([chunks[-1]])


def _der_oid(dotted: str) -> bytes:
    arcs = [int(part) for part in dotted.split(".")]
    if len(arcs) < 2:  # noqa: PLR2004 - an OID with one arc is not an OID
        raise ValueError(f"{dotted!r} is not an object identifier")
    body = _der_base128(_OID_FIRST_ARC_MULTIPLIER * arcs[0] + arcs[1])
    for arc in arcs[2:]:
        body += _der_base128(arc)
    return _der_tlv(_TAG_OID, body)


def _der_sequence(*parts: bytes) -> bytes:
    return _der_tlv(_TAG_SEQUENCE, b"".join(parts))


def build_timestamp_request(
    digest: bytes,
    *,
    nonce: int,
    cert_req: bool = True,
    policy_oid: str | None = None,
) -> bytes:
    """Encode an RFC 3161 ``TimeStampReq`` over a SHA-256 digest.

    ::

        TimeStampReq ::= SEQUENCE {
          version        INTEGER { v1(1) },
          messageImprint MessageImprint,
          reqPolicy      TSAPolicyId  OPTIONAL,
          nonce          INTEGER      OPTIONAL,
          certReq        BOOLEAN      DEFAULT FALSE,
          extensions     [0] IMPLICIT Extensions OPTIONAL }

    ``certReq`` is emitted only when true, because DER omits a field at its DEFAULT.

    Args:
        digest: The 32-byte SHA-256 over the signed checkpoint note.
        nonce: A positive integer echoed by the authority. Replay protection.
        cert_req: Ask the authority to include its signing certificate in the token, so
            that the bundle a stranger receives is self-contained.
        policy_oid: A specific TSA policy to request, or ``None`` for the default.

    Returns:
        The DER-encoded request.

    Raises:
        ValueError: If the digest is not 32 bytes or the nonce is not positive.
    """
    if len(digest) != _SHA256_BYTES:
        raise ValueError(
            f"this profile timestamps a SHA-256 digest; got {len(digest)} bytes. The "
            "digest is over the complete signed note, not over the body"
        )
    if nonce <= 0:
        raise ValueError("the nonce must be a positive integer")
    algorithm = _der_sequence(_der_oid(OID_SHA256), _der_tlv(_TAG_NULL, b""))
    imprint = _der_sequence(algorithm, _der_tlv(_TAG_OCTET_STRING, digest))
    parts = [_der_integer(1), imprint]
    if policy_oid is not None:
        parts.append(_der_oid(policy_oid))
    parts.append(_der_integer(nonce))
    if cert_req:
        parts.append(_der_tlv(_TAG_BOOLEAN, b"\xff"))
    return _der_sequence(*parts)


# ── DER reading ───────────────────────────────────────────────────────────────────────


def _read_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
    """Read one DER element.

    Returns:
        ``(tag, content, next_offset)``.

    Raises:
        TsaResponseInvalid: On a truncated element or an indefinite length, which BER
            allows and DER does not.
    """
    if offset >= len(data):
        raise TsaResponseInvalid(f"DER ended at offset {offset} where an element was expected")
    tag = data[offset]
    cursor = offset + 1
    if cursor >= len(data):
        raise TsaResponseInvalid("DER element has a tag and no length")
    first = data[cursor]
    cursor += 1
    if first == _INDEFINITE_LENGTH:
        raise TsaResponseInvalid("indefinite-length encoding is BER, not DER")
    if first & _LONG_FORM_MASK:
        count = first & _BASE128_MASK
        if cursor + count > len(data):
            raise TsaResponseInvalid("DER long-form length is truncated")
        length = int.from_bytes(data[cursor : cursor + count], "big")
        cursor += count
    else:
        length = first
    end = cursor + length
    if end > len(data):
        raise TsaResponseInvalid(
            f"DER element of tag 0x{tag:02X} claims {length} bytes and {len(data) - cursor} remain"
        )
    return tag, data[cursor:end], end


def _expect(data: bytes, offset: int, tag: int, what: str) -> tuple[bytes, int]:
    actual, content, nxt = _read_tlv(data, offset)
    if actual != tag:
        raise TsaResponseInvalid(f"expected {what} (tag 0x{tag:02X}), found tag 0x{actual:02X}")
    return content, nxt


def _read_oid(data: bytes, offset: int, what: str) -> tuple[str, int]:
    content, nxt = _expect(data, offset, _TAG_OID, what)
    if not content:
        raise TsaResponseInvalid(f"{what} is an empty object identifier")
    first = content[0]
    arcs = [first // _OID_FIRST_ARC_MULTIPLIER, first % _OID_FIRST_ARC_MULTIPLIER]
    value = 0
    for byte in content[1:]:
        value = (value << 7) | (byte & _BASE128_MASK)
        if not byte & _BASE128_CONTINUE:
            arcs.append(value)
            value = 0
    return ".".join(str(arc) for arc in arcs), nxt


def _read_integer(data: bytes, offset: int, what: str) -> tuple[int, int]:
    content, nxt = _expect(data, offset, _TAG_INTEGER, what)
    if not content:
        raise TsaResponseInvalid(f"{what} is a zero-length INTEGER")
    return int.from_bytes(content, "big", signed=True), nxt


def _read_generalized_time(data: bytes, offset: int) -> tuple[datetime, int]:
    content, nxt = _expect(data, offset, _TAG_GENERALIZED_TIME, "TSTInfo.genTime")
    text = content.decode("ascii", errors="replace")
    match = _GENERALIZED_TIME.match(text)
    if match is None:
        raise TsaResponseInvalid(
            f"genTime {text!r} is not the RFC 3161 §2.4.2 form YYYYMMDDHHMMSS[.f]Z; a "
            "timestamp with a local offset is a timestamp whose instant is an argument"
        )
    microsecond = int(match.group("frac").ljust(6, "0")) if match.group("frac") else 0
    return (
        datetime(
            int(match.group("y")),
            int(match.group("mo")),
            int(match.group("d")),
            int(match.group("h")),
            int(match.group("mi")),
            int(match.group("s")),
            microsecond,
            tzinfo=UTC,
        ),
        nxt,
    )


def parse_timestamp_response(der: bytes) -> bytes:
    """Return the ``TimeStampToken`` from a ``TimeStampResp``, or raise.

    Args:
        der: The complete response body.

    Returns:
        The ``ContentInfo`` DER of the token.

    Raises:
        TsaRejected: If ``PKIStatus`` is not granted or grantedWithMods.
        TsaResponseInvalid: If the response is malformed or carries no token.
    """
    body, _ = _expect(der, 0, _TAG_SEQUENCE, "TimeStampResp")
    status_info, after_status = _expect(body, 0, _TAG_SEQUENCE, "PKIStatusInfo")
    status, _ = _read_integer(status_info, 0, "PKIStatus")
    if status not in (_PKI_STATUS_GRANTED, _PKI_STATUS_GRANTED_WITH_MODS):
        raise TsaRejected(status, f"{len(status_info)} bytes of PKIStatusInfo returned")
    token = body[after_status:]
    if not token:
        raise TsaResponseInvalid(
            f"PKIStatus={status} claims success and the response carries no timeStampToken"
        )
    tag, _content, end = _read_tlv(token, 0)
    if tag != _TAG_SEQUENCE:
        raise TsaResponseInvalid(f"timeStampToken has tag 0x{tag:02X}, not a ContentInfo SEQUENCE")
    return token[:end]


def _tst_info_from_token(token_der: bytes) -> bytes:
    """Walk ContentInfo → SignedData → EncapsulatedContentInfo → the TSTInfo bytes."""
    content_info, _ = _expect(token_der, 0, _TAG_SEQUENCE, "ContentInfo")
    content_type, after_type = _read_oid(content_info, 0, "ContentInfo.contentType")
    if content_type != _OID_SIGNED_DATA:
        raise TsaResponseInvalid(
            f"the token's contentType is {content_type}, not id-signedData {_OID_SIGNED_DATA}"
        )
    explicit, _ = _expect(content_info, after_type, _TAG_CONTEXT_0, "ContentInfo.content [0]")
    signed_data, _ = _expect(explicit, 0, _TAG_SEQUENCE, "SignedData")

    _version, cursor = _read_integer(signed_data, 0, "SignedData.version")
    _digest_algorithms, cursor = _expect(
        signed_data, cursor, _TAG_SET, "SignedData.digestAlgorithms"
    )
    encap, _ = _expect(signed_data, cursor, _TAG_SEQUENCE, "SignedData.encapContentInfo")

    econtent_type, after_econtent_type = _read_oid(encap, 0, "encapContentInfo.eContentType")
    if econtent_type != _OID_CT_TST_INFO:
        raise TsaResponseInvalid(
            f"the encapsulated content type is {econtent_type}, not id-ct-TSTInfo "
            f"{_OID_CT_TST_INFO}"
        )
    econtent, _ = _expect(encap, after_econtent_type, _TAG_CONTEXT_0, "eContent [0]")
    tst_info, _ = _expect(econtent, 0, _TAG_OCTET_STRING, "eContent OCTET STRING")
    return tst_info


def _parse_tst_info(tst_info_der: bytes) -> tuple[datetime, bytes, str, int | None]:
    """Return ``(genTime, hashedMessage, hashAlgorithmOid, nonce)`` from TSTInfo."""
    body, _ = _expect(tst_info_der, 0, _TAG_SEQUENCE, "TSTInfo")
    _version, cursor = _read_integer(body, 0, "TSTInfo.version")
    _policy, cursor = _read_oid(body, cursor, "TSTInfo.policy")
    imprint, cursor = _expect(body, cursor, _TAG_SEQUENCE, "TSTInfo.messageImprint")
    algorithm, after_algorithm = _expect(imprint, 0, _TAG_SEQUENCE, "messageImprint.hashAlgorithm")
    hash_oid, _ = _read_oid(algorithm, 0, "hashAlgorithm.algorithm")
    hashed_message, _ = _expect(imprint, after_algorithm, _TAG_OCTET_STRING, "hashedMessage")
    _serial, cursor = _read_integer(body, cursor, "TSTInfo.serialNumber")
    gen_time, cursor = _read_generalized_time(body, cursor)

    # accuracy (SEQUENCE), ordering (BOOLEAN) and nonce (INTEGER) are optional and appear
    # in that order; [0] tsa and [1] extensions follow. Walk by tag rather than by
    # position so that an omitted optional does not shift everything after it.
    nonce: int | None = None
    while cursor < len(body):
        tag, _content, nxt = _read_tlv(body, cursor)
        if tag == _TAG_INTEGER:
            nonce, cursor = _read_integer(body, cursor, "TSTInfo.nonce")
            break
        if tag in (_TAG_SEQUENCE, _TAG_BOOLEAN):
            cursor = nxt
            continue
        break
    return gen_time, hashed_message, hash_oid, nonce


class UrllibTransport:
    """The stdlib HTTP transport, shared by the TSA and beacon clients.

    Implements :class:`~mainline_anchor.ports.HttpTransport`. It lives in this module
    rather than in a third one because it is thirty lines and a package-wide ``http.py``
    would be a file whose only content is an import graph.

    HTTPS only unless the caller says otherwise, and the exception is spelled out at the
    call site rather than defaulted: a plaintext TSA request is a request an intermediary
    can answer.
    """

    __slots__ = ("_allow_http", "_user_agent")

    def __init__(
        self, *, user_agent: str = "mainline-anchor/0.1", allow_http: bool = False
    ) -> None:
        """Configure the transport.

        Args:
            user_agent: Sent on every request. Several public TSAs refuse a blank one.
            allow_http: Permit ``http://`` URLs. Off by default.
        """
        self._user_agent = user_agent
        self._allow_http = allow_http

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> HttpResponse:
        """Perform one request, returning 4xx/5xx as a response rather than raising.

        Args:
            method: ``GET`` or ``POST``.
            url: An ``https://`` URL, or ``http://`` when ``allow_http`` is set.
            body: The request body.
            headers: Extra request headers.
            timeout: Seconds.

        Returns:
            The response.

        Raises:
            AnchorError: On a disallowed scheme or a transport-level failure.
        """
        allowed = ("https://", "http://") if self._allow_http else ("https://",)
        if not url.startswith(allowed):
            raise AnchorError(
                f"refusing to fetch {url!r}: this transport permits {allowed}. A plaintext "
                "request for a time bound is a time bound an intermediary can choose"
            )
        request = urllib.request.Request(url, data=body, method=method)  # noqa: S310 - scheme checked above
        request.add_header("User-Agent", self._user_agent)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - scheme checked above
                return HttpResponse(
                    status=int(response.status),
                    body=response.read(),
                    headers={k.lower(): v for k, v in response.headers.items()},
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status=int(exc.code),
                body=exc.read(),
                headers={k.lower(): v for k, v in exc.headers.items()},
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AnchorError(f"{method} {url} failed at the transport: {exc!r}") from exc


class HttpTsaAuthority:
    """One RFC 3161 authority reached over HTTP.

    Implements :class:`~mainline_anchor.ports.TsaPort`.
    """

    __slots__ = (
        "_cert_req",
        "_name",
        "_nonce_source",
        "_policy_oid",
        "_timeout",
        "_transport",
        "_url",
    )

    def __init__(
        self,
        name: str,
        url: str,
        transport: object,
        *,
        cert_req: bool = True,
        policy_oid: str | None = None,
        timeout: float = 10.0,
        nonce_source: object = None,
    ) -> None:
        """Bind an authority.

        Args:
            name: A stable identifier. The fanout uses it to prove two tokens came from
                two authorities, so it must differ between them.
            url: The authority's endpoint.
            transport: An :class:`~mainline_anchor.ports.HttpTransport`.
            cert_req: Ask for the signing certificate inside the token.
            policy_oid: A specific policy to request, or ``None``.
            timeout: Seconds.
            nonce_source: A zero-argument callable returning a positive int. Defaults to
                a 63-bit value from :mod:`secrets`; injectable so a test is deterministic.
        """
        self._name = name
        self._url = url
        self._transport = transport
        self._cert_req = cert_req
        self._policy_oid = policy_oid
        self._timeout = timeout
        self._nonce_source = nonce_source if nonce_source is not None else _random_nonce

    @property
    def name(self) -> str:
        """Return the authority's stable identifier."""
        return self._name

    def timestamp(self, digest: bytes) -> TimestampToken:
        """Obtain a token over ``digest``, refusing anything that is not one.

        Args:
            digest: The 32-byte SHA-256 over the signed note.

        Returns:
            The token, with ``genTime`` and the echoed message imprint.

        Raises:
            TsaRejected: If the authority refused.
            TsaResponseInvalid: If the answer is not a usable token over our digest.
            AnchorError: On a transport failure.
        """
        nonce = int(self._nonce_source())  # type: ignore[operator]
        request = build_timestamp_request(
            digest, nonce=nonce, cert_req=self._cert_req, policy_oid=self._policy_oid
        )
        response = self._transport.request(  # type: ignore[attr-defined]
            "POST",
            self._url,
            body=request,
            headers={"Content-Type": TSA_CONTENT_TYPE, "Accept": TSA_RESPONSE_CONTENT_TYPE},
            timeout=self._timeout,
        )
        if response.status != _HTTP_OK:
            raise TsaResponseInvalid(
                f"{self._name} answered HTTP {response.status} with {len(response.body)} bytes"
            )
        token_der = parse_timestamp_response(response.body)
        gen_time, hashed_message, hash_oid, echoed = _parse_tst_info(
            _tst_info_from_token(token_der)
        )
        if hash_oid != OID_SHA256:
            raise TsaResponseInvalid(
                f"{self._name} timestamped a {hash_oid} imprint, not SHA-256 ({OID_SHA256})"
            )
        if hashed_message != digest:
            raise TsaResponseInvalid(
                f"{self._name} returned a token over {hashed_message.hex()}, not over our "
                f"digest {digest.hex()}: a valid timestamp over somebody else's bytes"
            )
        if echoed is None:
            raise TsaResponseInvalid(
                f"{self._name} omitted the nonce; RFC 3161 §2.4.2 requires it to be present "
                "in the response when the request carried one, and its absence is how a "
                "replayed token gets in"
            )
        if echoed != nonce:
            raise TsaResponseInvalid(f"{self._name} echoed nonce {echoed}, not the {nonce} we sent")
        return TimestampToken(
            authority=self._name,
            token_der=token_der,
            gen_time=gen_time,
            message_imprint=hashed_message,
        )


def _random_nonce() -> int:
    # 63 bits, forced odd so it can never be zero and never needs a leading-zero byte
    # decision it did not ask for.
    return secrets.randbits(63) | 1
