# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Where the DSN comes from, and the refusal that runs before anything else.

Two jobs, and the second one is the interesting one.

**One.** Find the connection string. Five spellings are honoured, in a fixed order,
because five already exist in this repository: ``MAINLINE_GATE_DSN`` is this service's
own, and ``MAINLINE_TEST_DSN`` / ``TRAPPOINT_DSN`` / ``COCKROACH_URL`` / ``CRDB_URL``
are the four the test fixtures already read (quality-repair.md §1.4, measured: 28, 3,
19 and 17 occurrences). Inventing a sixth spelling would mean a developer who has
already exported one of the four gets an obscure failure instead of a connection.

**Two — and this is the part that is a claim rather than a convenience.**
:func:`load_config` **refuses to start** when any AWS or model-provider variable is
present in the environment it was handed. Not a warning; a raised
:class:`ModelEnvironmentPresent`.

The reason is that ARCHITECTURE.md §8.2's four enforcements are all statements about
*absence*, and absence is the one property that decays silently. E1 says the kernel task
role holds no Bedrock action. E2 says no route reaches a model endpoint. E3 says no
kernel source imports a model SDK. Each of those is asserted in CI against a committed
artefact. None of them can see a laptop, a container spec or a CI job that exported
``AWS_ACCESS_KEY_ID`` next to the gate service — and a process holding a usable
credential is a process whose isolation is a matter of trust rather than of
architecture. So the gate service asserts the fourth thing, at the only moment it can:
before it opens a connection.

There is deliberately **no override flag**. A flag would be the first thing set in the
one deployment where it mattered.

The environment is passed in rather than read from :data:`os.environ` at import time, so
a caller can be explicit about what the process is entitled to see and a test can assert
both directions without mutating global state.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from trappoint_core import RetryPolicy

__all__ = [
    "DEFAULT_SCHEMA",
    "DEFAULT_SUBJECT_KIND",
    "DSN_VARIABLES",
    "MODEL_ENVIRONMENT_NAMES",
    "MODEL_ENVIRONMENT_PREFIXES",
    "GateConfig",
    "GateServiceError",
    "MissingDsn",
    "ModelEnvironmentPresent",
    "load_config",
    "model_environment",
    "retry_policy",
]

#: The MAINLINE binding's business schema. `mainline.merge_permit` is emitted into the
#: BINDING's schema rather than into `trappoint`, so two bindings on one cluster do not
#: render one procedure twice (migration 0117's header).
DEFAULT_SCHEMA: Final = "mainline"

#: The only subject kind this service merges. `change_request` is the other kind
#: TRAPPOINT gates; a service that merged both would need two procedures and two
#: refusal vocabularies, and this one is deliberately about permits.
DEFAULT_SUBJECT_KIND: Final = "permit"

#: Read in this order; the first non-empty value wins. The last four already exist in
#: this repository's fixtures, so a developer who exported one of them is not asked to
#: export a fifth.
#:
#: **Write ``127.0.0.1``, not ``localhost``.** Measured on this Windows host against the
#: local node, four connects each, everything else identical::
#:
#:     localhost   5060.8 ms   5022.5 ms
#:     127.0.0.1      5.5 ms      5.3 ms
#:
#: ``localhost`` resolves to ``::1`` first; the node does not answer there, so libpq
#: waits out the whole ``connect_timeout`` before falling back to IPv4. The gate's
#: server-side p95 budget is 120 ms (ARCHITECTURE.md §6.5), so a DSN spelled
#: ``localhost`` spends forty budgets in name resolution before the transaction starts —
#: and it does it once per attempt, because the retry unit is the whole transaction.
#: Nothing in this module rewrites the host: a service that quietly edited an operator's
#: connection string would be a service whose wire log did not match its configuration.
DSN_VARIABLES: Final[tuple[str, ...]] = (
    "MAINLINE_GATE_DSN",
    "MAINLINE_TEST_DSN",
    "TRAPPOINT_DSN",
    "COCKROACH_URL",
    "CRDB_URL",
)

#: A variable whose name starts with any of these is a model-provider or cloud-provider
#: variable. Prefix matching rather than an exact list because the failure being defended
#: against is a NEW variable — `AWS_WEB_IDENTITY_TOKEN_FILE` and
#: `AWS_CONTAINER_CREDENTIALS_FULL_URI` are both credentials and neither is the one
#: anybody thinks of when writing an exact list.
MODEL_ENVIRONMENT_PREFIXES: Final[tuple[str, ...]] = (
    "ANTHROPIC_",
    "AWS_",
    "AZURE_OPENAI_",
    "BEDROCK_",
    "COHERE_",
    "DEEPSEEK_",
    "FIREWORKS_",
    "GEMINI_",
    "GOOGLE_API",
    "GROQ_",
    "HUGGINGFACE",
    "LANGCHAIN_",
    "LANGSMITH_",
    "LLAMA_CLOUD_",
    "MISTRAL_",
    "OLLAMA_",
    "OPENAI_",
    "PERPLEXITY_",
    "REPLICATE_",
    "STRANDS_",
    "TOGETHER_API",
    "VERTEX_",
    "XAI_",
)

#: Exact names that carry no distinguishing prefix.
MODEL_ENVIRONMENT_NAMES: Final[frozenset[str]] = frozenset(
    {
        "CLAUDE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "HF_TOKEN",
        "MODEL_ENDPOINT_URL",
    }
)


class GateServiceError(Exception):
    """Base class for every condition this service refuses to start or run under."""


class MissingDsn(GateServiceError):
    """No connection string was found in any of :data:`DSN_VARIABLES`."""

    def __init__(self, environ_keys: int) -> None:
        """Name the variables that were looked for, and how many were seen at all."""
        super().__init__(
            "no CockroachDB connection string: set one of "
            + ", ".join(DSN_VARIABLES)
            + f" ({environ_keys} environment variables were visible, none of them these)"
        )
        self.tried = DSN_VARIABLES


class ModelEnvironmentPresent(GateServiceError):
    """The environment holds a credential or endpoint this process must not hold.

    Raised BEFORE a connection is opened, and carrying the variable names — never their
    values, because the message is written to a log and a log is read by people who are
    not entitled to the credential either.
    """

    def __init__(self, variables: tuple[str, ...]) -> None:
        """Build the refusal from the offending names."""
        super().__init__(
            "MAINLINE: gate service refused to start — the environment holds "
            f"{len(variables)} model/cloud provider variable(s): {', '.join(variables)}. "
            "ARCHITECTURE.md §8.2 asserts that no model can reach the merge gate; a gate "
            "process holding a usable credential makes that claim a matter of trust "
            "rather than of architecture. There is no override flag, on purpose. Unset "
            "them, or run the gate service in its own process."
        )
        self.variables = variables


def model_environment(environ: Mapping[str, str]) -> tuple[str, ...]:
    """Return the sorted names in *environ* that a gate process must not hold.

    Only the NAMES. A value is never read, never copied and never logged: knowing that
    ``AWS_SECRET_ACCESS_KEY`` is set is the whole finding, and reading it would put a
    credential in this process's memory for the sake of reporting that it should not be
    there.

    An empty value counts as absent. ``AWS_PROFILE=`` is how a wrapper script clears an
    inherited variable, and treating that as present would refuse the very fix.
    """
    found = [
        name
        for name, value in environ.items()
        if value
        and (name in MODEL_ENVIRONMENT_NAMES or name.startswith(MODEL_ENVIRONMENT_PREFIXES))
    ]
    return tuple(sorted(found))


@dataclass(frozen=True, slots=True)
class GateConfig:
    """Everything the service needs to open one gate transaction.

    Attributes:
        dsn: the CockroachDB connection string, verbatim from the environment.
        schema: the binding's business schema; composed into the procedure name by
            ``trappoint_core.gate.procedure_name`` and validated there.
        subject_kind: the gated subject; ``permit`` for this service.
        application_name: goes on the wire as the libpq ``application_name``, so a merge
            is identifiable in ``SHOW SESSIONS`` and in the cluster's own logs without
            correlating timestamps.
        connect_timeout_s: passed to libpq. Non-optional on purpose: quality-repair.md
            §1.4 measured a suite that hung rather than failed because fixtures connect
            without one, and a gate call that waits forever is a gate call that has
            stopped asserting anything.
        statement_timeout_ms: applied through libpq ``options`` at connect time, so it
            is in force for the first statement of the transaction rather than set by a
            statement inside it.
        max_attempts: the ``40001`` ladder's bound. Only ``40001`` is ever retried.
        base_delay_s: first backoff ceiling.
        cap_delay_s: largest backoff ceiling.
    """

    dsn: str
    schema: str = DEFAULT_SCHEMA
    subject_kind: str = DEFAULT_SUBJECT_KIND
    application_name: str = "mainline-gate-svc"
    connect_timeout_s: int = 5
    statement_timeout_ms: int = 5000
    max_attempts: int = 5
    base_delay_s: float = 0.02
    cap_delay_s: float = 0.5

    def __post_init__(self) -> None:
        """Refuse a configuration that could not produce a bounded gate call."""
        if not self.dsn:
            raise ValueError("dsn must not be empty")
        if self.connect_timeout_s < 1:
            raise ValueError("connect_timeout_s must be at least 1 second")
        if self.statement_timeout_ms < 1:
            raise ValueError("statement_timeout_ms must be positive")

    @property
    def libpq_options(self) -> str:
        """Return the libpq ``options`` string carrying the statement timeout.

        Measured on CockroachDB CCL v26.2.5: connecting with
        ``options='-c statement_timeout=5000'`` and then issuing ``SHOW
        statement_timeout`` returns ``5000``.
        """
        return f"-c statement_timeout={self.statement_timeout_ms}"

    def redacted_dsn(self) -> str:
        """Return the DSN with any userinfo removed, for logs and CLI output.

        ``postgresql://root:hunter2@host:26257/db`` becomes
        ``postgresql://host:26257/db``. A DSN in a log is the second most common way a
        password reaches a ticket.
        """
        scheme, separator, rest = self.dsn.partition("://")
        if not separator:
            return self.dsn
        _, at, hostpart = rest.rpartition("@")
        return f"{scheme}://{hostpart}" if at else self.dsn


def retry_policy(config: GateConfig) -> RetryPolicy:
    """Build the ``40001`` ladder from *config*.

    A function rather than a field so that :class:`GateConfig` stays a plain record of
    environment-derived values and the policy object is constructed where it is used.
    """
    return RetryPolicy(
        max_attempts=config.max_attempts,
        base_delay_s=config.base_delay_s,
        cap_delay_s=config.cap_delay_s,
    )


def load_config(
    environ: Mapping[str, str] | None = None,
    *,
    schema: str = DEFAULT_SCHEMA,
    subject_kind: str = DEFAULT_SUBJECT_KIND,
) -> GateConfig:
    """Read the configuration, or refuse to start.

    The model-environment check runs FIRST — before the DSN is even looked for — so a
    process that should not exist is refused for the reason that matters rather than for
    a missing connection string it would also have had.

    Args:
        environ: the environment to read. Defaults to :data:`os.environ`.
        schema: override the binding's schema; the live probe against a scratch database
            uses this, and it is validated by ``trappoint_core`` before it reaches SQL.
        subject_kind: override the gated subject kind.

    Returns:
        The configuration.

    Raises:
        ModelEnvironmentPresent: the environment holds a model or cloud credential.
        MissingDsn: no connection string in any of :data:`DSN_VARIABLES`.
    """
    source: Mapping[str, str] = os.environ if environ is None else environ

    offending = model_environment(source)
    if offending:
        raise ModelEnvironmentPresent(offending)

    for name in DSN_VARIABLES:
        value = source.get(name, "")
        if value:
            return GateConfig(dsn=value, schema=schema, subject_kind=subject_kind)
    raise MissingDsn(len(source))
