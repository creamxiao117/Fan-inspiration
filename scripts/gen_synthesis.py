"""
综合笔记生成器（半自动）— 收集链接邻域 + 生成大纲，供 AI 扩写成文
==============================================================
只做「收集 + 大纲」，不调任何模型 API；正文由 AI（人工/对话）扩写。

用法：
    python gen_synthesis.py --moc "MOC-自我认知与心智成长"
    python gen_synthesis.py --seed "人生是修行"
    python gen_synthesis.py --topic "冥想"
    python gen_synthesis.py --moc "MOC-哲学知识整合" --depth 3

输出：
    1) 终端打印邻域（按链接距离）与可用 MOC 列表
    2) 写入「综合笔记素材-<主题>.md」（所有邻域卡片原文，供 AI 扩写）
    3) 打印扩写提示
"""

import argparse
import os
import re
from collections import defaultdict, deque

VAULT_DIR = r"D:/AIwork/20260811-Fan-LingGan/灵感知识库"
INDEX_FILE = os.path.join(VAULT_DIR, "00-首页索引.md")
SKIP = {"AGENTS.md", "CHARTER.md", "WORK.md", "RUNLOG.md", "00-首页索引.md",
        "收件箱.md", "使用指南.md", ".import_state.json"}
MOC_PREFIX = "MOC-"
LINK_RE = re.compile(r"\[\[([^\]\|#]+)")


def node_name(fn):
    return fn[:-3] if fn.lower().endswith(".md") else fn


def all_nodes():
    nodes = {}
    for fn in os.listdir(VAULT_DIR):
        if not fn.lower().endswith(".md"):
            continue
        if fn in SKIP:
            continue
        p = os.path.join(VAULT_DIR, fn)
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                c = f.read()
        except OSError as e:
            print(f"[警告] 读取 {fn} 失败，已跳过：{e}")
            continue
        nodes[node_name(fn)] = c
    return nodes


def parse_links(content):
    return [m.group(1).strip() for m in LINK_RE.finditer(content)]


def build_graph(nodes):
    g = defaultdict(set)
    for name, c in nodes.items():
        for link in parse_links(c):
            if link in nodes:
                g[name].add(link)
    return g


def strip_fm(c):
    return re.sub(r"^---\n.*?\n---\n", "", c, flags=re.S).strip()


def extract_card(name, content):
    body = strip_fm(content)
    voice = ""
    m = re.search(r"##\s*原始语音\s*\n(.*?)(?=\n##\s|\Z)", body, re.S)
    if m:
        voice = m.group(1).strip()
    extend = ""
    m2 = re.search(r"##\s*延伸\s*\n(.*?)(?=\n##\s|\Z)", body, re.S)
    if m2:
        extend = m2.group(1).strip()
    return {"name": name, "voice": voice or body, "extend": extend}


def register_to_index(note_name):
    """把综合笔记链接追加到首页「综合笔记」区块（幂等）。"""
    if not os.path.exists(INDEX_FILE):
        print(f"[首页] 未找到 {INDEX_FILE}，跳过注册。")
        return
    with open(INDEX_FILE, encoding="utf-8") as f:
        content = f.read()
    link = f"- [[{note_name}]]"
    if link in content:
        print(f"[首页] {note_name} 已注册，跳过。")
        return
    if "## 综合笔记" not in content:
        content = content.rstrip() + "\n\n## 综合笔记\n"
    lines = content.split("\n")
    out, inserted = [], False
    for ln in lines:
        out.append(ln)
        if ln.strip() == "## 综合笔记" and not inserted:
            out.append(link)
            inserted = True
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"[首页] 已注册 {note_name} 到「综合笔记」区块。")


def resolve_seeds(args, nodes):
    if args.moc:
        return [args.moc] if args.moc in nodes else []
    if args.seed:
        return [args.seed] if args.seed in nodes else []
    if args.topic:
        topic = args.topic
        return [n for n, c in nodes.items() if topic in n or topic in c]
    return []


def collect_neighbors(g, seeds, max_depth):
    """沿双向链接 BFS 收集种子邻域卡片（不含 MOC），返回按距离排序的 [(name, dist)]。"""
    dist = {s: 0 for s in seeds}
    q = deque(seeds)
    material = []
    while q:
        cur = q.popleft()
        d = dist[cur]
        if d >= max_depth:
            continue
        for nxt in g.get(cur, ()):
            if nxt not in dist:
                dist[nxt] = d + 1
                q.append(nxt)
                if not nxt.startswith(MOC_PREFIX):
                    material.append((nxt, d + 1))
    best: dict[str, int] = {}
    for n, d in material:
        if n not in best or d < best[n]:
            best[n] = d
    return sorted(best.items(), key=lambda x: (x[1], x[0]))


def register_backlinks(note_name, material):
    """把综合笔记链接反向补到素材原子卡「关联」区块（幂等）。"""
    n_ok = 0
    for name in material:
        if name.startswith(MOC_PREFIX):
            continue
        p = os.path.join(VAULT_DIR, name + ".md")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            content = f.read()
        link = f"- [[{note_name}]]"
        if link in content:
            continue
        anchor = "## 关联"
        if anchor in content:
            idx = content.index(anchor) + len(anchor)
            nl = content.find("\n", idx)
            insert_at = nl + 1 if nl != -1 else len(content)
            content = content[:insert_at] + link + "\n" + content[insert_at:]
        else:
            content = content.rstrip() + f"\n\n{anchor}\n{link}\n"
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        n_ok += 1
    print(f"[回链] 已给 {n_ok} 张素材卡补 [[{note_name}]] 链接。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moc")
    ap.add_argument("--seed")
    ap.add_argument("--topic")
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--out")
    ap.add_argument("--register", help="把指定综合笔记名注册到首页索引（反向登记产出端）")
    ap.add_argument("--backlink", help="从指定综合笔记（须已存在）正文提取 [[引用]]，"
                                       "反向补链到素材卡「关联」区块（幂等）")
    args = ap.parse_args()

    if args.backlink:
        note = args.backlink
        note_path = os.path.join(VAULT_DIR, note + ".md")
        if not os.path.exists(note_path):
            print(f"[回链] {note}.md 不存在：请先写完文章再回链。")
            return
        with open(note_path, encoding="utf-8") as f:
            note_content = f.read()
        material = [
            t for t in re.findall(r"\[\[([^\[\]]+?)\]\]", note_content)
            if t != note and os.path.exists(os.path.join(VAULT_DIR, t + ".md"))
        ]
        register_backlinks(note, material)
        return

    if args.register:
        register_to_index(args.register)
        return

    nodes = all_nodes()
    g = build_graph(nodes)
    seeds = resolve_seeds(args, nodes)
    if not seeds:
        print("[错误] 未找到种子。检查 --moc/--seed 名称，或 --topic 关键词。")
        print("可用 MOC：", [n for n in nodes if n.startswith(MOC_PREFIX)])
        return

    material = collect_neighbors(g, seeds, args.depth)

    theme = args.moc or args.seed or args.topic or "主题"
    print(f"[种子] {seeds}")
    print(f"[邻域] 共 {len(material)} 张素材卡（depth<={args.depth}）")
    for n, d in material:
        print(f"  (d{d}) {n}")

    out_path = args.out or os.path.join(VAULT_DIR, f"综合笔记素材-{theme}.md")
    lines = [f"# 综合笔记素材：{theme}\n"]
    lines.append(f"种子：{seeds}")
    lines.append(f"邻域卡片（按链接距离）：{len(material)} 张\n")
    lines.append("## 大纲草案")
    for d in sorted(set(dd for _, dd in material)):
        cards = [n for n, dd in material if dd == d]
        lines.append(f"- （距离{d}）" + "、".join(cards))
    lines.append("\n## 素材卡片")
    for n, d in material:
        card = extract_card(n, nodes[n])
        lines.append(f"\n### {n}  （距离{d}）")
        lines.append(f"原始语音：{card['voice']}")
        if card["extend"]:
            lines.append(f"延伸：{card['extend']}")
    text = "\n".join(lines) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\n[素材已写入] {out_path}")

    print(f"\n[扩写提示] 请用以上素材以《{theme}》为题写成连贯文章：")
    print("  - 保留原始灵感，用 [[卡名]] 回链原卡")
    print("  - 结构清晰、口语有深度")
    print(f"  - 输出到 综合笔记-{theme}.md")


if __name__ == "__main__":
    main()
