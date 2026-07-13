#!/usr/bin/env python3
"""Executable demos for design-spec §9 (验收场景).

Calls kb_engine.KB() / lint.py in-process — no MCP transport needed to see
the tools work, matching how mcp_server.py just thinly wraps the same KB
class. Scenarios 4 and 5 mutate in-memory snapshots only; nothing on disk
is touched, so this is safe to run against the committed wiki/.

Usage:
    python3 demo/showcase.py            # run all 5
    python3 demo/showcase.py 2          # run just scenario 2
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from kb_engine import KB  # noqa: E402
import lint  # noqa: E402
from common import RAW_DIR  # noqa: E402


def hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def show(label: str, obj) -> None:
    print(f"\n-- {label} --")
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(obj)


# ---------------------------------------------------------------------------
# Scenario 1: gradient queries
# ---------------------------------------------------------------------------

def naive_fulltext_search(query: str) -> str | None:
    """A dumb keyword-overlap grep over raw/*.md, used only as an independent
    cross-check that the frontmatter layer lost no information relative to
    the full-text layer (spec: "①两法应打平，证明双粒度无信息损失")."""
    tokens = [t for t in re.split(r"[\s，。；、]+", query) if len(t) >= 2]
    best, best_score = None, -1
    for path in sorted(RAW_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        score = sum(text.count(t) for t in tokens)
        if score > best_score:
            best, best_score = path.stem, score
    return best


def scenario_1(kb: KB) -> None:
    hr("Scenario 1 — 梯度查询 (gradient queries)")

    queries_tier1 = ["IS-IS组播多拓扑中路由信息不正确"]
    queries_tier2 = ["组播业务不通，IS-IS学到的组播路由不对"]
    queries_tier3 = ["IS-IS路由有问题"]

    print("\n### ① 近似标题原文 — structured match vs naive full-text grep")
    for q in queries_tier1:
        structured = kb.match_fault(q)
        top1_structured = structured["candidates"][0]["fault_id"] if structured["candidates"] else None
        top1_fulltext = naive_fulltext_search(q)
        agree = top1_fulltext and top1_fulltext.startswith(top1_structured or "\0")
        show(f"query={q!r}", {
            "structured_top1": top1_structured,
            "fulltext_top1_stem": top1_fulltext,
            "agree": bool(agree),
        })

    print("\n### ② 同义改写 — entity normalization via alias.json")
    for q in queries_tier2:
        r = kb.match_fault(q)
        show(f"query={q!r}", r)

    print("\n### ③ 模糊描述 — ambiguous, resolved via discriminators")
    for q in queries_tier3:
        r = kb.match_fault(q)
        show(f"query={q!r}", r)


# ---------------------------------------------------------------------------
# Scenario 2: disambiguation
# ---------------------------------------------------------------------------

def scenario_2(kb: KB) -> None:
    hr("Scenario 2 — 消歧演示 (FC-0087 组播 vs FC-0092 IPv6单播, near-duplicate docs)")
    q = "IS-IS路由有问题"
    r = kb.match_fault(q)
    show(f"query={q!r}", r)
    n_candidates = len(r["candidates"])
    n_discriminators = len(r.get("discriminators", []))
    print(
        f"\n{n_candidates} candidates returned, {n_discriminators} discriminator(s) — "
        f"agent gets ONE check_command to run ({r['discriminators'][0]['check_command']!r} "
        f"looking for {r['discriminators'][0]['check_field']!r}) instead of both full procedures."
    )


# ---------------------------------------------------------------------------
# Scenario 3: substructure queries via query_entity
# ---------------------------------------------------------------------------

def scenario_3(kb: KB) -> None:
    hr("Scenario 3 — 子结构查询 (query_entity one-hop)")

    print("\n### \"配置 isis topology multicast 前需要什么\" -> requires chain (out)")
    r = kb.query_entity("ACT-配置接口加入组播拓扑", direction="out", edge_type="requires")
    chain = [
        f"{e['order']}. [{e['视图']}] {e['命令']}" + (f"  (-> {e['to']})" if e["resolved"] else "")
        for e in sorted(r["out"], key=lambda e: e["order"])
    ]
    show("ordered requires chain", chain)

    print("\n### \"pim sm 能解决哪些问题\" -> reverse edge (in, 被引用于)")
    r = kb.query_entity("CMD-pim-sm", direction="in", edge_type="被引用于")
    show("faultcases pim-sm helps resolve", [e["neighbor"] for e in r["in"]])


# ---------------------------------------------------------------------------
# Scenario 4: governance — lint catches a manufactured conflict
# ---------------------------------------------------------------------------

def scenario_4() -> None:
    hr("Scenario 4 — 治理演示 (lint catches build-time errors, in-memory only)")

    pages = lint.load_pages()
    broken = copy.deepcopy(pages)

    # (a) ERROR: dangling ACT reference — a doc author fat-fingers an Action id.
    fc_fm = broken["faultcase"]["FC-0087"][0]
    fc_fm["判据分流"][1]["否则"] = "ACT-使能PIM-SM-typo"

    # (b) ERROR: anchor drifts from what the 判据 text claims (e.g. a doc edit
    # shifted the paragraph but nobody re-anchored it).
    fc2_fm = broken["faultcase"]["FC-0092"][0]
    fc2_fm["判据分流"][0]["判据锚点"] = "L1-L2"

    # (c) WARN: two Actions whose 命令序列 collapse to the same normalized
    # command — a duplicate nobody noticed.
    act_fm, act_body, act_path = broken["action"]["ACT-使能PIM-SM"]
    dup_id = "ACT-使能PIM-SM-copy"
    broken["action"][dup_id] = (
        {**copy.deepcopy(act_fm), "id": dup_id, "被引用于": []},
        act_body,
        act_path.with_name(f"{dup_id}.md"),
    )

    errors, warns, infos = lint.check(broken)
    print(f"\nInjected: 1 dangling ACT ref, 1 anchor drift, 1 duplicate Action.")
    print(f"lint result: {len(errors)} ERROR(s), {len(warns)} WARN(s) — nothing written to disk.\n")
    for e in errors:
        print(f"  ERROR [{e.page}] {e.message}")
    for w in warns:
        print(f"  WARN  [{w.page}] {w.message}")
    print(
        "\nContrast: a hand-written or LLM-distilled skill with the same typo would silently "
        "route to a dead end at query time. Here it's caught before compile_index.py ever "
        "writes index/."
    )


# ---------------------------------------------------------------------------
# Scenario 5: fallback — deleted criterion, information still recoverable via 回链
# ---------------------------------------------------------------------------

def scenario_5(kb: KB) -> None:
    hr("Scenario 5 — 兜底演示 (deleted criterion, source text still recoverable)")

    proc = kb.get_procedure("FC-0087", include_fulltext=True)
    step2 = next(s for s in proc["判据分流"] if s["step"] == 2)

    degraded_step2 = dict(step2)
    lost_fact = "multicast (NO PIM)"
    del degraded_step2["判据"]

    print(f"\nSimulating an extraction that dropped step 2's 判据 field entirely.")
    show("degraded frontmatter for step 2 (判据 missing)", degraded_step2)

    fact_in_frontmatter = lost_fact in json.dumps(degraded_step2, ensure_ascii=False)
    fact_in_fulltext = lost_fact in proc["正文"]
    print(f"\n{lost_fact!r} present in degraded frontmatter: {fact_in_frontmatter}")
    print(f"{lost_fact!r} present in get_procedure's 正文 (回链, always a verbatim raw/ copy): {fact_in_fulltext}")
    print(
        "\n正文 is populated straight from source (ingest.py copies raw/*.md byte-for-byte) and "
        "is never derived from frontmatter, so no extraction miss can remove it from what the "
        "agent can retrieve — this is the 'source of truth backstop' from design principle 1."
    )


SCENARIOS = {1: scenario_1, 2: scenario_2, 3: scenario_3, 4: scenario_4, 5: scenario_5}


def main() -> None:
    kb = KB()
    which = sys.argv[1:] or ["1", "2", "3", "4", "5"]
    for w in which:
        n = int(w)
        fn = SCENARIOS[n]
        if n == 4:
            fn()
        else:
            fn(kb)


if __name__ == "__main__":
    main()
