# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The bulk-assignment classifier is coefficients, not a pickle — and it is checkable.

Same reasoning as recall.md D8 for the calibrator: this artefact decides which K-means tree
an incident is filed into, which is to say it decides, years later, whether a fatality is
reachable from a permit.  A pickle is neither auditable nor safe to load.  So the tests
below assert the three properties that make the alternative real — it is JSON, it carries a
digest over its own contents, and a tampered coefficient is refused rather than used.
"""

from __future__ import annotations

import json

import pytest
from mainline_recall_agent.taxonomy import (
    ARTEFACT_KIND,
    ClassifierArtefactInvalid,
    ClassifierNotFitted,
    InductionRun,
    TaxonomyClassifier,
    tokenise,
)

TEXTS = [
    "the review noted: personal danger lock. witness statements refer to lock box.",
    "the review noted: lock box. a prior audit had raised isolation point register.",
    "the record shows group lockout board at the time of the event.",
    "the review noted: three points of contact. witness statements refer to fixed ladder.",
    "the record shows fixed ladder at the time of the event.",
    "a prior audit had raised three points of contact on the fixed ladder.",
]
SCOPES = ["scope-lockout"] * 3 + ["scope-ladder"] * 3


def test_tokeniser_preserves_identifiers_and_folds_case() -> None:
    tokens = tokenise("Isolating K-401 released H2S at 3 bar")
    assert "k-401" in tokens
    assert "h2s" in tokens
    assert "isolating" in tokens
    # Short tokens and stop words are dropped; "at" and "3" carry nothing.
    assert "at" not in tokens
    assert "3" not in tokens


def test_fit_and_predict_on_a_tiny_separable_set() -> None:
    model = TaxonomyClassifier.fit(texts=TEXTS, scopes=SCOPES, min_df=1)
    assert model.classes == ("scope-ladder", "scope-lockout")
    assert model.predict(["the crew signed onto the lock box"]) == ["scope-lockout"]
    assert model.predict(["three points of contact on the fixed ladder"]) == ["scope-ladder"]


def test_fitting_is_deterministic() -> None:
    first = TaxonomyClassifier.fit(texts=TEXTS, scopes=SCOPES, min_df=1)
    second = TaxonomyClassifier.fit(texts=list(TEXTS), scopes=list(SCOPES), min_df=1)
    assert first.digest() == second.digest()


def test_the_artefact_is_json_and_carries_its_own_digest() -> None:
    model = TaxonomyClassifier.fit(texts=TEXTS, scopes=SCOPES, min_df=1)
    artefact = model.to_dict()
    assert artefact["kind"] == ARTEFACT_KIND
    # If this serialises, it is not a pickle. The point is not the format, it is that a
    # stranger can read every coefficient that decides where an incident is filed.
    encoded = json.dumps(artefact)
    assert len(encoded) > 0
    restored = TaxonomyClassifier.from_dict(json.loads(encoded))
    assert restored.digest() == model.digest()
    assert restored.predict(["the crew signed onto the lock box"]) == ["scope-lockout"]


def test_a_tampered_coefficient_is_refused() -> None:
    model = TaxonomyClassifier.fit(texts=TEXTS, scopes=SCOPES, min_df=1)
    artefact = model.to_dict()
    artefact["weights"][0][0] += 0.5
    with pytest.raises(ClassifierArtefactInvalid) as excinfo:
        TaxonomyClassifier.from_dict(artefact)
    assert "digest" in excinfo.value.message


def test_an_unknown_artefact_kind_is_refused() -> None:
    model = TaxonomyClassifier.fit(texts=TEXTS, scopes=SCOPES, min_df=1)
    artefact = model.to_dict()
    artefact["kind"] = "pickle"
    with pytest.raises(ClassifierArtefactInvalid):
        TaxonomyClassifier.from_dict(artefact)


def test_a_mismatched_weight_matrix_is_refused() -> None:
    model = TaxonomyClassifier.fit(texts=TEXTS, scopes=SCOPES, min_df=1)
    artefact = model.to_dict()
    artefact["weights"] = artefact["weights"][:1]
    artefact["digest"] = TaxonomyClassifier.fit(texts=TEXTS, scopes=SCOPES, min_df=1).to_dict()[
        "digest"
    ]
    with pytest.raises(ClassifierArtefactInvalid):
        TaxonomyClassifier.from_dict(artefact)


def test_fitting_with_no_documents_is_refused() -> None:
    with pytest.raises(ClassifierNotFitted):
        TaxonomyClassifier.fit(texts=[], scopes=[])


def test_mismatched_lengths_are_refused() -> None:
    with pytest.raises(ClassifierArtefactInvalid):
        TaxonomyClassifier.fit(texts=TEXTS, scopes=SCOPES[:2])


def test_an_out_of_vocabulary_document_has_a_zero_margin() -> None:
    """A document with no known term scores nothing; the caller can see that it did."""
    model = TaxonomyClassifier.fit(texts=TEXTS, scopes=SCOPES, min_df=1)
    detailed = model.predict_detailed(doc_ids=["X-1"], texts=["zzzz yyyy xxxx"])
    assert detailed[0].score == pytest.approx(0.0)
    assert detailed[0].margin == pytest.approx(0.0)


def test_the_pipeline_records_the_classifier_digest_on_the_version(
    induction: InductionRun,
) -> None:
    assert induction.version.classifier_digest == induction.classifier.digest()
    assert induction.classifier.n_train == len(induction.assignments)
    # Every class the classifier can predict is a scope that exists in the taxonomy.
    for scope in induction.classifier.class_scopes:
        assert induction.snapshot.by_scope(scope) is not None
