"""
vault_mcp.py — 灵感知识库 MCP server（stdio JSON-RPC，零依赖）
==================================================
让 AI 客户端（WorkBuddy / Claude / 任意 MCP 客户端）直接查询 Obsidian vault：
  - search   关键词搜卡片（标题/正文），返回标题 + 摘要
  - read     按文件名/别名/标题读单卡全文
  - list     列卡片，可按 type 过滤（atom/moc/synthesis/...）
  - graph    返回 wikilink 图（节点 + 边，别名已归一）
  - lint     知识库体检（死链/孤立卡/缺字段），复用 lint_vault 规则

协议：MCP stdio transport（newline-delimited JSON-RPC 2.0，2024-11-05）。
零第三方依赖；运行需要 Python 3.11+。

配置：环境变量 VAULT_DIR 可覆盖 vault 路径（默认本项目 vault）。
"""

import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)  # 与 lint_vault.py 同目录（技能 scripts/ 布局）
sys.path.insert(0, os.path.dirname(_HERE))  # lint_vault.py 在上级（项目根布局）
import lint_vault as lv  # noqa: E402 — 需先改 sys.path 才能定位（兼容项目/技能两种布局）

VAULT_DIR = os.environ.get("VAULT_DIR", r"D:/AIwork/20260811-Fan-LingGan")  # vault 根
PROTOCOL_VERSION = "2024-11-05"
SUMMARY_LEN = 220


# ---------- 工具实现 ----------

def _load_files() -> dict:
    """读全部 md 文件内容。"""
    out = {}
    for fn in lv.md_files():
        with open(os.path.join(VAULT_DIR, fn), encoding="utf-8") as f:
            out[fn] = f.read()
    return out


def _summary(text: str) -> str:
    """取正文前若干字符作为摘要（去掉 frontmatter 与空行）。"""
    body = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:SUMMARY_LEN]


def tool_search(args: dict) -> dict:
    query = str(args.get("query", "")).strip()
    limit = max(1, min(int(args.get("limit", 5)), 20))
    if not query:
        return {"error": "query 必填"}
    ql = query.lower()
    hits = []
    for fn, content in _load_files().items():
        fm = lv.parse_frontmatter(content)
        ftype = str(fm.get("type") or lv.infer_type(fn))
        title = str(fm.get("title") or fn[:-3])
        hay = (fn + " " + title + " " + content).lower()
        if ql in hay:
            hits.append({
                "file": fn, "title": title, "type": ftype,
                "summary": _summary(content),
            })
    hits.sort(key=lambda h: (h["title"] != query, len(h["title"])))
    return {"count": len(hits), "results": hits[:limit]}


def tool_read(args: dict) -> dict:
    name = str(args.get("name", "")).strip()
    if not name:
        return {"error": "name 必填"}
    files = _load_files()
    target, _ = lv.build_index(list(files), files)  # 按文件名/aliases/标题解析
    fn = target.get(name)
    if not fn:
        return {"error": f"未找到卡片：{name}"}
    content = files[fn]
    fm = lv.parse_frontmatter(content)
    return {"file": fn, "type": str(fm.get("type") or lv.infer_type(fn)), "content": content}


def tool_list(args: dict) -> dict:
    ftype_filter = str(args.get("type", "")).strip() or None
    items = []
    for fn, content in _load_files().items():
        fm = lv.parse_frontmatter(content)
        ftype = str(fm.get("type") or lv.infer_type(fn))
        if ftype_filter and ftype != ftype_filter:
            continue
        items.append({"file": fn, "title": str(fm.get("title") or fn[:-3]), "type": ftype})
    items.sort(key=lambda x: x["file"])
    return {"count": len(items), "notes": items}


def tool_graph(args: dict) -> dict:
    files = _load_files()
    target, inlinks = lv.build_index(list(files), files)
    nodes = []
    for fn in files:
        fm = lv.parse_frontmatter(files[fn])
        nodes.append({
            "id": fn[:-3],
            "file": fn,
            "type": str(fm.get("type") or lv.infer_type(fn)),
            "inlinks": inlinks.get(fn[:-3], 0),
        })
    edges = []
    seen = set()
    for fn, content in files.items():
        for t in lv.extract_links(content):
            real = target.get(t)
            if real is not None and real != fn:
                key = (fn[:-3], real[:-3]) if fn[:-3] < real[:-3] else (real[:-3], fn[:-3])
                if key not in seen:
                    seen.add(key)
                    edges.append({"source": key[0], "target": key[1]})
    return {"nodes": nodes, "edges": edges}


def tool_lint(args: dict) -> dict:
    files = lv.md_files()
    contents = {}
    for fn in files:
        with open(os.path.join(VAULT_DIR, fn), encoding="utf-8") as f:
            contents[fn] = f.read()
    target, inlinks = lv.build_index(files, contents)
    problems = []
    for fn in files:
        name = fn[:-3]
        content = contents[fn]
        for t in lv.extract_links(content):
            if t != name and t not in target:
                problems.append(f"[死链] {fn}: 链接 [[{t}]] 不存在")
        problems.extend(lv.verify_file(fn, name, content, inlinks))
    return {"files": len(files), "problems": problems, "ok": len(problems) == 0}


TOOLS = [
    {
        "name": "search",
        "description": "在灵感知识库中按关键词搜索卡片（标题/正文），返回标题、类型与摘要",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回条数，默认 5，最大 20"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read",
        "description": "读取单张卡片全文，name 支持文件名 / aliases 语义标题 / 标题",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "卡片名"}},
            "required": ["name"],
        },
    },
    {
        "name": "list",
        "description": "列出知识库卡片，可按类型过滤（atom/moc/synthesis/inbox/guide/index/schema）",
        "inputSchema": {
            "type": "object",
            "properties": {"type": {"type": "string", "description": "卡片类型，缺省全部"}},
        },
    },
    {
        "name": "graph",
        "description": "返回知识库 wikilink 图：节点（含入链数）与边（双向链接已归一）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "lint",
        "description": "知识库体检：死链 / 孤立卡 / 缺 frontmatter 字段，返回问题清单",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ---------- stdio JSON-RPC 服务 ----------

def _respond(msg_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return json.dumps(payload, ensure_ascii=False)


def handle_request(msg: dict) -> str | None:
    method = msg.get("method") or ""
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return _respond(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "vault-mcp", "version": "0.1.0"},
        })
    if method == "notifications/initialized" or method.startswith("notifications/"):
        return None  # 通知无需响应
    if method == "ping":
        return _respond(mid, {})
    if method == "tools/list":
        return _respond(mid, {"tools": TOOLS})
    if method == "tools/call":
        tool = str(params.get("name", ""))
        args = params.get("arguments") or {}
        handler = {
            "search": tool_search,
            "read": tool_read,
            "list": tool_list,
            "graph": tool_graph,
            "lint": tool_lint,
        }.get(tool)
        if handler is None:
            return _respond(mid, None, {"code": -32601, "message": f"未知工具：{tool}"})
        try:
            result = handler(args)
        except Exception as e:  # 显式兜底：工具错误返回给客户端而非崩掉
            return _respond(mid, None, {"code": -32603, "message": str(e)})
        return _respond(mid, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]})
    # 其他未知方法：按 JSON-RPC 规范回 method not found
    return _respond(mid, None, {"code": -32601, "message": f"未知方法：{method}"})


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(msg)
        if resp:
            sys.stdout.write(resp + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
