#!/usr/bin/env python3
"""Validate wiki/ against SCHEMA.md §4 (edge table) and §1-3 (field contract).

Can be run standalone (`python3 scripts/lint.py`) to check whatever is
currently on disk, or imported by compile_index.py, which passes an
in-memory `pages` snapshot (with 被引用于 already filled in) so ERRORs are
caught before anything is written to index/.

Exit code is 1 iff any ERROR was found (WARN/INFO never fail the build).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ACTION_DIR,
    COMMAND_DIR,
    FAULTCASE_DIR,
    PageError,
    ROOT,
    anchor_text,
    fuzzy_match,
    read_page,
)


@dataclass
class Finding:
    level: str  # ERROR | WARN | INFO
    page: str
    message: str


Pages = dict[str, dict[str, tuple[dict, str, Path]]]  # {"faultcase": {id: (fm, body, path)}, ...}


def load_pages() -> Pages:
    pages: Pages = {"faultcase": {}, "action": {}, "command": {}}
    for kind, dir_ in (
        ("faultcase", FAULTCASE_DIR),
        ("action", ACTION_DIR),
        ("command", COMMAND_DIR),
    ):
        for path in sorted(dir_.glob("*.md")):
            try:
                fm, body = read_page(path)
            except PageError as e:
                pages.setdefault("_load_errors", []).append(str(e))  # type: ignore[union-attr]
                continue
            pid = fm.get("id")
            if pid:
                pages[kind][pid] = (fm, body, path)
    return pages


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def compute_expected_refs(pages: Pages) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Forward-edge scan used both by lint's back-edge reconciliation and by
    compile_index.py to fill 被引用于 before anything is written to disk."""
    fc_pages = pages["faultcase"]
    expected_act_refs: dict[str, set[str]] = {aid: set() for aid in pages["action"]}
    expected_cmd_refs: dict[str, set[str]] = {cid: set() for cid in pages["command"]}
    for fc_id, (fm, _body, _path) in fc_pages.items():
        for cmd_id in fm.get("涉及命令", []):
            expected_cmd_refs.setdefault(cmd_id, set()).add(fc_id)
        for step in fm.get("判据分流", []):
            cmd_id = step.get("命令")
            if cmd_id:
                expected_cmd_refs.setdefault(cmd_id, set()).add(fc_id)
            for field_name in ("否则", "满足"):
                val = step.get(field_name)
                if isinstance(val, str) and val.startswith("ACT-"):
                    expected_act_refs.setdefault(val, set()).add(fc_id)
    return expected_act_refs, expected_cmd_refs


def check(pages: Pages | None = None) -> tuple[list[Finding], list[Finding], list[Finding]]:
    pages = pages if pages is not None else load_pages()
    errors: list[Finding] = []
    warns: list[Finding] = []
    infos: list[Finding] = []

    fc_pages = pages["faultcase"]
    act_pages = pages["action"]
    cmd_pages = pages["command"]

    # forward-edge accumulators, used for the back-edge reconciliation pass
    expected_act_refs, expected_cmd_refs = compute_expected_refs(pages)

    for fc_id, (fm, body, path) in fc_pages.items():
        rel = _rel(path)
        source = fm.get("source")
        if not source or not (ROOT / source).exists():
            errors.append(Finding("ERROR", rel, f"source 不存在: {source!r}"))
            continue

        step_nums = {s.get("step") for s in fm.get("判据分流", [])}
        involved = set(fm.get("涉及命令", []))

        for cmd_id in involved:
            if cmd_id not in cmd_pages:
                errors.append(Finding("ERROR", rel, f"涉及命令 引用不存在的 CMD 页: {cmd_id}"))
            else:
                expected_cmd_refs[cmd_id].add(fc_id)

        for step in fm.get("判据分流", []):
            step_no = step.get("step")
            step_label = f"step {step_no}"

            cmd_id = step.get("命令")
            if cmd_id:
                if cmd_id not in cmd_pages:
                    errors.append(
                        Finding("ERROR", rel, f"{step_label}.命令 引用不存在的 CMD 页: {cmd_id}")
                    )
                else:
                    expected_cmd_refs[cmd_id].add(fc_id)
                if cmd_id not in involved:
                    warns.append(
                        Finding(
                            "WARN", rel, f"{step_label}.命令 {cmd_id} 未出现在 涉及命令 列表中"
                        )
                    )

            for field_name in ("否则", "满足"):
                val = step.get(field_name)
                if isinstance(val, str) and val.startswith("goto step"):
                    try:
                        n = int(val.split()[-1])
                    except ValueError:
                        errors.append(
                            Finding("ERROR", rel, f"{step_label}.{field_name} 无法解析的 goto: {val!r}")
                        )
                        continue
                    if n not in step_nums:
                        errors.append(
                            Finding(
                                "ERROR",
                                rel,
                                f"{step_label}.{field_name} goto step {n} 越界（本页 step 集合: {sorted(step_nums)}）",
                            )
                        )
                elif isinstance(val, str) and val.startswith("ACT-"):
                    if val not in act_pages:
                        errors.append(
                            Finding("ERROR", rel, f"{step_label}.{field_name} 引用不存在的 ACT 页: {val}")
                        )
                    else:
                        expected_act_refs[val].add(fc_id)
                elif field_name == "满足" and isinstance(val, dict) and val.get("_uncertain"):
                    warns.append(Finding("WARN", rel, f"{step_label}.满足 标记为 _uncertain，需人工补全"))
                elif field_name == "满足" and val not in (None, "故障排除") and not (
                    isinstance(val, str) and (val.startswith("goto") or val == "故障排除")
                ):
                    if not isinstance(val, dict):
                        errors.append(
                            Finding("ERROR", rel, f"{step_label}.满足 取值非法: {val!r}")
                        )

            anchor = step.get("判据锚点")
            judge = step.get("判据") or step.get("动作") or step.get("检查", "")
            if anchor:
                try:
                    text = anchor_text(source, anchor)
                except PageError as e:
                    errors.append(Finding("ERROR", rel, f"{step_label}.判据锚点 非法: {e}"))
                else:
                    if not fuzzy_match(judge, text):
                        errors.append(
                            Finding(
                                "ERROR",
                                rel,
                                f"{step_label}.判据锚点 {anchor} 与判据文本不匹配: "
                                f"判据={judge!r} vs 正文={text!r}",
                            )
                        )
            else:
                errors.append(Finding("ERROR", rel, f"{step_label} 缺少 判据锚点"))

    for act_id, (fm, body, path) in act_pages.items():
        rel = _rel(path)
        requires = fm.get("requires") or []
        orders = [r.get("order") for r in requires]
        if orders != list(range(1, len(orders) + 1)):
            errors.append(Finding("ERROR", rel, f"requires.order 不是从1连续递增: {orders}"))

        if requires:
            anchor = fm.get("requires锚点")
            if not anchor:
                errors.append(Finding("ERROR", rel, "requires 非空但缺少 requires锚点"))
            else:
                source = fm.get("source")
                try:
                    text = anchor_text(source, anchor)
                except PageError as e:
                    errors.append(Finding("ERROR", rel, f"requires锚点 非法: {e}"))
                else:
                    for r in requires:
                        cmd = r.get("命令", "")
                        if not fuzzy_match(f"`{cmd}`", text):
                            warns.append(
                                Finding(
                                    "WARN",
                                    rel,
                                    f"requires order={r.get('order')} 命令 {cmd!r} 在锚点区间内未找到匹配",
                                )
                            )

        actual_refs = set(fm.get("被引用于", []))
        expected = expected_act_refs.get(act_id, set())
        if actual_refs != expected:
            errors.append(
                Finding(
                    "ERROR",
                    rel,
                    f"被引用于 与正向边对账不一致: 实际={sorted(actual_refs)} 期望={sorted(expected)}",
                )
            )
        if not expected:
            warns.append(Finding("WARN", rel, "孤儿 Action 页：没有任何 FaultCase 触发它"))

    seen_cmd_seq: dict[tuple, list[str]] = {}
    for cmd_id, (fm, body, path) in cmd_pages.items():
        rel = _rel(path)
        actual_refs = set(fm.get("被引用于", []))
        expected = expected_cmd_refs.get(cmd_id, set())
        if actual_refs != expected:
            errors.append(
                Finding(
                    "ERROR",
                    rel,
                    f"被引用于 与正向边对账不一致: 实际={sorted(actual_refs)} 期望={sorted(expected)}",
                )
            )
        if not expected:
            warns.append(Finding("WARN", rel, "孤儿 Command 页：没有任何 FaultCase 引用它"))

    for act_id, (fm, body, path) in act_pages.items():
        seq = tuple((s.get("视图"), s.get("命令")) for s in fm.get("命令序列", []))
        seen_cmd_seq.setdefault(seq, []).append(act_id)
    for seq, ids in seen_cmd_seq.items():
        if len(ids) > 1:
            warns.append(
                Finding("WARN", "wiki/action/*", f"疑似重复 Action（命令序列相同）: {ids}")
            )

    infos.append(Finding("INFO", "-", f"FaultCase: {len(fc_pages)}, Action: {len(act_pages)}, Command: {len(cmd_pages)}"))
    n_edges = (
        sum(len(fm.get("判据分流", [])) for fm, _, _ in fc_pages.values())
        + sum(len(expected) for expected in expected_act_refs.values())
        + sum(len(expected) for expected in expected_cmd_refs.values())
    )
    infos.append(Finding("INFO", "-", f"边（含 goto/触发修复/uses）约: {n_edges}"))

    return errors, warns, infos


def main() -> int:
    errors, warns, infos = check()
    for f in errors:
        print(f"ERROR [{f.page}] {f.message}")
    for f in warns:
        print(f"WARN  [{f.page}] {f.message}")
    for f in infos:
        print(f"INFO  [{f.page}] {f.message}")
    print(f"\n{len(errors)} error(s), {len(warns)} warn(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
