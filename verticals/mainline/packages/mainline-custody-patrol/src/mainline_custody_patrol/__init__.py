# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``mainline-custody-patrol`` — custody of the custodian.

A tamper-evident log proves its own contents beautifully and, on its own, can say
nothing whatever about the platform underneath it. So an adversary who holds cloud-admin
rights does not attack the log: they change the platform. This package is the periodic,
hashed, Object-Locked answer to *"and who was watching the watchers"* — eight
attestations, collected on a schedule, each one canonicalised under RFC 8785, written to
S3 Object Lock COMPLIANCE in a second AWS account, and folded into the MAINLINE ledger
as a ``custodian_attestation`` leaf (``ARCHITECTURE.md`` §5.6, §8.6 I4; migration 0078).

The eight kinds:

======================= ==================================================================
``ccloud_audit``        the CockroachDB Cloud audit stream — the record an admin does not
                        author, and therefore the one in which a ``DROP TRIGGER`` shows up
``ccloud_backup``       backup inventory and retention, from the same CLI
``inspect_database``    the cluster's own index-consistency reporting
``schema_fingerprint``  the normalised, order-stable digest of the whole schema
``trigger_definitions`` the self-attesting gate: what the triggers ACTUALLY are, not what
                        the migrations said they would be (verifier check 11)
``kms_key_policy``      who may use, disable or schedule deletion of the log signing key
``s3_object_lock``      the retention mode and period actually configured on the bucket
``iam_snapshot``        who could have done any of the above
======================= ==================================================================

**Threat tiers this defeats, stated exactly.** T1 (a rogue DBA with arbitrary SQL) and
T2 (a cloud-org admin) are raised in cost, because the evidence about what they did
leaves their reach within one patrol interval. **T3 — a principal inside the Cockroach
Labs or AWS storage path — is not defeated by anything in this package**, and that
sentence is here rather than in a footnote because saying it first is the only version
of it that helps a customer.

**What is honest about today's state.** AWS credentials are not valid on any machine in
this build and there is no CockroachDB Cloud organisation attached to it. Every external
capability is therefore a :class:`typing.Protocol` with a fixture-backed fake that
asserts the *exact* call shape the live path will make — ``object_lock_mode="COMPLIANCE"``,
a retention date in the future, a store that reports back its own digest — so the first
live run fails loudly rather than succeeding wrongly. A collector that cannot run
produces a :class:`~mainline_custody_patrol.collect.Refusal` and the run reports itself
INCOMPLETE. **An unrun patrol is never reportable as a clean one**, and that is the one
property of this package that everything else is arranged around.
"""

from __future__ import annotations

from typing import Final

from .ccloud import (
    CcloudFieldMissing,
    CcloudFold,
    CcloudPage,
    CcloudPaginationUnresolved,
    CcloudShim,
    CcloudUnavailable,
    FixtureCcloud,
    PageCursor,
    audit_list,
    backup_list,
    require_field,
    require_sequence,
    resolve_shim,
    rfc3339,
)
from .collect import (
    ATTESTATION_KINDS,
    COMPLIANCE,
    INSERT_CUSTODIAN_ATTESTATION_SQL,
    LEDGER_ENTRY_KIND,
    Attestation,
    CloudControlPlane,
    CollectionRefused,
    CustodyPatrol,
    FixtureCloudControlPlane,
    InMemoryObjectStore,
    LeafLocator,
    LedgerSink,
    ObjectStore,
    ObjectStoreRefused,
    PatrolRun,
    PsycopgLeafLocator,
    Refusal,
    StoredObject,
    k2_migration_attestation,
    write_k2_migration_attestation,
)
from .fingerprint import (
    DEFAULT_SCHEMA_PREFIXES,
    FetchOutcome,
    FingerprintUnstable,
    InspectReport,
    PsycopgSqlSource,
    SchemaFingerprint,
    SqlSource,
    TriggerDefinitions,
    inspect_database,
    schema_fingerprint,
    stable_schema_fingerprint,
    trigger_definitions,
)

__version__: Final = "0.1.0"

__all__ = [
    "ATTESTATION_KINDS",
    "COMPLIANCE",
    "DEFAULT_SCHEMA_PREFIXES",
    "INSERT_CUSTODIAN_ATTESTATION_SQL",
    "LEDGER_ENTRY_KIND",
    "Attestation",
    "CcloudFieldMissing",
    "CcloudFold",
    "CcloudPage",
    "CcloudPaginationUnresolved",
    "CcloudShim",
    "CcloudUnavailable",
    "CloudControlPlane",
    "CollectionRefused",
    "CustodyPatrol",
    "FetchOutcome",
    "FingerprintUnstable",
    "FixtureCcloud",
    "FixtureCloudControlPlane",
    "InMemoryObjectStore",
    "InspectReport",
    "LeafLocator",
    "LedgerSink",
    "ObjectStore",
    "ObjectStoreRefused",
    "PageCursor",
    "PatrolRun",
    "PsycopgLeafLocator",
    "PsycopgSqlSource",
    "Refusal",
    "SchemaFingerprint",
    "SqlSource",
    "StoredObject",
    "TriggerDefinitions",
    "__version__",
    "audit_list",
    "backup_list",
    "inspect_database",
    "k2_migration_attestation",
    "require_field",
    "require_sequence",
    "resolve_shim",
    "rfc3339",
    "schema_fingerprint",
    "stable_schema_fingerprint",
    "trigger_definitions",
    "write_k2_migration_attestation",
]
