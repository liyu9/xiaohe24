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
**飞书真·交互式卡片 v2 终极 schema**（2026-06-05 实测纠正, 3 轮 patch 教训）：
- **唯一真·卡片**：`msg_type=interactive` + 顶层 `tag:"markdown"` 元素 + `header.template="blue"` + `header.title.content`（**header 不支持 icon**, markdown 元素支持 `icon: {tag:standard_icon, token, color}` 前缀图标）
- **5 种 200 OK 试验**：`tag:"markdown"` 顶层 / 无 schema / schema:"2.0" / `body.content` 包 markdown / `body.elements` 包 lark_md — **只有"顶层 `tag:"markdown"` 元素"客户端真·渲染 markdown**（列表/代码块/表格/加粗/斜体/链接全生效），其他形式虽然 200 OK 但飞书 IM 客户端**剥元素退化为 text**
- **❌ 错的（不要用）**：`tag:"div"` 包裹 `tag:"lark_md"` (飞书服务端把 div 元素剥掉退化成富文本)、`msg_type=post` + `zh_cn.title` (post 类型的 markdown 渲染仅部分生效)、`tag:"lark_md"` 顶层 (230099 unsupported)
- **飞书图标库**：~500 个 token，主人 6-05 选用 `chat_outlined` color=blue 配 "小赤" 卡片 header（飞书无 `robot/ai/bot` 主题图标，最贴近 AI 是 chat 类）
- **icon 元素仅生效一次**：只加在第一个 markdown 元素上避免重复
- **Markdown 元素 4000 字符上限、卡片 50 元素上限**：长内容要 truncate
- **含 markdown 表格时 SDK 降级为 plain text**（`_MARKDOWN_TABLE_RE` 检测）——保护原有行为不动
- **飞书 7.6+ 客户端支持完整 markdown 语法**（列表/代码块/表格），旧版降级占位图
- **当前 patch**（`feishu.py:4342-4361`）：`_build_outbound_payload` 走 interactive + header_title="小赤" + chat_outlined 图标
- **systemd 慢速关停**：feishu.py 改完 `systemctl --user restart hermes-gateway` 触发 `MemoryHigh=1200M` + `TimeoutStopSec=90` 慢速停, terminal 60s 超时会被打断. 用 `terminal(background=true, notify_on_complete=true)` 异步等