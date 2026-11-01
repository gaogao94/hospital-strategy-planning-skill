# evals —— 「医院战略规划」skill 的校验工具包

这个目录用来回答一个问题：**张琨原文的十一条建议，在 skill 真实跑起来的时候，是不是真的被触发、按序推进、落了盘，而不是只写在提示词里？**

工具包由三部分组成：

1. `trigger-matrix.json`：11 个触发点（P01–P11）+ 输出纪律阈值 + 全局禁止项。每条含 `required_probes`（探针）、`gate`（产物关键词）、`anti_patterns`（反例）。
2. `check_transcript.py`：读一份模拟会话 transcript，做 A–E 五类检查，输出 `report.json` + `report.md`，用退出码表达通过 / 不通过。
3. `scenarios.json` + `selftest/`：3 个模拟场景定义 + 4 份自测样例（good / bad / 无步骤标记 / 体检模式）。

只用 Python 标准库，无需安装任何第三方包。

---

## 快速开始

```powershell
cd "D:\阅读\医院战略规划skill\hospital-strategy-planning\evals"

# 本机 Python（标准库即可；Python ≥ 3.10，本机 3.12 已验证）
$PY = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

# 1) 自测：good 应通过（exit 0）
& $PY check_transcript.py selftest/good.json --json selftest/good.report.json

# 2) 自测：bad 应不通过（exit 1），并点名「缺 P05 / 开场超长 / 乱序」
& $PY check_transcript.py selftest/bad.json --json selftest/bad.report.json

# 3) 容错自测：去掉步骤标记，仍应按探针顺序对齐并通过（exit 0）
& $PY check_transcript.py selftest/good-nomarkers.json --json selftest/good-nomarkers.report.json

# 4) 体检模式自测：11 行体检表同一轮命中，gate 豁免（exit 0）
& $PY check_transcript.py selftest/review.json --json selftest/review.report.json

# 5) 校验真实模拟会话
& $PY check_transcript.py ..\..\sim\transcripts\s1.json --json ..\..\sim\reports\s1.check.json
```

`--json` 省略时，报告默认写到 transcript 同目录的 `report.json` / `report.md`。建议每次都显式给 `--json`，避免多次运行互相覆盖。

退出码：**0 = 通过**（11/11 且 critical 违规为 0）；**1 = 不通过**；**2 = 输入 / 矩阵配置错误**。

其他参数：`--matrix PATH` 指定矩阵；`--md PATH` 指定 md 报告；`--strict` 让 warning 也阻断；`--quiet` 只写报告不打印摘要。

---

## 输入格式

```json
{
  "meta": {"mode": "coach", "scenario": "S1", "description": "从零起草"},
  "turns": [
    {"role": "user", "text": "……"},
    {"role": "assistant", "text": "……"}
  ]
}
```

- `role`：`assistant` / `user` / `system`；检查只看 assistant 文本。
- `meta.mode`：
  - `coach`（缺省）：从零起草 / 改稿，按步骤逐轮推进；
  - `review`：体检 / 审稿模式，11 行体检表允许**同一轮**命中多个点，且豁免 gate 落盘检查。
- **轮次编号从 0 开始**，对应 `turns` 数组下标；报告里的「轮 N」都是这个编号。
- 会话约定（与 SKILL.md 一致，便于对齐）：
  - assistant 每轮带进度前缀 `【第N步/11·关键词】`（没有也能查，会自动按探针贪心对齐）；
  - 产物（表格 / 战略一张图 / 底稿节）用 ``` 围栏，或以 `【落盘】`、`产出：` 开头；
  - 每步落盘后正文只回一句 `已落盘：规划底稿.md §N`。

---

## 检查项与分级

| 代码 | 检查 | 口径 | 级别 |
|---|---|---|---|
| `STEP_MISSING` | 缺某一步 | 该步 `required_probes` 未全部命中 | critical |
| `STEP_OUT_OF_ORDER` | 乱序 | 后一步的命中轮早于前一步（原文顺序不可换） | critical |
| `OPENING_TOO_LONG` | 开场超长 | 第一条 assistant 轮正文 > 80 汉字 | critical |
| `OPENING_NO_QUESTION` | 开场无问号 | 开场没有问句（应一次一问收尾） | critical |
| `TURN_TOO_LONG` | 单轮正文超 120 字 | 普通轮剔除产物块后 > 120 汉字 | critical |
| `TOO_MANY_QUESTIONS` | 每轮问号 > 2 | 全轮文本（含产物块）问号数 > 2 | critical |
| `EXPLANATION_TOO_LONG` | 讲解超 1 句 | 单轮含「为什么 / 依据 / 原因 / 理由」的解释句 > 1 | warning |
| `TOO_MANY_BULLETS` | 项目符号 > 3 项 | 正文（剔除产物块）bullet 数 > 3 | warning |
| `BANNED_PHRASE` | 禁语 | 「作为一个 AI」「首先，让我们」「接下来我将」「综上所述」「希望以上对你有帮助」等 | critical |
| `TOOL_MENU_BEFORE_P05` | 工具菜单 | P05 之前 assistant 把 ≥2 个管理工具（BSC/BLM/7S/SWOT/PEST）当菜单罗列 | critical |
| `EMPTY_CHALLENGE` | 空泛挑战定稿 | 把「人才梯队有待加强」「信息化水平有待提升」当挑战写（非否定 / 非引用语境） | critical |
| `ANTI_PATTERN` | 反例命中 | 命中某一步 `anti_patterns` 且不在否定 / 引号语境 | warning |
| `INVENTED_NUMBER` | 编数字 | assistant 出现带单位（%/万/亿/元/人/例/张/床…）的数字，用户从未提供 | warning |
| `GATE_NOT_LANDED` | gate 未落盘 | 该步触发后，产物关键词没在该步区间或其后 2 轮内出现 | warning |

**字数阈值与 skill 铁律对齐**：skill 里写的是「默认 ≤2 句 / ≤60 字，硬上限 120 字（不含产物块）」，所以检查器按**硬上限 120 汉字**判 critical，60 字只作软目标、不判违规；开场额外要求 **≤80 汉字且含问号**。阈值集中在 `trigger-matrix.json` 的 `checker` 段，可改。

**critical / warning 的区别**：critical 影响退出码（不通过），warning 只提示质量瑕疵、不阻断；加 `--strict` 后 warning 也阻断。报告里两类分别列出。

```text
严重级别汇总
├─ critical：缺探针、乱序、开场超长/无问号、单轮正文 >120 字、问号 >2、禁语、工具菜单、空泛挑战
└─ warning ：讲解超 1 句、项目符号 >3、反例命中、编数字、gate 未落盘
```

---

## 触发矩阵（11 条建议）

矩阵字段：

- `required_probes`：**正则数组，全部命中**才算该步触发。允许 `|` 表示「或」，如 `"对手|竞争"`。
- `gate`：该步产物关键词正则。该步落位区间内、或落位轮后 2 轮内出现即算「落盘」；否则 warning——用来抓「嘴上说了、但原文逻辑没真正落地」。
- `anti_patterns`：反例正则。命中且不在否定 / 引号语境（±30 字内有「不、别、避免、反例、应改为、只说、套话……」或整段被「」引号包住）才计 warning，避免误伤「不要写××」这类纠偏表述。
- `signature`：一句话说明该步在验什么。

| 步 | 层 | 原文标题 | gate（产物关键词） |
|---|---|---|---|
| P01 | 想清楚 | 先看市场需求和竞争对手，再谈自身特色 | `目标市场人群痛点` / `竞争格局` / `两张图` |
| P02 | 想清楚 | 直面挑战，别只罗列优势 | `挑战清单` / `挑战表` / `§2` |
| P03 | 想清楚 | 选题不能太大，也不能太小 | `选题[:：]` / `§3` / `遮住院名` |
| P04 | 想清楚 | 把逻辑链做实：指标、举措、结果 | `逻辑链` / `九栏` / `§4` |
| P05 | 想清楚 | 管理工具服务业务目标，不能反过来 | `业务目标` / `工具与业务目标` / `§5` |
| P06 | 做出来 | 规划编制是基本功，关键是把资源和绩效「配称」上去 | `战略一张图` / `五层` |
| P07 | 做出来 | 治理创新要落到业务结果上 | `四维` / `结果对照表` / `§7` |
| P08 | 讲明白 | 用经营汇报替代表决心汇报 | `四段` / `§8` / `汇报稿` |
| P09 | 讲明白 | 让深度思考过、作出艰难决策的人来讲 | `答辩` / `汇报人` / `§9` |
| P10 | 讲明白 | AI 时代，少写一点 | `一页纸` / `§10` |
| P11 | 讲明白 | 用通用叙事方法讲中国特色 | `通用叙事` / `价值医疗` / `§11` |

> 表里 P05 的 gate 实际值是 `业务目标|工具与业务目标|§\s*5`，以 `trigger-matrix.json` 为准。

探针设计原则（改矩阵时注意）：

- 每步 3–7 个探针；探针太多容易误判，太少区分度不够；
- 优先用**原文自带的测试词**：不做什么、外转/CMI/DRG、遮住院名、九栏、删掉工具、战略一张图、三句话、四维、四段、一半、20 分钟、放弃了什么、一页纸、结论句、价值医疗/IDS/人群健康、国际可比；
- 探针按「同一步区间内全部命中」判定，不是单轮全部命中（coach 模式多轮推进是常态）。

---

## 对齐算法（容错）

**coach 模式**

1. 有步骤标记（`【第2步/11·挑战】`、`P05`、`第5条` 等）：按标记定该步区间（到下一个其它步骤标记前），区间内跑完探针才算触发；
2. 没有步骤标记：从游标起按 P01→P11 做**探针贪心对齐**，哪一轮凑齐全部探针，就落在哪一轮；
3. 某步探针全部出现、但落位早于前序步骤 → 记**乱序**（critical）；探针始终不齐 → 记**缺**（critical），并列出还缺哪几个探针、给原文片段。

**review 模式（`meta.mode="review"`，体检 / 审稿）**

- 11 行体检表通常在同一轮 assistant 文本里，所以不要求逐轮推进，只要求「**后一点命中轮 ≥ 前一点命中轮**」，命中轮允许相同；
- 后一点命中轮 < 前一点 → 仍报**乱序**；
- **gate 落盘检查豁免**（体检表本身就是落盘物），报告里 11 条 gate 标记为「—」。

**轮次与片段**：报告里所有「轮 N」都是 turns 数组下标（从 0 开始）；违规项会附命中处原文片段，方便直接定位。

---

## 自测样例

| 样例 | 用途 | 期望 |
|---|---|---|
| `selftest/good.json` | 从零起草，11 步按序、每步落盘、纪律全过 | exit 0；11/11；0 critical；0 warning |
| `selftest/bad.json` | 开场超长 + 删掉 P05 整块 + P09 提到 P08 之前 | exit 1；critical 3：**缺 P05 / 开场超长 / 乱序** |
| `selftest/good-nomarkers.json` | good 去掉步骤标记 | exit 0；验证「标记缺失时探针贪心对齐」容错 |
| `selftest/review.json` | 体检模式：11 行体检表同一轮命中 | exit 0；mode=review；11 条 gate 全部豁免 |

`selftest/*.report.json` / `*.report.md` 是自测运行留档，可随时用上面命令重新生成。

---

## 如何新增场景

1. 在 `scenarios.json` 的 `scenarios` 数组里加一条：`id / name / mode / persona / user_style / opening_user_line / hidden_facts / pressure_moves / expected_triggers / must_do / must_not_do / success_criteria / failure_modes / expected_summary`。
2. 按场景演一场会话，写成 `{"meta": {"mode": "...", ...}, "turns": [...]}`，存到 `../../sim/transcripts/sN.json`（或 `selftest/` 下做小样例）。
3. 跑 `check_transcript.py`，确认 `expected_summary` 与实际一致；如果探针误判，先改矩阵再重跑全部自测。

**换问法 / 换闸门**：改 `trigger-matrix.json` 的 `required_probes` / `gate` / `anti_patterns`，然后重跑 4 份 selftest，全部符合预期再交。

---

## 已知限制（重要）

- 这是**文本层**的自动校验：只证明「原文十一条在该被提起的地方被提起、按序推进、产物关键词落盘、输出纪律达标」，**不证明**战略内容本身的临床 / 经营正确性——那仍要人审。
- 探针是正则启发式：可能漏判（skill 换了完全不同的说法）也可能误判（无关文本恰好包含关键词）。漏判 / 误判都优先通过改矩阵解决，不要在 checker 里加特例。
- 反例 / 空泛挑战会做「否定 / 引号语境豁免」，仍然可能误伤或漏放；它们中只有工具菜单和空泛挑战是 critical，其余反例是 warning。
- 编数字检查只认**阿拉伯数字 + 单位**（% / 万 / 亿 / 元 / 人 / 例 / 张 / 床…）且要求用户从未提供过；中文数字（「一百二十万」）不解析，引用原文数据也算 warning（如确属引用，可在 transcript 里由用户先给出该数字）。
- 产物块必须用 ``` 围栏，或以 `【落盘】` / `产出：` / `战略一张图` 开头；没有围栏、也没有前缀的多行产物会被当成正文计入字数。
- `review` 模式默认「体检表即落盘物」，所以豁免 gate；如果体检模式仍要求逐条落盘，请用 `coach` 模式跑。

---

## 实测记录（2026-11-01）

| 对象 | 模式 | 结果 |
|---|---|---|
| `selftest/good.json` | coach | exit 0，11/11，critical 0，warning 0 |
| `selftest/bad.json` | coach | exit 1，critical 3（缺 P05 / 开场超长 162 汉字 / P09 乱序） |
| `selftest/good-nomarkers.json` | coach（无标记） | exit 0，11/11，critical 0 |
| `selftest/review.json` | review | exit 0，11/11，gate 11 条豁免 |
| `sim/transcripts/s1.json`（三甲从零） | coach | exit 0，11/11，gate 11/11 落盘 |
| `sim/transcripts/s2.json`（县级审稿） | review | exit 0，11/11，gate 11 条豁免 |
| `sim/transcripts/s3.json`（阻抗型） | coach | exit 0，11/11，gate 11/11 落盘 |
| `sim/transcripts/s4.json`（续跑） | coach | exit 0，11/11，gate 11/11 落盘 |

负面路径也测过：单轮正文超 120 字、禁语、编数字（warning，`--strict` 下阻断）、gate 缺失、体检模式乱序、坏 JSON / 无 assistant 轮（exit 2），均按预期报出。
