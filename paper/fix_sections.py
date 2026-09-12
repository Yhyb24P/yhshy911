"""一次性修复：去掉章节标题中的手写编号（模板类自动编号）。"""
import io
import re

p = "paper/main.tex"
t = io.open(p, encoding="utf-8").read()

old = re.findall(r"\\subsection\{[^}]*\}", t)
t = re.sub(r"\\subsection\{\d+\.\d+\s+", r"\\subsection{", t)
new = re.findall(r"\\subsection\{[^}]*\}", t)

io.open(p, "w", encoding="utf-8").write(t)
print("BEFORE:", old)
print("AFTER :", new)
