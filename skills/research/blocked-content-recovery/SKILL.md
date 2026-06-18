---
name: blocked-content-recovery
description: Recovery workflow for when a direct content fetch (URL, API, file) is blocked by WAF/anti-bot, auth requirement, rate limit, or missing tools. Use when browser/curl/API returns 4xx/5xx/WAF/empty, when user pastes a URL but you have no working tool, or when you find yourself wanting to ask the user for title/screenshot/cookie before trying alternatives. Covers a 3-path discovery workflow (skill library → internet search → alternative methods) and a third-party skill/repo health check before adoption.
---

# Blocked Content Recovery

When a direct content fetch is blocked, run a **3-path discovery workflow** before giving up or asking the user. Do not stop at the first failure.

## Trigger Conditions

Activate this skill when any of the following is true:

- Browser, curl, or API call returns WAF challenge ("环境异常", "Access Denied", CAPTCHA, 滑块验证)
- HTTP returns 4xx/5xx or empty body where 2xx was expected
- You lack a tool to perform the user's task (e.g., user pastes a 微信公众号 link)
- You find yourself wanting to ask the user for the title, screenshot, or content directly — **stop and run the discovery workflow first**
- A third-party skill looks promising but you have not verified it actually works

## The 3-Path Discovery Workflow

Run these in order. Stop only when one of them produces a working result.

### Path 1 — Skill Library Search (do this first, ~5s)

```bash
hermes skills browse                  # scan local skills (~no network)
hermes skills search <keyword>        # search SkillHub registry (may be slow, can run in background)
hermes skills list --category <cat>   # filter by category
```

Match the user's task against the skill list. Many content-extraction patterns already exist as agent-installed skills (e.g. `ocr-and-documents`, `xurl`, `youtube-content`, `blogwatcher`, `nano-pdf`).

**If you find a matching skill** — load it with `skill_view` and follow its instructions. Stop.

**If `search` times out** — put it in the background with `terminal(background=true, notify_on_complete=true)` and continue with Path 2 in parallel.

### Path 2 — Internet Search for Known Workarounds (~5s)

Search the public web for "<problem> workaround 2025 2026" or "<problem> 解决方案". Targets to look for:

- GitHub repos with stars > 20 and last activity < 12 months
- Blog posts on csdn / 知乎 / 掘金 with concrete code
- StackOverflow answers with working examples
- Vendor docs / official APIs

If the target platform has a known mirror or旁路, prefer that:

| Target | Known bypass |
| --- | --- |
| 微信公众号 (mp.weixin.qq.com) | 搜狗微信搜索 `weixin.sogou.com/weixin` (with cookie), GitHub `wechat-article-extractor-*` repos |
| Paywalled / deleted pages | `web.archive.org/web/<url>`, Google cache, 转载站 |
| Sites blocking headless UA | `curl` with full `User-Agent` + `Referer` + `Cookie` from a real browser session |
| Anti-bot WAFs | 仿浏览器: Selenium/Playwright with `navigator.webdriver` patched, residential proxy, persistent browser profile |

### Path 3 — Alternative Methods

If Paths 1 and 2 yield nothing:

- **Sogou / Bing / DuckDuckGo** with `site:` operator to find re-posts of the content
- **Wayback Machine** for archived versions of the URL
- **Different user agent family** (mobile UA often bypasses desktop WAFs)
- **Public APIs the target exposes** (e.g., 公众号's RSSHub route, YouTube Data API)
- **Direct HTML** if the page is a static page (sometimes the browser hits JS-required paths, but `curl` on the document HTML is enough)

## Critical Rules (do not skip)

1. **Never give up or ask the user before exhausting all 3 paths.** Asking the user for title/screenshot/cookie is a *last resort*, not a *first move*.
2. **Always verify with real HTTP 200 before claiming something works.** Do not say "已搜到" / "已配置" / "API 已通" without a `tool_call` showing the actual response (status code, body sample, etc.). This is a hard rule for this user — they will catch and call out any fabrication.
3. **When you must ask the user, offer concrete options, not open-ended questions.** "Do you want A, B, or C?" is fine. "How should we proceed?" is not.
4. **Do not act as a CAPTCHA solver.** If a 滑块 / hCaptcha / 极验 page appears, switch to Path 2 (search for旁路) instead of trying to bypass the challenge. You will lose and waste cycles.
5. **If an MCP tool returns a generic auth error, the issue may not be auth.** Probe with direct HTTP before assuming credentials are wrong — body schema mismatches often surface as `login fail` messages from MCP wrappers.

## Third-Party Skill / Repo Health Check

Before adopting any third-party skill, repo, or library, do a 60-second health check. Many "look-good" GitHub repos are abandoned demos with unmaintained deps.

### Red Flags (one or more = treat as demo, not mature tool)

- `created_at == pushed_at` AND recent (last commit same day as creation)
- README still has placeholder text (`yourusername`, `TODO`, `FIXME`, `<repo-name>`)
- Dependencies include `request-promise`, `request`, `node-sass`, or any package deprecated > 2 years
- Stars < 5, forks < 5, no description
- Last commit > 12 months ago with open issues
- Code does not work when actually run (use the `spike` skill for quick throwaway validation)

### Health Check Recipe

Use the script at `scripts/github-repo-health.py` (in this skill's directory). It returns a JSON verdict you can paste into chat as evidence.

```bash
python ~/.hermes/skills/blocked-content-recovery/scripts/github-repo-health.py <owner>/<repo>
```

## Tool-Specific Notes (update as you discover more)

### minimax Token Plan MCP `web_search` is broken (as of 2026-06)

The MCP tool sends body `{query: ...}` but the API requires `{q, count}`. It returns `login fail: Please carry the API secret key` regardless of credentials. **Workaround**: call the HTTP endpoint directly.

```python
import json, urllib.request, os, re
key = None
with open(os.path.expanduser('~/.hermes/.env')) as f:
    for line in f:
        m = re.match(r'^MINIMAX_CODING_API_KEY\s*=\s*["\']?([^"\'\s]+)', line)
        if m: key = m.group(1); break
req = urllib.request.Request(
    'https://api.minimaxi.com/v1/coding_plan/search', method='POST',
    headers={'Authorization': f'Bearer {key}', 'MM-API-Source': 'MiniMax-M3', 'Content-Type': 'application/json'},
    data=json.dumps({"q": query, "count": 5}).encode())
with urllib.request.urlopen(req, timeout=20) as r:
    print(json.loads(r.read()))
```

## Common Pitfalls

- **Headless browser + WAF = usually useless.** Server-side bot detection sees through `playwright`/`puppeteer` headers in 2026. Only useful with stealth plugins + residential proxies, and even then unreliable.
- **SkillHub registry can be slow.** `hermes skills search` regularly exceeds 60s on first call. Run in background; do not block the workflow on it.
- **Treat generic MCP errors as "probe with direct HTTP", not "the key is broken".** A `login fail` from a coding-plan MCP usually means body schema, not auth.
- **Do not encode "browser doesn't work" or "X tool is broken" as a negative rule.** Tools change; capture the *workaround* not the *refusal*.

## Verification Checklist (before reporting success)

- [ ] Tool call shows real 2xx response with non-empty data
- [ ] Third-party skill, if any, passed the health check
- [ ] If asking user for input, you gave concrete options (not "what do you want?")
- [ ] If a workaround was used, you noted it for the next time this domain comes up
