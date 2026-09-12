"""将论文所引用的图件同步为根目录 results/figures 的实际项目产物。

论文目录中的图件只是编译副本；本脚本不以其内容为输入。表格由
build_tables.py 从 results/tables/paper_table*.csv 独立重建。
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper"
SOURCE = ROOT / "results" / "figures"


def main() -> None:
    tex = (PAPER / "main.tex").read_text(encoding="utf-8")
    refs = sorted(set(re.findall(r"includegraphics\[[^\]]*\]\{([^}]+)\}", tex)))
    for ref in refs:
        rel = Path(ref)
        if rel.parent != Path("figures"):
            raise ValueError(f"图件引用不在 figures/ 下：{ref}")
        copied = False
        for ext in (".pdf", ".png"):
            src = SOURCE / f"{rel.name}{ext}"
            if not src.exists():
                continue
            dst = PAPER / f"{ref}{ext}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied = True
            print(f"SYNC {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")
        if not copied:
            raise FileNotFoundError(f"本地项目未产生论文图件：{ref}")


if __name__ == "__main__":
    main()
