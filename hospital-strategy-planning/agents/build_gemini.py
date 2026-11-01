# -*- coding: utf-8 -*-
"""Generate agents/gemini.toml from agents/system-prompt.md.

Usage: python agents/build_gemini.py
Keeps the Gemini CLI custom command in sync with the portable system prompt.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "system-prompt.md")
DST = os.path.join(HERE, "gemini.toml")

body = io.open(SRC, "r", encoding="utf-8").read().strip()
# TOML multiline basic strings: escape backslash and triple quotes only.
body = body.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')

header = (
    "# Gemini CLI custom command for hospital-strategy-planning.\n"
    "# Install: copy to ~/.gemini/commands/hospital-strategy.toml, then type /hospital-strategy.\n"
    "# Generated from system-prompt.md; regenerate with: python agents/build_gemini.py\n\n"
    'description = "医院战略规划教练：按张琨十一条建议，一次一问引导公立医院完成/体检战略规划"\n\n'
    'prompt = """\n'
)
footer = '\n\n用户请求：\n{{args}}\n"""\n'

io.open(DST, "w", encoding="utf-8", newline="\n").write(header + body + footer)
print("written:", DST, len(body), "chars")
