import time
import httpx
import pytest
from app.core.config import settings
from app.rag import tools as tools_module
from app.rag.tools import ResearchToolRegistry, extract_page_text, parse_duckduckgo_results
DUCKDUCKGO_PAGE = """
<div class="result results_links results_links_deep result--ad">
  <h2 class="result__title"><a rel="nofollow" class="result__a" href="https://duckduckgo.com/y.js?ad_domain=ads.example.com&amp;u3=x">廣告</a></h2>
  <a class="result__snippet" href="https://duckduckgo.com/y.js?ad_domain=ads.example.com">廣告內容</a>
</div>
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.example.com%2Frelease%2Dnotes.html&amp;rut=abc">Release Notes &amp; <b>Changes</b></a></h2>
  <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.example.com%2Frelease%2Dnotes.html&amp;rut=abc">docs.example.com</a>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.example.com%2Frelease%2Dnotes.html">The <b>2026</b> release adds GPU support.</a>
</div>
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title"><a class="result__a" rel="nofollow" href="https://github.com/example/repo">example/repo</a></h2>
</div>
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnews.example.com%2Fa&amp;rut=def">新聞標題</a></h2>
  <div class="result__snippet">第三筆的摘要</div>
</div>
"""
def assert_fast(func, *args):
    started = time.monotonic()
    result = func(*args)
    assert time.monotonic() - started < 2.0
    return result
def test_duckduckgo_results_are_parsed_per_result_and_skip_ads():
    results = parse_duckduckgo_results(DUCKDUCKGO_PAGE, 5)
    assert results == [
        {"title": "Release Notes & Changes", "url": "https://docs.example.com/release-notes.html", "snippet": "The 2026 release adds GPU support."},
        {"title": "example/repo", "url": "https://github.com/example/repo", "snippet": ""},
        {"title": "新聞標題", "url": "https://news.example.com/a", "snippet": "第三筆的摘要"},
    ]
def test_duckduckgo_results_stop_at_max_results():
    assert [result["url"] for result in parse_duckduckgo_results(DUCKDUCKGO_PAGE, 1)] == ["https://docs.example.com/release-notes.html"]
def test_duckduckgo_parsing_is_linear():
    assert assert_fast(parse_duckduckgo_results, 'class="result__a"' * 200_000, 5) == []
    assert assert_fast(parse_duckduckgo_results, "<" * 300_000 + 'class="result__a"', 5) == []
@pytest.mark.asyncio
@pytest.mark.parametrize("page, expected_count", [(DUCKDUCKGO_PAGE, 3), ("<html><body>請稍後再試</body></html>", 0)])
async def test_web_search_reports_pages_without_results_as_errors(monkeypatch, page, expected_count):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", None)
    monkeypatch.setattr(
        tools_module.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=page)), **kwargs),
    )
    result = await ResearchToolRegistry().web_search("OpenVINO release", 5)
    assert result["count" if expected_count else "results"] == (expected_count if expected_count else [])
    assert ("error" in result) == (expected_count == 0)
def test_page_text_prefers_main_and_skips_navigation_inside_it():
    page = """
    <html><head><title>發行說明 &amp; 更新</title></head><body>
      <header><nav><a>首頁</a><a>文件</a></nav></header>
      <div class="sidebar"><nav><ul><li>目錄一</li><li>目錄二</li></ul></nav></div>
      <main id="content">
        <header><h1>2026.1 發行說明</h1></header>
        <nav class="toc"><nav><a>本頁目錄</a></nav><a>章節</a></nav>
        <p>新增 GPU 支援。</p>
        <aside>相關連結</aside>
        <div role="navigation">上一頁 下一頁</div>
        <p>修正記憶體問題。</p>
      </main>
      <footer>版權所有</footer>
    </body></html>
    """
    title, text = extract_page_text(page)
    assert title == "發行說明 & 更新"
    assert text == "2026.1 發行說明 新增 GPU 支援。 修正記憶體問題。"
def test_page_text_uses_role_main_or_articles_when_there_is_no_main_element():
    role_main = '<div class="related" role="navigation">上一頁</div><div class="body" role="main"><div><p>正文</p></div></div><div>頁尾</div>'
    articles = "<div>選單</div><article><p>第一篇</p></article><div>廣告</div><article><p>第二篇</p></article><div>頁尾</div>"
    assert extract_page_text(role_main)[1] == "正文"
    assert extract_page_text(articles)[1] == "第一篇 廣告 第二篇"
def test_page_text_without_main_skips_page_chrome():
    page = '<header>網站名稱</header><nav>選單</nav><div role="banner">橫幅</div><p>內文</p><aside>側欄</aside><footer>頁尾</footer>'
    assert extract_page_text(page)[1] == "內文"
def test_page_text_keeps_content_of_unclosed_chrome_elements():
    assert extract_page_text("<nav><p>選單</p><p>內文</p>")[1] == "選單 內文"
def test_page_text_extraction_is_linear():
    assert_fast(extract_page_text, "<nav>" * 100_000)
    assert_fast(extract_page_text, "<nav>" * 100_000 + "</nav>")
    assert_fast(extract_page_text, '<div role="navigation">' * 50_000)
    assert_fast(extract_page_text, "<main>" * 100_000 + "</main>" * 3)
    assert_fast(extract_page_text, "<article>" * 100_000 + "</article>")