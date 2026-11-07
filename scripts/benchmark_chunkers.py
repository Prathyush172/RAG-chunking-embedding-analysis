"""
scripts/benchmark_chunkers.py — Run all chunking configurations across all 4 RFCs.
Measures chunk counts, avg/min/max tokens, chunking time (median of 3 runs),
verifies invariants, and prints sample body chunks with populated sections.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.chunkers import build_chunker
from app.core.sections import parse_sections, sections_to_dict
from preprocess import clean_text, load_corpus_config


def main():
    import os
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    with open(REPO_ROOT / "configs" / "experiment.yaml", encoding="utf-8") as f:
        exp_cfg = yaml.safe_load(f)

    chunk_configs = exp_cfg["presets"]["full"]["chunking_configs"]
    docs = load_corpus_config()

    doc_data = {}
    for d in docs:
        doc_id = d["doc_id"]
        clean_path = REPO_ROOT / d["clean_file"]
        text = clean_path.read_text(encoding="utf-8")
        sections = sections_to_dict(parse_sections(text))
        doc_data[doc_id] = {
            "text": text,
            "sections": sections,
            "title": d["title"],
            "rfc": d["rfc_number"],
        }

    print("\n" + "=" * 95)
    print(f"{'RFC':<18} | {'Strategy & Config':<22} | {'Chunks':>6} | {'Avg Tok':>7} | {'Min Tok':>7} | {'Max Tok':>7} | {'Time (s)':>8}")
    print("=" * 95)

    sample_chunks_by_rfc = {d["doc_id"]: [] for d in docs}

    for doc_id, data in doc_data.items():
        text = data["text"]
        sections = data["sections"]
        for cfg in chunk_configs:
            strategy = cfg["strategy"]
            label = cfg["label"]

            kwargs = {}
            if strategy == "fixed":
                kwargs = {"chunk_tokens": cfg["chunk_tokens"], "overlap_pct": cfg["overlap_pct"]}
            elif strategy == "sentence":
                kwargs = {"chunk_tokens": cfg["chunk_tokens"], "overlap_sentences": cfg["overlap_sentences"]}
            elif strategy == "semantic":
                kwargs = {
                    "max_tokens": cfg["max_tokens"],
                    "min_tokens": cfg["min_tokens"],
                    "similarity_percentile": cfg["similarity_percentile"],
                }

            chunker = build_chunker(strategy, **kwargs)
            res = chunker.chunk(text, doc_id, sections=sections, verify=True, exclude_front_matter=True)
            chunks = res.chunks

            tok_counts = [c.token_count for c in chunks]
            avg_tok = sum(tok_counts) / len(tok_counts) if tok_counts else 0
            min_tok = min(tok_counts) if tok_counts else 0
            max_tok = max(tok_counts) if tok_counts else 0

            print(f"{doc_id:<18} | {label:<22} | {len(chunks):>6} | {avg_tok:>7.1f} | {min_tok:>7} | {max_tok:>7} | {res.elapsed_seconds:>8.3f}")

            # Grab 3 sample chunks from the body for each RFC under a representative config
            if label == "sent_256_0" and not sample_chunks_by_rfc[doc_id]:
                sample_chunks_by_rfc[doc_id] = chunks[:3]

    print("=" * 95)

    print("\n\n" + "#" * 95)
    print("SAMPLE BODY CHUNKS PER RFC (with section values)")
    print("#" * 95)

    for doc_id, chunks in sample_chunks_by_rfc.items():
        print(f"\n==================== Document: {doc_id} ====================")
        for idx, c in enumerate(chunks, 1):
            print(f"\n--- [{doc_id.upper()} Sample Chunk {idx}] ID: {c.chunk_id} ---")
            print(f"Section:    {c.section}")
            print(f"Span:       [{c.char_start}:{c.char_end}] ({c.char_end - c.char_start} chars)")
            print(f"Tokens:     {c.token_count}")
            print(f"Metadata:   {c.metadata}")
            preview = c.text.strip().replace("\n", " ")
            if len(preview) > 200:
                preview = preview[:200] + "... [truncated]"
            print(f"Text Preview: {preview}")


if __name__ == "__main__":
    main()
