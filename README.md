# 医院战略规划教练（Hospital Strategy Planning Skill）

把张琨《听完几十家医院「十五五」规划，我坐立难安！》里的**十一条建议**，做成一个可以装进 Agent harness（DSH / Claude Code / WorkBuddy 类工作台 / Gemini CLI 等）的 skill：**一次只问一个问题、每步落盘、用原文自带的测试当闸门**，带医院——尤其是公立医院——走完「想清楚 → 做出来 → 讲明白」。

> 原文：张琨《听完几十家医院「十五五」规划，我坐立难安！》，公众号「张琨随笔」，2026-11-01
> https://mp.weixin.qq.com/s/qi9F7Jr7mOqa-9ncb7TNzw
>
> 本仓库是对原文方法论的工程化封装，引用原文仅用于方法论说明与教学；原文版权归原作者所有。如原作者对引用方式有异议，请提 issue，我们会调整或移除相关内容。

## 作者与咨询

- 制作：**徐奕高，CPHQ**（美国国家医疗质量协会认证医疗质量专家）
- 咨询电话：**18682053605**
- **不做硬广**：固定开场、每一步、收尾都不带作者信息；只有用户明确露出「烦了 / 做不下去 / 没人手 / 推不动」这类受挫信号时，才给一句软性转介（整个会话最多一次），然后继续帮他做。用户主动问「谁做的 / 怎么联系」时正常回答。

## 为什么做这个

文章的判断是：中国公立医院的战略管理整体仍处初级阶段——**可训练，不可耻**。常见的规划长这样：BSC、BLM、SWOT、PEST 念一遍菜单；讲三上三下写了百万字；讲口号讲决心；PPT 越来越漂亮、字越来越密，**定位、取舍、配称**却说不出来。

AI 恰好能补上执行层的那一段：它擅长追问、结构化、落盘，不擅长替医院做决策。所以这个 skill 的设计目标很克制：

- **话少**：一次只问一个问题，默认 ≤2 句 / ≤60 字；教学每步最多一句原文；
- **一针见血**：答得虚就逼数字、逼科室、逼病种、逼「放弃了什么」；
- **按原文走**：三层十一问，顺序不换，每条都有原文自带的测试当闸门；
- **重活 Agent 干**：底稿、战略一张图、四维结果表、四段汇报、一页纸、体检表都自动落盘。

## 它长什么样

三层十一问（原文顺序）：

| 层 | 步 | 你要回答的核心问题 | 过关闸门（原文自带的测试） |
|---|---|---|---|
| 想清楚 | 1 市场与竞争 | 方圆百公里，谁在抢你的病人、人才、医保额度？ | 三对手+强弱科；外转痛点；**未来五年明确不做什么 ≥3 条** |
| 想清楚 | 2 挑战 | 哪三条问题让你们睡不着？ | 每条带数字/待补、点到科室病种；让院长皱眉 |
| 想清楚 | 3 选题 | 未来五年最想押注的那件事是什么？ | 把院名遮住，别人还认得出是你 |
| 想清楚 | 4 逻辑链 | 最重要的目标用哪个指标量？ | 目标→指标→举措→责任人→基线→目标值→复盘 九栏不空 + 预测模型 |
| 想清楚 | 5 工具 | 这份规划要解决的三个业务问题是什么？ | 删掉 BSC/BLM/SWOT，业务目标还在 |
| 做出来 | 6 配称 | 床位、手术室、设备、绩效往哪倾斜？ | 战略一张图五层+不做什么；科主任三句话测试**说不出不进下一步** |
| 做出来 | 7 结果对照表 | 这套治理用哪四个维度证明有效？ | 四维（业务增长/财务经营/质量安全/健康结果）各有指标+基线+现状 |
| 讲明白 | 8 四段汇报 | 你们放弃了什么？ | 四段齐全；结果段有真实数字；第三+第四段≥一半 |
| 讲明白 | 9 谁来讲 | 谁上台讲？ | 书记/院长/分管领导；20 分钟+10 到 15 分钟答辩 |
| 讲明白 | 10 一页纸 | 整份战略一页纸讲得完吗？ | 一页一个观点；标题写结论句 |
| 讲明白 | 11 通用叙事 | 要不要用国际通用语言再讲一遍？ | DRG/DIP↔价值医疗、医联体↔IDS、分级诊疗↔人群健康 + 国际可比指标 |

另有一页「体检模式」：贴一版现成规划稿，直接出 11 行体检表 + 最疼 3 条。

## 安装

**方式一：Agent Skills（DSH / Claude Code 等）**

```powershell
# DSH
Copy-Item -Recurse hospital-strategy-planning "$env:USERPROFILE\.dsh\skills\"
# Claude Code（用户级）
Copy-Item -Recurse hospital-strategy-planning "$env:USERPROFILE\.claude\skills\"
```

**方式二：只有系统提示词的 harness（WorkBuddy 类工作台 / 自定义 GPT）**

把 [`agents/system-prompt.md`](hospital-strategy-planning/agents/system-prompt.md) 全文粘进系统提示词即可，它不依赖文件读取。

**方式三：OpenAI / Codex 风格 agent**

用 [`agents/openai.yaml`](hospital-strategy-planning/agents/openai.yaml) 作接口配置，正文仍用 `system-prompt.md`。

**方式四：Gemini CLI**

```powershell
Copy-Item hospital-strategy-planning\agents\gemini.toml "$env:USERPROFILE\.gemini\commands\hospital-strategy.toml"
```

之后输入 `/hospital-strategy`。

触发词：医院战略规划、发展规划、五年规划、十五五规划、公立医院战略管理、医院集团/医联体战略、战略地图、战略解码、一页纸战略、规划报告/编制/修改/评审/审稿、战略汇报/答辩、学科/病种/资源投入取舍、国考与等级评审。

## 怎么用

```
> 我们医院要做十五五规划，从零开始。
> 这是我们院的规划稿，帮我看看。
> 下周要答辩，帮我压成 20 分钟。
> 这个学科明年还投不投？
```

产出会落成文件：`规划底稿.md`、`战略一张图.md`、`汇报稿.md`、`体检报告.md`、`STATE.md`（断点续跑）。

## 校验：原文逻辑真的会被稳定触发吗

这个仓库的重点不只是提示词，还有**可自动运行的校验**：

| 层 | 做什么 | 结果 |
|---|---|---|
| 原文对照 | 未看过草稿的审校者先从原文独立提炼基准（11 条逐字标题/关键句/必测动作/20 条逐字锚点），再审 skill | 初版 11 条 **0 缺失、18/22**，挑出 7 个偷懒漏洞与 7 处引文失真 → 全部修复；终版复核为「可交付、11 条动作/测试/停止条件无退化」 |
| 触发矩阵 | [`evals/trigger-matrix.json`](hospital-strategy-planning/evals/trigger-matrix.json)：11 条 × 探针 / 闸门 / 反例 | 自测：好样例 exit 0（11/11），坏样例 exit 1 并点名「缺 P05 / 开场超长 / 乱序 P09」 |
| 自演对练 | 4 个场景整段对话（从零 / 体检改稿 / 阻抗型 / 续跑），用 [`check_transcript.py`](hospital-strategy-planning/evals/check_transcript.py) 自动判 | **4/4 场景 11/11，0 critical，0 warning**（[汇总](docs/sim/自演对练汇总.md)） |
| 真实交互冒烟 | fresh 执行者只读 skill，真人扮演没耐心院长逐条对话 | 开场逐字照模板、一次一问、拒整篇生成、真实落盘；暴露的 2 个问题已在终版修复（[记录](docs/sim/真实交互冒烟.md)） |

复跑：

```powershell
cd hospital-strategy-planning/evals
python check_transcript.py selftest/good.json   # exit 0
python check_transcript.py selftest/bad.json    # exit 1，点名 缺 P05 / 开场超长 / 乱序
```

完整校验过程见 [验收报告](docs/验收报告.md)、[独立审校](docs/audit/01-skill-audit.md)、[终版复核](docs/audit/02-final-recheck.md)。

## 仓库结构

```
hospital-strategy-planning/    # 可安装的 skill 本体
  SKILL.md                     # 主文件：铁律、入口、11 步索引、闸门、自检
  references/
    canon.md                   # 原文标尺：三层十一条、逐字原话、必测动作
    steps.md                   # 每步问句/逼问/闸门/反例/落盘字段
    artifacts.md               # 底稿/两张图/逻辑链/战略一张图/四维表/四段汇报/一页纸/体检表
  agents/                      # 多 harness 打包（system-prompt / openai.yaml / gemini.toml）
  evals/                       # 触发矩阵 + 检查器 + 场景 + 自测样例
docs/                          # 校验证据（审校、对练、冒烟、验收报告）
```

## 边界与已知限制

- 战略由医院决策者拍板，skill 只负责追问、结构化、落盘。
- **不编数字**：缺数据一律标【待补】+谁补。
- 自演对练是模拟会话；完整验证集中在「从零起草 + 体检改稿」两条主路径，评审/答辩打磨/单点取舍三个入口做了规则与路由，未做完整会话对练。
- 引用原文时请注明作者与文章；本仓库不包含原文全文，仅引用方法论要点。

## 致谢与许可

- 方法论与原文引用：张琨《听完几十家医院「十五五」规划，我坐立难安！》（公众号「张琨随笔」）
- 代码与 skill 文本：[MIT License](LICENSE)
- 原文版权归原作者；引用部分的版权不因本仓库的 MIT 许可而改变。

---

**English (short):** A portable agent skill that walks hospitals through strategic planning, following Zhang Kun's 11 recommendations (think clearly → make it happen → tell it clearly). It asks one question at a time, keeps replies under ~60 characters, writes artifacts to disk, and gates each step on the article's own tests (e.g. "what will you explicitly NOT do?", "can a department head explain it in three sentences?"). Includes an automated trigger matrix and checker proving the 11 recommendations fire reliably.
