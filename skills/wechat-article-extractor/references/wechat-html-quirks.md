# WeChat Raw HTML — Quirks and Pitfalls

Captured 2026-06-18 from a real extraction session on `https://mp.weixin.qq.com/s/kJYmszZc9w2UoZBZ5EfDNQ` (the "CodexGuide" article by 苍何). Use this as a reference when the bundled `extract_wechat.py` produces wrong output on a real `mp.weixin.qq.com` page.

## Key facts

- **WeChat's `js_content` div is rendered with `style="visibility: hidden; opacity: 0;"`** until client-side JS hydrates it. The CONTENT IS THERE in the static HTML — do not skip it thinking it's empty/hidden. The bundled script's `find_content_block` matched this div in theory but produced garbled output in practice.
- **End sentinel**: the article body is followed by `<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p></div>`. Use `mp-style-type` as the cut-off marker — do not trust any "footer" heuristic on raw WeChat HTML.
- **Images use `data-src` not `src`** (WeChat lazy-load). The script already prefers `data-src` — good.
- **HTML entity decode order matters**: the script decodes entities BEFORE stripping the remaining tags. For some entity-heavy content (e.g. `&lt;` from a code sample, or `&quot;` inside an attribute echoed into the visible text), decoding first can cause the unescaped `<`/`>` to be mistaken for tags. In my manual workaround, stripping tags first then `html.unescape` produced cleaner output. The script's order works for the common case but is brittle.
- **Title comes from `og:title`**, not `<title>` (the `<title>` is empty on WeChat). Author/date are not in standard meta tags on WeChat — they require parsing the JS-side render hooks (`#js_name`, `js_article_create_time`) or fallback to a summary footer.
- **Page size**: a typical WeChat article HTML is **2-4 MB** (lots of inline `style` attributes per element, lots of `data-*` attributes, lots of `<span leaf="">` wrapping for the editor's text-run tracking). The script's 500KB slice limit is fine for the body itself but full-page is 3MB+.

## Working manual extraction recipe (used as fallback)

```python
import re
import html as htmlmod

with open('/tmp/wx_raw.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Locate js_content opening
start = html.find('id="js_content"')
assert start >= 0, "not a WeChat article page"

# 2. Cut at the mp-style-type sentinel (end of article body)
end = html.find('mp-style-type', start)
body_html = html[start:end]
# Drop the trailing <p style="display: none;"> tail if present
body_html = re.sub(r'<p style="display: none;">.*?</p>', '', body_html, flags=re.S)

# 3. Promote data-src -> src on <img>
body_html = re.sub(r'<img([^>]*?)\sdata-src="([^"]+)"', r'<img\1src="\2"', body_html)

# 4. Strip editor noise attributes
body_html = re.sub(r'\s*leaf=""', '', body_html)
body_html = re.sub(r'\s*nodeleaf=""', '', body_html)
body_html = re.sub(r'\s*data-aistatus="[^"]*"', '', body_html)

# 5. Block-level tags -> markdown
body_html = re.sub(r'<br\s*/?>', '\n', body_html)
body_html = re.sub(r'<p[^>]*>', '\n\n', body_html)
body_html = re.sub(r'</p>', '', body_html)
body_html = re.sub(r'<blockquote[^>]*>', '\n\n> ', body_html)
body_html = re.sub(r'</blockquote>', '\n\n', body_html)
body_html = re.sub(r'</?section[^>]*>', '\n', body_html)
body_html = re.sub(r'</?figure[^>]*>', '\n', body_html)

# 6. Inline tags
body_html = re.sub(r'<img[^>]*src="([^"]+)"[^>]*/?>', r'![image](\1)', body_html)
body_html = re.sub(r'<(strong|b)[^>]*>', '**', body_html)
body_html = re.sub(r'</(strong|b)>', '**', body_html)
body_html = re.sub(r'<em[^>]*>', '*', body_html)
body_html = re.sub(r'</em>', '*', body_html)
body_html = re.sub(r'<span[^>]*>', '', body_html)
body_html = re.sub(r'</span>', '', body_html)
body_html = re.sub(r'<center[^>]*>', '\n', body_html)
body_html = re.sub(r'</center>', '\n', body_html)

# 7. Strip remaining tags FIRST, then decode entities (this order matters)
body_html = re.sub(r'<[^>]+>', '', body_html)
body_html = htmlmod.unescape(body_html)
body_html = re.sub(r'\n{3,}', '\n\n', body_html).strip()
```

## When the bundled script fails — try these in order

1. **Re-run with a different selector**: the script's first attempt at `<div class="detail-content">` is for 53ai.com mirrors. For raw WeChat it falls through to `id="js_content"` — which should work, but in our test session it didn't.
2. **Sanity check** that the input is actually a WeChat page: `grep -c 'mp.weixin.qq.com' file` or `grep -c 'id="js_content"' file`. If neither, you got a CAPTCHA or a redirect.
3. **If the script warns "Could not find main content block"** but the file is 2MB+ and contains `id="js_content"`, the script's `find_content_block` has a bug on this case. Use the manual recipe above.
4. **If output is truncated** (image count high, char count low), the script likely fell back to full-HTML and pulled nav/header junk. Re-extract using the `js_content` → `mp-style-type` slice.

## Captured 2026-06-18 verification numbers

For the CodexGuide article (1240px-wide images, ~18 inline images):
- File: 2,992,565 bytes (3.0 MB)
- `id="js_content"` at byte 406,502
- `mp-style-type` at byte 425,298 → body slice 18,796 bytes
- Clean markdown output: 5,248 chars, 18 image links
- Bundled script output: 5,676 chars, 20 image links (2 extra from nav/header)
