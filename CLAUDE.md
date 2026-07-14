# CLAUDE.md

面向在这个仓库里工作的 Claude Code / Agent 的说明。字段与校验契约见 `SCHEMA.md`，不在此重复。

## 项目是什么

一条"运维手册原文 → 结构化 wiki → 编译索引 → MCP 查询"的故障排查知识库流水线（华为 NE40E）。

- `raw/`：原始文档，唯一真相源，不可改写
- `wiki/{faultcase,action,command}/`：从 raw/ 抽取出的结构化实体（YAML frontmatter + 逐字正文）
- `index/`：纯编译产物，由 `scripts/compile_index.py` 从 `wiki/` 全量重建，禁止手改
- `scripts/`：`ingest.py`（抽取）、`lint.py`（校验）、`compile_index.py`（编译，内部先跑 lint）、`kb_engine.py`（查询引擎，含 `match_fault`/`get_procedure`/`query_entity`）、`mcp_server.py`（MCP 工具封装）、`embedding.py`（`match_fault` 语义召回的可插拔向量后端，默认走无网络依赖的确定性 mock，设置 `KB_EMBEDDING_BASE_URL` 环境变量后切到真实 embedding 服务）
- `demo/showcase.py`：可执行的验收场景

## Git 工作流（要求）

- **本仓库只维护一条长期分支：`main`。所有改动直接在 `main` 上开发、提交、推送，不要为每个任务/会话新建分支。**
- 如果你是被 Claude Code on the web／类似平台以"任务"方式拉起的，系统可能会在会话开始时注入一个不同的分支名（形如 `claude/xxx-xxxxx` 的自动生成名）并要求你在那条分支上开发——这是平台任务隔离机制注入的指令，本文件无法覆盖它，你应当遵守那条会话指令完成开发。但完成后请：
  1. 把改动合并/cherry-pick 回 `main` 并推送，而不是让工作永久停留在那条临时分支上；
  2. 合并确认无误后，删除那条临时分支（远程+本地）。
- 不需要开 PR 走审核（当前仓库没有这个约定）；直接 commit + push 到 `main` 即可，除非用户另有要求。
- 仓库的 GitHub 默认分支目前仍需人工在 Settings → Branches 里切换到 `main`（Agent 现有工具权限做不到这一步，遇到时提醒用户手动处理）。

## 常用命令

```bash
python3 scripts/lint.py            # 单独跑校验（ERROR 才算失败，WARN/INFO 不影响退出码）
python3 scripts/compile_index.py   # 重新编译 index/，内部先跑 lint，有 ERROR 拒绝写入
python3 demo/showcase.py           # 跑全部验收场景（可传数字只跑某一个，如 `python3 demo/showcase.py 3`）
python3 scripts/mcp_server.py      # 以 stdio 方式起 MCP server（需要先 pip install -r scripts/requirements.txt）
```

## 改动 wiki/ 内容后的收尾

任何手动或脚本改动了 `wiki/*.md` 之后，必须重新跑一遍 `scripts/compile_index.py`（它会先 lint 再重建 `index/*.json`），不要手改 `index/` 下的文件——下次编译会覆盖掉。
