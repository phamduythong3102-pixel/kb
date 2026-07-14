#!/usr/bin/env python3
"""Core query engine behind the MCP tools (section 8 of the design spec).

Pure Python, no MCP dependency here on purpose: mcp_server.py wraps this
module for the stdio server, and demo/*.py import it directly so the
showcase scripts don't need to spin up a subprocess MCP client to prove the
tools work.

Loads index/*.json once at construction ("MCP 服务启动时载入内存") and never
touches wiki/ again after that — all three tools are served purely from the
in-memory entity inverted index, alias table, and edge adjacency list.
"""
from __future__ import annotations

import re
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ACTION_DIR,
    COMMAND_DIR,
    FAULTCASE_DIR,
    INDEX_DIR,
    ROOT,
    load_json,
    read_page,
)
from embedding import cosine, embed  # noqa: E402

FIELD_RE = re.compile(r"字段\s*(\S+(?:\s+\S+)*?)(?:\s*值为|\s*中包含|，|$)")

# 被引用于 is the reverse of 触发修复/uses (design principle 4): it is not a
# distinct edge stored in edges.json, so a query_entity(edge_type="被引用于")
# is served by matching these underlying forward-edge types on the "in" side.
EDGE_TYPE_ALIASES = {"被引用于": {"uses", "触发修复"}}


class KB:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.entity_inverted: dict[str, list[str]] = load_json(INDEX_DIR / "entity_inverted.json")
        self.alias: dict[str, str] = load_json(INDEX_DIR / "alias.json")
        self.edges: dict[str, list[dict]] = load_json(INDEX_DIR / "edges.json")

        self._in_edges: dict[str, list[dict]] = {}
        for src, edge_list in self.edges.items():
            for e in edge_list:
                self._in_edges.setdefault(e["to"], []).append({**e, "from": src})

        self.fc: dict[str, dict] = {}
        self.act: dict[str, dict] = {}
        self.cmd: dict[str, dict] = {}
        for dir_, store in ((FAULTCASE_DIR, self.fc), (ACTION_DIR, self.act), (COMMAND_DIR, self.cmd)):
            for path in sorted(dir_.glob("*.md")):
                fm, body = read_page(path)
                store[fm["id"]] = {"fm": fm, "body": body, "path": path}

        # longest-alias-first so multi-word aliases win over short substrings
        self._alias_keys_sorted = sorted(self.alias.keys(), key=len, reverse=True)

        # Semantic recall leg (match_fault's second path, alongside the
        # entity_inverted keyword path). Precomputed by compile_index.py at
        # build time (SCHEMA.md §6) and just loaded here like every other
        # index file — a real embedding backend only gets called once per
        # compile, not once per KB() startup. A FaultCase page added without
        # rerunning compile_index.py won't have a vector yet; match_fault
        # treats that as "no semantic signal" for it rather than erroring.
        self._fc_vectors: dict[str, list[float]] = load_json(INDEX_DIR / "embeddings.json")

    # -- shared: query normalization ------------------------------------

    def normalize_query(self, query: str) -> list[str]:
        """query text -> canonical entities/CMD-ids it mentions, via alias.json."""
        q = query.lower()
        hits: list[str] = []
        covered = [False] * len(q)
        for key in self._alias_keys_sorted:
            kl = key.lower()
            idx = q.find(kl)
            if idx == -1:
                continue
            if any(covered[idx : idx + len(kl)]):
                continue
            for i in range(idx, idx + len(kl)):
                covered[i] = True
            canonical = self.alias[key]
            if canonical not in hits:
                hits.append(canonical)
        return hits

    # -- 8.1 match_fault ---------------------------------------------------

    # Fusion weights for the two recall legs (§ design discussion: keyword
    # path is precise but brittle to unlisted synonyms/hypernyms; semantic
    # path catches paraphrases the alias table doesn't know about but is
    # noisier). Keyword is weighted higher because entity_inverted hits are
    # curated/exact; semantic is a recall net, not the primary signal.
    _KEYWORD_WEIGHT = 0.6
    _SEMANTIC_WEIGHT = 0.4
    # Below this cosine similarity a semantic "hit" is noise, not a signal —
    # matters more for the mock embedder (embedding.py) than a real model,
    # but keep the floor regardless so a bad match never turns into a candidate.
    _SEMANTIC_MIN_SIM = 0.15

    def match_fault(self, query: str, top_k: int = 3) -> dict:
        matched = self.normalize_query(query)
        matched_entities = [e for e in matched if e in self.entity_inverted]

        # -- leg 1: keyword/entity path (entity_inverted.json) --
        keyword_scores: dict[str, float] = {}
        overlap: dict[str, list[str]] = {}
        for entity in matched_entities:
            for fc_id in self.entity_inverted[entity]:
                overlap.setdefault(fc_id, [])
                if entity not in overlap[fc_id]:
                    overlap[fc_id].append(entity)
        for fc_id, ents in overlap.items():
            total = len(self.fc[fc_id]["fm"].get("症状实体", [])) or 1
            keyword_scores[fc_id] = len(ents) / total

        # -- leg 2: semantic path (embedding cosine similarity) --
        query_vec = embed(query)
        semantic_scores: dict[str, float] = {}
        for fc_id, vec in self._fc_vectors.items():
            sim = cosine(query_vec, vec)
            if sim >= self._SEMANTIC_MIN_SIM:
                semantic_scores[fc_id] = sim

        fc_ids = set(keyword_scores) | set(semantic_scores)
        if not fc_ids:
            return self._fallback(query, matched)

        combined: dict[str, float] = {
            fc_id: (
                self._KEYWORD_WEIGHT * keyword_scores.get(fc_id, 0.0)
                + self._SEMANTIC_WEIGHT * semantic_scores.get(fc_id, 0.0)
            )
            for fc_id in fc_ids
        }

        ranked = sorted(fc_ids, key=lambda fid: (-combined[fid], fid))[:top_k]
        candidates = []
        for fid in ranked:
            matched_via = []
            if fid in keyword_scores:
                matched_via.append("keyword")
            if fid in semantic_scores:
                matched_via.append("semantic")
            candidates.append(
                {
                    "fault_id": fid,
                    "title": self.fc[fid]["fm"]["title"],
                    "matched_entities": overlap.get(fid, []),
                    "score": round(combined[fid], 3),
                    "matched_via": matched_via,
                }
            )

        discriminators = []
        if len(candidates) > 1:
            discriminators = self._discriminators(ranked)

        result = {"candidates": candidates}
        if discriminators:
            result["discriminators"] = discriminators
        elif len(candidates) > 1:
            # spec §8.1: "候选多于1个时必须返回 discriminators"; if the two
            # top procedures never check the same command we cannot build a
            # single distinguishing check, so fall back honestly instead of
            # fabricating one.
            result["discriminators"] = []
            result["_note"] = "候选procedure无共享判据命令，无法生成单一区分命令；建议回退兜底模式或都展开确认。"
        return result

    def _discriminators(self, ranked_ids: list[str]) -> list[dict]:
        out = []
        for i in range(len(ranked_ids)):
            for j in range(i + 1, len(ranked_ids)):
                a, b = ranked_ids[i], ranked_ids[j]
                d = self._discriminator_pair(a, b)
                if d:
                    out.append(d)
        return out

    def _discriminator_pair(self, a: str, b: str) -> dict | None:
        by_cmd_a: dict[str, list[dict]] = {}
        for s in self.fc[a]["fm"].get("判据分流", []):
            if s.get("命令"):
                by_cmd_a.setdefault(s["命令"], []).append(s)
        by_cmd_b: dict[str, list[dict]] = {}
        for s in self.fc[b]["fm"].get("判据分流", []):
            if s.get("命令"):
                by_cmd_b.setdefault(s["命令"], []).append(s)

        for cmd_id, steps_a in by_cmd_a.items():
            steps_b = by_cmd_b.get(cmd_id)
            if not steps_b:
                continue
            for sa in steps_a:
                judge_a = sa.get("判据", "")
                field_a = self._extract_field(judge_a)
                if not field_a:
                    continue
                if any(sb.get("判据", "") == judge_a for sb in steps_b):
                    continue
                return {
                    "between": [a, b],
                    "check_command": self.cmd[cmd_id]["fm"]["命令"],
                    "check_field": field_a,
                    "if_present": a,
                    "if_absent": b,
                }
        return None

    @staticmethod
    def _extract_field(judge_text: str) -> str | None:
        m = FIELD_RE.search(judge_text)
        return m.group(1) if m else None

    def _fallback(self, query: str, matched: list[str]) -> dict:
        """两条召回路都没有候选：如实报告识别到的实体，转人工/转其他排障入口。

        Previously also expanded a Command-node neighborhood here (edges in
        both directions) for whichever matched entity resolved to a CMD-id.
        That branch assumed a caller might type a raw command name as the
        query — a reasonable guess for a human poking at the KB directly,
        but this server's actual caller only ever submits ticket symptom
        text (现象), which essentially never normalizes to a CMD-id via
        alias.json. Removed rather than kept as unreachable code.
        """
        return {
            "candidates": [],
            "discriminators": [],
            "fallback": {
                "matched_entities": matched,
                "note": "无法从实体倒排索引与语义相似度中命中任何故障案例；建议人工浏览 wiki/faultcase/ 或改写查询。",
            },
        }

    # -- 8.2 get_procedure ---------------------------------------------------

    def get_procedure(self, fault_id: str, include_fulltext: bool = True) -> dict:
        if fault_id not in self.fc:
            return {"error": f"unknown fault_id: {fault_id}"}
        rec = self.fc[fault_id]
        fm, body = rec["fm"], rec["body"]

        chain = []
        for step in fm.get("判据分流", []):
            entry = dict(step)
            otherwise = step.get("否则")
            if isinstance(otherwise, str) and otherwise.startswith("ACT-"):
                act = self.act.get(otherwise)
                if act:
                    afm = act["fm"]
                    requires = sorted(afm.get("requires", []), key=lambda r: r.get("order", 0))
                    entry["否则_expanded"] = {
                        "action_id": otherwise,
                        "命令序列": afm.get("命令序列", []),
                        "requires": requires,
                        "source": afm.get("source"),
                        "正文": act["body"].strip(),
                    }
            chain.append(entry)

        result = {
            "fault_id": fault_id,
            "title": fm["title"],
            "症状实体": fm.get("症状实体", []),
            "判据分流": chain,
            "source": fm.get("source"),
        }
        if include_fulltext:
            result["正文"] = body.strip()
        return result

    # -- 8.3 query_entity ---------------------------------------------------

    def _entity_kind(self, entity_id: str) -> str | None:
        if entity_id in self.fc:
            return "FaultCase"
        if entity_id in self.act:
            return "Action"
        if entity_id in self.cmd:
            return "Command"
        if entity_id in self.entity_inverted:
            return "SymptomEntity"
        return None

    def _summarize(self, entity_id: str) -> dict:
        kind = self._entity_kind(entity_id)
        if kind == "FaultCase":
            return {"id": entity_id, "type": kind, "title": self.fc[entity_id]["fm"]["title"]}
        if kind == "Action":
            cmds = self.act[entity_id]["fm"].get("命令序列", [])
            return {"id": entity_id, "type": kind, "命令序列": cmds}
        if kind == "Command":
            return {"id": entity_id, "type": kind, "命令": self.cmd[entity_id]["fm"]["命令"]}
        if kind == "SymptomEntity":
            return {"id": entity_id, "type": kind, "faultcases": self.entity_inverted[entity_id]}
        return {"id": entity_id, "type": None}

    def query_entity(self, entity_id: str, direction: str = "both", edge_type: str | None = None) -> dict:
        kind = self._entity_kind(entity_id)
        if kind is None:
            return {"error": f"unknown entity_id: {entity_id}"}

        out_edges = self.edges.get(entity_id, []) if direction in ("out", "both") else []
        in_edges = self._in_edges.get(entity_id, []) if direction in ("in", "both") else []
        if edge_type:
            wanted = EDGE_TYPE_ALIASES.get(edge_type, {edge_type})
            out_edges = [e for e in out_edges if e["type"] in wanted]
            in_edges = [e for e in in_edges if e["type"] in wanted]

        def enrich(edges: list[dict], self_field: str) -> list[dict]:
            enriched = []
            for e in edges:
                other = e[self_field]
                enriched.append({**e, "neighbor": self._summarize(other)})
            return enriched

        return {
            "entity": self._summarize(entity_id),
            "out": enrich(out_edges, "to"),
            "in": enrich(in_edges, "from"),
        }
