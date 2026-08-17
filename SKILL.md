---
name: Fan-inspiration
description: 把 iPhone 语音转文字产生的灵感碎片（带错别字、重复多份），流水线式整理成可生长的 Obsidian 知识库（Zettelkasten 卡片盒）。触发：用户要把语音/速记灵感碎片导入、整理、去重、分类、语义纠错、连成体系，或写成综合笔记；关键词含「灵感 / 知识库 / 卡片盒 / Obsidian / Zettelkasten / 双向链接 / 综合笔记」。
---

# Fan Inspiration — 灵感碎片 → 知识体系流水线

## Overview

一套把零散灵感（iPhone 语音转文字产生、带语音错别字、iOS 复制成多份副本）整理成
**Obsidian 卡片盒（Zettelkasten）** 的端到端工作流。核心理念：

> 原子卡片 + 双向链接 + MOC 主题地图 + 综合笔记输出 → 碎片自己长成体系。

零第三方依赖（纯标准库）；AI 只做「语义级纠错」和「综合笔记扩写」两件事，机械活全交给脚本。

## When to use

- 用户积攒了一批语音/速记灵感碎片，要导入知识库
- 要批量去重、分类、修正语音错别字
- 想让碎片互联成网络，或把相连卡片串成一篇完整文章
- 用户提到 Obsidian / Zettelkasten / 双向链接 / 综合笔记 / 知识管理体系

## 前置条件

- Python 3.11+（脚本只用标准库，无需 `pip install`）
- 一个 Obsidian vault（首次可为空，或用本工作流生成的骨架）
- iPhone 语音经「快捷指令」同步到 iCloud 某文件夹（源目录）

## 配置（迁移必改）

每个脚本顶部有路径常量，**迁移到其他机器只改这两处**：

- `scripts/import_new.py`：`ICLOUD_DIR`（语音源目录）、`VAULT_DIR`（vault 根）
- `scripts/gen_synthesis.py` / `scripts/refine_pending.py` / `scripts/lint_vault.py` / `scripts/vault_mcp.py`：`VAULT_DIR`
- `scripts/vault_mcp.py`：也可用环境变量 `VAULT_DIR` 覆盖（优先于文件内常量）

⚠️ `import_new.py` 的 `MOC_KEYWORDS` 的 **key 必须和 vault 内 MOC 文件名严格一致**，否则分类链接断链。
⚠️ vault 根需有 `schema.md`（随技能附带，复制到 vault 根即可）——import/lint 都按它执行。

## 全流程（Workflow）

### 阶段 0 · 捕获（用户侧，无脚本）

iPhone 语音 → 快捷指令 → iCloud 文件夹。一条语音 ≈ 一份 `.txt`（iOS 会复制约 5 份副本，脚本自动去重）。

### 阶段 1 · 导入 → 原子卡（`scripts/import_new.py`，两步 CoT）

```bash
python scripts/import_new.py --dry   # 先预览将要导入的新灵感（分类/关联命中），不写文件
python scripts/import_new.py         # 正式导入，生成原子卡
python scripts/import_new.py --no-llm # 禁用 LLM 阶段（无 API key 时自动回退，也可显式禁用）
python scripts/import_new.py --init  # 强制重建基线（不生成卡）
```

逻辑（两阶段流水线，借鉴 llm_wiki 的 Two-Step CoT Ingest）：
1. **Stage 1（确定性，本地规则）**：扫描 iCloud `.txt` → 归一化哈希游标去重（忽略 iOS 多副本）→ 过滤纯空文档 → 关键词分类候选 MOC → 邻域关联候选
2. **Stage 2（LLM 语义，可选）**：配 `LLM_API_KEY`（OpenAI 兼容，可用 `LLM_BASE_URL`/`LLM_MODEL` 覆盖默认）时启用——读 `schema.md` + 草稿 + 邻域上下文，让 LLM「先分析语义、再生成 JSON」（语义标题/纠错文本/MOC 确认/关联卡/延伸点）；**无 key 自动回退 Stage 1 结果（status=待校）**
3. 生成 `灵感-时间戳-N.md` 原子卡：frontmatter 按 schema.md（`type: atom` / `title` / `tags` / `date` / `sources`[语音+sha1:12] / `status` / `aliases:[语义标题]`），含「原始语音」「修正」「延伸」「关联 [[链接]]」。（文件名是时间戳、链接用语义标题，靠 `aliases` 让 Obsidian 解析，链接不断链）
4. 自动关联 vault 已有具体卡片 + 反向注册到对应 MOC 列表（注册语义标题）
5. 新卡 status：LLM 模式→`已校`，规则回退→`待校`；操作追加 `log.md`

首次运行自动建立基线（把当前所有文本标记为已处理，**不重复生成已有卡**）；后续只处理新增。

### 阶段 2 · 体检（`scripts/lint_vault.py`，每次导入后跑）

```bash
python scripts/lint_vault.py        # 只检查：死链 / 孤立卡 / 缺 frontmatter / type 非法 / title 不一致
python scripts/lint_vault.py --fix  # 按 schema 补全可推断字段，摘要写入 log.md
```

要点：死链判定**认 aliases 解析**（`[[语义标题]]` 命中任意卡 aliases 不算死链）并跳过反引号内模板示例；`--fix` 补 type/title/date/sources（推断 `语音碎片:<mtime>（推断）`）/status（tags 或延伸节推断）。有问题退出码 1，可作 CI 门禁。

### 阶段 3 · 语义纠错（`scripts/refine_pending.py` + AI 同轮修正）

```bash
python scripts/refine_pending.py --list      # 列出待校原子卡及其原始语音
```

判定规则（与 schema.md 对齐）：只看 `type: atom` 卡片；待校 = frontmatter `status: 待校` 或 tags 含「待校」；
**不再全文匹配「待校」两字**（曾把 schema.md 规则说明误报成待校卡）。

AI 读待校卡 → 结合语境修正语音错别字（如 像睡→像水、行式→形势、若者→弱者）→ 改写「修正」段 → 补延伸与关联 → 标记已校：

```bash
python scripts/refine_pending.py --done-all  # 批量翻转 待校→已校
```

⚠️ **坑**：`--done "中文名"` 单卡入口未实现（`--done` 调用签名不匹配会直接报错），统一用 `--done-all` 整批翻转最稳。

⚠️ **历史坑（2026-08-17 已修）**：早期导入的卡内容已校订但标题仍是语音误识（如 `把把人生定义为体验的旅程去享受这`、
`Ive want to lean`）——改标题用 `scripts/revise_drafts.py`（一次性映射表，勿重跑），会同步文件名/frontmatter/全库 wikilink。

### 阶段 4 · 连接（自动 + 人工）

- 导入时**已自动**：预置 `[[MOC-xxx]]`、关联 vault 已有具体卡、反向注册 MOC 列表
- 人工（可选）：在 Obsidian 里补 `[[双向链接]]`，让卡片长成网络（Graph 视图可见）

### 阶段 5 · 输出（综合笔记，`scripts/gen_synthesis.py`）

```bash
python scripts/gen_synthesis.py --moc "MOC-自我认知与心智成长"   # 以 MOC 为种子
python scripts/gen_synthesis.py --seed "像水一样"                 # 以单卡为种子
python scripts/gen_synthesis.py --topic "修行"                   # 以关键词为种子
python scripts/gen_synthesis.py --register "综合笔记-xxx"        # 反向注册到首页（幂等）
python scripts/gen_synthesis.py --backlink "综合笔记-xxx"        # 文章写完后，反向补链到素材卡「关联」区块（幂等）
```
注：`--seed` / `--topic` 可传「标题 / 文件名(basename) / 别名」任意一种，脚本统一按三者解析
（vault 内增量卡文件名是 `灵感-时间戳-N` 而链接用标题，故必须标题感知，否则「找不到种子 / 图不连通」）。
`--backlink` 要求笔记已存在：从文章正文提取 `[[引用]]` 反向补链到素材卡（避免补到不存在的笔记造成死链）。

逻辑：沿 `[[双向链接]]` 做图 BFS 收集邻域卡片 → 按链接距离生成大纲 → 打包素材文件 →
**AI 扩写成连贯文章（脚本不调任何 API）** → 文内 `[[回链原卡]]`。这是 Zettelkasten 的「表达」环节，闭环收口。

### 阶段 6 · AI 直查（MCP server，`scripts/vault_mcp.py`）

```bash
# 注册到 MCP 客户端（如 ~/.workbuddy/mcp.json）：
python scripts/vault_mcp.py   # stdio JSON-RPC，零依赖；VAULT_DIR 环境变量可覆盖 vault
```

5 个工具：`search`（关键词搜卡）/ `read`（按文件名/别名/标题读卡）/ `list`（按 type 过滤列卡）/
`graph`（wikilink 图：节点+入链数+边）/ `lint`（体检，复用 lint_vault 规则）。
WorkBuddy 在「连接器管理 → 自定义连接」Trust 后即可在会话里直接搜知识库。

## 红线 / 已知坑

- 增量卡文件名是 `灵感-时间戳-N`、但链接/MOC 用标题 → 必须标题感知（已做）：`--seed/--topic` 传标题/文件名/别名均可命中；Obsidian 侧靠卡片 `aliases:[标题]` 解析 `[[标题]]`；lint 死链判定同样认 aliases
- `refine_pending` 的 `--done` 单卡入口实际未实现（调用签名不匹配），统一用 `--done-all` 批量翻转（与中文 argv 无关）
- 中文标点在 ruff 下会触发 RUF001/002/003 误报 → 迁移时带上 `pyproject.toml`（已关闭这三条）
- `MOC_KEYWORDS` 的 key 必须与 vault 内 MOC 文件名**严格一致**
- 静默吞错（bare/blank except）已改为显式 `OSError` 告警
- LLM 阶段（两步 CoT）：related 会过滤为 vault 实际存在的卡（防幻觉死链）；LLM 输出 JSON 解析支持 ```json 代码块与前后废话；`llm_config()` 无 key 返回 None 即回退规则
- 迁移新 vault：先复制 `schema.md` 到 vault 根，否则 lint 会把 schema 外的 md 当普通文件检查（log.md 已内置跳过）

## 文件清单

| 文件 | 作用 |
|---|---|
| `schema.md` | 知识库规则（卡片类型表 + frontmatter 规范 + 命名规则），复制到 vault 根 |
| `scripts/import_new.py` | 增量导入（两步 CoT）：去重 / 分类 / LLM 纠错 / 原子卡 / 关联 / MOC 反向注册 |
| `scripts/lint_vault.py` | 知识库体检：死链 / 孤立卡 / frontmatter 规范检查与 `--fix` 补全，写 log.md |
| `scripts/gen_synthesis.py` | 综合笔记生成器：邻域收集 + 大纲 + 首页注册（`--register`）+ 素材卡回链（`--backlink`） |
| `scripts/refine_pending.py` | 待校卡发现（`--list`，按 status/tags 精准判定）与标记（`--done-all`） |
| `scripts/rename_drafts.py` | 一次性迁移：把 `灵感-时间戳-N.md` 草稿卡改名为语义标题（勿重跑） |
| `scripts/revise_drafts.py` | 一次性迁移：误识标题卡校订（映射表改标题+文件名+全库链接，勿重跑） |
| `scripts/vault_mcp.py` | MCP server（stdio JSON-RPC 零依赖）：search / read / list / graph / lint |

## 验证状态

- ruff（项目 `pyproject.toml` 红线配置）：全部受检脚本 `All checks passed!`
- mypy 务实档：`Success`
- 真实闭环跑通：导入（LLM/规则）→ 体检全绿 → 语义纠错 → 已校 → 连网 → 成文 → 首页/素材卡回链 → MCP 直查
- 2026-08-17：R4（schema + lint + 两步 CoT）+ R5（草稿卡改名收尾 + 综合笔记 backlink + MCP server）
