# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A committed, deterministic stand-in for the induction judge.

Read this paragraph before using anything in this module, and quote it in any document
that reports a number produced with it.

**A taxonomy induced by this class is not a model-induced taxonomy.**  It is a function of
a committed rule table plus the corpus, and nothing more.  It exists for the same reason
``providers.surrogate.SurrogateEmbedder`` exists: AWS credentials are not valid on the
development machine, the demo and CI must run offline, and a pipeline that can only be
executed with a live Bedrock endpoint is a pipeline nobody can red-green.  It is declared
non-semantic (:attr:`is_semantic` is ``False``), its model id says what it is, and that id
is written onto every :class:`~mainline_recall_agent.taxonomy.versioning.TaxonomyVersion`
it produces, so a reader of the version record can never mistake one for the other.

What it does implement faithfully is the *interface*: it satisfies
``providers.types.JudgeProvider``, it is handed the same
:class:`~...providers.system_blocks.SystemPrefix` and the same user payload as the live
judge, and it returns the same validated Pydantic models.  The induction loop therefore has
exactly one code path, and the phase-1/phase-2 orchestration that runs in CI is the
orchestration that would run against Claude.

The rule table is data, not code, and it lives with the fixture corpus rather than in this
package — a keyword table encoding one corpus's semantics is not a shipped capability.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from mainline_recall_agent.providers.types import ResolvedModel, Usage, ValidatedModelT

from .errors import InductionQualityError, TaxonomyError
from .merge import DEFAULT_MIN_SUPPORT, DEFAULT_SIMILARITY, LabelCandidate, cluster_labels
from .models import LEVEL_FILE, LEVEL_SERIES
from .schemas import DocumentLabel, LabelProposalBatch, MergeDecision

__all__ = [
    "OFFLINE_JUDGE_MODEL_ID",
    "InductionRule",
    "RuleBasedInductionJudge",
]

#: Written into ``TaxonomyVersion.model``.  Deliberately not shaped like a Bedrock id.
OFFLINE_JUDGE_MODEL_ID: Final[str] = "offline-rule-induction-1"

#: One in this many documents gets a variant wording of its file label, so that the merge
#: phase has something real to merge.  A fixed modulus over a digest of the doc id, so the
#: same corpus always produces the same variants and the merge is reproducible.
_VARIANT_MODULUS: Final[int] = 5


@dataclass(frozen=True, slots=True)
class InductionRule:
    """One leaf of the committed rule table."""

    activity_root: str
    series_label: str
    file_label: str
    triggers: tuple[str, ...]
    variants: tuple[str, ...] = ()

    def score(self, text: str) -> int:
        return sum(1 for trigger in self.triggers if trigger in text)

    @property
    def order_key(self) -> tuple[str, str, str]:
        return (self.activity_root, self.series_label, self.file_label)


def _digest_int(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")


class RuleBasedInductionJudge:
    """A ``JudgeProvider`` that answers the two induction phases without a network.

    Phase ``propose`` scores each narrative against the rule table by trigger-term
    containment and returns the best-scoring leaf, abstaining when nothing matches — the
    same ``insufficient_evidence`` escape the live judge is instructed to take, exercised
    on the same field.

    Phase ``merge`` delegates to :func:`~mainline_recall_agent.taxonomy.merge.cluster_labels`.
    """

    def __init__(
        self,
        rules: Sequence[InductionRule],
        *,
        rules_id: str = "unnamed-rule-table",
        min_support: int = DEFAULT_MIN_SUPPORT,
        similarity_threshold: float = DEFAULT_SIMILARITY,
    ) -> None:
        if not rules:
            raise InductionQualityError(
                "the offline induction judge needs at least one rule; an empty rule table "
                "would abstain on every document and produce an empty taxonomy that looks "
                "like a corpus problem"
            )
        self._rules = tuple(sorted(rules, key=lambda r: r.order_key))
        self._rules_id = rules_id
        self._min_support = min_support
        self._threshold = similarity_threshold
        self._calls = 0

    # -- construction ------------------------------------------------------------------

    @classmethod
    def from_json(cls, path: str | Path, **kwargs: Any) -> RuleBasedInductionJudge:
        """Load a committed rule table.

        The file's ``rules_id`` becomes part of the judge's identity, so a version record
        names not only *that* the offline judge was used but *which* table it used.
        """
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "rules" not in payload:
            raise TaxonomyError(
                "offline induction rule table must be an object with a 'rules' array",
                path=str(source),
            )
        rules = [
            InductionRule(
                activity_root=str(entry["activity_root"]),
                series_label=str(entry["series_label"]),
                file_label=str(entry["file_label"]),
                triggers=tuple(str(t).lower() for t in entry.get("triggers", ())),
                variants=tuple(str(v) for v in entry.get("variants", ())),
            )
            for entry in payload["rules"]
        ]
        return cls(rules, rules_id=str(payload.get("rules_id", source.stem)), **kwargs)

    # -- JudgeProvider ------------------------------------------------------------------

    @property
    def resolved_model(self) -> ResolvedModel:
        return ResolvedModel(
            requested_tier=OFFLINE_JUDGE_MODEL_ID,
            resolved_tier=OFFLINE_JUDGE_MODEL_ID,
            profile_id=f"{OFFLINE_JUDGE_MODEL_ID}:{self._rules_id}",
            profile_arn=None,
            region="local",
            source="pinned",
            degraded=True,
        )

    @property
    def last_usage(self) -> Usage | None:
        """Always zero tokens.  Nothing was sent anywhere, and saying so is the point."""
        return Usage()

    @property
    def is_semantic(self) -> bool:
        """False.  A rule table is not a language model and must never be scored as one."""
        return False

    @property
    def call_count(self) -> int:
        return self._calls

    @property
    def rules_id(self) -> str:
        return self._rules_id

    def judge(
        self,
        system_blocks: Sequence[Any],
        user_payload: dict[str, Any],
        schema: type[ValidatedModelT],
    ) -> ValidatedModelT:
        self._calls += 1
        phase = str(user_payload.get("phase", ""))
        if phase == "propose":
            payload = self._propose(user_payload)
        elif phase == "merge":
            payload = self._merge(user_payload)
        else:
            raise TaxonomyError(
                "unknown induction phase; the offline judge implements 'propose' and "
                "'merge' only",
                phase=phase,
            )
        # Validated through the same client-side path the live judge uses, so a change to
        # the schema breaks the offline lane too instead of only the cloud one.
        return schema.model_validate(payload)

    # -- phases -------------------------------------------------------------------------

    def _propose(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        documents = payload.get("documents", [])
        labels: list[dict[str, Any]] = []
        for document in documents:
            doc_id = str(document.get("doc_id", ""))
            text = " ".join(
                str(document.get(field, "")) for field in ("title", "narrative")
            ).lower()
            best: InductionRule | None = None
            best_score = 0
            for rule in self._rules:
                score = rule.score(text)
                if score > best_score:
                    best, best_score = rule, score
            if best is None:
                labels.append(
                    DocumentLabel(
                        doc_id=doc_id,
                        activity_root="",
                        series_label="",
                        file_label="",
                        insufficient_evidence=True,
                        confidence=0.0,
                    ).model_dump()
                )
                continue
            file_label = best.file_label
            if best.variants:
                seed = _digest_int(doc_id)
                if seed % _VARIANT_MODULUS == 0:
                    file_label = best.variants[seed % len(best.variants)]
            labels.append(
                DocumentLabel(
                    doc_id=doc_id,
                    activity_root=best.activity_root,
                    series_label=best.series_label,
                    file_label=file_label,
                    insufficient_evidence=False,
                    confidence=min(1.0, best_score / max(len(best.triggers), 1)),
                ).model_dump()
            )
        return LabelProposalBatch.model_validate({"labels": labels}).model_dump()

    def _merge(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        candidates = [
            LabelCandidate(
                level=int(entry["level"]),
                activity_root=str(entry["activity_root"]),
                parent_label=(
                    str(entry["parent_label"])
                    if entry.get("parent_label") not in (None, "")
                    else None
                ),
                label=str(entry["label"]),
                support=int(entry.get("support", 1)),
            )
            for entry in payload.get("candidates", [])
            if int(entry["level"]) in (LEVEL_SERIES, LEVEL_FILE)
        ]
        groups = cluster_labels(
            candidates,
            min_support=int(payload.get("min_support", self._min_support)),
            threshold=float(payload.get("similarity_threshold", self._threshold)),
        )
        return MergeDecision(groups=groups).model_dump()
