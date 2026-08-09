# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Loading the corpus, and putting the workspace sources on ``sys.path``.

A module rather than ``conftest.py`` on purpose. Several directories in this repository
carry a ``conftest.py``, and under pytest's prepend import mode they all want the module
name ``conftest``; a test file that said ``from conftest import CASES`` would be asserting
that pytest bound the name to *this* one. A distinctly-named module cannot be shadowed,
and the corpus is too load-bearing to import by luck.

The ``sys.path`` insertions are a convenience for a checkout where ``uv sync`` has not run
since a package landed. They are not a substitute for installation, which is why the skip
reasons elsewhere say "not importable" rather than "not installed".
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CORPUS_DIR = HERE / "corpus"
FIXTURES_DIR = HERE / "fixtures"

_SRC_ROOTS = (
    REPO_ROOT / "verticals/mainline/packages/mainline-quarantine/src",
    REPO_ROOT / "verticals/mainline/packages/mainline-domain/src",
    REPO_ROOT / "packages/mainline-agentkit/src",
)
for _root in _SRC_ROOTS:
    if _root.is_dir() and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))


#: ``(...) Tj`` with PDF string escaping. Enough for an uncompressed content stream, which
#: is what ``corpus/pdf/table_cell_injection.pdf`` deliberately is; it is not a PDF parser
#: and does not pretend to be one. The format router - Docling, Textract, the DOCX native
#: path - belongs to another domain, and layers 2 to 6 all operate on extracted text.
_PDF_TEXT_OP = re.compile(r"\((?P<text>(?:\\.|[^\\()])*)\)\s*Tj")


def extract_pdf_text(path: Path) -> str:
    """Pull the text-showing operators out of an uncompressed PDF content stream."""
    raw = path.read_bytes().decode("latin-1")
    cells: list[str] = []
    for match in _PDF_TEXT_OP.finditer(raw):
        body = match.group("text")
        cells.append(body.replace(r"\(", "(").replace(r"\)", ")").replace("\\\\", "\\"))
    return "\n".join(cells)


def load_cases() -> list[dict[str, Any]]:
    """Every corpus case, sorted by id so failures are reported in a stable order."""
    cases: list[dict[str, Any]] = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        case["_path"] = str(path.relative_to(REPO_ROOT).as_posix())
        if case.get("pdf"):
            case["document"] = extract_pdf_text(CORPUS_DIR / case["pdf"])
        cases.append(case)
    return cases


CASES = load_cases()


def load_script(relative: str, module_name: str) -> ModuleType:
    """Import a module under ``scripts/`` by PATH, never by adding a directory to sys.path.

    ``scripts/agents/`` would be importable as the top-level name ``agents``, and this
    repository also has ``tests/agents/``. Which one won would then depend on the order
    pytest happened to prepend directories in - and the module being resolved here is the
    one that proves layer 1 over the whole tree. It is imported by its path.
    """
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
