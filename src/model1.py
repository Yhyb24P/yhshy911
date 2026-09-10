"""问题 1：预热平衡阶段（0–1800 s）。

附录 2 常物性 + D1(X)，共边界驱动的双场并行模型（model.md §7）。
输出：data/附件3/result1.xlsx（温度/水分浓度两个工作表，t=1..1800 s，4 位小数）。
"""
import os
import time as _time

import numpy as np

from props import DryingRoom
from solver import FVMSolver
from xlsx_io import R_COLS, write_workbook
from utils import atomic_json_dump, input_signature, save_fig, setup_plot, staged_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "results/tables/q1_meta.json")


def _signature(N):
    return input_signature([
        __file__, os.path.join(ROOT, "src/solver.py"),
        os.path.join(ROOT, "src/props.py"), os.path.join(ROOT, "src/xlsx_io.py"),
        os.path.join(ROOT, "data/附件1.xlsx"),
    ], settings=(N, 0.03125, 1.0, 1800.0))


def run(N=2561, plot=True):
    t_start = _time.time()
    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
    # t=1 s 表面边界层厚度仅约 0.007 cm；P0 收敛验证表明需使用更细的
    # Q1 专用网格和初始时间步，才能稳定到题目要求的四位小数。
    s = FVMSolver(1, room, N=N, dt_cap=0.03125)
    r_phys = np.array(R_COLS) * 1e-2

    times = np.arange(1, 1801, dtype=int)
    Tmat = np.empty((len(times), len(R_COLS)))
    Xmat = np.empty_like(Tmat)
    for k, t in enumerate(times):
        s.advance_to(float(t))
        T, X, _ = s.sample(r_phys)
        Tmat[k], Xmat[k] = T, X
        if (k + 1) % 300 == 0:
            Ts, Xs = s.surface()
            print(f"  t={t:>5d} s   T_s={Ts:8.3f} °C   X_s={Xs:8.4f}", flush=True)

    out = os.path.join(ROOT, "data/附件3/result1.xlsx")
    write_workbook(out, [
        ("温度", R_COLS, times, Tmat),
        ("水分浓度", R_COLS, times, Xmat),
    ])
    print(f"[model1] 写入 {out}（{len(times)} 行 × {len(R_COLS)} 列 × 2 工作表）")

    tab = os.path.join(ROOT, "results/tables")
    os.makedirs(tab, exist_ok=True)
    csv_path = os.path.join(tab, "q1_samples.csv")
    tmp_csv = staged_path(csv_path)
    np.savetxt(tmp_csv,
               np.column_stack([times, Tmat, Xmat]),
               delimiter=",",
               header="t," + ",".join(f"T_{c}" for c in R_COLS)
                      + "," + ",".join(f"X_{c}" for c in R_COLS),
               comments="", fmt="%.4f")
    os.replace(tmp_csv, csv_path)
    atomic_json_dump({"N": N, "signature": _signature(N), "n_rows": len(times)}, META)

    if plot:
        import matplotlib.pyplot as plt
        r_cm = np.array(R_COLS)
        setup_plot()
        fig, ax = plt.subplots()
        for t_show in (600, 1200, 1800):
            ax.plot(r_cm, Tmat[t_show - 1], marker="o", ms=3, label=f"t={t_show} s")
        ax.set_xlabel("r / cm")
        ax.set_ylabel("T / °C")
        ax.set_title("Q1 temperature distribution")
        ax.legend()
        save_fig(fig, "q1_temperature")
        setup_plot()
        fig, ax = plt.subplots()
        for t_show in (600, 1200, 1800):
            ax.plot(r_cm, Xmat[t_show - 1], marker="o", ms=3, label=f"t={t_show} s")
        ax.set_xlabel("r / cm")
        ax.set_ylabel("X (kg/kg)")
        ax.set_title("Q1 moisture distribution")
        ax.legend()
        save_fig(fig, "q1_moisture")

    print(f"[model1] 完成，耗时 {_time.time() - t_start:.1f} s")
    return dict(times=times, T=Tmat, X=Xmat)


if __name__ == "__main__":
    run()
