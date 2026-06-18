# Hermes → Feishu: What Actually Happens on the Wire

This is the condensed transport flow that Hermes uses to deliver assistant
text into Feishu. The key file is
`gateway/platforms/feishu.py` in the Hermes install. The behaviour described
here is what the agent has to write against.

## Default text path (the one the user actually sees)

1. `FeishuPlatform.send()` is called with a chunk of assistant text.
2. `_build_outbound_payload(chunk)` picks `msg_type`:
   - `text` is the default (`preferred_message_type: str = "text"` at l.353).
   - If the chunk contains certain structures (lists, links, etc.) it may
     try `post` (rich text) using `tag: "md"` inline markdown (l.572, 606).
3. `_send_to_feishu` POSTs to `im/v1/messages` with `msg_type=text` and the
   payload as `{"text": json.dumps(content)}`.
4. **If the Feishu API returns an error** — especially the
   `_POST_CONTENT_INVALID_RE` regex at l.1791 — the platform **automatically
   falls back to `msg_type=text` with `_strip_markdown_to_plain_text(chunk)`**
   (l.1796-1797). This is the strip.
5. The fallback payload is `{"text": <plain text>}`. The user sees a wall
   of unformatted text.

**Key insight:** even though the agent wrote beautiful markdown, the
fallback is silent. The user just sees "format didn't render".

## What the strip removes

`_strip_markdown_to_plain_text` (defined somewhere in feishu.py) does
roughly:

- Strips `**bold**`, `*italic*`, `` `code` `` markdown markers
- Removes `#`, `##`, `###` headers (the whole line)
- Removes `>` blockquote markers
- Removes `|` table pipes and `---` table separators
- Collapses multi-line code blocks to a placeholder like `[code]`
- Compresses internal whitespace

So **bold becomes plain, headers disappear, tables become runs of
words separated by spaces, and code blocks become `[code]`**. The user
sees the *words* but not the *structure*.

## Where the actual markdown can survive

The `post` message type uses Feishu's `tag: "md"` inline element, which
DOES render **bold**, *italic*, `code`, and links — as long as the API
accepts the payload. The `post` path is taken when:

- The chunk's content passes the validity regex (no weird control chars,
  no over-long lines, no markdown that Feishu's parser rejects).
- The Feishu API doesn't return 230xxx (content invalid) errors.

In practice this means **simple inline markdown survives if and only if
the chunk's total length and structure are within Feishu's post-format
limits**. Long tables, nested lists, and multi-line code blocks frequently
trip the regex.

## What survives in text-type (the fallback)

After `_strip_markdown_to_plain_text`, what's left:

- Plain text content
- Emojis (they're not markdown)
- Newlines (the strip collapses runs but preserves one)
- URLs (they're plain text)

The user's client renders this as monospace-style or proportional text
depending on their settings, with no bold, no bullets, no structure.

## Card path (`msg_type: interactive`)

`feishu.py:870-880` handles `interactive` and `card` types. The agent
doesn't emit this by default. The structure is Feishu's Card JSON 2.0
schema (header, elements, fields, actions). To use it from Hermes you
have to construct the JSON yourself and call
`feishu-api.sh send` from the `feishu-enhanced` skill, or patch
`preferred_message_type` in venv source (fragile).

## What this means for the agent

The cheapest path to "looks right in Feishu":

1. Write using only the constructs that survive `_strip_markdown_to_plain_text`
   (plain text, emojis, newlines, manual indentation with full-width spaces).
2. Use `**bold**` *italic* and `` `code` `` markers liberally — the strip
   removes them, but if the chunk happens to go through the `post` path
   (which it sometimes does for short messages), they render.
3. For tables, lists, headers — rewrite as flat bulleted or numbered lists
   with bold lead-ins. See `SKILL.md` for the translation table.

The most reliable path:

1. Tell the user the message is going to be long.
2. Send the structured part (table, code) as a file attachment via
   `send_document` (l.2054) so the user gets the original formatting.
3. Send a short summary in the chat that uses the Feishu-friendly format.

This is the cleanest answer when the structure is load-bearing and the
fallback strip would destroy it.
