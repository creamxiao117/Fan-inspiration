"""
待校卡片发现与标记工具（语音语义纠错工作流）
==========================================
import_new.py 生成的原子卡默认带 `status: 待校`（语音错别字靠语义级校对）。
本工具负责：
  --list   列出所有待校原子卡及其原始语音，供 AI 语义校对
  --done   校对完成后翻转状态（待校 -> 已校）

真实语义纠错由 AI 在同一轮「导入新灵感」中完成：读新卡 → 修正错别字
→ 改写「修正」段 → 跑 --done 翻转标签。脚本只做机械列举/标记。

判定规则（与 schema.md / lint_vault.py 对齐）：
  - 只看 type=atom 的原子卡；MOC/首页/指南/schema/log 等非卡片不参与
  - 待校 = frontmatter `status: 待校` 或 tags 含「待校」；不再全文匹配（避免误报）

用法：
    python refine_pending.py --list
    python refine_pending.py --done "两套系统"
"""

import argparse
import os
import re

import lint_vault as lv  # 复用 frontmatter 解析/类型推断（同项目根）

VAULT_DIR = lv.VAULT_DIR


def card_files():
    yield from lv.md_files()


def is_pending(fn, content) -> bool:
    """是否待校原子卡：type=atom 且 status/tags 标注待校。"""
    fm = lv.parse_frontmatter(content)
    ftype = str(fm.get("type") or lv.infer_type(fn))
    if ftype != "atom":
        return False
    if fm.get("status") == "待校":
        return True
    tags = fm.get("tags")
    return isinstance(tags, list) and any("待校" in str(t) for t in tags)


def get_raw_voice(content):
    m = re.search(r"##\s*原始语音\s*\n>\s*(.*?)(?=\n##|\Z)", content, re.S)
    return m.group(1).strip() if m else ""


def cmd_list():
    found = []
    for fn in card_files():
        p = os.path.join(VAULT_DIR, fn)
        with open(p, encoding="utf-8", errors="replace") as f:
            c = f.read()
        if is_pending(fn, c):
            found.append((fn[:-3], get_raw_voice(c)))
    if not found:
        print("[无待校] vault 内没有待校对的原子卡。")
        return
    print(f"[待校卡片 {len(found)} 张]")
    for name, voice in found:
        print(f"\n● {name}")
        print(f"  原始语音：{voice[:160]}")


def cmd_done(name=None, all_=False):
    targets = []
    if all_:
        for fn in card_files():
            p = os.path.join(VAULT_DIR, fn)
            with open(p, encoding="utf-8", errors="replace") as f:
                c = f.read()
            if is_pending(fn, c):
                targets.append(fn)
    elif name:
        target = name if name.endswith(".md") else name + ".md"
        targets = [target]

    if not targets:
        print("[无待校] 没有需要标记的卡片。")
        return
    for t in targets:
        p = os.path.join(VAULT_DIR, t)
        if not os.path.exists(p):
            print(f"[跳过] 未找到：{t}")
            continue
        with open(p, encoding="utf-8") as f:
            c = f.read()
        # 精准翻转标签与状态字段，不触碰正文里的「待校」一词（避免误改原始语音）
        c = re.sub(r"tags:\s*\[([^\]]*?)待校([^\]]*?)\]", r"tags: [\1已校\2]", c)
        c = re.sub(r"status:\s*待校", "status: 已校", c)
        if "tags:" not in c and "待校" in c:
            c = c.replace("待校", "已校")
        with open(p, "w", encoding="utf-8") as f:
            f.write(c)
        print(f"[完成] {t[:-3]} 已标记为 已校。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出待校卡片")
    ap.add_argument("--done", help="标记指定卡片为已校（卡片名，可不含 .md）")
    ap.add_argument("--done-all", action="store_true", help="标记全部待校卡片为已校（避免中文文件名经 shell 编码错乱）")
    a = ap.parse_args()
    if a.done_all:
        cmd_done(all_=True)
    elif a.done:
        cmd_done(name=a.done)
    else:
        cmd_list()
