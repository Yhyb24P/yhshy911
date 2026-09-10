"""审计冻结后派生指标、品质扫描与 Pareto 结果。"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import quality_optimization as quality
import validate_metrics
import visualize


ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "results" / "tables"


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run():
    with open(TABLES / "flux_balance.json", encoding="utf-8") as f:
        flux = json.load(f)
    _assert(flux["signature"] == validate_metrics._signature(
        flux["N"], flux["t_end"], flux["interval"]),
        "积分通量检查内容指纹已过期")
    expected_pre_platform = int(round(14400.0 / flux["interval"]))
    _assert(flux["coverage"]["start_s"] == 0
            and flux["coverage"]["end_s"] >= 43200
            and flux["coverage"]["excluded_intervals"] == 0
            and flux["coverage"]["covers_all_0_4h_intervals"]
            and flux["coverage"]["n_intervals_0_4h"] == expected_pre_platform,
            "积分通量检查未覆盖前 4 h 全部区间")
    for q, values in flux["metrics"].items():
        _assert(values["max_rel_to_12h_loss"] <= 1e-4
                and values["max_abs_closure_0_4h"] >= 0,
                f"Q{q} 积分通量检查未通过")

    with open(TABLES / "quality_pareto_meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    settings = meta["temperature_C"]
    signature = quality._signature(
        meta["N"], settings["start"], settings["stop"], settings["step"],
        settings["measured_baseline"], meta["hm_factors"])
    _assert(meta["signature"] == signature, "品质扫描内容指纹已过期")
    df = pd.read_csv(TABLES / "quality_pareto.csv")
    profiles = pd.read_csv(TABLES / "quality_profiles.csv")
    required = {
        "scenario", "T_platform_C", "hm_factor", "t_dry_s", "t_dry_h", "X_mean_event",
        "X_std_event", "X_range_event", "X_surface_event", "X_min_event",
        "X_max_event", "is_baseline", "is_pareto", "representative",
    }
    _assert(required <= set(df.columns), "quality_pareto.csv 字段不完整")
    _assert(len(df) == meta["n_scenarios"], "品质扫描情景数与元数据不一致")
    _assert(df["scenario"].is_unique, "品质扫描情景名称不唯一")
    _assert(np.isfinite(df.select_dtypes(include=[np.number])).all().all(),
            "品质扫描包含非有限数值")
    _assert((df["X_std_event"] >= 0).all(), "面积加权标准差出现负值")
    _assert((df["X_min_event"] <= df["X_mean_event"]).all()
            and (df["X_mean_event"] <= df["X_max_event"]).all(),
            "事件平均含水率不在场值范围内")
    _assert(np.allclose(df["X_range_event"],
                        df["X_max_event"] - df["X_min_event"], atol=1e-10),
            "含水率极差字段不一致")
    _assert(np.allclose(df["X_max_event"], 0.15, atol=2e-8),
            "至少一个情景未准确定位 X_max=0.15 事件")
    _assert(df["is_baseline"].sum() == 1, "实测平台基准方案应恰有一个")
    with open(TABLES / "q2_meta.json", encoding="utf-8") as f:
        q2_meta = json.load(f)
    baseline_event = float(df.loc[df["is_baseline"], "t_dry_s"].iloc[0])
    _assert(abs(baseline_event - q2_meta["t_dry"]) < 0.01,
            "品质扫描基准事件与正式 Q3 事件不一致")

    expected_pareto = quality.pareto_mask(df[["t_dry_h", "X_std_event"]])
    _assert(np.array_equal(df["is_pareto"].to_numpy(bool), expected_pareto),
            "Pareto 标记与支配关系重算不一致")
    _assert(int(expected_pareto.sum()) == meta["n_pareto"], "Pareto 点数错误")
    toy = np.array([[1.0, 1.0], [2.0, 2.0], [0.8, 1.2], [1.2, 0.8]])
    _assert(np.array_equal(quality.pareto_mask(toy), [True, False, True, True]),
            "Pareto 支配逻辑自检失败")

    _assert(set(profiles["scenario"]) == set(df["scenario"]), "终点剖面情景不完整")
    counts = profiles.groupby("scenario").size()
    _assert((counts == 101).all(), "每个终点剖面应包含 101 个物理半径点")
    _assert(profiles.groupby("scenario")["r_cm"].min().eq(0).all()
            and profiles.groupby("scenario")["r_cm"].max().eq(2).all(),
            "终点剖面必须覆盖中心至表面")
    _assert(df["representative"].fillna("").str.contains("fastest").any()
            and df["representative"].fillna("").str.contains("most_uniform").any()
            and df["representative"].fillna("").str.contains("compromise").any(),
            "缺少最快、最均匀或折中代表方案")

    with open(TABLES / "quality_grid_convergence.json", encoding="utf-8") as f:
        quality_grid = json.load(f)
    Ns = tuple(quality_grid["Ns"])
    temperatures = tuple(quality_grid["temperatures_C"])
    _assert(quality_grid["signature"] ==
            validate_metrics._quality_grid_signature(Ns, temperatures),
            "品质指标网格收敛指纹已过期")
    _assert(Ns == (321, 641) and len(quality_grid["rows"]) == 6,
            "品质指标网格收敛配置或行数错误")
    _assert(temperatures == (48.0, 50.165, 52.0)
            and len(quality_grid["comparisons"]) == 3,
            "品质指标网格收敛温度配置错误")
    _assert(all(abs(row["X_max_event"] - 0.15) <= 2e-8
                for row in quality_grid["rows"]),
            "品质指标网格收敛存在未定位到阈值的事件")
    for comparison in quality_grid["comparisons"]:
        rows = [row for row in quality_grid["rows"]
                if row["T_platform_C"] == comparison["T_platform_C"]]
        coarse = next(row for row in rows if row["N"] == 321)
        fine = next(row for row in rows if row["N"] == 641)
        signed_delta = fine["X_std_event"] - coarse["X_std_event"]
        _assert(abs(comparison["delta_sigma_641_minus_321"] - signed_delta) < 1e-14
                and abs(comparison["delta_sigma_abs"] - abs(signed_delta)) < 1e-14,
                "品质标准差网格差重算不一致")
    changes = {}
    for N in Ns:
        changes[N] = (next(row["X_std_event"] for row in quality_grid["rows"]
                           if row["N"] == N and row["T_platform_C"] == 52.0)
                      - next(row["X_std_event"] for row in quality_grid["rows"]
                             if row["N"] == N and row["T_platform_C"] == 50.165))
    signal = abs(changes[321])
    max_grid_delta = max(item["delta_sigma_abs"]
                         for item in quality_grid["comparisons"])
    resolution = quality_grid["conclusion"]
    _assert(abs(resolution["sigma_signal_baseline_to_52"] - signal) < 1e-14
            and abs(resolution["sigma_change_52_minus_baseline_N321"]
                    - changes[321]) < 1e-14
            and abs(resolution["sigma_change_52_minus_baseline_N641"]
                    - changes[641]) < 1e-14
            and abs(resolution["max_grid_delta_sigma"] - max_grid_delta) < 1e-14
            and abs(resolution["grid_delta_to_signal_ratio"]
                    - max_grid_delta / signal) < 1e-12
            and resolution["direction_consistent"] == (changes[321] * changes[641] > 0)
            and resolution["uniformity_change_resolved"]
            == (changes[321] * changes[641] > 0 and max_grid_delta / signal < 0.25),
            "品质指标可辨识结论与原始网格数据不一致")
    visualization_meta = TABLES / "visualization_meta.json"
    if visualization_meta.exists():
        with open(visualization_meta, encoding="utf-8") as f:
            visual = json.load(f)
        _assert(visual["signature"] == visualize._signature(), "可视化内容指纹已过期")
        for name, expected in visual["source_sha256"].items():
            _assert(_sha256(TABLES / name) == expected,
                    f"品质分析文件内容校验失败：{name}")
        for name in visual["files"]:
            path = ROOT / "results" / "figures" / name
            _assert(path.exists() and path.stat().st_size > 1000,
                    f"可视化文件缺失或异常：{name}")
            _assert(_sha256(path) == visual["output_sha256"][name],
                    f"可视化文件内容校验失败：{name}")
    print(f"[通过] 品质分析：{len(df)} 个情景，{expected_pareto.sum()} 个非支配点；"
          f"品质网格误差/温度信号={resolution['grid_delta_to_signal_ratio']:.2f}，"
          f"可辨识={resolution['uniformity_change_resolved']}")


if __name__ == "__main__":
    run()
