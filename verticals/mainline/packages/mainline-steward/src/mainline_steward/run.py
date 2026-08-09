# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One scheduled Steward run, from the occurrence to the row.

The order below is the argument, so it is worth reading as a sequence rather than as
code. Nothing that can fail late is allowed to fail late:

1. **Claim the occurrence.** At-least-once delivery means a redelivery is expected. It is
   refused first, before any credential is used and before any read is issued.
2. **Verify the skill pins.** A run whose consumed skills are not the pinned bytes is
   refused before it reads anything, because the report it would produce would name a
   review that did not happen.
3. **Resolve the identity.** ``agent_identity`` is computed once, at the top, from the
   prompt digest and the six other A13 inputs. A run that cannot name itself does not
   read.
4. **Read.** Every statement comes from the audit-surface contract. A read that will not
   answer becomes an *unanswered finding*, not an exception — which of the contracted
   reads failed is an ops fact, and losing it would make a partial reading look clean.
5. **Attach prose.** The Claude Code session's narrative is matched onto findings that
   already exist. It cannot create one, and it cannot touch a statement or a hash.
6. **Attest.** Canonicalise, leaf-hash, write the detail file, write the one row.

The stock CockroachDB skills' native diagnostics read ``crdb_internal``, which the
Managed MCP surface cannot reach at all. They are pointed at the pre-materialised
``mainline_audit`` ops views instead — ``v_gate_latency_daily``, ``v_txn_restart_daily``,
``v_unused_indexes``, ``v_changefeed_health`` — and the runbook says so in as many words.
*The limitation is the product's ops API*, which is the pattern this whole domain runs on.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from mainline_mcp.catalogue import Catalogue, ContractError, ViewSpec, load_contract
from mainline_mcp.client import Client
from mainline_mcp.limits import BUDGET_RESPONSE_BYTES, McpClientError

from .attestation import Emitter, OpsAttestation, build_attestation
from .ccloud import CcloudPage, CcloudShim, CustodianPatrol, resolve_shim
from .digest import tree_sha256
from .errors import ConfigurationRefused, ScheduleRefused
from .findings import EVIDENCE_OF_REVIEW, Finding, sentence
from .guard import OccurrenceGuard
from .identity import AgentIdentity, resolve_identity
from .narrative import NarrativeSet, attach_narratives, read_transcript
from .schedule import Occurrence, RunKind, ScheduleBook, load_schedules
from .skills import MaterialisedSkill, SkillLock, default_lock, load_lock

__all__ = [
    "PROMPT_SUFFIXES",
    "RunConfig",
    "RunResult",
    "StewardRun",
    "read_allowed_tools",
]

PROMPT_SUFFIXES: Final = (".md",)
"""``prompt_version`` covers the Markdown prompt assets and nothing else.

A stray editor swap file or a ``.DS_Store`` must not change the agent's identity, and A13
makes ``prompt_version`` part of ``agent_identity`` — so an over-broad digest would mint a
new agent every time somebody opened the directory.
"""

_SQL_ROLE: Final = "mainline_auditor"


def read_allowed_tools(settings_path: Path) -> tuple[str, ...]:
    """Return the allowlist from the Steward's Claude Code settings file.

    Read rather than declared: the attestation records the tools the session was actually
    permitted, and a constant here would record what we meant instead of what shipped.
    """
    if not settings_path.is_file():
        raise ConfigurationRefused(f"no settings file at {settings_path}")
    try:
        document = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationRefused(f"{settings_path} is not valid JSON: {exc}") from exc
    permissions = document.get("permissions", {})
    allow = permissions.get("allow", []) if isinstance(permissions, Mapping) else []
    if not isinstance(allow, list) or not allow:
        raise ConfigurationRefused(
            f"{settings_path} declares no permissions.allow entries. Capability starvation "
            "is expressed as configuration here; an empty allowlist read as 'anything goes' "
            "would invert the control"
        )
    return tuple(str(entry) for entry in allow)


@dataclass(frozen=True, slots=True)
class RunConfig:
    """Everything a run needs that is not the MCP client."""

    app_dir: Path
    contract_path: Path
    site_code: str
    mcp_cluster_id: str
    iam_role_arn: str
    model_id: str
    inference_profile_arn: str
    schema_version: str
    claude_code_version: str
    skills_root: Path | None = None
    transcript: Path | None = None
    out_dir: Path | None = None
    state_dir: Path | None = None
    ccloud_fixtures: Path | None = None
    dry_run: bool = True
    sql_role: str = _SQL_ROLE
    skill_lock_path: Path | None = None

    @property
    def prompts_dir(self) -> Path:
        """Where the content-addressed prompt assets live."""
        return self.app_dir / "prompts"

    @property
    def schedules_path(self) -> Path:
        """The declarative calendar."""
        return self.app_dir / "schedules.yaml"

    @property
    def settings_path(self) -> Path:
        """The Claude Code settings file whose allowlist is the capability boundary."""
        return self.app_dir / "settings.json"

    def require(self) -> None:
        """Refuse a configuration that is incomplete, before anything is read.

        Every field below appears in the attestation. A run that discovered at emit time
        that it never knew its own cluster id has already done its reads under an
        identity it cannot name, which is worse than not running.
        """
        missing = [
            name
            for name in (
                "site_code",
                "mcp_cluster_id",
                "iam_role_arn",
                "model_id",
                "inference_profile_arn",
                "schema_version",
                "claude_code_version",
            )
            if not str(getattr(self, name)).strip()
        ]
        if missing:
            raise ConfigurationRefused(
                f"run configuration is missing {missing}. Every one of these appears in the "
                "attestation, so a run without them would attest to an unnamed identity"
            )
        if not self.app_dir.is_dir():
            raise ConfigurationRefused(f"no steward app directory at {self.app_dir}")


@dataclass(frozen=True, slots=True)
class RunResult:
    """What a completed run produced."""

    occurrence: Occurrence
    identity: AgentIdentity
    skills: tuple[MaterialisedSkill, ...]
    findings: tuple[Finding, ...]
    narratives: NarrativeSet
    attestation: OpsAttestation
    detail_path: Path | None
    row: Mapping[str, Any]
    emitted: bool

    def render(self) -> str:
        """Render a human-readable run report. The disclaimer is on it, always."""
        lines = [
            f"steward run   {self.occurrence.key}",
            f"outcome       {self.attestation.outcome}",
            f"agent         {self.identity.agent_identity} ({self.identity.identity_source})",
            (
                f"skills        {len(self.skills)} pinned, "
                f"{sum(1 for s in self.skills if s.pin.pin_state == 'enforced')} digest-enforced"
            ),
            (
                f"detail        {self.detail_path} "
                f"sha256(0x00||canon)={self.attestation.leaf_hash_hex}"
            ),
            f"row           {'sent' if self.emitted else 'NOT SENT (dry run)'}: {self.row}",
            "",
            sentence(EVIDENCE_OF_REVIEW),
            "",
        ]
        lines.extend(finding.render() for finding in self.findings)
        return "\n".join(lines)


class StewardRun:
    """Execute one occurrence: one client, one catalogue, and only the emitter's write."""

    def __init__(
        self,
        config: RunConfig,
        *,
        client: Client,
        emitter: Emitter | None = None,
        guard: OccurrenceGuard | None = None,
        ccloud: CcloudShim | None = None,
        lock: SkillLock | None = None,
    ) -> None:
        """Bind the configuration and the collaborators, validating the configuration first."""
        config.require()
        self._config = config
        self._client = client
        self._emitter = emitter or Emitter(client, dry_run=config.dry_run)
        self._guard = guard or OccurrenceGuard.for_directory(config.state_dir)
        self._ccloud = ccloud
        self._lock = lock or (
            load_lock(config.skill_lock_path) if config.skill_lock_path else default_lock()
        )
        self._catalogue: Catalogue | None = None
        self._book: ScheduleBook | None = None

    @property
    def catalogue(self) -> Catalogue:
        """The audit-surface contract, loaded once."""
        if self._catalogue is None:
            try:
                self._catalogue = load_contract(self._config.contract_path)
            except ContractError as exc:
                raise ConfigurationRefused(
                    f"the audit-surface contract is unusable: {exc}. Every statement a "
                    "Steward run issues comes from it, so there is nothing to read without it"
                ) from exc
        return self._catalogue

    @property
    def schedules(self) -> ScheduleBook:
        """The declared calendar, loaded once."""
        if self._book is None:
            self._book = load_schedules(self._config.schedules_path)
        return self._book

    def prompt_version(self) -> str:
        """Return the digest of the prompt tree — one seventh of ``agent_identity``."""
        return tree_sha256(self._config.prompts_dir, suffixes=PROMPT_SUFFIXES)

    def resolve_views(self, occurrence: Occurrence) -> tuple[ViewSpec, ...]:
        """Resolve the schedule's declared views against the contract, refusing any unknown.

        A view the contract does not carry is a schedule that would read nothing and
        report cleanly, which is the substitution this package exists to refuse.
        """
        catalogue = self.catalogue
        unknown = [name for name in occurrence.schedule.views if not catalogue.has(name)]
        if unknown:
            raise ScheduleRefused(
                f"{occurrence.schedule.schedule_id} declares views the audit-surface contract "
                f"does not carry: {unknown}. Contracted views are {list(catalogue.names())}"
            )
        return tuple(catalogue.by_name(name) for name in occurrence.schedule.views)

    def materialise_skills(self, occurrence: Occurrence) -> tuple[MaterialisedSkill, ...]:
        """Verify every skill this schedule consumes against its pin.

        With no ``skills_root`` configured the schedule must consume no skills; a run that
        claims a skill it never checked out would be the exact defect a pin prevents.
        """
        pins = self._lock.for_ids(occurrence.schedule.skills)
        if not pins:
            return ()
        root = self._config.skills_root
        if root is None:
            raise ConfigurationRefused(
                f"{occurrence.schedule.schedule_id} consumes {len(pins)} skills and no "
                "skills_root is configured. A run cannot attest to bytes it never had"
            )
        return tuple(self._lock.verify(pin, root / pin.path) for pin in pins)

    def read_views(
        self, views: Sequence[ViewSpec], *, skill_for: Mapping[str, str] | None = None
    ) -> tuple[Finding, ...]:
        """Issue one contracted read per view, capturing a failure as an unanswered finding."""
        attribution = dict(skill_for or {})
        findings: list[Finding] = []
        for view in views:
            skill_id = attribution.get(view.name)
            try:
                result = self._client.select_query(view.statement, max_rows=view.row_cap)
            except McpClientError as exc:
                findings.append(
                    Finding.unanswered_view(view=view, detail=str(exc), skill_id=skill_id)
                )
                continue
            if result.is_error:
                # The surface answered, and the answer was an error. That is a read that
                # did not happen, and it must not become a finding with no rows in it —
                # "the view returned nothing" and "the view could not be read" are the two
                # states this product exists to keep apart.
                findings.append(
                    Finding.unanswered_view(
                        view=view,
                        detail=result.text[:400] or "the surface returned an error result",
                        skill_id=skill_id,
                        elapsed_ms=self._client.last_elapsed_ms,
                    )
                )
                continue
            detail = ""
            if result.byte_count > min(view.byte_budget, BUDGET_RESPONSE_BYTES):
                detail = (
                    f"response is {result.byte_count} bytes against a {view.byte_budget}-byte "
                    "budget; the budget is 80% of the server cap so this fires with headroom left"
                )
            findings.append(
                Finding.from_view_read(
                    view=view,
                    rows=result.rows,
                    response_bytes=result.byte_count,
                    elapsed_ms=self._client.last_elapsed_ms,
                    skill_id=skill_id,
                    detail=detail,
                )
            )
        return tuple(findings)

    def read_custody(self, occurrence: Occurrence) -> tuple[Finding, ...]:
        """Run §8.6 I4's three ``ccloud`` reads and hash each page."""
        shim, source = resolve_shim(explicit=self._ccloud, fixtures=self._config.ccloud_fixtures)
        patrol = CustodianPatrol(shim, cluster_id=self._config.mcp_cluster_id)
        pages = patrol.run(starting_from=occurrence.since)
        return (
            *(Finding.from_ccloud_page(page) for page in pages),
            Finding.from_ccloud_page(_shim_provenance_page(source, occurrence.since)),
        )

    def execute(self, occurrence: Occurrence) -> RunResult:
        """Run one occurrence end to end and return what it produced."""
        started = datetime.now(tz=UTC)
        self._guard.claim(occurrence.key)
        try:
            views = self.resolve_views(occurrence)
            skills = self.materialise_skills(occurrence)
            identity = resolve_identity(
                sql_role=self._config.sql_role,
                iam_role_arn=self._config.iam_role_arn,
                prompt_version=self.prompt_version(),
                model_id=self._config.model_id,
                inference_profile_arn=self._config.inference_profile_arn,
                schema_version=self._config.schema_version,
            )
            skill_for = _skill_attribution(occurrence, views, skills)
            findings = self.read_views(views, skill_for=skill_for)
            if occurrence.schedule.kind is RunKind.CUSTODIAN_PATROL:
                findings = findings + self.read_custody(occurrence)
            narratives = read_transcript(
                self._config.transcript, subjects=[f.subject for f in findings]
            )
            findings = attach_narratives(findings, narratives.narratives)
            runtime: dict[str, Any] = {
                "agent_runtime": "claude-code",
                "agent_runtime_version": self._config.claude_code_version,
                "allowed_tools": list(read_allowed_tools(self._config.settings_path)),
                "prompt_asset": occurrence.schedule.prompt,
                "prompt_version": identity.prompt_version,
                "max_turns": occurrence.schedule.max_turns,
            } | narratives.to_payload()
            attestation = build_attestation(
                occurrence=occurrence,
                identity=identity,
                site_code=self._config.site_code,
                mcp_cluster_id=self._config.mcp_cluster_id,
                skills=skills,
                findings=findings,
                runtime=runtime,
                started_at=started,
                finished_at=datetime.now(tz=UTC),
            )
            detail_path = None
            if self._config.out_dir is not None:
                detail_path = attestation.write_detail(
                    self._config.out_dir / f"{_slug(occurrence.key)}.ops-attestation.json"
                )
            row = self._emitter.emit(attestation)
        except Exception:
            # The claim is given back so a genuine retry of a failed occurrence can run.
            # Deliberately not a bare `except:` — the exception is re-raised unchanged and
            # nothing here decides that a failure was survivable.
            self._guard.release(occurrence.key)
            raise
        return RunResult(
            occurrence=occurrence,
            identity=identity,
            skills=skills,
            findings=findings,
            narratives=narratives,
            attestation=attestation,
            detail_path=detail_path,
            row=row.as_mapping(),
            emitted=not self._emitter.dry_run,
        )


def _skill_attribution(
    occurrence: Occurrence,
    views: Sequence[ViewSpec],
    skills: Sequence[MaterialisedSkill],
) -> dict[str, str]:
    """Attribute each view read to the skill whose run it belongs to.

    A positional map, and honest about being one: the schedule declares its skills and its
    views in order, and the attribution is which run the read belongs to — not a claim
    that a particular skill emitted a particular statement. The statements come from the
    contract, never from a skill.
    """
    if not skills or not occurrence.schedule.skills:
        return {}
    ordered = [skill.pin.skill_id for skill in skills]
    return {view.name: ordered[index % len(ordered)] for index, view in enumerate(views)}


def _shim_provenance_page(source: str, since: str) -> CcloudPage:
    """Record *which* ccloud shim answered — fixture, binary, or the cloud lead's.

    Emitted as a finding of its own so a reader can never mistake a fixture-backed
    custodian patrol for a live one. Distinguishing the two after the fact, from the
    attestation alone, is the whole reason this exists.
    """
    return CcloudPage.build(
        command=f"(ccloud shim provenance) source={source} starting_from={since}",
        document={"shim_source": source, "starting_from": since},
        source="shim_provenance",
    )


def _slug(text: str) -> str:
    """Return a filesystem-safe form of an occurrence key."""
    return "".join(c if c.isalnum() or c in "-._" else "-" for c in text)
