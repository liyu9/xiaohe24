# Keyword patterns by event class

Each section is a **starter set** — replace with the user's actual vocabulary
after a few days of observation. The default assumption is Chinese, with
English / pinyin as fallback only when the user has used them in chat.

## 1. Medication intake (the canonical case)

**Drug keywords (canonical → alias):**
- 氯雷他定 → 开瑞坦
- 西替利嗪 → 仙特明
- 依巴斯汀 → (no common alias)
- 息斯敏 → 阿司咪唑
- 扑尔敏 → 氯苯那敏
- 非索非那定 → (no common alias)
- 孟鲁司特 → 顺尔宁
- "过敏药" / "抗过敏" → fallback: write "未指定药品名" via the LLM-asks branch

**Intake signals** (must match one):
- 刚吃 / 刚吃了 / 刚服了 / 刚喝了 / 刚服 / 刚吞
- 吃了 / 服了 / 喝了 / 吞了
- 吃了一片 / 吃了两片 / 吃了一颗
- "今天早上吃了" / "中午吃了" (time-of-day qualifier is fine)

**Bare mentions (do NOT trigger):**
- "这药副作用大不大"
- "氯雷他定能长期吃吗"
- "X 跟 Y 能一起吃吗"

**Dose regex:** `(\d+\s*(?:mg|毫克|片|颗))` — handles "10mg", "1片", "10 毫克".

**Symptom keywords (Chinese; ordered by frequency):**
荨麻疹 / 鼻塞 / 打喷嚏 / 眼睛痒 / 皮肤痒 / 流鼻涕 / 鼻痒 / 皮疹 / 湿疹 / 瘙痒

## 2. Coffee / drink intake

**Drink keywords:** 咖啡 / 美式 / 拿铁 / 卡布 / 摩卡 / 浓缩 / 手冲 / 冷萃 / latte / americano
**Intake signals:** 喝了 / 刚喝 / 来了一杯 / 续了一杯 / 灌了 / 整了
**Bare mentions:** "咖啡因有什么影响" / "哪种咖啡好喝"
**Size keywords:** 小杯 / 中杯 / 大杯 / 特大 / 短笛 / tall / grande / venti

**Anti-pattern**: do not assume "1 杯" means any size; if user said "喝了杯
咖啡" without size, leave 杯型 column empty.

## 3. Exercise / workout

**Activity keywords:** 跑步 / 跑了 / 跑了步 / 跑了X公里 / 跑了X分钟 / 撸铁 / 举铁 / 游泳 / 骑车 / 瑜伽 / HIIT / pilates
**Intake signals:** 跑了 / 游了 / 骑了 / 练了 / 做了 / 刚练完 / 撸完
**Duration regex:** `(X\s*(?:分钟|分|小时|小时|k|公里))` — works for "30分钟", "1小时", "5k"

**Anti-pattern**: do not assume duration from a vague "跑了会儿" — the
duration column is the load-bearing data, leave it empty.

## 4. Expense (record keeping)

**Amount regex:** `(?:花了|花了|付了|花了|用了|共计|总共)[约大概]?\s*(\d+(?:\.\d+)?)\s*元?`
- 涵盖 "花了 50 块" / "付了 128" / "总共 89.5"

**Trigger phrases:** 买了 / 花了 / 付了 / 订了 / 订了 / 充值了
**Anti-pattern**: do not extract amount from "几十块" or "一百多" — fuzzy
amounts are not recordable. The amount column is load-bearing; if you can't
parse a number, ask.

**Optional columns:** 类别 (餐饮/交通/购物/...), 支付方式 (微信/支付宝/...),
备注

## 5. Study / focus time

**Activity keywords:** 看了 / 复习了 / 写了 / 做了 / 学了 / 看了X章
**Subject keywords** (optional column): 语文 / 数学 / 英语 / 专业课 / 代码
**Duration regex:** same as exercise (X小时 / X分钟)

## 6. Mood / health log

**Mood keywords** (single-select options): 开心 / 平静 / 烦躁 / 焦虑 / 抑郁 / 疲惫
**Health keywords** (single-select options): 正常 / 头疼 / 失眠 / 胃疼 / 感冒
**Trigger phrases:** 今天感觉 / 我现在 / 觉得 / 状态
**Anti-pattern**: do not parse mood from "我今天加班到十点，真累" — "累" is
not in the option list; let the LLM ask. Or extend the option list with
疲惫/累/累死了 and re-evaluate.

## Pattern to avoid across all classes

- **Do not** add common Chinese sentence-final particles (啊/呀/呢/吧/了) as
  intake signals. They have too many false positives in non-intake sentences.
- **Do not** include "今天"/"刚才" as intake signals. They are temporal
  qualifiers, not actions; the LLM context is already time-stamped.
- **Do not** include "想"/"要"/"会" as intake signals. They are future-tense
  or hypothetical, not actual events.

## How to extend this list safely

After 2-3 days of running the plugin, search the Bitable for rows where
备注 contains a keyword you did not anticipate. Add that keyword to the
relevant section and bump the plugin version. Do not bulk-add on day 1;
the user's vocabulary is the source of truth, not a generic dictionary.
