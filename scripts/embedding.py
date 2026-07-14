#!/usr/bin/env python3
"""Text -> embedding vector, single seam for swapping mock <-> real backend.

kb_engine.KB uses this for match_fault's semantic recall leg. Real backend
calls an OpenAI-compatible embeddings endpoint; mock backend needs no network
and no extra dependency, so the dual-path code exercises end-to-end in this
sandbox without reaching the internal embedding service. Set
KB_EMBEDDING_BASE_URL to switch to the real endpoint once it's reachable from
wherever this runs.
"""
from __future__ import annotations

import hashlib
import math
import os
import re

_MOCK_DIM = 128


def _mock_embed(text: str) -> list[float]:
    """Deterministic bag-of-char-bigrams hash embedding.

    Not a real model — it only makes cosine similarity track character-level
    overlap (shared substrings/tokens), which is enough to prove out the
    dual-path scoring and fusion logic before the real endpoint is wired in.
    A real model would also catch paraphrases/hypernyms with no character
    overlap at all (e.g. "组播业务" vs "组播多拓扑"); this mock will not.
    """
    vec = [0.0] * _MOCK_DIM
    flat = re.sub(r"\s+", "", text.lower())
    bigrams = [flat[i : i + 2] for i in range(len(flat) - 1)] or [flat]
    for bg in bigrams:
        h = int(hashlib.md5(bg.encode("utf-8")).hexdigest(), 16)
        vec[h % _MOCK_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _real_embed(text: str, model: str = "qwen3-embedding-0.6b") -> list[float]:
    import httpx
    from openai import OpenAI

    base_url = os.environ["KB_EMBEDDING_BASE_URL"]
    api_key = os.environ.get("KB_EMBEDDING_API_KEY", "sk-1234")
    client = OpenAI(api_key=api_key, base_url=base_url, http_client=httpx.Client(verify=False))
    response = client.embeddings.create(input=text, model=model)
    return response.data[0].embedding


def embed(text: str) -> list[float]:
    """KB_EMBEDDING_BASE_URL unset (default) -> mock. Set it -> real endpoint."""
    if os.environ.get("KB_EMBEDDING_BASE_URL"):
        return _real_embed(text)
    return _mock_embed(text)


def semantic_text(fm: dict) -> str:
    """Frontmatter -> the text actually embedded for a FaultCase.

    title + 症状实体 (not full 正文): keeps embedding calls cheap and keeps
    the signal aligned with what the keyword leg (entity_inverted.json)
    already indexes, so match_fault's score fusion compares like with like
    rather than a short query against a whole raw document's worth of noise.
    Shared by compile_index.py (writes index/embeddings.json at build time)
    and kb_engine.py (embeds the live query the same way at match time).
    """
    return " ".join([fm.get("title", ""), *fm.get("症状实体", [])])


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
