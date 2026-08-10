# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The synthetic corpus: the only body of documents this repository is allowed to reason over.

Nine subpackages, each a stage, each runnable as ``python -m mainline_corpus.<stage>``:

``gazetteer``   the authored ground facts — sites, assets, people, citations, taxonomy — as
                YAML read from disk beside this module, never from a network.
``skeleton``    stage 1: the deterministic site/asset/energy graph and the incident timeline.
``moc_stream``  stage 1c: the change-request stream and ``cr_clause``, the relation the
                change-request half of the merge gate reads.
``blame``       ground-truth blame edges and the negative controls that make recall falsifiable.
``injectors``   the realism injectors, applied after the ground truth is fixed so that the
                truth is never a function of the noise.
``prompts``     the authored prompt texts, as Markdown beside this module.
``render``      stage 2: the three-tier renderer and its content-addressed committed cache.
``reflow``      typesetting drift, so that a fixity claim is tested against a document that
                moved rather than one that did not.
``docx``        stage 3: byte-reproducible OOXML.
``rng``         the one seeded generator. Nothing in this package calls ``random`` directly.

WHY THIS FILE IS INERT. Until 2026-08-10 this directory had **no** ``__init__.py`` at all and
the distribution had no ``pyproject.toml``; ``mainline_corpus`` existed only as an implicit
namespace package that resolved when — and only when — somebody had put
``verticals/mainline/packages/mainline-corpus/src`` on ``PYTHONPATH`` by hand. Four consumers
(``tests/unit/moc_stream/``, ``tests/integration/schema/test_mi_event_severity.py``,
``tests/security/injection/``, ``mainline_boundary.greps``) imported it anyway.

It re-exports nothing, and that is deliberate. ``gazetteer`` needs PyYAML and ``docx.template``
needs Jinja2; a top-level ``__init__`` that imported its own subpackages would make the cost of
``import mainline_corpus`` the union of every stage's dependencies, and would make
``mainline_boundary.greps`` — which only wants the *path* — pay for a template engine. Import
the stage you want.

Nothing in this package calls a model, a clock, a network or a database at import time. The one
tier that can reach a model (``render.bedrock``) requires ``--allow-live``, refuses any
inference profile that is not ``au.*``, and is served from the committed cache on every dated
path.
"""

from __future__ import annotations

from typing import Final

#: Kept in step with ``[project] version`` in this distribution's ``pyproject.toml``.
__version__: Final[str] = "0.1.0"

#: The stages, in the order the pipeline runs them. Names only — importing this module
#: must not import any of them (see the module docstring).
STAGES: Final[tuple[str, ...]] = (
    "gazetteer",
    "skeleton",
    "moc_stream",
    "blame",
    "injectors",
    "prompts",
    "render",
    "reflow",
    "docx",
)

__all__: Final[tuple[str, ...]] = ("STAGES", "__version__")
