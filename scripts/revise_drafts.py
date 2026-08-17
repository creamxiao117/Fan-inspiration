"""
revise_drafts.py — 一次性迁移：6 张误识标题卡校订（R6，勿重跑）
==================================================
内容早已校订（修正节完整），仅标题/文件名仍是语音误识原文。
本脚本：按映射重命名文件 → 同步 frontmatter title → 更新全库 [[旧标题]] 引用 → aliases 保留旧标题兼容。

新标题取自各卡「修正」节的核心语义。
"""

import os
import re

VAULT_DIR = r"D:/AIwork/20260811-Fan-LingGan/灵感知识库"

REVISE = {
    "把把人生定义为体验的旅程去享受这.md": "把人生定义为体验的旅程去享受过程.md",
    "Ive want to lean.md": "以教代学：学会某样东西就教出去.md",
    "学习如何使用get work t.md": "git worktree 与 AI agent 协作.md",
    "记录一下生活中哪些事情会激发我的.md": "记录激发情绪的事，练习情绪觉察.md",
    "拎得清判断一件事情或者是一份一项.md": "拎得清：事情与我人生价值的匹配.md",
    "需要反思和父母之间的关系为什么父.md": "反思与父母的关系，打破代际模式.md",
}


def do_revise() -> None:
    """重命名 + 同步 frontmatter title。"""
    for old, new in REVISE.items():
        p = os.path.join(VAULT_DIR, old)
        if not os.path.exists(p):
            print(f"[缺失] {old} 不存在，跳过")
            continue
        with open(p, encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r"^title: .*$", f"title: {new[:-3]}", content, count=1, flags=re.MULTILINE)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        os.rename(p, os.path.join(VAULT_DIR, new))
        print(f"[改名] {old} -> {new}")


def update_links() -> None:
    """更新全库 [[旧标题]] wikilink 引用（MOC 列表等）。"""
    for fn in sorted(os.listdir(VAULT_DIR)):
        if not fn.lower().endswith(".md"):
            continue
        p = os.path.join(VAULT_DIR, fn)
        with open(p, encoding="utf-8") as f:
            content = f.read()
        changed = False
        for old, new in REVISE.items():
            old_name, new_name = old[:-3], new[:-3]
            if old_name in content:
                content = content.replace(f"[[{old_name}|", f"[[{new_name}|")
                content = content.replace(f"[[{old_name}]]", f"[[{new_name}]]")
                changed = True
        if changed:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[链接更新] {fn}")


def main() -> int:
    existing = set(os.listdir(VAULT_DIR))
    for old, new in REVISE.items():
        if old not in existing:
            print(f"[缺失] {old} 不存在，跳过")
        if new in existing:
            print(f"[冲突] {new} 已存在，中止")
            return 1

    do_revise()
    update_links()
    print("\n[完成] 6 张卡标题校订完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
