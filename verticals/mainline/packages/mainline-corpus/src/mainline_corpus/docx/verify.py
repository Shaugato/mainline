# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The reproducibility proof, and the control that makes it worth having.

── THE FOUR WAYS ────────────────────────────────────────────────────────────────────────────

The brief asks for byte equality asserted four ways.  Three are executable here and one is not,
and saying which is which is the point:

1. **Two in-process renders.**  Catches a cache, a mutable default, a dict whose order depends
   on insertion, anything that makes the second call differ from the first.
2. **Two subprocess renders.**  Catches everything a fresh interpreter would change:
   ``PYTHONHASHSEED`` (salted ``hash()`` reaching a sort), import order, module-level state
   built at first import.  In-process equality cannot see any of that, which is why the second
   pair is not redundant with the first.
3. **In-process against subprocess**, and both against the committed bytes on disk.
4. **ubuntu-latest against windows-latest.**  This worker has one operating system.  The matrix
   leg is *engineered* here — stored compression, pinned member metadata, LF-only generated XML,
   no locale, no clock — and must be *asserted* by a CI job that runs on both.  That job belongs
   to ``.github/workflows/corpus.yml``, which this worker does not own; see the cross-domain
   note.  Nothing in this file claims the matrix is green, because this file cannot know.

── THE RED CONTROL ──────────────────────────────────────────────────────────────────────────

PL-2: a suite that has never been red asserts nothing.  For a reproducibility claim the trap is
specific and quiet — DOS timestamps have **two-second** resolution, so two renders a second apart
agree by accident even with the pin removed, and the suite passes for the wrong reason.

:func:`pin_is_load_bearing` closes that hole without depending on timing.  It exercises the
*unpinned* path — ``ZipFile.writestr(name_as_str, data)``, which is exactly the call
``python-docx``'s ``_ZipPkgWriter`` makes — and requires the resulting member timestamp to differ
from the epoch we pin to.  If that ever stops being true, the equality findings have quietly
stopped demonstrating that our pin is what produces the equality, and this check goes red.

The first version of that control was wrong in an instructive way, and the function's docstring
records it: it probed ``ZipInfo(filename=…)``, whose ``date_time`` default *is* the DOS epoch, so
the control passed while proving nothing.  Writing a control that fails for the right reason is
the same discipline as writing a test that goes red for the right reason.

── THE OPTIONAL CHECK THAT EARNED ITS PLACE ─────────────────────────────────────────────────

:func:`opens_with_python_docx` runs only when ``python-docx`` happens to be importable, and it is
not a dependency.  On its first run it rejected all thirteen documents: the main part had been
typed with the WordprocessingML *namespace URI* instead of its *content type*, a one-token
mistake that our own reader could never have caught, because our own reader never looks at
``[Content_Types].xml``.  Word would have called every file corrupt.  That is the whole argument
for keeping a third-party parse in the loop even when it must be allowed to skip.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tokenize
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .build_templates import build_all_templates, check_templates, templates_root
from .manifest import MANIFEST_NAME, digest, manifest_text, read_manifest
from .render import render_all, rendered_root
from .sources import RENDER_TARGETS, RETYPESET_PAIR, SPINE_CLAUSE_UUID, build_document
from .template import _rename_map
from .zipwriter import FIXED_DATE_TIME, read_package

__all__ = [
    "Finding",
    "check_all",
    "manifest_entries",
    "pin_is_load_bearing",
    "retypeset_pair_record",
]

#: Assembled from fragments so that this module's own source does not trip the scan it performs.
_BANNED_TOKENS: Final[tuple[str, ...]] = (
    "datetime." + "now",
    "date." + "today",
    "time." + "time(",
    "time." + "localtime",
    "uuid" + "4(",
    "uuid" + "1(",
    "strf" + "time(",
    "locale." + "getlocale",
    "getdefault" + "locale",
    "random." + "random(",
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One check and what it found.  ``skipped`` is never silent: it always carries a reason."""

    name: str
    ok: bool
    detail: str
    skipped: bool = False

    def line(self) -> str:
        status = "SKIP" if self.skipped else ("PASS" if self.ok else "FAIL")
        return f"[{status}] {self.name}: {self.detail}"


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def _src_root() -> Path:
    """Return the directory that must be on ``PYTHONPATH`` for ``mainline_corpus``."""
    return _package_dir().parents[1]


# ── the artefact set the manifest covers ─────────────────────────────────────────────────────


def manifest_entries(rendered: Mapping[str, bytes]) -> dict[str, bytes]:
    """``{path relative to fixtures/corpus: bytes}`` for every ``.docx`` stage 3 produces."""
    entries = {f"templates/{key}.docx": payload for key, payload in build_all_templates().items()}
    entries.update({f"rendered/{name}": payload for name, payload in rendered.items()})
    return entries


# ── individual checks ────────────────────────────────────────────────────────────────────────


def pin_is_load_bearing() -> Finding:
    """Prove the pin is load-bearing: the unpinned path must still stamp a wall clock.

    Written the first time against ``ZipInfo(filename=...)`` and **wrong**: that constructor's
    ``date_time`` default *is* the DOS epoch, so the control passed trivially and proved nothing.
    The wall clock enters through ``ZipFile.writestr(name_as_str, data)``, which mints a
    ``ZipInfo`` with ``time.localtime()`` — and that is precisely the call ``python-docx``'s
    ``_ZipPkgWriter`` makes for every part.  So the control exercises *that* call, on a throwaway
    archive, and requires the result to differ from the epoch we pin to.

    If this check ever passes trivially — if a future ``zipfile`` stopped stamping the clock —
    the byte-equality findings would have quietly stopped demonstrating that our pin is what
    produces the equality, and this goes red to say so.
    """
    probe = io.BytesIO()
    with zipfile.ZipFile(probe, mode="w") as archive:
        archive.writestr("word/document.xml", b"<w:document/>")
    with zipfile.ZipFile(io.BytesIO(probe.getvalue())) as archive:
        observed = archive.infolist()[0].date_time
    if observed == FIXED_DATE_TIME:
        return Finding(
            "pin_is_load_bearing",
            ok=False,
            detail=(
                f"the unpinned writestr path already stamps {FIXED_DATE_TIME}, so the "
                "byte-equality checks no longer demonstrate that our pin is what produces the "
                "equality. Re-derive the control before trusting the suite."
            ),
        )
    return Finding(
        "pin_is_load_bearing",
        ok=True,
        detail=(
            f"the unpinned writestr path stamps {observed} (wall clock); every member this "
            f"package writes carries {FIXED_DATE_TIME} instead"
        ),
    )


def templates_agree_with_builder() -> Finding:
    """Require the committed templates to be exactly what ``build_templates.py`` produces."""
    root = templates_root()
    if not root.is_dir():
        return Finding(
            "templates_committed",
            ok=False,
            detail=f"{root} does not exist; run `build-templates` to write the eight templates",
        )
    drifted = check_templates(root)
    if drifted:
        return Finding(
            "templates_committed",
            ok=False,
            detail=(
                f"{len(drifted)} template(s) differ from a fresh build: {', '.join(drifted)}. "
                "A template is a generated artefact; edit build_templates.py, never the .docx."
            ),
        )
    return Finding(
        "templates_committed",
        ok=True,
        detail=(
            f"all {len(build_all_templates())} committed templates match their builder, "
            "byte for byte"
        ),
    )


def _subprocess_digests() -> dict[str, str]:
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH", "")
    root = str(_src_root())
    environment["PYTHONPATH"] = f"{root}{os.pathsep}{existing}" if existing else root
    # A fresh interpreter is the point: PYTHONHASHSEED, import order and module-level state are
    # exactly what an in-process repeat cannot observe.
    completed = subprocess.run(
        [sys.executable, "-m", "mainline_corpus.docx", "digests"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        cwd=str(_src_root()),
        timeout=600,
    )
    parsed: dict[str, str] = json.loads(completed.stdout)
    return parsed


def four_way_equality() -> list[Finding]:
    """Two in-process renders, two subprocess renders, and the committed bytes on disk."""
    first = {name: digest(payload) for name, payload in render_all().items()}
    second = {name: digest(payload) for name, payload in render_all().items()}
    findings = [_compare("in_process_repeat", first, second)]
    try:
        third = _subprocess_digests()
        fourth = _subprocess_digests()
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
        findings.append(
            Finding("subprocess_repeat", ok=False, detail=f"subprocess render failed: {exc}")
        )
        return findings
    findings.append(_compare("subprocess_repeat", third, fourth))
    findings.append(_compare("in_process_vs_subprocess", first, third))
    findings.append(_on_disk(first))
    return findings


def _compare(name: str, left: Mapping[str, str], right: Mapping[str, str]) -> Finding:
    if left == right:
        return Finding(name, ok=True, detail=f"{len(left)} documents, identical digests")
    differing = sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))
    return Finding(
        name,
        ok=False,
        detail=f"{len(differing)} document(s) differ between runs: {', '.join(differing[:5])}",
    )


def _on_disk(expected: Mapping[str, str]) -> Finding:
    root = rendered_root()
    missing = [name for name in expected if not (root / name).is_file()]
    if missing:
        return Finding(
            "committed_bytes",
            ok=False,
            detail=(
                f"{len(missing)} rendered document(s) are not committed: {', '.join(missing[:5])}. "
                "Run `render` before `verify`."
            ),
        )
    actual = {name: digest((root / name).read_bytes()) for name in expected}
    return _compare("committed_bytes", dict(expected), actual)


def manifest_reproduces(rendered: Mapping[str, bytes]) -> Finding:
    """``MANIFEST.docx.sha256`` on disk must equal the one a fresh build computes."""
    path = rendered_root() / MANIFEST_NAME
    if not path.is_file():
        return Finding("manifest", ok=False, detail=f"{path} is missing; run `render` first")
    expected = manifest_text(manifest_entries(rendered))
    if path.read_text(encoding="utf-8") == expected:
        return Finding(
            "manifest",
            ok=True,
            detail=f"{MANIFEST_NAME} reproduces exactly ({len(expected.splitlines())} files)",
        )
    committed = read_manifest(path)
    fresh = read_manifest_from_text(expected)
    differing = sorted(
        key for key in set(committed) | set(fresh) if committed.get(key) != fresh.get(key)
    )
    return Finding(
        "manifest",
        ok=False,
        detail=f"{len(differing)} entr(ies) differ: {', '.join(differing[:5])}",
    )


def read_manifest_from_text(text: str) -> dict[str, str]:
    """Parse manifest text held in memory, in the same format :mod:`manifest` writes."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip():
            head, _, tail = line.partition("  ")
            result[tail] = head
    return result


def _executable_source(path: Path) -> str:
    """Return a module's source with every comment and string literal blanked out.

    The scan has to read *code*, not prose.  Half the modules in this package explain in their
    docstrings exactly which clock they refuse to call, and a substring scan over raw text turns
    every one of those explanations into a violation — which trains a reader to ignore the check,
    which is worse than not having it.  ``tokenize`` gives the distinction for free.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    blanked = [list(line) for line in lines]
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type not in {tokenize.COMMENT, tokenize.STRING}:
                continue
            (start_row, start_col), (end_row, end_col) = token.start, token.end
            for row in range(start_row, end_row + 1):
                line = blanked[row - 1]
                first = start_col if row == start_row else 0
                last = end_col if row == end_row else len(line)
                for column in range(first, min(last, len(line))):
                    if line[column] not in "\r\n":
                        line[column] = " "
    return "".join("".join(line) for line in blanked)


def no_banned_tokens() -> Finding:
    """No wall clock, no entropy, no locale anywhere in this package's executable source."""
    offenders: list[str] = []
    for path in sorted(_package_dir().glob("*.py")):
        text = _executable_source(path)
        offenders.extend(f"{path.name}:{token}" for token in _BANNED_TOKENS if token in text)
    if offenders:
        return Finding(
            "no_wall_clock",
            ok=False,
            detail=(
                f"banned construct(s) present: {', '.join(offenders)}. A clock, an entropy source "
                "or a locale lookup inside a reproducible artefact is a defect, not a convenience."
            ),
        )
    return Finding(
        "no_wall_clock",
        ok=True,
        detail=f"{len(_BANNED_TOKENS)} banned constructs absent from every module in the package",
    )


def retypeset_pair_record() -> dict[str, Any]:
    """State the K3 claim as data: one identity, two house styles, two labels, two ordinals."""
    before_name, after_name = RETYPESET_PAIR
    targets = {target.output_name: target for target in RENDER_TARGETS}
    before = build_document(targets[before_name])
    after = build_document(targets[after_name])
    left = before.clause_by_uuid(SPINE_CLAUSE_UUID)
    right = after.clause_by_uuid(SPINE_CLAUSE_UUID)
    if left is None or right is None:
        raise LookupError(
            f"the spine clause {SPINE_CLAUSE_UUID} is absent from "
            f"{before_name if left is None else after_name}; the retypeset pair cannot make the "
            "identity claim it exists to make"
        )
    return {
        "clause_uuid": SPINE_CLAUSE_UUID,
        "identity_held": left.clause_uuid == right.clause_uuid,
        "before": {
            "document": before_name,
            "generation": before.generation,
            "printed_label": left.printed_label,
            "ordinal": left.ordinal,
            "heading": f"{left.heading_number} {left.heading_title}",
        },
        "after": {
            "document": after_name,
            "generation": after.generation,
            "printed_label": right.printed_label,
            "ordinal": right.ordinal,
            "heading": f"{right.heading_number} {right.heading_title}",
        },
        "label_changed": left.printed_label != right.printed_label,
        "ordinal_changed": left.ordinal != right.ordinal,
    }


def retypeset_pair_check(rendered: Mapping[str, bytes]) -> Finding:
    """Assert the done-when: 7.3 becomes 5.2.1, the ordinal moves, the identity does not."""
    record = retypeset_pair_record()
    before_name, after_name = RETYPESET_PAIR
    problems: list[str] = []
    if not record["identity_held"]:
        problems.append("clause_uuid differs across the pair")
    if not record["label_changed"]:
        problems.append("printed_label did not change")
    if not record["ordinal_changed"]:
        problems.append("ordinal did not change")
    for name, label in (
        (before_name, record["before"]["printed_label"]),
        (after_name, record["after"]["printed_label"]),
    ):
        payload = rendered.get(name)
        if payload is None:
            problems.append(f"{name} was not rendered")
            continue
        document_xml = read_package(payload)["word/document.xml"].decode("utf-8")
        if f">{label}</w:t>" not in document_xml:
            problems.append(f"{name} does not print the label {label}")
    if problems:
        return Finding("retypeset_pair", ok=False, detail="; ".join(problems))
    return Finding(
        "retypeset_pair",
        ok=True,
        detail=(
            f"{SPINE_CLAUSE_UUID} is printed {record['before']['printed_label']} at ordinal "
            f"{record['before']['ordinal']} in generation 1 and "
            f"{record['after']['printed_label']} at ordinal {record['after']['ordinal']} in "
            "generation 2; the identity is unchanged"
        ),
    )


def relationship_ids_normalised(rendered: Mapping[str, bytes]) -> Finding:
    """Every rendered package's relationship ids are already ``rId1…rIdN`` in canonical order."""
    offenders: list[str] = []
    for name, payload in sorted(rendered.items()):
        for part_name, part in sorted(read_package(payload).items()):
            if not part_name.endswith(".rels"):
                continue
            rename = _rename_map(part.decode("utf-8"), part_name)
            if any(old != new for old, new in rename.items()):
                offenders.append(f"{name}:{part_name}")
    if offenders:
        return Finding(
            "rid_normalised",
            ok=False,
            detail=f"relationship ids are not canonical in {', '.join(offenders[:5])}",
        )
    return Finding(
        "rid_normalised",
        ok=True,
        detail=f"every .rels part in {len(rendered)} documents is already in canonical rId order",
    )


def opens_with_python_docx(rendered: Mapping[str, bytes]) -> Finding:
    """If ``python-docx`` happens to be installed, make it open every document we produced.

    Skipped with a reason when it is not.  ``python-docx`` is not in ``uv.lock`` and this build
    does not require it; when a developer does have it, this is a genuine third-party parse of
    our output rather than our own reader agreeing with our own writer.
    """
    try:
        import docx
    except ImportError:
        return Finding(
            "python_docx_opens",
            ok=True,
            skipped=True,
            detail="python-docx is not installed; stage 3 does not require it (ADR 0034)",
        )
    failures: list[str] = []
    for name, payload in sorted(rendered.items()):
        try:
            document = docx.Document(io.BytesIO(payload))
        except (ValueError, KeyError, OSError) as exc:
            failures.append(f"{name}: {exc}")
            continue
        if not document.paragraphs:
            failures.append(f"{name}: opened but contains no paragraphs")
    if failures:
        return Finding("python_docx_opens", ok=False, detail="; ".join(failures[:3]))
    return Finding(
        "python_docx_opens",
        ok=True,
        detail=f"python-docx opened all {len(rendered)} documents",
    )


def check_all() -> list[Finding]:
    """Run every check, in the order a reader should read them."""
    findings = [pin_is_load_bearing(), no_banned_tokens(), templates_agree_with_builder()]
    rendered = render_all()
    findings.extend(four_way_equality())
    findings.append(manifest_reproduces(rendered))
    findings.append(retypeset_pair_check(rendered))
    findings.append(relationship_ids_normalised(rendered))
    findings.append(opens_with_python_docx(rendered))
    return findings


def failed(findings: Sequence[Finding]) -> list[Finding]:
    """Return the findings that are neither passing nor skipped."""
    return [finding for finding in findings if not finding.ok and not finding.skipped]
