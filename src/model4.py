"""问题 4：实测收缩驱动的移动域模型。

附录 4 物性 + 附件 2 实测半径 R(t)（PCHIP + 末端平台钳制，model.md §10）。
求解域为 ξ∈[0,1]；Excel 固定物理位置 r_j 在每时刻映射 ξ_j=r_j/R(t_n)，
越材位置（r_j>R(t_n)）写空值，末列恒为药材表面 X(ξ=1,t_n)（model.md §17.4）。
输出：data/附件3/result4.xlsx（完整 60 s 间隔行）；精确事件保存在元数据中。
"""
import json
import os
import time as _time

import numpy as np

from props import DryingRoom, Radius
from solver import FVMSolver, integrate_to_event, map_to_physical, surface_from_state
from xlsx_io import Q4_R_COLS, write_workbook
from utils import atomic_json_dump, input_signature, save_fig, setup_plot, staged_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "results/tables/q4_meta.json")
CSV = os.path.join(ROOT, "results/tables/q4_samples.csv")


def _signature(N):
    return input_signature([
        __file__, os.path.join(ROOT, "src/solver.py"),
        os.path.join(ROOT, "src/props.py"), os.path.join(ROOT, "src/xlsx_io.py"),
        os.path.join(ROOT, "data/附件1.xlsx"), os.path.join(ROOT, "data/附件2.xlsx"),
    ], settings=(N, 60.0))


def _row(Tcells, Xcells, t, room, rad):
    """某时刻的输出行：0–1.9 cm 固定位置 + 移动表面值。"""
    Rk = float(rad(t))
    mapped = map_to_physical(Xcells, np.array(Q4_R_COLS) * 1e-2, Rk)
    surf = surface_from_state(4, room, t, Tcells, Xcells, Rk)[1]
    return np.append(mapped, surf)


def run(N=321, reuse=True, plot=True):
    out = os.path.join(ROOT, "data/附件3/result4.xlsx")
    signature = _signature(N)
    if reuse and all(os.path.exists(p) for p in (META, CSV, out)):
        meta = json.load(open(META))
        if meta.get("N") == N and meta.get("signature") == signature:
            print(f"[model4] 复用已有结果：t_dry^(4)={meta['t_dry']:.2f} s（{meta['t_dry']/3600:.2f} h）")
            return meta

    if os.path.exists(META):
        os.remove(META)

    t_start = _time.time()
    room = DryingRoom(os.path.join(ROOT, "data/附件1.xlsx"))
    rad = Radius(os.path.join(ROOT, "data/附件2.xlsx"))
    s = FVMSolver(4, room, N=N, radius=rad)
    times, Ts, Xs, t_dry, T_ev, X_ev = integrate_to_event(s, 60.0)

    Xout = np.array([_row(Ts[k], Xs[k], times[k], room, rad) for k in range(len(times))])
    write_workbook(out, [("Sheet1", Q4_R_COLS + ["药材表面"], times, Xout)])
    print(f"[model4] 写入 {out}（{len(times)} 行 × {len(Q4_R_COLS)+1} 列，严格 60 s 间隔）")

    tab = os.path.join(ROOT, "results/tables")
    os.makedirs(tab, exist_ok=True)
    tmp_csv = staged_path(CSV)
    np.savetxt(tmp_csv,
               np.column_stack([times, Xout]),
               delimiter=",",
               header="t," + ",".join(f"X_{c}" for c in Q4_R_COLS) + ",X_surface",
               comments="", fmt="%.6f")
    os.replace(tmp_csv, CSV)

    meta = dict(N=N, signature=signature, t_dry=t_dry, n_rows=len(times),
                T_event=T_ev.tolist(), X_event=X_ev.tolist())
    atomic_json_dump(meta, META)
    print(f"[model4] t_dry^(4) = {t_dry:.2f} s = {t_dry/3600:.3f} h")

    if plot:
        import matplotlib.pyplot as plt
        setup_plot()
        fig, ax = plt.subplots()
        tgrid = np.arange(0, 259201, 1800)
        ax.plot(tgrid / 3600, rad(tgrid) * 1e2, label="measured R(t)")
        ax.axhline(1.198, color="gray", ls=":", lw=1)
        ax.set_xlabel("t / h")
        ax.set_ylabel("R / cm")
        ax.set_title("Q4 measured radius")
        ax.legend()
        save_fig(fig, "q4_radius")
        setup_plot()
        fig, ax = plt.subplots()
        ax.plot(np.array(times) / 3600, [x[0] for x in Xs], label="X_center")
        ax.axhline(0.15, color="red", ls="--", lw=1, label="criterion 0.15")
        ax.axvline(t_dry / 3600, color="gray", ls=":", lw=1)
        ax.set_xlabel("t / h")
        ax.set_ylabel("X_center (kg/kg)")
        ax.set_title(f"Q4 drying curve (t_dry={t_dry/3600:.2f} h)")
        ax.legend()
        save_fig(fig, "q4_drying_curve")

    print(f"[model4] 完成，耗时 {_time.time() - t_start:.1f} s")
    return meta


if __name__ == "__main__":
    run()
