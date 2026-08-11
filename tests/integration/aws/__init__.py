# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Live-AWS integration tests: the tier that is allowed to spend money and cross a wire.

Everything under this package asserts against **two** live services at once — Amazon
Bedrock in ``ap-southeast-2`` and CockroachDB Cloud in ``aws-ap-southeast-1`` — which is
the only place in the suite where that is true, and the reason it is its own tier.

**How a run without credentials is meant to end.**  Not with a green that means nothing.
Each live test carries ``requires_aws`` and/or ``requires_cluster`` so that
``pytest -m 'not requires_aws'`` **deselects** it — the run reports it was never
collected, which is a different sentence from "it passed".  When a live test *is*
collected and the credential is genuinely absent, it skips with a reason that names the
missing variable; it never swallows an exception and calls that a skip, because a skip
whose reason is "something went wrong" hides exactly the failure the tier exists to catch.

The hermetic assertions in this package — the ones that read a committed artefact and
check it says what it claims — carry no ``requires_*`` marker at all.  They run on a
stranger's machine, with no AWS account, against files in the repository, and they are
what stops ``evidence/aws/`` from drifting into decoration.
"""

from __future__ import annotations

__all__: list[str] = []
