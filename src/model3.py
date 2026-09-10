"""问题 3：固定尺寸模型的烘干终止时刻。

沿用 Q2 方程（附录 3），把计算延伸到全体位置 X<0.15（model.md §9）。
复用 model2 的严格 60 s 间隔轨迹（results/tables/q2_60s.csv），
缺失时先运行 model2。
输出：data/附件3/result3.xlsx（完整 60 s 间隔行）与 t_dry^(3)（元数据，供后续表 5 提取）。
"""
import os

import pandas as pd

from xlsx_io import R_COLS, write_workbook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "results/tables/q2_meta.json")
CSV = os.path.join(ROOT, "results/tables/q2_60s.csv")


def run(N=321):
    # 由 model2 统一校验代码、附件、N、CSV 和工作簿，避免复用过期轨迹。
    import model2
    meta = model2.run(N=N, reuse=True)

    df = pd.read_csv(CSV)
    times = df["t"].to_numpy(dtype=float)
    Xphys = df[[f"X_{c}" for c in R_COLS]].to_numpy(dtype=float)

    out = os.path.join(ROOT, "data/附件3/result3.xlsx")
    write_workbook(out, [("Sheet1", R_COLS, times, Xphys)])
    print(f"[model3] 写入 {out}（{len(times)} 行，严格 60 s 间隔）")
    print(f"[model3] t_dry^(3) = {meta['t_dry']:.4f} s = {meta['t_dry']/3600:.4f} h（论文表 5 使用此值）")
    return meta


if __name__ == "__main__":
    run()
