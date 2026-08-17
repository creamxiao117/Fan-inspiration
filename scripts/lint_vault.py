"""
lint_vault.py — 知识库体检工具（借鉴 llm_wiki 的 Lint 操作）
==================================================
检查 vault 内所有 .md 卡片，规则见 schema.md：
  1. 死链：[[目标]] 指向的文件不存在
  2. 缺 frontmatter / 缺必填字段
  3. type 不在 schema 类型表内
  4. title 与文件名不一致
  5. 孤立原子卡：没有任何文件链接它（连 MOC 索引都没有）

--fix 模式：按 schema 补全可推断的缺失字段（type/title/date/sources/status），
并保留原 frontmatter 的其余自定义键；操作摘要追加到 log.md。

用法：
    python lint_vault.py            # 只检查，报告问题（有问题退出码 1）
    python lint_vault.py --fix      # 修复可补字段后，再报告剩余问题
"""

import argparse
import os
import re
import sys
from datetime import datetime

VAULT_DIR = r"D:/AIwork/20260811-Fan-LingGan/灵感知识库"
LOG_FILE = os.path.join(VAULT_DIR, "log.md")

# schema.md 类型表：每个类型必填的 frontmatter 键（顺序即序列化顺序）
REQUIRED_FIELDS: dict[str, list[str]] = {
    "atom": ["type", "title", "tags", "date", "sources", "status"],
    "moc": ["type", "title", "tags", "date"],
    "synthesis": ["type", "title"],
    "inbox": ["type", "title"],
    "guide": ["type", "title"],
    "index": ["type", "title"],
    "schema": ["type", "title"],
}
VALID_TYPES = set(REQUIRED_FIELDS)

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
WIKI_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")
EXTRA_FIXED = ["type", "title", "tags", "date", "sources", "status"]


def infer_type(fname: str) -> str:
    """按文件名前缀推断类型（与 schema.md 三、命名规则一致）。"""
    base = os.path.basename(fname)
    if base.startswith("MOC-") or base.startswith("MOC·"):
        return "moc"
    if base.startswith("综合笔记素材-") or base.startswith("综合笔记-"):
        return "synthesis"
    if base.startswith("收件箱"):
        return "inbox"
    if base.startswith("使用指南"):
        return "guide"
    if base.startswith("00-"):
        return "index"
    if base in ("schema.md", "purpose.md"):
        return "schema"
    return "atom"


def parse_frontmatter(content: str) -> dict[str, object]:
    """解析 YAML frontmatter 为 dict；无 frontmatter 返回 {}。零依赖，只支持 key: value。"""
    m = FM_RE.match(content)
    if not m:
        return {}
    fm: dict[str, object] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]
        else:
            fm[key] = val.strip("\"'")
    return fm


def serialize_frontmatter(fm: dict[str, object]) -> str:
    """按固定顺序输出 frontmatter 块；EXTRA_FIXED 之外的键按原顺序跟在后面。"""
    lines = ["---"]
    done: set[str] = set()
    for key in EXTRA_FIXED:
        if key in fm:
            lines.append(f"{key}: {_fmt_value(fm[key])}")
            done.add(key)
    for key in fm:
        if key not in done:
            lines.append(f"{key}: {_fmt_value(fm[key])}")
    lines.append("---")
    return "\n".join(lines)


def _fmt_value(val: object) -> str:
    if isinstance(val, list):
        return "[" + ", ".join(str(x) for x in val) + "]"
    return str(val)


def extract_links(content: str) -> list[str]:
    """返回内容里所有 [[目标]] 的规范化目标名（去别名/章节/.md 后缀）。

    跳过行内代码 `...` 与代码块 ``` 内的 [[...]]（文档模板示例，非真实链接）。
    """
    targets = []
    # 先把代码块与行内代码挖掉，避免把模板示例当链接
    stripped = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    stripped = re.sub(r"`[^`]*`", "", stripped)
    for m in WIKI_RE.findall(stripped):
        target = m.split("|")[0].split("#")[0].strip()
        if target.endswith(".md"):
            target = target[:-3]
        if target:
            targets.append(target)
    return targets


SKIP_FILES = {"log.md", "README.md"}  # 操作日志/目录说明，非卡片
RAW_PREFIX = "raw"  # raw/ 子目录 = 原始材料（豁免卡片规范检查，仅查死链）


def md_files() -> list[str]:
    """递归扫描 vault 下全部 .md，返回相对路径（含 raw/、wiki/ 子目录）。"""
    out = []
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if fn.lower().endswith(".md") and os.path.basename(fn) not in SKIP_FILES:
                rel = os.path.relpath(os.path.join(root, fn), VAULT_DIR)
                out.append(rel.replace("\\", "/"))
    return sorted(out)


def is_raw(rel_path: str) -> bool:
    """是否原始材料文件（raw/ 子目录下）。"""
    return rel_path.split("/")[0] == RAW_PREFIX


def has_extension_section(content: str) -> bool:
    """正文是否已有带内容的「延伸」节（用于推断 status）。"""
    m = re.search(r"##\s*延伸\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if not m:
        return False
    body = m.group(1)
    return any(line.strip().startswith("-") for line in body.splitlines())


def infer_status(content: str) -> str:
    """推断原子卡 status：tags 已标「已校/待校」优先，否则看延伸节是否有内容。"""
    fm = parse_frontmatter(content)
    tags = fm.get("tags")
    if isinstance(tags, list):
        tag_str = ",".join(str(x) for x in tags)
        if "已校" in tag_str:
            return "已校"
        if "待校" in tag_str or "待整理" in tag_str:
            return "待校"
    return "已校" if has_extension_section(content) else "待校"


def append_log(entry: str):
    """追加解析格式操作日志（log.md）。"""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("# 操作日志\n\n知识库维护操作记录，格式：`- 时间 | 操作 | 摘要`。\n\n")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def build_fix_content(fn: str, ftype: str, name: str, content: str, fm: dict) -> tuple[str | None, int]:
    """补全 frontmatter 缺失字段（按 schema），返回 (新内容, 修复字段数)；无需修复返回 (None, 0)。"""
    missing = [k for k in REQUIRED_FIELDS.get(ftype, []) if k not in fm]
    if not missing:
        return None, 0
    st = os.stat(os.path.join(VAULT_DIR, fn))
    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
    if "type" in missing:
        fm["type"] = ftype
    if "title" in missing:
        fm["title"] = name
    if ftype in ("atom", "moc") and "date" in missing:
        fm["date"] = mtime
    if ftype == "atom":
        if "sources" in missing:
            fm["sources"] = [f"语音碎片:{mtime}（推断）"]
        if "status" in missing:
            fm["status"] = infer_status(content)
    new_block = serialize_frontmatter(fm)
    if FM_RE.match(content):
        return re.sub(FM_RE, new_block + "\n", content, count=1), len(missing)
    return new_block + "\n" + content, len(missing)


def verify_file(fn: str, name: str, content: str, inlinks: dict) -> list:
    """复查单文件，返回问题列表。raw/ 原始材料豁免卡片规范检查。"""
    if is_raw(fn):
        return []
    out: list[str] = []
    fm2 = parse_frontmatter(content)
    if not fm2:
        return [f"[缺frontmatter] {fn}"]
    ftype2 = str(fm2.get("type") or infer_type(fn))
    if ftype2 not in VALID_TYPES:
        out.append(f"[非法type] {fn}: type={ftype2!r}")
    missing2 = [k for k in REQUIRED_FIELDS.get(ftype2, []) if k not in fm2]
    if missing2:
        out.append(f"[缺字段] {fn}: 缺 {', '.join(missing2)}")
    if "title" in fm2 and str(fm2["title"]) != name:
        out.append(f"[title不一致] {fn}: frontmatter title={fm2['title']!r}")
    if ftype2 == "atom" and inlinks.get(name, 0) == 0:
        out.append(f"[孤立卡] {fn}: 无任何入链")
    return out


def build_index(files: list, contents: dict) -> tuple[dict, dict]:
    """构建链接解析表（文件名/aliases → 实际文件）与入链统计（供孤立卡判定）。

    链接名 key 同时注册 basename（Obsidian 默认按文件名解析）与相对路径两种形式。
    """
    target_file: dict[str, str] = {}
    for fn in files:
        base = os.path.basename(fn)[:-3]
        target_file[base] = fn
        target_file[fn[:-3]] = fn  # 路径形式 [[raw/sources/xxx]]
        fm0 = parse_frontmatter(contents[fn])
        aliases = fm0.get("aliases")
        if isinstance(aliases, list):
            for a in aliases:
                target_file[str(a)] = fn
        elif aliases:
            target_file[str(aliases)] = fn

    inlinks: dict[str, int] = {}
    for fn, content in contents.items():
        for t in extract_links(content):
            real = target_file.get(t)
            if real is not None and real != fn:
                real_noext = os.path.basename(real)[:-3]
                inlinks[real_noext] = inlinks.get(real_noext, 0) + 1
    return target_file, inlinks


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库体检（schema 见 schema.md）")
    ap.add_argument("--fix", action="store_true", help="补全可推断的缺失 frontmatter 字段")
    args = ap.parse_args()

    files = md_files()
    contents = {}
    for fn in files:
        with open(os.path.join(VAULT_DIR, fn), encoding="utf-8") as f:
            contents[fn] = f.read()

    target_file, inlinks = build_index(files, contents)

    problems: list[str] = []
    fixed_counts: dict[str, int] = {}

    for fn in files:
        name = os.path.basename(fn)[:-3]
        content = contents[fn]
        ftype = infer_type(fn)
        fm = parse_frontmatter(content)

        # --- 死链 ---
        for t in extract_links(content):
            if t != name and t not in target_file:
                problems.append(f"[死链] {fn}: 链接 [[{t}]] 不存在")

        # --- frontmatter 缺失 / 补全（raw 原始材料豁免）---
        if args.fix and not is_raw(fn):
            new_content, n = build_fix_content(fn, ftype, name, content, fm)
            if new_content:
                contents[fn] = new_content
                key = "缺 frontmatter" if not fm else "缺字段"
                fixed_counts[key] = fixed_counts.get(key, 0) + (1 if not fm else n)

        # 复查（fix 后）
        problems.extend(verify_file(fn, name, contents[fn], inlinks))

    # 写回 fix 结果 + 报告
    return flush_and_report(args, fixed_counts, files, problems, contents)


def flush_and_report(args, fixed_counts: dict, files: list, problems: list, contents: dict) -> int:
    if args.fix and fixed_counts:
        for fn, content in contents.items():
            with open(os.path.join(VAULT_DIR, fn), "w", encoding="utf-8") as f:
                f.write(content)
        summary = "，".join(f"{k} {v} 处" for k, v in fixed_counts.items())
        append_log(f"- {datetime.now().strftime('%Y-%m-%d %H:%M')} | lint --fix | {summary}")
        print(f"[修复] {summary}，已写入 log.md")
    if problems:
        for p in problems:
            print(p)
        print(f"\n[汇总] {len(files)} 个文件 | {len(problems)} 个问题")
        return 1
    print(f"[通过] {len(files)} 个文件，无问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
