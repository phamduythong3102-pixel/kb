#!/usr/bin/env python3
"""wiki/ -> index/{entity_inverted,alias,edges}.json (+ 被引用于 back-edges).

Order of operations (all in-memory first, nothing touches disk until the
whole thing validates clean):
  1. load wiki/
  2. compute 被引用于 from the forward edges and merge into the in-memory
     Action/Command frontmatter
  3. run lint.check() against that merged snapshot
  4. ERROR -> abort, nothing written. clean -> write the updated wiki pages
     (被引用于 only) and the four index/*.json files.

This is what makes 被引用于 "generated, never hand-written" (SCHEMA.md §4)
and what makes index/ a pure build artifact (design principle 6).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import INDEX_DIR, dump_json, normalize_command, write_page  # noqa: E402
import lint  # noqa: E402


def build_entity_inverted(fc_pages: dict) -> dict[str, list[str]]:
    inverted: dict[str, set[str]] = {}
    for fc_id, (fm, _body, _path) in fc_pages.items():
        for entity in fm.get("症状实体", []):
            inverted.setdefault(entity, set()).add(fc_id)
    return {k: sorted(v) for k, v in sorted(inverted.items())}


def build_alias(fc_pages: dict, cmd_pages: dict) -> dict[str, str]:
    alias: dict[str, str] = {}

    def add(raw: str, canonical: str) -> None:
        raw = raw.strip()
        if raw and raw != canonical:
            alias[raw] = canonical
        alias.setdefault(canonical, canonical)

    for _fc_id, (fm, _body, _path) in fc_pages.items():
        for entity, variants in (fm.get("别名") or {}).items():
            for v in variants:
                add(v, entity)
            add(entity, entity)
    for cmd_id, (fm, _body, _path) in cmd_pages.items():
        canonical_text = fm.get("命令", "")
        for v in fm.get("别名") or []:
            add(v, cmd_id)
        add(canonical_text, cmd_id)
        add(cmd_id, cmd_id)
    return dict(sorted(alias.items()))


def build_edges(fc_pages: dict, act_pages: dict, cmd_pages: dict) -> dict[str, list[dict]]:
    """Cross-page entity edges only. `goto` stays inside each FaultCase's own
    判据分流 (it's page-internal step navigation, already served in full by
    get_procedure) rather than being duplicated into this graph index."""
    edges: dict[str, list[dict]] = {}

    def add_edge(src: str, edge: dict) -> None:
        edges.setdefault(src, []).append(edge)

    for fc_id, (fm, _body, _path) in fc_pages.items():
        seen_cmd = set()
        seen_act = set()
        for step in fm.get("判据分流", []):
            cmd_id = step.get("命令")
            if cmd_id and cmd_id not in seen_cmd:
                add_edge(fc_id, {"type": "uses", "to": cmd_id, "via": f"step{step.get('step')}"})
                seen_cmd.add(cmd_id)
            for field_name in ("否则",):
                val = step.get(field_name)
                if isinstance(val, str) and val.startswith("ACT-") and val not in seen_act:
                    add_edge(
                        fc_id,
                        {"type": "触发修复", "to": val, "via": f"step{step.get('step')}"},
                    )
                    seen_act.add(val)
        for cmd_id in fm.get("涉及命令", []):
            if cmd_id not in seen_cmd:
                add_edge(fc_id, {"type": "uses", "to": cmd_id, "via": "涉及命令"})
                seen_cmd.add(cmd_id)

    for act_id, (fm, _body, _path) in act_pages.items():
        for r in fm.get("requires", []):
            raw_cmd = r.get("命令", "")
            resolved_id, _display = normalize_command(raw_cmd)
            to = resolved_id if resolved_id in cmd_pages else raw_cmd
            add_edge(
                act_id,
                {
                    "type": "requires",
                    "to": to,
                    "order": r.get("order"),
                    "视图": r.get("视图"),
                    "命令": raw_cmd,
                    "resolved": resolved_id in cmd_pages,
                },
            )
    # 被引用于 is not stored as its own out-edge here: it is the reverse of
    # `uses`/`触发修复` (design principle 4), already recoverable as an
    # in-edge of the ACT/CMD node via the forward edges above. kb_engine's
    # query_entity treats edge_type="被引用于" as an alias for those two
    # types when looking at in-edges, which keeps this adjacency list free
    # of duplicate/redundant entries while still matching the 被引用于 field
    # persisted in the Action/Command frontmatter (SCHEMA.md §4).

    return dict(sorted(edges.items()))


def main() -> int:
    pages = lint.load_pages()
    expected_act_refs, expected_cmd_refs = lint.compute_expected_refs(pages)

    for act_id, (fm, body, path) in pages["action"].items():
        fm["被引用于"] = sorted(expected_act_refs.get(act_id, set()))
    for cmd_id, (fm, body, path) in pages["command"].items():
        fm["被引用于"] = sorted(expected_cmd_refs.get(cmd_id, set()))

    errors, warns, infos = lint.check(pages)
    if errors:
        print(f"compile_index: {len(errors)} ERROR(s), refusing to write index/. Run "
              f"scripts/lint.py for details.")
        for e in errors:
            print(f"  ERROR [{e.page}] {e.message}")
        return 1

    for kind in ("action", "command"):
        for pid, (fm, body, path) in pages[kind].items():
            write_page(path, fm, body)

    fc_pages, act_pages, cmd_pages = pages["faultcase"], pages["action"], pages["command"]
    INDEX_DIR.mkdir(exist_ok=True)
    dump_json(INDEX_DIR / "entity_inverted.json", build_entity_inverted(fc_pages))
    dump_json(INDEX_DIR / "alias.json", build_alias(fc_pages, cmd_pages))
    dump_json(INDEX_DIR / "edges.json", build_edges(fc_pages, act_pages, cmd_pages))

    print("compile_index: OK")
    for w in warns:
        print(f"  WARN [{w.page}] {w.message}")
    for i in infos:
        print(f"  INFO [{i.page}] {i.message}")
    print(f"  wrote {INDEX_DIR}/{{entity_inverted,alias,edges}}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
