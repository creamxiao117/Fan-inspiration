"""
灵感增量导入脚本 (路径 A) — 两步 CoT ingest（借鉴 llm_wiki）
==================================================
扫描 iPhone 语音 -> 快捷指令 -> iCloud 文件夹里的 .txt 碎片，两步流水线：

Stage 1（确定性，本地规则）：
  - 归一化哈希去重（自动忽略 iOS 多副本）/ 空文档过滤
  - 关键词分类候选 MOC / 邻域关联候选

Stage 2（LLM 语义，可选，OpenAI 兼容接口）：
  - 读 vault 内 schema.md + 草稿 + 邻域上下文
  - LLM 两步分析（先理解语义，再生成）：纠错标题/正文、确认 MOC、关联卡、延伸点
  - 无 LLM key 时自动回退 Stage 1 结果（生成 status=待校 的草稿卡）

新卡模式（与既有草稿卡一致）：
  - 文件名 `灵感-YYYYMMDD-HHMM-NN.md`（临时名，人工校订后改为语义标题）
  - frontmatter 按 schema.md：type/title/tags/date/sources/status
  - aliases 存语义标题，MOC 反向注册语义标题（Obsidian 链接可解析，lint 不报死链）

用法：
    python import_new.py                     # 导入新增（无 LLM key 时回退规则）
    python import_new.py --no-llm            # 禁用 LLM 阶段
    python import_new.py --init              # 强制重建基线（不生成卡）
    python import_new.py --dry               # 只预览，不写文件

LLM 配置（环境变量，OpenAI 兼容）：
    LLM_BASE_URL  如 https://api.openai.com/v1 （默认 https://api.openai.com/v1）
    LLM_API_KEY   必填才启用 LLM 阶段
    LLM_MODEL     如 gpt-4o-mini（默认 gpt-4o-mini）
"""

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime

# ---------- 路径配置 ----------
ICLOUD_DIR = r"F:/Fan-SJSS/iCloud/iCloudDrive/iCloud~is~workflow~my~workflows"
VAULT_DIR = r"D:/AIwork/20260811-Fan-LingGan/灵感知识库"
STATE_FILE = os.path.join(VAULT_DIR, ".import_state.json")
SCHEMA_FILE = os.path.join(VAULT_DIR, "schema.md")
LOG_FILE = os.path.join(VAULT_DIR, "log.md")

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
SKIP_FILES = {"00-首页索引.md", "收件箱.md", "使用指南.md", "schema.md", "log.md",
              "AGENTS.md", "CHARTER.md", "WORK.md", "RUNLOG.md"}

# ---------- 可选：常见语音误识自动替换（累积式，精确匹配才替换）----------
COMMON_FIXES = {
    # "误识词": "正确词",
    # 例："像睡一样": "像水一样",
}

DATE_PREFIX = re.compile(r"^\s*(\d{4}年\d{1,2}月\d{1,2}日[\s_]*\d{1,2}[:_]\d{1,2})\s*")
JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

LLM_DEFAULTS = {"base": "https://api.openai.com/v1", "model": "gpt-4o-mini"}


def normalize(text: str) -> str:
    """去除所有空白后用于哈希去重；iOS 副本仅换行/空格差异也能归并。"""
    return re.sub(r"\s+", "", text).strip()


def is_empty(text: str) -> bool:
    """过滤空文档：去掉日期前缀后无实词（仅时间戳的视为空）。"""
    body = DATE_PREFIX.sub("", text).strip()
    return len(normalize(body)) == 0


def classify(text: str) -> str:
    """Stage 1 分类：按关键词命中数选 MOC，命中最多者胜；并列或零命中用默认。"""
    best, best_n = DEFAULT_MOC, 0
    for moc, kws in MOC_KEYWORDS.items():
        n = sum(1 for k in kws if k in text)
        if n > best_n:
            best, best_n = moc, n
    return best


def auto_fix(text: str) -> str:
    """仅在 COMMON_FIXES 精确命中时替换；否则保留原文，交由 LLM/人工校对。"""
    out = text
    for wrong, right in COMMON_FIXES.items():
        out = out.replace(wrong, right)
    return out


def make_title(text: str) -> str:
    """取首句/前若干字做卡片标题（Stage 1 兜底标题）。"""
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
    """扫描 vault，返回已有原子卡标题（排除 MOC/首页/收件箱/说明/骨架/raw-wiki 子目录）。"""
    cards = []
    for fn in os.listdir(VAULT_DIR):
        if not fn.lower().endswith(".md"):
            continue
        if fn in SKIP_FILES or fn.startswith("MOC-") or os.path.isdir(os.path.join(VAULT_DIR, fn)):
            continue
        cards.append(fn[:-3])
    return cards


def find_related(text: str, cards: list, top: int = 3) -> list:
    """Stage 1 关联：从现有卡片中找出与新文本语义相关的（标题子串命中）。"""
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


# ---------- Stage 2：LLM 两步 CoT ----------

def llm_config() -> dict | None:
    """返回 {base, key, model}；缺 API key 返回 None（禁用 LLM 阶段）。"""
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key:
        return None
    return {
        "base": os.environ.get("LLM_BASE_URL", LLM_DEFAULTS["base"]).rstrip("/"),
        "key": key,
        "model": os.environ.get("LLM_MODEL", LLM_DEFAULTS["model"]),
    }


def read_schema() -> str:
    if os.path.exists(SCHEMA_FILE):
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            return f.read()
    return "（schema.md 缺失）"


def _chat_complete(cfg: dict, messages: list) -> str:
    """OpenAI 兼容 chat/completions 调用（urllib 零依赖）。"""
    url = f"{cfg['base']}/chat/completions"
    payload = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['key']}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return str(data["choices"][0]["message"]["content"])


def _extract_json(text: str) -> dict:
    """从 LLM 输出提取 JSON：优先 ```json 代码块，否则取首个 {..} 区间。"""
    m = JSON_BLOCK.search(text)
    candidate = m.group(1) if m else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"LLM 输出无 JSON：{text[:200]}")
    return json.loads(candidate[start:end + 1])


def llm_refine(cfg: dict, raw: str, moc: str, related: list, schema: str) -> dict:
    """两步 CoT：让 LLM 先分析再生成，返回结构化卡片数据。"""
    prompt = f"""你是灵感知识库的整理助手。请分两步处理：
第一步（分析）：理解这条语音灵感的真实含义，判断它属于哪个主题、与知识库哪些卡片相关、有什么可延伸的方向。
第二步（生成）：基于分析，输出一张原子卡所需的结构化数据。

知识库规则（schema.md）：
{schema}

输入原始语音（含语音识别误差，请先理解真实语义再纠错）：
{raw}

主题候选（关键词规则命中，可能不准，你可修正）：
{moc}

现有相关卡片（标题子串匹配，可增删）：
{'; '.join(related) if related else '（无）'}

现有全部主题地图（MOC）：
{'; '.join(MOC_KEYWORDS)}

只输出 JSON，不要其他文字，格式：
{{"title": "语义化标题（不超过16字，去掉口语冗余）",
  "fixed": "纠错后的完整文本",
  "moc": "选定的 MOC 文件名（必须在上面的 MOC 列表中）",
  "related": ["现有卡片标题"],
  "extension": ["延伸点1", "延伸点2", "延伸点3"]}}
"""
    content = _chat_complete(cfg, [
        {"role": "system", "content": "你只输出 JSON，不输出其他内容。"},
        {"role": "user", "content": prompt},
    ])
    data = _extract_json(content)
    moc_out = str(data.get("moc") or moc)
    if moc_out not in MOC_KEYWORDS:
        moc_out = moc if moc in MOC_KEYWORDS else DEFAULT_MOC
    return {
        "title": str(data.get("title") or make_title(raw))[:16],
        "fixed": str(data.get("fixed") or raw),
        "moc": moc_out,
        "related": [str(x) for x in data.get("related") or []],
        "extension": [str(x) for x in data.get("extension") or []],
    }


# ---------- 卡片生成 ----------

def source_hash(raw: str) -> str:
    """溯源标识：归一化文本 SHA-1 前 12 位。"""
    return "语音:" + hashlib.sha1(normalize(raw).encode("utf-8")).hexdigest()[:12]


def build_card(title, raw, fixed, moc, created, related, extension, status, src):
    rel_lines = "\n".join(f"- [[{r}]]" for r in related)
    moc_line = f"- [[{moc}]]"
    rel_block = (rel_lines + "\n" + moc_line) if rel_lines else moc_line
    ext_lines = "\n".join(f"- {e}" for e in extension) if extension else "- "
    return f"""---
type: atom
title: {title}
tags: [灵感, {"已校" if status == "已校" else "待校"}]
date: {created[:10]}
sources: [{src}]
status: {status}
aliases: [{title}]
created: {created}
source: iCloud语音
moc: [[{moc}]]
---
# {title}

## 原始语音
> {raw.strip()}

## 修正
{fixed.strip() if fixed.strip() != raw.strip() else "（规则/LLM 未命中明显误识，保留原文，待人工校对）"}

## 延伸
{ext_lines}

## 关联
{rel_block}
"""


def append_log(entry: str):
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("# 操作日志\n\n知识库维护操作记录，格式：`- 时间 | 操作 | 摘要`。\n\n")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def refine_step(cfg: dict, raw: str, moc: str, related: list, schema: str, cards: list) -> tuple:
    """Stage 2 单条处理：LLM 两步 CoT；失败回退规则结果。

    返回 (title, fixed, moc, related, extension, status, llm_used)。
    """
    title, fixed = make_title(raw), auto_fix(raw)
    extension: list = []
    status = "待校"
    llm_used = False
    try:
        refined = llm_refine(cfg, raw, moc, related, schema)
        title, fixed, moc, related, extension = (
            refined["title"], refined["fixed"], refined["moc"],
            refined["related"], refined["extension"],
        )
        # 只保留确实存在的关联卡，避免 LLM 幻觉造成死链
        related = [
            r for r in related
            if r in cards or os.path.exists(os.path.join(VAULT_DIR, r + ".md"))
        ][:3]
        status = "已校"
        llm_used = True
    except (ValueError, KeyError, urllib.error.URLError, OSError) as e:
        print(f"  [警告] LLM 阶段失败，回退规则结果：{e}")
    return title, fixed, moc, related, extension, status, llm_used


def process_new_item(i: int, key: str, grp: list, cards: list, cfg: dict | None,
                     schema: str, created: str, stamp: str, args, known: set) -> str | None:
    """处理一条新灵感：LLM/规则 → 生成卡 + 注册 MOC + 更新基线。返回 log 行（dry 返回 None）。"""
    raw = grp[0][1]
    moc = classify(raw)
    related = find_related(raw, cards)
    if cfg:
        title, fixed, moc, related, extension, status, llm_used = refine_step(cfg, raw, moc, related, schema, cards)
    else:
        title, fixed, extension, status, llm_used = make_title(raw), auto_fix(raw), [], "待校", False

    fname = f"灵感-{stamp}-{i:02d}.md"
    fpath = os.path.join(VAULT_DIR, fname)
    print(f"  {i}. [{moc}] {title}" + (" (LLM)" if llm_used else " (规则)"))
    print(f"     源: {grp[0][0]} (+{len(grp)-1} 副本) -> {fname}")
    print(f"     关联: {related if related else '（仅 MOC）'}")
    if args.dry:
        return None
    content = build_card(title, raw, fixed, moc, created, related, extension, status, source_hash(raw))
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    register_to_moc(moc, title)
    known.add(key)
    mode = "LLM 已校" if llm_used else "规则待校"
    return f"- {created} | import | 新增 {fname} [{moc}] {title}（{mode}）"


def report_llm_mode(cfg: dict | None, no_llm: bool):
    if cfg:
        print(f"[LLM] 两步 CoT 已启用：{cfg['model']} @ {cfg['base']}")
    elif no_llm:
        print("[LLM] 已通过 --no-llm 禁用，回退规则分类（status=待校）")
    else:
        print("[LLM] 未配置 LLM_API_KEY，回退规则分类（status=待校）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="重建基线（不生成卡）")
    ap.add_argument("--dry", action="store_true", help="只预览，不写文件")
    ap.add_argument("--no-llm", action="store_true", help="禁用 LLM 阶段（强制走规则）")
    args = ap.parse_args()

    cfg = None if args.no_llm else llm_config()
    report_llm_mode(cfg, args.no_llm)

    state = load_state()
    known = set(state.get("hashes", []))
    items = scan_icloud()

    # 按归一化 key 聚合（忽略 iOS 多副本）
    groups: dict[str, list] = {}
    for name, content, key in items:
        groups.setdefault(key, []).append((name, content))

    new_groups = {k: v for k, v in groups.items() if k and k not in known and not is_empty(v[0][1])}

    if (args.init or not known) and not args.dry:
        for k in groups:
            if k:
                known.add(k)
        state["hashes"] = sorted(known)
        state["last_run"] = datetime.now().isoformat(timespec="seconds")
        save_state(state)
        print(f"[基线] 已建立。当前 iCloud 共 {len(groups)} 条唯一文本（含空文档），全部标记为已处理。")
        return

    if not new_groups:
        print("[无新增] iCloud 自上次以来没有新的灵感碎片。")
        return

    cards = collect_existing_cards()  # 运行前快照，避免自我关联
    schema = read_schema() if cfg else ""
    print(f"[发现 {len(new_groups)} 条新灵感]")
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    log_lines = []
    for i, (key, grp) in enumerate(new_groups.items(), 1):
        line = process_new_item(i, key, grp, cards, cfg, schema, created, stamp, args, known)
        if line:
            log_lines.append(line)

    if not args.dry:
        state["hashes"] = sorted(known)
        state["last_run"] = datetime.now().isoformat(timespec="seconds")
        save_state(state)
        for line in log_lines:
            append_log(line)
        print(f"\n[完成] 已生成 {len(new_groups)} 张原子卡到 vault，基线已更新，log.md 已记录。")


if __name__ == "__main__":
    main()
