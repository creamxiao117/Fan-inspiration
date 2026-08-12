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
- `scripts/gen_synthesis.py` 与 `scripts/refine_pending.py`：`VAULT_DIR`

⚠️ `import_new.py` 的 `MOC_KEYWORDS` 的 **key 必须和 vault 内 MOC 文件名严格一致**，否则分类链接断链。

## 全流程（Workflow）

### 阶段 0 · 捕获（用户侧，无脚本）

iPhone 语音 → 快捷指令 → iCloud 文件夹。一条语音 ≈ 一份 `.txt`（iOS 会复制约 5 份副本，脚本自动去重）。

### 阶段 1 · 导入 → 原子卡（`scripts/import_new.py`）

```bash
python scripts/import_new.py --dry   # 先预览将要导入的新灵感（分类/关联命中），不写文件
python scripts/import_new.py         # 正式导入，生成原子卡
python scripts/import_new.py --init  # 强制重建基线（不生成卡）
```

逻辑：
1. 扫描 iCloud `.txt` → **归一化哈希游标去重**（忽略 iOS 多副本）→ 过滤纯空文档
2. 关键词分类到 5 张 MOC
3. 生成 `灵感-时间戳-N.md` 原子卡：含「原始语音」「修正」「延伸」「关联 [[链接]]」
4. 自动关联 vault 已有具体卡片 + 反向注册到对应 MOC 列表
5. 新卡默认标 `待校` 标签

首次运行自动建立基线（把当前所有文本标记为已处理，**不重复生成已有卡**）；后续只处理新增。

### 阶段 2 · 语义纠错（`scripts/refine_pending.py` + AI 同轮修正）

```bash
python scripts/refine_pending.py --list      # 列出待校卡及其原始语音
```

AI 读新卡 → 结合语境修正语音错别字（如 像睡→像水、行式→形势、若者→弱者）→ 改写「修正」段 → 补延伸与关联 → 标记已校：

```bash
python scripts/refine_pending.py --done-all  # 批量翻转 待校→已校
```

⚠️ **坑**：勿用 `--done "中文名"`。中文文件名经 Git Bash 传参到 Python 会编码错乱，导致按名找不到文件。用 `--done-all` 整批翻转最稳。

### 阶段 3 · 连接（自动 + 人工）

- 导入时**已自动**：预置 `[[MOC-xxx]]`、关联 vault 已有具体卡、反向注册 MOC 列表
- 人工（可选）：在 Obsidian 里补 `[[双向链接]]`，让卡片长成网络（Graph 视图可见）

### 阶段 4 · 输出（综合笔记，`scripts/gen_synthesis.py`）

```bash
python scripts/gen_synthesis.py --moc "MOC-自我认知与心智成长"   # 以 MOC 为种子
python scripts/gen_synthesis.py --seed "像水一样"                 # 以单卡为种子
python scripts/gen_synthesis.py --topic "修行"                   # 以关键词为种子
python scripts/gen_synthesis.py --register "综合笔记-xxx"        # 反向注册到首页（幂等）
```

逻辑：沿 `[[双向链接]]` 做图 BFS 收集邻域卡片 → 按链接距离生成大纲 → 打包素材文件 →
**AI 扩写成连贯文章（脚本不调任何 API）** → 文内 `[[回链原卡]]`。这是 Zettelkasten 的「表达」环节，闭环收口。

## 红线 / 已知坑

- 中文文件名经 shell（Git Bash）传参会编码错乱 → `refine_pending` 用 `--done-all` 而非 `--done 中文名`
- 中文标点在 ruff 下会触发 RUF001/002/003 误报 → 迁移时带上 `pyproject.toml`（已关闭这三条）
- `MOC_KEYWORDS` 的 key 必须与 vault 内 MOC 文件名**严格一致**
- 静默吞错（bare/blank except）已改为显式 `OSError` 告警

## 文件清单

| 文件 | 作用 |
|---|---|
| `scripts/import_new.py` | 增量导入：去重 / 分类 / 原子卡 / 关联已有卡 / MOC 反向注册 |
| `scripts/gen_synthesis.py` | 综合笔记生成器：邻域收集 + 大纲 + 首页幂等注册 |
| `scripts/refine_pending.py` | 待校卡发现（`--list`）与标记（`--done-all`） |

## 验证状态

- ruff（项目 `pyproject.toml` 红线配置）：三脚本 `All checks passed!`
- mypy 务实档：`Success`
- 真实闭环跑通：导入 → 语义纠错 → 已校 → 连网 → 成文 → 首页可发现
