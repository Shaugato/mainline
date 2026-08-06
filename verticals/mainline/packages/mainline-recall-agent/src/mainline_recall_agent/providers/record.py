# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Cassette recorder.  Opt-in twice, on purpose.

    MAINLINE_RECALL_CASSETTE_MODE=record MAINLINE_RECALL_ALLOW_NETWORK=1 \\
      python -m mainline_recall_agent.providers.record --provider bedrock --facet mechanism

Recording issues real, billable calls against real safety narratives, so it never happens
because a test happened to miss.  A miss in replay raises ``CassetteMiss`` and names the
digest and the command to record it.

The fixture corpus lives at ``tests/fixtures/cassettes/recall/fixture_corpus.json`` and is
composed through ``embed_text`` — the same D3 template both the event side and the permit
side use — so the recorded vectors are of the strings the system actually embeds, not of
bare cue text.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .base import embed_text
from .cassette import CassetteStore, RecordingEmbeddingProvider, assert_recording_permitted
from .types import FACETS

__all__ = ["load_fixture_corpus", "main"]

FIXTURE_CORPUS_NAME = "fixture_corpus.json"


def load_fixture_corpus(store: CassetteStore | None = None) -> list[dict[str, Any]]:
    """Load the committed fixture corpus (cue records, not composed strings)."""
    root = (store or CassetteStore()).root
    path = root / FIXTURE_CORPUS_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = list(document["cues"])
    return entries


def composed_texts(entries: list[dict[str, Any]], facet: str) -> list[str]:
    return [
        embed_text(
            activity_path=entry["activity_path"],
            asset_class=entry["asset_class"],
            facet=facet,
            cue_text=entry["facets"][facet],
        )
        for entry in entries
        if facet in entry["facets"]
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record recall provider cassettes.")
    parser.add_argument("--provider", choices=("bedrock", "local"), required=True)
    parser.add_argument("--facet", choices=FACETS, action="append", default=None)
    parser.add_argument("--revision", default=os.environ.get("MAINLINE_BGE_REVISION"))
    parser.add_argument("--cassette-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    assert_recording_permitted()
    store = CassetteStore(args.cassette_dir) if args.cassette_dir else CassetteStore()
    facets = args.facet or list(FACETS)

    if args.provider == "bedrock":
        from .bedrock_titan import BedrockTitanV2

        inner: Any = BedrockTitanV2()
        provenance = "bedrock-live"
    else:
        from .local_bge import LocalBGE

        inner = LocalBGE(revision=args.revision)
        provenance = "local-bge"

    recorder = RecordingEmbeddingProvider(
        inner,
        store,
        provenance=provenance,
        note=f"fixture corpus, recorded via {args.provider}",
    )
    entries = load_fixture_corpus(store)
    written = 0
    for facet in facets:
        texts = composed_texts(entries, facet)
        if not texts:
            continue
        recorder.embed(texts, facet)
        written += len(texts)
    print(f"recorded {written} embedding cassettes under {store.root}")
    print(f"embed_model={recorder.model_id} index_gen={recorder.index_gen}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
