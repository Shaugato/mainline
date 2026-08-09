# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# THE STEWARD — headless Claude Code over the CockroachDB Agent Skills, on a schedule.
#
# Build from the REPOSITORY ROOT, for arm64:
#
#     docker build --platform linux/arm64 \
#       -f verticals/mainline/apps/steward/Dockerfile -t mainline-steward:dev .
#
# ARM64 because §8.3 puts every Fargate task on ARM64 (Graviton), and because a task
# whose architecture differs between the image and the task definition fails at start
# with an error that names neither.
#
# ── THE BASE IS PINNED BY DIGEST, AND HERE IS EXACTLY WHAT THAT DIGEST IS ────────────
#
# `node:24-trixie-slim`, multi-architecture index digest
# sha256:0711b541c1c33a8a530ac4f0d391baa9a15b3d804695b1b24a47daa5fb60e74d, whose arm64
# manifest is sha256:8525258f39fa3365fcf9a9d01e85458c7280ad00bd30c5e67655311262257e9e.
# Both were read from Docker Hub's registry API on 2026-08-04. THEY WERE NOT PULLED FROM
# THE BUILD MACHINE — no image was fetched here — so the honest status is "recorded, not
# verified". The failure mode of a wrong digest is the correct one: the daemon refuses a
# digest that does not resolve, so a wrong pin cannot silently produce a different image.
#
# A Node base rather than a Python one because Claude Code is an npm distribution and
# Debian trixie ships Python 3.13 in `python3`. The alternative — a Python base plus a
# NodeSource repository — adds a third-party apt source to an image that signs nothing but
# reads an evidentiary database. `RUN` step 2 asserts the Python version rather than
# assuming it, so a base-image change that moved Python breaks the build instead of the
# attestation.
FROM node:24-trixie-slim@sha256:0711b541c1c33a8a530ac4f0d391baa9a15b3d804695b1b24a47daa5fb60e74d

# Pinned explicitly. The version that actually ran is ALSO recorded into every
# attestation from `claude --version`, so a drift between this pin and the running binary
# is visible in the evidence rather than only in a build log.
ARG CLAUDE_CODE_VERSION=2.1.221

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    STEWARD_HOME=/opt/steward \
    PATH=/opt/steward/venv/bin:$PATH

# 1. Architecture assertion, then the four packages this image needs and no others.
#    `git` checks out the pinned skills commit; `ca-certificates` is what makes TLS to
#    cockroachlabs.cloud and to api.anthropic.com possible; `python3-venv` because Debian
#    marks the system interpreter externally-managed (PEP 668) and installing into it is
#    the kind of shortcut that later breaks a security update.
RUN set -eux; \
    test "$(dpkg --print-architecture)" = "arm64" \
      || { echo "this image is arm64 only; build with --platform linux/arm64" >&2; exit 1; }; \
    apt-get update; \
    apt-get install --no-install-recommends -y \
      ca-certificates \
      git \
      python3 \
      python3-venv; \
    rm -rf /var/lib/apt/lists/*

# 2. Assert the interpreter, then build the virtual environment.
RUN set -eux; \
    python3 --version; \
    python3 -c 'import sys; assert sys.version_info[:2] == (3, 13), sys.version'; \
    python3 -m venv "${STEWARD_HOME}/venv"; \
    "${STEWARD_HOME}/venv/bin/pip" install --no-cache-dir --upgrade pip

# 3. Claude Code, at a pinned version. `--ignore-scripts` because a postinstall script in
#    a dependency is arbitrary code running as root in an image that will hold a database
#    credential.
RUN set -eux; \
    npm install -g --ignore-scripts "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"; \
    npm cache clean --force; \
    claude --version

# 4. The Python distributions, installed from local paths in ONE pip invocation so that
#    `mainline-steward`'s workspace dependencies resolve against the copies beside it
#    rather than against an index. Nothing here is fetched from PyPI except `httpx`,
#    `pyyaml` and their transitive dependencies — there is no pgwire driver, no AWS SDK
#    and no model SDK in this image, and `test_no_other_write_path.py` is what keeps it
#    that way.
COPY packages/trappoint-jcs /src/packages/trappoint-jcs
COPY packages/mainline-mcp /src/packages/mainline-mcp
COPY verticals/mainline/packages/mainline-steward /src/verticals/mainline/packages/mainline-steward
RUN set -eux; \
    "${STEWARD_HOME}/venv/bin/pip" install --no-cache-dir \
      /src/packages/trappoint-jcs \
      /src/packages/mainline-mcp \
      /src/verticals/mainline/packages/mainline-steward; \
    "${STEWARD_HOME}/venv/bin/mainline-steward" --help >/dev/null; \
    rm -rf /src

# 5. The application: the calendar, the prompts, the runbooks, the two configuration files.
#    `spec/` carries the audit-surface contract, which is the source of EVERY statement a
#    run issues. It is copied whole rather than by file so that a contract landing later
#    in the build order does not need an edit here; if it is absent at run time the run
#    refuses and names the worker who owns it.
COPY verticals/mainline/apps/steward/ ${STEWARD_HOME}/app/
COPY spec/ ${STEWARD_HOME}/spec/

# 6. The writable surfaces, owned by the unprivileged user the task runs as. `run/` holds
#    the transcript and the canonical attestation bytes; `state/` holds the occurrence
#    claims; `skills/` is where the pinned commit is checked out. All three are DENIED to
#    the Claude Code session by settings.json — the session reads the skills through
#    `.claude/skills`, and must never read the state directory that decides whether its
#    own run is a duplicate.
RUN set -eux; \
    mkdir -p ${STEWARD_HOME}/run ${STEWARD_HOME}/state ${STEWARD_HOME}/skills \
             ${STEWARD_HOME}/app/.claude/skills; \
    chmod +x ${STEWARD_HOME}/app/entrypoint.sh; \
    chown -R node:node ${STEWARD_HOME}

USER node
WORKDIR /opt/steward/app

# The container answers exactly one occurrence and exits. There is no daemon, no loop and
# no in-container scheduler: EventBridge Scheduler is the entire calendar (§8.5), and a
# second calendar inside the image would be a second answer to "when did this run".
ENTRYPOINT ["/opt/steward/app/entrypoint.sh"]
