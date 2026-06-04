Skills `skillhub-management` and `finance-data` created from one session — captured the recurring "check CLI → search → install" SkillHub pattern (used 3+ times in one session) and the qt.gtimg.cn / Stooq free-quote endpoints with GBK decoding pitfall.
§
飞书消息格式约束（Hermes 默认 text 类型，避免被 strip markdown 剥光）：
- ✅ 安全：**粗体 **x** / 斜体 *x* / 行内代码 `x` / [链接](url) / - 列表项（必须 - 不要 * 或 1.）
- ❌ 禁用：markdown 表格、# ## 标题、> 引用、嵌套列表（缩进会丢）、多行代码块
- 改写技巧：表格→编号列表 ①②③；标题→粗体+换行；代码块→行内代码+短行
- 长内容：>1500 字主动拆 2-3 条
- 验证：飞书 preferred_message_type='text' 路径在 feishu.py:1789 失败时降级到 text + _strip_markdown_to_plain_text（彻底剥光）
- 视觉任务先实测再写：之前编"图是费曼学习法"是真错误，HTTP 200 真调用 M3 后才看到实际是 minimax 产品页
§
**minimax Token Plan MCP 部署**（实测跑通）：包 `minimax-coding-plan-mcp` PyPI v0.0.4，端点 `POST https://api.minimaxi.com/v1/coding_plan/search`（Bearer 鉴权 + MM-API-Source header），工具 `web_search`/`understand_image`（后者**付费**）。**必须**腾讯 PyPI 镜像 + venv 装（pip --target 装 binary 找不到包），wrapper 调 `venv/bin/python -c "from minimax_mcp.server import main()"`，路径持久化到 `~/.hermes/mcp/...`（**不**放 /tmp）。yaml `${VAR}` 引用 env，key 留 .env chmod 600。`mcp_servers.X.connect_timeout: 120+`，env 全大写 KEY 被 `hermes config set` 误判时手 patch yaml。`hermes mcp test` 报 "Connection closed" = 99% server import 错，**不**是网络；用 `timeout 5 wrapper < /dev/null` 看 traceback。

**Claude Code CLI 部署**（v2.1.162 装好，无 key 暂未调通）：`npm install -g @anthropic-ai/claude-code` 腾讯镜像 5s，binary 在 prefix 自定义目录必须 export PATH。鉴权 3 选 1：A. ANTHROPIC_API_KEY 写 .env；B. `claude auth login` OAuth 需浏览器；C. **国内推荐** OpenRouter 跳板（ANTHROPIC_API_KEY=sk-or-... + ANTHROPIC_BASE_URL=https://openrouter.ai/api/v1）。坑：`doctor`/`auth status` 无 key 时连 anthropic 超时 60s+（**不**用探活）；编码任务必加 `--max-turns`+`--max-budget-usd`+`--allowedTools`；国内 api.anthropic.com 返 403 直连。封装 `~/.hermes/bin/claude_code_caller.py`：call_claude() Python API + tmux 交互模式。协作规则 `~/.claude/CLAUDE.md`：仅写新功能/重构/复杂 bug/测试生成时调 Claude，单行改/配置 key/小脚本小赤自己写。

**vision**：minimax-M3 走 anthropic_messages 协议（`/anthropic/v1/messages`），多模态可用；`auxiliary.vision.provider: minimax_coding` + `image_input_mode: both` 即可。

**飞书流式核心**：PATCH `im/v1/messages/{message_id}` 增量更新已发卡片，**不**刷屏。