# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fetch the two beacons that bound a checkpoint from below (ruling CU-4).

drand's quicknet round and a NIST Interoperable Randomness Beacon 2.0 pulse both go into
the checkpoint body **before it is signed**, which is why the beacon step is first in
:data:`mainline_anchor.ports.STEP_ORDER` and not one of ARCHITECTURE.md §7.3's five.

Two beacons, because only one of them is load-bearing offline:

* **drand quicknet** is ``bls-unchained-g1-rfc9380`` — BLS12-381 signatures on G1, which
  ``cryptography`` cannot verify at all. A verifier under the one-dependency floor can
  check the round-to-time arithmetic and the internal ``randomness == SHA-256(signature)``
  binding, and that is all. It is a lower bound a stranger can *sanity-check*, not one
  they can *verify*.
* **NIST 2.0** is RSA-PKCS#1 v1.5 over SHA-512 with an X.509 certificate, which
  ``cryptography`` verifies. It is the beacon the offline argument actually rests on.

Both are fetched. Neither is fabricated when unavailable: a checkpoint whose body shape
varies with beacon reachability produces two classes of checkpoint, and an opposing expert
gets to ask which class this one is. The beacon step is fatal in
:mod:`mainline_anchor.fanout` for exactly that reason — one shape, always.

**Endpoint paths are configuration, not constants.** The defaults below are the documented
public paths, but no live call has been made from the machine this package was written on,
so each is a constructor argument and a wrong default is a one-line deployment fix rather
than a code change. Anything this module could not verify says so here and in the README.
"""

from __future__ import annotations

import json
from typing import Any, Final

from trappoint_ledger.beacon import (
    DRAND_CHAIN_HASH_QUICKNET,
    DrandRound,
    NistPulse,
)

from mainline_anchor.ports import AnchorError, BeaconSnapshot, coerce_any_mapping

__all__ = [
    "DEFAULT_DRAND_URL_TEMPLATE",
    "DEFAULT_NIST_URL",
    "BeaconUnavailable",
    "HttpBeaconSource",
    "StaticBeaconSource",
]

#: drand's public HTTP API, formatted with the chain hash. **Unverified from this machine**
#: — see the module docstring. The League of Entropy also publishes mirrors
#: (``api2.drand.sh``, ``api3.drand.sh``, ``drand.cloudflare.com``); a deployment that
#: cares about availability points a second source at one of them.
DEFAULT_DRAND_URL_TEMPLATE: Final = "https://api.drand.sh/{chain_hash}/public/latest"

#: The NIST beacon's "most recent pulse" endpoint. **Unverified from this machine.**
DEFAULT_NIST_URL: Final = "https://beacon.nist.gov/beacon/2.0/pulse/last"

_HTTP_OK: Final = 200


class BeaconUnavailable(AnchorError):
    """A beacon could not be fetched, or answered with something unusable.

    Fatal by design one frame up. There is no fallback that produces a checkpoint of the
    same shape, and a checkpoint of a different shape is a question we would rather not
    be asked.
    """


class HttpBeaconSource:
    """Fetch a live drand round and NIST pulse over an injected transport.

    Implements :class:`~mainline_anchor.ports.BeaconPort`.
    """

    __slots__ = ("_chain_hash", "_drand_url", "_nist_url", "_timeout", "_transport")

    def __init__(
        self,
        transport: Any,
        *,
        chain_hash: str = DRAND_CHAIN_HASH_QUICKNET,
        drand_url_template: str = DEFAULT_DRAND_URL_TEMPLATE,
        nist_url: str = DEFAULT_NIST_URL,
        timeout: float = 5.0,
    ) -> None:
        """Bind a transport and the two endpoints.

        Args:
            transport: An :class:`~mainline_anchor.ports.HttpTransport`.
            chain_hash: The drand chain. Ruling CU-4 pins quicknet, because the offline
                round-to-time arithmetic is only valid for quicknet's genesis and period.
            drand_url_template: Formatted with ``chain_hash``.
            nist_url: The NIST pulse endpoint.
            timeout: Seconds, per request.
        """
        self._transport = transport
        self._chain_hash = chain_hash
        self._drand_url = drand_url_template.format(chain_hash=chain_hash)
        self._nist_url = nist_url
        self._timeout = timeout

    def snapshot(self) -> BeaconSnapshot:
        """Fetch both beacons.

        Returns:
            The snapshot that goes into the checkpoint body.

        Raises:
            BeaconUnavailable: If either beacon fails, answers non-200, returns
                non-JSON, or returns a round on a chain other than the pinned one.
        """
        return BeaconSnapshot(drand=self.drand_round(), nist=self.nist_pulse())

    def drand_round(self) -> DrandRound:
        """Fetch the latest drand round on the pinned chain."""
        payload = self._get_json(self._drand_url, "drand")
        try:
            round_object = DrandRound.from_api(payload, chain_hash=self._chain_hash)
        except Exception as exc:
            raise BeaconUnavailable(f"the drand round did not parse: {exc}") from exc
        if not round_object.randomness_binds_signature():
            # An internal-consistency check, not verification: anyone can mint a
            # self-consistent pair. It costs one SHA-256 and it catches a truncated or
            # mismatched response before those bytes are signed into a checkpoint that
            # can never be withdrawn.
            raise BeaconUnavailable(
                f"drand round {round_object.round_number} does not satisfy "
                "randomness == SHA-256(signature); the response is internally "
                "inconsistent and must not be signed into a checkpoint"
            )
        return round_object

    def nist_pulse(self) -> NistPulse:
        """Fetch the most recent NIST 2.0 pulse."""
        payload = self._get_json(self._nist_url, "NIST")
        try:
            return NistPulse.from_api(payload)
        except Exception as exc:
            raise BeaconUnavailable(f"the NIST pulse did not parse: {exc}") from exc

    def _get_json(self, url: str, what: str) -> dict[str, Any]:
        try:
            response = self._transport.request("GET", url, timeout=self._timeout)
        except AnchorError:
            raise
        except Exception as exc:
            raise BeaconUnavailable(f"the {what} beacon transport failed: {exc!r}") from exc
        if response.status != _HTTP_OK:
            raise BeaconUnavailable(f"the {what} beacon at {url} answered HTTP {response.status}")
        try:
            decoded = json.loads(response.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BeaconUnavailable(f"the {what} beacon returned non-JSON: {exc}") from exc
        return dict(coerce_any_mapping(decoded))


class StaticBeaconSource:
    """A fixed snapshot, for the byte-deterministic reference ledger and for tests.

    Implements :class:`~mainline_anchor.ports.BeaconPort`.

    ``evidence/reference-ledger`` must regenerate byte-for-byte on a stranger's machine
    (ruling CU-6), which a live beacon makes impossible. A fixture is therefore correct
    there and dishonest in production, so this class exists as a named, greppable type
    rather than as a flag on :class:`HttpBeaconSource`.
    """

    __slots__ = ("_snapshot",)

    def __init__(self, snapshot: BeaconSnapshot) -> None:
        """Hold the snapshot this source always returns."""
        self._snapshot = snapshot

    def snapshot(self) -> BeaconSnapshot:
        """Return the fixed snapshot."""
        return self._snapshot
