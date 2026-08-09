# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Package data shipped inside the distribution.

Only ``skills.lock.json`` lives here. It is a package resource rather than a file beside
the Dockerfile because the lock has to travel with the code that verifies it: a container
image whose lock and whose verifier came from different commits pins nothing.
"""
