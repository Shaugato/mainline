# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Loading the anchored recall policy, and the THYMOGATE gate on starting at all.

Two refusals live here, and neither is a validation nicety.

**MI18 — a run cites only an anchored policy.** ``recall_policy.anchored_tree_size`` must be
non-NULL and inside a cosigned checkpoint before a run may cite the row.
``fn_recall_policy_anchored`` (migration 0112) enforces it on ``recall_run`` INSERT with a
``P0001``. This module checks it *before* the run starts, for a reason that is not
performance: a run that spent twenty seconds reranking and then discovered its policy was
never anchored has burned a model budget and produced a refusal that reads like a bug. The
database keeps the guarantee; this keeps the diagnosis early. **The early check never
substitutes for the trigger** — that is the P2 discipline, and `test_policy_gate.py` asserts
the trigger still refuses with the check removed.

**M5 THYMOGATE — a policy that missed a known killer may not run.** If
``recall_policy.thymogate_certificate_id`` is set, the certificate it names must exist and
carry ``verdict = 'pass'``. The column is nullable at K4 and becomes ``NOT NULL`` at K8
(recall lead D14), so "no certificate" is currently a legal state and is *not* a refusal —
but a certificate that is named and is not clean, or is named and cannot be read, is. The
absence of a verdict is not a pass.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from mainline_recall_agent.run.errors import PolicyRefused, ThymogateRefused
from mainline_recall_agent.run.session import SqlSession

__all__ = [
    "POLICY_SQL",
    "THYMOGATE_SQL",
    "RecallPolicy",
    "ThymogateCertificate",
    "load_policy",
    "load_thymogate",
]

POLICY_SQL: Final = """
SELECT rp.policy_version,
       rp.taxonomy_ver,
       rp.embed_model,
       rp.gen_model,
       rp.prompt_version,
       rp.beam_size,
       rp.tau::STRING,
       rp.arms::STRING,
       rp.calibrator::STRING,
       rp.anchored_tree_size,
       rp.thymogate_certificate_id
  FROM mainline_meas.recall_policy rp
 WHERE rp.policy_version = $1
""".strip()

THYMOGATE_SQL: Final = """
SELECT tc.certificate_id,
       encode(tc.config_digest, 'hex'),
       encode(tc.panel_digest, 'hex'),
       tc.panel_size,
       tc.n_missed,
       tc.verdict
  FROM mainline_meas.thymogate_certificate tc
 WHERE tc.certificate_id = $1
""".strip()

#: The one verdict that permits a run. ``thymogate_certificate.verdict_matches_arithmetic``
#: already makes ``'pass'`` equivalent to ``n_missed = 0`` in the database; both are checked
#: here, because a certificate that disagreed with itself is a finding, not a pass.
_CLEAN_VERDICT: Final = "pass"


@dataclass(frozen=True, slots=True)
class ThymogateCertificate:
    """M5's negative-selection certificate, as read from the database."""

    certificate_id: str
    config_digest: str
    panel_digest: str
    panel_size: int
    n_missed: int
    verdict: str

    @property
    def clean(self) -> bool:
        """A clean certificate passed *and* its arithmetic agrees with its verdict."""
        return self.verdict == _CLEAN_VERDICT and self.n_missed == 0


@dataclass(frozen=True, slots=True)
class RecallPolicy:
    """One anchored ``mainline_meas.recall_policy`` row, with its JSONB parsed."""

    policy_version: str
    taxonomy_ver: int
    embed_model: str
    gen_model: str
    prompt_version: str
    beam_size: int
    tau: Mapping[str, Any]
    arms: Mapping[str, Any]
    calibrator: Mapping[str, Any]
    anchored_tree_size: int | None
    thymogate_certificate_id: str | None

    @property
    def anchored(self) -> bool:
        """Whether the policy's commitment has landed in a checkpoint (MI18, S24)."""
        return self.anchored_tree_size is not None

    def tau_thresholds(self) -> dict[int, float]:
        """``tau`` as a severity-keyed table.

        Raises:
            PolicyRefused: if the stored shape is not a mapping of severity to threshold. A
                malformed tau is not a default to fall back from: it is the number that
                decides whether a fatality is raised.
        """
        table: dict[int, float] = {}
        for key, value in self.tau.items():
            try:
                severity = int(key)
                threshold = float(value)
            except (TypeError, ValueError) as exc:
                raise PolicyRefused(
                    f"{self.policy_version}: tau entry {key!r}={value!r} is not a "
                    "severity->threshold pair"
                ) from exc
            if not 0.0 <= threshold <= 1.0:
                raise PolicyRefused(
                    f"{self.policy_version}: tau({severity}) = {threshold} is outside [0, 1]; "
                    "admission compares a calibrated probability, not a distance"
                )
            table[severity] = threshold
        if not table:
            raise PolicyRefused(f"{self.policy_version}: tau is empty")
        return table


def _as_mapping(raw: object, *, what: str, policy_version: str) -> dict[str, Any]:
    """Parse a JSONB column that the driver may hand back as text or as a dict."""
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise PolicyRefused(f"{policy_version}: {what} is not readable JSON") from exc
        if isinstance(parsed, dict):
            return parsed
    raise PolicyRefused(f"{policy_version}: {what} is not a JSON object")


def load_policy(session: SqlSession, policy_version: str) -> RecallPolicy:
    """Read one policy row and refuse it if it may not arm a run.

    Raises:
        PolicyRefused: the row is absent, unanchored (MI18), or malformed.
    """
    rows: Sequence[Sequence[Any]] = session.query(POLICY_SQL, (policy_version,))
    if not rows:
        raise PolicyRefused(
            f"no recall_policy row for {policy_version!r}. tau is a calibration artefact with "
            "its own commit, author and gold set; a run cannot invent one."
        )
    row = rows[0]
    policy = RecallPolicy(
        policy_version=str(row[0]),
        taxonomy_ver=int(row[1]),
        embed_model=str(row[2]),
        gen_model=str(row[3]),
        prompt_version=str(row[4]),
        beam_size=int(row[5]),
        tau=_as_mapping(row[6], what="tau", policy_version=policy_version),
        arms=_as_mapping(row[7], what="arms", policy_version=policy_version),
        calibrator=_as_mapping(row[8], what="calibrator", policy_version=policy_version),
        anchored_tree_size=None if row[9] is None else int(row[9]),
        thymogate_certificate_id=None if row[10] is None else str(row[10]),
    )
    if not policy.anchored:
        raise PolicyRefused(
            f"{policy_version} has no anchored_tree_size: its commitment has not landed in a "
            "cosigned checkpoint, so a run citing it could be retro-fitted afterwards. "
            "fn_recall_policy_anchored (0112) refuses the run row with P0001; this is the "
            "same refusal, taken before the model budget is spent."
        )
    # Called for its refusals, not its value: a malformed tau must stop the run here rather
    # than surface as a KeyError inside admission.
    policy.tau_thresholds()
    return policy


def load_thymogate(session: SqlSession, policy: RecallPolicy) -> ThymogateCertificate | None:
    """Read and gate on the policy's THYMOGATE certificate, if it names one.

    Returns:
        The certificate, or ``None`` when the policy names none (legal at K4, refused at K8).

    Raises:
        ThymogateRefused: the certificate is named and is missing, unclean, or
            self-contradictory.
    """
    certificate_id = policy.thymogate_certificate_id
    if certificate_id is None:
        return None

    rows = session.query(THYMOGATE_SQL, (certificate_id,))
    if not rows:
        raise ThymogateRefused(
            f"{policy.policy_version} names THYMOGATE certificate {certificate_id} and no "
            "such row exists. A policy that cannot show it was measured against the panel of "
            "the fleet's known killers has not been measured; the absence of a verdict is "
            "not a pass."
        )
    row = rows[0]
    certificate = ThymogateCertificate(
        certificate_id=str(row[0]),
        config_digest=str(row[1]),
        panel_digest=str(row[2]),
        panel_size=int(row[3]),
        n_missed=int(row[4]),
        verdict=str(row[5]),
    )
    if not certificate.clean:
        raise ThymogateRefused(
            f"{policy.policy_version} names THYMOGATE certificate {certificate_id}, whose "
            f"verdict is {certificate.verdict!r} with {certificate.n_missed} of "
            f"{certificate.panel_size} panel members missed. Bringing into existence a tuned "
            "retriever that would have missed a known killer is the one thing negative "
            "selection exists to prevent, and it does not become acceptable because a permit "
            "is waiting."
        )
    return certificate
