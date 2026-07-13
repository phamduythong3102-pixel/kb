#!/usr/bin/env python3
"""raw/*.md -> wiki/{faultcase,action,command}/*.md

Section 7 of the design spec calls for an LLM call to turn each fault
document into typed frontmatter. This repo has no LLM API wired into the
sandbox that runs this script, so `extract_steps()` below is a deterministic
stand-in tuned to the "IS-IS 多拓扑路由不正确" document template: numbered
steps, one `执行 \`command\` 命令` per step, one negative/positive branch pair
per step (optionally preceded by a "字段值为/中包含" judgement paragraph and
followed by a prerequisite bullet list), and a final "收集信息联系技术支持"
step. Real heterogeneous documents would replace `extract_steps()` with an
actual model call — the seam is deliberately a single function so that swap
is local. Anything the extractor can't pin down is marked `_uncertain: true`
per SCHEMA.md rather than guessed.

Usage:
    python3 scripts/ingest.py [raw/FC-...md ...]   # default: all of raw/
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ACTION_DIR,
    COMMAND_DIR,
    FAULTCASE_DIR,
    RAW_DIR,
    normalize_command,
    write_page,
)

STEP_HEADER_RE = re.compile(r"^(\d+)\.\s+(.+)$")
CMD_LITERAL_RE = re.compile(r"`([^`]+)`")
FIELD_VALUE_RE = re.compile(
    r"如果显示信息字段\s*(?P<field>\S+(?:\s+\S+)*?)\s*值为\s*(?P<v1>[^，,；;]+)，"
    r"则(?P<d1>[^；;]+)；如果显示信息字段\s*(?P=field)\s*值为\s*(?P<v2>[^，,；;]+)，"
    r"则(?P<d2>[^。]+)。"
)
FIELD_CONTAIN_RE = re.compile(
    r"如果显示信息字段\s*(?P<field>\S+(?:\s+\S+)*?)\s*中包含\s*(?P<v>[^，,；;]+)，"
    r"则(?P<d1>[^；;]+)；否则(?P<d2>[^。]+)。"
)
GOTO_STEP_RE = re.compile(r"请执行步骤(\d+)")
FAULT_CLEARED_RE = re.compile(r"故障已经排除")
LEADING_COND_RE = re.compile(r"^如果(.+?)[，,]")
FIELD_MISSING_RE = re.compile(r"未包含字段\s*([^，,]+)")
FIELD_PRESENT_RE = re.compile(r"(?<!未)包含字段\s*([^，,]+)")
VIEW_CMD_RE = re.compile(r"在(?P<view>[^下]+)下执行命令\s*`(?P<cmd>[^`]+)`")
TITLE_RE = re.compile(r"^(?:IS-IS\s*)?(?P<mt>.+?)拓扑中(?:路由信息)?不正确$")
# A branch bullet triggers a dedicated Action page only when it uses the
# imperative "请在<视图>下执行命令 `X`" instruction template. Softer phrasing
# like "并确认...已执行命令 `X`" (a diagnostic re-check, not an instruction)
# is deliberately excluded and falls through to an inline 否则 action instead.
ACT_TRIGGER_RE = re.compile(r"请在(?P<view>[^视图]*?视图)下执行命令\s*`(?P<cmd>[^`]+)`")
NEGATIVE_KEYWORDS = ("未包含", "没有", "不正确", "对端设备")


@dataclass
class Block:
    start: int
    end: int
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def anchor(self) -> str:
        return f"L{self.start}-L{self.end}"


def split_blocks(lines: list[str], start_idx: int) -> list[Block]:
    blocks: list[Block] = []
    i, n = start_idx, len(lines)
    while i < n:
        if lines[i].strip() == "":
            i += 1
            continue
        start = i
        while i < n and lines[i].strip() != "":
            i += 1
        blocks.append(Block(start + 1, i, lines[start:i]))
        i += 1
    return blocks


@dataclass
class PendingAction:
    id: str
    view: str
    raw_cmd: str
    requires: list[dict] = field(default_factory=list)
    requires_anchor: str | None = None


def action_id_from_bullet(bullet_text: str, raw_cmd: str) -> tuple[str, str]:
    """Derive an ACT id/title from the clause following the command mention.

    e.g. "...执行命令 `isis topology multicast`，配置接口加入组播拓扑。"
    -> ("ACT-配置接口加入组播拓扑", "配置接口加入组播拓扑")
    """
    after = bullet_text.split(f"`{raw_cmd}`", 1)[1]
    after = after.lstrip("，, ")
    phrase = re.split("[。；]", after)[0].strip()
    phrase = re.sub(r"^使能", "使能", phrase)  # no-op, keeps intent explicit
    if not phrase:
        phrase = raw_cmd
    return f"ACT-{phrase}", phrase


def parse_doc(raw_path: Path) -> dict:
    text = raw_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title_line = lines[0].lstrip("# ").strip()
    heading_idx = next(i for i, l in enumerate(lines) if l.strip() == "#### 操作步骤")
    blocks = split_blocks(lines, heading_idx + 1)

    m = TITLE_RE.match(title_line.replace("IS-IS ", "").replace("IS-IS", ""))
    topology_phrase = None
    if m:
        topology_phrase = m.group("mt") + "拓扑"
    symptom_entities = ["IS-IS"]
    _uncertain_entities = topology_phrase is None
    if topology_phrase:
        symptom_entities.append(topology_phrase)
    else:
        symptom_entities.append(title_line)
    symptom_entities.append("路由不正确")

    steps: list[dict] = []
    pending_actions: dict[str, PendingAction] = {}
    used_cmd_ids: list[str] = []
    used_cmd_raw: dict[str, set[str]] = {}

    def register_cmd(raw_cmd: str) -> str:
        cid, _ = normalize_command(raw_cmd)
        used_cmd_ids.append(cid)
        used_cmd_raw.setdefault(cid, set()).add(raw_cmd)
        return cid

    j = 0
    while j < len(blocks):
        header_m = STEP_HEADER_RE.match(blocks[j].lines[0])
        if not header_m:
            j += 1
            continue
        step_num = int(header_m.group(1))
        title_text = header_m.group(2)

        if "联系技术支持" in title_text and "收集" in title_text:
            collect_start = blocks[j].start
            bullet_lines: list[str] = []
            k = j + 1
            while k < len(blocks):
                bullet_lines.extend(l.lstrip("- ").rstrip("。") for l in blocks[k].lines)
                k += 1
            collect_end = blocks[-1].end
            steps.append(
                {
                    "step": step_num,
                    "检查": "收集信息联系技术支持",
                    "动作": "收集" + "、".join(bullet_lines),
                    "判据锚点": f"L{collect_start}-L{collect_end}",
                }
            )
            j = k
            continue

        j += 1
        cmd_block = blocks[j]
        cmd_m = CMD_LITERAL_RE.search(cmd_block.text)
        raw_cmd = cmd_m.group(1) if cmd_m else None
        cmd_id = register_cmd(raw_cmd) if raw_cmd else None
        j += 1

        judge_text = None
        anchor_block = None
        desc_m = None
        if j < len(blocks):
            desc_m = FIELD_VALUE_RE.search(blocks[j].text) or FIELD_CONTAIN_RE.search(
                blocks[j].text
            )
        if desc_m:
            gd = desc_m.groupdict()
            if "v1" in gd:
                up_is_v1 = "没有" not in gd["d1"]
                pos_v, neg_v = (gd["v1"], gd["v2"]) if up_is_v1 else (gd["v2"], gd["v1"])
                judge_text = f"{gd['field']} 值为 {pos_v}（非 {neg_v}）"
            else:
                judge_text = f"{gd['field']} 中包含 {gd['v']}"
            anchor_block = blocks[j]
            j += 1

        # Gather every block belonging to this step's branch section: single-
        # line "- " blocks are the two branch bullets (order in the source
        # text is not reliable — some docs state the positive branch first,
        # e.g. the route-check step); multi-line "- " blocks are a
        # prerequisite command list; anything else is throwaway intro prose.
        branch_blocks: list[Block] = []
        prereq_block: Block | None = None
        while j < len(blocks) and not STEP_HEADER_RE.match(blocks[j].lines[0]):
            b = blocks[j]
            if b.lines[0].startswith("- ") and len(b.lines) == 1:
                branch_blocks.append(b)
            elif b.lines[0].startswith("- ") and len(b.lines) > 1:
                prereq_block = b
            j += 1
        if len(branch_blocks) != 2:
            raise ValueError(f"{raw_path}: step {step_num}: expected 2 branch bullets, "
                              f"found {len(branch_blocks)}")

        def is_negative(text: str) -> bool:
            return any(kw in text for kw in NEGATIVE_KEYWORDS)

        neg_candidates = [b for b in branch_blocks if is_negative(b.lines[0])]
        neg_block = neg_candidates[0] if neg_candidates else branch_blocks[0]
        pos_block = next((b for b in branch_blocks if b is not neg_block), branch_blocks[-1])
        neg_text = neg_block.lines[0].lstrip("- ").strip()
        pos_text = pos_block.lines[0].lstrip("- ").strip()

        otherwise: object
        act_trigger_m = ACT_TRIGGER_RE.search(neg_text)
        if act_trigger_m:
            neg_raw_cmd = act_trigger_m.group("cmd")
            act_id, _phrase = action_id_from_bullet(neg_text, neg_raw_cmd)
            pa = pending_actions.setdefault(
                act_id,
                PendingAction(id=act_id, view=act_trigger_m.group("view"), raw_cmd=neg_raw_cmd),
            )
            register_cmd(neg_raw_cmd)
            otherwise = act_id

            if prereq_block is not None:
                requires = []
                for order, line in enumerate(prereq_block.lines, start=1):
                    rm = VIEW_CMD_RE.search(line)
                    if rm:
                        requires.append(
                            {"order": order, "视图": rm.group("view"), "命令": rm.group("cmd")}
                        )
                pa.requires = requires
                pa.requires_anchor = prereq_block.anchor
        elif "对端设备" in neg_text:
            _, _, tail = neg_text.partition("请")
            action_clause = ("请" + tail).strip() if tail else neg_text
            action_clause = action_clause.lstrip("请")
            first, _, rest = action_clause.partition("，")
            otherwise = {"动作": first.rstrip("。"), "备注": rest.rstrip("。")} if rest else {
                "动作": action_clause.rstrip("。")
            }
        else:
            goto_m = GOTO_STEP_RE.search(neg_text)
            if goto_m:
                otherwise = f"goto step {goto_m.group(1)}"
            else:
                clause = re.sub(r"^如果[^，]*，", "", neg_text).strip()
                otherwise = {"动作": clause.rstrip("。")}

        goto_m = GOTO_STEP_RE.search(pos_text)
        if goto_m:
            satisfies = f"goto step {goto_m.group(1)}"
        elif FAULT_CLEARED_RE.search(pos_text):
            satisfies = "故障排除"
        else:
            satisfies = None

        if judge_text is None:
            cond_m = LEADING_COND_RE.match(pos_text)
            if cond_m:
                judge_text = cond_m.group(1)
            else:
                miss = FIELD_MISSING_RE.search(neg_text) or FIELD_PRESENT_RE.search(neg_text)
                judge_text = f"回显包含字段 {miss.group(1)}" if miss else neg_text

        if anchor_block:
            anchor = anchor_block.anchor
        else:
            lo = min(neg_block.start, pos_block.start)
            hi = max(neg_block.end, pos_block.end)
            anchor = f"L{lo}-L{hi}"

        step_entry = {
            "step": step_num,
            "检查": title_text,
            "判据": judge_text,
            "判据锚点": anchor,
            "否则": otherwise,
            "满足": satisfies if satisfies else {"_uncertain": True},
        }
        if cmd_id:
            step_entry["命令"] = cmd_id
        steps.append(step_entry)

    fc_id_guess = raw_path.stem.split("-isis")[0]
    return {
        "id": fc_id_guess,
        "title": title_line,
        "症状实体": symptom_entities,
        "_uncertain_entities": _uncertain_entities,
        "涉及命令": list(dict.fromkeys(used_cmd_ids)),
        "used_cmd_raw": used_cmd_raw,
        "判据分流": steps,
        "pending_actions": pending_actions,
        "source": f"raw/{raw_path.name}",
    }


COMMAND_TYPE_DISPLAY_PREFIX = "display"


def write_command_pages(all_cmds: dict[str, set[str]], fc_ref_map: dict[str, list[str]]) -> None:
    for cmd_id, raw_forms in all_cmds.items():
        path = COMMAND_DIR / f"{cmd_id}.md"
        canonical = None
        aliases = set()
        for raw in sorted(raw_forms):
            norm_id, display = normalize_command(raw)
            assert norm_id == cmd_id
            if canonical is None:
                canonical = display
            if raw != canonical:
                aliases.add(raw)
        cmd_type = "display" if canonical.startswith(COMMAND_TYPE_DISPLAY_PREFIX) else "config"
        fm = {
            "type": "Command",
            "id": cmd_id,
            "命令": canonical,
            "类型": cmd_type,
            "别名": sorted(aliases),
            "被引用于": [],
        }
        refs = fc_ref_map.get(cmd_id, [])
        body_lines = [f"# {canonical}", ""]
        if refs:
            body_lines.append("由以下故障案例引用（构建脚本聚合，见各案例判据分流）：")
            body_lines.append("")
            for r in refs:
                body_lines.append(f"- {r}")
            body_lines.append("")
        write_page(path, fm, "\n".join(body_lines))


def write_action_pages(doc: dict) -> None:
    for act_id, pa in doc["pending_actions"].items():
        path = ACTION_DIR / f"{act_id}.md"
        fm = {
            "type": "Action",
            "id": act_id,
            "命令序列": [{"视图": pa.view, "命令": pa.raw_cmd}],
            "requires": pa.requires,
            "被引用于": [],
            "source": doc["source"],
        }
        if pa.requires_anchor:
            fm["requires锚点"] = pa.requires_anchor
        raw_lines = (RAW_DIR / Path(doc["source"]).name).read_text(encoding="utf-8").splitlines()
        if pa.requires_anchor:
            from common import parse_anchor

            start, _ = parse_anchor(pa.requires_anchor)
            intro_start = start - 1
            while intro_start > 1 and raw_lines[intro_start - 2].strip() != "":
                intro_start -= 1
            _, end = parse_anchor(pa.requires_anchor)
            body = "\n".join(raw_lines[intro_start - 1 : end])
        else:
            body = f"执行命令 `{pa.raw_cmd}`。"
        write_page(path, fm, f"# {act_id[len('ACT-') :]}\n\n{body}\n")


def write_faultcase_page(doc: dict) -> None:
    fc_id = doc["id"]
    raw_path = RAW_DIR / Path(doc["source"]).name
    matches = list(FAULTCASE_DIR.glob(f"{fc_id}-*.md"))
    path = matches[0] if matches else FAULTCASE_DIR / f"{fc_id}-{raw_path.stem}.md"

    # 别名 (entity synonyms) is a human/LLM-curated cold-start step (SCHEMA.md
    # §7): preserve it across re-ingests instead of clobbering it back to
    # empty every time the structural extraction reruns.
    existing_alias = None
    if path.exists():
        from common import read_page

        try:
            existing_fm, _ = read_page(path)
            existing_alias = existing_fm.get("别名")
        except Exception:
            pass

    fm = {
        "type": "FaultCase",
        "id": fc_id,
        "title": doc["title"],
        "症状实体": doc["症状实体"],
    }
    if existing_alias:
        fm["别名"] = existing_alias
    fm["涉及命令"] = doc["涉及命令"]
    fm["判据分流"] = [dict(s) for s in doc["判据分流"]]
    fm["source"] = doc["source"]
    if doc.get("_uncertain_entities"):
        fm["_uncertain_entities"] = True

    body = raw_path.read_text(encoding="utf-8")
    write_page(path, fm, f"\n{body}")


def main(argv: list[str]) -> None:
    targets = [Path(a) for a in argv] if argv else sorted(RAW_DIR.glob("*.md"))
    all_docs = [parse_doc(p) for p in targets]

    all_cmds: dict[str, set[str]] = {}
    fc_ref_map: dict[str, list[str]] = {}
    for doc in all_docs:
        for cmd_id in doc["涉及命令"]:
            all_cmds.setdefault(cmd_id, set()).update(doc["used_cmd_raw"].get(cmd_id, ()))
            fc_ref_map.setdefault(cmd_id, [])
            if doc["id"] not in fc_ref_map[cmd_id]:
                fc_ref_map[cmd_id].append(doc["id"])

    for doc in all_docs:
        write_faultcase_page(doc)
        write_action_pages(doc)
    write_command_pages(all_cmds, fc_ref_map)

    print(f"ingested {len(all_docs)} doc(s):")
    for doc in all_docs:
        n_actions = len(doc["pending_actions"])
        print(f"  {doc['id']}: {len(doc['判据分流'])} steps, {n_actions} action(s) derived")


if __name__ == "__main__":
    main(sys.argv[1:])
