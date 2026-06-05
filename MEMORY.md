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
- **飞书 7.6+ 客户端支持完整 markdown 语法**（列表/代码块/表格），旧版降级占位图
- **schema 2.0 卡片不渲染 form/input/selectMenu/datePicker**（6-05 实测给主人 DM 发 1 张含这些元素的卡片，HTTP 200 + code:0 但飞书客户端**按钮和表单全部不显示**，hr + note 能渲染但交互元素被静默丢弃）。这些是 schema 1.0 专属元素，新版 interactive 卡片走 schema 2.0 框架不识别。**真·可用的交互元素**只有 button / markdown / hr / note / collapsible_panel / standard_icon / action 容器。指南文档"form 容器回传数据"那套是过时 schema 1.0
§
**加粗红线**（6-05 主人拍板，已违反 1 次）：飞书回复中**禁止字字加粗 / 词组加粗**。SOUL.md 有这条规则但容易在长文里滑过去。**自检规则**——回复前扫一眼加粗数量：飞书短消息 ≤ 1 处加粗，长分析 ≤ 2 处，且加粗的必须是"整段观点"而非"短语"或"词组"。判断标准：把加粗的 3-4 个字拎出来独立看，是完整观点才允许加粗；是名词/动词/形容词一律去掉加粗。例：❌ 第 **1 层**：长期记忆  ✅ 第 1 层：长期记忆 / 整段：**小赤没灵魂但可以逼近**（这条整段是结论可加粗）。