---
type: schema
title: schema
tags: [规则, schema]
---

# 知识库规则（Schema）

本文件定义知识库的结构规则。**所有维护工具（import / lint / 综合笔记生成）与 LLM 在生成、修改卡片时必须遵守本规则。**

## 一、卡片类型

| type 值 | 文件名前缀 | 说明 |
|---|---|---|
| `atom` | （无前缀） | 原子卡，一张卡一个想法，知识库主体 |
| `moc` | `MOC-` | 主题地图，按主题索引原子卡 |
| `synthesis` | `综合笔记-` | 跨卡综合的文章（体系产出端） |
| `inbox` | `收件箱` | 新捕获碎片的暂存区 |
| `guide` | `使用指南` | 使用说明 |
| `index` | `00-首页索引` | 首页索引 |
| `schema` | `schema` / `purpose` | 规则与方向文档 |

## 一·五、目录结构（vault 根 = 项目根）

Obsidian 打开的是项目根 `D:\AIwork\20260811-Fan-LingGan\`，全部规则文件在根，知识卡在子目录：

| 位置 | 内容 |
|---|---|
| vault 根（`*.md`） | `schema.md` / `purpose.md` / `使用指南.md` / `00-首页索引.md` / `收件箱.md` / `log.md` |
| `灵感知识库/` | 知识主体：MOC / 原子卡 / 综合笔记（工具读写此目录） |
| `raw/sources/` | 外部文章剪藏（原始 Markdown）——不可变；`type: raw`；命名 `YYYY-MM-DD-标题.md`；由 `clip_article.py` / Web Clipper 写入 |
| `raw/assets/` | 图片等媒体附件——不可变 |
| `wiki/sources/` | 文章提炼卡（加工产物）——`type: sourcenote`，frontmatter 必填 `source: [[raw/sources/原文]]` 回链 |

- raw/ 是**原始材料**，lint 豁免卡片规范检查（仅查死链），不参与孤立卡判定
- 外部知识要长进体系：剪藏进 `raw/sources/` → 读后提炼成 `wiki/sources/` 提炼卡或原子卡 → 连入 MOC
- 项目骨架文档（AGENTS/CHARTER/WORK/RUNLOG/overview）与一次性整理稿不参与 lint 检查

## 二、frontmatter 规范（所有卡片必填）

```yaml
---
type: atom            # 上表取值之一
title: 卡片标题        # 与文件名（不含 .md）一致
tags: [灵感, 关键词]   # 自由标签
date: 2026-08-11      # 原子卡/MOC 必填；其余可选
sources: [来源标识]    # 原子卡必填：原始语音文件名或归一化哈希；可多来源
status: 待校|已校      # 原子卡必填；其余类型可省略
---
```

- `title` 必须与文件名一致（不含扩展名），改名必须同步 frontmatter。
- `sources` 是溯源字段：语音碎片卡填 iCloud 源文件名；综合笔记填其素材卡标题列表。

## 三、命名规则

- 原子卡：直接以标题命名，如 `两套系统.md`；脚本生成时可用 `灵感-YYYYMMDD-HHMM-NN.md` 临时名，人工校订后改为语义标题并同步 `title`。
- MOC：`MOC-主题名.md`，主题名与 `import_new.py` 的 `MOC_KEYWORDS` key 一致。
- 综合笔记：`综合笔记-主题.md`。

## 四、结构规则

- 原子卡建议含 `## 原始语音`、`## 延伸`、`## 关联` 三节；`关联` 节用 `[[wikilink]]` 互链。
- `[[wikilink]]` 指向必须存在：不要链接不存在的卡（lint 会报死链）。
- 新卡默认 `status: 待校`，人工或 LLM 校订后翻为 `已校`。
- 收件箱是唯一"暂存"区，成品卡不放收件箱。

## 五、Lint 检查项（lint_vault.py）

1. 死链：`[[目标]]` 指向的文件不存在。
2. 缺 frontmatter / 缺必填字段（见上表）。
3. `type` 不在上表内。
4. `title` 与文件名不一致。
5. 孤立卡：原子卡无任何入链（除 MOC 对它的索引外）。
