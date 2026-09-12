"""从 results/tables/paper_table*.csv 生成 paper/tables.tex（论文表 1–6）。

生成结果由 main.tex 通过 \\input{tables.tex} 引入；重新运行本脚本即可与
results/tables 中的正式表格保持同步，避免手工誊抄数字。
"""
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(ROOT, "results", "tables")
OUT = os.path.join(ROOT, "paper", "tables.tex")

# 标题与题注（表 1–6 对应题目要求的六张表）
TABLES = {
    1: ("预热平衡阶段不同时刻的温度分布", "单位：\\si{}"),  # placeholder, replaced below
}

CAPTIONS = {
    1: "预热阶段不同时刻的温度分布（单位：℃）",
    2: "预热阶段不同时刻的干基含水率分布（单位：$\\mathrm{kg\\,kg^{-1}}$）",
    3: "烘干前 3 小时不同时刻的温度分布（单位：℃）",
    4: "烘干前 3 小时不同时刻的干基含水率分布（单位：$\\mathrm{kg\\,kg^{-1}}$）",
    5: "固定半径工况代表性时刻的干基含水率（单位：$\\mathrm{kg\\,kg^{-1}}$）",
    6: "收缩工况代表性时刻的干基含水率（单位：$\\mathrm{kg\\,kg^{-1}}$）",
}

# 仅表 5、6 含代表性时刻和连续终止事件，须在表内说明采样口径。
NOTES = {
    5: ("表中每 6 h 取样；末行为连续事件定位得到的精确烘干终止时刻，"
        "不是 60 s 规则输出时间点。"),
    6: ("表中每 6 h 取样；0--1.5 cm 为固定物理坐标，空白表示该位置已位于"
        "收缩后药材外部；“药材表面”为移动坐标 $r=R(t)$。末行为连续事件"
        "定位得到的精确烘干终止时刻。"),
}

LABELS = {
    1: "tab:t1", 2: "tab:t2", 3: "tab:t3",
    4: "tab:t4", 5: "tab:t5", 6: "tab:t6",
}


def _escape(s):
    """转义 LaTeX 特殊字符（表中仅出现中文、数字与括号，保守处理）。"""
    return (s.replace("\\", r"\textbackslash{}")
             .replace("&", r"\&").replace("%", r"\%")
             .replace("#", r"\#").replace("_", r"\_"))


def _fmt_num(x):
    """数值列固定四位小数；空单元格（收缩工况越材位置）保持为空。"""
    x = x.strip()
    if not x:
        return ""
    try:
        return f"{float(x):.4f}"
    except ValueError:
        return _escape(x)  # 如「烘干结束时间（57.1904 h）」行的时间标签


def _fmt_time(x):
    """时间列：整数不带小数，小数保留原样。"""
    x = x.strip()
    try:
        v = float(x)
        return f"{v:g}" if v == int(v) else f"{v:g}"
    except ValueError:
        return _escape(x)


def build_table(idx):
    path = os.path.join(CSV_DIR, f"paper_table{idx}.csv")
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [row for row in csv.reader(f) if row]
    header, data = rows[0], rows[1:]
    ncols = len(header)

    lines = []
    lines.append("\\begin{table}[htbp]")
    lines.append("\\centering")
    lines.append(f"\\caption{{{CAPTIONS[idx]}}}")
    lines.append(f"\\label{{{LABELS[idx]}}}")
    # 时间列左对齐，数值列居中（四位小数等宽）
    lines.append("\\begin{tabular}{l" + "c" * (ncols - 1) + "}")
    lines.append("\\toprule")
    lines.append(" & ".join(_escape(h) for h in header) + r" \\")
    lines.append("\\midrule")
    for row in data:
        cells = [_fmt_time(row[0])] + [_fmt_num(c) for c in row[1:]]
        lines.append(" & ".join(cells) + r" \\")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    if idx in NOTES:
        lines.append(r"\parbox{0.88\linewidth}{\footnotesize\textit{注：}" + NOTES[idx] + "}")
    lines.append("\\end{table}")
    return "\n".join(lines)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    parts = [build_table(i) for i in (1, 2, 3, 4, 5, 6)]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("% 自动生成：python paper/build_tables.py（勿手工编辑）\n")
        f.write("\n\n".join(parts))
        f.write("\n")
    # 同时输出单表文件，供 main.tex 在各小节分别引入
    for i, part in zip((1, 2, 3, 4, 5, 6), parts):
        single = os.path.join(ROOT, "paper", "tables", f"t{i}.tex")
        with open(single, "w", encoding="utf-8") as f:
            f.write("% 自动生成：python paper/build_tables.py（勿手工编辑）\n")
            f.write(part)
            f.write("\n")
    print(f"[build_tables] 写入 {OUT} 与 paper/tables/t1..t6.tex")


if __name__ == "__main__":
    main()
