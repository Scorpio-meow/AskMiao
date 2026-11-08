import argparse
import json
import re
import sys
import textwrap
from pathlib import Path
from urllib.parse import urljoin

RELEASE_HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$", re.M)
VERSION_LINE = re.compile(r'^__version__ = "([^"]+)"$', re.M)
ABSOLUTE_TAG = re.compile(r"<(?:link|meta)\b[^>]*\sdata-absolute\b[^>]*>")
URL_ATTRIBUTE = re.compile(r'\s(?:href|content)="([^"]*)"')
RELEASE_SLOT = re.compile(r'(<([a-z]+)\b[^>]*\sdata-release="(version|date)"[^>]*>)(</\2>)')
JSON_LD = re.compile(r'<script type="application/ld\+json" data-stamp>(.*?)</script>', re.S)


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
    html, count = RELEASE_SLOT.subn(lambda m: m.group(1).replace(f' data-release="{m.group(3)}"', "") + values[m.group(3)] + m.group(4), html)
    if not count:
        fail("頁面沒有任何 data-release 標記")
    return html, count


def stamp_structured_data(base, html, version, date):
    match = JSON_LD.search(html)
    if not match:
        fail('頁面沒有 <script type="application/ld+json" data-stamp>')
    data = json.loads(match.group(1))
    for key in ("url", "image"):
        if key not in data:
            fail(f"結構化資料缺少 {key}")
        data[key] = urljoin(base, data[key])
    data["version"] = version
    data["dateModified"] = date
    body = textwrap.indent(json.dumps(data, ensure_ascii=False, indent=2), "  ")
    block = '<script type="application/ld+json">\n' + body + "\n  </script>"
    return html[:match.start()] + block + html[match.end():]


def main():
    parser = argparse.ArgumentParser(description="部署前把版本、發行日期與絕對網址寫進介紹網站")
    parser.add_argument("--page", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--changelog", required=True)
    parser.add_argument("--version-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not args.base_url.startswith("https://"):
        fail(f"base URL 必須是 https：{args.base_url}")
    base = args.base_url.rstrip("/") + "/"

    version, date = latest_release(Path(args.changelog).read_text(encoding="utf-8"))
    declared = VERSION_LINE.search(Path(args.version_file).read_text(encoding="utf-8"))
    if not declared:
        fail(f"{args.version_file} 找不到 __version__")
    if declared.group(1) != version:
        fail(f"版本不一致：CHANGELOG 是 {version}，{args.version_file} 是 {declared.group(1)}")

    page = Path(args.page)
    html = page.read_text(encoding="utf-8")
    html, absolute_count = absolutize(base, html)
    html, release_count = fill_release(html, {"version": version, "date": date})
    html = stamp_structured_data(base, html, version, date)
    page.write_text(html, encoding="utf-8", newline="")

    with open(args.output, "a", encoding="utf-8") as output:
        output.write(f"version={version}\nrelease_date={date}\n")
    print(f"{version}（{date}）：絕對網址 {absolute_count} 處、版本欄位 {release_count} 處、結構化資料 1 處")


if __name__ == "__main__":
    main()