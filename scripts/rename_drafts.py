"""
rename_drafts.py — 一次性迁移：草稿卡改名（R5，勿重跑）
==================================================
把 8 张 `灵感-YYYYMMDD-HHMM-NN.md` 草稿卡改名为卡内 # 语义标题，
同步 frontmatter title，旧文件名并入 aliases 兼容历史链接；
更新引用旧文件名的链接（综合笔记-知识管理.md）。

改名后 Obsidian 链接直接命中文件名，aliases 兜底 MOC 旧截断标题。
"""

import os
import re

VAULT_DIR = r"D:/AIwork/20260811-Fan-LingGan/灵感知识库"
HEAD_RE = re.compile(r"^# (.+)$", re.MULTILINE)


def do_rename(renames: dict) -> None:
    """执行改名 + 更新 frontmatter（title 同步、旧文件名并入 aliases）。"""
    for old, new in renames.items():
        p = os.path.join(VAULT_DIR, old)
        with open(p, encoding="utf-8") as f:
            content = f.read()
        new_title = new[:-3]
        content = re.sub(r"^title: .*$", f"title: {new_title}", content, count=1, flags=re.MULTILINE)
        aliases_m = re.search(r"^aliases: \[(.*)\]$", content, flags=re.MULTILINE)
        if aliases_m:
            old_items = [x.strip() for x in aliases_m.group(1).split(",") if x.strip()]
            if old[:-3] not in old_items:
                content = re.sub(
                    r"^aliases: \[(.*)\]$",
                    f"aliases: [{', '.join([*old_items, old[:-3]])}]",
                    content, count=1, flags=re.MULTILINE,
                )
        else:
            content = re.sub(
                r"^(status: .*)$",
                f"\\1\naliases: [{old[:-3]}]",
                content, count=1, flags=re.MULTILINE,
            )
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        os.rename(p, os.path.join(VAULT_DIR, new))


def update_links(renames: dict) -> None:
    """更新引用旧文件名的 wikilink（[[旧名|别名]] 与纯 [[旧名]]）。"""
    for fn in os.listdir(VAULT_DIR):
        if not fn.lower().endswith(".md"):
            continue
        p = os.path.join(VAULT_DIR, fn)
        with open(p, encoding="utf-8") as f:
            content = f.read()
        changed = False
        for old, new in renames.items():
            old_name = old[:-3]
            new_name = new[:-3]
            if old_name in content:
                content = content.replace(f"[[{old_name}|", f"[[{new_name}|")
                content = content.replace(f"[[{old_name}]]", f"[[{new_name}]]")
                changed = True
        if changed:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[链接更新] {fn}")


def main() -> int:
    renames = {}
    for fn in sorted(os.listdir(VAULT_DIR)):
        if not re.match(r"^灵感-\d{8}-\d{4}-\d{2}\.md$", fn):
            continue
        with open(os.path.join(VAULT_DIR, fn), encoding="utf-8") as f:
            content = f.read()
        m = HEAD_RE.search(content)
        new_name = m.group(1).strip() if m else fn[:-3]
        new_name = new_name.replace("/", "／").replace("\\", "＼").strip()
        if not new_name or new_name == fn[:-3]:
            print(f"[跳过] {fn}：无可用语义标题")
            continue
        renames[fn] = new_name + ".md"
        print(f"[改名] {fn} -> {new_name}.md")

    existing = set(os.listdir(VAULT_DIR))
    for old, new in renames.items():
        if new in existing and new != old:
            print(f"[冲突] {new} 已存在，中止")
            return 1

    do_rename(renames)
    update_links(renames)
    print(f"\n[完成] 共改名 {len(renames)} 张卡")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
