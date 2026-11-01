#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_transcript.py — 「医院战略规划」skill 会话校验器（纯标准库）。

用途
----
输入一份模拟会话 transcript（JSON），对照 ``trigger-matrix.json`` 做五类检查：

  A. 覆盖与顺序：P01→P11 十一条建议的触发探针是否按原文顺序全部命中；
  B. 输出纪律：开场 ≤80 汉字且含问号（不含作者信息）、普通轮正文 ≤120 汉字、每轮 ≤2 个问号、
     单轮「为什么/依据」讲解 ≤1 句、正文项目符号 ≤3 项；
  C. 禁语与反例：AI 套话、P05 之前把管理工具当菜单罗列、把空泛话当挑战定稿、
     各步反例句式；
  D. 编数字预警：assistant 给出用户从未提供过的带单位数字；
  E. gate 落盘：每步命中后，该步产物关键词是否在同一区间或其后 2 轮内出现。

用法
----
    python check_transcript.py <transcript.json> [--matrix PATH]
                               [--json report.json] [--md report.md]
                               [--strict] [--quiet]

退出码：0=通过（11/11 且无 critical 违规；--strict 时 warning 也不允许）；1=不通过；2=输入/配置错误。

transcript 格式::

    {"meta": {...},
     "turns": [{"role": "user"|"assistant", "text": "..."}]}

轮次（turn）下标从 0 开始，对应 turns 数组下标。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

CHECKER_VERSION = "1.0.0"
DEFAULT_MATRIX = Path(__file__).resolve().parent / "trigger-matrix.json"

# --------------------------------------------------------------------------
# 严重级别：critical 影响退出码，warning 只提示（--strict 时也影响）
# --------------------------------------------------------------------------
SEVERITY = {
    # A 覆盖与顺序
    "STEP_MISSING": "critical",
    "STEP_OUT_OF_ORDER": "critical",
    # B 输出纪律
    "OPENING_TOO_LONG": "critical",
    "OPENING_NO_QUESTION": "critical",
    "TURN_TOO_LONG": "critical",
    "TOO_MANY_QUESTIONS": "critical",
    "EXPLANATION_TOO_LONG": "warning",
    "TOO_MANY_BULLETS": "warning",
    # C 禁语与反例
    "BANNED_PHRASE": "critical",
    "TOOL_MENU_BEFORE_P05": "critical",
    "EMPTY_CHALLENGE": "critical",
    "ANTI_PATTERN": "warning",
    # D 编数字
    "INVENTED_NUMBER": "warning",
    # E gate 落盘
    "GATE_NOT_LANDED": "warning",
}

RULE_LABEL = {
    "STEP_MISSING": "缺",
    "STEP_OUT_OF_ORDER": "乱序",
    "OPENING_TOO_LONG": "开场超长",
    "OPENING_NO_QUESTION": "开场无问号",
    "TURN_TOO_LONG": "单轮正文超 120 字",
    "TOO_MANY_QUESTIONS": "每轮问号 > 2",
    "EXPLANATION_TOO_LONG": "单轮「为什么/依据」讲解 > 1 句",
    "TOO_MANY_BULLETS": "正文项目符号 > 3 项",
    "BANNED_PHRASE": "禁语",
    "TOOL_MENU_BEFORE_P05": "P05 之前把管理工具当推荐菜单罗列",
    "EMPTY_CHALLENGE": "把空泛话当挑战定稿",
    "ANTI_PATTERN": "反例命中",
    "INVENTED_NUMBER": "编数字预警",
    "GATE_NOT_LANDED": "gate 未落盘",
}

# --------------------------------------------------------------------------
# 正则 / 常量
# --------------------------------------------------------------------------
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
QUESTION_RE = re.compile(r"[？?]")
FENCE_RE = re.compile(r"```[\s\S]*?(?:```|$)")
TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
BULLET_RE = re.compile(
    r"^(?:[-*+•·]\s+|\d+[.、)）]\s*|[（(]\d+[)）]\s*"
    r"|[一二三四五六七八九十]+[、.]\s*|[①②③④⑤⑥⑦⑧⑨⑩]\s*)"
)
SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
EXPLAIN_CUE_RE = re.compile(r"依据|原因|理由|因为|之所以|是因为|为什么")
NEG_CUE_RE = re.compile(
    r"不|没|别|勿|避免|防止|反例|警惕|禁|忌|而非|不是|替代|代替|少|拒|莫|戒|"
    r"无需|不必|错误|哪家医院都能用|哪家都成立|都成立|放之四海|等于没写|换个说法|"
    r"只说|空话|套话|空泛|打回|不合格|太虚|泛泛|没写|一笔带过|应改为|应该|建议|改为"
)
# 带单位数字：用于「编数字」检查（只认 % / 金额 / 人数量级，避免把「20 分钟」算成数据）
NUM_CLAIM_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(%|％|万人次|人次|人|例|名|位|张|床|万元|亿元|万|亿|元)"
)
NUM_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


class ConfigError(Exception):
    """矩阵 / 输入配置错误。"""


class InputError(Exception):
    """transcript 结构错误。"""


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def force_utf8_stdio() -> None:
    """Windows 控制台默认 GBK，重定向输出时避免 UnicodeEncodeError。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def count_cjk(text: str) -> int:
    return len(CJK_RE.findall(text))


def strip_body(text: str, strip_cfg: dict) -> str:
    """返回「普通对话正文」：剔除代码块、表格行、产物块后的剩余文本。"""
    cfg = strip_cfg or {}
    content = text
    if cfg.get("code_fences", True):
        content = FENCE_RE.sub(" ", content)
    prefixes = tuple(cfg.get("block_prefixes") or ())
    out_lines: list[str] = []
    skipping_block = False
    for raw in content.splitlines():
        stripped = raw.strip()
        if cfg.get("table_lines", True) and TABLE_LINE_RE.match(raw):
            continue
        # 允许产物块以 Markdown 标题形式出现，如「# 战略一张图 v1」
        normalized = re.sub(r"^[#>*+\-\s]+", "", stripped)
        if prefixes and normalized.startswith(prefixes):
            skipping_block = True
            continue
        if skipping_block:
            if stripped == "":
                skipping_block = False
            continue
        out_lines.append(raw)
    return "\n".join(out_lines)


def count_question_marks(text: str) -> int:
    return len(QUESTION_RE.findall(text))


def count_bullets(body: str) -> int:
    total = 0
    for raw in body.splitlines():
        line = raw.strip()
        if line and BULLET_RE.match(line):
            total += 1
    return total


def explanation_sentences(body: str) -> list[str]:
    """找出含「为什么/依据/原因/理由…」的解释句（启发式，至少 6 个汉字）。"""
    found: list[str] = []
    for part in SENTENCE_SPLIT_RE.split(body):
        part = part.strip()
        if not part:
            continue
        if EXPLAIN_CUE_RE.search(part) and count_cjk(part) >= 6:
            found.append(part)
    return found


def inside_quote(text: str, start: int, end: int) -> bool:
    """match 是否被成对引号包住（中文引号 / 中文双单引号 / 英文双引号近似判断）。"""
    for open_ch, close_ch in (("「", "」"), ("『", "』"), ("“", "”"), ("‘", "’")):
        last_open = text.rfind(open_ch, 0, start)
        if last_open == -1:
            continue
        last_close = text.rfind(close_ch, 0, start)
        if last_open > last_close and text.find(close_ch, end) != -1:
            return True
    # 英文双引号：按出现次数奇偶近似
    if text.count('"', 0, start) % 2 == 1 and text.find('"', end) != -1:
        return True
    return False


def is_exempted(text: str, start: int, end: int, window: int = 30) -> bool:
    """反例 / 空泛挑战命中时，若处于引号内或 ±window 字内出现否定、纠偏线索则豁免。"""
    if inside_quote(text, start, end):
        return True
    context = text[max(0, start - window): min(len(text), end + window)]
    return bool(NEG_CUE_RE.search(context))


def snippet(text: str, start: int, end: int, pad: int = 14, limit: int = 56) -> str:
    left = max(0, start - pad)
    right = min(len(text), end + pad)
    frag = text[left:right].replace("\r", " ").replace("\n", " ").strip()
    if len(frag) > limit:
        frag = frag[: limit - 1] + "…"
    return frag


# --------------------------------------------------------------------------
# 载入
# --------------------------------------------------------------------------
def load_json(path: Path, what: str) -> dict:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ConfigError(f"{what}不存在：{path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{what}不是合法 JSON：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{what}顶层必须是 JSON 对象：{path}")
    return data


def load_transcript(path: Path) -> tuple[list[dict], dict]:
    """返回 (规范化 turns, transcript meta)。"""
    data = load_json(path, "transcript")
    raw_turns = data.get("turns")
    if not isinstance(raw_turns, list) or not raw_turns:
        raise InputError(f"transcript 缺少非空 turns 数组：{path}")
    normalized: list[dict] = []
    for idx, turn in enumerate(raw_turns):
        if not isinstance(turn, dict):
            raise InputError(f"turns[{idx}] 不是对象")
        role = turn.get("role")
        if role not in ("assistant", "user", "system"):
            raise InputError(f"turns[{idx}].role 必须是 assistant/user/system，实际 {role!r}")
        text = turn.get("text")
        if text is None:
            text = turn.get("content")
        if not isinstance(text, str):
            raise InputError(f"turns[{idx}].text 必须是字符串")
        normalized.append({"role": role, "text": text})
    if not any(t["role"] == "assistant" for t in normalized):
        raise InputError("transcript 里没有 assistant 轮，无法校验")
    meta = data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    else:
        meta = dict(meta)
    # 兼容把 mode 写在顶层的写法
    for key in ("mode", "scenario", "path"):
        if key not in meta and key in data:
            meta[key] = data[key]
    return normalized, meta


def detect_mode(meta: dict) -> str:
    """coach=从零/改稿逐轮推进（默认）；review=体检/审稿（11 行体检表同轮命中）。"""
    mode = str(meta.get("mode", "") or "").strip().lower()
    if mode in ("review", "review_mode", "体检", "审稿", "评审", "fitcheck", "fit_check"):
        return "review"
    return "coach"


def load_matrix(path: Path) -> dict:
    matrix = load_json(path, "trigger-matrix")
    steps = matrix.get("steps")
    if not isinstance(steps, list) or len(steps) != 11:
        raise ConfigError(f"trigger-matrix.steps 必须是 11 条，实际 {type(steps)} / {len(steps) if isinstance(steps, list) else '-'}")
    seen = set()
    for step in steps:
        for field in ("id", "layer", "title", "required_probes", "gate", "signature"):
            if field not in step:
                raise ConfigError(f"步骤 {step.get('id', '?')} 缺少字段 {field}")
        if step["id"] in seen:
            raise ConfigError(f"步骤 id 重复：{step['id']}")
        seen.add(step["id"])
        probes = step["required_probes"]
        if not isinstance(probes, list) or not probes or not all(isinstance(p, str) for p in probes):
            raise ConfigError(f"步骤 {step['id']} 的 required_probes 必须是非空字符串数组")
        if not isinstance(step["gate"], str) or not step["gate"]:
            raise ConfigError(f"步骤 {step['id']} 的 gate 必须是正则字符串")
    matrix.setdefault("checker", {})
    matrix.setdefault("global_rules", {})
    return matrix


# --------------------------------------------------------------------------
# 探针与步骤对齐
# --------------------------------------------------------------------------
def compile_step(payload: dict) -> dict:
    sid = payload["id"]
    try:
        probes = [re.compile(p) for p in payload["required_probes"]]
        gate = re.compile(payload["gate"])
        antis = [re.compile(p) for p in payload.get("anti_patterns", [])]
    except re.error as exc:
        raise ConfigError(f"步骤 {sid} 的正则无法编译：{exc}") from exc
    return {
        "id": sid,
        "layer": payload["layer"],
        "title": payload["title"],
        "probe_src": list(payload["required_probes"]),
        "probes": probes,
        "gate": gate,
        "gate_src": payload["gate"],
        "antis": antis,
        "anti_src": list(payload.get("anti_patterns", [])),
        "signature": payload["signature"],
    }


def build_markers(turns: list[dict], patterns: list[str]) -> dict[int, set[str]]:
    """识别 assistant 轮里的显式步骤标记，返回 {轮下标: {P01,...}}。"""
    compiled = []
    for pattern in patterns or []:
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            raise ConfigError(f"step_marker_patterns 正则无法编译：{pattern}（{exc}）") from exc
    markers: dict[int, set[str]] = {}
    for idx, turn in enumerate(turns):
        if turn["role"] != "assistant":
            continue
        ids: set[str] = set()
        for regex in compiled:
            for match in regex.finditer(turn["text"]):
                number = next((g for g in match.groups() if g), None)
                if number is None:
                    continue
                try:
                    num = int(number)
                except ValueError:
                    continue
                if 1 <= num <= 11:
                    ids.add(f"P{num:02d}")
        if ids:
            markers[idx] = ids
    return markers


def match_probes(turns: list[dict], steps: list[dict]) -> dict[str, list[list[int]]]:
    """{step_id: [ [命中轮...], ... ]}，探针只匹配 assistant 全文。"""
    assistant = [(idx, turn["text"]) for idx, turn in enumerate(turns) if turn["role"] == "assistant"]
    result: dict[str, list[list[int]]] = {}
    for step in steps:
        per_probe: list[list[int]] = []
        for probe in step["probes"]:
            hits = [idx for idx, text in assistant if probe.search(text)]
            per_probe.append(hits)
        result[step["id"]] = per_probe
    return result


def align_steps(turns: list[dict], steps: list[dict], markers: dict[int, set[str]],
                probe_hits: dict[str, list[list[int]]], cfg: dict,
                mode: str = "coach") -> tuple[list[dict], list[dict]]:
    """按模式对齐 11 步。

    - ``coach``（默认，从零/改稿）：步骤逐步推进；有标记按标记定区间，无标记按探针贪心；
    - ``review``（体检/审稿）：11 行体检表可能同一轮命中多个点，只要求
      「后一点命中轮 >= 前一点命中轮」，命中轮允许相同；乱序仍报。
    """
    if mode == "review":
        return _align_steps_review(turns, steps, probe_hits)
    return _align_steps_coach(turns, steps, markers, probe_hits, cfg)


def _align_steps_review(turns: list[dict], steps: list[dict],
                        probe_hits: dict[str, list[list[int]]]) -> tuple[list[dict], list[dict]]:
    """体检模式对齐：不要求逐轮推进，只要求命中轮单调不减。"""
    assistant_idx = [idx for idx, turn in enumerate(turns) if turn["role"] == "assistant"]
    coverage: list[dict] = []
    order_violations: list[dict] = []
    prev_hit: int | None = None
    prev_sid: str | None = None

    for step in steps:
        sid = step["id"]
        per = probe_hits[sid]
        firsts: list[int | None] = [hits[0] if hits else None for hits in per]
        cov: dict = {
            "id": sid,
            "layer": step["layer"],
            "title": step["title"],
            "signature": step["signature"],
            "triggered": False,
            "position": None,
            "mode": "review",
            "span": None,
            "probe_turns": {},
            "missing_probes": [step["probe_src"][i] for i, hits in enumerate(per) if not hits],
            "declared_turns": [],
        }
        single_turn: int | None = None
        for turn_idx in assistant_idx:
            text = turns[turn_idx]["text"]
            if all(probe.search(text) for probe in step["probes"]):
                single_turn = turn_idx
                break
        if single_turn is not None:
            hit = single_turn
            cov["mode"] = "review"
        elif all(first is not None for first in firsts):
            hit = max(first for first in firsts if first is not None)
            cov["mode"] = "review-cumulative"
        else:
            hit = None
        if hit is None:
            coverage.append(cov)
            continue
        cov["triggered"] = True
        cov["position"] = hit
        cov["span"] = [min(first for first in firsts if first is not None), hit]
        cov["probe_turns"] = {
            step["probe_src"][idx]: first
            for idx, first in enumerate(firsts)
            if first is not None
        }
        if prev_hit is not None and hit < prev_hit:
            cov["mode"] = "out_of_order"
            order_violations.append(
                {
                    "step": sid,
                    "first_hit_turn": hit,
                    "expected_after": prev_hit,
                    "prev_step": prev_sid,
                    "prev_position": prev_hit,
                    "missing_probes": [],
                    "note": "review 模式要求后一点命中轮 >= 前一点命中轮",
                }
            )
        prev_hit = hit
        prev_sid = sid
        coverage.append(cov)
    return coverage, order_violations


def _align_steps_coach(turns: list[dict], steps: list[dict], markers: dict[int, set[str]],
                probe_hits: dict[str, list[list[int]]], cfg: dict) -> tuple[list[dict], list[dict]]:
    """把 11 步对齐到轮次。返回 (coverage, order_violations)。

    规则：
    - 有步骤标记（如「【第2步/11·挑战】」）时按标记定步区间，区间内跑完探针才算触发；
    - 标记缺失时，从游标起按 P01→P11 顺序做探针贪心对齐（容错）；
    - 若某步探针全部出现在前序步骤落位之前 → 记「乱序”。
    """
    turn_count = len(turns)
    assistant_idx = [idx for idx, turn in enumerate(turns) if turn["role"] == "assistant"]
    all_marker_turns = sorted(markers)
    marker_steps: dict[str, list[int]] = {step["id"]: [t for t in all_marker_turns if step["id"] in markers[t]] for step in steps}

    coverage: list[dict] = []
    order_violations: list[dict] = []
    cursor = 0
    prev_placed: dict | None = None

    for step in steps:
        sid = step["id"]
        per = probe_hits[sid]
        triggered_anywhere = all(bool(hits) for hits in per)
        missing_src = [step["probe_src"][i] for i, hits in enumerate(per) if not hits]
        cov: dict = {
            "id": sid,
            "layer": step["layer"],
            "title": step["title"],
            "signature": step["signature"],
            "triggered": False,
            "position": None,
            "mode": None,
            "span": None,
            "probe_turns": {},
            "missing_probes": [step["probe_src"][i] for i, hits in enumerate(per) if not hits],
            "declared_turns": marker_steps.get(sid, []),
        }
        step_markers = [t for t in marker_steps.get(sid, []) if t >= cursor]

        if step_markers:
            start = step_markers[0]
            next_different = [
                t for t in all_marker_turns
                if t > start and any(other != sid for other in markers[t])
            ]
            end = (next_different[0] - 1) if next_different else turn_count - 1
            local: dict[int, int | None] = {}
            for probe_index, hits in enumerate(per):
                candidates = [t for t in hits if start <= t <= end]
                local[probe_index] = candidates[0] if candidates else None
            cov["mode"] = "marker"
            cov["span"] = [start, end]
            cov["declared_turn"] = start
            if all(value is not None for value in local.values()):
                cov["triggered"] = True
                cov["position"] = start
                cov["probe_turns"] = {
                    step["probe_src"][idx]: turn for idx, turn in local.items() if turn is not None
                }
                cursor = end + 1
                prev_placed = {"id": sid, "position": start, "span": [start, end]}
            else:
                unmatched = [step["probe_src"][idx] for idx, turn in local.items() if turn is None]
                cov["missing_probes"] = unmatched
                cov["note"] = f"步骤标记区间 [轮{start}-轮{end}] 内探针未全部命中"
                cursor = max(cursor, end + 1)
                # 标记存在、但探针全在区间外：给出可用信息
                outside_turns = [t for hits in per for t in hits if not (start <= t <= end)]
                if outside_turns and triggered_anywhere:
                    cov["note"] += f"；探针命中在区间外的轮 {sorted(set(outside_turns))[:5]}"
        else:
            # 无可用标记：探针贪心（受下一个其它步骤标记约束）
            later_markers = [t for t in all_marker_turns if t >= cursor]
            other_markers = [t for t in later_markers if not (sid in markers.get(t, set()))]
            boundary = (other_markers[0] - 1) if other_markers else turn_count - 1
            cov["mode"] = "probe"
            if not triggered_anywhere:
                cov["missing_probes"] = missing_src or cov["missing_probes"]
                cov["note"] = "探针在整份 transcript 中未全部命中"
            else:
                firsts: list[int] = []
                for hits in per:
                    candidates = [t for t in hits if cursor <= t <= boundary]
                    firsts.append(candidates[0] if candidates else -1)
                if all(t >= 0 for t in firsts):
                    completed = max(firsts)
                    start = min(firsts)
                    cov["triggered"] = True
                    cov["position"] = completed
                    cov["span"] = [start, completed]
                    cov["probe_turns"] = {
                        step["probe_src"][idx]: turn for idx, turn in enumerate(firsts)
                    }
                    cursor = completed + 1
                    prev_placed = {"id": sid, "position": completed, "span": [start, completed]}
                else:
                    # 探针存在，但都在游标之前（或跨到下一步骤标记之后）
                    independent_completion = max(hits[0] for hits in per if hits)
                    cov["missing_probes"] = [
                        step["probe_src"][idx] for idx, turn in enumerate(firsts) if turn < 0
                    ]
                    if all(t < 0 for t in firsts) and independent_completion < cursor:
                        cov["triggered"] = True
                        cov["mode"] = "out_of_order"
                        cov["note"] = (
                            f"探针在轮 {independent_completion} 已全部出现，"
                            f"但按顺序此时已过位（游标在轮 {cursor}）"
                        )
                        order_violations.append(
                            {
                                "step": sid,
                                "first_hit_turn": independent_completion,
                                "expected_after": (
                                    prev_placed["position"] if prev_placed else -1
                                ),
                                "prev_step": prev_placed["id"] if prev_placed else None,
                                "prev_position": prev_placed["position"] if prev_placed else None,
                                "missing_probes": [],
                            }
                        )
                    else:
                        cov["note"] = "探针命中在游标之前，或落在下一步骤标记之后"
        coverage.append(cov)

    return coverage, order_violations


# --------------------------------------------------------------------------
# 检查 B：输出纪律
# --------------------------------------------------------------------------
def check_discipline(turns: list[dict], cfg: dict) -> tuple[dict, list[dict]]:
    violations: list[dict] = []
    assistant_idx = [idx for idx, turn in enumerate(turns) if turn["role"] == "assistant"]
    opening_idx = assistant_idx[0] if assistant_idx else None
    strip_cfg = cfg.get("body_strip", {})
    opening_limit = int(cfg.get("opening_char_limit", 80))
    body_limit = int(cfg.get("body_char_limit", 120))
    max_questions = int(cfg.get("max_questions_per_turn", 2))
    max_explain = int(cfg.get("max_explain_sentences_per_turn", 1))
    max_bullets = int(cfg.get("max_bullets_per_turn", 3))

    opening: dict = {"turn": opening_idx, "chars": None, "questions": None, "ok": True}
    turn_stats: list[dict] = []

    for idx in assistant_idx:
        text = turns[idx]["text"]
        body = strip_body(text, strip_cfg)
        body_chars = count_cjk(body)
        questions = count_question_marks(text)
        explanation = explanation_sentences(body)
        bullets = count_bullets(body)

        if idx == opening_idx:
            opening.update(
                chars=body_chars,
                questions=questions,
                has_question=questions > 0,
            )
            if body_chars > opening_limit:
                opening["ok"] = False
                violations.append(
                    violation(
                        "OPENING_TOO_LONG",
                        f"开场超长：首条 assistant 轮正文 {body_chars} 汉字 > {opening_limit}",
                        turn=idx,
                        detail=f"开场应 ≤{opening_limit} 汉字且含一个问号；实际 {body_chars} 汉字、{questions} 个问号。",
                        snippet_text=snippet(text, 0, min(len(text), 40)),
                    )
                )
            if cfg.get("opening_requires_question", True) and questions == 0:
                opening["ok"] = False
                violations.append(
                    violation(
                        "OPENING_NO_QUESTION",
                        "开场无问号：首条 assistant 轮没有问句",
                        turn=idx,
                        detail=f"开场应 ≤{opening_limit} 汉字并以一个问题收尾（一次一问）。",
                        snippet_text=snippet(text, 0, min(len(text), 40)),
                    )
                )
            turn_stats.append(
                {
                    "turn": idx,
                    "role": "opening",
                    "body_chars": body_chars,
                    "questions": questions,
                    "explain_sentences": len(explanation),
                    "bullets": bullets,
                    "violations": [],
                }
            )
            continue

        turn_violations: list[str] = []
        if body_chars > body_limit:
            turn_violations.append("TURN_TOO_LONG")
            violations.append(
                violation(
                    "TURN_TOO_LONG",
                    f"单轮正文超 120 字：轮 {idx} 剔除产物块后 {body_chars} 汉字 > {body_limit}",
                    turn=idx,
                    detail="普通对话轮只留一两句；表格、一张图等产物应放进单独产物块。",
                    snippet_text=snippet(body, 0, min(len(body), 40)),
                )
            )
        if questions > max_questions:
            turn_violations.append("TOO_MANY_QUESTIONS")
            violations.append(
                violation(
                    "TOO_MANY_QUESTIONS",
                    f"每轮问号 > 2：轮 {idx} 有 {questions} 个问号",
                    turn=idx,
                    detail="一次只问一个问题（最多两个选项）；问号含产物块内的。",
                    snippet_text=snippet(text, 0, min(len(text), 40)),
                )
            )
        if len(explanation) > max_explain:
            turn_violations.append("EXPLANATION_TOO_LONG")
            violations.append(
                violation(
                    "EXPLANATION_TOO_LONG",
                    f"单轮「为什么/依据」讲解 > 1 句：轮 {idx} 有 {len(explanation)} 句",
                    turn=idx,
                    detail="每步最多引一句原文解释，不展开、不背定义。命中句：" + " / ".join(explanation[:3]),
                    snippet_text=snippet(" / ".join(explanation), 0, min(len(explanation[0]), 40)) if explanation else "",
                )
            )
        if bullets > max_bullets:
            turn_violations.append("TOO_MANY_BULLETS")
            violations.append(
                violation(
                    "TOO_MANY_BULLETS",
                    f"正文项目符号 > 3 项：轮 {idx} 有 {bullets} 项",
                    turn=idx,
                    detail="正文不用长清单；长清单放进产物块。",
                    snippet_text=snippet(body, 0, min(len(body), 40)),
                )
            )
        turn_stats.append(
            {
                "turn": idx,
                "role": "assistant",
                "body_chars": body_chars,
                "questions": questions,
                "explain_sentences": len(explanation),
                "bullets": bullets,
                "violations": turn_violations,
            }
        )

    return {
        "limits": {
            "opening_char_limit": opening_limit,
            "body_char_limit": body_limit,
            "max_questions_per_turn": max_questions,
            "max_explain_sentences_per_turn": max_explain,
            "max_bullets_per_turn": max_bullets,
        },
        "opening": opening,
        "turns": turn_stats,
    }, violations


# --------------------------------------------------------------------------
# 检查 C：禁语与反例
# --------------------------------------------------------------------------
def check_banned_and_anti(turns: list[dict], steps: list[dict], coverage: list[dict],
                          matrix: dict) -> list[dict]:
    violations: list[dict] = []
    global_rules = matrix.get("global_rules", {})

    banned = global_rules.get("banned_phrases", [])
    for idx, turn in enumerate(turns):
        if turn["role"] != "assistant":
            continue
        text = turn["text"]
        for pattern in banned:
            try:
                regex = re.compile(pattern)
            except re.error as exc:
                raise ConfigError(f"global_rules.banned_phrases 正则错误：{pattern}（{exc}）") from exc
            for match in regex.finditer(text):
                violations.append(
                    violation(
                        "BANNED_PHRASE",
                        f"禁语：{match.group(0)[:24]}",
                        turn=idx,
                        detail=f"命中禁语 / AI 套话，规则：{pattern}",
                        snippet_text=snippet(text, match.start(), match.end()),
                    )
                )

    # 空泛挑战（原文点名「人才梯队有待加强」「信息化水平有待提升」当挑战定稿）
    empty_patterns = global_rules.get("empty_challenge", [])
    for idx, turn in enumerate(turns):
        if turn["role"] != "assistant":
            continue
        text = turn["text"]
        for pattern in empty_patterns:
            try:
                regex = re.compile(pattern)
            except re.error as exc:
                raise ConfigError(f"global_rules.empty_challenge 正则错误：{pattern}（{exc}）") from exc
            for match in regex.finditer(text):
                if is_exempted(text, match.start(), match.end()):
                    continue
                violations.append(
                    violation(
                        "EMPTY_CHALLENGE",
                        "把空泛话当挑战定稿",
                        turn=idx,
                        detail=f"「{match.group(0)}」写在哪家医院都成立，等于没写；应换成具体科室/病种/数字。",
                        snippet_text=snippet(text, match.start(), match.end()),
                    )
                )

    # P05 之前把管理工具当推荐菜单罗列
    tool_cfg = global_rules.get("tool_menu") or {}
    tools = tool_cfg.get("tools") or []
    min_distinct = int(tool_cfg.get("min_distinct", 2))
    if tools:
        before_step = tool_cfg.get("before_step", "P05")
        boundary_position: int | None = None
        for cov in coverage:
            if cov["id"] == before_step and cov["position"] is not None:
                # 用该步区间起点（无标记贪心时落位轮可能晚于上一步提问轮）
                span = cov.get("span") or []
                boundary_position = span[0] if span else cov["position"]
                break
        for idx, turn in enumerate(turns):
            if turn["role"] != "assistant":
                continue
            if boundary_position is not None and idx >= boundary_position:
                continue
            text = turn["text"]
            found = sorted({name for name in tools if re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text)})
            if len(found) >= min_distinct:
                violations.append(
                    violation(
                        "TOOL_MENU_BEFORE_P05",
                        "P05 之前把管理工具当推荐菜单罗列",
                        turn=idx,
                        detail=(
                            f"P05 之前出现 {len(found)} 个管理工具（{'、'.join(found)}）；"
                            "原文批评「一道道端上来，像在念一份菜单」，工具应先服务业务目标。"
                        ),
                        snippet_text=None,
                    )
                )

    # 各步反例
    for step in steps:
        for anti_index, anti in enumerate(step["antis"]):
            for idx, turn in enumerate(turns):
                if turn["role"] != "assistant":
                    continue
                text = turn["text"]
                for match in anti.finditer(text):
                    if is_exempted(text, match.start(), match.end()):
                        continue
                    violations.append(
                        violation(
                            "ANTI_PATTERN",
                            f"反例命中：{step['id']}「{match.group(0)[:20]}」",
                            turn=idx,
                            detail=(
                                f"命中 {step['id']} 的反例正则 #{anti_index + 1}：{step['anti_src'][anti_index]}；"
                                "该步反例清单见 trigger-matrix.json。"
                            ),
                            snippet_text=snippet(text, match.start(), match.end()),
                        )
                    )

    return violations


# --------------------------------------------------------------------------
# 检查 D：编数字
# --------------------------------------------------------------------------
def canonical_number(token: str) -> str:
    token = token.replace(",", "")
    try:
        value = float(token)
        if value == int(value):
            return str(int(value))
        return repr(value)
    except ValueError:
        return token


def check_invented_numbers(turns: list[dict]) -> tuple[list[dict], dict]:
    provided: set[str] = set()
    for turn in turns:
        if turn["role"] != "user":
            continue
        for token in NUM_TOKEN_RE.findall(turn["text"]):
            provided.add(canonical_number(token))
    claims: list[dict] = []
    for idx, turn in enumerate(turns):
        if turn["role"] != "assistant":
            continue
        text = turn["text"]
        seen: set[tuple[int, str]] = set()
        for match in NUM_CLAIM_RE.finditer(text):
            token = match.group(1)
            key = (match.start(), token)
            if key in seen:
                continue
            seen.add(key)
            canon = canonical_number(token)
            if canon in provided:
                continue
            claims.append(
                {
                    "turn": idx,
                    "token": match.group(0).strip(),
                    "rule": "assistant 陈述的数字在用户输入里找不到",
                    "snippet": snippet(text, match.start(), match.end()),
                }
            )
    violations: list[dict] = []
    for claim in claims:
        violations.append(
            violation(
                "INVENTED_NUMBER",
                f"编数字预警：轮 {claim['turn']} 出现「{claim['token']}」",
                turn=claim["turn"],
                detail="该数字（含 %/人数/金额/床位等单位）用户从未提供过；应写【待补】并登记待补清单。",
                snippet_text=claim["snippet"],
            )
        )
    return claims, {"user_number_tokens": sorted(provided), "unprovided": claims}


# --------------------------------------------------------------------------
# 检查 E：gate 落盘
# --------------------------------------------------------------------------
def resolve_artifact_spans(text: str, strip_cfg: dict) -> list[tuple[int, int]]:
    """产物块位置：代码围栏 + 以产物前缀开头的连续块。"""
    spans: list[tuple[int, int]] = []
    for match in FENCE_RE.finditer(text):
        spans.append((match.start(), match.end()))
    prefixes = tuple(strip_cfg.get("block_prefixes") or ())
    offset = 0
    in_block = False
    block_start = 0
    for raw in text.splitlines(keepends=True):
        stripped = raw.strip()
        normalized = re.sub(r"^[#>*+\-\s]+", "", stripped)
        if not in_block:
            if prefixes and normalized.startswith(prefixes):
                in_block = True
                block_start = offset
        else:
            if stripped == "":
                spans.append((block_start, offset))
                in_block = False
        offset += len(raw)
    if in_block:
        spans.append((block_start, offset))
    return spans


def check_gate(turns: list[dict], steps: list[dict], coverage: list[dict],
               cfg: dict, review_mode: bool = False) -> tuple[list[dict], list[dict]]:
    strip_cfg = cfg.get("body_strip", {})
    window_extra = int(cfg.get("gate_window_turns", 2))
    turn_count = len(turns)
    position_by_id = {cov["id"]: cov for cov in coverage}
    results: list[dict] = []
    violations: list[dict] = []
    for step in steps:
        cov = position_by_id[step["id"]]
        record = {
            "id": step["id"],
            "gate": step["gate_src"],
            "position": cov["position"],
            "window": None,
            "landed": False,
            "hit_turn": None,
            "in_artifact": False,
            "skipped": False,
        }
        if review_mode:
            record["skipped"] = True
            record["skip_reason"] = "review 模式（体检/审稿）：体检表本身即落盘物，豁免 gate 检查"
            results.append(record)
            continue
        if cov["position"] is None:
            record["skipped"] = True
            record["skip_reason"] = "该步未落位（缺探针或乱序），无法检查 gate"
            results.append(record)
            continue
        span = cov["span"] or [cov["position"], cov["position"]]
        start = max(0, min(span))
        end = min(turn_count - 1, max(span) + window_extra)
        record["window"] = [start, end]
        best_hit = None
        for idx in range(start, end + 1):
            if turns[idx]["role"] != "assistant":
                continue
            text = turns[idx]["text"]
            match = step["gate"].search(text)
            if match is None:
                continue
            artifacts = resolve_artifact_spans(text, strip_cfg)
            in_artifact = any(a_start <= match.start() < a_end for a_start, a_end in artifacts)
            best_hit = {
                "turn": idx,
                "in_artifact": in_artifact,
                "snippet": snippet(text, match.start(), match.end()),
                "span": [match.start(), match.end()],
            }
            break
        if best_hit is None:
            violations.append(
                violation(
                    "GATE_NOT_LANDED",
                    f"gate 未落盘：{step['id']}",
                    turn=cov["position"],
                    detail=(
                        f"「{step['title']}」已触发，但产物关键词 gate=/{step['gate_src']}/ "
                        f"未在轮 {start}-{end} 出现——原文逻辑像只说了没落地。"
                    ),
                    snippet_text=None,
                )
            )
        else:
            record.update(
                landed=True,
                hit_turn=best_hit["turn"],
                in_artifact=best_hit["in_artifact"],
                hit_snippet=best_hit["snippet"],
            )
        results.append(record)
    return results, violations


# --------------------------------------------------------------------------
# 违规构造 / 报告
# --------------------------------------------------------------------------
def violation(code: str, rule: str, turn: int | None = None, detail: str = "",
              snippet_text: str | None = "") -> dict:
    return {
        "code": code,
        "severity": SEVERITY.get(code, "warning"),
        "rule": rule,
        "label": RULE_LABEL.get(code, code),
        "turn": turn,
        "detail": detail,
        "snippet": snippet_text or "",
    }


def build_report(transcript_path: Path, matrix_path: Path, turns: list[dict],
                 matrix: dict, coverage: list[dict], order_violations: list[dict],
                 violations: list[dict], discipline: dict, gate_results: list[dict],
                 numbers: dict, meta_mode: str = "coach",
                 transcript_meta: dict | None = None) -> dict:
    critical = [v for v in violations if v["severity"] == "critical"]
    warning = [v for v in violations if v["severity"] == "warning"]
    missing = [cov["id"] for cov in coverage if not cov["triggered"]]
    out_of_order = [item["step"] for item in order_violations]
    triggered_count = sum(1 for cov in coverage if cov["triggered"])
    passed = triggered_count == len(coverage) and not critical
    return {
        "checker": {"name": "check_transcript.py", "version": CHECKER_VERSION},
        "meta": {
            "transcript": str(transcript_path.resolve()),
            "matrix": str(matrix_path.resolve()),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "mode": meta_mode,
            "transcript_meta": transcript_meta or {},
            "turn_count": len(turns),
            "assistant_turn_count": sum(1 for t in turns if t["role"] == "assistant"),
        },
        "summary": {
            "mode": meta_mode,
            "total_steps": len(coverage),
            "triggered": f"{triggered_count}/{len(coverage)}",
            "triggered_count": triggered_count,
            "missing": missing,
            "out_of_order": out_of_order,
            "critical_count": len(critical),
            "warning_count": len(warning),
            "passed": passed,
            "exit_code": 0 if passed else 1,
        },
        "coverage": coverage,
        "order": {
            "out_of_order": order_violations,
            "missing": missing,
        },
        "discipline": discipline,
        "guards": {
            "banned_and_anti": [v for v in violations if v["code"] in ("BANNED_PHRASE", "ANTI_PATTERN", "EMPTY_CHALLENGE", "TOOL_MENU_BEFORE_P05")],
            "invented_numbers": [v for v in violations if v["code"] == "INVENTED_NUMBER"],
            "gate": gate_results,
        },
        "numbers": numbers,
        "violations": {"critical": critical, "warning": warning},
    }


def md_escape(text: str) -> str:
    return text.replace("|", "／").replace("\n", " ").strip()


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    meta = report["meta"]
    lines: list[str] = []
    verdict = "✅ 通过" if summary["passed"] else "❌ 未通过"
    lines.append("# 「医院战略规划」skill 会话校验报告")
    lines.append("")
    lines.append(f"- **结论**：{verdict}")
    lines.append(f"- **覆盖**：{summary['triggered']} 条建议触发；缺失 {summary['missing'] or '无'}；乱序 {summary['out_of_order'] or '无'}")
    lines.append(f"- **违规**：critical {summary['critical_count']} 项 / warning {summary['warning_count']} 项")
    mode = meta.get("mode", "coach")
    mode_label = "review（体检/审稿：11 行体检表同轮命中，gate 豁免）" if mode == "review" else "coach（从零/改稿：逐轮推进）"
    lines.append(f"- **模式**：{mode_label}")
    lines.append(f"- **transcript**：`{meta['transcript']}`")
    lines.append(f"- **矩阵**：`{meta['matrix']}`")
    lines.append(f"- **生成时间**：{meta['generated_at']}；轮次编号从 0 开始（turns 数组下标）")
    lines.append("")

    lines.append("## A. 覆盖与顺序（11 条建议）")
    lines.append("")
    lines.append("| 步 | 层 | 原文标题 | 触发 | 落位轮 | 对齐方式 | 探针命中轮 |")
    lines.append("|---|---|---|---|---|---|---|")
    for cov in report["coverage"]:
        turns_hit = sorted({turn for turn in cov.get("probe_turns", {}).values() if turn is not None})
        probe_turns = "，".join(f"轮{turn}" for turn in turns_hit) if turns_hit else "—"
        lines.append(
            "| {id} | {layer} | {title} | {triggered} | {position} | {mode} | {probe_turns} |".format(
                id=cov["id"],
                layer=cov["layer"],
                title=md_escape(cov["title"]),
                triggered="✅" if cov["triggered"] else "❌",
                position=cov["position"] if cov["position"] is not None else "—",
                mode=cov.get("mode") or "—",
                probe_turns=probe_turns,
            )
        )
    lines.append("")
    if summary["missing"] or summary["out_of_order"]:
        lines.append("**问题点**：")
        for cov in report["coverage"]:
            if not cov["triggered"]:
                lines.append(
                    f"- ❌ 缺 {cov['id']}（{cov['layer']}·{cov['title']}）：未命中探针 "
                    f"{'；'.join(cov.get('missing_probes') or ['—'])}"
                )
        for item in report["order"]["out_of_order"]:
            lines.append(
                f"- ❌ 乱序：{item['step']} 的探针在轮 {item['first_hit_turn']} 已全部出现，"
                f"但前序步骤 {item.get('prev_step')} 落位在轮 {item.get('prev_position')}"
            )
        lines.append("")

    lines.append("## B. 输出纪律")
    lines.append("")
    opening = report["discipline"]["opening"]
    limits = report["discipline"].get("limits", {})
    lines.append(
        f"- 开场（轮 {opening.get('turn')}）：正文 {opening.get('chars')} 汉字"
        f"（阈值 {limits.get('opening_char_limit', 80)}），"
        f"问号 {opening.get('questions')} 个 → {'✅' if opening.get('ok') else '❌'}"
    )
    lines.append("")
    lines.append("| 轮 | 正文汉字 | 问号 | 讲解句 | 项目符号 | 结论 |")
    lines.append("|---|---|---|---|---|---|")
    for turn in report["discipline"]["turns"]:
        if turn["role"] != "assistant":
            continue
        bad = "，".join(turn["violations"]) if turn["violations"] else "✅"
        lines.append(
            f"| {turn['turn']} | {turn['body_chars']} | {turn['questions']} | "
            f"{turn['explain_sentences']} | {turn['bullets']} | {bad} |"
        )
    lines.append("")

    lines.append("## C. 禁语与反例")
    lines.append("")
    guard_items = report["guards"]["banned_and_anti"]
    if guard_items:
        for item in guard_items:
            lines.append(f"- 【{item['severity']}】轮 {item['turn']}·{item['rule']}：{item['detail']}")
            if item.get("snippet"):
                lines.append(f"  - 片段：`{md_escape(item['snippet'])}`")
    else:
        lines.append("- ✅ 未命中禁语 / 反例 / 工具菜单 / 空泛挑战。")
    lines.append("")

    lines.append("## D. 编数字预警")
    lines.append("")
    number_items = report["guards"]["invented_numbers"]
    if number_items:
        for item in number_items:
            lines.append(f"- 【{item['severity']}】轮 {item['turn']}·{item['rule']}")
            if item.get("snippet"):
                lines.append(f"  - 片段：`{md_escape(item['snippet'])}`")
    else:
        lines.append("- ✅ assistant 未出现用户未提供的带单位数字。")
    lines.append("")

    lines.append("## E. gate 落盘")
    lines.append("")
    if report["meta"].get("mode") == "review":
        lines.append("- review 模式：11 行体检表本身就是落盘物，**gate 检查豁免**（下表全为 —，不计违规）。")
        lines.append("")
    lines.append("| 步 | 落位轮 | gate 关键词 | 是否落盘 | 命中轮 | 是否在产物块 |")
    lines.append("|---|---|---|---|---|---|")
    for item in report["guards"]["gate"]:
        landed = "✅" if item["landed"] else ("—" if item["skipped"] else "⚠️")
        lines.append(
            "| {id} | {position} | `{gate}` | {landed} | {hit} | {artifact} |".format(
                id=item["id"],
                position=item["position"] if item["position"] is not None else "—",
                gate=md_escape(item["gate"]),
                landed=landed,
                hit=item["hit_turn"] if item.get("hit_turn") is not None else "—",
                artifact=("是" if item.get("in_artifact") else "否") if item["landed"] else "—",
            )
        )
    lines.append("")

    lines.append("## 违规定级汇总")
    lines.append("")
    lines.append("### critical（影响退出码）")
    if report["violations"]["critical"]:
        for item in report["violations"]["critical"]:
            lines.append(
                f"- **{item['label']}**（轮 {item['turn'] if item['turn'] is not None else '—'}）：{item['rule']}"
            )
            if item["detail"]:
                lines.append(f"  - {item['detail']}")
            if item.get("snippet"):
                lines.append(f"  - 片段：`{md_escape(item['snippet'])}`")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("### warning（不阻断，--strict 时阻断）")
    if report["violations"]["warning"]:
        for item in report["violations"]["warning"]:
            lines.append(
                f"- **{item['label']}**（轮 {item['turn'] if item['turn'] is not None else '—'}）：{item['rule']}"
            )
            if item["detail"]:
                lines.append(f"  - {item['detail']}")
            if item.get("snippet"):
                lines.append(f"  - 片段：`{md_escape(item['snippet'])}`")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("---")
    lines.append("检查项口径见 `evals/README.md`；矩阵见 `evals/trigger-matrix.json`。")
    lines.append("")
    return "\n".join(lines)


def write_reports(report: dict, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run_check(transcript_path: Path, matrix_path: Path, strict: bool = False) -> dict:
    matrix = load_matrix(matrix_path)
    turns, transcript_meta = load_transcript(transcript_path)
    mode = detect_mode(transcript_meta)
    cfg = matrix.get("checker", {})
    steps = [compile_step(step) for step in matrix["steps"]]

    markers = build_markers(turns, cfg.get("step_marker_patterns", []))
    probe_hits = match_probes(turns, steps)
    coverage, order_violations = align_steps(turns, steps, markers, probe_hits, cfg, mode=mode)

    # 缺失步骤：找出「命中探针最多」的那一轮，报告里给原文片段
    for cov in coverage:
        if cov["triggered"]:
            continue
        counts: dict[int, int] = {}
        for hits in probe_hits.get(cov["id"], []):
            for turn_index in hits:
                counts[turn_index] = counts.get(turn_index, 0) + 1
        if counts:
            best_turn = max(counts, key=lambda t: (counts[t], -t))
            cov["best_partial"] = {
                "turn": best_turn,
                "matched": counts[best_turn],
                "total": len(probe_hits[cov["id"]]),
            }

    violations: list[dict] = []

    # A. 覆盖与顺序
    for cov in coverage:
        if not cov["triggered"]:
            hint = cov.get("note") or ""
            partial = cov.get("best_partial")
            if partial:
                partial_text = (
                    f"；最接近的是轮 {partial['turn']}（{partial['matched']}/{partial['total']} 个探针命中）"
                )
                partial_snippet = snippet(turns[partial["turn"]]["text"], 0, min(len(turns[partial["turn"]]["text"]), 48))
            else:
                partial_text = ""
                partial_snippet = None
            violations.append(
                violation(
                    "STEP_MISSING",
                    f"缺 {cov['id']}（{cov['layer']}·{cov['title']}）",
                    turn=partial["turn"] if partial else cov.get("declared_turn"),
                    detail=(
                        "未命中探针："
                        + "；".join(cov.get("missing_probes") or ["—"])
                        + (f"（{hint}）" if hint else "")
                        + partial_text
                    ),
                    snippet_text=partial_snippet,
                )
            )
    for item in order_violations:
        order_turn = item["first_hit_turn"]
        order_snippet = None
        if isinstance(order_turn, int) and 0 <= order_turn < len(turns) and turns[order_turn]["role"] == "assistant":
            order_snippet = snippet(turns[order_turn]["text"], 0, min(len(turns[order_turn]["text"]), 48))
        violations.append(
            violation(
                "STEP_OUT_OF_ORDER",
                f"乱序：{item['step']}",
                turn=order_turn,
                detail=(
                    f"{item['step']} 的探针在轮 {item['first_hit_turn']} 已全部出现，"
                    f"但前序步骤 {item.get('prev_step')} 落位在轮 {item.get('prev_position')}——"
                    "原文十一条顺序不可换（想清楚→做出来→讲明白）。"
                ),
                snippet_text=order_snippet,
            )
        )

    # B. 输出纪律 / C. 禁语与反例 / D. 编数字 / E. gate
    discipline, discipline_violations = check_discipline(turns, cfg)
    violations.extend(discipline_violations)
    violations.extend(check_banned_and_anti(turns, steps, coverage, matrix))
    number_claims, numbers_info = check_invented_numbers(turns)
    violations.extend(
        violation(
            "INVENTED_NUMBER",
            f"编数字预警：轮 {claim['turn']} 出现「{claim['token']}」",
            turn=claim["turn"],
            detail="该数字（含 %/人数/金额/床位等单位）用户从未提供过；应写【待补】并登记待补清单。",
            snippet_text=claim["snippet"],
        )
        for claim in number_claims
    )
    gate_results, gate_violations = check_gate(turns, steps, coverage, cfg, review_mode=(mode == "review"))
    violations.extend(gate_violations)

    # 按轮次排序，便于阅读
    violations.sort(key=lambda item: (item["turn"] if item["turn"] is not None else -1, item["code"]))

    report = build_report(
        transcript_path, matrix_path, turns, matrix, coverage, order_violations,
        violations, discipline, gate_results, numbers_info,
        meta_mode=mode, transcript_meta=transcript_meta,
    )
    if strict:
        report["summary"]["passed"] = report["summary"]["passed"] and not report["violations"]["warning"]
        report["summary"]["strict"] = True
        report["summary"]["exit_code"] = 0 if report["summary"]["passed"] else 1
    return report


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="「医院战略规划」skill 会话校验器：覆盖与顺序 / 输出纪律 / 禁语与反例 / 编数字 / gate 落盘",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("transcript", help="模拟会话 JSON 路径")
    parser.add_argument("--matrix", default=None, help=f"触发矩阵路径（默认 {DEFAULT_MATRIX}）")
    parser.add_argument("--json", dest="report_json", default=None, help="report.json 输出路径（默认 transcript 同目录 report.json）")
    parser.add_argument("--md", dest="report_md", default=None, help="report.md 输出路径（默认与 --json 同名的 .md）")
    parser.add_argument("--strict", action="store_true", help="warning 也视为不通过")
    parser.add_argument("--quiet", action="store_true", help="不打印摘要，只写报告")
    parser.add_argument("--version", action="version", version=f"check_transcript.py {CHECKER_VERSION}")
    args = parser.parse_args(argv)

    transcript_path = Path(args.transcript)
    matrix_path = Path(args.matrix) if args.matrix else DEFAULT_MATRIX
    report_json = Path(args.report_json) if args.report_json else transcript_path.parent / "report.json"
    report_md = Path(args.report_md) if args.report_md else report_json.with_suffix(".md")

    try:
        report = run_check(transcript_path, matrix_path, strict=args.strict)
    except (ConfigError, InputError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    write_reports(report, report_json, report_md)

    if not args.quiet:
        summary = report["summary"]
        verdict = "通过" if summary["passed"] else "不通过"
        print(f"[结论] {verdict}：触发 {summary['triggered']}；critical {summary['critical_count']}，warning {summary['warning_count']}")
        if summary["missing"]:
            print(f"[覆盖] 缺失：{'、'.join(summary['missing'])}")
        if summary["out_of_order"]:
            print(f"[覆盖] 乱序：{'、'.join(summary['out_of_order'])}")
        critical = report["violations"]["critical"]
        if critical:
            print("[critical]")
            for item in critical[:6]:
                print(f"  - {item['rule']}")
            if len(critical) > 6:
                print(f"  - …… 另有 {len(critical) - 6} 项，见报告")
        warning = report["violations"]["warning"]
        if warning:
            print("[warning]")
            for item in warning[:6]:
                print(f"  - {item['rule']}")
            if len(warning) > 6:
                print(f"  - …… 另有 {len(warning) - 6} 项，见报告")
        print(f"[报告] {report_json}")
        print(f"       {report_md}")

    return report["summary"]["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
