"""冻结后分析验证：全时域积分通量闭合与终点品质网格收敛。"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from metrics import drying_rate_from_flux, weighted_mean_X
from props import DryingRoom, Radius
import quality_optimization as quality
from solver import FVMSolver
from utils import atomic_json_dump, input_signature


ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "results" / "tables"
OUT = TABLES / "flux_balance.json"
QUALITY_GRID_OUT = TABLES / "quality_grid_convergence.json"


def _signature(N, t_end, interval):
    return input_signature([
        __file__, ROOT / "src" / "metrics.py", ROOT / "src" / "solver.py",
        ROOT / "src" / "props.py", ROOT / "data" / "附件1.xlsx",
        ROOT / "data" / "附件2.xlsx",
    ], settings=("integral-flux-balance", N, t_end, interval))


def flux_balance_check(N=81, t_end=43200.0, interval=30.0):
    """验证 0–t_end 的累计面积平均含水率–边界通量积分闭合。"""
    print("== 全时域平均含水率积分通量闭合 ==")
    room = DryingRoom(ROOT / "data" / "附件1.xlsx")
    times = np.arange(0.0, t_end + 0.5 * interval, interval)
    if abs(times[-1] - t_end) > 1e-9:
        raise ValueError("t_end 必须是 interval 的整数倍")
    result = {}
    for q in (2, 4):
        radius = Radius(ROOT / "data" / "附件2.xlsx") if q == 4 else None
        solver = FVMSolver(q, room, N=N, radius=radius)
        means = [weighted_mean_X(solver.X)]
        flux_rates = [drying_rate_from_flux(
            solver.surface()[1], room.Ca(0.0), float(solver.R_at(0.0)), solver.hM)]
        for t in times[1:]:
            solver.advance_to(float(t))
            means.append(weighted_mean_X(solver.X))
            flux_rates.append(drying_rate_from_flux(
                solver.surface()[1], room.Ca(t), float(solver.R_at(t)), solver.hM))
        means = np.asarray(means)
        flux_rates = np.asarray(flux_rates)
        interval_flux = 0.5 * interval * (flux_rates[:-1] + flux_rates[1:])
        cumulative_flux = np.concatenate([[0.0], np.cumsum(interval_flux)])
        closure = means - means[0] + cumulative_flux
        interval_residual = np.diff(means) + interval_flux
        moisture_loss = means[0] - means[-1]
        scale = max(abs(float(moisture_loss)), 1e-12)
        pre_platform = times <= room.times[-1]
        metrics = {
            "final_abs_closure": abs(float(closure[-1])),
            "max_abs_closure": float(np.max(np.abs(closure))),
            "max_rel_to_12h_loss": float(np.max(np.abs(closure)) / scale),
            "max_interval_residual": float(np.max(np.abs(interval_residual))),
            "max_abs_closure_0_4h": float(np.max(np.abs(closure[pre_platform]))),
            "moisture_loss_0_12h": float(moisture_loss),
        }
        result[q] = metrics
        print(f"  Q{q}: max|E|={metrics['max_abs_closure']:.3e}, "
              f"max|E|/ΔX_12h={metrics['max_rel_to_12h_loss']:.3e}, "
              f"0–4h max|E|={metrics['max_abs_closure_0_4h']:.3e}")
        if metrics["max_rel_to_12h_loss"] > 1e-4:
            raise AssertionError(f"Q{q} 累计积分通量闭合误差过大")
    n_pre_platform = int(np.sum(times[1:] <= room.times[-1]))
    expected_pre_platform = int(round(room.times[-1] / interval))
    coverage = {
        "start_s": 0.0, "end_s": t_end, "sample_interval_s": interval,
        "n_intervals": len(times) - 1,
        "n_intervals_0_4h": n_pre_platform,
        "excluded_intervals": 0,
        "covers_all_0_4h_intervals": n_pre_platform == expected_pre_platform,
        "quadrature": "trapezoidal boundary-flux integral",
    }
    atomic_json_dump({"signature": _signature(N, t_end, interval),
                      "N": N, "t_end": t_end, "interval": interval,
                      "coverage": coverage, "metrics": result}, OUT)
    print(f"[flux] 写入 {OUT}（0–4 h 区间 {coverage['n_intervals_0_4h']} 个，未排除）")
    return result


def _quality_grid_signature(Ns, temperatures):
    return input_signature([
        __file__, ROOT / "src" / "quality_optimization.py",
        ROOT / "src" / "metrics.py", ROOT / "src" / "solver.py",
        ROOT / "src" / "props.py", ROOT / "data" / "附件1.xlsx",
        TABLES / "quality_pareto.csv", TABLES / "quality_pareto_meta.json",
    ], settings=("quality-grid", tuple(Ns), tuple(temperatures), 1.0))


def quality_grid_convergence(Ns=(321, 641), temperatures=(48.0, 50.165, 52.0), jobs=3):
    """只对三个代表温度验证 sigma_X(t_f) 的 N=321→641 误差。"""
    print("== 终点面积加权标准差网格收敛 ==")
    Ns = tuple(map(int, Ns))
    temperatures = tuple(map(float, temperatures))
    if Ns != (321, 641):
        raise ValueError("当前冻结协议固定比较 N=(321, 641)")

    with open(TABLES / "quality_pareto_meta.json", encoding="utf-8") as stream:
        meta = json.load(stream)
    settings = meta["temperature_C"]
    expected = quality._signature(
        meta["N"], settings["start"], settings["stop"], settings["step"],
        settings["measured_baseline"], meta["hm_factors"])
    if meta["N"] != 321 or meta["signature"] != expected:
        raise AssertionError("N=321 正式品质扫描缺失或指纹已过期")
    base = pd.read_csv(TABLES / "quality_pareto.csv")

    rows = []
    for temperature in temperatures:
        matched = base[(np.isclose(base["T_platform_C"], temperature, atol=1e-10))
                       & np.isclose(base["hm_factor"], 1.0)]
        if len(matched) != 1:
            raise AssertionError(f"N=321 品质扫描缺少 T={temperature:g} °C")
        row = matched.iloc[0]
        rows.append({"T_platform_C": temperature, "N": 321,
                     "t_dry_s": float(row["t_dry_s"]),
                     "X_std_event": float(row["X_std_event"]),
                     "X_max_event": float(row["X_max_event"])})

    tasks = [(641, temperature, 1.0) for temperature in temperatures]
    jobs = max(1, min(int(jobs), len(tasks)))
    if jobs == 1:
        evaluated = map(quality._evaluate_scenario, tasks)
    else:
        executor = ProcessPoolExecutor(max_workers=jobs)
        evaluated = executor.map(quality._evaluate_scenario, tasks)
    try:
        for index, (record, _profiles) in enumerate(evaluated, 1):
            rows.append({"T_platform_C": record["T_platform_C"], "N": 641,
                         "t_dry_s": record["t_dry_s"],
                         "X_std_event": record["X_std_event"],
                         "X_max_event": record["X_max_event"]})
            print(f"  [{index}/{len(tasks)}] T={record['T_platform_C']:6.3f} °C, "
                  f"N=641: t_f={record['t_dry_h']:.4f} h, "
                  f"sigma={record['X_std_event']:.9f}", flush=True)
    finally:
        if jobs != 1:
            executor.shutdown()

    comparisons = []
    for temperature in temperatures:
        coarse = next(row for row in rows
                      if row["N"] == 321 and row["T_platform_C"] == temperature)
        fine = next(row for row in rows
                    if row["N"] == 641 and row["T_platform_C"] == temperature)
        comparisons.append({
            "T_platform_C": temperature,
            "delta_t_s_641_minus_321": fine["t_dry_s"] - coarse["t_dry_s"],
            "delta_sigma_641_minus_321": fine["X_std_event"] - coarse["X_std_event"],
            "delta_sigma_abs": abs(fine["X_std_event"] - coarse["X_std_event"]),
        })
    baseline = settings["measured_baseline"]
    sigma_base = next(row["X_std_event"] for row in rows
                      if row["N"] == 321 and row["T_platform_C"] == baseline)
    sigma_52 = next(row["X_std_event"] for row in rows
                    if row["N"] == 321 and row["T_platform_C"] == 52.0)
    sigma_base_fine = next(row["X_std_event"] for row in rows
                           if row["N"] == 641 and row["T_platform_C"] == baseline)
    sigma_52_fine = next(row["X_std_event"] for row in rows
                         if row["N"] == 641 and row["T_platform_C"] == 52.0)
    change_coarse = sigma_52 - sigma_base
    change_fine = sigma_52_fine - sigma_base_fine
    signal = abs(change_coarse)
    uncertainty = max(item["delta_sigma_abs"] for item in comparisons)
    resolution_ratio = uncertainty / max(signal, 1e-30)
    direction_consistent = bool(change_coarse * change_fine > 0.0)
    conclusion = {
        "sigma_signal_baseline_to_52": signal,
        "sigma_change_52_minus_baseline_N321": change_coarse,
        "sigma_change_52_minus_baseline_N641": change_fine,
        "max_grid_delta_sigma": uncertainty,
        "grid_delta_to_signal_ratio": resolution_ratio,
        "direction_consistent": direction_consistent,
        "uniformity_change_resolved": bool(direction_consistent and resolution_ratio < 0.25),
        "resolution_rule": "same change direction on N=321/641 and max |sigma_641-sigma_321| < 0.25 * |sigma_321(52)-sigma_321(baseline)|",
    }
    payload = {"signature": _quality_grid_signature(Ns, temperatures),
               "Ns": list(Ns), "temperatures_C": list(temperatures),
               "event_interval_s": quality.EVENT_INTERVAL,
               "rows": rows, "comparisons": comparisons, "conclusion": conclusion}
    atomic_json_dump(payload, QUALITY_GRID_OUT)
    print(f"[quality-grid] max δsigma={uncertainty:.3e}, "
          f"baseline→52 signal={signal:.3e}, ratio={resolution_ratio:.2f}, "
          f"resolved={conclusion['uniformity_change_resolved']}")
    print(f"[quality-grid] 写入 {QUALITY_GRID_OUT}")
    return payload


def audit_flux():
    with open(OUT, encoding="utf-8") as stream:
        data = json.load(stream)
    if data["signature"] != _signature(data["N"], data["t_end"], data["interval"]):
        raise AssertionError("积分通量检查内容指纹已过期")
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality-grid", action="store_true",
                        help="追加三个代表温度的 N=321/641 品质指标收敛")
    parser.add_argument("--jobs", type=int, default=min(3, os.cpu_count() or 1))
    parser.add_argument("--flux-interval", type=float, default=30.0)
    args = parser.parse_args()
    flux_balance_check(interval=args.flux_interval)
    if args.quality_grid:
        quality_grid_convergence(jobs=args.jobs)


if __name__ == "__main__":
    main()
