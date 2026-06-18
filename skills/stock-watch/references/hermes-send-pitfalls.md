# `hermes send` Push Pitfalls (Learn Once)

When a stock-watch script needs to push a WeChat/IM message, the
naive `os.system("hermes send -t weixin 'msg'")` looks fine but **hangs the
caller indefinitely**. The reason: `hermes send` runs an LLM-driven agent
loop to deliver, even when message text is passed via `-f`. From a watch
loop you want fire-and-forget, not roundtrip.

## Correct pattern (use this)

```python
import subprocess, tempfile
def send(msg):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(msg); tmp = f.name
    subprocess.Popen(
        ["hermes", "send", "--quiet", "-t", "weixin", "-f", tmp],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    # DO NOT call .wait() — returns immediately, send happens in background
```

Why this works:
- **`-f <file>`** avoids shell quoting hell for messages with `"` / `$` / `\`
- **`subprocess.Popen` (not `run` / not `os.system`)** — non-blocking
- **`DEVNULL` for stdout/stderr** — the agent's verbose output doesn't pollute your script's stdout
- **No `wait()`** — your watch loop can keep ticking every 3 min

## Also wrong

| Pattern | Failure mode |
|---|---|
| `os.system("hermes send ...")` | blocks until full send completes; subprocess inherits stdin and can wait for input |
| `subprocess.run([...], capture_output=True)` | blocks; if delivery takes 30s, your 3-min cron tick stacks up |
| `hermes send "msg"` with backticks/dollar in msg | shell expands `$VAR` and `\`cmd\`` — message arrives with garbage |
| `hermes send "msg"` with double-quote in msg | shell arg parse breaks |

## For long messages (>1800 chars)

WeChat/IM clients truncate around 2000 chars. Split before sending:

```python
def chunked_send(msg, max_len=1800):
    chunks, cur, n = [], [], 0
    for line in msg.split("\n"):
        if n + len(line) + 1 > max_len:
            chunks.append("\n".join(cur)); cur, n = [], 0
        cur.append(line); n += len(line) + 1
    if cur: chunks.append("\n".join(cur))
    for i, ck in enumerate(chunks, 1):
        if len(chunks) > 1:
            ck = f"[{i}/{len(chunks)}]\n{ck}"
        send(ck)  # uses the safe send() above
```

## For tests / dry-runs

Set `STOCK_DRY_RUN=1` env var; the script's `send()` should early-return and
print the message it *would* have sent. This lets you run `STOCK_DRY_RUN=1
python3 stock-watch.py close --force` to verify the message body without
pushing to WeChat.

## Cron + deliver=origin

When scheduling a push via `hermes cronjob create --deliver origin`, the
agent's final response (the one from your prompt) is auto-routed back to
the same channel that started the cron. For watch-style jobs, the prompt
should NOT do `os.system` or `subprocess.run`; either let cron deliver
the agent's stdout, or do the send inside the script before the agent
exits (using the safe Popen pattern above).

## See also

- `finance-data` skill → "A 股 + 港股 (Tencent Finance)" — same
  `qt.gtimg.cn` endpoint, GBK decoding
- `stock-watch/SKILL.md` → the full watchlist + cron + threshold pattern
