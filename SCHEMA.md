# SCHEMA（机读版）

本文件是 `scripts/lint.py`、`scripts/compile_index.py`、`scripts/ingest.py` 共同遵守的字段与校验契约。人类可读的设计背景见项目根目录设计规格文档；本文件只保留字段定义与校验规则，供程序读取（也供人核对）。

## 0. 通用约定

- 所有 wiki 页面是 YAML frontmatter + Markdown 正文的双层文件。
- 正文（frontmatter 之后的部分）必须是 `source` 指向的 raw 文件中对应内容的逐字搬运（允许去除 Markdown 语法差异，如列表符号统一），不允许改写、缩写、润色、总结。
- 每个「锚点」字段的取值格式固定为 `"L<start>-L<end>"`，指向 `source` 文件的 1-indexed 行号闭区间（与 `Read` 工具的行号一致）。
- id 命名：FaultCase 用 `FC-XXXX`（4位数字，允许跳号）；Action 用 `ACT-<中文或英文短语>`；Command 用 `CMD-<归一化命令，短横线分隔>`。
- frontmatter 字段最小化：只允许本文件列出的字段，禁止追加解释性字段。抽取 pipeline 若认为某取值不确定，写入该字段的同时在同一条目内加 `_uncertain: true`。

## 1. FaultCase（`wiki/faultcase/*.md`）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | `"FaultCase"` | 是 | 固定值 |
| `id` | string `FC-\d{4}` | 是 | 全局唯一 |
| `title` | string | 是 | 与原文标题一致 |
| `症状实体` | string[] | 是 | 归一化的症状/领域实体列表，供倒排索引使用 |
| `别名` | map<string, string[]> | 否 | `症状实体` 中某一项 → 该实体的口语/同义变体列表。用于 query 归一化（alias.json 的来源之一）|
| `涉及命令` | `CMD-*` id[] | 是 | 本案例处理流程中涉及的全部命令实体（含判据检查命令与修复动作内的命令），去重 |
| `判据分流` | 见下表 | 是 | 有序 step 列表，程序确定性遍历 |
| `source` | string（相对路径） | 是 | 指向 `raw/*.md`，`判据分流[].判据锚点` 均以此文件的行号为准 |
| `常见原因` | string[] | 否 | 该类故障的常见原因列表，逐条对应原文列表项，不作模糊匹配/锚点校验 |
| `相关告警` | string[] | 否 | 关联的告警 ID/名称列表 |
| `相关日志` | string[] | 否 | 关联的日志 ID 列表 |
| `补充来源` | string[] | 否 | `常见原因`/`相关告警`/`相关日志` 等字段来源的其余 `raw/*.md` 文件（`source` 之外），仅供人工回链，不参与锚点校验 |

`判据分流[]` 每条：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `step` | int | 是 | 从 1 开始，页内唯一 |
| `检查` | string | 是 | 人类可读的检查项描述（解释性内容，不作为程序输入）|
| `命令` | `CMD-*` id | 否 | 执行本步检查所用的命令；纯收尾步骤（如 step 5 收集信息）可省略 |
| `动作` | string | 否 | 无需命令、直接执行的动作（用于收尾步骤替代 `命令`）|
| `判据` | string | 是（有 `命令`/`动作` 时） | 用于程序侧模糊匹配正文的判据文本 |
| `判据锚点` | anchor | 是 | 指向正文中该判据依据的行区间 |
| `否则` | `ACT-*` id \| `{动作, 备注?}` \| `"goto step N"` | 是 | 分流目标。取值为 `ACT-*` 时生成「触发修复」边；取值为内联对象时不生成边，仅供 Agent 展示；取值为 `goto step N` 时生成同页内「goto」边 |
| `满足` | `"goto step N"` \| `"故障排除"` | 是 | N 必须存在于本页 step 列表，或字面量 `故障排除` 表示终止 |

## 2. Action（`wiki/action/*.md`）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | `"Action"` | 是 | 固定值 |
| `id` | string `ACT-*` | 是 | 全局唯一 |
| `命令序列` | `{视图, 命令}[]` | 是 | 该动作本身要执行的命令，按顺序 |
| `requires` | `{order, 视图, 命令}[]` | 否 | 前置依赖命令，`order` 从 1 开始严格递增 |
| `requires锚点` | anchor | requires 非空时必填 | 指向正文中前置依赖段落的行区间 |
| `被引用于` | `FC-*` id[] | 是（脚本生成） | 由 `compile_index.py` 从全部 FaultCase 的「触发修复」边反向生成；ingest 阶段必须留空数组 `[]` |
| `source` | string | 是 | 指向 `raw/*.md` |

## 3. Command（`wiki/command/*.md`）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | `"Command"` | 是 | 固定值 |
| `id` | string `CMD-*` | 是 | 全局唯一，来自归一化命令 |
| `命令` | string | 是 | 归一化后的命令全称（可含可选参数占位） |
| `类型` | `"display" \| "config"` | 是 | |
| `别名` | string[] | 否 | 归一化前的原始写法变体（去参数占位前/undo 形式/视图前缀等），聚合进 `index/alias.json` |
| `被引用于` | `FC-*` id[] | 是（脚本生成） | 由 `compile_index.py` 从全部 FaultCase 的「涉及命令」边反向生成；ingest 阶段必须留空数组 `[]` |

## 4. 边类型与校验（对应设计规格第6节，逐条落地）

| 边类型 | 方向 | 载体字段 | 生成方式 | lint 级别与规则 |
|---|---|---|---|---|
| `goto` | FC 内 step→step | `判据分流[].满足` / `.否则` 中的 `goto step N` | 抽取 | ERROR：N 必须是本页存在的 step |
| `触发修复` | FC → ACT | `判据分流[].否则` 为 `ACT-*` 字符串 | 抽取 | ERROR：目标 ACT 页必须存在 |
| `uses` | FC → CMD | `判据分流[].命令`、`涉及命令` | 抽取 | ERROR：目标 CMD 页必须存在 |
| `requires` | ACT → CMD/配置 | `requires[]`（按 `order`） | 抽取 | ERROR：`order` 必须从1连续递增；WARN：`requires锚点` 区间内应能模糊匹配到对应命令文本 |
| `被引用于` | ACT/CMD → FC | `被引用于[]` | **仅脚本生成**，ingest 产出必须为空 | ERROR：与正向边（`触发修复`/`uses`）全量对账，任何不一致（多、少、错）均报错 |
| `回链` | 任意页 → raw | `source` + 各锚点字段 | 抽取 | ERROR：锚点必须是合法行区间；`判据`/`检查`/`requires` 命令文本需与锚点区间正文模糊匹配（默认阈值：字符级 token 重合度 ≥ 0.5，或命令字面量作为子串出现）|

lint 输出分三级：
- **ERROR**：上表标记 ERROR 的项，任一命中即阻断构建（`compile_index.py` 拒绝产出 index/）。
- **WARN**：孤儿页面（无任何入边的 ACT/CMD）、被 `判据分流`/`requires` 提及但缺页的实体、疑似重复 Action（`命令序列` 归一化后完全相同的两个 ACT 页）。不阻断构建，产出报告供人工审阅。
- **INFO**：页面/边/命令数量等统计信息。

## 5. 命令归一化规则（`scripts/common.py: normalize_command`）

1. 去除参数占位符（如 `topology-name`、`topology-id` 之类的 `<xxx>`/斜体变量名）。
2. 去除 `undo` 前缀，`undo isis topology multicast` 与 `isis topology multicast` 归一化为同一 CMD。
3. 命令 id 不携带视图前缀（视图信息保留在使用处的 `视图` 字段），如 `isis topology multicast` 在接口视图和其他视图下出现均归一化为同一 CMD。
4. 归一化后若与既有 CMD 冲突（同 id 不同原文写法），原始写法进入该 CMD 页 `别名` 字段；若语义不同却撞 id，ingest 阶段应报 `_uncertain: true` 并停止自动合并，留给人工在 alias 候选区裁决。

## 6. index/ 编译产物

- `entity_inverted.json`：`{ 实体: [FC-id, ...] }`，来源于所有 FaultCase 的 `症状实体`。
- `alias.json`：`{ 别名字符串: 规范实体或CMD-id }`，来源于 FaultCase 的 `别名` 字段与 Command 的 `别名` 字段（含 id 本身与 `命令` 全称）。
- `edges.json`：`{ from_id: [{type, to, ...meta}] }` 全量边表（正向 + 脚本生成的反向），供 `query_entity` 直接邻接查询。
- `embeddings.npy`：可选，本设计中未启用（实体倒排 + 别名表已满足召回需求；语料规模增长后可按第5条设计原则追加，不在本次实现范围）。

以上产物必须可由 `scripts/compile_index.py` 从 `wiki/` 全量重建，任何手改 `index/*.json` 的行为在下次构建时都会被覆盖。
