# Fan-inspiration

把 iPhone 语音转文字产生的灵感碎片，加工成可生长的 Obsidian 知识库（Zettelkasten 卡片盒 + MOC 主题地图）的自动化流水线。

## 全流程（四阶段）

1. **捕获** — iPhone 语音 → 快捷指令 → iCloud 文件夹（iOS 会复制约 5 份副本，脚本自动去重）
2. **导入** — `scripts/import_new.py`：归一化哈希去重 + 空文档过滤 + 5 类 MOC 自动分类 + 生成原子卡（标 `待校`）+ 自动关联 vault 已有卡片 + 反向注册到对应 MOC
3. **语义纠错** — `scripts/refine_pending.py --list` 列出待校卡 → 由 AI 同轮按语境修正语音识别错别字 → `--done-all` 翻转 `待校→已校`（规避中文名经 shell 的编码坑）
4. **连接 + 输出** — 在 Obsidian 补 `[[双向链接]]`；`scripts/gen_synthesis.py` 沿链接图 BFS 收集邻域卡片 → 由 AI 扩写成综合笔记 → `--register` 反向登记到首页索引

## 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能说明：触发条件、配置点、红线坑、调用方式 |
| `scripts/import_new.py` | 增量导入（去重/分类/生成原子卡/自动关联） |
| `scripts/gen_synthesis.py` | 综合笔记生成器（邻域收集 + 大纲 + 反向注册首页） |
| `scripts/refine_pending.py` | 待校卡片列举与标记（语义纠错环节） |

## 迁移要点

- 脚本顶部 `ICLOUD_DIR` / `VAULT_DIR` 两个常量按你的环境修改
- `import_new.py` 的 `MOC_KEYWORDS` 的 key 必须与 vault 内 MOC 文件名**严格一致**，否则分类链接断链
- 首次运行 `import_new.py` 自动建立基线（把当前 iCloud 文本标记为已处理，不重复生成已有卡片），之后只处理新增

## 质量门禁

脚本通过了 `ruff`（0 error）与 `mypy` 务实档（0 error）双闸门。建议在仓库根放 `pyproject.toml`（见本地项目 `D:\AIwork\20260811-Fan-LingGan\pyproject.toml`）以复用红线规则。
