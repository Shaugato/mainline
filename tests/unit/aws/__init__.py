# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the AWS fleet's shared client contract.

**Nothing in this package touches AWS.**  No credentials, no network, no ``boto3``
import: ``scripts/aws/_common.py`` imports ``boto3`` and ``psycopg`` inside the functions
that need them precisely so that the two pieces every worker depends on for safety —
:func:`redact` and :func:`assert_in_region` — can be tested on a machine that has neither.

A redactor that is only exercised on the machine holding the secrets is a redactor whose
first real test is the leak.
"""
