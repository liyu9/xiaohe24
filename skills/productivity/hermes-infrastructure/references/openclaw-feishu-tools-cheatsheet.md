# OpenClaw Feishu Tools Cheatsheet

Extracted from `@openclaw/feishu/dist/api.js` (community-maintained plugin by @m1heng, version 2026.6.1). All tools are invoked via `POST /tools/invoke` with body `{"name": "<tool>", "args": {...}}` and `Authorization: Bearer <gateway.auth.token>`.

## Bitable (multi-dimensional table)

| Tool | Required Args | Returns |
|---|---|---|
| `feishu_bitable_create_app` | `name` | `{app_token, default_table_id, url}` |
| `feishu_bitable_create_field` | `app_token, table_id, field_name, type, property` | field object |
| `feishu_bitable_create_record` | `app_token, table_id, fields` | `{record: {record_id, fields}}` |
| `feishu_bitable_update_record` | `app_token, table_id, record_id, fields` | updated record |
| `feishu_bitable_get_meta` | `url` (or app_token+table_id) | `{app_token, tables: [...]}` |
| `feishu_bitable_get_record` | `app_token, table_id, record_id` | record |
| `feishu_bitable_list_fields` | `app_token, table_id` | fields array |
| `feishu_bitable_list_records` | `app_token, table_id, page_size?, page_token?` | `{records, has_more, total, page_token}` |

Field types (for `create_field`): `1` = text, `5` = date (ms epoch), `7` = checkbox, `13` = number, etc. See Lark OpenAPI docs for the full enum.

## Doc (Feishu Docs / Wiki Docs)

`feishu_doc` is a **multi-action tool**. One call, one tool, switch on `action`:

- `read` — args: `doc_token` → returns blocks
- `write` — args: `doc_token, content` → replaces doc
- `append` — args: `doc_token, content` → adds to end
- `insert` — args: `doc_token, content, after_block_id` → inserts at position
- `create` — args: `title, folder_token?, grant_to_requester?` → new doc
- `list_blocks` — args: `doc_token`
- `get_block` — args: `doc_token, block_id`
- `update_block` — args: `doc_token, block_id, content`
- `delete_block` — args: `doc_token, block_id`
- `create_table` / `create_table_with_values` / `write_table_cells` — table sub-actions
- `insert_table_row` / `insert_table_column` / `delete_table_rows` / `delete_table_columns` / `merge_table_cells`
- `upload_image` / `upload_file` — args: `doc_token, url OR file_path, parent_block_id?, filename?`
- `color_text` — args: `doc_token, block_id, content`

## Drive (cloud space)

`feishu_drive` — `action`: `list`, `get`, `move`, `delete`, `upload`, `download`, etc. Args: `action, file_token, ...`.

## Chat (metadata only — NOT a message sender)

`feishu_chat` — `action`: `members` | `info` | `member_info` (3 actions, all read-only). Args depend on the action.

- `members` — args: `chat_id`, optional `page_size`/`page_token`/`member_id_type` → chat members list
- `info` — args: `chat_id` → chat metadata
- `member_info` — args: `member_id`, optional `member_id_type` (default `open_id`) → one member

> **⚠️ Reality check2026-06-09:** This cheatsheet used to list `send_message`/`list_chats`/`get_chat`/`list_members` as available actions. **They are not in the installed plugin.** `@openclaw/feishu@2026.6.1` only implements the3 actions above. Verified by reading `node_modules/@openclaw/feishu/dist/drive-BIrffRwc.js:236-247` (the `switch(p.action)` in `feishu_chat.execute`) and by live `/tools/invoke` probes returning `Unknown action: send_message` / `Unknown action: list_chats` / etc.
>
> **Implication:** `openclaw` gateway **cannot send Feishu IM messages** in this plugin version. To DM the user, fall back to direct Feishu OpenAPI `POST /open-apis/im/v1/messages` with `FEISHU_APP_ID`/`FEISHU_APP_SECRET` from `~/.hermes/.env` + a cached `tenant_access_token` (use `~/.agents/skills/feishu-enhanced/scripts/feishu_card.py token`).
>
> **Don't trust this cheatsheet table blindly — always probe** with the loop in the parent SKILL.md before betting a workflow on a tool.

## Wiki (knowledge base)

`feishu_wiki` — `action`: `list_spaces`, `get_space`, `list_nodes`, `get_node`, `move_node`, etc.

## Permission

`feishu_perm` — `action`: `grant`, `revoke`, `transfer`, `list`. Args depend on the action.

## App scopes

`feishu_app_scopes` — discover / verify the app's granted OAuth scopes.

## Common return shape

All tools return their payload JSON-stringified inside `result.content[0].text`. To extract:

```python
text = resp["result"]["content"][0]["text"]
payload = json.loads(text)
```

If the call failed inside the Lark SDK, `result.details.error` will have a human-readable message (e.g. `"request miss app_token path argument"`).
