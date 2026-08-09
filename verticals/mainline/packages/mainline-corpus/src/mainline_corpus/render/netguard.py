# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The offline guard: ``--offline`` is enforced, not documented.

``corpusgen render`` defaults to offline (D2).  A default that is merely a default is a
promise; a default that raises when broken is a control.  The difference matters because the
judge-facing claim is *"this corpus rebuilds with zero Bedrock calls"*, and the only way to
know that is true is for the process to be unable to make one.

What is patched, and why each is necessary:

* ``socket.socket.connect`` / ``connect_ex`` — the actual egress. botocore's HTTP pool ends up
  here for every request.
* ``socket.create_connection`` — the convenience wrapper does not route through the bound
  method on some code paths, so patching only the method leaves a hole.
* ``socket.getaddrinfo`` / ``gethostbyname`` — resolution is itself network traffic to a
  resolver.  A run that resolved a hostname and then failed to connect would still have leaked
  the fact that it ran.
* ``ssl.SSLContext.wrap_socket`` is deliberately **not** patched: it wraps an already-connected
  socket, so blocking ``connect`` is strictly upstream of it.

Loopback is not exempt.  Nothing in stage 2 talks to a local service, and an exemption is a
hole in the shape of ``localhost:8080``.

This is *not* ``pytest-socket``.  That guard belongs to the test session and is installed by
``tests/unit/corpus/conftest.py``.  This one is armed inside the production command, where it
is the thing that makes the claim on the command line true.

The guard is a context manager and is re-entrant by counting, so ``arm()`` inside ``arm()`` is
safe and the innermost exit does not disarm the outer scope.  ``allow()`` is the single, named
hole: only :mod:`mainline_corpus.render.bedrock` uses it, and only under ``--allow-live``.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Final

__all__ = ["OfflineViolation", "allow", "arm", "is_armed"]


class OfflineViolation(RuntimeError):
    """The process tried to open a network connection while the offline guard was armed."""


_LOCK: Final[threading.Lock] = threading.Lock()
_STATE: Final[dict[str, int]] = {"depth": 0, "allow_depth": 0}

_MESSAGE: Final[str] = (
    "offline guard: outbound network access is refused during `corpusgen render`.\n"
    "  attempted: {what}\n"
    "The corpus must rebuild from the committed cache with zero Bedrock calls; that claim is\n"
    "enforced here rather than asserted in a README. Pass --allow-live to reach Bedrock, which\n"
    "opens the guard only for the duration of a bedrock-tier call and records `bedrock` in the\n"
    "renderer census, where the honesty card will report it."
)


def _refuse(what: str) -> None:
    if _STATE["allow_depth"] > 0:
        return
    raise OfflineViolation(_MESSAGE.format(what=what))


def is_armed() -> bool:
    """Report whether the guard is currently installed."""
    return bool(_STATE["depth"])


#: The five originals, captured once at import.  Captured here rather than at ``arm()`` time so
#: that a second ``arm()`` can never save an already-guarded function and then "restore" the
#: guard permanently — a bug that would leave a long-lived process unable to open a socket
#: after the render finished, with no error to explain it.
_REAL_CONNECT: Final[Callable[..., Any]] = socket.socket.connect
_REAL_CONNECT_EX: Final[Callable[..., Any]] = socket.socket.connect_ex
_REAL_CREATE_CONNECTION: Final[Callable[..., Any]] = socket.create_connection
_REAL_GETADDRINFO: Final[Callable[..., Any]] = socket.getaddrinfo
_REAL_GETHOSTBYNAME: Final[Callable[..., Any]] = socket.gethostbyname


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    _refuse(f"socket.connect({address!r})")
    return _REAL_CONNECT(self, address)


def _guarded_connect_ex(self: socket.socket, address: Any) -> Any:
    _refuse(f"socket.connect_ex({address!r})")
    return _REAL_CONNECT_EX(self, address)


def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
    _refuse(f"socket.create_connection({address!r})")
    return _REAL_CREATE_CONNECTION(address, *args, **kwargs)


def _guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
    _refuse(f"socket.getaddrinfo({host!r}, {port!r})")
    return _REAL_GETADDRINFO(host, port, *args, **kwargs)


def _guarded_gethostbyname(host: Any) -> Any:
    _refuse(f"socket.gethostbyname({host!r})")
    return _REAL_GETHOSTBYNAME(host)


def _swap(
    connect: Callable[..., Any],
    connect_ex: Callable[..., Any],
    create_connection: Callable[..., Any],
    getaddrinfo: Callable[..., Any],
    gethostbyname: Callable[..., Any],
) -> None:
    """Install one set of five.

    ``setattr`` for the three module-level functions because monkey-patching a stdlib module is
    what this file does on purpose, and a direct assignment trips the type checker on every line
    for a reason that does not apply here.
    """
    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    setattr(socket, "create_connection", create_connection)  # noqa: B010
    setattr(socket, "getaddrinfo", getaddrinfo)  # noqa: B010
    setattr(socket, "gethostbyname", gethostbyname)  # noqa: B010


def _install() -> None:
    _swap(
        _guarded_connect,
        _guarded_connect_ex,
        _guarded_create_connection,
        _guarded_getaddrinfo,
        _guarded_gethostbyname,
    )


def _restore() -> None:
    _swap(
        _REAL_CONNECT,
        _REAL_CONNECT_EX,
        _REAL_CREATE_CONNECTION,
        _REAL_GETADDRINFO,
        _REAL_GETHOSTBYNAME,
    )


@contextmanager
def arm() -> Iterator[None]:
    """Arm the guard for the duration of the block.  Re-entrant."""
    with _LOCK:
        _STATE["depth"] += 1
        first = _STATE["depth"] == 1
        if first:
            _install()
    try:
        yield
    finally:
        with _LOCK:
            _STATE["depth"] -= 1
            if _STATE["depth"] == 0:
                _restore()


@contextmanager
def allow(*, reason: str) -> Iterator[None]:
    """Open the single named hole in the guard.

    ``reason`` is required and unused by the control flow on purpose: it forces every call site
    to state, in the source, why it is allowed to reach the network.  There is exactly one call
    site — the ``bedrock`` tier under ``--allow-live`` — and a second one should have to argue
    for itself in code review.
    """
    if not reason:
        raise ValueError("netguard.allow() requires a reason")
    with _LOCK:
        _STATE["allow_depth"] += 1
    try:
        yield
    finally:
        with _LOCK:
            _STATE["allow_depth"] -= 1
