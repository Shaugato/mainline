# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The cheap deterministic bulk-assignment classifier, serialised as coefficients.

TnT-LLM's third step: once the taxonomy is frozen, stop paying a model per document and
assign the corpus with something cheap that was fitted on the model's labels.  Two
constraints on "something cheap" come from this product rather than from the paper:

**It is committed as coefficients, never as a pickle.**  Same reasoning as recall.md D8 for
the calibrator: a pickle is neither auditable nor safe to load, and this artefact decides
which K-means tree an incident is filed into — which is to say it decides, years later,
whether a fatality is reachable from a permit.  The artefact here is JSON: the vocabulary,
the IDF vector, the class list with its scope ids, a weight matrix and an intercept vector,
plus a digest over the canonical form of all of it.  A stranger can re-score a document from
it with numpy and twenty lines.

**It is closed-form.**  The linear head is a regularised class centroid over L2-normalised
TF-IDF rows (Rocchio), scored by dot product — which is exactly a linear model, ``argmax_c
w_c . x + b_c``, with ``w_c`` the centroid and ``b_c`` zero under cosine.  An
iteratively-fitted head (softmax regression by gradient descent) would score a little
better and would introduce a learning rate, an iteration count and a convergence question.
An optimiser that quietly under-converges does not fail; it misfiles a few percent of
documents, and the symptom is a taxonomy that looks fine and an arm that comes back empty
three years later.  The artefact format carries ``weights`` and ``intercept`` precisely so
that a fitted head can be substituted later without changing anything downstream — the
format is general, the default is the one with no knobs.

Honest about the limits: a centroid classifier is a bag-of-words method with no notion of
word order or negation, so ``"the isolation was not applied"`` and ``"the isolation was
applied"`` are near-identical to it.  For *filing* — which activity was being performed —
that is adequate, and it is the reason the same method is not used anywhere near severity.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from mainline_recall_agent.providers.canonical import canonical_json, sha256_hex

from .errors import ClassifierArtefactInvalid, ClassifierNotFitted

__all__ = [
    "ARTEFACT_KIND",
    "STOPWORDS",
    "Prediction",
    "TaxonomyClassifier",
    "tokenise",
]

ARTEFACT_KIND: Final[str] = "tfidf-linear-centroid"
ARTEFACT_VERSION: Final[int] = 1

#: Vocabulary bounds.  A cap keeps the committed artefact reviewable — a JSON file nobody
#: can read is only marginally better than a pickle — and a document-frequency floor drops
#: the hapax legomena that make a centroid memorise its training set.
DEFAULT_MAX_FEATURES: Final[int] = 2000
DEFAULT_MIN_DF: Final[int] = 2
MIN_TOKEN_CHARS: Final[int] = 3

#: Ridge on the centroid: shrinks a class built from few documents toward the origin, so a
#: 3-document class cannot out-shout a 300-document one on a single shared term.
DEFAULT_SHRINKAGE: Final[float] = 1.0

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9][a-z0-9'\-]*")

#: Deliberately small and functional.  Domain words are never stopped: "isolation",
#: "energy", "height", "atmosphere" are the signal.
STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "about", "after", "again", "against", "all", "also", "and", "any", "are", "around",
        "because", "been", "before", "being", "between", "both", "but", "came", "can",
        "did", "does", "doing", "down", "due", "during", "each", "for", "from",
        "further", "had", "has", "have", "having", "her", "here", "him", "his", "how",
        "into", "its", "itself", "just", "more", "most", "not", "now", "off", "once",
        "only", "other", "our", "out", "over", "own", "prior", "said", "same", "she",
        "should", "some", "such", "than", "that", "the", "their", "them", "then", "there",
        "these", "they", "this", "those", "through", "too", "under", "until", "very",
        "was", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
        "will", "with", "would", "you", "your",
    }
)


def tokenise(text: str) -> list[str]:
    """Lowercase, identifier-preserving tokens of length >= 3, stop words removed.

    Hyphens and apostrophes stay inside tokens so ``k-401``, ``h2s`` and ``fall-arrest``
    survive as single features.  Case is folded here — unlike in
    :mod:`~mainline_recall_agent.taxonomy.labels`, where a capital is evidence — because a
    narrative's capitalisation carries sentence position, not identity.
    """
    return [
        token
        for token in _TOKEN_RE.findall(text.lower())
        if len(token) >= MIN_TOKEN_CHARS and token not in STOPWORDS
    ]


@dataclass(frozen=True, slots=True)
class Prediction:
    """One document's assignment, with the runner-up so a margin is visible."""

    doc_id: str
    scope_id: str
    label: str
    score: float
    margin: float


class TaxonomyClassifier:
    """TF-IDF vectoriser plus a linear head, fitted and serialised together.

    Fit once on the induction's own labels (``assign_leaves``), then used to assign the
    rest of the corpus.  The vectoriser and the head are one object because they are one
    artefact: an IDF vector without the weights it was fitted against is not re-usable, and
    a weight matrix indexed by a vocabulary nobody kept is not auditable.
    """

    def __init__(
        self,
        *,
        vocabulary: Mapping[str, int],
        idf: Sequence[float],
        classes: Sequence[str],
        class_scopes: Sequence[str],
        weights: Sequence[Sequence[float]],
        intercept: Sequence[float],
        n_train: int = 0,
        min_df: int = DEFAULT_MIN_DF,
        max_features: int = DEFAULT_MAX_FEATURES,
        shrinkage: float = DEFAULT_SHRINKAGE,
    ) -> None:
        self._vocabulary = dict(vocabulary)
        self._idf = np.asarray(idf, dtype=np.float64)
        self._classes = tuple(classes)
        self._class_scopes = tuple(class_scopes)
        self._weights = np.asarray(weights, dtype=np.float64)
        self._intercept = np.asarray(intercept, dtype=np.float64)
        self._n_train = n_train
        self._min_df = min_df
        self._max_features = max_features
        self._shrinkage = shrinkage
        self._validate()

    def _validate(self) -> None:
        n_features = len(self._vocabulary)
        n_classes = len(self._classes)
        if n_features == 0 or n_classes == 0:
            raise ClassifierArtefactInvalid(
                "classifier artefact has no vocabulary or no classes",
                n_features=n_features,
                n_classes=n_classes,
            )
        if len(self._class_scopes) != n_classes:
            raise ClassifierArtefactInvalid(
                "every class must name the scope_id it assigns to",
                n_classes=n_classes,
                n_scopes=len(self._class_scopes),
            )
        if self._idf.shape != (n_features,):
            raise ClassifierArtefactInvalid(
                "idf vector does not match the vocabulary", idf=self._idf.shape
            )
        if self._weights.shape != (n_classes, n_features):
            raise ClassifierArtefactInvalid(
                "weight matrix is not (n_classes, n_features)",
                weights=self._weights.shape,
                expected=(n_classes, n_features),
            )
        if self._intercept.shape != (n_classes,):
            raise ClassifierArtefactInvalid(
                "intercept vector does not match the class list",
                intercept=self._intercept.shape,
            )
        if not np.all(np.isfinite(self._weights)) or not np.all(np.isfinite(self._idf)):
            raise ClassifierArtefactInvalid("artefact contains a non-finite coefficient")

    # -- properties ---------------------------------------------------------------------

    @property
    def classes(self) -> tuple[str, ...]:
        return self._classes

    @property
    def class_scopes(self) -> tuple[str, ...]:
        return self._class_scopes

    @property
    def n_features(self) -> int:
        return len(self._vocabulary)

    @property
    def n_train(self) -> int:
        return self._n_train

    # -- fitting ------------------------------------------------------------------------

    @classmethod
    def fit(
        cls,
        *,
        texts: Sequence[str],
        scopes: Sequence[str],
        labels: Mapping[str, str] | None = None,
        min_df: int = DEFAULT_MIN_DF,
        max_features: int = DEFAULT_MAX_FEATURES,
        shrinkage: float = DEFAULT_SHRINKAGE,
    ) -> TaxonomyClassifier:
        """Fit on ``(text, scope_id)`` pairs.  No randomness anywhere in this method.

        ``labels`` optionally maps ``scope_id -> human-readable label`` so the artefact
        carries wording as well as identity; the classifier itself only ever predicts a
        scope id, because a label is a rename away from being a different string and a
        scope id is not.
        """
        if len(texts) != len(scopes):
            raise ClassifierArtefactInvalid(
                "texts and scopes must be the same length",
                texts=len(texts),
                scopes=len(scopes),
            )
        if not texts:
            raise ClassifierNotFitted("no training documents were supplied")

        tokenised = [tokenise(text) for text in texts]
        document_frequency: dict[str, int] = {}
        for tokens in tokenised:
            for token in set(tokens):
                document_frequency[token] = document_frequency.get(token, 0) + 1
        eligible = [
            (term, df) for term, df in document_frequency.items() if df >= max(min_df, 1)
        ]
        if not eligible:
            raise ClassifierNotFitted(
                "no term survived the document-frequency floor; the training set is too "
                "small or too heterogeneous to fit a vocabulary",
                n_documents=len(texts),
                min_df=min_df,
            )
        # Sorted by descending document frequency, ties broken lexicographically: a total
        # order, so two runs on the same corpus produce byte-identical vocabularies.
        eligible.sort(key=lambda pair: (-pair[1], pair[0]))
        selected = sorted(term for term, _ in eligible[:max_features])
        vocabulary = {term: index for index, term in enumerate(selected)}

        n_documents = len(texts)
        idf = np.zeros(len(vocabulary), dtype=np.float64)
        for term, index in vocabulary.items():
            # Smoothed IDF: ln((1 + n) / (1 + df)) + 1.  Never zero, so a term present in
            # every document still contributes its (small) length-normalised weight rather
            # than vanishing and changing the norm.
            idf[index] = math.log((1.0 + n_documents) / (1.0 + document_frequency[term])) + 1.0

        matrix = _transform(tokenised, vocabulary, idf)
        ordered_scopes = sorted(set(scopes))
        weights = np.zeros((len(ordered_scopes), len(vocabulary)), dtype=np.float64)
        scope_index = {scope: index for index, scope in enumerate(ordered_scopes)}
        counts = np.zeros(len(ordered_scopes), dtype=np.float64)
        for row, scope in enumerate(scopes):
            index = scope_index[scope]
            weights[index] += matrix[row]
            counts[index] += 1.0
        weights /= (counts + shrinkage)[:, None]
        norms = np.linalg.norm(weights, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        weights /= norms

        label_map = dict(labels or {})
        return cls(
            vocabulary=vocabulary,
            idf=idf.tolist(),
            classes=[label_map.get(scope, scope) for scope in ordered_scopes],
            class_scopes=ordered_scopes,
            weights=weights.tolist(),
            intercept=[0.0] * len(ordered_scopes),
            n_train=n_documents,
            min_df=min_df,
            max_features=max_features,
            shrinkage=shrinkage,
        )

    # -- inference ----------------------------------------------------------------------

    def scores(self, texts: Sequence[str]) -> np.ndarray:
        matrix = _transform([tokenise(text) for text in texts], self._vocabulary, self._idf)
        return matrix @ self._weights.T + self._intercept

    def predict(self, texts: Sequence[str]) -> list[str]:
        """Predicted ``scope_id`` per text.  Ties resolve to the first class in order."""
        return [self._class_scopes[int(index)] for index in np.argmax(self.scores(texts), axis=1)]

    def predict_detailed(
        self, *, doc_ids: Sequence[str], texts: Sequence[str]
    ) -> list[Prediction]:
        if len(doc_ids) != len(texts):
            raise ClassifierArtefactInvalid(
                "doc_ids and texts must be the same length",
                doc_ids=len(doc_ids),
                texts=len(texts),
            )
        matrix = self.scores(texts)
        out: list[Prediction] = []
        for row, doc_id in enumerate(doc_ids):
            order = np.argsort(-matrix[row])
            best = int(order[0])
            runner = float(matrix[row][int(order[1])]) if matrix.shape[1] > 1 else 0.0
            out.append(
                Prediction(
                    doc_id=doc_id,
                    scope_id=self._class_scopes[best],
                    label=self._classes[best],
                    score=float(matrix[row][best]),
                    margin=float(matrix[row][best]) - runner,
                )
            )
        return out

    # -- serialisation ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """The committed artefact.  ``digest`` is over the canonical form of the rest."""
        body: dict[str, Any] = {
            "kind": ARTEFACT_KIND,
            "version": ARTEFACT_VERSION,
            "tokeniser": {
                "pattern": _TOKEN_RE.pattern,
                "min_token_chars": MIN_TOKEN_CHARS,
                "case_folded": True,
                "stopwords_sha256": sha256_hex(canonical_json(sorted(STOPWORDS))),
            },
            "vectoriser": {
                "scheme": "smoothed-idf, l2-normalised tf",
                "min_df": self._min_df,
                "max_features": self._max_features,
                "vocabulary": dict(sorted(self._vocabulary.items())),
                "idf": [float(value) for value in self._idf],
            },
            "head": {
                "scheme": "regularised class centroid, cosine scored",
                "shrinkage": self._shrinkage,
            },
            "classes": list(self._classes),
            "class_scopes": list(self._class_scopes),
            "weights": [[float(v) for v in row] for row in self._weights],
            "intercept": [float(v) for v in self._intercept],
            "n_train": self._n_train,
        }
        body["digest"] = sha256_hex(canonical_json(body))
        return body

    def digest(self) -> str:
        """sha256 of the artefact, recorded on the taxonomy version record."""
        return str(self.to_dict()["digest"])

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TaxonomyClassifier:
        """Load a committed artefact, verifying its digest before trusting a coefficient."""
        if payload.get("kind") != ARTEFACT_KIND:
            raise ClassifierArtefactInvalid(
                "unknown classifier artefact kind", kind=payload.get("kind")
            )
        declared = payload.get("digest")
        body = {key: value for key, value in payload.items() if key != "digest"}
        recomputed = sha256_hex(canonical_json(body))
        if declared != recomputed:
            raise ClassifierArtefactInvalid(
                "classifier artefact digest does not match its contents",
                declared=declared,
                recomputed=recomputed,
            )
        vectoriser = payload["vectoriser"]
        head = payload.get("head", {})
        return cls(
            vocabulary=vectoriser["vocabulary"],
            idf=vectoriser["idf"],
            classes=payload["classes"],
            class_scopes=payload["class_scopes"],
            weights=payload["weights"],
            intercept=payload["intercept"],
            n_train=int(payload.get("n_train", 0)),
            min_df=int(vectoriser.get("min_df", DEFAULT_MIN_DF)),
            max_features=int(vectoriser.get("max_features", DEFAULT_MAX_FEATURES)),
            shrinkage=float(head.get("shrinkage", DEFAULT_SHRINKAGE)),
        )


def _transform(
    tokenised: Sequence[Sequence[str]], vocabulary: Mapping[str, int], idf: np.ndarray
) -> np.ndarray:
    """TF-IDF rows, L2-normalised.  A document with no in-vocabulary term is the zero row.

    The zero row is not an error: it scores 0 against every class and the argmax lands on
    the first class in order.  Callers that care — the holdout scorer does — read the
    margin, which is 0.0 for exactly this case.
    """
    matrix = np.zeros((len(tokenised), len(vocabulary)), dtype=np.float64)
    for row, tokens in enumerate(tokenised):
        for token in tokens:
            index = vocabulary.get(token)
            if index is not None:
                matrix[row, index] += 1.0
    matrix *= idf[None, :]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    matrix /= norms
    return matrix
