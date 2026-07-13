"""Shared helpers for ingest.py / compile_index.py / lint.py.

Keeps I/O, anchor handling, and command normalization in one place so the
three pipeline stages agree on format. See ../SCHEMA.md for the field
contract this module implements.
"""
from __future__ import annotations

import re
import functools
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw"
WIKI_DIR = ROOT / "wiki"
FAULTCASE_DIR = WIKI_DIR / "faultcase"
ACTION_DIR = WIKI_DIR / "action"
COMMAND_DIR = WIKI_DIR / "command"
INDEX_DIR = ROOT / "index"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


class PageError(ValueError):
    pass


def read_page(path: Path) -> tuple[dict[str, Any], str]:
    """Split a wiki markdown file into (frontmatter dict, body text)."""
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise PageError(f"{path}: missing frontmatter block")
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)
    return fm, body


def write_page(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    yaml_text = yaml.dump(
        frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    path.write_text(f"---\n{yaml_text}---\n{body}", encoding="utf-8")


def all_wiki_pages() -> list[Path]:
    return sorted(FAULTCASE_DIR.glob("*.md")) + sorted(ACTION_DIR.glob("*.md")) + sorted(
        COMMAND_DIR.glob("*.md")
    )


# ---------------------------------------------------------------------------
# Anchors: "L<start>-L<end>", 1-indexed, inclusive, into a raw/*.md file.
# ---------------------------------------------------------------------------

ANCHOR_RE = re.compile(r"^L(\d+)-L(\d+)$")


def parse_anchor(anchor: str) -> tuple[int, int]:
    m = ANCHOR_RE.match(anchor.strip())
    if not m:
        raise PageError(f"malformed anchor: {anchor!r}")
    start, end = int(m.group(1)), int(m.group(2))
    if start < 1 or end < start:
        raise PageError(f"invalid anchor range: {anchor!r}")
    return start, end


@functools.lru_cache(maxsize=None)
def _raw_lines(source_rel: str) -> tuple[str, ...]:
    path = ROOT / source_rel
    return tuple(path.read_text(encoding="utf-8").splitlines())


def anchor_text(source_rel: str, anchor: str) -> str:
    start, end = parse_anchor(anchor)
    lines = _raw_lines(source_rel)
    if end > len(lines):
        raise PageError(f"{source_rel}: anchor {anchor} exceeds file length ({len(lines)} lines)")
    return "\n".join(lines[start - 1 : end])


def _char_bigrams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", s)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i : i + 2] for i in range(len(s) - 1)}


_TOKEN_SPLIT_RE = re.compile(r"[\s，,。；;（）()「」【】、：:—-]+")


def _tokens(s: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT_RE.split(s) if len(t) >= 2 and t not in ("非", "则", "如果")]


def fuzzy_match(needle: str, haystack: str, threshold: float = 0.5) -> bool:
    """True if `needle` plausibly derives from `haystack`.

    Three strategies, any one sufficient (see SCHEMA.md §4 回链) — this is a
    drift/hallucination check, not an exact-quote check, since judge text is
    a build-time paraphrase of the source sentence (e.g. "X 值为 A（非 B）"
    summarizing "如果...值为 A...；如果...值为 B...没有Up"):
    1. Any backtick-quoted or bare command-like literal in `needle` appears
       verbatim in `haystack`.
    2. Character-bigram Jaccard overlap >= threshold.
    3. Most of `needle`'s meaningful (len>=2) tokens, split on punctuation,
       appear verbatim as substrings of `haystack` (>= threshold fraction).
    """
    literals = re.findall(r"`([^`]+)`", needle)
    if not literals:
        literals = [needle]
    haystack_flat = re.sub(r"\s+", "", haystack)
    for lit in literals:
        lit_flat = re.sub(r"\s+", "", lit)
        if lit_flat and lit_flat in haystack_flat:
            return True

    a, b = _char_bigrams(needle), _char_bigrams(haystack)
    if a and b and len(a & b) / len(a | b) >= threshold:
        return True

    tokens = _tokens(needle)
    if tokens:
        hits = sum(1 for t in tokens if re.sub(r"\s+", "", t) in haystack_flat)
        if hits / len(tokens) >= threshold:
            return True

    return False


# ---------------------------------------------------------------------------
# Command normalization (SCHEMA.md §5)
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"<[^>]+>|\btopology-name\b|\btopology-id\b")
_UNDO_RE = re.compile(r"^\s*undo\s+")
# Command families whose trailing "topology <word>" argument selects a
# specific topology instance rather than identifying a different command —
# generalized so `display isis route topology multicast` and
# `display isis route topology ipv6-unicast` collapse to one CMD entity.
# This is a documented, corpus-specific heuristic (SCHEMA.md §5); it is not
# a general CLI-argument parser.
_TOPOLOGY_ARG_FAMILIES = ("display isis route",)
_TOPOLOGY_ARG_RE = re.compile(r"\btopology\s+\S+")
# Output-verbosity modifiers that don't change which entity a display
# command refers to; dropped from the id slug only, kept in the display form.
_ID_ONLY_DROP = {"verbose"}


def normalize_command(raw: str) -> tuple[str, str]:
    """Return (id_slug, normalized_display_form) for a raw command string.

    - strips backticks/whitespace
    - drops `undo` prefix
    - strips parameter placeholders (<...>, topology-name, topology-id)
    - generalizes trailing `topology <word>` for the families above
    - collapses whitespace, lowercases only the id slug (display form keeps
      original casing since Huawei CLI keywords are case-sensitive in docs)
    """
    text = raw.strip().strip("`").strip()
    text = _UNDO_RE.sub("", text)
    text = _PLACEHOLDER_RE.sub("", text)
    for family in _TOPOLOGY_ARG_FAMILIES:
        if text.startswith(family):
            text = _TOPOLOGY_ARG_RE.sub("topology <topology>", text)
    text = re.sub(r"\s+", " ", text).strip()
    slug_source = re.sub(r"<[^>]+>", "", text)
    slug_tokens = [t for t in slug_source.lower().split(" ") if t and t not in _ID_ONLY_DROP]
    slug = re.sub(r"[^a-z0-9]+", "-", " ".join(slug_tokens)).strip("-")
    return f"CMD-{slug}", text


def load_json(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    import json

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
