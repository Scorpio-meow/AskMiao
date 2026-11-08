import argparse
import json
import re
import sys
import textwrap
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "site" / "index.html"
CHANGELOG = ROOT / "CHANGELOG.md"
VERSION_FILE = ROOT / "backend" / "app" / "__init__.py"
RELEASE_HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$", re.M)
VERSION_LINE = re.compile(r'^__version__ = "([^"]+)"$', re.M)
ABSOLUTE_TAG = re.compile(r"<(?:link|meta)\b[^>]*\sdata-absolute\b[^>]*>")
URL_ATTRIBUTE = re.compile(r'\s(?:href|content)="([^"]*)"')
JSON_LD_OPEN = '<script type="application/ld+json" data-stamp>'
SCRIPT_CLOSE = "</script>"


def fail(message):
    sys.exit(f"stamp_site: {message}")


def latest_release(changelog):
    match = RELEASE_HEADING.search(changelog)
    if not match:
        fail("CHANGELOG 找不到「## [x.y.z] - YYYY-MM-DD」格式的版本標題")
    return match.group(1), match.group(2)


def absolutize(base, html):
    def replace(match):
        tag = match.group(0)
        attribute = URL_ATTRIBUTE.search(tag)
        if not attribute:
            fail(f"標記了 data-absolute 卻沒有 href 或 content：{tag}")
        absolute = urljoin(base, attribute.group(1))
        tag = tag[:attribute.start(1)] + absolute + tag[attribute.end(1):]
        return re.sub(r"\sdata-absolute\b", "", tag)

    html, count = ABSOLUTE_TAG.subn(replace, html)
    if not count:
        fail("頁面沒有任何 data-absolute 標記")
    return html, count


def fill_release(html, values):
    count = 0
    for key, value in values.items():
        slot = f'<span data-release="{key}"></span>'
        count += html.count(slot)
        html = html.replace(slot, f"<span>{value}</span>")
    if not count:
        fail('頁面沒有任何 <span data-release="…"></span> 標記')
    return html, count


def stamp_structured_data(base, html, version, date):
    start = html.find(JSON_LD_OPEN)
    end = html.find(SCRIPT_CLOSE, start) if start >= 0 else -1
    if end < 0:
        fail(f"頁面沒有 {JSON_LD_OPEN}")
    data = json.loads(html[start + len(JSON_LD_OPEN):end])
    for key in ("url", "image"):
        if key not in data:
            fail(f"結構化資料缺少 {key}")
        data[key] = urljoin(base, data[key])
    data["version"] = version
    data["dateModified"] = date
    body = textwrap.indent(json.dumps(data, ensure_ascii=False, indent=2), "  ")
    block = '<script type="application/ld+json">\n' + body + "\n  </script>"
    return html[:start] + block + html[end + len(SCRIPT_CLOSE):]


def main():
    parser = argparse.ArgumentParser(description="部署前把版本、發行日期與絕對網址寫進介紹網站，並在 stdout 印出 GitHub Actions 的步驟輸出")
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    if not args.base_url.startswith("https://"):
        fail(f"base URL 必須是 https：{args.base_url}")
    base = args.base_url.rstrip("/") + "/"

    version, date = latest_release(CHANGELOG.read_text(encoding="utf-8"))
    declared = VERSION_LINE.search(VERSION_FILE.read_text(encoding="utf-8"))
    if not declared:
        fail("backend/app/__init__.py 找不到 __version__")
    if declared.group(1) != version:
        fail(f"版本不一致：CHANGELOG 是 {version}，backend/app/__init__.py 是 {declared.group(1)}")

    html = PAGE.read_text(encoding="utf-8")
    html, absolute_count = absolutize(base, html)
    html, release_count = fill_release(html, {"version": version, "date": date})
    html = stamp_structured_data(base, html, version, date)
    PAGE.write_text(html, encoding="utf-8", newline="")

    print(f"version={version}")
    print(f"release_date={date}")
    print(f"{version}（{date}）：絕對網址 {absolute_count} 處、版本欄位 {release_count} 處、結構化資料 1 處", file=sys.stderr)


if __name__ == "__main__":
    main()