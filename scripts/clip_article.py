"""
clip_article.py — 网页文章剪藏（零依赖）
==================================================
把网上看到的好文章存进 vault 的 raw/sources/（原始材料区，不可变），
供后续提炼成 wiki/sources/ 卡片或原子卡。

三种输入：
  --url <URL>        抓取网页并转 Markdown（urllib 零依赖，纯静态页可用）
  --html <文件.html>  浏览器「复制 → 粘贴到文件」的 HTML 转 Markdown（动态页用这个）
  --md <文本>        直接粘贴 Markdown（或从 stdin 读取）

输出：raw/sources/YYYY-MM-DD-标题.md，frontmatter 带 source(URL)/date/title。
HTML→MD 用标准库 html.parser，支持 h1-h6/p/a/img/strong/em/ul/ol/li/blockquote/pre/code/br/hr/table。

用法：
  python clip_article.py --url "https://example.com/article"
  python clip_article.py --html "C:/Users/xxx/Downloads/page.html"
  python clip_article.py --md "粘贴的 markdown"     # 或 echo "..." | python clip_article.py
"""

import argparse
import html
import os
import re
import sys
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

VAULT_DIR = r"D:/AIwork/20260811-Fan-LingGan/灵感知识库"
RAW_DIR = os.path.join(VAULT_DIR, "raw", "sources")

HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
SKIP_TAGS = {"script", "style", "head", "noscript", "iframe", "svg", "form"}
INLINE_CODE = {"code", "kbd", "samp"}
INLINE_EM = {"em", "i"}
INLINE_STRONG = {"strong", "b"}


class HtmlToMarkdown(HTMLParser):
    """轻量 HTML → Markdown 转换器（标准库，够用即可）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip_depth = 0
        self.link_href: str | None = None
        self.link_text: list[str] = []
        self.heading: list[str] = []
        self.in_title = False
        self.list_stack: list[str | None] = []
        self.in_pre = False
        self.table_rows: list[list[str]] = []
        self.in_td = False
        self.cell_text: list[str] = []

    def _flush(self, text: str) -> None:
        if self.skip_depth == 0:
            self.out.append(text)

    def handle_starttag(self, tag, attrs) -> None:  # noqa: C901 — HTML 标签分发器，分支多但逻辑线性
        ad = dict(attrs)
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag == "title":
            self.in_title = True
            return
        if tag in HEADING_LEVELS:
            self._flush("\n" + "#" * HEADING_LEVELS[tag] + " ")
        elif tag == "p":
            self._flush("\n\n")
        elif tag == "br":
            self._flush("\n")
        elif tag == "hr":
            self._flush("\n\n---\n\n")
        elif tag == "a":
            self.link_href = ad.get("href")
            self.link_text = []
        elif tag == "img":
            src = ad.get("src", "")
            alt = ad.get("alt", "")
            self._flush(f"![{alt}]({src})")
        elif tag in INLINE_STRONG:
            self._flush("**")
        elif tag in INLINE_EM:
            self._flush("*")
        elif tag in INLINE_CODE and not self.in_pre:
            self._flush("`")
        elif tag == "pre":
            self.in_pre = True
            self._flush("\n```\n")
        elif tag in ("ul", "ol"):
            self.list_stack.append(ad.get("start", "1") if tag == "ol" else None)
            self._flush("\n")
        elif tag == "li":
            depth = len(self.list_stack) - 1
            indent = "  " * depth
            marker = self.list_stack[-1]
            self._flush(f"\n{indent}- " if marker is None else f"\n{indent}{marker}. ")
            if marker is not None and isinstance(marker, str) and marker.isdigit():
                self.list_stack[-1] = str(int(marker) + 1)
        elif tag == "blockquote":
            self._flush("\n> ")
        elif tag == "table":
            self.table_rows = []
            self._flush("\n")
        elif tag == "tr":
            self.table_rows.append([])
        elif tag in ("td", "th"):
            self.in_td = True
            self.cell_text = []
        elif tag == "div" or tag == "span":
            pass  # 结构标签不输出

    def handle_endtag(self, tag) -> None:  # noqa: C901 — HTML 标签分发器，分支多但逻辑线性
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "title":
            self.in_title = False
            return
        if tag in HEADING_LEVELS:
            self._flush("\n")
        elif tag == "p":
            self._flush("\n\n")
        elif tag == "a":
            text = "".join(self.link_text).strip()
            if text:
                self._flush(f"[{text}]({self.link_href})" if self.link_href else text)
            self.link_href = None
        elif tag in INLINE_STRONG:
            self._flush("**")
        elif tag in INLINE_EM:
            self._flush("*")
        elif tag in INLINE_CODE and not self.in_pre:
            self._flush("`")
        elif tag == "pre":
            self.in_pre = False
            self._flush("\n```\n")
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            self._flush("\n")
        elif tag == "blockquote":
            self._flush("\n\n")
        elif tag == "table":
            rows = []
            for r in self.table_rows:
                rows.append("| " + " | ".join(c.strip() for c in r) + " |")
            if rows:
                ncol = len(self.table_rows[0])
                sep = "|" + "---|" * ncol
                self._flush("\n" + "\n".join([rows[0], sep, *rows[1:]]) + "\n")
            self._flush("\n")
        elif tag in ("td", "th"):
            self.in_td = False
            if self.table_rows:
                self.table_rows[-1].append("".join(self.cell_text).strip())

    def handle_data(self, data) -> None:
        if self.skip_depth > 0:
            return
        if self.in_title:
            self.heading.append(data)
            return
        if self.in_pre:
            self.out.append(data)
            return
        if self.in_td:
            self.cell_text.append(data)
            return
        if self.link_href is not None:
            self.link_text.append(data)
            return
        self._flush(data)

    def render(self) -> str:
        text = "".join(self.out)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        return text.strip() + "\n"


def slugify(title: str) -> str:
    """文件名安全化：去非法字符/空白，截断 48 字。"""
    s = re.sub(r'[\\/:*?"<>|\s]+', "-", title).strip("-")
    return s[:48] or "untitled"


def fetch(url: str) -> tuple[str, str]:
    """抓取网页，返回 (html, 标题)。编码从 header/meta 推断，兜底 utf-8。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    charset = resp.headers.get_content_charset() or "utf-8"
    try:
        text = raw.decode(charset)
    except (UnicodeDecodeError, LookupError):
        m = re.search(rb'charset=["\']?([\w-]+)', raw[:2048])
        text = raw.decode(m.group(1).decode() if m else "utf-8", errors="replace")
    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    title = html.unescape(title_m.group(1)).strip() if title_m else url
    return text, title


def to_markdown(html_text: str) -> str:
    p = HtmlToMarkdown()
    p.feed(html_text)
    p.close()
    return p.render()


def save_md(md_text: str, title: str, source: str) -> str:
    os.makedirs(RAW_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fname = f"{today}-{slugify(title)}.md"
    fpath = os.path.join(RAW_DIR, fname)
    n = 2
    while os.path.exists(fpath):
        fpath = os.path.join(RAW_DIR, f"{today}-{slugify(title)}-{n}.md")
        n += 1
    fm = f"---\ntype: raw\ntitle: {title}\ndate: {today}\nsource: {source}\n---\n\n"
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(fm + md_text)
    return fpath


def main() -> int:
    ap = argparse.ArgumentParser(description="网页文章剪藏 → raw/sources/")
    ap.add_argument("--url", help="网页 URL（静态页可抓取）")
    ap.add_argument("--html", help="本地 HTML 文件路径（浏览器复制保存的）")
    ap.add_argument("--md", help="直接粘贴 Markdown 文本")
    args = ap.parse_args()

    if args.md:
        md_text, title, source = args.md.strip(), args.md[:30], "手动粘贴"
    elif args.html:
        with open(args.html, encoding="utf-8", errors="replace") as f:
            html_text = f.read()
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.S | re.I)
        title = html.unescape(title_m.group(1)).strip() if title_m else os.path.basename(args.html)
        md_text, source = to_markdown(html_text), args.html
    elif args.url:
        html_text, title = fetch(args.url)
        md_text, source = to_markdown(html_text), args.url
    else:
        md_text = sys.stdin.read().strip()
        if not md_text:
            print("用法：--url / --html / --md 三选一，或从 stdin 传 Markdown")
            return 1
        title, source = md_text[:30], "stdin"

    if not md_text.strip():
        print("[空] 转换结果为空，未保存。")
        return 1
    fpath = save_md(md_text, title, source)
    print(f"[已保存] {fpath}")
    print(f"[标题] {title}")
    print(f"[来源] {source}")
    print("[提示] 加工：读原文 → 提炼卡放 wiki/sources/（type: sourcenote，回链原文）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
