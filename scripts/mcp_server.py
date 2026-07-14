#!/usr/bin/env python3
"""MCP server exposing match_fault / get_procedure (spec §8; query_entity
exists in kb_engine.KB per §8.3 but is intentionally not registered as a
tool here — see the comment near the bottom of this file for why).

Loads index/*.json into memory once at startup (KB()) and never touches
disk again per request — "查询期零重基础设施" (design philosophy, §2).

Run: python3 scripts/mcp_server.py   (stdio transport)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_engine import KB  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("troubleshooting-kb")
kb = KB()


@mcp.tool()
def match_fault(query: str, top_k: int = 3) -> dict:
    """Match a (possibly colloquial or vague) fault description against the
    knowledge base's FaultCase entities. Returns ranked candidates and, when
    more than one candidate is returned, a discriminating check that
    distinguishes them without requiring the caller to read either
    procedure in full."""
    return kb.match_fault(query, top_k=top_k)


@mcp.tool()
def get_procedure(fault_id: str, include_fulltext: bool = True) -> dict:
    """Fetch a FaultCase's full 判据分流 (criteria-routing) chain, with every
    ACT-triggering branch inlined (command sequence + ordered requires
    chain), plus the verbatim source text for grounding."""
    return kb.get_procedure(fault_id, include_fulltext=include_fulltext)


# query_entity (one-hop FaultCase/Action/Command adjacency query) is
# deliberately not registered as an MCP tool: the ticket-driven caller this
# server serves only ever goes 现象 -> match_fault -> get_procedure, and
# get_procedure already inlines every ACT branch's command sequence and
# requires chain, so there is no point in this flow where a reverse/adjacency
# lookup gets used. KB.query_entity itself is untouched (still called
# directly by demo/showcase.py's scenario 3) — this only removes it from the
# Agent-facing tool surface so it doesn't compete for tool-selection budget.
# Re-add the @mcp.tool() decorator here if a caller that actually explores
# the graph (e.g. an ops/authoring tool) needs it.


if __name__ == "__main__":
    mcp.run(transport="stdio")
