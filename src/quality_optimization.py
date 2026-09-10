"""平台温度的干燥时间–终点均匀性多目标情景扫描。

主 PDE 和生产求解器保持不变。每个情景仅替换附件 1 观测结束后的平台
温度，终点品质直接由 N 个 FVM 控制体场计算。这里的第一目标称为干燥
效率（终止时间），不解释为缺少设备功率数据时无法定义的总能耗。
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from metrics import moisture_range, weighted_mean_X, weighted_std_X
from props import DryingRoom, HM, R0
from solver import FVMSolver, map_to_physical, surface_from_state
from utils import atomic_json_dump, input_signature, staged_path


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "tables" / "quality_pareto.csv"
PROFILES = ROOT / "results" / "tables" / "quality_profiles.csv"
META = ROOT / "results" / "tables" / "quality_pareto_meta.json"
EVENT_INTERVAL = 1.0


class PlatformTemperatureRoom(DryingRoom):
    """附件观测区间不变，仅替换 4 h 后的平台温度。"""

    def __init__(self, path, platform_temperature):
        super().__init__(path)
        self.platform_temperature = float(platform_temperature)

    def Ta(self, t):
        a = np.asarray(t, dtype=float)
        measured = np.interp(a, self.times, self.Ta_data)
        out = np.where(a <= self.times[-1], measured, self.platform_temperature)
        return float(out) if out.ndim == 0 else out


def pareto_mask(objectives):
    """最小化目标的非支配点掩码；相同目标点均保留。"""
    values = np.asarray(objectives, dtype=float)
    if values.ndim != 2 or values.shape[1] < 2 or not np.isfinite(values).all():
        raise ValueError("objectives 必须是有限二维数组")
    keep = np.ones(len(values), dtype=bool)
    for i, point in enumerate(values):
        dominated = np.all(values <= point, axis=1) & np.any(values < point, axis=1)
        keep[i] = not np.any(dominated)
    return keep


def compromise_index(objectives, mask):
    """返回 Pareto 集中归一化后距理想点最近的方案索引。"""
    values = np.asarray(objectives, dtype=float)
    indices = np.flatnonzero(mask)
    front = values[indices]
    span = np.ptp(front, axis=0)
    normalized = (front - front.min(axis=0)) / np.where(span > 0, span, 1.0)
    return int(indices[np.argmin(np.linalg.norm(normalized, axis=1))])


def _temperatures(start, stop, step, baseline):
    count = int(round((stop - start) / step))
    if step <= 0 or abs(start + count * step - stop) > 1e-9:
        raise ValueError("温度范围必须可被 step 整除")
    return sorted(set(np.round(np.linspace(start, stop, count + 1), 10)) | {float(baseline)})


def _signature(N, start, stop, step, baseline, hm_factors=(1.0,)):
    return input_signature([
        __file__, ROOT / "src" / "metrics.py", ROOT / "src" / "solver.py",
        ROOT / "src" / "props.py", ROOT / "data" / "附件1.xlsx",
    ], settings=(N, start, stop, step, baseline, tuple(hm_factors), EVENT_INTERVAL))


def _atomic_csv(df, path):
    tmp = staged_path(path)
    try:
        df.to_csv(tmp, index=False, float_format="%.10g", lineterminator="\n")
        Path(tmp).replace(path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _formal_event(solver):
    """复现 model2 的逐秒推进与事件括区，不保存中间场。"""
    k = 0
    checkpoint = solver.clone()
    while True:
        k += 1
        solver.advance_to(EVENT_INTERVAL * k)
        if solver.g() <= 0.0:
            # 从最近的整分钟快照只重放最后不足 60 步，获得穿越前完整
            # BDF2 状态；避免在约 20 万个逐秒步上反复复制 321-cell 场。
            replay = checkpoint.clone()
            first = int(round(checkpoint.t / EVENT_INTERVAL)) + 1
            for j in range(first, k):
                replay.advance_to(EVENT_INTERVAL * j)
            lo_solver = replay.clone()
            replay.advance_to(EVENT_INTERVAL * k)
            return replay.refine_event(lo_solver, EVENT_INTERVAL * k)
        if k % int(round(60.0 / EVENT_INTERVAL)) == 0:
            checkpoint = solver.clone()


def _evaluate_scenario(task):
    """进程工作单元：独立求解一个平台温度/传质能力情景。"""
    N, platform, factor = task
    room = PlatformTemperatureRoom(ROOT / "data" / "附件1.xlsx", platform)
    solver = FVMSolver(2, room, N=N, hM=HM * factor)
    t_dry, T_event, X_event = _formal_event(solver)
    X_event = np.asarray(X_event)
    surface = surface_from_state(2, room, t_dry, T_event, X_event, R0,
                                 hM=HM * factor)[1]
    field_with_surface = np.append(X_event, surface)
    r_profile = np.linspace(0.0, R0, 101)
    profile = map_to_physical(X_event, r_profile, R0)
    profile[-1] = surface
    scenario = (f"T{platform:.3f}".rstrip("0").rstrip(".")
                + f"_hm{factor:.3f}".rstrip("0").rstrip("."))
    record = {
        "scenario": scenario,
        "T_platform_C": platform,
        "hm_factor": factor,
        "t_dry_s": t_dry,
        "t_dry_h": t_dry / 3600.0,
        "X_mean_event": weighted_mean_X(X_event),
        "X_std_event": weighted_std_X(X_event),
        "X_range_event": moisture_range(field_with_surface),
        "X_surface_event": surface,
        "X_min_event": field_with_surface.min(),
        "X_max_event": field_with_surface.max(),
    }
    profiles = [{"scenario": scenario, "T_platform_C": platform,
                 "hm_factor": factor, "r_cm": r * 100.0, "X_event": x}
                for r, x in zip(r_profile, profile)]
    return record, profiles


def run(N=321, start=48.0, stop=52.0, step=0.25, hm_factors=(1.0,),
        reuse=True, jobs=1):
    base_room = DryingRoom(ROOT / "data" / "附件1.xlsx")
    baseline = float(base_room.Ta_end)
    hm_factors = tuple(sorted(set(map(float, hm_factors)) | {1.0}))
    if any(f <= 0 for f in hm_factors):
        raise ValueError("h_m 倍率必须为正")
    signature = _signature(N, start, stop, step, baseline, hm_factors)
    if reuse and OUT.exists() and PROFILES.exists() and META.exists():
        with open(META, encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("signature") == signature:
            print(f"[quality] 复用 {OUT}")
            return pd.read_csv(OUT)

    started = time.time()
    temperatures = _temperatures(start, stop, step, baseline)
    scenarios = [(N, platform, factor)
                 for platform in temperatures for factor in hm_factors]
    jobs = max(1, min(int(jobs), len(scenarios)))
    if jobs == 1:
        evaluated = map(_evaluate_scenario, scenarios)
    else:
        executor = ProcessPoolExecutor(max_workers=jobs)
        evaluated = executor.map(_evaluate_scenario, scenarios)
    records, profiles = [], []
    try:
        for index, (record, scenario_profiles) in enumerate(evaluated, 1):
            record["is_baseline"] = (
                abs(record["T_platform_C"] - baseline) < 1e-10
                and record["hm_factor"] == 1.0)
            records.append(record)
            profiles.extend(scenario_profiles)
            print(f"  [{index:02d}/{len(scenarios)}] "
                  f"T_plat={record['T_platform_C']:6.3f} °C  "
                  f"h_m×{record['hm_factor']:g}  t_f={record['t_dry_h']:7.3f} h  "
                  f"sigma={record['X_std_event']:.6f}", flush=True)
    finally:
        if jobs != 1:
            executor.shutdown()

    df = pd.DataFrame(records).sort_values("T_platform_C").reset_index(drop=True)
    objectives = df[["t_dry_h", "X_std_event"]].to_numpy()
    mask = pareto_mask(objectives)
    df["is_pareto"] = mask
    representative = np.full(len(df), "", dtype=object)
    labels = (
        (int(np.argmin(df["t_dry_h"])), "fastest"),
        (int(np.argmin(df["X_std_event"])), "most_uniform"),
        (compromise_index(objectives, mask), "compromise"),
    )
    for idx, label in labels:
        representative[idx] = "+".join(filter(None, (representative[idx], label)))
    df["representative"] = representative

    profile_df = pd.DataFrame(profiles)
    profile_df = profile_df.merge(df[["scenario", "is_pareto", "representative"]],
                                  on="scenario", how="left", validate="many_to_one")
    _atomic_csv(df, OUT)
    _atomic_csv(profile_df, PROFILES)
    meta = {
        "N": N,
        "signature": signature,
        "temperature_C": {"start": start, "stop": stop, "step": step,
                          "measured_baseline": baseline},
        "hm_factors": list(hm_factors),
        "n_scenarios": len(df),
        "n_pareto": int(mask.sum()),
        "files": [OUT.name, PROFILES.name],
    }
    atomic_json_dump(meta, META)
    print(f"[quality] 写入 {OUT} 与 {PROFILES}，耗时 {time.time()-started:.1f} s")
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--N", type=int, default=321)
    parser.add_argument("--start", type=float, default=48.0)
    parser.add_argument("--stop", type=float, default=52.0)
    parser.add_argument("--step", type=float, default=0.25)
    parser.add_argument("--hm-factors", default="1.0",
                        help="逗号分隔的边界传质能力倍率；例如 0.75,1,1.25")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1),
                        help="并行情景进程数；默认最多使用 4 个 CPU 核")
    args = parser.parse_args()
    factors = tuple(float(value) for value in args.hm_factors.split(","))
    run(args.N, args.start, args.stop, args.step, factors,
        reuse=not args.force, jobs=args.jobs)


if __name__ == "__main__":
    main()
