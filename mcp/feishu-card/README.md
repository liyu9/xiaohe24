# 飞书卡片消息工具 / Feishu Card Tool

`hermes-agent` 的飞书 interactive 卡片消息 + 流式更新工具集。**纯 stdlib**，**无**第三方依赖，**0 网络外**。

## 目录

```
~/.hermes/mcp/feishu-card/
├── feishu_card.py        # 核心库（send/update/reply/token）
├── template_send.py      # 模板化快速发送（alert/progress/report）
├── run-mcp.sh            # minimax MCP wrapper（持续运行）
├── templates/
│   ├── alert.json        # 告警卡片
│   ├── progress.json     # 任务进度
│   └── report.json       # 数据报告
├── venv/                 # minimax-coding-plan-mcp 的 venv
├── logs/                 # （保留）
└── README.md             # 本文件
```

## 凭证

凭证存在 `~/.hermes/feishu_credentials.json`（chmod 600）。**不要**写进 git，**不要**贴飞书。

格式：
```json
{
  "app_id": "cli_xxxxxxxxxxxx",
  "app_secret": "32位字符串"
}
```

**首次配置**：
```bash
python3 ~/.hermes/mcp/feishu-card/feishu_card.py save <app_id> <app_secret>
```

**飞书开放平台开权限**（一次性）：
1. https://open.feishu.cn/app → 选 App
2. 权限管理 → 搜"消息" → 勾选 `im:message` 全套
3. 搜"联系人" → 勾选 `contact:user.id:readonly`
4. 创建版本 → 申请发布（企业内部直接通过）

## 3 种用法

### 1. CLI 简单发

```bash
# 拿 token 测试
python3 feishu_card.py token

# 发卡片（JSON 从文件）
python3 feishu_card.py send ou_xxxxx templates/alert.json
# → message_id: om_xxxxxx

# PATCH 更新（同一 message_id）
python3 feishu_card.py update om_xxxxxx templates/alert_v2.json

# 回复（reply 模式）
python3 feishu_card.py reply om_xxxxxx templates/report.json
```

### 2. 模板化发送（推荐）

```bash
# 告警
python3 template_send.py alert ou_xxxxx \
  --title "服务异常" \
  --severity "严重" \
  --time "2026-06-04 17:30" \
  --description "CPU 持续 5 分钟 > 90%" \
  --button-url "https://grafana.example.com" \
  --alert-id "AL-2026060401"

# 任务进度
python3 template_send.py progress ou_xxxxx \
  --title "数据备份" \
  --current 2 --total 5 \
  --status "备份中..." \
  --steps "1. 启动\n2. 备份 /home\n3. 备份 /etc\n4. 备份 /var\n5. 验证"

# 数据报告
python3 template_send.py report ou_xxxxx \
  --title "腾讯 00700" \
  --subtitle "今日行情" \
  --items "**现价：456.200 港元**\n**涨跌：-2.19%**" \
  --button-url "https://quote.eastmoney.com/hk/00700.html"
```

### 3. Python import

```python
import sys
sys.path.insert(0, "/home/ubuntu/.hermes/mcp/feishu-card")
import feishu_card as fc

card = {
    "config": {"wide_screen_mode": True},
    "header": {
        "title": {"content": "📊 测试卡片", "tag": "plain_text"},
        "template": "blue"
    },
    "elements": [
        {"tag": "markdown", "content": "**Hello from Hermes**"}
    ]
}
msg_id = fc.send_card("ou_xxxxx", card)
print(f"已发: {msg_id}")

# 后续更新
fc.update_card(msg_id, card)  # 传新 card
```

## 流式更新（核心场景）

**典型场景**：cron 任务跑 5 分钟，主人要"边跑边看状态"。

```python
import time
import feishu_card as fc

# 1) 发占位卡片
card_placeholder = {
    "header": {"title": {"content": "🔄 任务执行中", "tag": "plain_text"}, "template": "blue"},
    "elements": [{"tag": "markdown", "content": "⏳ 启动中..."}]
}
msg_id = fc.send_card("ou_xxxxx", card_placeholder)
print(f"占位卡片: {msg_id}")

# 2) 步骤 1
time.sleep(2)
fc.update_card(msg_id, {
    "header": {"title": {"content": "🔄 数据备份", "tag": "plain_text"}, "template": "blue"},
    "elements": [{"tag": "markdown", "content": "**1/5** 备份 /home ✅"}]
})

# 3) 步骤 2
time.sleep(2)
fc.update_card(msg_id, {
    "header": {"title": {"content": "🔄 数据备份", "tag": "plain_text"}, "template": "blue"},
    "elements": [{"tag": "markdown", "content": "**2/5** 备份 /etc ⏳"}]
})

# ... 后续 ...

# 4) 完成
fc.update_card(msg_id, {
    "header": {"title": {"content": "✅ 任务完成", "tag": "plain_text"}, "template": "green"},
    "elements": [{"tag": "markdown", "content": "**5/5** 全部完成 🎉"}]
})
```

**主人在飞书看**：同一张卡片**持续刷新**，**不**会刷屏。

## 卡片 header 颜色

| 颜色 | template 值 | 适用场景 |
|---|---|---|
| 蓝 | `blue` | 普通信息、进度 |
| 绿 | `green` | 成功、完成 |
| 黄 | `yellow` | 警告 |
| 橙 | `orange` | 提示 |
| 红 | `red` | 错误、告警 |
| 灰 | `grey` | 存档、关闭 |
| 靛 | `indigo` | 通知 |
| 紫 | `purple` | 特殊标记 |

## Element 组件

| tag | 用途 |
|---|---|
| `markdown` | Markdown 文本（支持 `**粗体**` `*斜体*` `[链接](url)` `<font color='red'>...</font>` `<at user_id="ou_xxx"/>`） |
| `divider` / `hr` | 分割线 |
| `plain_text` | 纯文本 |
| `note` | 灰色提示栏 |
| `action` | 按钮组容器 |
| `button` | 按钮（`type`: `default`/`primary`/`danger`） |
| `image` | 图片 |
| `column_set` | 多列布局 |
| `form` | 表单（输入框、选择器） |
| `person` | 人员 |
| `chat` | 群聊 |

完整组件库：https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-components

## PATCH 限制

`update_card` 有以下限制（**飞书官方**）：
- 1 分钟内 PATCH 同一 message_id **最多 5 次**（频繁会被限流）
- **不支持**改 msg_type（必须是 interactive）
- **不支持**改 receive_id
- 卡片 JSON **必须**完整（**不**是 PATCH 局部）

## Token 管理

- **自动缓存 2 小时**（剩 60s 自动续）
- 不用每次都传
- 失效时**自动**重拿

## 飞书 API 端点

| 端点 | 用途 |
|---|---|
| `POST /open-apis/auth/v3/tenant_access_token/internal` | 拿 token |
| `POST /open-apis/im/v1/messages?receive_id_type=open_id` | 发消息（卡片/文本/富文本/图片/文件） |
| `PATCH /open-apis/im/v1/messages/{message_id}` | 更新已发卡片 |

官方文档：
- 卡片消息：https://open.feishu.cn/document/server-docs/im-v1/message/create
- 更新卡片：https://open.feishu.cn/document/server-docs/im-v1/message-card/patch
- Markdown 标签：https://open.feishu.cn/document/common-capabilities/message-card/message-cards-content/using-markdown-tags

## 已知限制

- **不**支持机器人 webhook 模式（仅支持 tenant_access_token）
- **不**支持发送/更新"系统消息"（如欢迎语）
- **不**支持富文本 `post` 消息（仅 `interactive` 卡片）
- 凭证**不**支持自动刷新（手动重跑 `save` 命令）

## 维护

- 不需要 cron / 后台进程
- 重启系统**不**丢失（路径在 `~/.hermes/mcp/feishu-card/`）
- venv 已固化（含 40+ deps：minimax_mcp, dotenv, mcp, fastmcp 等）
