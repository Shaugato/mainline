# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``mainline-steward`` — the command surface the Fargate entrypoint drives.

Five verbs, and the split between them is the deployment's:

* ``schedules`` — print the declared calendar. The infra lead's OpenTofu reads this to
  create the EventBridge Scheduler rules, so the container and the infrastructure are
  reading one file rather than agreeing by coincidence.
* ``prompt`` — print the rendered prompt for one occurrence, and its ``prompt_version``.
  The entrypoint pipes it into ``claude -p``.
* ``skills verify`` / ``skills record`` — check a checkout against the pins, or write the
  digests back into the lock once (the second is run by a human and its output committed;
  a lock that heals itself on every run pins nothing).
* ``attest`` — do the contracted reads, build the ``ops_attestation``, and write the one
  permitted row.

``attest`` exits **0** on an already-attested occurrence. EventBridge Scheduler is
at-least-once, so a redelivery that does nothing is correct behaviour and must not page
anybody; the reason is printed so an operator reading logs sees which it was.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from mainline_mcp.client import Client
from mainline_mcp.limits import MCP_ENDPOINT

from .attestation import BytesEncoding, Emitter
from .digest import tree_sha256
from .errors import OccurrenceAlreadyAttested, StewardError
from .findings import EVIDENCE_OF_REVIEW, sentence
from .prompts import render_prompt
from .run import PROMPT_SUFFIXES, RunConfig, StewardRun, read_allowed_tools
from .schedule import ScheduleBook, load_schedules
from .skills import SkillLock, default_lock, load_lock

EXIT_OK: Final = 0
EXIT_REFUSED: Final = 1
EXIT_USAGE: Final = 2

_APP_DIR_ENV: Final = "MAINLINE_STEWARD_APP_DIR"
_CONTRACT_ENV: Final = "MAINLINE_MCP_CONTRACT"
_API_KEY_ENV: Final = "CC_MCP_API_KEY"
_CLUSTER_ENV: Final = "MAINLINE_MCP_CLUSTER_ID"


def _default_app_dir() -> Path:
    return Path(os.environ.get(_APP_DIR_ENV, "/opt/steward/app"))


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _build_config(args: argparse.Namespace) -> RunConfig:
    app_dir = Path(args.app_dir)
    contract = (
        Path(args.contract)
        if args.contract
        else Path(_env(_CONTRACT_ENV, str(app_dir / "audit-surface.contract.yaml")))
    )
    return RunConfig(
        app_dir=app_dir,
        contract_path=contract,
        site_code=args.site_code or _env("MAINLINE_SITE_CODE"),
        mcp_cluster_id=args.cluster_id or _env(_CLUSTER_ENV),
        iam_role_arn=_env("MAINLINE_STEWARD_TASK_ROLE_ARN"),
        model_id=_env("MAINLINE_STEWARD_MODEL_ID", "au.anthropic.claude-opus-5"),
        inference_profile_arn=_env("MAINLINE_STEWARD_INFERENCE_PROFILE_ARN"),
        schema_version=_env("MAINLINE_SCHEMA_VERSION"),
        claude_code_version=_env("MAINLINE_STEWARD_CLAUDE_CODE_VERSION"),
        skills_root=Path(args.skills_root) if args.skills_root else None,
        transcript=Path(args.transcript) if args.transcript else None,
        out_dir=Path(args.out) if args.out else None,
        state_dir=Path(args.state_dir) if args.state_dir else None,
        ccloud_fixtures=Path(args.ccloud_fixtures) if args.ccloud_fixtures else None,
        dry_run=not args.send,
        skill_lock_path=Path(args.skill_lock) if args.skill_lock else None,
    )


def _client(args: argparse.Namespace) -> Client:
    api_key = _env(_API_KEY_ENV)
    cluster = args.cluster_id or _env(_CLUSTER_ENV)
    if not api_key or not cluster:
        raise StewardError(
            f"no Managed-MCP credential: set {_API_KEY_ENV} and {_CLUSTER_ENV}. The endpoint "
            f"is {MCP_ENDPOINT} and the service account is Cluster Operator with mcp:read "
            "plus insert_rows on mainline_meas.external_attestation and nothing else"
        )
    return Client.connect(api_key=api_key, cluster_id=cluster)


def _book(app_dir: Path) -> ScheduleBook:
    """Load the declarative calendar for an app directory."""
    return load_schedules(app_dir / "schedules.yaml")


def _cmd_schedules(args: argparse.Namespace) -> int:
    run = _book(Path(args.app_dir))
    if args.json:
        print(
            json.dumps(
                {
                    "timezone": run.default_timezone,
                    "schedules": [
                        {
                            "schedule_id": s.schedule_id,
                            "kind": str(s.kind),
                            "expression": s.expression,
                            "timezone": s.timezone,
                            "prompt": s.prompt,
                            "views": list(s.views),
                            "skills": list(s.skills),
                            "max_turns": s.max_turns,
                        }
                        for s in run
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return EXIT_OK
    for schedule in run:
        print(f"{schedule.schedule_id:24s} {schedule.expression:20s} {schedule.kind}")
        print(f"{'':24s} views: {', '.join(schedule.views)}")
        if schedule.skills:
            print(f"{'':24s} skills: {', '.join(schedule.skills)}")
    return EXIT_OK


def _cmd_prompt(args: argparse.Namespace) -> int:
    app_dir = Path(args.app_dir)
    schedule = _book(app_dir).by_id(args.schedule_id)
    occurrence = schedule.occurrence(args.occurrence_ts)
    version = tree_sha256(app_dir / "prompts", suffixes=PROMPT_SUFFIXES)
    if args.version_only:
        print(version)
        return EXIT_OK
    print(render_prompt(app_dir / "prompts", occurrence, prompt_version=version))
    return EXIT_OK


def _lock(args: argparse.Namespace) -> SkillLock:
    return load_lock(Path(args.skill_lock)) if args.skill_lock else default_lock()


def _cmd_skills_verify(args: argparse.Namespace) -> int:
    lock = _lock(args)
    root = Path(args.skills_root)
    pins = (
        lock.for_ids(_book(Path(args.app_dir)).by_id(args.schedule_id).skills)
        if (args.schedule_id)
        else tuple(lock)
    )
    materialised = [lock.verify(pin, root / pin.path) for pin in pins]
    for item in materialised:
        print(
            f"{item.pin.skill_id:36s} {item.skill_sha256}  "
            f"{item.file_count:3d} files  {item.pin.pin_state}"
        )
    if args.record:
        destination = Path(args.record)
        destination.write_text(
            json.dumps(lock.with_recorded(materialised).to_document(), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"recorded {len(materialised)} digests into {destination}")
    return EXIT_OK


def _cmd_skills_commit(args: argparse.Namespace) -> int:
    """Print the single upstream commit the lock pins, or refuse if it pins several.

    The entrypoint fetches exactly one object name. A lock pinning two commits would make
    that fetch silently consume one of them for every skill, so the refusal is here rather
    than in the shell.
    """
    commits = sorted({pin.commit for pin in _lock(args)})
    if len(commits) != 1:
        raise StewardError(
            f"the lock pins {len(commits)} upstream commits {commits}; the checkout fetches "
            "one object name, so a multi-commit lock would consume bytes it did not pin"
        )
    print(commits[0])
    return EXIT_OK


def _cmd_skills_stage(args: argparse.Namespace) -> int:
    """Copy one schedule's pinned skills into a Claude Code skills directory.

    Copied, never symlinked: a link would let the session follow a path back out of the
    verified checkout, and what the session reads must be exactly what was digested.
    """
    lock = _lock(args)
    schedule = _book(Path(args.app_dir)).by_id(args.schedule_id)
    root = Path(args.skills_root)
    destination = Path(args.destination)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    staged = 0
    for pin in lock.for_ids(schedule.skills):
        materialised = lock.verify(pin, root / pin.path)
        shutil.copytree(materialised.local_path, destination / pin.skill_id)
        staged += 1
        print(f"staged {pin.skill_id} {materialised.skill_sha256}")
    print(f"{staged} skills staged into {destination}")
    return EXIT_OK


def _cmd_allowlist(args: argparse.Namespace) -> int:
    """Print the allowlist, optionally only the entries a CLI ``--allowedTools`` takes.

    The entrypoint passes these on the command line as well as in ``--settings``, so a
    settings file that failed to load cannot degrade into a permissive session.
    """
    entries = read_allowed_tools(Path(args.app_dir) / "settings.json")
    if args.mcp_only:
        entries = tuple(entry for entry in entries if entry.startswith("mcp__"))
    for entry in entries:
        print(entry)
    return EXIT_OK


def _cmd_attest(args: argparse.Namespace) -> int:
    config = _build_config(args)
    occurrence = (
        load_schedules(config.schedules_path).by_id(args.schedule_id).occurrence(args.occurrence_ts)
    )
    client = _client(args)
    try:
        emitter = Emitter(
            client,
            encoding=BytesEncoding(args.bytes_encoding),
            dry_run=config.dry_run,
        )
        runner = StewardRun(config, client=client, emitter=emitter)
        result = runner.execute(occurrence)
    finally:
        client.close()
    print(result.render())
    if args.report:
        Path(args.report).write_text(
            json.dumps(dict(result.attestation.payload), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return EXIT_OK


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-dir", default=str(_default_app_dir()))
    parser.add_argument("--skill-lock", default=None)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser. Exposed so a test can exercise every verb's wiring."""
    parser = argparse.ArgumentParser(
        prog="mainline-steward",
        description="The Steward's attestation emitter. " + sentence(EVIDENCE_OF_REVIEW),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    schedules = sub.add_parser("schedules", help="print the declared calendar")
    _add_common(schedules)
    schedules.add_argument("--json", action="store_true")
    schedules.set_defaults(handler=_cmd_schedules)

    prompt = sub.add_parser("prompt", help="render one occurrence's prompt")
    _add_common(prompt)
    prompt.add_argument("schedule_id")
    prompt.add_argument("occurrence_ts")
    prompt.add_argument("--version-only", action="store_true")
    prompt.set_defaults(handler=_cmd_prompt)

    skills = sub.add_parser("skills", help="pin operations over the consumed Agent Skills")
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)

    verify = skills_sub.add_parser("verify", help="digest a checkout and compare it to the pins")
    _add_common(verify)
    verify.add_argument("--skills-root", required=True)
    verify.add_argument("--schedule-id", default=None, help="verify only this schedule's skills")
    verify.add_argument("--record", default=None, help="write the digests back to this path")
    verify.set_defaults(handler=_cmd_skills_verify)

    commit = skills_sub.add_parser("commit", help="print the single pinned upstream commit")
    _add_common(commit)
    commit.set_defaults(handler=_cmd_skills_commit)

    stage = skills_sub.add_parser("stage", help="copy a schedule's skills into a skills directory")
    _add_common(stage)
    stage.add_argument("--schedule-id", required=True)
    stage.add_argument("--skills-root", required=True)
    stage.add_argument("--destination", required=True)
    stage.set_defaults(handler=_cmd_skills_stage)

    allowlist = sub.add_parser("allowlist", help="print settings.json's permissions.allow")
    _add_common(allowlist)
    allowlist.add_argument("--mcp-only", action="store_true")
    allowlist.set_defaults(handler=_cmd_allowlist)

    attest = sub.add_parser("attest", help="read, hash and write the one permitted row")
    _add_common(attest)
    attest.add_argument("schedule_id")
    attest.add_argument("occurrence_ts")
    attest.add_argument("--contract", default=None)
    attest.add_argument("--site-code", default=None)
    attest.add_argument("--cluster-id", default=None)
    attest.add_argument("--skills-root", default=None)
    attest.add_argument("--transcript", default=None)
    attest.add_argument("--out", default=None)
    attest.add_argument("--state-dir", default=None)
    attest.add_argument("--ccloud-fixtures", default=None)
    attest.add_argument("--report", default=None)
    attest.add_argument(
        "--bytes-encoding",
        default=BytesEncoding.HEX_ESCAPE.value,
        choices=[member.value for member in BytesEncoding],
    )
    attest.add_argument(
        "--send",
        action="store_true",
        help=(
            "actually write the row. Off by default: insert_rows is a real append to a "
            "real evidentiary table and a run that did not mean it must not add one"
        ),
    )
    attest.set_defaults(handler=_cmd_attest)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit status; never raises to the shell."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        status: int = args.handler(args)
    except OccurrenceAlreadyAttested as exc:
        print(f"nothing to do: {exc}")
        return EXIT_OK
    except StewardError as exc:
        print(f"REFUSED  {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except (OSError, ValueError) as exc:
        print(f"REFUSED  {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    return status


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
