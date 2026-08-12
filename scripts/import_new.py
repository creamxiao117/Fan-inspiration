"""
灵感增量导入脚本 (路径 A)
==================
扫描 iPhone 语音 -> 快捷指令 -> iCloud 文件夹里的 .txt 碎片，
去重 / 过滤空文档 / 自动分类到 5 张 MOC / 生成原子卡并预置双向链接。
增强：生成新卡时自动关联 vault 已有具体卡片，并反向注册到对应 MOC 列表。

游标机制：用「归一化文本哈希集合」作为已处理基线。
- 首次运行（state 为空）：建立基线，把当前所有文本标记为已处理，不重复生成卡。
- 后续运行：只处理哈希不在基线中的新文本（自动忽略 iOS 复制的多份副本）。

用法：
    python import_new.py            # 导入新增（非首次会成卡）
    python import_new.py --init     # 强制重建基线（不生成卡）
    python import_new.py --dry      # 只打印将要处理的新灵感，不写文件
"""

import json
import os
import re
from datetime import datetime

# ---------- 路径配置（迁移到其他机器请修改此处两个常量）----------
# iPhone 语音碎片源：iOS「快捷指令/我的工作流程」同步到 iCloud 的文件夹
ICLOUD_DIR = r"F:/Fan-SJSS/iCloud/iCloudDrive/iCloud~is~workflow~my~workflows"
# Obsidian vault 根目录（原子卡与 MOC 落在此）
VAULT_DIR = r"D:/AIwork/20260811-Fan-LingGan/灵感知识库"
STATE_FILE = os.path.join(VAULT_DIR, ".import_state.json")

# ---------- 5 张 MOC 分类关键词 ----------
# key 必须与 vault 内实际 MOC 文件名完全一致，否则分类链接会断链
MOC_KEYWORDS = {
    "MOC-自我认知与心智成长": [
        "自我", "认知", "心智", "成长", "修行", "平凡", "内求", "平静",
        "弱者", "强者", "像水", "心态", "情绪", "觉察",
    ],
    "MOC-觉察冥想情绪": [
        "冥想", "禅", "正念", "打坐", "呼吸", "佛", "无常", "观息", "静坐", "觉知",
    ],
    "MOC-哲学知识整合": [
        "叔本华", "吸引力", "佛家", "哲学", "虚无", "欲望", "因果", "业", "能量", "频率",
    ],
    "MOC-职业工作方法商业": [
        "商业", "行业", "朝阳", "需求", "变现", "赚钱", "职业", "AI", "创业",
        "产品", "市场", "副业", "客户",
    ],
    "MOC-兴趣体验表达": [
        "播客", "表达", "创作", "写作", "视频", "输出", "兴趣", "分享", "内容", "记录", "声音",
    ],
}
DEFAULT_MOC = "MOC-自我认知与心智成长"

# ---------- vault 内非卡片文件（不参与关联匹配）----------
SKIP_FILES = {"00-首页索引.md", "收件箱.md", "使用指南.md",
              "AGENTS.md", "CHARTER.md", "WORK.md", "RUNLOG.md"}

# ---------- 可选：常见语音误识自动替换（累积式，精确匹配才替换）----------
COMMON_FIXES = {
    # "误识词": "正确词",
    # 例："像睡一样": "像水一样",
}

DATE_PREFIX = re.compile(r"^\s*(\d{4}年\d{1,2}月\d{1,2}日[\s_]*\d{1,2}[:_]\d{1,2})\s*")


def normalize(text: str) -> str:
    """去除所有空白后用于哈希去重；iOS 副本仅换行/空格差异也能归并。"""
    return re.sub(r"\s+", "", text).strip()


def is_empty(text: str) -> bool:
    """过滤空文档：去掉日期前缀后无实词（仅时间戳的视为空）。"""
    body = DATE_PREFIX.sub("", text).strip()
    return len(normalize(body)) == 0


def classify(text: str) -> str:
    """按关键词命中数选 MOC，命中最多者胜；并列或零命中用默认。"""
    best, best_n = DEFAULT_MOC, 0
    for moc, kws in MOC_KEYWORDS.items():
        n = sum(1 for k in kws if k in text)
        if n > best_n:
            best, best_n = moc, n
    return best


def auto_fix(text: str) -> str:
    """仅在 COMMON_FIXES 精确命中时替换；否则保留原文，交由人工校对。"""
    out = text
    for wrong, right in COMMON_FIXES.items():
        out = out.replace(wrong, right)
    return out


def make_title(text: str) -> str:
    """取首句/前若干字做卡片标题。"""
    clean = text.strip()
    clean = DATE_PREFIX.sub("", clean).strip()
    clean = re.sub(r"\s+", " ", clean)
    if not clean:
        return "未命名灵感"
    m = re.split(r"[。，,．.\n]", clean)
    head = m[0] if m else clean
    head = head[:16]
    return head or "未命名灵感"


def collect_existing_cards() -> list:
    """扫描 vault，返回已有原子卡标题（排除 MOC/首页/收件箱/说明/骨架文件）。"""
    cards = []
    for fn in os.listdir(VAULT_DIR):
        if not fn.lower().endswith(".md"):
            continue
        if fn in SKIP_FILES or fn.startswith("MOC-"):
            continue
        cards.append(fn[:-3])
    return cards


def find_related(text: str, cards: list, top: int = 3) -> list:
    """从现有卡片中找出与新文本语义相关的（标题子串命中），返回链接名。"""
    hits = []
    for c in cards:
        core = c.replace("的", "")
        if len(core) >= 3 and (core in text or core[:3] in text):
            hits.append(c)
        if len(hits) >= top:
            break
    return hits


def register_to_moc(moc: str, card_title: str):
    """把新卡链接追加到对应 MOC 列表末尾（去重）。"""
    moc_path = os.path.join(VAULT_DIR, moc + ".md")
    if not os.path.exists(moc_path):
        return
    with open(moc_path, encoding="utf-8") as f:
        content = f.read()
    link = f"- [[{card_title}]]"
    if link in content:
        return
    if content.rstrip().endswith("]"):
        content = content.rstrip() + "\n" + link + "\n"
    else:
        content = content.rstrip() + "\n\n" + link + "\n"
    with open(moc_path, "w", encoding="utf-8") as f:
        f.write(content)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"hashes": [], "last_run": None}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def scan_icloud() -> list:
    """返回所有 .txt（含隐藏的 .com.apple.* 副本）的 (文件名, 原始内容, 归一化key)。"""
    items = []
    for name in os.listdir(ICLOUD_DIR):
        if not name.lower().endswith(".txt"):
            continue
        p = os.path.join(ICLOUD_DIR, name)
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError as e:
            print(f"[警告] 读取 {name} 失败，已跳过：{e}")
            continue
        items.append((name, content, normalize(content)))
    return items


def build_card(title, raw, fixed, moc, created, related):
    rel_lines = "\n".join(f"- [[{r}]]" for r in related)
    moc_line = f"- [[{moc}]]"
    rel_block = (rel_lines + "\n" + moc_line) if rel_lines else moc_line
    return f"""---
created: {created}
tags: [灵感, 待校]
source: iCloud语音
moc: [[{moc}]]
---
# {title}

## 原始语音
> {raw.strip()}

## 修正（自动）
{fixed.strip() if fixed.strip() != raw.strip() else "（自动规则未命中明显误识，保留原文，待人工校对）"}

## 延伸
- 

## 关联
{rel_block}
"""


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="重建基线（不生成卡）")
    ap.add_argument("--dry", action="store_true", help="只预览，不写文件")
    args = ap.parse_args()

    state = load_state()
    known = set(state.get("hashes", []))
    items = scan_icloud()

    # 按归一化 key 聚合（忽略 iOS 多副本）
    groups: dict[str, list] = {}
    for name, content, key in items:
        groups.setdefault(key, []).append((name, content))

    new_groups = {k: v for k, v in groups.items() if k and k not in known and not is_empty(v[0][1])}

    if (args.init or not known) and not args.dry:
        # 基线模式：把当前所有非空 key 写入 state，不生成卡
        for k in groups:
            if k:
                known.add(k)
        state["hashes"] = sorted(known)
        state["last_run"] = datetime.now().isoformat(timespec="seconds")
        save_state(state)
        print(f"[基线] 已建立。当前 iCloud 共 {len(groups)} 条唯一文本（含空文档），全部标记为已处理。")
        print("        后续 iPhone 新增灵感，再运行本脚本即自动成卡。")
        return

    if not new_groups:
        print("[无新增] iCloud 自上次以来没有新的灵感碎片。")
        return

    cards = collect_existing_cards()  # 运行前快照，避免自我关联
    print(f"[发现 {len(new_groups)} 条新灵感]")
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    for i, (key, grp) in enumerate(new_groups.items(), 1):
        raw = grp[0][1]
        fixed = auto_fix(raw)
        moc = classify(raw)
        title = make_title(raw)
        related = find_related(raw, cards)
        fname = f"灵感-{stamp}-{i:02d}.md"
        fpath = os.path.join(VAULT_DIR, fname)
        print(f"  {i}. [{moc}] {title}")
        print(f"     源: {grp[0][0]} (+{len(grp)-1} 副本) -> {fname}")
        print(f"     关联: {related if related else '（仅 MOC）'}")
        if not args.dry:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(build_card(title, raw, fixed, moc, created, related))
            register_to_moc(moc, title)
            known.add(key)

    if not args.dry:
        state["hashes"] = sorted(known)
        state["last_run"] = datetime.now().isoformat(timespec="seconds")
        save_state(state)
        print(f"\n[完成] 已生成 {len(new_groups)} 张原子卡到 vault，基线已更新。")


if __name__ == "__main__":
    main()
