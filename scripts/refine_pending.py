"""
待校卡片发现与标记工具（语音语义纠错工作流）
==========================================
import_new.py 生成的卡片默认带 `待校` 标签（语音错别字靠语义级校对）。
本工具负责：
  --list      列出所有待校卡片及其原始语音，供 AI 语义校对
  --done-all  校对完成后批量翻转标签（待校 -> 已校）

真实语义纠错由 AI 在同一轮「导入新灵感」中完成：读新卡 → 修正错别字
→ 改写「修正」段 → 跑 --done-all 翻转标签。脚本只做机械列举/标记。

注意：勿用 --done "中文名"，中文文件名经 Git Bash 传参到 Python 会编码错乱
导致按名找不到文件。直接 --done-all 批量翻转更稳。

用法：
    python refine_pending.py --list
    python refine_pending.py --done-all
"""

import argparse
import os
import re

# ---------- 路径配置（迁移到其他机器请修改此处）----------
VAULT_DIR = r"D:/AIwork/20260811-Fan-LingGan/灵感知识库"
SKIP = {"AGENTS.md", "CHARTER.md", "WORK.md", "RUNLOG.md",
        "00-首页索引.md", "收件箱.md", "使用指南.md"}


def card_files():
    for fn in os.listdir(VAULT_DIR):
        if not fn.lower().endswith(".md"):
            continue
        if fn in SKIP or fn.startswith("MOC-"):
            continue
        yield fn


def get_raw_voice(content):
    m = re.search(r"##\s*原始语音\s*\n>\s*(.*?)(?=\n##|\Z)", content, re.S)
    return m.group(1).strip() if m else ""


def cmd_list():
    found = []
    for fn in card_files():
        p = os.path.join(VAULT_DIR, fn)
        with open(p, encoding="utf-8", errors="replace") as f:
            c = f.read()
        if "待校" in c:
            found.append((fn[:-3], get_raw_voice(c)))
    if not found:
        print("[无待校] vault 内没有待校对的卡片。")
        return
    print(f"[待校卡片 {len(found)} 张]")
    for name, voice in found:
        print(f"\n● {name}")
        print(f"  原始语音：{voice[:160]}")


def cmd_done(all_=False):
    targets = []
    if all_:
        for fn in card_files():
            p = os.path.join(VAULT_DIR, fn)
            with open(p, encoding="utf-8", errors="replace") as f:
                c = f.read()
            if "待校" in c:
                targets.append(fn)
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
        # 仍保留单卡入口，但推荐用 --done-all 规避中文名编码问题
        cmd_done(name=a.done)
    else:
        cmd_list()
