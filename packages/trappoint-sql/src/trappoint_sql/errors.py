# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The refusal vocabulary of ``trappoint render``.

Every class here is a *refusal to emit SQL*. That is the whole product of this
distribution: a render that refuses is the compile-time form of a gate that refuses,
and the message is read by someone who has just been told their vertical may not
generate a schema. So the messages are sentences, and each one names the offending
object.

``UsageError`` is separated from the rest because the CLI maps it to exit code ``2``
while every refusal maps to ``1`` — a wrapper must never mistake "you typed it wrong"
for "the binding is unbacked" and retry.
"""

from __future__ import annotations

__all__ = [
    "AttestationRefused",
    "AuthoritySourceRefused",
    "BindingInvalid",
    "RenderError",
    "RenderRefused",
    "TemplateRefused",
    "UsageError",
]


class RenderError(Exception):
    """Base class for everything this distribution raises deliberately."""


class UsageError(RenderError):
    """The invocation was wrong: a missing path, an unreadable file, a bad flag."""


class BindingInvalid(RenderError):
    """``vertical.toml`` does not satisfy ``spec/binding/vertical.schema.json``."""


class AuthoritySourceRefused(RenderError):
    """The Authority Source Contract refused the binding.

    Raised for `A-1` through `A-9` of ``spec/binding/authority-source.md``. This is the
    compile-time form of specification rule `P-2` and of adversarial finding `S1`: a
    projected gate column with no declared authority source never reaches a migration.
    """


class AttestationRefused(RenderError):
    """The ground-truth attestation is absent, stale in shape, or answers ``UNKNOWN``.

    Ruling `D5`: a capability under a `GT-*` check is a render-time switch, never a
    runtime branch. An unanswered capability therefore cannot reach rendered SQL — not
    as a fallback, not as a default, not as a warning.
    """


class TemplateRefused(RenderError):
    """A template violated a rule the renderer enforces over template sources."""


class RenderRefused(RenderError):
    """The rendered output was refused after generation.

    Covers the ``--check`` zero-diff assertion, duplicate output filenames across
    templates, banned tokens (ruling `D10`), and the grant covenant `R-1`.
    """
