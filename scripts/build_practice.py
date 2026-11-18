"""Generate the practice archive and pages for entries with their own content."""

import json
import os
from datetime import date
from html import escape
from pathlib import Path
from textwrap import indent
from urllib.parse import urlsplit


SITE = Path(__file__).resolve().parents[1]
PRACTICE = SITE / "practice"


def text_field(record, key):
    value = record[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 须为非空文本")
    return value.strip()


def safe_href(value):
    parts = urlsplit(value)
    if parts.scheme not in ("", "http", "https") or any(ord(char) < 32 for char in value):
        raise ValueError(f"链接须为站内相对路径或 HTTP(S) 地址：{value!r}")
    return escape(value)


def read_links(entry, key):
    links = entry.get(key, [])
    if not isinstance(links, list):
        raise ValueError(f"{key} 须为数组")
    return [
        (escape(text_field(link, "label")), safe_href(text_field(link, "href")))
        for link in links
    ]


def read_entry(path):
    try:
        day = date.fromisoformat(path.stem)
        if day.isoformat() != path.stem:
            raise ValueError("文件名须为 YYYY-MM-DD.json")
        entry = json.loads(path.read_text(encoding="utf-8"))
        fields = {
            key: escape(text_field(entry, key))
            for key in ("title", "topic", "kind", "summary")
        }
        direct_link = "href" in entry
        href = safe_href(text_field(entry, "href")) if direct_link else f"./{day.isoformat()}.html"
        raw_sections = entry.get("sections", [])
        if not isinstance(raw_sections, list) or (not direct_link and not raw_sections):
            raise ValueError("独立记录的 sections 须为至少包含一项的数组")
        sections = [
            (escape(text_field(section, "heading")), escape(text_field(section, "text")))
            for section in raw_sections
        ]
        links = read_links(entry, "links")
        challenges = read_links(entry, "challenges")
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"{path.name}：{error}") from error

    return dict(
        fields,
        day=day.isoformat(),
        href=href,
        direct_link=direct_link,
        sections=sections,
        links=links,
        challenges=challenges,
    )


def entry_meta(entry):
    day = entry["day"]
    return (
        f'<time datetime="{day}">{day.replace("-", ".")}</time>'
        f'<span>{entry["topic"]} · {entry["kind"]}</span>'
    )


def challenge_links(entry, padding):
    if not entry["challenges"]:
        return ""
    links = " · ".join(f'<a href="{href}">{label}</a>' for label, href in entry["challenges"])
    return f'{padding}<p class="case-links">挑战题面 · {links}</p>\n'


def archive_item(entry):
    return f"""<li id="practice-{entry['day']}">
  <p class="meta">{entry_meta(entry)}</p>
  <h3><a href="{entry['href']}">{entry['title']}</a></h3>
  <p>{entry['summary']}</p>
{challenge_links(entry, '  ')}</li>"""


def update_items(page, marker, items):
    start = f"<!-- {marker}:start -->"
    end = f"<!-- {marker}:end -->"
    original = page.read_text(encoding="utf-8")
    if original.count(start) != 1 or original.count(end) != 1:
        raise ValueError(f"{page.name} 缺少唯一的 {marker} 起止标记")

    before, remainder = original.split(start, 1)
    _, after = remainder.split(end, 1)
    padding = before.rsplit("\n", 1)[-1]
    return f"{before}{start}\n{indent(items, padding)}\n{padding}{end}{after}"


def render_day(entry):
    sections = []
    for index, (heading, text) in enumerate(entry["sections"], start=1):
        section_id = f"practice-section-{index}"
        paragraphs = "\n".join(f"          <p>{part}</p>" for part in text.split("\n\n") if part)
        sections.append(f"""        <section class="topic-section" aria-labelledby="{section_id}">
          <h2 id="{section_id}">{heading}</h2>
{paragraphs}
        </section>""")

    links = [
        f'<a href="{href}">{label}</a>'
        for label, href in entry["links"]
    ]
    links.append('<a href="./ideas.html">查看出题思路</a>')
    related = " · ".join(links)
    title = entry["title"]
    summary = entry["summary"]
    day = entry["day"]
    body = "\n".join(sections)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{summary}">
  <title>{title} | 每日出题实践</title>
  <link rel="stylesheet" href="../styles.css">
</head>
<body>
  <a class="skip-link" href="#main">跳到正文</a>
  <header class="site-header">
    <div class="wrap header-inner">
      <a class="wordmark" href="../index.html" aria-label="AI4S Bench 笔记首页">AI4S <span>Bench Notes</span></a>
      <nav aria-label="栏目">
        <a href="../bench.html">Bench 指标</a>
        <a href="./index.html" aria-current="location">每日出题实践</a>
        <a href="../papers.html">论文更新</a>
        <a href="../skills.html">Skills 与插件</a>
      </nav>
    </div>
  </header>

  <main class="wrap" id="main" tabindex="-1">
    <div class="intro intro-topic">
      <a class="page-back" href="./index.html#practice-{day}"><span aria-hidden="true">←</span> 返回每日出题实践</a>
      <h1>{title}</h1>
      <p class="meta">{entry_meta(entry)}</p>
      <p>{summary}</p>
{challenge_links(entry, '      ')}    </div>
    <article class="topic-content">
{body}
      <p class="case-links">{related}</p>
    </article>
  </main>
</body>
</html>
"""


def write_page(path, contents):
    if path.exists() and path.read_text(encoding="utf-8") == contents:
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(contents, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    sources = sorted((PRACTICE / "entries").glob("*.json"), reverse=True)
    entries = [read_entry(path) for path in sources]
    daily_pages = [
        (PRACTICE / f"{entry['day']}.html", render_day(entry))
        for entry in entries
        if not entry["direct_link"]
    ]
    empty = "<li>暂无出题记录。</li>"
    archive_items = "\n".join(archive_item(entry) for entry in entries) or empty
    archive = PRACTICE / "index.html"
    archive_contents = update_items(archive, "practice-entries", archive_items)
    for path, contents in daily_pages:
        write_page(path, contents)
    write_page(archive, archive_contents)
    print(f"已生成 {len(daily_pages)} 篇独立记录，栏目页收录 {len(entries)} 条记录。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
