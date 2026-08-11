<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Live-AWS integration tests: the tier that is allowed to spend money and cross a wire.

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

---

## Why this directory is not a Python package

This tier carries no `__init__.py`, and must not grow one.

pytest names a test module after the highest directory that still holds an
`__init__.py`. With one here, this directory and `tests/unit/aws/` both claimed the
top-level module name `aws`, whichever imported second lost, and collection of the
whole suite aborted with

    ModuleNotFoundError: No module named 'aws.test_common_redaction'

That is not a warning: **a collection error stops the entire run**, so every one of
the 9,281 collected tests went unmeasured because of it. `tests/unit/aws/` keeps the
package name because its siblings under `tests/unit/` are packages too; no other
directory under `tests/integration/` is one.

The prose that used to live in the module docstring is above, unchanged.
