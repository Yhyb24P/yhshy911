"""冻结后分析层验证：面积平均含水率与 Robin 边界通量平衡。"""
import json
from pathlib import Path

import numpy as np

from metrics import drying_rate_from_flux, weighted_mean_X
from props import DryingRoom, Radius
from solver import FVMSolver
from utils import atomic_json_dump, input_signature


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "tables" / "flux_balance.json"


def _signature(N, t_end, interval):
    return input_signature([
        __file__, ROOT / "src" / "metrics.py", ROOT / "src" / "solver.py",
        ROOT / "src" / "props.py", ROOT / "data" / "附件1.xlsx",
        ROOT / "data" / "附件2.xlsx",
    ], settings=(N, t_end, interval))


def flux_balance_check(N=81, t_end=43200.0, interval=60.0):
    """比较 -d X_bar/dt 与 2h_m(X_s-C_a)/R。"""
    print("== 平均含水率积分通量检查 ==")
    room = DryingRoom(ROOT / "data" / "附件1.xlsx")
    result = {}
    for q in (2, 4):
        radius = Radius(ROOT / "data" / "附件2.xlsx") if q == 4 else None
        solver = FVMSolver(q, room, N=N, radius=radius)
        times = np.arange(0.0, t_end + interval, interval)
        means = [weighted_mean_X(solver.X)]
        flux_rates = [drying_rate_from_flux(
            solver.surface()[1], room.Ca(0.0), float(solver.R_at(0.0)), solver.hM)]
        for t in times[1:]:
            solver.advance_to(float(t))
            means.append(weighted_mean_X(solver.X))
            flux_rates.append(drying_rate_from_flux(
                solver.surface()[1], room.Ca(t), float(solver.R_at(t)), solver.hM))
        numerical = -np.gradient(np.asarray(means), times, edge_order=2)
        flux_rates = np.asarray(flux_rates)
        # 中心差分跨越环境折点时不代表单侧瞬时通量，排除相邻点。
        mask = np.ones(len(times), dtype=bool)
        mask[[0, -1]] = False
        for knot in room.times:
            mask &= np.abs(times - knot) > interval
        absolute = np.abs(numerical[mask] - flux_rates[mask])
        relative = absolute / np.maximum(np.abs(flux_rates[mask]), 1e-12)
        result[q] = {"max_abs": float(absolute.max()),
                     "median_rel": float(np.median(relative)),
                     "p95_rel": float(np.percentile(relative, 95))}
        print(f"  Q{q}: max|ε_flux|={absolute.max():.3e} s^-1, "
              f"median rel={np.median(relative):.3e}, p95 rel={np.percentile(relative, 95):.3e}")
        if np.percentile(relative, 95) > 0.02:
            raise AssertionError(f"Q{q} 积分通量平衡误差过大")
    atomic_json_dump({"signature": _signature(N, t_end, interval),
                      "N": N, "t_end": t_end, "interval": interval,
                      "metrics": result}, OUT)
    print(f"[flux] 写入 {OUT}")
    return result


def audit():
    with open(OUT, encoding="utf-8") as f:
        data = json.load(f)
    if data["signature"] != _signature(data["N"], data["t_end"], data["interval"]):
        raise AssertionError("积分通量检查内容指纹已过期")
    return data


if __name__ == "__main__":
    flux_balance_check()
