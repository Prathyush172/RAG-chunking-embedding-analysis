"""
preprocess.py — RFC text cleaning pipeline.

Cleans raw RFC plain-text files from datasets/ and writes output to data/clean/.
The cleaned text is the single source of truth for all character offsets.
Cleaning steps (applied in order):
1. Replace form feed characters (\\x0c) with newlines.
2. Remove page footer lines: ^\S.*\[Page \d+\]\s*$
3. Remove page header lines: ^RFC \d+\s{2,}.+\s{2,}\w+ \d{4}\s*$
4. Strip trailing whitespace from every line.
5. Collapse 3+ consecutive blank lines into exactly 2.
6. Preserve section numbers, headings, and ASCII diagrams.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Regex patterns for RFC boilerplate removal
_FOOTER_RE = re.compile(r"^\S.*\[Page \d+\]\s*$", re.MULTILINE)
_HEADER_RE = re.compile(r"^RFC \d+\s{2,}.+\s{2,}\w+ \d{4}\s*$", re.MULTILINE)
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n{4,}")  # 3+ blank lines = 4+ newlines

_REPO_ROOT = Path(__file__).resolve().parent  # project root (preprocess.py is at root)


def load_corpus_config(config_path: Path | None = None) -> list[dict]:
    """Load corpus.yaml and return the list of document entries."""
    if config_path is None:
        config_path = _REPO_ROOT / "configs" / "corpus.yaml"
    with open(config_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data["corpus"]


def clean_text(raw: str) -> tuple[str, dict[str, int]]:
    """
    Clean a raw RFC text string.

    Returns:
        (cleaned_text, stats) where stats maps removal category -> line count.
    """
    stats: dict[str, int] = {
        "form_feeds": 0,
        "footer_lines": 0,
        "header_lines": 0,
        "trailing_ws_lines": 0,
        "blank_lines_collapsed": 0,
    }

    # 1. Replace form feeds with newlines
    ff_count = raw.count("\x0c")
    stats["form_feeds"] = ff_count
    text = raw.replace("\x0c", "\n")

    # 2. Remove footer lines (count matches; each match is one line)
    footer_matches = _FOOTER_RE.findall(text)
    stats["footer_lines"] = len(footer_matches)
    text = _FOOTER_RE.sub("", text)

    # 3. Remove header lines
    header_matches = _HEADER_RE.findall(text)
    stats["header_lines"] = len(header_matches)
    text = _HEADER_RE.sub("", text)

    # 4. Strip trailing whitespace
    lines_before = text.split("\n")
    stripped_lines = [line.rstrip() for line in lines_before]
    stats["trailing_ws_lines"] = sum(
        1 for a, b in zip(lines_before, stripped_lines) if a != b
    )
    text = "\n".join(stripped_lines)

    # 5. Collapse 3+ consecutive blank lines into 2
    # Count how many blank-line runs had 3+ blanks
    multi_blank_matches = _MULTI_BLANK_RE.findall(text)
    stats["blank_lines_collapsed"] = len(multi_blank_matches)
    text = _MULTI_BLANK_RE.sub("\n\n\n", text)

    # Ensure single trailing newline
    text = text.rstrip("\n") + "\n"

    return text, stats


def preprocess_document(
    doc: dict,
    repo_root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Read one raw RFC file, clean it, and write the result.

    Args:
        doc:       Entry from corpus.yaml.
        repo_root: Repository root (defaults to parent of this file's grandparent).
        dry_run:   If True, do not write the output file.

    Returns:
        Stats dict for this document.
    """
    root = repo_root or _REPO_ROOT
    src = root / doc["file"]
    dst = root / doc["clean_file"]

    if not src.exists():
        raise FileNotFoundError(f"Raw RFC file not found: {src}")

    raw = src.read_text(encoding="utf-8", errors="replace")
    cleaned, stats = clean_text(raw)

    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(cleaned, encoding="utf-8")
        logger.info("Written: %s (%d chars)", dst, len(cleaned))

    return stats


def run_preprocessing(
    config_path: Path | None = None,
    repo_root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, dict[str, int]]:
    """
    Run preprocessing for all documents in the corpus config.

    Returns:
        Mapping doc_id -> stats dict.
    """
    docs = load_corpus_config(config_path)
    all_stats: dict[str, dict[str, int]] = {}

    for doc in docs:
        doc_id = doc["doc_id"]
        logger.info("Preprocessing %s (RFC %s)…", doc_id, doc["rfc_number"])
        try:
            stats = preprocess_document(doc, repo_root=repo_root, dry_run=dry_run)
            all_stats[doc_id] = stats
            _print_stats(doc_id, doc["rfc_number"], stats)
        except FileNotFoundError as exc:
            logger.error("Skipping %s: %s", doc_id, exc)
            all_stats[doc_id] = {"error": str(exc)}

    return all_stats


def _print_stats(doc_id: str, rfc_number: int, stats: dict[str, int]) -> None:
    """Print removal statistics for one document."""
    print(f"\n{'='*60}")
    print(f"  {doc_id}  (RFC {rfc_number})")
    print(f"{'='*60}")
    for key, val in stats.items():
        label = key.replace("_", " ").capitalize()
        print(f"  {label:<35} {val:>6}")


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python preprocess.py`."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Preprocess RFC plain-text files.")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to corpus.yaml (default: configs/corpus.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report stats without writing output files.",
    )
    args = parser.parse_args(argv)

    all_stats = run_preprocessing(config_path=args.config, dry_run=args.dry_run)
    total_removed = sum(
        sum(v for k, v in s.items() if k != "error")
        for s in all_stats.values()
        if "error" not in s
    )
    print(f"\nTotal boilerplate items removed across all documents: {total_removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
