#!/usr/bin/env python3
"""MCP server exposing match_fault / get_procedure / query_entity (spec §8).

Loads index/*.json into memory once at startup (KB()) and never touches
disk again per request — "查询期零重基础设施" (design philosophy, §2).

Run: python3 scripts/mcp_server.py   (stdio transport)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

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


@mcp.tool()
def query_entity(
    entity_id: str,
    direction: Literal["out", "in", "both"] = "both",
    edge_type: str | None = None,
) -> dict:
    """One-hop adjacency query over the FaultCase/Action/Command graph.
    e.g. entity_id="ACT-配置接口加入组播拓扑", direction="out",
    edge_type="requires" returns its ordered prerequisite command chain;
    entity_id="CMD-pim-sm", direction="in", edge_type="被引用于" returns
    which FaultCases this command can help resolve."""
    return kb.query_entity(entity_id, direction=direction, edge_type=edge_type)


if __name__ == "__main__":
    mcp.run(transport="stdio")
