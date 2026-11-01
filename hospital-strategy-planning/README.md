# 医院战略规划教练（hospital-strategy-planning）

一个「装进 Agent harness 就能用」的医院战略规划引导 skill：引导医院——尤其是公立医院——按张琨《听完几十家医院「十五五」规划，我坐立难安！》的**十一条建议**，一步一步走完战略规划（或体检已有规划稿）。

它解决三个问题：

1. **不跑偏**：顺序严格按原文三层——想清楚（1–5）、做出来（6–7）、讲明白（8–11），每一步都有原文自带的「自检测试」当闸门（遮住院名、删掉 BSC/SWOT、科主任三句话、四段汇报三四段占一半……）。
2. **不说废话**：用户通常没耐心看长文。铁律是「一次只问一个问题、每轮 ≤2 句 / ≤60 字」，重活（底稿、表格、一张图）由 Agent 干，教学每步最多一句原文。
3. **可校验**：自带校验工具（`evals/`），用触发矩阵 + 输出纪律检查器证明原文十一条在真实会话中被稳定触发，而不是只在提示词里写着。

## 依据

- 原文：张琨《听完几十家医院「十五五」规划，我坐立难安！》，公众号「张琨随笔」，2026-11-01。
- 链接：https://mp.weixin.qq.com/s/qi9F7Jr7mOqa-9ncb7TNzw
- 原文要点、11 条逐字标题与关键原话已落到 `references/canon.md`（摘要行单独标注），作为本 skill 的验收标尺。

## 目录

```
SKILL.md                    # 主文件：铁律、11 步索引、模式、自检
references/
  canon.md                  # 原文标尺：三层十一条、逐字原话、必测动作、反例
  steps.md                  # 每一步的问句、逼问话术、闸门、反例、落盘字段
  artifacts.md              # 底稿/两张图/逻辑链/战略一张图/四维表/四段汇报/一页纸/体检表模板
evals/
  trigger-matrix.json       # 11 个触发点 + 输出纪律规则（校验标准）
  check_transcript.py       # 会话检查器（覆盖/顺序/字数/禁语/编数字）
  scenarios.json            # 3 个模拟场景
  selftest/                 # 自测样例（good 通过 / bad 报错 / review 体检模式）
agents/
  system-prompt.md          # 扁平版：粘贴到任何只有系统提示词的 harness
  openai.yaml               # OpenAI/Codex 风格 agent 配置
  gemini.toml               # Gemini CLI 自定义命令（由 build_gemini.py 生成）
  build_gemini.py           # 从 system-prompt.md 重新生成 gemini.toml
README.md
```

## 安装

### 1) DSH / Claude Code / 其他支持 Agent Skills 的 harness

把整个目录复制到用户级 skills 目录：

```powershell
# DSH
Copy-Item -Recurse hospital-strategy-planning "$env:USERPROFILE\.dsh\skills\"
# Claude Code（用户级）
Copy-Item -Recurse hospital-strategy-planning "$env:USERPROFILE\.claude\skills\"
```

触发词（描述里已写）：`医院战略规划`、`发展规划`、`五年规划`、`十五五规划`、`公立医院战略管理`、`医院集团/医联体战略`、`战略地图`、`战略解码`、`一页纸战略`、`战略规划报告/编制/修改/评审/审稿`、`战略汇报/答辩`、`学科/病种/资源投入取舍`、`国考与等级评审`。
也可以直接点名调用，例如「用 hospital-strategy-planning 带我过一遍战略规划」。

### 2) WorkBuddy 类工作台 / 自定义 GPT / 任何只有系统提示词的 harness

把 `agents/system-prompt.md` 全文粘进系统提示词（或角色设定）。它不依赖文件读取，自带 11 步问句、闸门和对话内底稿规则。

### 3) OpenAI / Codex 风格 agent

用 `agents/openai.yaml` 作为 agent 接口配置，正文仍用 `agents/system-prompt.md`。

### 4) Gemini CLI

```powershell
Copy-Item agents\gemini.toml "$env:USERPROFILE\.gemini\commands\hospital-strategy.toml"
```

之后输入 `/hospital-strategy`。`gemini.toml` 由 `agents/system-prompt.md` 生成，改了源文件请重新运行 `python agents/build_gemini.py`。

## 怎么用

- **从零起草**：「我们医院要做十五五规划，从零开始。」→ 11 步走完，产出 `规划底稿.md`、`战略一张图.md`、`汇报稿.md`。
- **体检已有稿**：「这是我们院的规划稿，帮我看看。」→ 11 行体检表 + 最疼 3 条 + 「先改哪条？」→ 选修稿或重写。
- **评审/听汇报**：「帮我评一下这份规划汇报。」→ 只出体检表和最疼 3 条，不接管写作。
- **答辩前打磨**：「下周要答辩，帮我压成 20 分钟。」→ 直接走第 8–10 步，缺配称先补第 6–7 步。
- **单点取舍**：「这个学科明年还投不投？」→ 只走第 1–3 步 + 第 6 步对应格。
- **断点续跑**：工作目录有 `STATE.md`/`规划底稿.md` 时，直接说「继续」。

预期体感：每次回复一两句话、一个问题；每步结尾一句「已落盘：…」；数字缺了就写【待补】，绝不编。

## 校验（为什么说原文逻辑会被触发）

```
cd evals
python check_transcript.py selftest/good.json   # 应 exit 0
python check_transcript.py selftest/bad.json    # 应 exit 1 并点名缺 P05 / 开场超长 / 乱序
python check_transcript.py <你的会话.json>
```

检查器做四类判断：

- **覆盖与顺序**：P01→P11 的探针必须按原文顺序出现（如 P01 必须问到「对手/外转/不做什么」；P09 必须落到「书记院长 + 20 分钟 + 答辩」）；体检模式（`meta.mode=review`）允许 11 行体检表在同一轮命中。
- **输出纪律**：开场 ≤80 字；普通对话轮 ≤120 字；每轮 ≤2 个问号；正文 ≤3 个 bullet。
- **禁语与反例**：工具菜单式开场、把「人才梯队有待加强」当挑战定稿、AI 套话；步内闸门产物是否真落盘（gate 关键词）。
- **编数字预警**：Agent 给出用户从未提供的数字。

模拟会话记录在 `../sim/transcripts/`（由独立自演对练生成，含 coach/review/阻抗/续跑四种），验收报告见 `../验收报告.md`。

## 自定义

- 换问法：改 `references/steps.md`（每个问句都可换说法，但保持「一次一问」）。
- 换闸门/加字：改 `evals/trigger-matrix.json`，再跑检查器。
- 适配不同 harness：改 `agents/system-prompt.md`，必要时重跑 `agents/build_gemini.py`。

## 边界

- 战略由医院决策者拍板，skill 只负责逼问、结构化、落盘。
- 不编造任何医院数据；判断以用户提供的事实为准。
- 引用原文时注明作者与文章；本 skill 是对原文方法论的工程化封装。
